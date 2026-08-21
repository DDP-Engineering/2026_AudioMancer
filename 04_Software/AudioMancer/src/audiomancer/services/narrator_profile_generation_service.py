#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file narrator_profile_generation_service.py
@brief AI-assisted text-only narrator profile generation for AudioMancer.
@details Analyzes the current book text with one configured AI profile, appends
         editable narrator voice-designer prompts and preview text, and stores
         resumable attempt state in the authoritative Narrator Voice document.
"""

# IMPORTS

import hashlib
import json
from pathlib import Path
import random
import re

from audiomancer import config
from audiomancer.services import (
    ai_budget_service,
    ai_translation_service,
    chunking_document_service,
    cleanup_metadata_service,
    llm_provider_service,
    narrator_definition_service,
    prompt_template_service,
    token_usage_service,
    tts_budget_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    emit_progress_update,
    raise_if_cancelled,
)
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

# @brief Component logger used by the narrator profile generation workflow.
_NARRATOR_PROFILE_GENERATION_LOGGER = get_component_logger("narrator_profile_generation")

# @brief Stable source token for approved translated chunk input.
SOURCE_TRANSLATED_CHUNKS = "approved_translation"

# @brief Stable source token for canonical chunking input.
SOURCE_CANONICAL_CHUNKS = "canonical_chunks"

# @brief Stable source token for cleaned-text paragraph metadata input.
SOURCE_CLEANED_METADATA = "cleaned_metadata"

# @brief Stable source token for plain cleaned text fallback input.
SOURCE_CLEANED_TEXT = "cleaned_text"

# @brief Stable operation-mode token for AI-generated narrator profiles.
NARRATOR_PROFILE_GENERATION_MODE_AI_ASSISTED = "ai_assisted"

# @brief In-memory narrator-profile-generation result payload type.
NarratorProfileGenerationReportPayload = dict[str, object]

# @brief Derived narrator-profile-generation operation-state view type.
OperationStatePayload = dict[str, object]

# @brief Runtime text unit consumed by the profile-generation workflow.
SourceUnitPayload = dict[str, object]

_STYLE_OBSERVATION_FIELDS = (
    "genre",
    "tone",
    "pacing",
    "narrator_distance",
    "emotional_range",
    "diction",
    "worldbuilding_cues",
    "themes",
    "narration_risks",
)

_STYLE_SUMMARY_TERM_LIMITS = {
    "genre": 8,
    "tone": 12,
    "pacing": 10,
    "narrator_distance": 8,
    "emotional_range": 12,
    "diction": 12,
    "worldbuilding_cues": 12,
    "themes": 16,
    "narration_risks": 12,
}


# PUBLIC API


@trace_function(_NARRATOR_PROFILE_GENERATION_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Derive the narrator profile generation state from the authoritative document.
    @param[in]  project_root Active project root folder.
    @return     Derived operation-state payload or `None` before an AI attempt.
    @exception  narrator_definition_service.NarratorVoiceDocumentContractError Raised for invalid data.
    """
    document = narrator_definition_service.load_narrator_voice_document(project_root)
    if document["status"] == narrator_definition_service.NARRATOR_VOICE_STATUS_NOT_STARTED:
        return None
    resume = document["resume"]
    completed_windows = int(resume["completed_window_count"]) if isinstance(resume, dict) else 0
    total_windows = int(resume["total_window_count"]) if isinstance(resume, dict) else 0
    return {
        "status": document["status"],
        "mode": NARRATOR_PROFILE_GENERATION_MODE_AI_ASSISTED,
        "progress_current": completed_windows,
        "progress_total": total_windows + 1 if total_windows else 0,
        "warning_count": 0,
        "metadata": {
            "token_usage": dict(document["token_usage"]),
            "budget_metadata": dict(document["budget_metadata"]),
            "additional_profile_instructions": document["additional_profile_instructions"],
        },
        "resume_checkpoint": None if resume is None else dict(resume),
    }


@trace_function(_NARRATOR_PROFILE_GENERATION_LOGGER)
def generate_narrator_profiles(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    profile_count: int,
    voice_language: str,
    progress_callback=None,
    cancel_requested=None,
    additional_profile_instructions: str | None = None,
) -> NarratorProfileGenerationReportPayload:
    """
    @brief      Generate and append editable text-only narrator profiles.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  profile_count Requested narrator profile count.
    @param[in]  voice_language Selected audiobook voice language code.
    @param[in]  progress_callback Optional progress callback for the modal dialog.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  additional_profile_instructions Optional operator-supplied profile-generation rules.
    @return     Persisted narrator profile generation report.
    @exception  ValueError Raised on invalid input, missing source text, or invalid AI output.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    _ = manifest
    resolved_project_root = Path(project_root)
    requested_count = _normalized_profile_count(profile_count)
    normalized_voice_language = narrator_definition_service.narrator_language_code(voice_language)
    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    if not profile_id or not model_name or not base_url:
        raise ValueError("Narrator profile generation requires a valid enabled AI profile.")

    prompt_template_service.validate_required_prompts(
        [
            "narrator_profile_style_system",
            "narrator_profile_style_window_user",
            "narrator_profile_generation_user",
        ]
    )
    source_units, source_token, _ = _resolve_source_units(resolved_project_root, normalized_voice_language)
    input_fingerprint = _build_input_fingerprint(source_units, source_token, normalized_voice_language)
    system_prompt = prompt_template_service.render_prompt("narrator_profile_style_system", {})
    existing_state = load_operation_state(resolved_project_root) or {}
    additional_profile_instructions = _resolve_additional_profile_instructions(
        additional_profile_instructions,
        existing_state,
    )
    additional_profile_instructions_fingerprint = _compute_prompt_fingerprint(additional_profile_instructions)
    budget_metadata = _build_budget_metadata(ai_profile_payload, system_prompt, additional_profile_instructions)
    windows = _build_source_windows(source_units, budget_metadata)
    if not windows:
        raise ValueError("Narrator profile generation requires at least one readable text window.")

    allocation = _gender_allocation(requested_count)
    model_settings = _build_model_settings(ai_profile_payload, budget_metadata)
    total_progress = len(windows) + 1
    resume_state = _restore_resume_state(
        existing_state,
        resolved_project_root,
        input_fingerprint=input_fingerprint,
        profile_id=profile_id,
        requested_count=requested_count,
        source_token=source_token,
        total_window_count=len(windows),
        budget_metadata=budget_metadata,
        model_settings=model_settings,
        additional_profile_instructions_fingerprint=additional_profile_instructions_fingerprint,
    )
    started_at = _utc_now_iso()
    log_path = _resolve_log_path(resolved_project_root, started_at)
    if resume_state["resume_compatible"]:
        token_usage = token_usage_service.restore_token_usage(resume_state["token_usage"])
        allocation = dict(resume_state["gender_allocation"])
        observations = [dict(item) for item in resume_state["style_observations"]]
        completed_window_count = int(resume_state["completed_window_count"])
    else:
        token_usage = token_usage_service.empty_token_usage()
        observations: list[dict[str, object]] = []
        completed_window_count = 0

    _write_operation_state(
        resolved_project_root,
        status="running",
        profile_id=profile_id,
        source_token=source_token,
        requested_count=requested_count,
        gender_allocation=allocation,
        input_fingerprint=input_fingerprint,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        model_settings=model_settings,
        style_observations=observations,
        total_window_count=len(windows),
        additional_profile_instructions=additional_profile_instructions,
    )
    emit_progress_update(
        progress_callback,
        completed_window_count,
        total_progress,
        "Analyzing narrator style...",
        token_usage=token_usage,
    )

    def _write_interrupted_state(status: str) -> None:
        """
        @brief      Persist the current resumable checkpoint after an interrupted run.
        @param[in]  status Terminal interrupted status to persist.
        @return     None.
        @exception  None
        """
        _write_operation_state(
            resolved_project_root,
            status=status,
            profile_id=profile_id,
            source_token=source_token,
            requested_count=requested_count,
            gender_allocation=allocation,
            input_fingerprint=input_fingerprint,
            token_usage=token_usage,
            budget_metadata=budget_metadata,
            model_settings=model_settings,
            style_observations=observations,
            total_window_count=len(windows),
            additional_profile_instructions=additional_profile_instructions,
        )

    for window_index, window_units in enumerate(windows, start=1):
        if window_index <= completed_window_count:
            continue
        try:
            raise_if_cancelled(cancel_requested)
        except OperationCancelledError:
            _write_interrupted_state("cancelled")
            raise
        user_prompt = _render_narrator_profile_prompt(
            "narrator_profile_style_window_user",
            {
                "units_block": _build_units_block(window_units),
                "additional_profile_instructions": additional_profile_instructions,
            },
        )
        try:
            response_result = llm_provider_service.chat_json(
                ai_profile_payload,
                system_prompt,
                user_prompt,
                log_path=log_path,
                log_context={
                    "operation_kind": "narrator_profile_generation",
                    "stage_label": "style_window",
                    "profile_id": profile_id,
                    "window_index": window_index,
                    "window_total": len(windows),
                },
                cancel_requested=cancel_requested,
            )
        except OperationCancelledError as error:
            _write_interrupted_state("cancelled")
            raise OperationCancelledError(
                "Narrator profile generation cancelled while waiting for the model response."
            ) from error
        except Exception:
            _write_interrupted_state("failed")
            raise
        try:
            token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
            observations.append(_normalize_style_observation(response_result.get("payload"), window_index))
        except Exception:
            _write_interrupted_state("failed")
            raise
        _write_operation_state(
            resolved_project_root,
            status="running",
            profile_id=profile_id,
            source_token=source_token,
            requested_count=requested_count,
            gender_allocation=allocation,
            input_fingerprint=input_fingerprint,
            token_usage=token_usage,
            budget_metadata=budget_metadata,
            model_settings=model_settings,
            style_observations=observations,
            total_window_count=len(windows),
            additional_profile_instructions=additional_profile_instructions,
        )
        emit_progress_update(
            progress_callback,
            window_index,
            total_progress,
            "Analyzing narrator style...",
            token_usage=token_usage,
        )

    try:
        raise_if_cancelled(cancel_requested)
    except OperationCancelledError:
        _write_interrupted_state("cancelled")
        raise
    style_summary = _build_style_observation_summary(observations)
    user_prompt = _render_narrator_profile_prompt(
        "narrator_profile_generation_user",
        {
            "voice_language": narrator_definition_service.narrator_language_label(normalized_voice_language),
            "profile_count": requested_count,
            "male_count": int(allocation["male"]),
            "female_count": int(allocation["female"]),
            "random_gender_count": int(allocation["random"]),
            "style_observations": json.dumps(style_summary, indent=2, ensure_ascii=False),
            "additional_profile_instructions": additional_profile_instructions,
        },
    )
    try:
        response_result = llm_provider_service.chat_json(
            ai_profile_payload,
            system_prompt,
            user_prompt,
            log_path=log_path,
            log_context={
                "operation_kind": "narrator_profile_generation",
                "stage_label": "profile_generation",
                "profile_id": profile_id,
                "requested_count": requested_count,
            },
            cancel_requested=cancel_requested,
        )
    except OperationCancelledError as error:
        _write_interrupted_state("cancelled")
        raise OperationCancelledError(
            "Narrator profile generation cancelled while waiting for the model response."
        ) from error
    except Exception:
        _write_interrupted_state("failed")
        raise
    try:
        token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
        raw_response_payload = response_result.get("payload", {})
        response_payload = dict(raw_response_payload) if isinstance(raw_response_payload, dict) else {}
        validated_profiles, preview_warnings = _validated_generated_profiles(
            response_payload,
            requested_count,
            allocation,
            normalized_voice_language,
        )
    except Exception:
        _write_interrupted_state("failed")
        raise
    created_profiles = narrator_definition_service.append_ai_generated_profiles(
        resolved_project_root,
        validated_profiles,
        persist=False,
    )
    generated_profile_ids = [str(profile.get("profile_id", "")) for profile in created_profiles]
    report_payload = {
        "narrator_profile_generation_mode": NARRATOR_PROFILE_GENERATION_MODE_AI_ASSISTED,
        "ai_profile_id": profile_id,
        "model_settings": model_settings,
        "source": source_token,
        "source_unit_count": len(source_units),
        "input_fingerprint": input_fingerprint,
        "requested_count": requested_count,
        "gender_allocation": allocation,
        "generated_profile_ids": generated_profile_ids,
        "generated_profile_count": len(generated_profile_ids),
        "style_brief": str(response_payload.get("style_brief", "")).strip(),
        "style_summary": style_summary,
        "budget_metadata": budget_metadata,
        "warning_count": len(preview_warnings),
        "warnings": list(preview_warnings),
        "token_usage": token_usage,
        "additional_profile_instructions": additional_profile_instructions,
        "additional_profile_instructions_fingerprint": additional_profile_instructions_fingerprint,
    }
    narrator_document = narrator_definition_service.load_narrator_voice_document(resolved_project_root)
    narrator_document["profiles"] = [*narrator_document["profiles"], *created_profiles]
    narrator_document["status"] = narrator_definition_service.NARRATOR_VOICE_STATUS_COMPLETED
    narrator_document["token_usage"] = token_usage_service.coerce_token_usage(token_usage)
    narrator_document["budget_metadata"] = dict(budget_metadata)
    narrator_document["additional_profile_instructions"] = additional_profile_instructions
    narrator_document["resume"] = None
    narrator_definition_service.write_narrator_voice_document(resolved_project_root, narrator_document)
    emit_progress_update(
        progress_callback,
        total_progress,
        total_progress,
        "Narrator profiles generated.",
        token_usage=token_usage,
    )
    return report_payload


# LOCAL HELPERS


def _normalized_profile_count(profile_count: int) -> int:
    """
    @brief      Normalize one requested narrator profile count.
    @param[in]  profile_count Candidate requested profile count.
    @return     Profile count inside the supported range.
    @exception  ValueError Raised when the requested count is invalid.
    """
    try:
        requested_count = int(profile_count)
    except (TypeError, ValueError) as error:
        raise ValueError("Narrator profile count must be a number.") from error
    if requested_count < 1 or requested_count > config.MAX_NARRATOR_PROFILE_GENERATION_COUNT:
        raise ValueError(
            f"Narrator profile count must be between 1 and {config.MAX_NARRATOR_PROFILE_GENERATION_COUNT}."
        )
    return requested_count


def _gender_allocation(profile_count: int) -> dict[str, object]:
    """
    @brief      Build the requested male/female/random narrator split.
    @param[in]  profile_count Requested narrator profile count.
    @return     Gender-allocation metadata payload.
    @exception  None
    """
    male_count = profile_count // 2
    female_count = profile_count // 2
    random_count = profile_count - male_count - female_count
    random_gender = random.choice(("male", "female")) if random_count else ""
    if random_gender == "male":
        male_count += random_count
    elif random_gender == "female":
        female_count += random_count
    return {
        "male": male_count,
        "female": female_count,
        "random": random_count,
        "random_gender": random_gender,
    }


def _resolve_source_units(
    project_root: Path,
    voice_language: str,
) -> tuple[list[SourceUnitPayload], str, Path]:
    """
    @brief      Resolve the best narrator-profile analysis text for the selected voice language.
    @param[in]  project_root Active project root folder.
    @param[in]  voice_language Selected audiobook voice language code.
    @return     Source units, source token, and backing artifact path.
    @exception  ValueError Raised when no readable book text exists.
    """
    translated_units = _approved_translation_units(project_root, voice_language)
    if translated_units:
        return translated_units, SOURCE_TRANSLATED_CHUNKS, project_root / config.TRANSLATED_CHUNKS_FILE_NAME

    chunk_units = _canonical_chunk_units(project_root)
    if chunk_units:
        return chunk_units, SOURCE_CANONICAL_CHUNKS, project_root / config.CHUNK_ARTIFACT_FILE_NAME

    metadata_units = _cleaned_metadata_units(project_root)
    if metadata_units:
        return metadata_units, SOURCE_CLEANED_METADATA, project_root / config.CLEANUP_DOCUMENT_FILE_NAME

    cleaned_text_path = project_root / config.CLEANED_TEXT_FILE_NAME
    cleaned_text = cleaned_text_path.read_text(encoding="utf-8") if cleaned_text_path.is_file() else ""
    if cleaned_text.strip():
        records = cleanup_metadata_service.build_paragraph_records_from_text(cleaned_text)
        if records:
            return _paragraph_units(records), SOURCE_CLEANED_TEXT, cleaned_text_path
    raise ValueError("Run cleanup or chunking before generating narrator profiles.")


def _approved_translation_units(project_root: Path, voice_language: str) -> list[SourceUnitPayload]:
    """
    @brief      Return approved translated chunks when they match the selected voice language.
    @param[in]  project_root Active project root folder.
    @param[in]  voice_language Selected audiobook voice language code.
    @return     Ordered translated source units or an empty list.
    @exception  None
    """
    document = ai_translation_service.load_translation_document(project_root)
    if document is None:
        return []
    target_language = narrator_definition_service.narrator_language_code(document["target_language"])
    if target_language != narrator_definition_service.narrator_language_code(voice_language):
        return []
    if not ai_translation_service.translation_is_completed(project_root):
        return []
    units: list[SourceUnitPayload] = []
    for index, chunk in enumerate(ai_translation_service.load_translated_chunks(project_root), start=1):
        if not bool(chunk.get("approved", False)):
            return []
        text = str(chunk.get("translated_text", "")).strip()
        if text:
            units.append(_source_unit(str(chunk.get("chunk_id", f"translated-{index:04d}")), index, text))
    return units


def _canonical_chunk_units(project_root: Path) -> list[SourceUnitPayload]:
    """
    @brief      Return canonical chunking output as narrator analysis units.
    @param[in]  project_root Active project root folder.
    @return     Ordered source units or an empty list.
    @exception  None
    """
    chunks = sorted(
        chunking_document_service.load_chunks(project_root),
        key=lambda item: int(item.get("sequence_index", 0) or 0),
    )
    units = []
    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("text", "")).strip()
        if text:
            units.append(_source_unit(str(chunk.get("chunk_id", f"chunk-{index:04d}")), index, text))
    return units


def _cleaned_metadata_units(project_root: Path) -> list[SourceUnitPayload]:
    """
    @brief      Return cleaned-text metadata paragraphs as narrator analysis units.
    @param[in]  project_root Active project root folder.
    @return     Ordered source units or an empty list.
    @exception  None
    """
    metadata_payload = cleanup_metadata_service.load_cleanup_metadata(project_root)
    if not isinstance(metadata_payload, dict):
        return []
    cleaned_text_path = project_root / config.CLEANED_TEXT_FILE_NAME
    if not cleaned_text_path.is_file():
        return []
    cleaned_text = cleaned_text_path.read_text(encoding="utf-8")
    if not cleaned_text.strip():
        return []
    return _paragraph_units(cleanup_metadata_service.load_or_build_paragraph_records(project_root, cleaned_text))


def _paragraph_units(records: list[dict[str, object]]) -> list[SourceUnitPayload]:
    """
    @brief      Convert cleaned paragraph records to narrator analysis units.
    @param[in]  records Cleaned paragraph records.
    @return     Ordered source units.
    @exception  None
    """
    units = []
    for index, record in enumerate(records, start=1):
        text = str(record.get("text", "")).strip()
        if text:
            units.append(_source_unit(str(record.get("paragraph_id", f"paragraph-{index:04d}")), index, text))
    return units


def _source_unit(unit_id: str, sequence_index: int, text: str) -> SourceUnitPayload:
    """
    @brief      Build one normalized source unit.
    @param[in]  unit_id Stable source unit identifier.
    @param[in]  sequence_index One-based source order.
    @param[in]  text Source unit text.
    @return     Source-unit payload.
    @exception  None
    """
    return {
        "unit_id": str(unit_id).strip() or f"unit-{sequence_index:04d}",
        "sequence_index": int(sequence_index),
        "text": str(text).strip(),
    }


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    system_prompt: str,
    additional_profile_instructions: str = "",
) -> dict[str, int]:
    """
    @brief      Build context-window budget metadata for narrator profile generation.
    @param[in]  ai_profile_payload Selected AI profile payload.
    @param[in]  system_prompt Rendered system prompt.
    @param[in]  additional_profile_instructions Optional operator-supplied profile-generation rules.
    @return     Context-budget metadata.
    @exception  ValueError Raised when too little input room remains.
    """
    style_prompt_shell = _render_narrator_profile_prompt(
        "narrator_profile_style_window_user",
        {
            "units_block": "",
            "additional_profile_instructions": additional_profile_instructions,
        },
    )
    generation_prompt_shell = _render_narrator_profile_prompt(
        "narrator_profile_generation_user",
        {
            "voice_language": "",
            "profile_count": 0,
            "male_count": 0,
            "female_count": 0,
            "random_gender_count": 0,
            "style_observations": "",
            "additional_profile_instructions": additional_profile_instructions,
        },
    )
    style_budget = ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{style_prompt_shell}",
        config.DEFAULT_NARRATOR_PROFILE_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_NARRATOR_PROFILE_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_NARRATOR_PROFILE_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_NARRATOR_PROFILE_MIN_TEXT_BUDGET_TOKENS,
        "AI narrator profile generation cannot run because the selected AI profile context window "
        "and max output tokens leave too little room for style input",
        online_text_context_fraction=config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION,
    )
    generation_prompt_budget_tokens = ai_budget_service.estimate_text_tokens(
        f"{system_prompt}\n\n{generation_prompt_shell}"
    )
    return {
        **style_budget,
        "style_window_size": (
            0
            if ai_budget_service.uses_online_text_budget(ai_profile_payload)
            else config.DEFAULT_NARRATOR_PROFILE_STYLE_WINDOW_SIZE
        ),
        "generation_prompt_budget_tokens": generation_prompt_budget_tokens,
    }


def _render_narrator_profile_prompt(prompt_name: str, variables: dict[str, object]) -> str:
    """
    @brief      Render one narrator-profile prompt with optional operator rules.
    @param[in]  prompt_name Prompt template identifier.
    @param[in]  variables Prompt variables.
    @return     Rendered narrator-profile prompt.
    @exception  None
    """
    template = prompt_template_service.load_prompt(prompt_name)
    placeholder_names = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", template))
    rendered_prompt = prompt_template_service.render_prompt(
        prompt_name,
        {key: value for key, value in variables.items() if key in placeholder_names},
    )
    additional_profile_instructions = _normalized_additional_profile_instructions(
        variables.get("additional_profile_instructions")
    )
    if additional_profile_instructions and "additional_profile_instructions" not in placeholder_names:
        rendered_prompt = _append_additional_profile_instructions(
            rendered_prompt,
            additional_profile_instructions,
        )
    return rendered_prompt


def _resolve_additional_profile_instructions(
    additional_profile_instructions: str | None,
    existing_state: dict[str, object],
) -> str:
    """
    @brief      Resolve operator rules for a new or resumed narrator-profile generation run.
    @param[in]  additional_profile_instructions New operator instructions or None when resuming.
    @param[in]  existing_state Existing narrator-definition operation state.
    @return     Normalized operator profile-generation instructions.
    @exception  None
    """
    if additional_profile_instructions is not None:
        return _normalized_additional_profile_instructions(additional_profile_instructions)
    if existing_state.get("mode") != NARRATOR_PROFILE_GENERATION_MODE_AI_ASSISTED or str(
        existing_state.get("status", "")
    ) not in {
        "running",
        "failed",
        "cancelled",
    }:
        return ""
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return ""
    return _normalized_additional_profile_instructions(metadata.get("additional_profile_instructions"))


def _normalized_additional_profile_instructions(value: object) -> str:
    """
    @brief      Normalize optional operator narrator-profile rules for prompts and state storage.
    @param[in]  value Candidate instruction text.
    @return     Trimmed instruction text.
    @exception  None
    """
    if value is None:
        return ""
    return str(value).strip()


def _append_additional_profile_instructions(prompt_text: str, additional_profile_instructions: str) -> str:
    """
    @brief      Append operator narrator-profile rules to one rendered prompt.
    @param[in]  prompt_text Rendered prompt template text.
    @param[in]  additional_profile_instructions Normalized operator rules.
    @return     Prompt text with an additional-rules section.
    @exception  None
    """
    if not additional_profile_instructions:
        return prompt_text
    return (
        f"{prompt_text.rstrip()}\n\n"
        f"Additional operator narrator profile instructions:\n{additional_profile_instructions}\n"
    )


def _compute_prompt_fingerprint(prompt_text: str) -> str:
    """
    @brief      Compute a stable fingerprint for operator-supplied prompt rules.
    @param[in]  prompt_text Operator prompt-rule text.
    @return     SHA-256 fingerprint for the prompt-rule text.
    @exception  None
    """
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def _build_source_windows(
    source_units: list[SourceUnitPayload],
    budget_metadata: dict[str, int],
) -> list[list[SourceUnitPayload]]:
    """
    @brief      Build budgeted source windows for style analysis.
    @param[in]  source_units Ordered source units.
    @param[in]  budget_metadata Context-budget metadata.
    @return     Ordered source windows.
    @exception  ValueError Raised when one source unit cannot fit the request budget.
    """
    if not source_units:
        return []
    max_window_units = int(budget_metadata.get("style_window_size", 0) or 0)
    if max_window_units <= 0:
        max_window_units = len(source_units)
    text_budget_tokens = int(budget_metadata["text_budget_tokens"])
    windows: list[list[SourceUnitPayload]] = []
    start_index = 0
    while start_index < len(source_units):
        end_index = start_index - 1
        current_tokens = 0
        current_count = 0
        while end_index + 1 < len(source_units) and current_count < max_window_units:
            candidate = source_units[end_index + 1]
            candidate_tokens = ai_budget_service.estimate_text_tokens(_build_units_block([candidate]))
            if candidate_tokens > text_budget_tokens:
                raise ValueError(
                    "AI narrator profile generation cannot run because source unit "
                    f"{candidate.get('unit_id', '')} exceeds the available request input budget "
                    f"({candidate_tokens} estimated tokens, {text_budget_tokens} available)."
                )
            if current_count > 0 and current_tokens + candidate_tokens > text_budget_tokens:
                break
            current_tokens += candidate_tokens
            current_count += 1
            end_index += 1
        windows.append(source_units[start_index : end_index + 1])
        start_index = end_index + 1
    return windows


def _build_units_block(source_units: list[SourceUnitPayload]) -> str:
    """
    @brief      Render source units into the model-facing prompt block.
    @param[in]  source_units Ordered source units.
    @return     Prompt-ready unit block.
    @exception  None
    """
    blocks = []
    for unit in source_units:
        blocks.append(
            "UNIT_BEGIN\n"
            f"UNIT_ID: {unit.get('unit_id', '')}\n"
            f"SEQUENCE_INDEX: {unit.get('sequence_index', '')}\n"
            "TEXT_BEGIN\n"
            f"{unit.get('text', '')}\n"
            "TEXT_END\n"
            "UNIT_END"
        )
    return "\n\n".join(blocks)


def _normalize_style_observation(payload: object, window_index: int) -> dict[str, object]:
    """
    @brief      Normalize one style-analysis response.
    @param[in]  payload Raw AI response payload.
    @param[in]  window_index One-based style window index.
    @return     Compact observation payload.
    @exception  None
    """
    response_payload = dict(payload) if isinstance(payload, dict) else {}
    return {
        "window_index": window_index,
        **{field_name: _string_list(response_payload.get(field_name)) for field_name in _STYLE_OBSERVATION_FIELDS},
    }


def _build_style_observation_summary(observations: list[dict[str, object]]) -> dict[str, object]:
    """
    @brief      Build a compact frequency summary of repeated narrator style observations.
    @param[in]  observations Per-window style observations from the first AI pass.
    @return     Compact style summary safe for the final profile-generation prompt.
    @exception  None
    """
    summarized_fields: dict[str, object] = {}
    unique_term_counts: dict[str, int] = {}
    omitted_term_counts: dict[str, int] = {}
    for field_name in _STYLE_OBSERVATION_FIELDS:
        ranked_terms = _rank_style_terms(observations, field_name)
        limit = max(1, int(_STYLE_SUMMARY_TERM_LIMITS[field_name]))
        summarized_fields[field_name] = ranked_terms[:limit]
        unique_term_counts[field_name] = len(ranked_terms)
        omitted_term_counts[field_name] = max(0, len(ranked_terms) - limit)
    return {
        "observation_count": len(observations),
        "summary_mode": "frequency_merge",
        "fields": summarized_fields,
        "unique_term_counts": unique_term_counts,
        "omitted_term_counts": omitted_term_counts,
    }


def _rank_style_terms(observations: list[dict[str, object]], field_name: str) -> list[dict[str, object]]:
    """
    @brief      Count and rank normalized style terms for one observation field.
    @param[in]  observations Per-window style observations.
    @param[in]  field_name Observation field to summarize.
    @return     Ranked term payloads with original display value and count.
    @exception  None
    """
    term_counts: dict[str, int] = {}
    term_display_values: dict[str, str] = {}
    term_first_seen: dict[str, int] = {}
    sequence_index = 0
    for observation in observations:
        for raw_term in _string_list(observation.get(field_name)):
            normalized_term = _normalized_style_term(raw_term)
            if not normalized_term:
                continue
            sequence_index += 1
            term_counts[normalized_term] = term_counts.get(normalized_term, 0) + 1
            term_display_values.setdefault(normalized_term, raw_term.strip())
            term_first_seen.setdefault(normalized_term, sequence_index)
    return [
        {
            "value": term_display_values[normalized_term],
            "count": term_counts[normalized_term],
        }
        for normalized_term in sorted(
            term_counts,
            key=lambda term: (-term_counts[term], term_first_seen[term], term_display_values[term].casefold()),
        )
    ]


def _normalized_style_term(term: object) -> str:
    """
    @brief      Normalize one style term for deterministic exact-frequency merging.
    @param[in]  term Candidate style term.
    @return     Lowercase normalized style key.
    @exception  None
    """
    return " ".join(str(term or "").casefold().strip(" \t\r\n.,;:!?").split())


def _validated_generated_profiles(
    response_payload: dict[str, object],
    requested_count: int,
    allocation: dict[str, object],
    voice_language: str,
) -> list[dict[str, object]]:
    """
    @brief      Validate generated narrator profiles before persistence.
    @param[in]  response_payload Raw generation response payload.
    @param[in]  requested_count Requested narrator profile count.
    @param[in]  allocation Required gender allocation payload.
    @param[in]  voice_language Selected audiobook voice language code.
    @details    Preview text whose length the accepted bounds refuse is replaced by the canonical
                default for the selected language rather than failing the batch, because it is an
                interchangeable sample script; an unusable prompt_text still rejects the whole
                response. Line breaks are spoken as pauses and are accepted.
    @return     Tuple of validated generated profile payloads and preview-substitution warnings.
    @exception  ValueError Raised when the AI response does not satisfy the contract.
    """
    raw_profiles = response_payload.get("profiles", [])
    if not isinstance(raw_profiles, list) or len(raw_profiles) != requested_count:
        raise ValueError(f"AI narrator generation must return exactly {requested_count} profiles.")
    profiles: list[dict[str, object]] = []
    warnings: list[str] = []
    names: set[str] = set()
    gender_counts = {"male": 0, "female": 0}
    min_preview_units = _minimum_preview_budget_units()
    max_preview_units = _maximum_preview_budget_units()
    for index, raw_profile in enumerate(raw_profiles, start=1):
        if not isinstance(raw_profile, dict):
            raise ValueError(f"Generated narrator profile #{index} is not an object.")
        display_name = str(raw_profile.get("display_name", "")).strip()
        gender = str(raw_profile.get("gender", "")).strip().casefold()
        style_label = str(raw_profile.get("style_label", "")).strip()
        prompt_text = str(raw_profile.get("prompt_text", "")).strip()
        preview_text = str(raw_profile.get("preview_text", "")).strip()
        if not display_name:
            raise ValueError(f"Generated narrator profile #{index} is missing a display_name.")
        if display_name.casefold() in names:
            raise ValueError(f"Generated narrator profile name is duplicated: {display_name}.")
        if gender not in gender_counts:
            raise ValueError(f"Generated narrator profile #{index} has unsupported gender '{gender}'.")
        if not prompt_text or len(prompt_text.split()) < 12:
            raise ValueError(f"Generated narrator profile '{display_name}' has an invalid prompt_text.")
        if _contains_audio_generation_request(prompt_text):
            raise ValueError(f"Generated narrator profile '{display_name}' prompt_text asks for audio generation.")
        preview_budget_units = tts_budget_service.estimate_budget_units(preview_text)
        unusable_preview_reason = ""
        if preview_budget_units < min_preview_units:
            unusable_preview_reason = (
                f"is too short for a voice-clone reference ({preview_budget_units} budget units, "
                f"minimum {min_preview_units})"
            )
        elif preview_budget_units > max_preview_units:
            unusable_preview_reason = (
                f"is too long for a narrator sample ({preview_budget_units} budget units, "
                f"maximum {max_preview_units})"
            )
        if unusable_preview_reason:
            preview_text = narrator_definition_service.preview_text_for_language(voice_language)
            warnings.append(
                f"Generated preview text for '{display_name}' {unusable_preview_reason}; "
                f"the default preview text for this language was used instead."
            )
        names.add(display_name.casefold())
        gender_counts[gender] += 1
        profiles.append(
            {
                "display_name": display_name,
                "gender": gender,
                "style_label": style_label,
                "language": voice_language,
                "prompt_text": prompt_text,
                "preview_text": preview_text,
            }
        )
    if gender_counts["male"] != int(allocation["male"]) or gender_counts["female"] != int(allocation["female"]):
        raise ValueError("AI narrator generation returned profiles with the wrong male/female allocation.")
    return profiles, warnings


def _minimum_preview_budget_units() -> int:
    """
    @brief      Return the shortest accepted narrator preview budget-unit estimate.
    @return     Minimum preview budget units.
    @exception  None
    """
    return narrator_definition_service.narrator_preview_word_bounds()[0]


def _maximum_preview_budget_units() -> int:
    """
    @brief      Return the bounded maximum accepted narrator preview budget-unit estimate.
    @return     Maximum accepted preview budget-unit estimate.
    @exception  None
    """
    return narrator_definition_service.narrator_preview_word_bounds()[1]


def _build_model_settings(
    ai_profile_payload: dict[str, object],
    budget_metadata: dict[str, int],
) -> dict[str, object]:
    """
    @brief      Build persisted model settings metadata for the generation run.
    @param[in]  ai_profile_payload Selected AI profile payload.
    @param[in]  budget_metadata Context-budget metadata.
    @return     Model settings payload.
    @exception  None
    """
    return {
        "profile_id": str(ai_profile_payload.get("id", "")).strip(),
        "backend_kind": str(ai_profile_payload.get("backend_kind", "")).strip(),
        "model_name": str(ai_profile_payload.get("model_name", "")).strip(),
        "context_window": int(budget_metadata.get("context_window", 0)),
        "max_output_tokens": int(budget_metadata.get("max_output_tokens", 0)),
        "temperature": float(ai_profile_payload.get("temperature", 0.0) or 0.0),
    }


def _restore_resume_state(
    existing_state: dict[str, object],
    project_root: Path,
    *,
    input_fingerprint: str,
    profile_id: str,
    requested_count: int,
    source_token: str,
    total_window_count: int,
    budget_metadata: dict[str, int],
    model_settings: dict[str, object],
    additional_profile_instructions_fingerprint: str,
) -> dict[str, object]:
    """
    @brief      Restore a compatible unfinished narrator-profile-generation checkpoint.
    @param[in]  existing_state Persisted operation-state payload.
    @param[in]  project_root Active project root folder.
    @param[in]  input_fingerprint Current source-text fingerprint.
    @param[in]  profile_id Current AI profile identifier.
    @param[in]  requested_count Current requested profile count.
    @param[in]  source_token Current source selector token.
    @param[in]  total_window_count Current source-window count.
    @param[in]  budget_metadata Current context-budget metadata.
    @param[in]  model_settings Current model settings metadata.
    @param[in]  additional_profile_instructions_fingerprint Operator instruction fingerprint.
    @return     Resume metadata with `resume_compatible` flag.
    @exception  None
    """
    _ = project_root
    fallback = _empty_resume_state()
    if str(existing_state.get("status", "")) not in {"running", "failed", "cancelled"}:
        return fallback
    resume_checkpoint = existing_state.get("resume_checkpoint")
    if not isinstance(resume_checkpoint, dict):
        return fallback
    expected_fingerprint = _build_resume_fingerprint(
        input_fingerprint=input_fingerprint,
        profile_id=profile_id,
        source_token=source_token,
        requested_count=requested_count,
        budget_metadata=budget_metadata,
        model_settings=model_settings,
        additional_profile_instructions_fingerprint=additional_profile_instructions_fingerprint,
    )
    if resume_checkpoint.get("resume_fingerprint") != expected_fingerprint:
        return fallback
    if resume_checkpoint.get("requested_count") != requested_count:
        return fallback
    if resume_checkpoint.get("total_window_count") != total_window_count:
        return fallback
    gender_allocation = dict(resume_checkpoint.get("gender_allocation") or {})
    if not _is_valid_gender_allocation(gender_allocation, requested_count):
        return fallback
    completed_window_count = int(resume_checkpoint.get("completed_window_count", 0))
    style_observations = _restore_style_observations(resume_checkpoint.get("style_observations"))
    if completed_window_count < 0 or completed_window_count > total_window_count:
        return fallback
    if len(style_observations) != completed_window_count:
        return fallback
    return {
        "resume_compatible": True,
        "token_usage": _restore_token_usage(existing_state),
        "gender_allocation": gender_allocation,
        "style_observations": style_observations,
        "completed_window_count": completed_window_count,
    }


def _empty_resume_state() -> dict[str, object]:
    """
    @brief      Build the default no-resume payload.
    @return     Resume metadata indicating a fresh run.
    @exception  None
    """
    return {
        "resume_compatible": False,
        "token_usage": token_usage_service.empty_token_usage(),
        "gender_allocation": {},
        "style_observations": [],
        "completed_window_count": 0,
    }


def _restore_style_observations(value: object) -> list[dict[str, object]]:
    """
    @brief      Normalize checkpointed style observations.
    @param[in]  value Candidate style-observation list.
    @return     Dictionary-only style observations.
    @exception  None
    """
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _restore_token_usage(existing_state: dict[str, object]) -> dict[str, object]:
    """
    @brief      Restore cumulative token usage from an unfinished run.
    @param[in]  existing_state Persisted operation-state payload.
    @return     Normalized token-usage payload.
    @exception  None
    """
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return token_usage_service.empty_token_usage()
    return token_usage_service.restore_token_usage(metadata.get("token_usage"))


def _is_valid_gender_allocation(gender_allocation: dict[str, object], requested_count: int) -> bool:
    """
    @brief      Return whether a checkpointed gender allocation matches the request.
    @param[in]  gender_allocation Candidate allocation payload.
    @param[in]  requested_count Requested profile count.
    @return     True when the payload is structurally compatible.
    @exception  None
    """
    try:
        male_count = int(gender_allocation.get("male", 0) or 0)
        female_count = int(gender_allocation.get("female", 0) or 0)
        random_count = int(gender_allocation.get("random", 0) or 0)
    except (TypeError, ValueError):
        return False
    random_gender = str(gender_allocation.get("random_gender", "") or "").strip()
    if male_count < 0 or female_count < 0 or random_count < 0:
        return False
    if male_count + female_count != requested_count:
        return False
    if random_count not in {0, 1}:
        return False
    if random_count == 0:
        return random_gender == ""
    return random_gender in {"male", "female"}


def _write_operation_state(
    project_root: Path,
    *,
    status: str,
    profile_id: str,
    source_token: str,
    requested_count: int,
    gender_allocation: dict[str, object],
    input_fingerprint: str,
    token_usage: dict[str, object],
    budget_metadata: dict[str, int],
    model_settings: dict[str, object],
    style_observations: list[dict[str, object]],
    total_window_count: int,
    additional_profile_instructions: str,
) -> None:
    """
    @brief      Persist one narrator-profile-generation operation state.
    @param[in]  project_root Active project root folder.
    @param[in]  status Runtime operation status token.
    @param[in]  profile_id Selected AI profile identifier.
    @param[in]  source_token Selected input source token.
    @param[in]  requested_count Requested narrator profile count.
    @param[in]  gender_allocation Requested gender-allocation metadata.
    @param[in]  input_fingerprint Stable source fingerprint.
    @param[in]  token_usage Cumulative token usage.
    @param[in]  budget_metadata Context-budget metadata.
    @param[in]  model_settings Selected model settings metadata.
    @param[in]  style_observations Completed style-window observations.
    @param[in]  total_window_count Total style-window count.
    @param[in]  additional_profile_instructions Optional operator-supplied profile-generation rules.
    @return     None.
    @exception  None
    """
    normalized_instructions = _normalized_additional_profile_instructions(additional_profile_instructions)
    instruction_fingerprint = _compute_prompt_fingerprint(normalized_instructions)
    document = narrator_definition_service.load_narrator_voice_document(project_root)
    document["status"] = status
    document["token_usage"] = token_usage_service.coerce_token_usage(token_usage)
    document["budget_metadata"] = dict(budget_metadata)
    document["additional_profile_instructions"] = normalized_instructions
    document["resume"] = (
        None
        if status == narrator_definition_service.NARRATOR_VOICE_STATUS_COMPLETED
        else {
            "resume_fingerprint": _build_resume_fingerprint(
                input_fingerprint=input_fingerprint,
                profile_id=profile_id,
                source_token=source_token,
                requested_count=requested_count,
                budget_metadata=budget_metadata,
                model_settings=model_settings,
                additional_profile_instructions_fingerprint=instruction_fingerprint,
            ),
            "requested_count": requested_count,
            "gender_allocation": dict(gender_allocation),
            "completed_window_count": len(style_observations),
            "total_window_count": int(total_window_count),
            "style_observations": [dict(item) for item in style_observations],
        }
    )
    narrator_definition_service.write_narrator_voice_document(project_root, document)


def _build_resume_fingerprint(
    *,
    input_fingerprint: str,
    profile_id: str,
    source_token: str,
    requested_count: int,
    budget_metadata: dict[str, int],
    model_settings: dict[str, object],
    additional_profile_instructions_fingerprint: str,
) -> str:
    """
    @brief      Build the complete deterministic AI resume identity.
    @return     SHA-256 fingerprint covering source, language, provider settings, budget, count, and instructions.
    """
    fingerprint_payload = {
        "source": source_token,
        "source_fingerprint": input_fingerprint,
        "profile_id": profile_id,
        "backend_kind": model_settings.get("backend_kind"),
        "model_name": model_settings.get("model_name"),
        "context_window": model_settings.get("context_window"),
        "max_output_tokens": model_settings.get("max_output_tokens"),
        "temperature": model_settings.get("temperature"),
        "budget_metadata": dict(budget_metadata),
        "requested_count": requested_count,
        "additional_profile_instructions_fingerprint": additional_profile_instructions_fingerprint,
    }
    serialized = json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_input_fingerprint(
    source_units: list[SourceUnitPayload],
    source_token: str,
    voice_language: str,
) -> str:
    """
    @brief      Build one fingerprint from source text and language.
    @param[in]  source_units Ordered source units.
    @param[in]  source_token Selected source token.
    @param[in]  voice_language Selected audiobook voice language.
    @return     SHA-256 fingerprint.
    @exception  None
    """
    digest = hashlib.sha256()
    digest.update(str(source_token).encode("utf-8"))
    digest.update(b"\n")
    digest.update(str(voice_language).encode("utf-8"))
    digest.update(b"\n")
    for unit in source_units:
        digest.update(str(unit.get("unit_id", "")).encode("utf-8"))
        digest.update(b"\n")
        digest.update(str(unit.get("sequence_index", "")).encode("utf-8"))
        digest.update(b"\n")
        digest.update(str(unit.get("text", "")).encode("utf-8"))
        digest.update(b"\n---\n")
    return digest.hexdigest()


def _resolve_log_path(project_root: Path, started_at: str) -> Path:
    """
    @brief      Resolve the AI transaction log path for one run.
    @param[in]  project_root Active project root folder.
    @param[in]  started_at Operation start timestamp.
    @return     Absolute transaction log path.
    @exception  None
    """
    timestamp_token = started_at.replace("-", "").replace(":", "").replace("+", "_").replace(".", "")
    return project_root / config.ai_transaction_log_file_name("narrator_profiles", timestamp_token)


def _string_list(value: object) -> list[str]:
    """
    @brief      Normalize one AI response value to a compact string list.
    @param[in]  value Candidate AI response field.
    @return     List of non-empty strings.
    @exception  None
    """
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [] if not text else [text]


def _contains_audio_generation_request(prompt_text: str) -> bool:
    """
    @brief      Detect prompt text that requests audio generation instead of voice design.
    @param[in]  prompt_text Generated profile prompt text.
    @return     True when the prompt text contains an audio-generation instruction.
    @exception  None
    """
    normalized_prompt = prompt_text.casefold()
    blocked_phrases = (
        "generate audio",
        "create audio",
        "make audio",
        "produce audio",
        "generate wav",
        "create wav",
        "text-to-speech request",
    )
    return any(phrase in normalized_prompt for phrase in blocked_phrases)


# END OF FILE
