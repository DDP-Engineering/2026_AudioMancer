#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file character_discovery_service.py
@brief AI-assisted character discovery helpers for AudioMancer.
@details Consumes canonical chunking output, discovers speaking characters over
         overlapping chunk windows, persists the `40_character_discovery`
         workflow artifacts, and maintains resumable AI operation state.
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.8.2
"""

# IMPORTS

import hashlib
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    deterministic_chunking_service,
    llm_provider_service,
    prompt_template_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    OperationCancelledError,
    build_operation_output_path,
    load_operation_state_payload,
    load_optional_json_artifact,
    raise_if_cancelled,
    relative_to_project,
    reset_operation_data,
    resolve_operation_path,
)
from audiomancer.services.operation_runtime_service import (
    emit_progress_update as _emit_progress,
)
from audiomancer.services.persistence_service import write_json_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

# @brief Component logger used by the character-discovery workflow service.
_CHARACTER_DISCOVERY_LOGGER = get_component_logger("character_discovery")

# @brief Stable character-discovery mode token used by persisted artifacts.
CHARACTER_DISCOVERY_MODE_AI_ASSISTED = "ai_assisted"
# @brief Stable not-started stage token used by the Characters page.
CHARACTER_DISCOVERY_STAGE_NOT_STARTED = "not_started"
# @brief Stable running stage token used by the Characters page.
CHARACTER_DISCOVERY_STAGE_IN_PROGRESS = "in_progress"
# @brief Stable completed stage token used by the Characters page.
CHARACTER_DISCOVERY_STAGE_COMPLETED = "completed"
# @brief Stable chunk id used for manual character evidence entries.
MANUAL_CHARACTER_EVIDENCE_CHUNK_ID = "manual"
# @brief Stable note used for manual character evidence entries.
MANUAL_CHARACTER_EVIDENCE_NOTE = "Added manually by the operator."
# @brief Discovery input is the canonical source chunking output.
CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS = "chunks"
# @brief Internal review status for AI-discovered character profiles.
CHARACTER_REVIEW_STATUS_DISCOVERED = "discovered"
# @brief Internal review status for manually added character profiles.
CHARACTER_REVIEW_STATUS_MANUAL = "manual"
# @brief Internal review status for operator-edited character profiles.
CHARACTER_REVIEW_STATUS_EDITED = "edited"
# @brief Supported review-status tokens persisted with character profiles.
CHARACTER_REVIEW_STATUSES = {
    CHARACTER_REVIEW_STATUS_DISCOVERED,
    CHARACTER_REVIEW_STATUS_MANUAL,
    CHARACTER_REVIEW_STATUS_EDITED,
}
# @brief Evidence confidence token for direct dialogue-span support.
EVIDENCE_CONFIDENCE_HIGH = "high"
# @brief Evidence confidence token for probable dialogue support.
EVIDENCE_CONFIDENCE_MEDIUM = "medium"
# @brief Evidence confidence token for weak or narrative-only support.
EVIDENCE_CONFIDENCE_LOW = "low"

# @brief Persisted character-profile payload type.
CharacterProfilePayload = dict[str, object]
# @brief Persisted character-discovery report payload type.
CharacterDiscoveryReportPayload = dict[str, object]
# @brief Persisted character-discovery operation-state payload type.
OperationStatePayload = dict[str, object]
TokenUsagePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]

CHARACTER_VOICE_BRIEF_FIELDS = (
    "voice_persona_summary",
    "voice_timbre_and_range",
    "voice_pacing_and_rhythm",
    "voice_emotional_baseline",
    "voice_articulation_and_pronunciation",
    "voice_delivery_constraints",
)
CHARACTER_VOICE_PROMPT_FIELD = "voice_definition_prompt"
CHARACTER_VOICE_SIGNATURE_FIELD = "voice_definition_source_signature"


# PUBLIC API


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional character-discovery operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.4.0
    """
    return load_operation_state_payload(
        project_root,
        "character_discovery",
        config.CHARACTER_DISCOVERY_STATE_FILE_NAME,
    )


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def load_character_profiles(project_root: str | Path) -> list[CharacterProfilePayload]:
    """
    @brief      Load the optional persisted character profile artifact.
    @param[in]  project_root Active project root folder.
    @return     Ordered character profile payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.5.0
    """
    output_path = resolve_operation_path(
        project_root,
        "character_discovery",
        config.CHARACTER_PROFILE_FILE_NAME,
    )
    payload = load_optional_json_artifact(output_path)
    if not isinstance(payload, list):
        return []
    return [_normalize_character_profile(item) for item in payload if isinstance(item, dict)]


def build_character_voice_definition_prompt(character_profile: dict[str, object]) -> str:
    """
    @brief      Build one Qwen-oriented voice-definition prompt from the stored character voice brief.
    @param[in]  character_profile Character profile payload with raw facts and voice-brief fields.
    @return     Stable English voice-definition prompt paragraph.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.3.0
    """
    normalized_profile = _normalized_character_profile_core(character_profile)
    derived_voice_fields = _derived_voice_definition_fields(normalized_profile)
    for field_name in CHARACTER_VOICE_BRIEF_FIELDS:
        normalized_profile[field_name] = (
            str(normalized_profile.get(field_name, "")).strip() or derived_voice_fields[field_name]
        )
    character_name = str(normalized_profile.get("canonical_name", "Character")).strip() or "Character"
    descriptor_parts = [
        ("Sex/Gender", _character_voice_gender_instruction(normalized_profile)),
        ("Persona", _sentence_fragment(normalized_profile.get("voice_persona_summary"))),
        ("Timbre", _sentence_fragment(normalized_profile.get("voice_timbre_and_range"))),
        ("Pace", _sentence_fragment(normalized_profile.get("voice_pacing_and_rhythm"))),
        ("Emotion", _sentence_fragment(normalized_profile.get("voice_emotional_baseline"))),
        ("Articulation", _sentence_fragment(normalized_profile.get("voice_articulation_and_pronunciation"))),
        ("Constraints", _sentence_fragment(normalized_profile.get("voice_delivery_constraints"))),
    ]
    cleaned_descriptors = [f"{label}: {value}" for label, value in descriptor_parts if value]
    if cleaned_descriptors:
        return (f"Create a consistent spoken voice for {character_name}. " + " ".join(cleaned_descriptors)).strip()
    return (
        f"Create a consistent spoken voice for {character_name} with clear diction, stable identity, "
        "natural emotional control, and delivery suitable for repeated dialogue narration. "
        f"Sex/Gender: {_character_voice_gender_instruction(normalized_profile)}"
    )


def regenerate_character_voice_definition(profile_payload: dict[str, object]) -> CharacterProfilePayload:
    """
    @brief      Rebuild the structured voice-definition brief and final prompt from the current character facts.
    @param[in]  profile_payload Character profile payload.
    @return     Updated character profile payload with regenerated voice-definition fields.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    normalized_profile = _normalize_character_profile(profile_payload)
    derived_voice_fields = _derived_voice_definition_fields(normalized_profile)
    updated_profile = dict(normalized_profile)
    updated_profile.update(derived_voice_fields)
    updated_profile[CHARACTER_VOICE_PROMPT_FIELD] = build_character_voice_definition_prompt(updated_profile)
    updated_profile[CHARACTER_VOICE_SIGNATURE_FIELD] = voice_definition_source_signature(updated_profile)
    updated_profile["voice_definition_stale"] = False
    return updated_profile


def voice_definition_source_signature(profile_payload: dict[str, object]) -> str:
    """
    @brief      Build one stable fingerprint for the raw character facts that drive voice-definition generation.
    @param[in]  profile_payload Character profile payload.
    @return     Hex-encoded signature string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    signature_payload = {
        "canonical_name": str(profile_payload.get("canonical_name", "")).strip(),
        "gender_hint": str(profile_payload.get("gender_hint", "")).strip(),
        "age_band": str(profile_payload.get("age_band", "")).strip(),
        "role_summary": str(profile_payload.get("role_summary", "")).strip(),
        "description": str(profile_payload.get("description", "")).strip(),
        "temperament": str(profile_payload.get("temperament", "")).strip(),
        "social_status": str(profile_payload.get("social_status", "")).strip(),
        "speaking_style": str(profile_payload.get("speaking_style", "")).strip(),
        "accent_or_dialect_hints": str(profile_payload.get("accent_or_dialect_hints", "")).strip(),
        "voice_notes": str(profile_payload.get("voice_notes", "")).strip(),
    }
    return hashlib.sha1(  # noqa: S324
        json.dumps(signature_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def load_character_discovery_report(
    project_root: str | Path,
) -> CharacterDiscoveryReportPayload | None:
    """
    @brief      Load the optional persisted character-discovery report.
    @param[in]  project_root Active project root folder.
    @return     Persisted report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.3.0
    """
    report_path = resolve_operation_path(
        project_root,
        "character_discovery",
        config.CHARACTER_DISCOVERY_REPORT_FILE_NAME,
    )
    payload = load_optional_json_artifact(report_path)
    if payload is None:
        return None
    return dict(payload)


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def load_input_chunks(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load the optional chunk-input snapshot for character discovery.
    @param[in]  project_root Active project root folder.
    @return     Ordered chunk payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    input_chunks, _input_source = _resolve_discovery_input_chunks(Path(project_root))
    return input_chunks


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def start_or_continue_discovery(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
    force_rerun: bool = False,
) -> CharacterDiscoveryReportPayload:
    """
    @brief      Run AI-assisted character discovery for the active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  force_rerun Ignore compatible resumable state and start a fresh internal run.
    @return     Final character-discovery report payload.
    @exception  ValueError Raised on missing chunking input or invalid profile data.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.3.0
    """
    resolved_project_root = Path(project_root)
    source_chunks, input_source = _resolve_discovery_input_chunks(resolved_project_root)
    if not source_chunks:
        raise ValueError("Run text chunking before starting Character Discovery.")

    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    if not profile_id or not model_name or not base_url:
        raise ValueError("Character discovery requires a valid enabled AI profile.")

    prompt_template_service.validate_required_prompts(
        [
            "character_discovery_system",
            "character_discovery_window_user",
            "character_profile_synthesis_user",
        ]
    )
    system_prompt = prompt_template_service.render_prompt(
        "character_discovery_system",
        {},
    )
    budget_metadata = _build_budget_metadata(ai_profile_payload, system_prompt)
    input_paths = _persist_input_snapshots(
        resolved_project_root,
        source_chunks,
        manifest,
        input_source,
    )
    output_path = build_operation_output_path(
        resolved_project_root,
        "character_discovery",
        config.CHARACTER_PROFILE_FILE_NAME,
    )
    report_path = build_operation_output_path(
        resolved_project_root,
        "character_discovery",
        config.CHARACTER_DISCOVERY_REPORT_FILE_NAME,
    )
    state_path = build_operation_output_path(
        resolved_project_root,
        "character_discovery",
        config.CHARACTER_DISCOVERY_STATE_FILE_NAME,
    )

    input_fingerprint = _build_input_fingerprint(source_chunks)
    windows = _build_chunk_windows(
        source_chunks,
        config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
        config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
        budget_metadata,
    )
    if not windows:
        raise ValueError("Character discovery requires at least one chunk window.")

    existing_state = {} if force_rerun else (load_operation_state(resolved_project_root) or {})
    started_at = str(existing_state.get("started_at") or _utc_now_iso())
    (
        start_window_index,
        raw_candidates,
        merged_candidates,
        rejected_candidates,
        synthesized_profiles,
        log_relative_path,
    ) = _restore_resume_state(
        existing_state,
        input_fingerprint,
        profile_id,
        len(windows),
        budget_metadata,
    )
    token_usage = (
        _restore_token_usage(existing_state)
        if start_window_index > 0 or raw_candidates or merged_candidates or synthesized_profiles
        else token_usage_service.empty_token_usage()
    )
    log_path = _resolve_log_path(resolved_project_root, started_at, log_relative_path)
    chunk_map = {
        str(chunk.get("chunk_id", "")): dict(chunk) for chunk in source_chunks if str(chunk.get("chunk_id", "")).strip()
    }
    initial_progress_current = len(windows) + len(synthesized_profiles) if merged_candidates else start_window_index
    initial_progress_total = len(windows) + len(merged_candidates) if merged_candidates else len(windows)
    _write_operation_state(
        state_path=state_path,
        project_root=resolved_project_root,
        input_paths=input_paths,
        output_path=None,
        report_path=None,
        status="running",
        progress_current=initial_progress_current,
        progress_total=initial_progress_total,
        started_at=started_at,
        completed_at=None,
        profile_id=profile_id,
        source_chunk_count=len(source_chunks),
        character_count=len(synthesized_profiles),
        analyzed_window_count=len(windows),
        merged_candidate_count=len(merged_candidates),
        rejected_candidate_count=len(rejected_candidates),
        input_source=input_source,
        warnings=[],
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        resume_checkpoint={
            "input_fingerprint": input_fingerprint,
            "input_source": input_source,
            "profile_id": profile_id,
            "completed_window_count": start_window_index,
            "total_window_count": len(windows),
            "budget_metadata": dict(budget_metadata),
            "raw_candidates": list(raw_candidates),
            "merged_candidates": list(merged_candidates),
            "rejected_candidates": list(rejected_candidates),
            "synthesized_profiles": list(synthesized_profiles),
            "synthesis_progress_count": len(synthesized_profiles),
            "log_relative_path": relative_to_project(resolved_project_root, log_path),
        },
    )
    _emit_progress(
        progress_callback,
        initial_progress_current,
        initial_progress_total,
        (
            "Character profile synthesis in progress..."
            if merged_candidates
            else ("Resuming character discovery..." if start_window_index > 0 else "Character discovery in progress...")
        ),
        token_usage=token_usage,
    )

    for window_index in range(start_window_index, len(windows)):
        raise_if_cancelled(cancel_requested)
        window_records = windows[window_index]
        user_prompt = prompt_template_service.render_prompt(
            "character_discovery_window_user",
            {"units_block": _build_units_block(window_records)},
        )
        try:
            response_result = llm_provider_service.chat_json(
                ai_profile_payload,
                system_prompt,
                user_prompt,
                log_path=log_path,
                log_context={
                    "operation_kind": "character_discovery",
                    "stage_label": "character_discovery_window",
                    "profile_id": profile_id,
                    "window_index": window_index + 1,
                    "window_total": len(windows),
                },
                cancel_requested=cancel_requested,
            )
        except OperationCancelledError as error:
            raise OperationCancelledError(
                "Character discovery cancelled while waiting for the model response."
            ) from error
        response_payload = dict(response_result.get("payload", {}))
        token_usage = token_usage_service.merge_token_usage(
            token_usage,
            response_result.get("usage"),
        )
        raw_candidates.extend(
            _normalize_window_candidates(
                response_payload.get("characters", []),
                chunk_map,
            )
        )
        _write_operation_state(
            state_path=state_path,
            project_root=resolved_project_root,
            input_paths=input_paths,
            output_path=None,
            report_path=None,
            status="running",
            progress_current=window_index + 1,
            progress_total=len(windows),
            started_at=started_at,
            completed_at=None,
            profile_id=profile_id,
            source_chunk_count=len(source_chunks),
            character_count=0,
            analyzed_window_count=len(windows),
            merged_candidate_count=0,
            rejected_candidate_count=len(rejected_candidates),
            input_source=input_source,
            warnings=[],
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            budget_metadata=budget_metadata,
            resume_checkpoint={
                "input_fingerprint": input_fingerprint,
                "input_source": input_source,
                "profile_id": profile_id,
                "completed_window_count": window_index + 1,
                "total_window_count": len(windows),
                "budget_metadata": dict(budget_metadata),
                "raw_candidates": list(raw_candidates),
                "merged_candidates": [],
                "rejected_candidates": [],
                "synthesized_profiles": [],
                "synthesis_progress_count": 0,
                "log_relative_path": relative_to_project(resolved_project_root, log_path),
            },
        )
        _emit_progress(
            progress_callback,
            window_index + 1,
            len(windows),
            "Character discovery in progress...",
            token_usage=token_usage,
        )

    if not merged_candidates:
        merged_candidates, rejected_candidates = _merge_character_candidates_with_rejections(raw_candidates)
    total_progress = max(len(windows) + len(merged_candidates), 1)
    _write_operation_state(
        state_path=state_path,
        project_root=resolved_project_root,
        input_paths=input_paths,
        output_path=None,
        report_path=None,
        status="running",
        progress_current=len(windows) + len(synthesized_profiles),
        progress_total=total_progress,
        started_at=started_at,
        completed_at=None,
        profile_id=profile_id,
        source_chunk_count=len(source_chunks),
        character_count=len(synthesized_profiles),
        analyzed_window_count=len(windows),
        merged_candidate_count=len(merged_candidates),
        rejected_candidate_count=len(rejected_candidates),
        input_source=input_source,
        warnings=[],
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        resume_checkpoint={
            "input_fingerprint": input_fingerprint,
            "input_source": input_source,
            "profile_id": profile_id,
            "completed_window_count": len(windows),
            "total_window_count": len(windows),
            "budget_metadata": dict(budget_metadata),
            "raw_candidates": list(raw_candidates),
            "merged_candidates": list(merged_candidates),
            "rejected_candidates": list(rejected_candidates),
            "synthesized_profiles": list(synthesized_profiles),
            "synthesis_progress_count": len(synthesized_profiles),
            "log_relative_path": relative_to_project(resolved_project_root, log_path),
        },
    )
    for profile_index in range(len(synthesized_profiles), len(merged_candidates)):
        raise_if_cancelled(cancel_requested)
        candidate = _budgeted_synthesis_candidate_payload(
            dict(merged_candidates[profile_index]),
            budget_metadata,
        )
        user_prompt = prompt_template_service.render_prompt(
            "character_profile_synthesis_user",
            {
                "character_payload": json.dumps(
                    candidate,
                    indent=2,
                    ensure_ascii=False,
                )
            },
        )
        try:
            response_result = llm_provider_service.chat_json(
                ai_profile_payload,
                system_prompt,
                user_prompt,
                log_path=log_path,
                log_context={
                    "operation_kind": "character_discovery",
                    "stage_label": "character_profile_synthesis",
                    "profile_id": profile_id,
                    "window_index": profile_index + 1,
                    "window_total": max(len(merged_candidates), 1),
                },
                cancel_requested=cancel_requested,
            )
        except OperationCancelledError as error:
            raise OperationCancelledError(
                "Character discovery cancelled while waiting for the model response."
            ) from error
        response_payload = dict(response_result.get("payload", {}))
        token_usage = token_usage_service.merge_token_usage(
            token_usage,
            response_result.get("usage"),
        )
        synthesized_profiles.append(_build_profile_from_synthesis(response_payload, candidate))
        _write_operation_state(
            state_path=state_path,
            project_root=resolved_project_root,
            input_paths=input_paths,
            output_path=None,
            report_path=None,
            status="running",
            progress_current=len(windows) + len(synthesized_profiles),
            progress_total=total_progress,
            started_at=started_at,
            completed_at=None,
            profile_id=profile_id,
            source_chunk_count=len(source_chunks),
            character_count=len(synthesized_profiles),
            analyzed_window_count=len(windows),
            merged_candidate_count=len(merged_candidates),
            rejected_candidate_count=len(rejected_candidates),
            input_source=input_source,
            warnings=[],
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            budget_metadata=budget_metadata,
            resume_checkpoint={
                "input_fingerprint": input_fingerprint,
                "input_source": input_source,
                "profile_id": profile_id,
                "completed_window_count": len(windows),
                "total_window_count": len(windows),
                "budget_metadata": dict(budget_metadata),
                "raw_candidates": list(raw_candidates),
                "merged_candidates": list(merged_candidates),
                "rejected_candidates": list(rejected_candidates),
                "synthesized_profiles": list(synthesized_profiles),
                "synthesis_progress_count": len(synthesized_profiles),
                "log_relative_path": relative_to_project(resolved_project_root, log_path),
            },
        )
        _emit_progress(
            progress_callback,
            len(windows) + len(synthesized_profiles),
            total_progress,
            "Character profile synthesis in progress...",
            token_usage=token_usage,
        )

    ordered_profiles = sorted(synthesized_profiles, key=_profile_sort_key)
    report_payload = {
        "input_chunk_count": len(source_chunks),
        "input_source": input_source,
        "analyzed_window_count": len(windows),
        "merged_candidate_count": len(merged_candidates),
        "rejected_candidate_count": len(rejected_candidates),
        "rejected_candidates": list(rejected_candidates),
        "character_count": len(ordered_profiles),
        "review_status_summary": _review_status_summary(ordered_profiles),
        "character_discovery_mode": CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
        "character_profile_id_last_used": profile_id,
        "window_size": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
        "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
        "budget_metadata": dict(budget_metadata),
        "warning_count": 0,
        "warnings": [],
        "generated_at": _utc_now_iso(),
        "token_usage": token_usage,
    }
    output_path.write_text(
        json.dumps(ordered_profiles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_operation_state(
        state_path=state_path,
        project_root=resolved_project_root,
        input_paths=input_paths,
        output_path=output_path,
        report_path=report_path,
        status="completed",
        progress_current=total_progress,
        progress_total=total_progress,
        started_at=started_at,
        completed_at=report_payload["generated_at"],
        profile_id=profile_id,
        source_chunk_count=len(source_chunks),
        character_count=len(ordered_profiles),
        analyzed_window_count=len(windows),
        merged_candidate_count=len(merged_candidates),
        rejected_candidate_count=len(rejected_candidates),
        input_source=input_source,
        warnings=[],
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        budget_metadata=budget_metadata,
        resume_checkpoint=None,
    )
    _emit_progress(
        progress_callback,
        total_progress,
        total_progress,
        "Character discovery completed.",
        token_usage=token_usage,
    )
    return report_payload


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def add_character_profile(
    project_root: str | Path,
    canonical_name: str,
) -> list[CharacterProfilePayload]:
    """
    @brief      Append one new manual character profile to the persisted list.
    @param[in]  project_root Active project root folder.
    @param[in]  canonical_name Validated canonical character name.
    @return     Updated ordered character profile payload list.
    @exception  ValueError Raised when the name is invalid or duplicated.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    1.1.0
    """
    resolved_project_root = Path(project_root)
    existing_profiles = load_character_profiles(resolved_project_root)
    normalized_name = validate_manual_character_name(existing_profiles, canonical_name)
    updated_profiles = list(existing_profiles)
    updated_profiles.append(_build_manual_character_profile(existing_profiles, normalized_name))
    updated_profiles = sorted(updated_profiles, key=_profile_sort_key)
    _write_character_profiles(resolved_project_root, updated_profiles)
    return updated_profiles


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def validate_manual_character_name(
    existing_profiles: list[dict[str, object]],
    candidate_name: object,
    exclude_character_id: str | None = None,
) -> str:
    """
    @brief      Validate one manually entered character name.
    @param[in]  existing_profiles Existing persisted character profile list.
    @param[in]  candidate_name Candidate canonical name entered by the operator.
    @param[in]  exclude_character_id Optional character id ignored during duplicate checks.
    @return     Normalized stripped character name.
    @exception  ValueError Raised when the name is invalid or already exists.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.1
    """
    normalized_name = str(candidate_name or "").strip()
    if not normalized_name or not any(char.isalnum() for char in normalized_name):
        raise ValueError("invalid_name")
    normalized_identity = _normalize_identity(normalized_name)
    if not normalized_identity:
        raise ValueError("invalid_name")
    for profile in existing_profiles:
        if (
            exclude_character_id not in (None, "")
            and str(profile.get("character_id", "")).strip() == exclude_character_id
        ):
            continue
        names_to_check = [str(profile.get("canonical_name", ""))]
        names_to_check.extend(str(alias) for alias in list(profile.get("aliases", [])))
        for existing_name in names_to_check:
            if _normalize_identity(existing_name) == normalized_identity:
                raise ValueError("duplicate_name")
    return normalized_name


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def update_character_profile(
    project_root: str | Path,
    profile_payload: dict[str, object],
) -> list[CharacterProfilePayload]:
    """
    @brief      Persist one operator edit to an existing character profile.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_payload Updated profile payload.
    @return     Updated ordered character profile payload list.
    @exception  ValueError Raised when the profile id is unknown.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    1.0.0
    """
    resolved_project_root = Path(project_root)
    selected_profile_id = str(profile_payload.get("character_id", "")).strip()
    if not selected_profile_id:
        raise ValueError("Character profile payload is missing character_id.")
    existing_profiles = load_character_profiles(resolved_project_root)
    normalized_name = validate_manual_character_name(
        existing_profiles,
        profile_payload.get("canonical_name", ""),
        exclude_character_id=selected_profile_id,
    )
    updated_profiles: list[CharacterProfilePayload] = []
    found_profile = False
    for existing_profile in existing_profiles:
        if str(existing_profile.get("character_id", "")).strip() == selected_profile_id:
            existing_normalized_profile = _normalize_character_profile(existing_profile)
            merged_profile = _normalize_character_profile(profile_payload)
            merged_profile["canonical_name"] = normalized_name
            if not str(profile_payload.get("review_status", "")).strip():
                merged_profile["review_status"] = _edited_review_status(existing_normalized_profile)
            merged_profile["updated_at"] = _utc_now_iso()
            current_signature = voice_definition_source_signature(merged_profile)
            stored_signature = str(existing_normalized_profile.get(CHARACTER_VOICE_SIGNATURE_FIELD, "")).strip()
            if _voice_definition_block_changed(existing_normalized_profile, merged_profile) or not stored_signature:
                merged_profile[CHARACTER_VOICE_SIGNATURE_FIELD] = current_signature
            else:
                merged_profile[CHARACTER_VOICE_SIGNATURE_FIELD] = stored_signature
            merged_profile["voice_definition_stale"] = (
                str(merged_profile.get(CHARACTER_VOICE_SIGNATURE_FIELD, "")).strip() != current_signature
            )
            updated_profiles.append(merged_profile)
            found_profile = True
        else:
            updated_profiles.append(_normalize_character_profile(existing_profile))
    if not found_profile:
        raise ValueError(f"Unknown character profile: {selected_profile_id}")
    updated_profiles = sorted(updated_profiles, key=_profile_sort_key)
    _write_character_profiles(resolved_project_root, updated_profiles)
    return updated_profiles


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def delete_character_profile(
    project_root: str | Path,
    character_id: str,
) -> list[CharacterProfilePayload]:
    """
    @brief      Delete one persisted character profile from discovery output.
    @param[in]  project_root Active project root folder.
    @param[in]  character_id Selected character profile identifier.
    @return     Updated ordered character profile payload list.
    @exception  ValueError Raised when the character id is unknown.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    selected_character_id = str(character_id).strip()
    if not selected_character_id:
        raise ValueError("Character profile payload is missing character_id.")
    existing_profiles = load_character_profiles(resolved_project_root)
    updated_profiles = [
        dict(profile)
        for profile in existing_profiles
        if str(profile.get("character_id", "")).strip() != selected_character_id
    ]
    if len(updated_profiles) == len(existing_profiles):
        raise ValueError(f"Unknown character profile: {selected_character_id}")
    _write_character_profiles(resolved_project_root, updated_profiles)
    return updated_profiles


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def reset_character_discovery(project_root: str | Path) -> None:
    """
    @brief      Clear character-discovery artifacts and dependent runtime data while preserving narrator profiles.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    reset_operation_data(
        project_root,
        "character_discovery",
        include_current=True,
        keep_input_snapshots=False,
        preserve_operation_kinds=NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    )


# LOCAL HELPERS


def _write_character_profiles(
    project_root: Path,
    profiles: list[CharacterProfilePayload],
) -> None:
    """
    @brief      Persist the current character profile list and count metadata.
    @param[in]  project_root Active project root folder.
    @param[in]  profiles Ordered character profile payload list.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    output_path = build_operation_output_path(
        project_root,
        "character_discovery",
        config.CHARACTER_PROFILE_FILE_NAME,
    )
    persisted_profiles = [_persistable_character_profile(profile) for profile in profiles]
    output_path.write_text(
        json.dumps(persisted_profiles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _sync_character_count_metadata(project_root, len(profiles))


def _build_manual_character_profile(
    existing_profiles: list[CharacterProfilePayload],
    canonical_name: str,
) -> CharacterProfilePayload:
    """
    @brief      Build one persisted manual-character profile payload.
    @param[in]  existing_profiles Existing persisted character profile list.
    @param[in]  canonical_name Validated canonical character name.
    @return     New manual character profile payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    1.0.0
    """
    return regenerate_character_voice_definition(
        {
            "character_id": _next_manual_character_id(existing_profiles, canonical_name),
            "canonical_name": canonical_name,
            "aliases": [],
            "gender_hint": "",
            "age_band": "",
            "role_summary": "",
            "description": "",
            "temperament": "",
            "social_status": "",
            "speaking_style": "",
            "accent_or_dialect_hints": "",
            "voice_notes": "",
            "relationship_hints": [],
            "confidence": "",
            "review_status": CHARACTER_REVIEW_STATUS_MANUAL,
            "evidence": [
                {
                    "chunk_id": MANUAL_CHARACTER_EVIDENCE_CHUNK_ID,
                    "sequence_index": 0,
                    "source_excerpt": MANUAL_CHARACTER_EVIDENCE_NOTE,
                    "reason": MANUAL_CHARACTER_EVIDENCE_NOTE,
                }
            ],
            "updated_at": _utc_now_iso(),
        }
    )


def _next_manual_character_id(
    existing_profiles: list[CharacterProfilePayload],
    canonical_name: str,
) -> str:
    """
    @brief      Generate one unique persisted identifier for a manual character.
    @param[in]  existing_profiles Existing persisted character profile list.
    @param[in]  canonical_name Validated canonical character name.
    @return     Unique character identifier string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    base_slug = _slugify_character_id(canonical_name, len(existing_profiles) + 1)
    existing_ids = {str(profile.get("character_id", "")).strip() for profile in existing_profiles}
    if base_slug not in existing_ids:
        return base_slug
    suffix = 2
    while f"{base_slug}_{suffix}" in existing_ids:
        suffix += 1
    return f"{base_slug}_{suffix}"


def _sync_character_count_metadata(project_root: Path, character_count: int) -> None:
    """
    @brief      Update persisted operation metadata after manual list changes.
    @param[in]  project_root Active project root folder.
    @param[in]  character_count Current persisted character count.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    state_payload = load_operation_state(project_root)
    if not isinstance(state_payload, dict):
        return
    metadata = dict(state_payload.get("metadata") or {})
    metadata["character_count"] = character_count
    state_payload["metadata"] = metadata
    state_payload["updated_at"] = _utc_now_iso()
    state_path = build_operation_output_path(
        project_root,
        "character_discovery",
        config.CHARACTER_DISCOVERY_STATE_FILE_NAME,
    )
    write_json_atomic(state_path, state_payload)


def _persist_input_snapshots(
    project_root: Path,
    source_chunks: list[dict[str, object]],
    manifest: dict[str, object],
    input_source: str,
) -> list[Path]:
    """
    @brief      Persist the input snapshots.
    @param[in]  project_root Active project root folder.
    @param[in]  source_chunks Value for `source_chunks`.
    @param[in]  manifest Active project manifest payload.
    @param[in]  input_source Selected discovery input source token.
    @return     Existing input artifact paths used by the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    _ = source_chunks
    _ = manifest
    chunk_input_path = project_root / config.CHUNK_ARTIFACT_FILE_NAME
    clean_text_input_path = project_root / config.CLEANED_TEXT_FILE_NAME
    _ = input_source
    input_paths = [chunk_input_path]
    if not clean_text_input_path.is_file():
        clean_text_input_path = chunk_input_path
    input_paths.append(clean_text_input_path)
    deduped_paths: list[Path] = []
    for input_path in input_paths:
        if input_path not in deduped_paths:
            deduped_paths.append(input_path)
    return deduped_paths


def _resolve_discovery_input_chunks(project_root: Path) -> tuple[list[dict[str, object]], str]:
    """
    @brief      Resolve the authoritative internal input for character discovery.
    @param[in]  project_root Active project root folder.
    @return     Ordered discovery chunks plus the input-source token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.2.0
    """
    source_chunks = sorted(
        deterministic_chunking_service.load_chunks(project_root),
        key=lambda item: int(item.get("sequence_index", 0)),
    )
    return (
        [_discovery_chunk_from_source(source_chunk) for source_chunk in source_chunks],
        CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS,
    )


def _discovery_chunk_from_source(source_chunk: dict[str, object]) -> dict[str, object]:
    """
    @brief      Build one discovery chunk from canonical source chunking output.
    @param[in]  source_chunk Source chunk payload.
    @return     Discovery chunk payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    discovery_chunk = dict(source_chunk)
    text = str(discovery_chunk.get("text", "")).strip()
    discovery_chunk["source_text"] = text
    discovery_chunk["input_source"] = CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS
    discovery_chunk["dialogue_spans"] = _detect_dialogue_spans(text)
    return discovery_chunk


def _resolve_chunk_input_snapshot_path(project_root: Path) -> Path | None:
    """
    @brief      Resolve the chunk input snapshot path.
    @param[in]  project_root Active project root folder.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    candidate_path = project_root / config.CHUNK_ARTIFACT_FILE_NAME
    return candidate_path if candidate_path.is_file() else None


def _source_snapshot_base_name(manifest: dict[str, object]) -> str:
    """
    @brief      Execute the source snapshot base name helper.
    @param[in]  manifest Active project manifest payload.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    source_document = manifest.get("source_document", {})
    if isinstance(source_document, dict):
        original_name = str(source_document.get("original_name", "")).strip()
        if original_name:
            return Path(original_name).stem
    return Path(config.CHUNK_ARTIFACT_FILE_NAME).stem


def _build_input_fingerprint(source_chunks: list[dict[str, object]]) -> str:
    """
    @brief      Build the input fingerprint.
    @param[in]  source_chunks Value for `source_chunks`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    digest = hashlib.sha256()
    for chunk in source_chunks:
        digest.update(str(chunk.get("chunk_id", "")).encode("utf-8"))
        digest.update(b"\n")
        digest.update(str(chunk.get("sequence_index", 0)).encode("utf-8"))
        digest.update(b"\n")
        digest.update(str(chunk.get("input_source", "")).encode("utf-8"))
        digest.update(b"\n")
        digest.update(str(chunk.get("text", "")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _detect_dialogue_spans(text: str) -> list[dict[str, object]]:
    """
    @brief      Detect direct-dialogue spans inside one discovery text chunk.
    @param[in]  text Discovery input text.
    @return     Ordered dialogue-span payloads.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    spans: list[dict[str, object]] = []
    normalized_text = str(text)
    quote_patterns = (
        ('"([^"\\n]{1,500})"', "quote"),
        ("\u201c([^\u201d\\n]{1,500})\u201d", "quote"),
        ("\u00ab([^\u00bb\\n]{1,500})\u00bb", "quote"),
        ("\u300c([^\u300d\\n]{1,500})\u300d", "quote"),
        ("\u300e([^\u300f\\n]{1,500})\u300f", "quote"),
    )
    for pattern, marker_type in quote_patterns:
        for match in re.finditer(pattern, normalized_text):
            spans.append(
                _dialogue_span_payload(
                    marker_type,
                    normalized_text[match.start() : match.end()],
                    match.start(),
                    match.end(),
                    len(spans) + 1,
                )
            )
    search_offset = 0
    for line in normalized_text.splitlines():
        line_start = normalized_text.find(line, search_offset)
        search_offset = line_start + len(line) if line_start >= 0 else search_offset
        stripped_line = line.strip()
        if not stripped_line.startswith(("- ", "--", "\u2014", "\u2013")):
            continue
        start_offset = line_start + line.find(stripped_line) if line_start >= 0 else 0
        end_offset = start_offset + len(stripped_line)
        spans.append(
            _dialogue_span_payload(
                "dash",
                stripped_line,
                start_offset,
                end_offset,
                len(spans) + 1,
            )
        )
    return sorted(spans, key=lambda item: int(item.get("start_offset", 0)))


def _dialogue_span_payload(
    marker_type: str,
    source_text: str,
    start_offset: int,
    end_offset: int,
    sequence_index: int,
) -> dict[str, object]:
    """
    @brief      Build one normalized dialogue-span payload.
    @param[in]  marker_type Dialogue marker type.
    @param[in]  source_text Span source text.
    @param[in]  start_offset Span start offset.
    @param[in]  end_offset Span end offset.
    @param[in]  sequence_index One-based span sequence index.
    @return     Dialogue-span payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    return {
        "dialogue_span_id": f"dialogue-{sequence_index:03d}",
        "marker_type": marker_type,
        "source_excerpt": _excerpt_text(source_text),
        "start_offset": max(int(start_offset), 0),
        "end_offset": max(int(end_offset), 0),
        "confidence": EVIDENCE_CONFIDENCE_HIGH,
    }


def _build_chunk_windows(
    source_chunks: list[dict[str, object]],
    window_size: int,
    overlap: int,
    budget_metadata: BudgetMetadataPayload,
) -> list[list[dict[str, object]]]:
    """
    @brief      Build context-budgeted chunk windows.
    @param[in]  source_chunks Value for `source_chunks`.
    @param[in]  window_size Maximum chunk count allowed in one request.
    @param[in]  overlap Requested chunk overlap between adjacent windows.
    @param[in]  budget_metadata Context-budget metadata for the selected profile.
    @return     Derived helper result.
    @exception  ValueError Raised when one source chunk cannot fit inside the request budget.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if not source_chunks:
        return []
    max_window_chunks = max(1, int(window_size))
    window_overlap = max(0, min(int(overlap), max_window_chunks - 1))
    text_budget_tokens = int(budget_metadata["text_budget_tokens"])
    windows: list[list[dict[str, object]]] = []
    start_index = 0
    while start_index < len(source_chunks):
        end_index = start_index - 1
        current_window_tokens = 0
        current_window_count = 0
        while end_index + 1 < len(source_chunks) and current_window_count < max_window_chunks:
            candidate_chunk = source_chunks[end_index + 1]
            candidate_tokens = _estimate_text_tokens(_build_units_block([candidate_chunk]))
            if candidate_tokens > text_budget_tokens:
                chunk_id = str(candidate_chunk.get("chunk_id", "")).strip() or f"#{end_index + 2}"
                raise ValueError(
                    "AI-assisted character discovery cannot run because source chunk "
                    f"{chunk_id} exceeds the available request input budget "
                    f"({candidate_tokens} estimated tokens, {text_budget_tokens} available). "
                    "Use a larger context window, reduce max output tokens, or re-run chunking with smaller chunks."
                )
            if current_window_count > 0 and current_window_tokens + candidate_tokens > text_budget_tokens:
                break
            current_window_tokens += candidate_tokens
            current_window_count += 1
            end_index += 1
        windows.append(source_chunks[start_index : end_index + 1])
        next_start_index = end_index + 1
        if next_start_index >= len(source_chunks):
            break
        start_index = max(start_index + 1, next_start_index - window_overlap)
    return windows


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    system_prompt: str,
) -> BudgetMetadataPayload:
    """
    @brief      Build context-window budget metadata for AI character discovery.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  system_prompt Rendered character-discovery system prompt.
    @return     Context-budget metadata used for windowing and synthesis guards.
    @exception  ValueError Raised when context and output settings leave too little input room.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    context_window = max(
        1,
        int(ai_profile_payload.get("context_window", config.DEFAULT_LLM_CONTEXT_WINDOW)),
    )
    max_output_tokens = max(
        1,
        int(
            ai_profile_payload.get(
                "max_output_tokens",
                config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            )
        ),
    )
    discovery_prompt_shell = prompt_template_service.render_prompt(
        "character_discovery_window_user",
        {"units_block": ""},
    )
    synthesis_prompt_shell = prompt_template_service.render_prompt(
        "character_profile_synthesis_user",
        {"character_payload": ""},
    )
    prompt_budget_tokens = _estimate_text_tokens(f"{system_prompt}\n\n{discovery_prompt_shell}")
    synthesis_prompt_budget_tokens = _estimate_text_tokens(f"{system_prompt}\n\n{synthesis_prompt_shell}")
    safety_margin_tokens = max(
        config.DEFAULT_CHARACTER_DISCOVERY_MIN_SAFETY_MARGIN_TOKENS,
        int(context_window * config.DEFAULT_CHARACTER_DISCOVERY_SAFETY_MARGIN_CONTEXT_FRACTION),
    )
    text_budget_tokens = _available_character_discovery_budget(
        context_window,
        max_output_tokens,
        prompt_budget_tokens,
        safety_margin_tokens,
    )
    synthesis_payload_budget_tokens = _available_character_discovery_budget(
        context_window,
        max_output_tokens,
        synthesis_prompt_budget_tokens,
        safety_margin_tokens,
    )
    min_text_budget = config.DEFAULT_CHARACTER_DISCOVERY_MIN_TEXT_BUDGET_TOKENS
    if text_budget_tokens < min_text_budget:
        raise ValueError(
            "AI-assisted character discovery cannot run because the selected AI profile context window "
            "and max output tokens leave too little room for discovery input "
            f"({text_budget_tokens} estimated tokens available, {min_text_budget} required)."
        )
    if synthesis_payload_budget_tokens < min_text_budget:
        raise ValueError(
            "AI-assisted character discovery cannot run because the selected AI profile context window "
            "and max output tokens leave too little room for character synthesis input "
            f"({synthesis_payload_budget_tokens} estimated tokens available, {min_text_budget} required)."
        )
    return {
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "prompt_budget_tokens": prompt_budget_tokens,
        "text_budget_tokens": text_budget_tokens,
        "safety_margin_tokens": safety_margin_tokens,
        "max_window_chunks": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
        "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
        "synthesis_prompt_budget_tokens": synthesis_prompt_budget_tokens,
        "synthesis_payload_budget_tokens": synthesis_payload_budget_tokens,
        "synthesis_max_evidence_items": config.DEFAULT_CHARACTER_DISCOVERY_SYNTHESIS_MAX_EVIDENCE_ITEMS,
    }


def _available_character_discovery_budget(
    context_window: int,
    max_output_tokens: int,
    prompt_budget_tokens: int,
    safety_margin_tokens: int,
) -> int:
    """
    @brief      Compute the usable input budget for one character-discovery AI request.
    @param[in]  context_window Selected profile context window.
    @param[in]  max_output_tokens Selected profile maximum output token budget.
    @param[in]  prompt_budget_tokens Estimated prompt-shell token budget.
    @param[in]  safety_margin_tokens Reserved safety margin.
    @return     Usable input-token budget.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    available_text_budget = context_window - max_output_tokens - prompt_budget_tokens - safety_margin_tokens
    return min(
        int(context_window * config.DEFAULT_CHARACTER_DISCOVERY_TEXT_CONTEXT_FRACTION),
        available_text_budget,
    )


def _estimate_text_tokens(text: str) -> int:
    """
    @brief      Estimate token usage for local budget checks.
    @param[in]  text Value for `text`.
    @return     Estimated token count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    return max(1, len(text) // 4)


def _build_units_block(window_records: list[dict[str, object]]) -> str:
    """
    @brief      Build the units block.
    @param[in]  window_records Value for `window_records`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    blocks: list[str] = []
    for chunk in window_records:
        blocks.append(
            f"CHUNK_ID: {chunk.get('chunk_id', '')}\n"
            f"SEQUENCE_INDEX: {chunk.get('sequence_index', 0)}\n"
            f"CHAPTER_LABEL: {chunk.get('chapter_label', '') or ''}\n"
            f"INPUT_SOURCE: {chunk.get('input_source', CHARACTER_DISCOVERY_INPUT_SOURCE_CHUNKS)}\n"
            "DIALOGUE_SPANS_BEGIN\n"
            f"{json.dumps(list(chunk.get('dialogue_spans', [])), ensure_ascii=False)}\n"
            "DIALOGUE_SPANS_END\n"
            "TEXT_BEGIN\n"
            f"{str(chunk.get('text', ''))}\n"
            "TEXT_END"
        )
    return "\n\n".join(blocks).strip()


def _restore_resume_state(
    existing_state: dict[str, object],
    input_fingerprint: str,
    profile_id: str,
    total_windows: int,
    budget_metadata: BudgetMetadataPayload,
) -> tuple[
    int,
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    str | None,
]:
    """
    @brief      Restore the resume state.
    @param[in]  existing_state Value for `existing_state`.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  profile_id Profile identifier.
    @param[in]  total_windows Total number of windows.
    @param[in]  budget_metadata Current context-budget metadata.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.1
    """
    if str(existing_state.get("status", "")) not in {"running", "failed"}:
        return 0, [], [], [], [], None
    if str(existing_state.get("mode", "")) != CHARACTER_DISCOVERY_MODE_AI_ASSISTED:
        return 0, [], [], [], [], None
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    if str(resume_checkpoint.get("input_fingerprint", "")) != input_fingerprint:
        return 0, [], [], [], [], None
    if str(resume_checkpoint.get("profile_id", "")) != profile_id:
        return 0, [], [], [], [], None
    if int(resume_checkpoint.get("total_window_count", 0)) != total_windows:
        return 0, [], [], [], [], None
    if dict(resume_checkpoint.get("budget_metadata") or {}) != dict(budget_metadata):
        return 0, [], [], [], [], None
    return (
        min(int(resume_checkpoint.get("completed_window_count", 0)), total_windows),
        _restore_mapping_list(resume_checkpoint.get("raw_candidates")),
        _restore_mapping_list(resume_checkpoint.get("merged_candidates")),
        _restore_mapping_list(resume_checkpoint.get("rejected_candidates")),
        _restore_mapping_list(resume_checkpoint.get("synthesized_profiles")),
        (
            None
            if resume_checkpoint.get("log_relative_path") in (None, "")
            else str(resume_checkpoint.get("log_relative_path"))
        ),
    )


def _restore_token_usage(existing_state: dict[str, object]) -> TokenUsagePayload:
    """
    @brief      Restore the token usage.
    @param[in]  existing_state Value for `existing_state`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return token_usage_service.empty_token_usage()
    return token_usage_service.restore_token_usage(metadata.get("token_usage"))


def _restore_mapping_list(payload: object) -> list[dict[str, object]]:
    """
    @brief      Restore the mapping list.
    @param[in]  payload Optional payload processed by the helper.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def _resolve_log_path(
    project_root: Path,
    started_at: str,
    log_relative_path: str | None,
) -> Path:
    """
    @brief      Resolve the log path.
    @param[in]  project_root Active project root folder.
    @param[in]  started_at Value for `started_at`.
    @param[in]  log_relative_path Path for `log_relative_path`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if log_relative_path not in (None, ""):
        resolved_log_path = project_root / str(log_relative_path)
        resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
        if not resolved_log_path.exists():
            resolved_log_path.write_text("", encoding="utf-8")
        return resolved_log_path
    timestamp_token = started_at.replace("-", "").replace(":", "").replace("+", "_").replace(".", "")
    resolved_log_path = build_operation_output_path(
        project_root,
        "character_discovery",
        config.ai_transaction_log_file_name("characters", timestamp_token),
    )
    if not resolved_log_path.exists():
        resolved_log_path.write_text("", encoding="utf-8")
    return resolved_log_path


def _write_operation_state(
    state_path: Path,
    project_root: Path,
    input_paths: list[Path],
    output_path: Path | None,
    report_path: Path | None,
    status: str,
    progress_current: int,
    progress_total: int,
    started_at: str,
    completed_at: str | None,
    profile_id: str,
    source_chunk_count: int,
    character_count: int,
    analyzed_window_count: int,
    merged_candidate_count: int,
    rejected_candidate_count: int,
    input_source: str,
    warnings: list[str],
    input_fingerprint: str,
    log_path: Path,
    token_usage: TokenUsagePayload,
    budget_metadata: BudgetMetadataPayload,
    resume_checkpoint: dict[str, object] | None,
) -> None:
    """
    @brief      Write the operation state.
    @param[in]  state_path Operation-state file path.
    @param[in]  project_root Active project root folder.
    @param[in]  input_paths Value for `input_paths`.
    @param[in]  output_path Output file path.
    @param[in]  report_path Report file path.
    @param[in]  status Value for `status`.
    @param[in]  progress_current Value for `progress_current`.
    @param[in]  progress_total Value for `progress_total`.
    @param[in]  started_at Value for `started_at`.
    @param[in]  completed_at Value for `completed_at`.
    @param[in]  profile_id Profile identifier.
    @param[in]  source_chunk_count Value for `source_chunk_count`.
    @param[in]  character_count Value for `character_count`.
    @param[in]  analyzed_window_count Value for `analyzed_window_count`.
    @param[in]  merged_candidate_count Value for `merged_candidate_count`.
    @param[in]  rejected_candidate_count Value for `rejected_candidate_count`.
    @param[in]  input_source Selected discovery input source token.
    @param[in]  warnings Value for `warnings`.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  log_path Operation log file path.
    @param[in]  token_usage Value for `token_usage`.
    @param[in]  budget_metadata Context-budget metadata used by discovery requests.
    @param[in]  resume_checkpoint Value for `resume_checkpoint`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    artifact_paths = [relative_to_project(project_root, log_path)]
    if report_path is not None and report_path.is_file():
        artifact_paths.insert(0, relative_to_project(project_root, report_path))
    state_payload: OperationStatePayload = {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": status,
        "input_paths": [
            relative_to_project(project_root, input_path) for input_path in input_paths if input_path.is_file()
        ],
        "output_paths": (
            [relative_to_project(project_root, output_path)]
            if output_path is not None and output_path.is_file()
            else []
        ),
        "artifact_paths": artifact_paths,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "mode": CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
        "started_at": started_at,
        "completed_at": completed_at,
        "updated_at": _utc_now_iso(),
        "warning_count": len(warnings),
        "metadata": {
            "ai_profile_id": profile_id,
            "source_chunk_count": source_chunk_count,
            "character_count": character_count,
            "analyzed_window_count": analyzed_window_count,
            "merged_candidate_count": merged_candidate_count,
            "rejected_candidate_count": rejected_candidate_count,
            "input_source": input_source,
            "window_size": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
            "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
            "warnings": list(warnings),
            "input_fingerprint": input_fingerprint,
            "log_relative_path": relative_to_project(project_root, log_path),
            "token_usage": token_usage_service.coerce_token_usage(token_usage),
            "budget_metadata": dict(budget_metadata),
        },
        "resume_checkpoint": (None if resume_checkpoint is None else dict(resume_checkpoint)),
    }
    write_json_atomic(state_path, state_payload)


def _normalize_window_candidates(
    payload: object,
    chunk_map: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Normalize the window candidates.
    @param[in]  payload Optional payload processed by the helper.
    @param[in]  chunk_map Value for `chunk_map`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if not isinstance(payload, list):
        return []
    normalized_candidates: list[dict[str, object]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        canonical_name = str(entry.get("canonical_name") or entry.get("name") or "").strip()
        if not canonical_name:
            continue
        evidence = _normalize_evidence(entry.get("evidence", []), chunk_map)
        normalized_candidates.append(
            {
                "canonical_name": canonical_name,
                "aliases": _normalize_string_list(entry.get("aliases", [])),
                "gender_hint": str(entry.get("gender_hint", "")).strip(),
                "age_band": str(entry.get("age_band", "")).strip(),
                "role_summary": str(entry.get("role_summary", "")).strip(),
                "description": str(entry.get("description", "")).strip(),
                "temperament": str(entry.get("temperament", "")).strip(),
                "social_status": str(entry.get("social_status", "")).strip(),
                "speaking_style": str(entry.get("speaking_style", "")).strip(),
                "accent_or_dialect_hints": str(entry.get("accent_or_dialect_hints", "")).strip(),
                "voice_notes": str(entry.get("voice_notes", "")).strip(),
                "voice_persona_summary": str(entry.get("voice_persona_summary", "")).strip(),
                "voice_timbre_and_range": str(entry.get("voice_timbre_and_range", "")).strip(),
                "voice_pacing_and_rhythm": str(entry.get("voice_pacing_and_rhythm", "")).strip(),
                "voice_emotional_baseline": str(entry.get("voice_emotional_baseline", "")).strip(),
                "voice_articulation_and_pronunciation": str(
                    entry.get("voice_articulation_and_pronunciation", "")
                ).strip(),
                "voice_delivery_constraints": str(entry.get("voice_delivery_constraints", "")).strip(),
                "voice_definition_prompt": str(entry.get("voice_definition_prompt", "")).strip(),
                "relationship_hints": _normalize_string_list(entry.get("relationship_hints", [])),
                "confidence": str(entry.get("confidence", "")).strip(),
                "evidence": evidence,
                "has_dialogue_evidence": any(
                    _evidence_has_direct_dialogue(item) for item in evidence if item.get("chunk_id") in chunk_map
                ),
            }
        )
    return normalized_candidates


def _normalize_string_list(payload: object) -> list[str]:
    """
    @brief      Normalize the string list.
    @param[in]  payload Optional payload processed by the helper.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if isinstance(payload, str):
        items = [item.strip() for item in payload.split(",")]
    elif isinstance(payload, list):
        items = [str(item).strip() for item in payload]
    else:
        items = []
    normalized_items: list[str] = []
    for item in items:
        if item and item not in normalized_items:
            normalized_items.append(item)
    return normalized_items


def _normalize_evidence(
    payload: object,
    chunk_map: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Normalize the evidence.
    @param[in]  payload Optional payload processed by the helper.
    @param[in]  chunk_map Value for `chunk_map`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if not isinstance(payload, list):
        return []
    evidence_items: list[dict[str, object]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        chunk_id = str(entry.get("chunk_id", "")).strip()
        if not chunk_id or chunk_id not in chunk_map:
            continue
        source_chunk = dict(chunk_map[chunk_id])
        dialogue_span_id = str(entry.get("dialogue_span_id", "")).strip()
        source_excerpt = str(entry.get("source_excerpt", "")).strip()
        if not source_excerpt and dialogue_span_id:
            source_excerpt = _dialogue_span_excerpt(source_chunk, dialogue_span_id)
        if not source_excerpt:
            source_excerpt = _excerpt_text(str(source_chunk.get("text", "")))
        reason = str(entry.get("reason", "")).strip() or "Mentioned in source chunk."
        confidence = _normalize_evidence_confidence(
            entry.get("confidence"),
            source_chunk,
            dialogue_span_id,
            source_excerpt,
            reason,
        )
        evidence_items.append(
            {
                "chunk_id": chunk_id,
                "sequence_index": int(source_chunk.get("sequence_index", 0)),
                "dialogue_span_id": dialogue_span_id,
                "source_excerpt": source_excerpt,
                "reason": reason,
                "confidence": confidence,
            }
        )
    return _dedupe_evidence(evidence_items)


def _dialogue_span_excerpt(source_chunk: dict[str, object], dialogue_span_id: str) -> str:
    """
    @brief      Resolve one dialogue-span excerpt from a source chunk.
    @param[in]  source_chunk Discovery chunk payload.
    @param[in]  dialogue_span_id Dialogue span identifier.
    @return     Span excerpt or an empty string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    for dialogue_span in list(source_chunk.get("dialogue_spans", [])):
        if not isinstance(dialogue_span, dict):
            continue
        if str(dialogue_span.get("dialogue_span_id", "")).strip() == dialogue_span_id:
            return str(dialogue_span.get("source_excerpt", "")).strip()
    return ""


def _normalize_evidence_confidence(
    raw_confidence: object,
    source_chunk: dict[str, object],
    dialogue_span_id: str,
    source_excerpt: str,
    reason: str,
) -> str:
    """
    @brief      Normalize or derive one evidence confidence token.
    @param[in]  raw_confidence Confidence value returned by the model.
    @param[in]  source_chunk Discovery chunk payload.
    @param[in]  dialogue_span_id Optional referenced dialogue span id.
    @param[in]  source_excerpt Evidence source excerpt.
    @param[in]  reason Evidence reason.
    @return     Evidence confidence token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    confidence = str(raw_confidence or "").strip().casefold()
    if confidence in {EVIDENCE_CONFIDENCE_HIGH, EVIDENCE_CONFIDENCE_MEDIUM, EVIDENCE_CONFIDENCE_LOW}:
        return confidence
    if dialogue_span_id and _dialogue_span_excerpt(source_chunk, dialogue_span_id):
        return EVIDENCE_CONFIDENCE_HIGH
    if _text_contains_dialogue_markers(source_excerpt):
        return EVIDENCE_CONFIDENCE_HIGH
    if _reason_mentions_dialogue(reason):
        return EVIDENCE_CONFIDENCE_MEDIUM
    return EVIDENCE_CONFIDENCE_LOW


def _merge_character_candidates(
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Merge the character candidates.
    @param[in]  candidates Value for `candidates`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    merged, _rejected = _merge_character_candidates_with_rejections(candidates)
    return merged


def _merge_character_candidates_with_rejections(
    candidates: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """
    @brief      Merge candidates by identity and retain rejected candidate diagnostics.
    @param[in]  candidates Candidate payload list.
    @return     Accepted merged candidates and rejected candidate diagnostics.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    merged = [_merge_candidate_identity_group(group) for group in _group_character_candidates_by_identity(candidates)]
    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for entry in sorted(merged, key=_candidate_sort_key):
        entry["evidence"] = _restore_evidence(entry.get("evidence", []))
        if not entry["evidence"]:
            rejected.append(_rejected_candidate_payload(entry, "missing_evidence"))
            continue
        if not _candidate_has_spoken_dialogue(entry):
            rejected.append(_rejected_candidate_payload(entry, "missing_spoken_dialogue_evidence"))
            continue
        accepted.append(entry)
    for index, entry in enumerate(accepted, start=1):
        entry["character_id"] = _slugify_character_id(
            str(entry.get("canonical_name", "")),
            index,
        )
    return accepted, rejected


def _group_character_candidates_by_identity(candidates: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    """
    @brief      Group candidates by normalized canonical or alias identity.
    @param[in]  candidates Candidate payload list.
    @return     Identity groups.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    groups: list[list[dict[str, object]]] = []
    for candidate in candidates:
        alias_keys = {_normalize_identity(str(candidate.get("canonical_name", "")))}
        alias_keys.update(_normalize_identity(alias) for alias in list(candidate.get("aliases", [])))
        alias_keys.discard("")
        target_group = None
        for group in groups:
            group_alias_keys: set[str] = set()
            for group_candidate in group:
                group_alias_keys.add(_normalize_identity(str(group_candidate.get("canonical_name", ""))))
                group_alias_keys.update(
                    _normalize_identity(alias) for alias in list(group_candidate.get("aliases", []))
                )
            if alias_keys.intersection(group_alias_keys):
                target_group = group
                break
        if target_group is None:
            groups.append([dict(candidate)])
        else:
            target_group.append(dict(candidate))
    return groups


def _merge_candidate_identity_group(identity_group: list[dict[str, object]]) -> dict[str, object]:
    """
    @brief      Synthesize one candidate payload from an identity group.
    @param[in]  identity_group Candidates believed to represent the same character.
    @return     Merged candidate payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    target: dict[str, object] = {}
    alias_keys: set[str] = set()
    for candidate in identity_group:
        candidate_alias_keys = {_normalize_identity(str(candidate.get("canonical_name", "")))}
        candidate_alias_keys.update(_normalize_identity(alias) for alias in list(candidate.get("aliases", [])))
        candidate_alias_keys.discard("")
        alias_keys.update(candidate_alias_keys)
        if not target:
            target = dict(candidate)
            continue
        target["aliases"] = _normalize_string_list(list(target.get("aliases", [])) + list(candidate.get("aliases", [])))
        target["relationship_hints"] = _normalize_string_list(
            list(target.get("relationship_hints", [])) + list(candidate.get("relationship_hints", []))
        )
        target["evidence"] = _dedupe_evidence(
            _restore_evidence(target.get("evidence", [])) + _restore_evidence(candidate.get("evidence", []))
        )
        target["has_dialogue_evidence"] = bool(target.get("has_dialogue_evidence")) or bool(
            candidate.get("has_dialogue_evidence")
        )
        for field_name in (
            "gender_hint",
            "age_band",
            "role_summary",
            "description",
            "temperament",
            "social_status",
            "speaking_style",
            "accent_or_dialect_hints",
            "voice_notes",
            "voice_persona_summary",
            "voice_timbre_and_range",
            "voice_pacing_and_rhythm",
            "voice_emotional_baseline",
            "voice_articulation_and_pronunciation",
            "voice_delivery_constraints",
            "voice_definition_prompt",
            "confidence",
        ):
            existing_value = str(target.get(field_name, "")).strip()
            candidate_value = str(candidate.get(field_name, "")).strip()
            if candidate_value and len(candidate_value) > len(existing_value):
                target[field_name] = candidate_value
    target["identity_alias_keys"] = sorted(alias_keys)
    target["identity_merge_count"] = len(identity_group)
    return target


def _rejected_candidate_payload(candidate: dict[str, object], reason: str) -> dict[str, object]:
    """
    @brief      Build one rejected-candidate diagnostic payload.
    @param[in]  candidate Candidate payload.
    @param[in]  reason Rejection reason token.
    @return     Rejected-candidate diagnostic payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    evidence = _restore_evidence(candidate.get("evidence", []))
    return {
        "canonical_name": str(candidate.get("canonical_name", "")).strip(),
        "reason": reason,
        "evidence_count": len(evidence),
        "identity_merge_count": int(candidate.get("identity_merge_count", 1)),
    }


def _restore_evidence(payload: object) -> list[dict[str, object]]:
    """
    @brief      Restore the evidence.
    @param[in]  payload Optional payload processed by the helper.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def _dedupe_evidence(
    evidence_items: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Execute the dedupe evidence helper.
    @param[in]  evidence_items Value for `evidence_items`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, int, str]] = set()
    for item in sorted(
        evidence_items,
        key=lambda value: (
            int(value.get("sequence_index", 0)),
            str(value.get("chunk_id", "")),
            str(value.get("reason", "")),
        ),
    ):
        key = (
            str(item.get("chunk_id", "")),
            int(item.get("sequence_index", 0)),
            str(item.get("reason", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(item))
    return deduped


def _budgeted_synthesis_candidate_payload(
    candidate: dict[str, object],
    budget_metadata: BudgetMetadataPayload,
) -> dict[str, object]:
    """
    @brief      Trim one merged candidate payload so synthesis input stays inside the selected profile budget.
    @param[in]  candidate Merged character candidate payload.
    @param[in]  budget_metadata Context-budget metadata for the selected profile.
    @return     Candidate payload safe to serialize into the synthesis prompt.
    @exception  ValueError Raised when even the minimum candidate payload exceeds the synthesis budget.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    evidence_items = _rank_synthesis_evidence(_restore_evidence(candidate.get("evidence", [])))
    max_evidence_items = max(1, int(budget_metadata["synthesis_max_evidence_items"]))
    payload = _synthesis_candidate_payload(candidate, evidence_items[:max_evidence_items])
    payload_budget_tokens = int(budget_metadata["synthesis_payload_budget_tokens"])
    if _estimate_text_tokens(json.dumps(payload, ensure_ascii=False)) <= payload_budget_tokens:
        return payload
    for evidence_count in range(min(max_evidence_items, len(evidence_items)) - 1, 0, -1):
        payload = _synthesis_candidate_payload(candidate, evidence_items[:evidence_count])
        if _estimate_text_tokens(json.dumps(payload, ensure_ascii=False)) <= payload_budget_tokens:
            return payload
    payload = _synthesis_candidate_payload(candidate, [])
    if _estimate_text_tokens(json.dumps(payload, ensure_ascii=False)) <= payload_budget_tokens:
        return payload
    character_name = str(candidate.get("canonical_name", "")).strip() or "Unknown character"
    raise ValueError(
        "AI-assisted character discovery cannot synthesize a profile for "
        f"{character_name!r} because the merged candidate payload exceeds the available synthesis budget "
        f"({payload_budget_tokens} estimated tokens)."
    )


def _synthesis_candidate_payload(
    candidate: dict[str, object],
    evidence_items: list[dict[str, object]],
) -> dict[str, object]:
    """
    @brief      Build the compact candidate payload sent to final character-profile synthesis.
    @param[in]  candidate Merged candidate payload.
    @param[in]  evidence_items Selected evidence payloads.
    @return     Compact synthesis input payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    return {
        "character_id": str(candidate.get("character_id", "")).strip(),
        "canonical_name": str(candidate.get("canonical_name", "")).strip(),
        "aliases": _normalize_string_list(candidate.get("aliases", [])),
        "role_summary": str(candidate.get("role_summary", "")).strip(),
        "confidence": str(candidate.get("confidence", "")).strip(),
        "identity_merge_count": int(candidate.get("identity_merge_count", 1)),
        "evidence": [_compact_synthesis_evidence(item) for item in evidence_items],
    }


def _rank_synthesis_evidence(evidence_items: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Rank evidence items for a compact synthesis payload.
    @param[in]  evidence_items Full merged evidence payload list.
    @return     Ordered evidence list, preferring direct dialogue and early source order.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    confidence_rank = {
        EVIDENCE_CONFIDENCE_HIGH: 0,
        EVIDENCE_CONFIDENCE_MEDIUM: 1,
        EVIDENCE_CONFIDENCE_LOW: 2,
    }
    return sorted(
        evidence_items,
        key=lambda item: (
            confidence_rank.get(str(item.get("confidence", "")).casefold(), 3),
            int(item.get("sequence_index", 0)),
            str(item.get("chunk_id", "")),
        ),
    )


def _compact_synthesis_evidence(evidence_item: dict[str, object]) -> dict[str, object]:
    """
    @brief      Build one compact evidence item for synthesis input.
    @param[in]  evidence_item Normalized evidence item.
    @return     Compact evidence payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    return {
        "chunk_id": str(evidence_item.get("chunk_id", "")).strip(),
        "sequence_index": int(evidence_item.get("sequence_index", 0)),
        "dialogue_span_id": str(evidence_item.get("dialogue_span_id", "")).strip(),
        "source_excerpt": _excerpt_text(str(evidence_item.get("source_excerpt", "")).strip()),
        "reason": _excerpt_text(str(evidence_item.get("reason", "")).strip(), limit=120),
        "confidence": str(evidence_item.get("confidence", "")).strip(),
    }


def _build_profile_from_synthesis(
    response_payload: dict[str, object],
    candidate: dict[str, object],
) -> CharacterProfilePayload:
    """
    @brief      Build the profile from synthesis.
    @param[in]  response_payload Payload for `response_payload`.
    @param[in]  candidate Value for `candidate`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return _profile_with_synchronized_voice_definition(
        {
            "character_id": str(candidate.get("character_id", "")),
            "canonical_name": str(
                response_payload.get(
                    "canonical_name",
                    candidate.get("canonical_name", ""),
                )
            ).strip(),
            "aliases": _normalize_string_list(response_payload.get("aliases", candidate.get("aliases", []))),
            "gender_hint": str(response_payload.get("gender_hint", candidate.get("gender_hint", ""))).strip(),
            "age_band": str(response_payload.get("age_band", candidate.get("age_band", ""))).strip(),
            "role_summary": str(
                response_payload.get(
                    "role_summary",
                    candidate.get("role_summary", ""),
                )
            ).strip(),
            "description": str(response_payload.get("description", candidate.get("description", ""))).strip(),
            "temperament": str(response_payload.get("temperament", candidate.get("temperament", ""))).strip(),
            "social_status": str(
                response_payload.get(
                    "social_status",
                    candidate.get("social_status", ""),
                )
            ).strip(),
            "speaking_style": str(
                response_payload.get(
                    "speaking_style",
                    candidate.get("speaking_style", ""),
                )
            ).strip(),
            "accent_or_dialect_hints": str(
                response_payload.get(
                    "accent_or_dialect_hints",
                    candidate.get("accent_or_dialect_hints", ""),
                )
            ).strip(),
            "voice_notes": str(response_payload.get("voice_notes", candidate.get("voice_notes", ""))).strip(),
            "voice_persona_summary": str(
                response_payload.get("voice_persona_summary", candidate.get("voice_persona_summary", ""))
            ).strip(),
            "voice_timbre_and_range": str(
                response_payload.get("voice_timbre_and_range", candidate.get("voice_timbre_and_range", ""))
            ).strip(),
            "voice_pacing_and_rhythm": str(
                response_payload.get("voice_pacing_and_rhythm", candidate.get("voice_pacing_and_rhythm", ""))
            ).strip(),
            "voice_emotional_baseline": str(
                response_payload.get("voice_emotional_baseline", candidate.get("voice_emotional_baseline", ""))
            ).strip(),
            "voice_articulation_and_pronunciation": str(
                response_payload.get(
                    "voice_articulation_and_pronunciation",
                    candidate.get("voice_articulation_and_pronunciation", ""),
                )
            ).strip(),
            "voice_delivery_constraints": str(
                response_payload.get("voice_delivery_constraints", candidate.get("voice_delivery_constraints", ""))
            ).strip(),
            "voice_definition_prompt": str(
                response_payload.get("voice_definition_prompt", candidate.get("voice_definition_prompt", ""))
            ).strip(),
            "relationship_hints": _normalize_string_list(
                response_payload.get(
                    "relationship_hints",
                    candidate.get("relationship_hints", []),
                )
            ),
            "confidence": str(response_payload.get("confidence", candidate.get("confidence", ""))).strip(),
            "review_status": _normalize_review_status(
                response_payload.get(
                    "review_status",
                    candidate.get("review_status", CHARACTER_REVIEW_STATUS_DISCOVERED),
                )
            ),
            "evidence": _restore_evidence(response_payload.get("evidence", candidate.get("evidence", [])))
            or _restore_evidence(candidate.get("evidence", [])),
            "updated_at": _utc_now_iso(),
        }
    )


def _normalize_character_profile(profile_payload: dict[str, object]) -> CharacterProfilePayload:
    """
    @brief      Normalize one stored character profile and backfill the voice-definition defaults.
    @param[in]  profile_payload Raw or partial character profile payload.
    @return     Normalized persisted profile payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    normalized_profile = _normalized_character_profile_core(profile_payload)
    derived_voice_fields = _derived_voice_definition_fields(normalized_profile)
    for field_name in CHARACTER_VOICE_BRIEF_FIELDS:
        normalized_profile[field_name] = (
            str(normalized_profile.get(field_name, "")).strip() or derived_voice_fields[field_name]
        )
    normalized_voice_prompt = str(normalized_profile.get(CHARACTER_VOICE_PROMPT_FIELD, "")).strip()
    normalized_profile[CHARACTER_VOICE_PROMPT_FIELD] = _ensure_character_voice_prompt_gender_instruction(
        normalized_voice_prompt or build_character_voice_definition_prompt(normalized_profile),
        normalized_profile,
    )
    current_signature = voice_definition_source_signature(normalized_profile)
    stored_signature = str(normalized_profile.get(CHARACTER_VOICE_SIGNATURE_FIELD, "")).strip()
    normalized_profile["voice_definition_stale"] = bool(stored_signature and stored_signature != current_signature)
    return normalized_profile


def _normalize_review_status(raw_status: object) -> str:
    """
    @brief      Normalize one internal character review-status token.
    @param[in]  raw_status Raw review status.
    @return     Supported review-status token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    review_status = str(raw_status or "").strip().casefold()
    if review_status in CHARACTER_REVIEW_STATUSES:
        return review_status
    return CHARACTER_REVIEW_STATUS_DISCOVERED


def _edited_review_status(existing_profile: dict[str, object]) -> str:
    """
    @brief      Derive review status for an operator-edited profile without UI changes.
    @param[in]  existing_profile Existing normalized character profile.
    @return     Updated review-status token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    existing_status = _normalize_review_status(existing_profile.get("review_status", ""))
    if existing_status == CHARACTER_REVIEW_STATUS_MANUAL:
        return CHARACTER_REVIEW_STATUS_MANUAL
    return CHARACTER_REVIEW_STATUS_EDITED


def _review_status_summary(profiles: list[dict[str, object]]) -> dict[str, int]:
    """
    @brief      Build a count summary for persisted internal review statuses.
    @param[in]  profiles Character profile payload list.
    @return     Review-status count summary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    summary = dict.fromkeys(sorted(CHARACTER_REVIEW_STATUSES), 0)
    for profile in profiles:
        review_status = _normalize_review_status(profile.get("review_status", ""))
        summary[review_status] = summary.get(review_status, 0) + 1
    return summary


def _normalized_character_profile_core(profile_payload: dict[str, object]) -> CharacterProfilePayload:
    """
    @brief      Normalize one character profile payload without regenerating the final voice-definition prompt.
    @param[in]  profile_payload Raw or partial character profile payload.
    @return     Core normalized profile payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    1.0.0
    """
    normalized_profile: CharacterProfilePayload = {
        "character_id": str(profile_payload.get("character_id", "")).strip(),
        "canonical_name": str(profile_payload.get("canonical_name", "")).strip(),
        "aliases": _normalize_string_list(profile_payload.get("aliases", [])),
        "gender_hint": str(profile_payload.get("gender_hint", "")).strip(),
        "age_band": str(profile_payload.get("age_band", "")).strip(),
        "role_summary": str(profile_payload.get("role_summary", "")).strip(),
        "description": str(profile_payload.get("description", "")).strip(),
        "temperament": str(profile_payload.get("temperament", "")).strip(),
        "social_status": str(profile_payload.get("social_status", "")).strip(),
        "speaking_style": str(profile_payload.get("speaking_style", "")).strip(),
        "accent_or_dialect_hints": str(profile_payload.get("accent_or_dialect_hints", "")).strip(),
        "voice_notes": str(profile_payload.get("voice_notes", "")).strip(),
        "voice_persona_summary": str(profile_payload.get("voice_persona_summary", "")).strip(),
        "voice_timbre_and_range": str(profile_payload.get("voice_timbre_and_range", "")).strip(),
        "voice_pacing_and_rhythm": str(profile_payload.get("voice_pacing_and_rhythm", "")).strip(),
        "voice_emotional_baseline": str(profile_payload.get("voice_emotional_baseline", "")).strip(),
        "voice_articulation_and_pronunciation": str(
            profile_payload.get("voice_articulation_and_pronunciation", "")
        ).strip(),
        "voice_delivery_constraints": str(profile_payload.get("voice_delivery_constraints", "")).strip(),
        CHARACTER_VOICE_PROMPT_FIELD: str(profile_payload.get(CHARACTER_VOICE_PROMPT_FIELD, "")).strip(),
        CHARACTER_VOICE_SIGNATURE_FIELD: str(profile_payload.get(CHARACTER_VOICE_SIGNATURE_FIELD, "")).strip(),
        "relationship_hints": _normalize_string_list(profile_payload.get("relationship_hints", [])),
        "confidence": str(profile_payload.get("confidence", "")).strip(),
        "review_status": _normalize_review_status(profile_payload.get("review_status", "")),
        "evidence": _restore_evidence(profile_payload.get("evidence", [])),
        "updated_at": None
        if profile_payload.get("updated_at") in (None, "")
        else str(profile_payload.get("updated_at")),
    }
    return normalized_profile


def _profile_with_synchronized_voice_definition(profile_payload: dict[str, object]) -> CharacterProfilePayload:
    """
    @brief      Execute the profile with synchronized voice definition helper.
    @param[in]  profile_payload Profile payload.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_profile = _normalize_character_profile(profile_payload)
    current_signature = voice_definition_source_signature(normalized_profile)
    normalized_profile[CHARACTER_VOICE_SIGNATURE_FIELD] = current_signature
    normalized_profile["voice_definition_stale"] = False
    return normalized_profile


def _persistable_character_profile(profile_payload: dict[str, object]) -> CharacterProfilePayload:
    """
    @brief      Execute the persistable character profile helper.
    @param[in]  profile_payload Profile payload.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_profile = _normalize_character_profile(profile_payload)
    normalized_profile.pop("voice_definition_stale", None)
    return normalized_profile


def _voice_definition_block_changed(
    left_profile: dict[str, object],
    right_profile: dict[str, object],
) -> bool:
    """
    @brief      Execute the voice definition block changed helper.
    @param[in]  left_profile Value for `left_profile`.
    @param[in]  right_profile Value for `right_profile`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    comparable_fields = (*CHARACTER_VOICE_BRIEF_FIELDS, CHARACTER_VOICE_PROMPT_FIELD)
    return any(
        str(left_profile.get(field_name, "")).strip() != str(right_profile.get(field_name, "")).strip()
        for field_name in comparable_fields
    )


def _character_voice_gender_instruction(profile_payload: dict[str, object]) -> str:
    """
    @brief      Build explicit sex/gender guidance for one character voice prompt.
    @param[in]  profile_payload Character profile payload.
    @return     Sex/gender instruction text without the field label.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    gender_hint = str(profile_payload.get("gender_hint", "")).strip()
    if gender_hint:
        return (
            f"{gender_hint}. Match this explicitly in the vocal identity and do not replace it with a different "
            "default."
        )
    return (
        "not specified in the source. Use a neutral or androgynous vocal identity and do not default to a male voice."
    )


def _ensure_character_voice_prompt_gender_instruction(prompt_text: str, profile_payload: dict[str, object]) -> str:
    """
    @brief      Add explicit sex/gender guidance to one character voice-definition prompt.
    @param[in]  prompt_text Candidate voice-definition prompt.
    @param[in]  profile_payload Character profile payload.
    @return     Prompt text containing explicit sex/gender guidance.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    normalized_prompt = str(prompt_text).strip()
    if _prompt_has_explicit_gender_instruction(normalized_prompt):
        return normalized_prompt
    return f"{normalized_prompt} Sex/Gender: {_character_voice_gender_instruction(profile_payload)}".strip()


def _prompt_has_explicit_gender_instruction(prompt_text: str) -> bool:
    """
    @brief      Return whether a prompt already carries explicit sex/gender guidance.
    @param[in]  prompt_text Candidate voice-definition prompt.
    @return     True when explicit sex or gender guidance is already present.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    normalized_prompt = str(prompt_text).casefold()
    return bool(
        re.search(r"\b(sex/gender|gender hint|gender)\s*:", normalized_prompt)
        or re.search(r"\b(female|male|woman|man|girl|boy|androgynous)\b", normalized_prompt)
    )


def _derived_voice_definition_fields(profile_payload: dict[str, object]) -> dict[str, str]:
    """
    @brief      Execute the derived voice definition fields helper.
    @param[in]  profile_payload Profile payload.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    character_name = str(profile_payload.get("canonical_name", "Character")).strip() or "Character"
    role_summary = str(profile_payload.get("role_summary", "")).strip()
    description = str(profile_payload.get("description", "")).strip()
    temperament = str(profile_payload.get("temperament", "")).strip()
    social_status = str(profile_payload.get("social_status", "")).strip()
    speaking_style = str(profile_payload.get("speaking_style", "")).strip()
    accent_hints = str(profile_payload.get("accent_or_dialect_hints", "")).strip()
    voice_notes = str(profile_payload.get("voice_notes", "")).strip()
    gender_hint = str(profile_payload.get("gender_hint", "")).strip()
    age_band = str(profile_payload.get("age_band", "")).strip()

    persona_components = [
        _phrase_join([age_band, gender_hint], suffix="voice persona") if age_band or gender_hint else "",
        role_summary,
        description,
        temperament,
        social_status,
    ]
    persona_summary = _compose_sentence(
        [item for item in persona_components if item],
        fallback=f"{character_name} should sound grounded, characterful, and easy to distinguish in repeated dialogue.",
    )
    timbre_and_range = _compose_sentence(
        [
            voice_notes,
            _phrase_join([age_band, gender_hint], suffix="timbre") if age_band or gender_hint else "",
        ],
        fallback=(
            "Use a natural, human voice with a stable timbre and comfortable range that stays believable over "
            "many lines."
        ),
    )
    pacing_and_rhythm = _compose_sentence(
        [
            speaking_style,
            "Keep pacing controlled and rhythm easy to follow in dialogue.",
        ],
        fallback="Keep the pacing natural and dialogue-friendly, with phrasing that remains clear and steady.",
    )
    emotional_baseline = _compose_sentence(
        [
            temperament,
            description,
            "Let the emotional baseline stay consistent unless the text clearly demands a stronger shift.",
        ],
        fallback=(
            "Maintain a coherent emotional baseline that matches the character and changes naturally with the text."
        ),
    )
    articulation_and_pronunciation = _compose_sentence(
        [
            accent_hints,
            speaking_style,
            "Keep diction clear and pronunciation consistent.",
        ],
        fallback="Keep diction clear, articulation clean, and pronunciation consistent from line to line.",
    )
    delivery_constraints = _compose_sentence(
        [
            "Avoid celebrity imitation and exaggerated caricature.",
            "Preserve a stable character identity across repeated dialogue.",
            "Stay expressive but natural rather than theatrical unless the text clearly calls for it.",
        ],
        fallback="Keep the delivery consistent, natural, and repeatable across many lines.",
    )
    return {
        "voice_persona_summary": persona_summary,
        "voice_timbre_and_range": timbre_and_range,
        "voice_pacing_and_rhythm": pacing_and_rhythm,
        "voice_emotional_baseline": emotional_baseline,
        "voice_articulation_and_pronunciation": articulation_and_pronunciation,
        "voice_delivery_constraints": delivery_constraints,
    }


def _compose_sentence(parts: list[str], fallback: str) -> str:
    """
    @brief      Compose the sentence.
    @param[in]  parts Value for `parts`.
    @param[in]  fallback Value for `fallback`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    cleaned_parts = [_sentence_fragment(part) for part in parts if _sentence_fragment(part)]
    if not cleaned_parts:
        return fallback
    sentence = " ".join(cleaned_parts).strip()
    return sentence if sentence.endswith(".") else f"{sentence}."


def _sentence_fragment(value: object) -> str:
    """
    @brief      Execute the sentence fragment helper.
    @param[in]  value Candidate value.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_value = re.sub(r"\s+", " ", str(value or "").strip())
    if not normalized_value:
        return ""
    normalized_value = normalized_value.rstrip(".")
    return normalized_value if normalized_value.endswith(".") else f"{normalized_value}."


def _phrase_join(parts: list[str], suffix: str) -> str:
    """
    @brief      Execute the phrase join helper.
    @param[in]  parts Value for `parts`.
    @param[in]  suffix Value for `suffix`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_parts = [str(part).strip() for part in parts if str(part).strip()]
    if not normalized_parts:
        return ""
    return f"{', '.join(normalized_parts)} {suffix}".strip()


def _normalize_identity(value: str) -> str:
    """
    @brief      Normalize the identity.
    @param[in]  value Candidate value.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _slugify_character_id(name: str, fallback_index: int) -> str:
    """
    @brief      Execute the slugify character id helper.
    @param[in]  name Value for `name`.
    @param[in]  fallback_index Value for `fallback_index`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    return slug or f"character_{fallback_index:04d}"


def _candidate_sort_key(candidate: dict[str, object]) -> tuple[int, str]:
    """
    @brief      Execute the candidate sort key helper.
    @param[in]  candidate Value for `candidate`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    evidence = _restore_evidence(candidate.get("evidence", []))
    if not evidence:
        return 999999, str(candidate.get("canonical_name", "")).casefold()
    return (
        min(int(item.get("sequence_index", 0)) for item in evidence),
        str(candidate.get("canonical_name", "")).casefold(),
    )


def _profile_sort_key(profile: CharacterProfilePayload) -> tuple[int, str]:
    """
    @brief      Execute the profile sort key helper.
    @param[in]  profile Value for `profile`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    evidence = _restore_evidence(profile.get("evidence", []))
    if not evidence:
        return 999999, str(profile.get("canonical_name", "")).casefold()
    return (
        min(int(item.get("sequence_index", 0)) for item in evidence),
        str(profile.get("canonical_name", "")).casefold(),
    )


def _candidate_has_spoken_dialogue(candidate: dict[str, object]) -> bool:
    """
    @brief      Execute the candidate has spoken dialogue helper.
    @param[in]  candidate Value for `candidate`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    if bool(candidate.get("has_dialogue_evidence")):
        return True
    evidence_items = _restore_evidence(candidate.get("evidence", []))
    if not evidence_items:
        return False
    return any(_evidence_has_direct_dialogue(evidence) for evidence in evidence_items)


def _evidence_has_direct_dialogue(evidence: dict[str, object]) -> bool:
    """
    @brief      Decide whether one evidence item directly supports spoken dialogue.
    @param[in]  evidence Evidence payload.
    @return     True when the evidence is anchored to dialogue without depending on natural-language keywords.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    if str(evidence.get("dialogue_span_id", "")).strip():
        return True
    if str(evidence.get("confidence", "")).strip().casefold() == EVIDENCE_CONFIDENCE_HIGH:
        return True
    if _text_contains_dialogue_markers(str(evidence.get("source_excerpt", ""))):
        return True
    return _reason_mentions_dialogue(str(evidence.get("reason", "")))


def _text_contains_dialogue_markers(text: str) -> bool:
    """
    @brief      Execute the text contains dialogue markers helper.
    @param[in]  text Value for `text`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    normalized = text.strip()
    if not normalized:
        return False
    if any(marker in normalized for marker in ('"', "\u201c", "\u201d", "\u00ab", "\u00bb", "\u300c", "\u300d")):
        return True
    return normalized.startswith(("- ", "--", "\u2014", "\u2013"))


def _reason_mentions_dialogue(reason: str) -> bool:
    """
    @brief      Execute the reason mentions dialogue helper.
    @param[in]  reason Value for `reason`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    lowered = reason.casefold()
    return any(
        token in lowered
        for token in (
            "dialogue",
            "direct speech",
            "speaks",
            "speaking",
            "quote",
            "quoted speech",
            "says",
            "said",
            "asks",
            "asked",
            "answers",
            "answered",
            "replies",
            "replied",
            "whispers",
            "whispered",
            "shouts",
            "shouted",
        )
    )


def _excerpt_text(text: str, limit: int = 180) -> str:
    """
    @brief      Execute the excerpt text helper.
    @param[in]  text Value for `text`.
    @param[in]  limit Value for `limit`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


# END OF FILE
