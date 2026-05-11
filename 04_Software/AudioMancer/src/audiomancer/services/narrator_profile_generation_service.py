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
         editable narrator voice-designer prompts and preview text, and persists
         generation report/state sidecars without generating narrator audio.
@author Eng. Dan Dumitru Pasare
@date 2026-05-11
@version 0.2.1
"""

# IMPORTS

import hashlib
import json
from pathlib import Path
import random

from audiomancer import config
from audiomancer.services import (
    ai_budget_service,
    ai_translation_service,
    cleanup_metadata_service,
    deterministic_chunking_service,
    llm_provider_service,
    narrator_definition_service,
    prompt_template_service,
    token_usage_service,
    tts_budget_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    build_operation_output_path,
    build_operation_state_payload,
    emit_progress_update,
    load_operation_state_payload,
    raise_if_cancelled,
    relative_to_project,
    resolve_operation_path,
)
from audiomancer.services.persistence_service import write_json_atomic
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

# @brief Persisted narrator-profile-generation report payload type.
NarratorProfileGenerationReportPayload = dict[str, object]

# @brief Persisted narrator-profile-generation operation-state payload type.
OperationStatePayload = dict[str, object]

# @brief Runtime text unit consumed by the profile-generation workflow.
SourceUnitPayload = dict[str, object]


# PUBLIC API


@trace_function(_NARRATOR_PROFILE_GENERATION_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load the optional narrator profile generation runtime state.
    @param[in]  project_root Active project root folder.
    @return     Persisted operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    return load_operation_state_payload(
        project_root,
        "narrator_definition",
        config.NARRATOR_PROFILE_GENERATION_STATE_FILE_NAME,
    )


@trace_function(_NARRATOR_PROFILE_GENERATION_LOGGER)
def load_generation_report(project_root: str | Path) -> NarratorProfileGenerationReportPayload | None:
    """
    @brief      Load the optional narrator profile generation report.
    @param[in]  project_root Active project root folder.
    @return     Persisted report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    report_path = resolve_operation_path(
        project_root,
        "narrator_definition",
        config.NARRATOR_PROFILE_GENERATION_REPORT_FILE_NAME,
    )
    if not report_path.is_file():
        return None
    return dict(json.loads(report_path.read_text(encoding="utf-8")))


@trace_function(_NARRATOR_PROFILE_GENERATION_LOGGER)
def generate_narrator_profiles(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    profile_count: int,
    voice_language: str,
    preview_text_character_limit: int,
    progress_callback=None,
    cancel_requested=None,
) -> NarratorProfileGenerationReportPayload:
    """
    @brief      Generate and append editable text-only narrator profiles.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  profile_count Requested narrator profile count.
    @param[in]  voice_language Selected audiobook voice language code.
    @param[in]  preview_text_character_limit Maximum accepted preview text characters.
    @param[in]  progress_callback Optional progress callback for the modal dialog.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Persisted narrator profile generation report.
    @exception  ValueError Raised on invalid input, missing source text, or invalid AI output.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.2.0
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
    source_units, source_token, source_path = _resolve_source_units(resolved_project_root, normalized_voice_language)
    input_fingerprint = _build_input_fingerprint(source_units, source_token, normalized_voice_language)
    system_prompt = prompt_template_service.render_prompt("narrator_profile_style_system", {})
    budget_metadata = _build_budget_metadata(ai_profile_payload, system_prompt)
    windows = _build_source_windows(source_units, budget_metadata)
    if not windows:
        raise ValueError("Narrator profile generation requires at least one readable text window.")

    state_path = build_operation_output_path(
        resolved_project_root,
        "narrator_definition",
        config.NARRATOR_PROFILE_GENERATION_STATE_FILE_NAME,
    )
    report_path = build_operation_output_path(
        resolved_project_root,
        "narrator_definition",
        config.NARRATOR_PROFILE_GENERATION_REPORT_FILE_NAME,
    )
    allocation = _gender_allocation(requested_count)
    model_settings = _build_model_settings(ai_profile_payload, budget_metadata)
    total_progress = len(windows) + 1
    existing_state = load_operation_state(resolved_project_root) or {}
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
    )
    if resume_state["resume_compatible"]:
        started_at = str(resume_state["started_at"])
        token_usage = token_usage_service.restore_token_usage(resume_state["token_usage"])
        log_path = Path(resume_state["log_path"])
        allocation = dict(resume_state["gender_allocation"])
        observations = [dict(item) for item in resume_state["style_observations"]]
        completed_window_count = int(resume_state["completed_window_count"])
    else:
        started_at = _utc_now_iso()
        token_usage = token_usage_service.empty_token_usage()
        log_path = _resolve_log_path(resolved_project_root, started_at)
        observations: list[dict[str, object]] = []
        completed_window_count = 0

    _write_operation_state(
        state_path,
        resolved_project_root,
        input_path=source_path,
        report_path=None,
        status="running",
        progress_current=completed_window_count,
        progress_total=total_progress,
        started_at=started_at,
        completed_at=None,
        profile_id=profile_id,
        source_token=source_token,
        source_unit_count=len(source_units),
        requested_count=requested_count,
        generated_profile_ids=[],
        gender_allocation=allocation,
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        model_settings=model_settings,
        style_observations=observations,
        total_window_count=len(windows),
    )
    emit_progress_update(
        progress_callback,
        completed_window_count,
        total_progress,
        "Analyzing narrator style...",
        token_usage=token_usage,
    )

    for window_index, window_units in enumerate(windows, start=1):
        if window_index <= completed_window_count:
            continue
        raise_if_cancelled(cancel_requested)
        user_prompt = prompt_template_service.render_prompt(
            "narrator_profile_style_window_user",
            {"units_block": _build_units_block(window_units)},
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
            raise OperationCancelledError(
                "Narrator profile generation cancelled while waiting for the model response."
            ) from error
        token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
        observations.append(_normalize_style_observation(response_result.get("payload"), window_index))
        _write_operation_state(
            state_path,
            resolved_project_root,
            input_path=source_path,
            report_path=None,
            status="running",
            progress_current=window_index,
            progress_total=total_progress,
            started_at=started_at,
            completed_at=None,
            profile_id=profile_id,
            source_token=source_token,
            source_unit_count=len(source_units),
            requested_count=requested_count,
            generated_profile_ids=[],
            gender_allocation=allocation,
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            budget_metadata=budget_metadata,
            model_settings=model_settings,
            style_observations=observations,
            total_window_count=len(windows),
        )
        emit_progress_update(
            progress_callback,
            window_index,
            total_progress,
            "Analyzing narrator style...",
            token_usage=token_usage,
        )

    raise_if_cancelled(cancel_requested)
    user_prompt = prompt_template_service.render_prompt(
        "narrator_profile_generation_user",
        {
            "voice_language": narrator_definition_service.narrator_language_label(normalized_voice_language),
            "profile_count": requested_count,
            "male_count": int(allocation["male"]),
            "female_count": int(allocation["female"]),
            "random_gender_count": int(allocation["random"]),
            "style_observations": json.dumps(observations, indent=2, ensure_ascii=False),
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
        raise OperationCancelledError(
            "Narrator profile generation cancelled while waiting for the model response."
        ) from error
    token_usage = token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
    raw_response_payload = response_result.get("payload", {})
    response_payload = dict(raw_response_payload) if isinstance(raw_response_payload, dict) else {}
    validated_profiles = _validated_generated_profiles(
        response_payload,
        requested_count,
        allocation,
        normalized_voice_language,
        preview_text_character_limit,
    )
    generation_metadata = {
        "generated_by": "ai_narrator_profile_generation",
        "ai_profile_id": profile_id,
        "model_name": model_name,
        "source": source_token,
        "input_fingerprint": input_fingerprint,
        "generated_at": _utc_now_iso(),
    }
    created_profiles = narrator_definition_service.append_ai_generated_profiles(
        resolved_project_root,
        validated_profiles,
        generation_metadata,
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
        "budget_metadata": budget_metadata,
        "warning_count": 0,
        "warnings": [],
        "generated_at": generation_metadata["generated_at"],
        "token_usage": token_usage,
    }
    write_json_atomic(report_path, report_payload)
    _write_operation_state(
        state_path,
        resolved_project_root,
        input_path=source_path,
        report_path=report_path,
        status="completed",
        progress_current=total_progress,
        progress_total=total_progress,
        started_at=started_at,
        completed_at=str(report_payload["generated_at"]),
        profile_id=profile_id,
        source_token=source_token,
        source_unit_count=len(source_units),
        requested_count=requested_count,
        generated_profile_ids=generated_profile_ids,
        gender_allocation=allocation,
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        model_settings=model_settings,
        style_observations=observations,
        total_window_count=len(windows),
    )
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    translated_units = _approved_translation_units(project_root, voice_language)
    if translated_units:
        return translated_units, SOURCE_TRANSLATED_CHUNKS, project_root / config.TRANSLATED_CHUNKS_FILE_NAME

    chunk_units = _canonical_chunk_units(project_root)
    if chunk_units:
        return chunk_units, SOURCE_CANONICAL_CHUNKS, project_root / config.CHUNK_ARTIFACT_FILE_NAME

    metadata_units = _cleaned_metadata_units(project_root)
    if metadata_units:
        return metadata_units, SOURCE_CLEANED_METADATA, project_root / config.CLEANED_TEXT_METADATA_FILE_NAME

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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    report = ai_translation_service.load_translation_report(project_root)
    if not isinstance(report, dict):
        return []
    target_language = narrator_definition_service.narrator_language_code(report.get("target_language"))
    if target_language != narrator_definition_service.narrator_language_code(voice_language):
        return []
    total_count = int(report.get("total_chunk_count", 0) or 0)
    approved_count = int(report.get("approved_chunk_count", 0) or 0)
    if total_count <= 0 or approved_count < total_count:
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    chunks = sorted(
        deterministic_chunking_service.load_chunks(project_root),
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    metadata_payload = cleanup_metadata_service.load_cleanup_metadata(project_root)
    if not isinstance(metadata_payload, dict):
        return []
    paragraph_payloads = metadata_payload.get("paragraphs", [])
    if not isinstance(paragraph_payloads, list):
        return []
    return _paragraph_units([dict(item) for item in paragraph_payloads if isinstance(item, dict)])


def _paragraph_units(records: list[dict[str, object]]) -> list[SourceUnitPayload]:
    """
    @brief      Convert cleaned paragraph records to narrator analysis units.
    @param[in]  records Cleaned paragraph records.
    @return     Ordered source units.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    return {
        "unit_id": str(unit_id).strip() or f"unit-{sequence_index:04d}",
        "sequence_index": int(sequence_index),
        "text": str(text).strip(),
    }


def _build_budget_metadata(ai_profile_payload: dict[str, object], system_prompt: str) -> dict[str, int]:
    """
    @brief      Build context-window budget metadata for narrator profile generation.
    @param[in]  ai_profile_payload Selected AI profile payload.
    @param[in]  system_prompt Rendered system prompt.
    @return     Context-budget metadata.
    @exception  ValueError Raised when too little input room remains.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    style_prompt_shell = prompt_template_service.render_prompt(
        "narrator_profile_style_window_user",
        {"units_block": ""},
    )
    generation_prompt_shell = prompt_template_service.render_prompt(
        "narrator_profile_generation_user",
        {
            "voice_language": "",
            "profile_count": 0,
            "male_count": 0,
            "female_count": 0,
            "random_gender_count": 0,
            "style_observations": "",
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    response_payload = dict(payload) if isinstance(payload, dict) else {}
    return {
        "window_index": window_index,
        "genre": _string_list(response_payload.get("genre")),
        "tone": _string_list(response_payload.get("tone")),
        "pacing": _string_list(response_payload.get("pacing")),
        "narrator_distance": _string_list(response_payload.get("narrator_distance")),
        "emotional_range": _string_list(response_payload.get("emotional_range")),
        "diction": _string_list(response_payload.get("diction")),
        "worldbuilding_cues": _string_list(response_payload.get("worldbuilding_cues")),
        "themes": _string_list(response_payload.get("themes")),
        "narration_risks": _string_list(response_payload.get("narration_risks")),
    }


def _validated_generated_profiles(
    response_payload: dict[str, object],
    requested_count: int,
    allocation: dict[str, object],
    voice_language: str,
    preview_text_character_limit: int,
) -> list[dict[str, object]]:
    """
    @brief      Validate generated narrator profiles before persistence.
    @param[in]  response_payload Raw generation response payload.
    @param[in]  requested_count Requested narrator profile count.
    @param[in]  allocation Required gender allocation payload.
    @param[in]  voice_language Selected audiobook voice language code.
    @param[in]  preview_text_character_limit Maximum accepted preview text characters.
    @return     Validated generated profile payloads.
    @exception  ValueError Raised when the AI response does not satisfy the contract.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.2.0
    """
    raw_profiles = response_payload.get("profiles", [])
    if not isinstance(raw_profiles, list) or len(raw_profiles) != requested_count:
        raise ValueError(f"AI narrator generation must return exactly {requested_count} profiles.")
    profiles: list[dict[str, object]] = []
    names: set[str] = set()
    gender_counts = {"male": 0, "female": 0}
    preview_limit = max(1, int(preview_text_character_limit or config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT))
    min_preview_words = _minimum_preview_word_count()
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
        if not preview_text:
            raise ValueError(f"Generated narrator profile '{display_name}' is missing preview_text.")
        preview_word_count = tts_budget_service.estimated_word_count(preview_text)
        if preview_word_count < min_preview_words:
            raise ValueError(
                f"Generated narrator profile '{display_name}' preview_text is too short for a Qwen TTS reference "
                f"({preview_word_count} words, minimum {min_preview_words})."
            )
        if "\n" in preview_text or len(preview_text.split()) > 24:
            raise ValueError(f"Generated narrator profile '{display_name}' preview_text must be one short sentence.")
        if len(preview_text) > preview_limit:
            raise ValueError(
                f"Generated narrator profile '{display_name}' preview_text exceeds {preview_limit} characters."
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
    return profiles


def _minimum_preview_word_count() -> int:
    """
    @brief      Estimate the minimum preview-text word count for useful Qwen TTS references.
    @return     Minimum preview word count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    return max(
        1,
        int(
            float(config.DEFAULT_TTS_MIN_PREVIEW_AUDIO_SECONDS) * float(config.DEFAULT_TTS_WORDS_PER_AUDIO_SECOND)
            + 0.999
        ),
    )


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    @return     Resume metadata with `resume_compatible` flag.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    fallback = _empty_resume_state()
    if str(existing_state.get("status", "")) not in {"running", "failed", "cancelled"}:
        return fallback
    if str(existing_state.get("mode", "")) != NARRATOR_PROFILE_GENERATION_MODE_AI_ASSISTED:
        return fallback
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    if str(resume_checkpoint.get("input_fingerprint", "")) != input_fingerprint:
        return fallback
    if str(resume_checkpoint.get("profile_id", "")) != profile_id:
        return fallback
    if str(resume_checkpoint.get("source", "")) != source_token:
        return fallback
    try:
        checkpoint_requested_count = int(resume_checkpoint.get("requested_count", 0) or 0)
        checkpoint_window_count = int(resume_checkpoint.get("total_window_count", 0) or 0)
        checkpoint_budget_metadata = dict(resume_checkpoint.get("budget_metadata") or {})
        checkpoint_model_settings = dict(resume_checkpoint.get("model_settings") or {})
    except (TypeError, ValueError):
        return fallback
    if checkpoint_requested_count != int(requested_count):
        return fallback
    if checkpoint_window_count != int(total_window_count):
        return fallback
    if checkpoint_budget_metadata != dict(budget_metadata):
        return fallback
    if checkpoint_model_settings != dict(model_settings):
        return fallback
    try:
        gender_allocation = dict(resume_checkpoint.get("gender_allocation") or {})
    except (TypeError, ValueError):
        return fallback
    if not _is_valid_gender_allocation(gender_allocation, requested_count):
        return fallback
    try:
        completed_window_count = max(0, int(resume_checkpoint.get("completed_window_count", 0) or 0))
    except (TypeError, ValueError):
        return fallback
    completed_window_count = min(completed_window_count, total_window_count)
    style_observations = _restore_style_observations(resume_checkpoint.get("style_observations"))
    if len(style_observations) < completed_window_count:
        return fallback
    style_observations = style_observations[:completed_window_count]
    log_path = _restored_log_path(project_root, resume_checkpoint)
    return {
        "resume_compatible": True,
        "started_at": str(existing_state.get("started_at") or _utc_now_iso()),
        "token_usage": _restore_token_usage(existing_state),
        "log_path": log_path,
        "gender_allocation": gender_allocation,
        "style_observations": style_observations,
        "completed_window_count": completed_window_count,
    }


def _empty_resume_state() -> dict[str, object]:
    """
    @brief      Build the default no-resume payload.
    @return     Resume metadata indicating a fresh run.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    return {
        "resume_compatible": False,
        "started_at": "",
        "token_usage": token_usage_service.empty_token_usage(),
        "log_path": Path(),
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return token_usage_service.empty_token_usage()
    return token_usage_service.restore_token_usage(metadata.get("token_usage"))


def _restored_log_path(project_root: Path, resume_checkpoint: dict[str, object]) -> Path:
    """
    @brief      Restore the AI transaction log path from a checkpoint.
    @param[in]  project_root Active project root folder.
    @param[in]  resume_checkpoint Persisted resume checkpoint.
    @return     Absolute AI transaction log path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    log_relative_path = str(resume_checkpoint.get("log_relative_path", "") or "").strip()
    if not log_relative_path:
        return _resolve_log_path(project_root, _utc_now_iso())
    log_path = Path(log_relative_path)
    return log_path if log_path.is_absolute() else project_root / log_path


def _is_valid_gender_allocation(gender_allocation: dict[str, object], requested_count: int) -> bool:
    """
    @brief      Return whether a checkpointed gender allocation matches the request.
    @param[in]  gender_allocation Candidate allocation payload.
    @param[in]  requested_count Requested profile count.
    @return     True when the payload is structurally compatible.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    state_path: Path,
    project_root: Path,
    *,
    input_path: Path,
    report_path: Path | None,
    status: str,
    progress_current: int,
    progress_total: int,
    started_at: str,
    completed_at: str | None,
    profile_id: str,
    source_token: str,
    source_unit_count: int,
    requested_count: int,
    generated_profile_ids: list[str],
    gender_allocation: dict[str, object],
    input_fingerprint: str,
    log_path: Path,
    token_usage: dict[str, object],
    budget_metadata: dict[str, int],
    model_settings: dict[str, object],
    style_observations: list[dict[str, object]],
    total_window_count: int,
) -> None:
    """
    @brief      Persist one narrator-profile-generation operation state.
    @param[in]  state_path Runtime state artifact path.
    @param[in]  project_root Active project root folder.
    @param[in]  input_path Backing input artifact path.
    @param[in]  report_path Optional completed report artifact path.
    @param[in]  status Runtime operation status token.
    @param[in]  progress_current Completed work units.
    @param[in]  progress_total Total work units.
    @param[in]  started_at Operation start timestamp.
    @param[in]  completed_at Optional completion timestamp.
    @param[in]  profile_id Selected AI profile identifier.
    @param[in]  source_token Selected input source token.
    @param[in]  source_unit_count Number of text units analyzed.
    @param[in]  requested_count Requested narrator profile count.
    @param[in]  generated_profile_ids Generated narrator profile identifiers.
    @param[in]  gender_allocation Requested gender-allocation metadata.
    @param[in]  input_fingerprint Stable source fingerprint.
    @param[in]  log_path AI transaction log path.
    @param[in]  token_usage Cumulative token usage.
    @param[in]  budget_metadata Context-budget metadata.
    @param[in]  model_settings Selected model settings metadata.
    @param[in]  style_observations Completed style-window observations.
    @param[in]  total_window_count Total style-window count.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.2.0
    """
    output_paths = [config.NARRATOR_PROFILE_FILE_NAME] if generated_profile_ids else []
    artifact_paths = [relative_to_project(project_root, state_path), relative_to_project(project_root, log_path)]
    if report_path is not None:
        artifact_paths.append(relative_to_project(project_root, report_path))
    state_payload = build_operation_state_payload(
        status=status,
        input_paths=[relative_to_project(project_root, input_path)],
        output_paths=output_paths,
        artifact_paths=artifact_paths,
        progress_current=progress_current,
        progress_total=progress_total,
        mode=NARRATOR_PROFILE_GENERATION_MODE_AI_ASSISTED,
        started_at=started_at,
        completed_at=completed_at,
        warning_count=0,
        metadata={
            "ai_profile_id": profile_id,
            "source": source_token,
            "source_unit_count": source_unit_count,
            "requested_count": requested_count,
            "generated_profile_ids": list(generated_profile_ids),
            "gender_allocation": dict(gender_allocation),
            "input_fingerprint": input_fingerprint,
            "log_relative_path": relative_to_project(project_root, log_path),
            "token_usage": token_usage_service.coerce_token_usage(token_usage),
            "budget_metadata": dict(budget_metadata),
            "model_settings": dict(model_settings),
        },
        resume_checkpoint=(
            None
            if status == "completed"
            else {
                "input_fingerprint": input_fingerprint,
                "profile_id": profile_id,
                "source": source_token,
                "requested_count": requested_count,
                "gender_allocation": dict(gender_allocation),
                "completed_window_count": len(style_observations),
                "total_window_count": int(total_window_count),
                "style_observations": [dict(item) for item in style_observations],
                "log_relative_path": relative_to_project(project_root, log_path),
                "budget_metadata": dict(budget_metadata),
                "model_settings": dict(model_settings),
            }
        ),
    )
    write_json_atomic(state_path, state_payload)


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    timestamp_token = started_at.replace("-", "").replace(":", "").replace("+", "_").replace(".", "")
    return project_root / config.ai_transaction_log_file_name("narrator_profiles", timestamp_token)


def _string_list(value: object) -> list[str]:
    """
    @brief      Normalize one AI response value to a compact string list.
    @param[in]  value Candidate AI response field.
    @return     List of non-empty strings.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
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
