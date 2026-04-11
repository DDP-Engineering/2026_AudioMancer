#!/usr/bin/env python3
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
@version 0.3.0
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
    @version    0.2.0
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
    return [dict(item) for item in payload if isinstance(item, dict)]


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
    @version    0.1.0
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
    @version    0.1.0
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
            merged_profile = dict(profile_payload)
            merged_profile["canonical_name"] = normalized_name
            merged_profile["updated_at"] = _utc_now_iso()
            updated_profiles.append(merged_profile)
            found_profile = True
        else:
            updated_profiles.append(dict(existing_profile))
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
    @version    0.1.0
    """
    output_path = build_operation_output_path(
        project_root,
        "character_discovery",
        config.CHARACTER_PROFILE_FILE_NAME,
    )
    output_path.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False) + "\n",
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
    @version    0.1.0
    """
    return {
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
    source_document = manifest.get("source_document", {})
    if isinstance(source_document, dict):
        original_name = str(source_document.get("original_name", "")).strip()
        if original_name:
            return Path(original_name).stem
    return Path(config.CHUNK_ARTIFACT_FILE_NAME).stem


def _build_input_fingerprint(source_chunks: list[dict[str, object]]) -> str:
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
    metadata = existing_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return token_usage_service.empty_token_usage()
    return token_usage_service.restore_token_usage(metadata.get("token_usage"))


def _restore_mapping_list(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def _resolve_log_path(
    project_root: Path,
    started_at: str,
    log_relative_path: str | None,
) -> Path:
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
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def _dedupe_evidence(
    evidence_items: list[dict[str, object]],
) -> list[dict[str, object]]:
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
    return {
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


def _normalize_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _slugify_character_id(name: str, fallback_index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    return slug or f"character_{fallback_index:04d}"


def _candidate_sort_key(candidate: dict[str, object]) -> tuple[int, str]:
    evidence = _restore_evidence(candidate.get("evidence", []))
    if not evidence:
        return 999999, str(candidate.get("canonical_name", "")).casefold()
    return (
        min(int(item.get("sequence_index", 0)) for item in evidence),
        str(candidate.get("canonical_name", "")).casefold(),
    )


def _profile_sort_key(profile: CharacterProfilePayload) -> tuple[int, str]:
    evidence = _restore_evidence(profile.get("evidence", []))
    if not evidence:
        return 999999, str(profile.get("canonical_name", "")).casefold()
    return (
        min(int(item.get("sequence_index", 0)) for item in evidence),
        str(profile.get("canonical_name", "")).casefold(),
    )


def _candidate_has_spoken_dialogue(candidate: dict[str, object]) -> bool:
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
    normalized = text.strip()
    if not normalized:
        return False
    if '"' in normalized:
        return True
    return normalized.startswith("- ") or normalized.startswith("--")


def _reason_mentions_dialogue(reason: str) -> bool:
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
    if callable(progress_callback):
        progress_callback(
            progress_current,
            progress_total,
            progress_percent(progress_current, progress_total),
            message,
            token_usage,
        )


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
