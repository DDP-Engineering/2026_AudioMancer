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
@date 2026-04-11
@version 0.5.0
"""

# IMPORTS

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    deterministic_chunking_service,
    llm_provider_service,
    prompt_template_service,
    text_cleanup_state_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    build_operation_artifact_path,
    build_operation_input_snapshot_path,
    build_operation_output_path,
    progress_percent,
    raise_if_cancelled,
    relative_to_project,
    reset_operation_data,
)

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

# @brief Persisted character-profile payload type.
CharacterProfilePayload = dict[str, object]
# @brief Persisted character-discovery report payload type.
CharacterDiscoveryReportPayload = dict[str, object]
# @brief Persisted character-discovery operation-state payload type.
OperationStatePayload = dict[str, object]
TokenUsagePayload = dict[str, object]

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
    @date       2026-04-11
    @version    0.2.0
    """
    state_path = build_operation_output_path(
        project_root,
        "character_discovery",
        config.OPERATION_STATE_FILE_NAME,
    )
    if not state_path.is_file():
        return None
    return dict(json.loads(state_path.read_text(encoding="utf-8")))


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def load_character_profiles(project_root: str | Path) -> list[CharacterProfilePayload]:
    """
    @brief      Load the optional persisted character profile artifact.
    @param[in]  project_root Active project root folder.
    @return     Ordered character profile payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.3.0
    """
    output_path = build_operation_output_path(
        project_root,
        "character_discovery",
        config.CHARACTER_PROFILE_FILE_NAME,
    )
    if not output_path.is_file():
        return []
    payload = json.loads(output_path.read_text(encoding="utf-8"))
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
    @version    1.1.0
    """
    normalized_profile = _normalized_character_profile_core(character_profile)
    derived_voice_fields = _derived_voice_definition_fields(normalized_profile)
    for field_name in CHARACTER_VOICE_BRIEF_FIELDS:
        normalized_profile[field_name] = (
            str(normalized_profile.get(field_name, "")).strip() or derived_voice_fields[field_name]
        )
    character_name = str(normalized_profile.get("canonical_name", "Character")).strip() or "Character"
    descriptor_parts = [
        _sentence_fragment(normalized_profile.get("voice_persona_summary")),
        _sentence_fragment(normalized_profile.get("voice_timbre_and_range")),
        _sentence_fragment(normalized_profile.get("voice_pacing_and_rhythm")),
        _sentence_fragment(normalized_profile.get("voice_emotional_baseline")),
        _sentence_fragment(normalized_profile.get("voice_articulation_and_pronunciation")),
        _sentence_fragment(normalized_profile.get("voice_delivery_constraints")),
    ]
    cleaned_descriptors = [part for part in descriptor_parts if part]
    if cleaned_descriptors:
        return (f"Create a consistent spoken voice for {character_name}. " + " ".join(cleaned_descriptors)).strip()
    return (
        f"Create a consistent spoken voice for {character_name} with clear diction, stable identity, "
        "natural emotional control, and delivery suitable for repeated dialogue narration."
    )


def regenerate_character_voice_definition(profile_payload: dict[str, object]) -> CharacterProfilePayload:
    """
    @brief      Rebuild the structured voice-definition brief and final prompt from the current character facts.
    @param[in]  profile_payload Character profile payload.
    @return     Updated character profile payload with regenerated voice-definition fields.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
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
    @version    1.0.0
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
    @date       2026-04-08
    @version    0.1.0
    """
    report_path = build_operation_artifact_path(
        project_root,
        "character_discovery",
        config.CHARACTER_DISCOVERY_REPORT_FILE_NAME,
    )
    if not report_path.is_file():
        return None
    return dict(json.loads(report_path.read_text(encoding="utf-8")))


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def load_input_chunks(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load the optional chunk-input snapshot for character discovery.
    @param[in]  project_root Active project root folder.
    @return     Ordered chunk payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    input_path = _resolve_chunk_input_snapshot_path(Path(project_root))
    if input_path is None or not input_path.is_file():
        return []
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def start_or_continue_discovery(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> CharacterDiscoveryReportPayload:
    """
    @brief      Run AI-assisted character discovery for the active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Final character-discovery report payload.
    @exception  ValueError Raised on missing chunking input or invalid profile data.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    source_chunks = sorted(
        deterministic_chunking_service.load_chunks(resolved_project_root),
        key=lambda item: int(item.get("sequence_index", 0)),
    )
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
    chunk_input_path, clean_text_input_path = _persist_input_snapshots(
        resolved_project_root,
        source_chunks,
        manifest,
    )
    output_path = build_operation_output_path(
        resolved_project_root,
        "character_discovery",
        config.CHARACTER_PROFILE_FILE_NAME,
    )
    report_path = build_operation_artifact_path(
        resolved_project_root,
        "character_discovery",
        config.CHARACTER_DISCOVERY_REPORT_FILE_NAME,
    )
    state_path = build_operation_output_path(
        resolved_project_root,
        "character_discovery",
        config.OPERATION_STATE_FILE_NAME,
    )

    input_fingerprint = _build_input_fingerprint(source_chunks)
    windows = _build_chunk_windows(
        source_chunks,
        config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
        config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
    )
    if not windows:
        raise ValueError("Character discovery requires at least one chunk window.")

    existing_state = load_operation_state(resolved_project_root) or {}
    started_at = str(existing_state.get("started_at") or _utc_now_iso())
    (
        start_window_index,
        raw_candidates,
        merged_candidates,
        synthesized_profiles,
        log_relative_path,
    ) = _restore_resume_state(
        existing_state,
        input_fingerprint,
        profile_id,
        len(windows),
    )
    token_usage = _restore_token_usage(existing_state)
    log_path = _resolve_log_path(resolved_project_root, started_at, log_relative_path)
    chunk_map = {
        str(chunk.get("chunk_id", "")): dict(chunk) for chunk in source_chunks if str(chunk.get("chunk_id", "")).strip()
    }
    initial_progress_current = len(windows) + len(synthesized_profiles) if merged_candidates else start_window_index
    initial_progress_total = len(windows) + len(merged_candidates) if merged_candidates else len(windows)
    _write_operation_state(
        state_path=state_path,
        project_root=resolved_project_root,
        input_paths=[chunk_input_path, clean_text_input_path],
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
        warnings=[],
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        resume_checkpoint={
            "input_fingerprint": input_fingerprint,
            "profile_id": profile_id,
            "completed_window_count": start_window_index,
            "total_window_count": len(windows),
            "raw_candidates": list(raw_candidates),
            "merged_candidates": list(merged_candidates),
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

    system_prompt = prompt_template_service.render_prompt(
        "character_discovery_system",
        {},
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
            input_paths=[chunk_input_path, clean_text_input_path],
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
            warnings=[],
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            resume_checkpoint={
                "input_fingerprint": input_fingerprint,
                "profile_id": profile_id,
                "completed_window_count": window_index + 1,
                "total_window_count": len(windows),
                "raw_candidates": list(raw_candidates),
                "merged_candidates": [],
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
        merged_candidates = _merge_character_candidates(raw_candidates)
    total_progress = max(len(windows) + len(merged_candidates), 1)
    _write_operation_state(
        state_path=state_path,
        project_root=resolved_project_root,
        input_paths=[chunk_input_path, clean_text_input_path],
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
        warnings=[],
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
        resume_checkpoint={
            "input_fingerprint": input_fingerprint,
            "profile_id": profile_id,
            "completed_window_count": len(windows),
            "total_window_count": len(windows),
            "raw_candidates": list(raw_candidates),
            "merged_candidates": list(merged_candidates),
            "synthesized_profiles": list(synthesized_profiles),
            "synthesis_progress_count": len(synthesized_profiles),
            "log_relative_path": relative_to_project(resolved_project_root, log_path),
        },
    )
    for profile_index in range(len(synthesized_profiles), len(merged_candidates)):
        raise_if_cancelled(cancel_requested)
        candidate = dict(merged_candidates[profile_index])
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
            input_paths=[chunk_input_path, clean_text_input_path],
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
            warnings=[],
            input_fingerprint=input_fingerprint,
            log_path=log_path,
            token_usage=token_usage,
            resume_checkpoint={
                "input_fingerprint": input_fingerprint,
                "profile_id": profile_id,
                "completed_window_count": len(windows),
                "total_window_count": len(windows),
                "raw_candidates": list(raw_candidates),
                "merged_candidates": list(merged_candidates),
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
        "analyzed_window_count": len(windows),
        "merged_candidate_count": len(merged_candidates),
        "character_count": len(ordered_profiles),
        "character_discovery_mode": CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
        "character_profile_id_last_used": profile_id,
        "window_size": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
        "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
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
        input_paths=[chunk_input_path, clean_text_input_path],
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
        warnings=[],
        input_fingerprint=input_fingerprint,
        log_path=log_path,
        token_usage=token_usage,
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
    @version    1.0.0
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
    @version    0.1.0
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
    @brief      Clear character-discovery artifacts plus downstream narrator data.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    reset_operation_data(
        project_root,
        "character_discovery",
        include_current=True,
        keep_input_snapshots=False,
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
        config.OPERATION_STATE_FILE_NAME,
    )
    state_path.write_text(
        json.dumps(state_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _persist_input_snapshots(
    project_root: Path,
    source_chunks: list[dict[str, object]],
    manifest: dict[str, object],
) -> tuple[Path, Path]:
    """
    @brief      Persist the input snapshots.
    @param[in]  project_root Active project root folder.
    @param[in]  source_chunks Value for `source_chunks`.
    @param[in]  manifest Active project manifest payload.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    source_base_name = _source_snapshot_base_name(manifest)
    chunk_input_path = build_operation_input_snapshot_path(
        project_root,
        "character_discovery",
        f"{source_base_name}.json",
    )
    clean_text_input_path = build_operation_input_snapshot_path(
        project_root,
        "character_discovery",
        f"{source_base_name}.txt",
    )
    chunk_input_path.write_text(
        json.dumps(source_chunks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    cleaned_text = text_cleanup_state_service.read_optional_project_text(
        project_root,
        f"{config.CLEANUP_FOLDER_NAME}/{config.CLEANED_TEXT_FILE_NAME}",
    )
    if cleaned_text is None:
        cleaned_text = "\n\n".join(
            str(chunk.get("text", "")).strip() for chunk in source_chunks if str(chunk.get("text", "")).strip()
        )
    clean_text_input_path.write_text(
        cleaned_text.strip() + "\n",
        encoding="utf-8",
    )
    return chunk_input_path, clean_text_input_path


def _resolve_chunk_input_snapshot_path(project_root: Path) -> Path | None:
    """
    @brief      Resolve the chunk input snapshot path.
    @param[in]  project_root Active project root folder.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    operation_state = load_operation_state(project_root)
    if isinstance(operation_state, dict):
        input_paths = operation_state.get("input_paths", [])
        if isinstance(input_paths, list):
            for relative_path in input_paths:
                if not isinstance(relative_path, str):
                    continue
                candidate_path = project_root / relative_path
                if (
                    candidate_path.is_file()
                    and candidate_path.suffix.casefold() == ".json"
                    and candidate_path.name.startswith(config.OPERATION_INPUT_FILE_PREFIX)
                ):
                    return candidate_path
    discovery_root = project_root / config.CHARACTER_DISCOVERY_FOLDER_NAME
    candidates = sorted(discovery_root.glob(f"{config.OPERATION_INPUT_FILE_PREFIX}*.json"))
    return candidates[0] if candidates else None


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
    @version    0.1.0
    """
    digest = hashlib.sha256()
    for chunk in source_chunks:
        digest.update(str(chunk.get("chunk_id", "")).encode("utf-8"))
        digest.update(b"\n")
        digest.update(str(chunk.get("sequence_index", 0)).encode("utf-8"))
        digest.update(b"\n")
        digest.update(str(chunk.get("text", "")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _build_chunk_windows(
    source_chunks: list[dict[str, object]],
    window_size: int,
    overlap: int,
) -> list[list[dict[str, object]]]:
    """
    @brief      Build the chunk windows.
    @param[in]  source_chunks Value for `source_chunks`.
    @param[in]  window_size Value for `window_size`.
    @param[in]  overlap Value for `overlap`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if not source_chunks:
        return []
    step = max(1, window_size - overlap)
    windows: list[list[dict[str, object]]] = []
    for start_index in range(0, len(source_chunks), step):
        window = source_chunks[start_index : start_index + window_size]
        if not window:
            continue
        windows.append(window)
        if start_index + window_size >= len(source_chunks):
            break
    return windows


def _build_units_block(window_records: list[dict[str, object]]) -> str:
    """
    @brief      Build the units block.
    @param[in]  window_records Value for `window_records`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    blocks: list[str] = []
    for chunk in window_records:
        blocks.append(
            f"CHUNK_ID: {chunk.get('chunk_id', '')}\n"
            f"SEQUENCE_INDEX: {chunk.get('sequence_index', 0)}\n"
            f"CHAPTER_LABEL: {chunk.get('chapter_label', '') or ''}\n"
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
) -> tuple[
    int,
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
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if str(existing_state.get("status", "")) not in {"running", "failed"}:
        return 0, [], [], [], None
    if str(existing_state.get("mode", "")) != CHARACTER_DISCOVERY_MODE_AI_ASSISTED:
        return 0, [], [], [], None
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    if str(resume_checkpoint.get("input_fingerprint", "")) != input_fingerprint:
        return 0, [], [], [], None
    if str(resume_checkpoint.get("profile_id", "")) != profile_id:
        return 0, [], [], [], None
    if int(resume_checkpoint.get("total_window_count", 0)) != total_windows:
        return 0, [], [], [], None
    return (
        min(int(resume_checkpoint.get("completed_window_count", 0)), total_windows),
        _restore_mapping_list(resume_checkpoint.get("raw_candidates")),
        _restore_mapping_list(resume_checkpoint.get("merged_candidates")),
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
        f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}{timestamp_token}.log",
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
    warnings: list[str],
    input_fingerprint: str,
    log_path: Path,
    token_usage: TokenUsagePayload,
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
    @param[in]  warnings Value for `warnings`.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  log_path Operation log file path.
    @param[in]  token_usage Value for `token_usage`.
    @param[in]  resume_checkpoint Value for `resume_checkpoint`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    artifact_paths = [relative_to_project(project_root, log_path)]
    if report_path is not None and report_path.is_file():
        artifact_paths.insert(0, relative_to_project(project_root, report_path))
    state_payload: OperationStatePayload = {
        "folder_relative_path": config.CHARACTER_DISCOVERY_FOLDER_NAME,
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
            "window_size": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
            "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
            "warnings": list(warnings),
            "input_fingerprint": input_fingerprint,
            "log_relative_path": relative_to_project(project_root, log_path),
            "token_usage": token_usage_service.coerce_token_usage(token_usage),
        },
        "resume_checkpoint": (None if resume_checkpoint is None else dict(resume_checkpoint)),
    }
    state_path.write_text(
        json.dumps(state_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


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
    @version    0.1.0
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
                    _text_contains_dialogue_markers(str(chunk_map[item["chunk_id"]].get("text", "")))
                    or _text_contains_dialogue_markers(str(item.get("source_excerpt", "")))
                    or _reason_mentions_dialogue(str(item.get("reason", "")))
                    for item in evidence
                    if item.get("chunk_id") in chunk_map
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
    @version    0.1.0
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
        evidence_items.append(
            {
                "chunk_id": chunk_id,
                "sequence_index": int(source_chunk.get("sequence_index", 0)),
                "source_excerpt": (
                    str(entry.get("source_excerpt", "")).strip() or _excerpt_text(str(source_chunk.get("text", "")))
                ),
                "reason": (str(entry.get("reason", "")).strip() or "Mentioned in source chunk."),
            }
        )
    return _dedupe_evidence(evidence_items)


def _merge_character_candidates(
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Merge the character candidates.
    @param[in]  candidates Value for `candidates`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    merged: list[dict[str, object]] = []
    for candidate in candidates:
        alias_keys = {_normalize_identity(str(candidate.get("canonical_name", "")))}
        alias_keys.update(_normalize_identity(alias) for alias in list(candidate.get("aliases", [])))
        alias_keys.discard("")
        target = next(
            (item for item in merged if alias_keys.intersection(set(item.get("_alias_keys", [])))),
            None,
        )
        if target is None:
            target = dict(candidate)
            target["_alias_keys"] = sorted(alias_keys)
            merged.append(target)
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
        target["_alias_keys"] = sorted(set(target.get("_alias_keys", [])) | alias_keys)
    filtered: list[dict[str, object]] = []
    for index, entry in enumerate(sorted(merged, key=_candidate_sort_key), start=1):
        entry["character_id"] = _slugify_character_id(
            str(entry.get("canonical_name", "")),
            index,
        )
        entry["evidence"] = _restore_evidence(entry.get("evidence", []))
        entry.pop("_alias_keys", None)
        if _candidate_has_spoken_dialogue(entry):
            filtered.append(entry)
    return filtered


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
    normalized_profile[CHARACTER_VOICE_PROMPT_FIELD] = str(
        normalized_profile.get(CHARACTER_VOICE_PROMPT_FIELD, "")
    ).strip() or build_character_voice_definition_prompt(normalized_profile)
    current_signature = voice_definition_source_signature(normalized_profile)
    stored_signature = str(normalized_profile.get(CHARACTER_VOICE_SIGNATURE_FIELD, "")).strip()
    normalized_profile["voice_definition_stale"] = bool(stored_signature and stored_signature != current_signature)
    return normalized_profile


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
        fallback="Use a natural, human voice with a stable timbre and comfortable range that stays believable over many lines.",
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
        fallback="Maintain a coherent emotional baseline that matches the character and changes naturally with the text.",
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
    @version    0.1.0
    """
    if bool(candidate.get("has_dialogue_evidence")):
        return True
    evidence_items = _restore_evidence(candidate.get("evidence", []))
    if not evidence_items:
        return False
    for evidence in evidence_items:
        if _text_contains_dialogue_markers(str(evidence.get("source_excerpt", ""))):
            return True
        if _reason_mentions_dialogue(str(evidence.get("reason", ""))):
            return True
    return False


def _text_contains_dialogue_markers(text: str) -> bool:
    """
    @brief      Execute the text contains dialogue markers helper.
    @param[in]  text Value for `text`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized = text.strip()
    if not normalized:
        return False
    if '"' in normalized:
        return True
    return normalized.startswith("- ") or normalized.startswith("--")


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


def _emit_progress(
    progress_callback,
    progress_current: int,
    progress_total: int,
    message: str,
    token_usage: TokenUsagePayload | None = None,
) -> None:
    """
    @brief      Emit the progress.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_current Value for `progress_current`.
    @param[in]  progress_total Value for `progress_total`.
    @param[in]  message Operator-facing message text.
    @param[in]  token_usage Value for `token_usage`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if callable(progress_callback):
        progress_callback(
            progress_current,
            progress_total,
            progress_percent(progress_current, progress_total),
            message,
            token_usage,
        )


def _utc_now_iso() -> str:
    """
    @brief      Execute the utc now iso helper.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
