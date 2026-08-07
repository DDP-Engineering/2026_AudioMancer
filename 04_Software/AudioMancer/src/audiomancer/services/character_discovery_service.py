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
         overlapping chunk windows, persists compact voice-ready profiles in the
         `40_character_discovery` workflow artifacts, and maintains resumable AI
         operation state.
"""

# IMPORTS

import hashlib
import json
from pathlib import Path
import re
import unicodedata

from audiomancer import config
from audiomancer.services import (
    ai_budget_service,
    ai_translation_service,
    chunking_document_service,
    deterministic_chunking_service,
    llm_provider_service,
    project_workspace_service,
    prompt_template_service,
    token_usage_service,
    tts_budget_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    OperationCancelledError,
    build_operation_output_path,
    raise_if_cancelled,
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
# @brief Discovery input uses canonical original chunks.
CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL = "original"
# @brief Discovery input uses fully approved translated chunks.
CHARACTER_DISCOVERY_INPUT_SOURCE_TRANSLATED = "translated"
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
# @brief Supported confidence tokens for inferred demographic fields.
DEMOGRAPHIC_CONFIDENCE_VALUES = {
    EVIDENCE_CONFIDENCE_HIGH,
    EVIDENCE_CONFIDENCE_MEDIUM,
    EVIDENCE_CONFIDENCE_LOW,
}
# @brief Stable reasons for candidates excluded from speaking-character synthesis.
REJECTED_CANDIDATE_REASONS = frozenset(("missing_evidence", "missing_spoken_dialogue_evidence"))

# @brief Persisted character-profile payload type.
CharacterProfilePayload = dict[str, object]
# @brief Authoritative Character Discovery document payload type.
CharacterDocumentPayload = dict[str, object]
TokenUsagePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]

CHARACTER_VOICE_PROMPT_FIELD = "voice_definition_prompt"
CHARACTER_PREVIEW_TEXT_FIELD = "preview_text"
_CHARACTER_DOCUMENT_FIELDS = frozenset(
    (
        "status",
        "source",
        "instructions",
        "token_usage",
        "character_profile_id_last_used",
        "rejected_candidates",
        "checkpoint",
        "failure",
        "characters",
    )
)
_CHARACTER_SOURCE_FIELDS = frozenset(("kind", "language", "fingerprint"))
_CHARACTER_DOCUMENT_STATUSES = frozenset(("running", "cancelled", "failed", "completed"))
_TOKEN_USAGE_FIELDS = frozenset(
    ("input_tokens", "output_tokens", "total_tokens", "usage_available")
)


class CharacterDocumentError(ValueError):
    """Raised when the authoritative Character Discovery document is invalid."""


# PUBLIC API


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def load_character_document(project_root: str | Path) -> CharacterDocumentPayload | None:
    """Load and strictly validate the authoritative Character Discovery document."""
    document_path = resolve_operation_path(
        project_root,
        "character_discovery",
        config.CHARACTERS_DOCUMENT_FILE_NAME,
    )
    if not document_path.is_file():
        return None
    try:
        payload = json.loads(document_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CharacterDocumentError("Character Discovery data is not valid JSON.") from error
    _validate_character_document(payload)
    return dict(payload)


def write_character_document(
    project_root: str | Path,
    document: CharacterDocumentPayload,
) -> Path:
    """Strictly validate and atomically persist the Character Discovery document."""
    _validate_character_document(document)
    document_path = build_operation_output_path(
        project_root,
        "character_discovery",
        config.CHARACTERS_DOCUMENT_FILE_NAME,
    )
    write_json_atomic(document_path, document)
    return document_path


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def load_character_profiles(project_root: str | Path) -> list[CharacterProfilePayload]:
    """Project the authoritative document's nested character records for consumers."""
    document = load_character_document(project_root)
    if document is None:
        return []
    return [
        _normalize_character_profile(_flat_character_profile(item))
        for item in document["characters"]
        if isinstance(item, dict)
    ]


def character_operation_summary(
    document: CharacterDocumentPayload,
    source_chunk_count: int = 0,
) -> dict[str, object]:
    """Derive the shared manifest operation summary from one character document."""
    checkpoint = document.get("checkpoint")
    if isinstance(checkpoint, dict) and checkpoint.get("phase") == "discovery":
        progress_current = int(checkpoint.get("completed_window_count", 0))
        progress_total = int(checkpoint.get("planned_window_count", 0))
    elif isinstance(checkpoint, dict) and checkpoint.get("phase") == "synthesis":
        progress_current = int(checkpoint.get("completed_window_count", 0)) + int(
            checkpoint.get("next_candidate_index", 0)
        )
        progress_total = int(checkpoint.get("planned_window_count", 0)) + len(checkpoint.get("candidates", []))
    else:
        progress_current = 0
        progress_total = 0
    return {
        "status": str(document.get("status", "not_started")),
        "progress_current": progress_current,
        "progress_total": progress_total,
        "mode": CHARACTER_DISCOVERY_MODE_AI_ASSISTED,
        "warning_count": len(_restore_rejected_candidate_diagnostics(document.get("rejected_candidates"))),
    }


def build_character_voice_definition_prompt(character_profile: dict[str, object]) -> str:
    """
    @brief      Build one Qwen-oriented voice-definition prompt from the compact character profile.
    @param[in]  character_profile Character profile payload with identity, sex/gender, age, and voice prompt fields.
    @return     Stable English voice-definition prompt paragraph.
    @exception  None
    """
    normalized_profile = _normalized_character_profile_core(character_profile)
    stored_voice_prompt = str(normalized_profile.get(CHARACTER_VOICE_PROMPT_FIELD, "")).strip()
    if stored_voice_prompt:
        return _ensure_character_voice_prompt_instructions(stored_voice_prompt, normalized_profile)
    character_name = str(normalized_profile.get("canonical_name", "Character")).strip() or "Character"
    return (
        f"Create a consistent spoken voice for {character_name} with clear diction, stable identity, "
        "natural emotional control, and delivery suitable for repeated dialogue narration. "
        f"Sex/Gender: {_character_voice_gender_instruction(normalized_profile)} "
        f"Age Domain: {_character_voice_age_instruction(normalized_profile)}"
    )


def regenerate_character_voice_definition(profile_payload: dict[str, object]) -> CharacterProfilePayload:
    """
    @brief      Normalize the compact profile and ensure the final voice prompt contains voice guidance.
    @param[in]  profile_payload Character profile payload.
    @return     Updated compact character profile payload.
    @exception  None
    """
    normalized_profile = _normalize_character_profile(profile_payload)
    updated_profile = dict(normalized_profile)
    updated_profile[CHARACTER_VOICE_PROMPT_FIELD] = build_character_voice_definition_prompt(updated_profile)
    return updated_profile


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def load_input_chunks(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load the optional chunk-input snapshot for character discovery.
    @param[in]  project_root Active project root folder.
    @return     Ordered chunk payload list.
    @exception  None
    """
    input_chunks, _source = _resolve_discovery_input_chunks(Path(project_root))
    return input_chunks


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def start_or_continue_discovery(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
    force_rerun: bool = False,
    additional_character_discovery_instructions: str | None = None,
) -> CharacterDocumentPayload:
    """
    @brief      Run AI-assisted character discovery for the active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  force_rerun Ignore compatible resumable state and start a fresh internal run.
    @param[in]  additional_character_discovery_instructions Optional operator-supplied discovery rules.
    @return     Final character-discovery report payload.
    @exception  ValueError Raised on missing chunking input or invalid profile data.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    resolved_project_root = Path(project_root)
    source_chunks, source_metadata = _resolve_discovery_input_chunks(resolved_project_root)
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
    existing_document = {} if force_rerun else (load_character_document(resolved_project_root) or {})
    if existing_document and dict(existing_document.get("source", {})) != source_metadata:
        reset_character_discovery(resolved_project_root)
        existing_document = {}
    additional_character_discovery_instructions = _resolve_additional_character_discovery_instructions(
        additional_character_discovery_instructions,
        existing_document,
    )
    budget_metadata = _build_budget_metadata(
        ai_profile_payload,
        system_prompt,
        additional_character_discovery_instructions,
    )
    document_path = build_operation_output_path(
        resolved_project_root,
        "character_discovery",
        config.CHARACTERS_DOCUMENT_FILE_NAME,
    )

    input_fingerprint = str(source_metadata["fingerprint"])
    resume_checkpoint = existing_document.get("checkpoint") if isinstance(existing_document, dict) else {}
    if not isinstance(resume_checkpoint, dict):
        resume_checkpoint = {}
    run_token = _utc_now_iso()
    (
        completed_window_count,
        planned_window_count,
        next_discovery_start_chunk_index,
        raw_candidates,
        merged_candidates,
        rejected_candidates,
        _restored_synthesized_profiles,
        next_candidate_index,
        resume_phase,
    ) = _restore_resume_state(
        existing_document,
        input_fingerprint,
        source_chunks,
    )
    resume_is_compatible = resume_phase is not None
    character_inventory = (
        _restore_mapping_list(existing_document.get("characters"))
        if resume_is_compatible
        else []
    )
    windows = (
        []
        if merged_candidates
        else _build_chunk_windows(
            source_chunks[next_discovery_start_chunk_index:],
            config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE,
            config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
            budget_metadata,
        )
    )
    if not merged_candidates and not windows and not raw_candidates:
        raise ValueError("Character discovery requires at least one chunk window.")
    if not merged_candidates:
        planned_window_count = completed_window_count + len(windows)
    discovery_progress_total = planned_window_count
    token_usage = (
        _restore_token_usage(existing_document)
        if resume_is_compatible
        else token_usage_service.empty_token_usage()
    )
    log_path = _resolve_log_path(resolved_project_root, run_token)
    chunk_map = {
        str(chunk.get("chunk_id", "")): dict(chunk) for chunk in source_chunks if str(chunk.get("chunk_id", "")).strip()
    }
    initial_progress_current = (
        discovery_progress_total + next_candidate_index if merged_candidates else completed_window_count
    )
    initial_progress_total = (
        discovery_progress_total + len(merged_candidates) if merged_candidates else discovery_progress_total
    )
    _write_operation_state(
        state_path=document_path,
        status="running",
        phase="synthesis" if merged_candidates else "discovery",
        progress_current=initial_progress_current,
        progress_total=initial_progress_total,
        run_token=run_token,
        profile_id=profile_id,
        input_fingerprint=input_fingerprint,
        token_usage=token_usage,
        additional_character_discovery_instructions=additional_character_discovery_instructions,
        checkpoint={
            "completed_window_count": completed_window_count,
            "planned_window_count": planned_window_count,
            "next_discovery_start_chunk_index": next_discovery_start_chunk_index,
            "raw_candidates": list(raw_candidates),
            "merged_candidates": list(merged_candidates),
            "rejected_candidates": list(rejected_candidates),
            "next_candidate_index": next_candidate_index,
        },
        source=source_metadata,
        character_inventory=character_inventory,
        rejected_candidates=rejected_candidates,
    )
    _emit_progress(
        progress_callback,
        initial_progress_current,
        initial_progress_total,
        (
            "Character profile synthesis in progress..."
            if merged_candidates
            else (
                "Resuming character discovery..."
                if completed_window_count > 0
                else "Character discovery in progress..."
            )
        ),
        token_usage=token_usage,
    )

    discovery_progress_current = completed_window_count
    discovery_checkpoint = {
        "completed_window_count": completed_window_count,
        "planned_window_count": planned_window_count,
        "next_discovery_start_chunk_index": next_discovery_start_chunk_index,
        "raw_candidates": list(raw_candidates),
        "merged_candidates": [],
        "rejected_candidates": [],
        "next_candidate_index": 0,
    }
    try:
        for relative_window_index, window_records in enumerate(windows):
            raise_if_cancelled(cancel_requested)
            progress_window_index = completed_window_count + relative_window_index
            user_prompt = _append_additional_character_discovery_instructions(
                prompt_template_service.render_prompt(
                    "character_discovery_window_user",
                    {"units_block": _build_units_block(window_records)},
                ),
                additional_character_discovery_instructions,
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
                        "window_index": progress_window_index + 1,
                        "window_total": discovery_progress_total,
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
            next_discovery_start_chunk_index = _next_chunk_index_after_window(source_chunks, window_records)
            discovery_progress_current = progress_window_index + 1
            discovery_checkpoint = {
                "completed_window_count": discovery_progress_current,
                "planned_window_count": discovery_progress_total,
                "next_discovery_start_chunk_index": next_discovery_start_chunk_index,
                "raw_candidates": list(raw_candidates),
                "merged_candidates": [],
                "rejected_candidates": [],
                "next_candidate_index": 0,
            }
            _write_operation_state(
                state_path=document_path,
                status="running",
                phase="discovery",
                progress_current=discovery_progress_current,
                progress_total=discovery_progress_total,
                run_token=run_token,
                profile_id=profile_id,
                input_fingerprint=input_fingerprint,
                token_usage=token_usage,
                additional_character_discovery_instructions=additional_character_discovery_instructions,
                checkpoint=discovery_checkpoint,
                character_inventory=character_inventory,
                rejected_candidates=rejected_candidates,
            )
            _emit_progress(
                progress_callback,
                discovery_progress_current,
                discovery_progress_total,
                "Character discovery in progress...",
                token_usage=token_usage,
            )
    except OperationCancelledError:
        _write_operation_state(
            state_path=document_path,
            status="cancelled",
            phase="discovery",
            progress_current=discovery_progress_current,
            progress_total=discovery_progress_total,
            run_token=run_token,
            profile_id=profile_id,
            input_fingerprint=input_fingerprint,
            token_usage=token_usage,
            additional_character_discovery_instructions=additional_character_discovery_instructions,
            checkpoint=discovery_checkpoint,
            character_inventory=character_inventory,
            rejected_candidates=rejected_candidates,
        )
        raise
    except Exception:
        _write_operation_state(
            state_path=document_path,
            status="failed",
            phase="discovery",
            progress_current=discovery_progress_current,
            progress_total=discovery_progress_total,
            run_token=run_token,
            profile_id=profile_id,
            input_fingerprint=input_fingerprint,
            token_usage=token_usage,
            additional_character_discovery_instructions=additional_character_discovery_instructions,
            checkpoint=discovery_checkpoint,
            character_inventory=character_inventory,
            rejected_candidates=rejected_candidates,
        )
        raise

    if not merged_candidates:
        merged_candidates, rejected_candidates = _merge_character_candidates_with_rejections(raw_candidates)
    total_progress = max(discovery_progress_total + len(merged_candidates), 1)
    _write_operation_state(
        state_path=document_path,
        status="running",
        phase="synthesis",
        progress_current=discovery_progress_total + next_candidate_index,
        progress_total=total_progress,
        run_token=run_token,
        profile_id=profile_id,
        input_fingerprint=input_fingerprint,
        token_usage=token_usage,
        additional_character_discovery_instructions=additional_character_discovery_instructions,
        checkpoint={
            "completed_window_count": discovery_progress_total,
            "planned_window_count": discovery_progress_total,
            "next_discovery_start_chunk_index": len(source_chunks),
            "raw_candidates": list(raw_candidates),
            "merged_candidates": list(merged_candidates),
            "rejected_candidates": list(rejected_candidates),
            "next_candidate_index": next_candidate_index,
        },
        character_inventory=character_inventory,
        rejected_candidates=rejected_candidates,
    )
    synthesis_progress_current = discovery_progress_total + next_candidate_index
    synthesis_checkpoint = {
        "completed_window_count": discovery_progress_total,
        "planned_window_count": discovery_progress_total,
        "next_discovery_start_chunk_index": len(source_chunks),
        "raw_candidates": list(raw_candidates),
        "merged_candidates": list(merged_candidates),
        "rejected_candidates": list(rejected_candidates),
        "next_candidate_index": next_candidate_index,
    }
    try:
        for profile_index in range(next_candidate_index, len(merged_candidates)):
            raise_if_cancelled(cancel_requested)
            candidate = _budgeted_synthesis_candidate_payload(
                dict(merged_candidates[profile_index]),
                budget_metadata,
            )
            user_prompt = _append_additional_character_discovery_instructions(
                prompt_template_service.render_prompt(
                    "character_profile_synthesis_user",
                    {
                        "character_payload": json.dumps(
                            candidate,
                            indent=2,
                            ensure_ascii=False,
                        )
                    },
                ),
                additional_character_discovery_instructions,
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
            synthesized_profile = _build_profile_from_synthesis(response_payload, candidate)
            character_inventory = _merge_synthesized_profile_into_inventory(
                character_inventory,
                synthesized_profile,
            )
            next_candidate_index = profile_index + 1
            synthesis_progress_current = discovery_progress_total + next_candidate_index
            synthesis_checkpoint = {
                "completed_window_count": discovery_progress_total,
                "planned_window_count": discovery_progress_total,
                "next_discovery_start_chunk_index": len(source_chunks),
                "raw_candidates": list(raw_candidates),
                "merged_candidates": list(merged_candidates),
                "rejected_candidates": list(rejected_candidates),
                "next_candidate_index": next_candidate_index,
            }
            _write_operation_state(
                state_path=document_path,
                status="running",
                phase="synthesis",
                progress_current=synthesis_progress_current,
                progress_total=total_progress,
                run_token=run_token,
                profile_id=profile_id,
                input_fingerprint=input_fingerprint,
                token_usage=token_usage,
                additional_character_discovery_instructions=additional_character_discovery_instructions,
                checkpoint=synthesis_checkpoint,
                character_inventory=character_inventory,
                rejected_candidates=rejected_candidates,
            )
            _emit_progress(
                progress_callback,
                synthesis_progress_current,
                total_progress,
                "Character profile synthesis in progress...",
                token_usage=token_usage,
            )
    except OperationCancelledError:
        _write_operation_state(
            state_path=document_path,
            status="cancelled",
            phase="synthesis",
            progress_current=synthesis_progress_current,
            progress_total=total_progress,
            run_token=run_token,
            profile_id=profile_id,
            input_fingerprint=input_fingerprint,
            token_usage=token_usage,
            additional_character_discovery_instructions=additional_character_discovery_instructions,
            checkpoint=synthesis_checkpoint,
            character_inventory=character_inventory,
            rejected_candidates=rejected_candidates,
        )
        raise
    except Exception:
        _write_operation_state(
            state_path=document_path,
            status="failed",
            phase="synthesis",
            progress_current=synthesis_progress_current,
            progress_total=total_progress,
            run_token=run_token,
            profile_id=profile_id,
            input_fingerprint=input_fingerprint,
            token_usage=token_usage,
            additional_character_discovery_instructions=additional_character_discovery_instructions,
            checkpoint=synthesis_checkpoint,
            character_inventory=character_inventory,
            rejected_candidates=rejected_candidates,
        )
        raise

    ordered_inventory = sorted(character_inventory, key=_nested_profile_sort_key)
    _write_operation_state(
        state_path=document_path,
        status="completed",
        phase="completed",
        progress_current=total_progress,
        progress_total=total_progress,
        run_token=run_token,
        profile_id=profile_id,
        input_fingerprint=input_fingerprint,
        token_usage=token_usage,
        additional_character_discovery_instructions=additional_character_discovery_instructions,
        checkpoint=None,
        character_inventory=ordered_inventory,
        rejected_candidates=rejected_candidates,
    )
    completed_document = load_character_document(resolved_project_root)
    assert completed_document is not None
    project_workspace_service.sync_manifest_operation_summary(
        resolved_project_root,
        "character_discovery",
        character_operation_summary(completed_document, len(source_chunks)),
        current_stage="character_discovery_ready",
    )
    _emit_progress(
        progress_callback,
        total_progress,
        total_progress,
        "Character discovery completed.",
        token_usage=token_usage,
    )
    return completed_document


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
            merged_profile["_provenance_edited"] = True
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
    """
    reset_operation_data(
        project_root,
        "character_discovery",
        include_current=True,
        preserve_operation_kinds=NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    )


def invalidate_if_source_changed(project_root: str | Path) -> bool:
    """Reset Character Discovery and downstream artifacts when its effective source changed."""
    document = load_character_document(project_root)
    if document is None:
        return False
    _chunks, current_source = _resolve_discovery_input_chunks(Path(project_root))
    if dict(document.get("source", {})) == current_source:
        return False
    reset_character_discovery(project_root)
    return True


def _validate_character_document(payload: object) -> None:
    """Validate the strict, hard-break Character Discovery document contract."""
    if not isinstance(payload, dict) or set(payload) != _CHARACTER_DOCUMENT_FIELDS:
        raise CharacterDocumentError("Character Discovery data has an incompatible root contract.")
    if str(payload.get("status", "")) not in _CHARACTER_DOCUMENT_STATUSES:
        raise CharacterDocumentError("Character Discovery data has an invalid status.")
    source = payload.get("source")
    if not isinstance(source, dict) or set(source) != _CHARACTER_SOURCE_FIELDS:
        raise CharacterDocumentError("Character Discovery data has an invalid source contract.")
    if str(source.get("kind", "")) not in {
        CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL,
        CHARACTER_DISCOVERY_INPUT_SOURCE_TRANSLATED,
    }:
        raise CharacterDocumentError("Character Discovery data has an invalid source kind.")
    if not all(isinstance(source.get(field), str) for field in _CHARACTER_SOURCE_FIELDS):
        raise CharacterDocumentError("Character Discovery source fields must be strings.")
    if not isinstance(payload.get("instructions"), str):
        raise CharacterDocumentError("Character Discovery instructions must be a string.")
    if not isinstance(payload.get("character_profile_id_last_used"), str):
        raise CharacterDocumentError("Character Discovery last-used profile id must be a string.")
    _validate_rejected_candidate_diagnostics(payload.get("rejected_candidates"))
    token_usage = payload.get("token_usage")
    if not isinstance(token_usage, dict) or set(token_usage) != _TOKEN_USAGE_FIELDS:
        raise CharacterDocumentError("Character Discovery token_usage has an invalid contract.")
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        if type(token_usage.get(field)) is not int or int(token_usage[field]) < 0:
            raise CharacterDocumentError("Character Discovery token counts must be non-negative integers.")
    if type(token_usage.get("usage_available")) is not bool:
        raise CharacterDocumentError("Character Discovery usage_available must be boolean.")
    characters = payload.get("characters")
    if not isinstance(characters, list):
        raise CharacterDocumentError("Character Discovery characters must be an array.")
    for character in characters:
        _validate_nested_character(character)
    checkpoint = payload.get("checkpoint")
    if checkpoint is not None:
        _validate_character_checkpoint(checkpoint)
    failure = payload.get("failure")
    if failure is not None and (
        not isinstance(failure, dict)
        or set(failure) != {"phase", "message"}
        or not all(isinstance(failure.get(field), str) for field in ("phase", "message"))
    ):
        raise CharacterDocumentError("Character Discovery failure must be null or a phase/message object.")


def _validate_nested_character(payload: object) -> None:
    """Validate one nested character record."""
    expected_fields = {
        "character_id",
        "canonical_name",
        "aliases",
        "traits",
        "voice",
        "discovery_confidence",
        "provenance",
        "evidence",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise CharacterDocumentError("Character Discovery contains an invalid character record.")
    traits = payload.get("traits")
    voice = payload.get("voice")
    provenance = payload.get("provenance")
    if not isinstance(traits, dict) or set(traits) != {"gender", "age"}:
        raise CharacterDocumentError("Character traits must contain gender and age.")
    for trait_name in ("gender", "age"):
        trait = traits.get(trait_name)
        if not isinstance(trait, dict) or set(trait) != {"value", "confidence"}:
            raise CharacterDocumentError(f"Character {trait_name} must contain value and confidence.")
    if not isinstance(voice, dict) or set(voice) != {"definition_prompt", "preview_text"}:
        raise CharacterDocumentError("Character voice must contain definition_prompt and preview_text.")
    if (
        not isinstance(provenance, dict)
        or set(provenance) != {"origin", "edited"}
        or str(provenance.get("origin", "")) not in {"ai", "manual"}
        or type(provenance.get("edited")) is not bool
    ):
        raise CharacterDocumentError("Character provenance is invalid.")
    if not isinstance(payload.get("aliases"), list) or not isinstance(payload.get("evidence"), list):
        raise CharacterDocumentError("Character aliases and evidence must be arrays.")
    string_fields = ("character_id", "canonical_name", "discovery_confidence")
    if not all(isinstance(payload.get(field), str) for field in string_fields):
        raise CharacterDocumentError("Character identity and confidence fields must be strings.")
    if not all(isinstance(item, str) for item in payload["aliases"]):
        raise CharacterDocumentError("Character aliases must contain only strings.")
    for trait_name in ("gender", "age"):
        trait = traits[trait_name]
        if not all(isinstance(trait.get(field), str) for field in ("value", "confidence")):
            raise CharacterDocumentError("Character trait values must be strings.")
    if not all(isinstance(voice.get(field), str) for field in ("definition_prompt", "preview_text")):
        raise CharacterDocumentError("Character voice values must be strings.")
    if not all(isinstance(item, dict) for item in payload["evidence"]):
        raise CharacterDocumentError("Character evidence must contain only objects.")


def _validate_character_checkpoint(payload: object) -> None:
    """Validate one phase-specific resume checkpoint."""
    if not isinstance(payload, dict):
        raise CharacterDocumentError("Character Discovery checkpoint must be an object.")
    phase = str(payload.get("phase", ""))
    expected_fields = (
        {"phase", "completed_window_count", "planned_window_count", "next_chunk_index", "candidates"}
        if phase == "discovery"
        else {"phase", "completed_window_count", "planned_window_count", "next_candidate_index", "candidates"}
    )
    if phase not in {"discovery", "synthesis"} or set(payload) != expected_fields:
        raise CharacterDocumentError("Character Discovery checkpoint has an invalid phase contract.")
    index_field = "next_chunk_index" if phase == "discovery" else "next_candidate_index"
    if type(payload.get(index_field)) is not int or int(payload[index_field]) < 0:
        raise CharacterDocumentError("Character Discovery checkpoint index must be non-negative.")
    for field in ("completed_window_count", "planned_window_count"):
        if type(payload.get(field)) is not int or int(payload[field]) < 0:
            raise CharacterDocumentError("Character Discovery window counts must be non-negative integers.")
    if int(payload["completed_window_count"]) > int(payload["planned_window_count"]):
        raise CharacterDocumentError("Character Discovery completed windows cannot exceed planned windows.")
    if phase == "synthesis" and int(payload["completed_window_count"]) != int(payload["planned_window_count"]):
        raise CharacterDocumentError("Character Discovery synthesis requires all discovery windows to be complete.")
    if not isinstance(payload.get("candidates"), list):
        raise CharacterDocumentError("Character Discovery checkpoint candidates must be an array.")


def _validate_rejected_candidate_diagnostics(payload: object) -> None:
    """Validate the compact, deterministic rejected-candidate diagnostic array."""
    if not isinstance(payload, list):
        raise CharacterDocumentError("Character Discovery rejected candidates must be an array.")
    previous_sort_key: tuple[str, str] | None = None
    seen_diagnostic_keys: set[tuple[str, str]] = set()
    for diagnostic in payload:
        expected_fields = {"canonical_name", "reason", "evidence_count", "identity_merge_count"}
        if not isinstance(diagnostic, dict) or set(diagnostic) != expected_fields:
            raise CharacterDocumentError("Character Discovery rejected candidate has an invalid contract.")
        canonical_name = diagnostic.get("canonical_name")
        reason = diagnostic.get("reason")
        evidence_count = diagnostic.get("evidence_count")
        identity_merge_count = diagnostic.get("identity_merge_count")
        if not isinstance(canonical_name, str) or not canonical_name.strip() or not _normalize_identity(canonical_name):
            raise CharacterDocumentError("Character Discovery rejected candidate name is invalid.")
        if reason not in REJECTED_CANDIDATE_REASONS:
            raise CharacterDocumentError("Character Discovery rejected candidate reason is invalid.")
        if type(evidence_count) is not int or evidence_count < 0:
            raise CharacterDocumentError("Character Discovery rejected candidate evidence count is invalid.")
        if type(identity_merge_count) is not int or identity_merge_count < 1:
            raise CharacterDocumentError("Character Discovery rejected candidate merge count is invalid.")
        diagnostic_key = (_normalize_identity(canonical_name), reason)
        sort_key = (canonical_name.casefold(), reason)
        if diagnostic_key in seen_diagnostic_keys or (previous_sort_key is not None and sort_key < previous_sort_key):
            raise CharacterDocumentError("Character Discovery rejected candidates must be unique and ordered.")
        seen_diagnostic_keys.add(diagnostic_key)
        previous_sort_key = sort_key


def _flat_character_profile(payload: dict[str, object]) -> CharacterProfilePayload:
    """Project one nested persisted character into the existing consumer shape."""
    traits = payload.get("traits", {})
    traits = traits if isinstance(traits, dict) else {}
    gender = traits.get("gender", {})
    gender = gender if isinstance(gender, dict) else {}
    age = traits.get("age", {})
    age = age if isinstance(age, dict) else {}
    voice = payload.get("voice", {})
    voice = voice if isinstance(voice, dict) else {}
    provenance = payload.get("provenance", {})
    provenance = provenance if isinstance(provenance, dict) else {}
    origin = str(provenance.get("origin", "ai"))
    edited = bool(provenance.get("edited", False))
    review_status = (
        CHARACTER_REVIEW_STATUS_MANUAL
        if origin == "manual"
        else (CHARACTER_REVIEW_STATUS_EDITED if edited else CHARACTER_REVIEW_STATUS_DISCOVERED)
    )
    return {
        "character_id": str(payload.get("character_id", "")),
        "canonical_name": str(payload.get("canonical_name", "")),
        "aliases": list(payload.get("aliases", [])),
        "gender_hint": str(gender.get("value", "")),
        "gender_confidence": str(gender.get("confidence", "")),
        "age_hint": str(age.get("value", "")),
        "age_confidence": str(age.get("confidence", "")),
        CHARACTER_VOICE_PROMPT_FIELD: str(voice.get("definition_prompt", "")),
        CHARACTER_PREVIEW_TEXT_FIELD: str(voice.get("preview_text", "")),
        "confidence": str(payload.get("discovery_confidence", "")),
        "review_status": review_status,
        "evidence": list(payload.get("evidence", [])),
        "_provenance_origin": origin,
        "_provenance_edited": edited,
    }


def _nested_character_profile(
    profile_payload: dict[str, object],
    existing_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """Convert one consumer profile into the authoritative nested shape."""
    normalized = _normalize_character_profile(profile_payload)
    existing_provenance = (
        existing_payload.get("provenance", {})
        if isinstance(existing_payload, dict)
        else {}
    )
    existing_provenance = existing_provenance if isinstance(existing_provenance, dict) else {}
    review_status = _normalize_review_status(normalized.get("review_status", ""))
    origin = str(
        profile_payload.get(
            "_provenance_origin",
            existing_provenance.get(
                "origin",
                "manual" if review_status == CHARACTER_REVIEW_STATUS_MANUAL else "ai",
            ),
        )
    )
    edited = bool(
        profile_payload.get(
            "_provenance_edited",
            existing_provenance.get("edited", review_status == CHARACTER_REVIEW_STATUS_EDITED),
        )
    )
    return {
        "character_id": str(normalized.get("character_id", "")),
        "canonical_name": str(normalized.get("canonical_name", "")),
        "aliases": list(normalized.get("aliases", [])),
        "traits": {
            "gender": {
                "value": str(normalized.get("gender_hint", "")),
                "confidence": str(normalized.get("gender_confidence", "")),
            },
            "age": {
                "value": str(normalized.get("age_hint", "")),
                "confidence": str(normalized.get("age_confidence", "")),
            },
        },
        "voice": {
            "definition_prompt": str(normalized.get(CHARACTER_VOICE_PROMPT_FIELD, "")),
            "preview_text": str(normalized.get(CHARACTER_PREVIEW_TEXT_FIELD, "")),
        },
        "discovery_confidence": str(normalized.get("confidence", "")),
        "provenance": {"origin": origin, "edited": edited},
        "evidence": list(normalized.get("evidence", [])),
    }


def _new_character_document(
    source: dict[str, str],
    instructions: str,
    *,
    status: str = "running",
) -> CharacterDocumentPayload:
    """Build a new authoritative Character Discovery document."""
    return {
        "status": status,
        "source": dict(source),
        "instructions": str(instructions),
        "token_usage": _persisted_character_token_usage(
            token_usage_service.empty_token_usage()
        ),
        "character_profile_id_last_used": "",
        "rejected_candidates": [],
        "checkpoint": {
            "phase": "discovery",
            "completed_window_count": 0,
            "planned_window_count": 0,
            "next_chunk_index": 0,
            "candidates": [],
        },
        "failure": None,
        "characters": [],
    }


@trace_function(_CHARACTER_DISCOVERY_LOGGER)
def drop_character_evidence_for_chunks(
    project_root: str | Path,
    chunk_ids: list[str] | tuple[str, ...] | set[str],
) -> int:
    """
    @brief      Remove chunk-scoped Character Discovery evidence for selected chunks.
    @details    Character profiles are preserved. Manual evidence entries remain
                untouched because they are not anchored to generated chunks.
    @param[in]  project_root Active project root folder.
    @param[in]  chunk_ids Source chunk identifiers whose evidence is stale.
    @return     Number of evidence records removed.
    @exception  None
    """
    normalized_chunk_ids = {str(chunk_id).strip() for chunk_id in chunk_ids if str(chunk_id).strip()}
    if not normalized_chunk_ids:
        return 0
    resolved_project_root = Path(project_root)
    profiles = load_character_profiles(resolved_project_root)
    if not profiles:
        return 0
    removed_count = 0
    updated_profiles: list[CharacterProfilePayload] = []
    for profile in profiles:
        evidence_items = _restore_evidence(profile.get("evidence", []))
        preserved_evidence = [
            evidence
            for evidence in evidence_items
            if str(evidence.get("chunk_id", "")).strip() not in normalized_chunk_ids
            or str(evidence.get("chunk_id", "")).strip() == MANUAL_CHARACTER_EVIDENCE_CHUNK_ID
        ]
        removed_count += len(evidence_items) - len(preserved_evidence)
        updated_profile = dict(profile)
        updated_profile["evidence"] = preserved_evidence
        updated_profile["has_dialogue_evidence"] = any(
            _evidence_has_direct_dialogue(item)
            for item in preserved_evidence
            if str(item.get("chunk_id", "")).strip() != MANUAL_CHARACTER_EVIDENCE_CHUNK_ID
        )
        updated_profiles.append(updated_profile)
    if removed_count:
        _write_character_profiles(resolved_project_root, updated_profiles)
    return removed_count


# LOCAL HELPERS


def _write_character_profiles(
    project_root: Path,
    profiles: list[CharacterProfilePayload],
) -> None:
    """
    @brief      Persist the current character profile list.
    @param[in]  project_root Active project root folder.
    @param[in]  profiles Ordered character profile payload list.
    @return     None.
    @exception  None
    """
    document = load_character_document(project_root)
    if document is None:
        _chunks, source = _resolve_discovery_input_chunks(project_root)
        document = _new_character_document(source, "", status="completed")
        document["checkpoint"] = None
    existing_by_id = {
        str(item.get("character_id", "")): item
        for item in document.get("characters", [])
        if isinstance(item, dict)
    }
    document["characters"] = [
        _nested_character_profile(
            profile,
            existing_by_id.get(str(profile.get("character_id", ""))),
        )
        for profile in profiles
    ]
    write_character_document(project_root, document)


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
    """
    return regenerate_character_voice_definition(
        {
            "character_id": _next_manual_character_id(existing_profiles, canonical_name),
            "canonical_name": canonical_name,
            "aliases": [],
            "gender_hint": "",
            "gender_confidence": "",
            "age_hint": "",
            "age_confidence": "",
            "voice_definition_prompt": "",
            "preview_text": "",
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
    """
    base_slug = _slugify_character_id(canonical_name, len(existing_profiles) + 1)
    existing_ids = {str(profile.get("character_id", "")).strip() for profile in existing_profiles}
    if base_slug not in existing_ids:
        return base_slug
    suffix = 2
    while f"{base_slug}_{suffix}" in existing_ids:
        suffix += 1
    return f"{base_slug}_{suffix}"


def _resolve_discovery_input_chunks(project_root: Path) -> tuple[list[dict[str, object]], dict[str, str]]:
    """
    @brief      Resolve the authoritative internal input for character discovery.
    @param[in]  project_root Active project root folder.
    @return     Ordered discovery chunks plus the input-source token.
    @exception  None
    """
    original_chunks = sorted(
        chunking_document_service.load_chunks(project_root),
        key=lambda item: int(item.get("sequence_index", 0)),
    )
    manifest = project_workspace_service.load_manifest(project_root)
    source_kind = CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL
    source_language = str(manifest.get("original_language", "")).strip()
    source_chunks = original_chunks
    try:
        translation_document = ai_translation_service.load_translation_document(project_root)
    except (OSError, ValueError):
        translation_document = None
    if translation_document is not None:
        translated_by_id = {
            str(item.get("chunk_id", "")).strip(): item
            for item in translation_document.get("chunks", [])
            if isinstance(item, dict) and str(item.get("chunk_id", "")).strip()
        }
        translated_chunks: list[dict[str, object]] = []
        translation_is_complete = bool(original_chunks)
        for original_chunk in original_chunks:
            chunk_id = str(original_chunk.get("chunk_id", "")).strip()
            translated_chunk = translated_by_id.get(chunk_id)
            translated_text = (
                ""
                if translated_chunk is None
                else str(translated_chunk.get("translated_text", ""))
            )
            if (
                translated_chunk is None
                or not bool(translated_chunk.get("approved", False))
                or not translated_text.strip()
            ):
                translation_is_complete = False
                break
            translated_chunks.append(
                {
                    **dict(original_chunk),
                    "text": translated_text,
                }
            )
        if translation_is_complete and len(translated_chunks) == len(original_chunks):
            source_kind = CHARACTER_DISCOVERY_INPUT_SOURCE_TRANSLATED
            source_language = str(translation_document.get("target_language", "")).strip()
            source_chunks = translated_chunks
    discovery_chunks: list[dict[str, object]] = []
    current_chapter_label: str | None = None
    for source_chunk in source_chunks:
        detected_chapter_label = deterministic_chunking_service._chapter_label_from_text(
            str(source_chunk.get("text", ""))
        )
        if detected_chapter_label is not None:
            current_chapter_label = detected_chapter_label
        discovery_chunks.append(
            _discovery_chunk_from_source(
                source_chunk,
                current_chapter_label,
                source_kind,
            )
        )
    fingerprint = _build_input_fingerprint(
        discovery_chunks,
        source_kind=source_kind,
        source_language=source_language,
    )
    return discovery_chunks, {
        "kind": source_kind,
        "language": source_language,
        "fingerprint": fingerprint,
    }


def _discovery_chunk_from_source(
    source_chunk: dict[str, object],
    chapter_label: str | None,
    input_source: str,
) -> dict[str, object]:
    """
    @brief      Build one discovery chunk from canonical source chunking output.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  chapter_label Runtime chapter context carried from ordered chunk text.
    @return     Discovery chunk payload.
    @exception  None
    """
    discovery_chunk = dict(source_chunk)
    text = str(discovery_chunk.get("text", "")).strip()
    discovery_chunk["chapter_label"] = chapter_label
    discovery_chunk["source_text"] = text
    discovery_chunk["input_source"] = input_source
    discovery_chunk["dialogue_spans"] = _detect_dialogue_spans(text)
    return discovery_chunk


def _build_input_fingerprint(
    source_chunks: list[dict[str, object]],
    *,
    source_kind: str = CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL,
    source_language: str = "",
) -> str:
    """
    @brief      Build the input fingerprint.
    @param[in]  source_chunks Value for `source_chunks`.
    @return     Derived helper result.
    """
    digest = hashlib.sha256()
    digest.update(str(source_kind).encode("utf-8"))
    digest.update(b"\n")
    digest.update(str(source_language).encode("utf-8"))
    digest.update(b"\n")
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
    """
    if not source_chunks:
        return []
    max_window_chunks = len(source_chunks) if int(window_size) <= 0 else max(1, int(window_size))
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
    additional_character_discovery_instructions: str = "",
) -> BudgetMetadataPayload:
    """
    @brief      Build context-window budget metadata for AI character discovery.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  system_prompt Rendered character-discovery system prompt.
    @param[in]  additional_character_discovery_instructions Optional operator-supplied discovery rules.
    @return     Context-budget metadata used for windowing and synthesis guards.
    @exception  ValueError Raised when context and output settings leave too little input room.
    """
    discovery_prompt_shell = _append_additional_character_discovery_instructions(
        prompt_template_service.render_prompt(
            "character_discovery_window_user",
            {"units_block": ""},
        ),
        additional_character_discovery_instructions,
    )
    synthesis_prompt_shell = _append_additional_character_discovery_instructions(
        prompt_template_service.render_prompt(
            "character_profile_synthesis_user",
            {"character_payload": ""},
        ),
        additional_character_discovery_instructions,
    )
    discovery_budget_metadata = ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{discovery_prompt_shell}",
        config.DEFAULT_CHARACTER_DISCOVERY_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_CHARACTER_DISCOVERY_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_CHARACTER_DISCOVERY_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_CHARACTER_DISCOVERY_MIN_TEXT_BUDGET_TOKENS,
        "AI-assisted character discovery cannot run because the selected AI profile context window "
        "and max output tokens leave too little room for discovery input",
        online_text_context_fraction=config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION,
    )
    context_window = int(discovery_budget_metadata["context_window"])
    max_output_tokens = int(discovery_budget_metadata["max_output_tokens"])
    safety_margin_tokens = int(discovery_budget_metadata["safety_margin_tokens"])
    synthesis_prompt_budget_tokens = _estimate_text_tokens(f"{system_prompt}\n\n{synthesis_prompt_shell}")
    if ai_budget_service.uses_online_text_budget(ai_profile_payload):
        synthesis_payload_budget_tokens = int(context_window * config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION)
    else:
        synthesis_payload_budget_tokens = ai_budget_service.available_text_budget(
            context_window,
            max_output_tokens,
            synthesis_prompt_budget_tokens,
            safety_margin_tokens,
            config.DEFAULT_CHARACTER_DISCOVERY_TEXT_CONTEXT_FRACTION,
        )
    min_text_budget = config.DEFAULT_CHARACTER_DISCOVERY_MIN_TEXT_BUDGET_TOKENS
    if synthesis_payload_budget_tokens < min_text_budget:
        raise ValueError(
            "AI-assisted character discovery cannot run because the selected AI profile context window "
            "and max output tokens leave too little room for character synthesis input "
            f"({synthesis_payload_budget_tokens} estimated tokens available, {min_text_budget} required)."
        )
    return {
        **discovery_budget_metadata,
        "max_window_chunks": (
            0
            if ai_budget_service.uses_online_text_budget(ai_profile_payload)
            else config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE
        ),
        "window_overlap": config.DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP,
        "synthesis_prompt_budget_tokens": synthesis_prompt_budget_tokens,
        "synthesis_payload_budget_tokens": synthesis_payload_budget_tokens,
        "synthesis_max_evidence_items": config.DEFAULT_CHARACTER_DISCOVERY_SYNTHESIS_MAX_EVIDENCE_ITEMS,
    }


def _resolve_additional_character_discovery_instructions(
    additional_character_discovery_instructions: str | None,
    existing_state: dict[str, object],
) -> str:
    """
    @brief      Resolve operator rules for a new or resumed Character Discovery run.
    @param[in]  additional_character_discovery_instructions New operator instructions or None when resuming.
    @param[in]  existing_state Existing Character Discovery operation state.
    @return     Normalized operator Character Discovery instructions.
    @exception  None
    """
    is_resumable_status = str(existing_state.get("status", "")) in {
        "running",
        "failed",
        "cancelled",
    }
    if is_resumable_status:
        return _normalized_additional_character_discovery_instructions(
            existing_state.get("instructions")
        )
    return _normalized_additional_character_discovery_instructions(
        additional_character_discovery_instructions
    )


def _normalized_additional_character_discovery_instructions(value: object) -> str:
    """
    @brief      Normalize optional operator Character Discovery rules.
    @param[in]  value Candidate instruction text.
    @return     Trimmed instruction text.
    @exception  None
    """
    if value is None:
        return ""
    return str(value).strip()


def _append_additional_character_discovery_instructions(prompt_text: str, instructions: str) -> str:
    """
    @brief      Append optional operator Character Discovery rules to one rendered prompt.
    @param[in]  prompt_text Rendered prompt template text.
    @param[in]  instructions Normalized operator rules.
    @return     Prompt text with the optional rule section appended.
    @exception  None
    """
    normalized_instructions = _normalized_additional_character_discovery_instructions(instructions)
    if not normalized_instructions:
        return prompt_text
    return (
        f"{prompt_text.rstrip()}\n\nAdditional operator Character Discovery instructions:\n{normalized_instructions}\n"
    )


def _estimate_text_tokens(text: str) -> int:
    """
    @brief      Estimate token usage for local budget checks.
    @param[in]  text Value for `text`.
    @return     Estimated token count.
    @exception  None
    """
    return ai_budget_service.estimate_text_tokens(text)


def _build_units_block(window_records: list[dict[str, object]]) -> str:
    """
    @brief      Build the units block.
    @param[in]  window_records Value for `window_records`.
    @return     Derived helper result.
    """
    blocks: list[str] = []
    for chunk in window_records:
        blocks.append(
            f"CHUNK_ID: {chunk.get('chunk_id', '')}\n"
            f"SEQUENCE_INDEX: {chunk.get('sequence_index', 0)}\n"
            f"CHAPTER_LABEL: {chunk.get('chapter_label', '') or ''}\n"
            f"INPUT_SOURCE: {chunk.get('input_source', CHARACTER_DISCOVERY_INPUT_SOURCE_ORIGINAL)}\n"
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
    source_chunks: list[dict[str, object]],
) -> tuple[
    int,
    int,
    int,
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    int,
    str | None,
]:
    """
    @brief      Restore the resume state.
    @param[in]  existing_state Value for `existing_state`.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  source_chunks Current source chunk records.
    @return     Derived helper result.
    """
    if str(existing_state.get("status", "")) not in {"running", "failed", "cancelled"}:
        return 0, 0, 0, [], [], [], [], 0, None
    source = existing_state.get("source", {})
    if not isinstance(source, dict) or str(source.get("fingerprint", "")) != input_fingerprint:
        return 0, 0, 0, [], [], [], [], 0, None
    checkpoint = existing_state.get("checkpoint")
    if not isinstance(checkpoint, dict):
        return 0, 0, 0, [], [], [], [], 0, None
    phase = str(checkpoint.get("phase", ""))
    candidates = _restore_mapping_list(checkpoint.get("candidates"))
    if phase == "discovery":
        if (
            type(checkpoint.get("next_chunk_index")) is not int
            or type(checkpoint.get("completed_window_count")) is not int
            or type(checkpoint.get("planned_window_count")) is not int
        ):
            return 0, 0, 0, [], [], [], [], 0, None
        completed_window_count = int(checkpoint["completed_window_count"])
        planned_window_count = int(checkpoint["planned_window_count"])
        if completed_window_count < 0 or planned_window_count < completed_window_count:
            return 0, 0, 0, [], [], [], [], 0, None
        next_chunk_index = max(
            0,
            min(int(checkpoint.get("next_chunk_index", 0)), len(source_chunks)),
        )
        return (
            completed_window_count,
            planned_window_count,
            next_chunk_index,
            candidates,
            [],
            [],
            [],
            0,
            "discovery",
        )
    if phase != "synthesis":
        return 0, 0, 0, [], [], [], [], 0, None
    if (
        type(checkpoint.get("next_candidate_index")) is not int
        or type(checkpoint.get("completed_window_count")) is not int
        or type(checkpoint.get("planned_window_count")) is not int
    ):
        return 0, 0, 0, [], [], [], [], 0, None
    completed_window_count = int(checkpoint["completed_window_count"])
    planned_window_count = int(checkpoint["planned_window_count"])
    if (
        completed_window_count < 0
        or planned_window_count < completed_window_count
        or completed_window_count != planned_window_count
    ):
        return 0, 0, 0, [], [], [], [], 0, None
    next_candidate_index = max(
        0,
        min(int(checkpoint.get("next_candidate_index", 0)), len(candidates)),
    )
    completed_candidates = candidates[:next_candidate_index]
    current_ai_by_id = {
        str(item.get("character_id", "")): item
        for item in existing_state.get("characters", [])
        if isinstance(item, dict)
        and isinstance(item.get("provenance"), dict)
        and str(item["provenance"].get("origin", "")) == "ai"
    }
    synthesized_profiles = [
        _normalize_character_profile(_flat_character_profile(current_ai_by_id[candidate_id]))
        for candidate in completed_candidates
        if (candidate_id := str(candidate.get("character_id", ""))) in current_ai_by_id
    ]
    return (
        completed_window_count,
        planned_window_count,
        len(source_chunks),
        [],
        candidates,
        _restore_rejected_candidate_diagnostics(existing_state.get("rejected_candidates")),
        synthesized_profiles,
        next_candidate_index,
        "synthesis",
    )


def _next_chunk_index_after_window(
    source_chunks: list[dict[str, object]],
    window_records: list[dict[str, object]],
) -> int:
    """
    @brief      Return the next source chunk index after one completed discovery window.
    @param[in]  source_chunks Current source chunk records.
    @param[in]  window_records Completed discovery window records.
    @return     Source chunk index immediately after the completed window.
    """
    if not window_records:
        return 0
    chunk_index_by_id = {
        str(chunk.get("chunk_id", "")).strip(): index
        for index, chunk in enumerate(source_chunks)
        if str(chunk.get("chunk_id", "")).strip()
    }
    completed_indexes = [
        chunk_index_by_id[str(chunk.get("chunk_id", "")).strip()]
        for chunk in window_records
        if str(chunk.get("chunk_id", "")).strip() in chunk_index_by_id
    ]
    if not completed_indexes:
        return 0
    return min(max(completed_indexes) + 1, len(source_chunks))


def _restore_token_usage(existing_state: dict[str, object]) -> TokenUsagePayload:
    """
    @brief      Restore the token usage.
    @param[in]  existing_state Value for `existing_state`.
    @return     Derived helper result.
    """
    return token_usage_service.restore_token_usage(existing_state.get("token_usage"))


def _restore_mapping_list(payload: object) -> list[dict[str, object]]:
    """
    @brief      Restore the mapping list.
    @param[in]  payload Optional payload processed by the helper.
    @return     Derived helper result.
    """
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def _restore_rejected_candidate_diagnostics(payload: object) -> list[dict[str, object]]:
    """Restore compact rejected-candidate diagnostics from compatible persisted state."""
    return _normalize_rejected_candidate_diagnostics(payload)


def _normalize_rejected_candidate_diagnostics(payload: object) -> list[dict[str, object]]:
    """Deduplicate and order internally generated rejected-candidate diagnostics."""
    if not isinstance(payload, list):
        return []
    diagnostics_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        canonical_name = str(entry.get("canonical_name", "")).strip()
        reason = str(entry.get("reason", "")).strip()
        evidence_count = entry.get("evidence_count")
        identity_merge_count = entry.get("identity_merge_count")
        identity = _normalize_identity(canonical_name)
        if (
            not identity
            or reason not in REJECTED_CANDIDATE_REASONS
            or type(evidence_count) is not int
            or evidence_count < 0
            or type(identity_merge_count) is not int
            or identity_merge_count < 1
        ):
            continue
        diagnostic_key = (identity, reason)
        existing = diagnostics_by_key.get(diagnostic_key)
        if existing is None:
            diagnostics_by_key[diagnostic_key] = {
                "canonical_name": canonical_name,
                "reason": reason,
                "evidence_count": evidence_count,
                "identity_merge_count": identity_merge_count,
            }
            continue
        existing["evidence_count"] = max(int(existing["evidence_count"]), evidence_count)
        existing["identity_merge_count"] = max(int(existing["identity_merge_count"]), identity_merge_count)
    return sorted(
        diagnostics_by_key.values(),
        key=lambda diagnostic: (str(diagnostic["canonical_name"]).casefold(), str(diagnostic["reason"])),
    )


def _merge_synthesized_profile_into_inventory(
    character_inventory: list[dict[str, object]],
    synthesized_profile: CharacterProfilePayload,
) -> list[dict[str, object]]:
    """
    @brief      Add one synthesized profile without replacing current durable data.
    @param[in]  character_inventory Current authoritative nested character records.
    @param[in]  synthesized_profile Newly synthesized flat character profile.
    @return     Updated nested inventory with no duplicate stable identifier.
    """
    synthesized_character_id = str(synthesized_profile.get("character_id", ""))
    preserved_inventory = _restore_mapping_list(character_inventory)
    if any(
        str(item.get("character_id", "")) == synthesized_character_id
        for item in preserved_inventory
    ):
        return preserved_inventory
    preserved_inventory.append(_nested_character_profile(synthesized_profile))
    return preserved_inventory


def _resolve_log_path(project_root: Path, run_token: str) -> Path:
    """
    @brief      Resolve the log path.
    @param[in]  project_root Active project root folder.
    @param[in]  run_token Runtime token used only for deriving a new log filename.
    @return     Derived helper result.
    """
    timestamp_token = run_token.replace("-", "").replace(":", "").replace("+", "_").replace(".", "")
    resolved_log_path = build_operation_output_path(
        project_root,
        "character_discovery",
        config.ai_transaction_log_file_name("character_discovery", timestamp_token),
    )
    if not resolved_log_path.exists():
        resolved_log_path.write_text("", encoding="utf-8")
    return resolved_log_path


def _write_operation_state(
    state_path: Path,
    status: str,
    phase: str,
    progress_current: int,
    progress_total: int,
    run_token: str,
    profile_id: str,
    input_fingerprint: str,
    token_usage: TokenUsagePayload,
    additional_character_discovery_instructions: str,
    checkpoint: dict[str, object] | None,
    source: dict[str, str] | None = None,
    character_inventory: list[dict[str, object]] | None = None,
    rejected_candidates: list[dict[str, object]] | None = None,
) -> None:
    """
    @brief      Write the operation state.
    @param[in]  state_path Operation-state file path.
    @param[in]  status Value for `status`.
    @param[in]  phase Character Discovery operation phase.
    @param[in]  progress_current Value for `progress_current`.
    @param[in]  progress_total Value for `progress_total`.
    @param[in]  run_token Runtime token preserved only inside the resume checkpoint.
    @param[in]  profile_id Profile identifier.
    @param[in]  input_fingerprint Value for `input_fingerprint`.
    @param[in]  token_usage Value for `token_usage`.
    @param[in]  additional_character_discovery_instructions Optional operator-supplied discovery rules.
    @param[in]  checkpoint Value for `checkpoint`.
    @param[in]  character_inventory Current authoritative nested character records.
    @param[in]  rejected_candidates Current compact rejected-candidate diagnostics.
    @return     None.
    """
    _ = (
        progress_current,
        progress_total,
        run_token,
        input_fingerprint,
    )
    existing_document = load_character_document(state_path.parent)
    resolved_source = dict(source or (existing_document or {}).get("source", {}))
    if not resolved_source:
        raise CharacterDocumentError("Character Discovery source metadata is required.")
    legacy_checkpoint = dict(checkpoint) if isinstance(checkpoint, dict) else None
    nested_characters = (
        _restore_mapping_list(character_inventory)
        if character_inventory is not None
        else _restore_mapping_list((existing_document or {}).get("characters"))
    )
    persisted_rejected_candidates = _normalize_rejected_candidate_diagnostics(
        rejected_candidates
        if rejected_candidates is not None
        else (existing_document or {}).get("rejected_candidates")
    )
    if phase == "discovery" and legacy_checkpoint is not None:
        persisted_checkpoint: dict[str, object] | None = {
            "phase": "discovery",
            "completed_window_count": max(
                0,
                int(legacy_checkpoint.get("completed_window_count", 0)),
            ),
            "planned_window_count": max(
                0,
                int(legacy_checkpoint.get("planned_window_count", 0)),
            ),
            "next_chunk_index": max(
                0,
                int(legacy_checkpoint.get("next_discovery_start_chunk_index", 0)),
            ),
            "candidates": _restore_mapping_list(legacy_checkpoint.get("raw_candidates")),
        }
    elif phase == "synthesis" and legacy_checkpoint is not None:
        persisted_checkpoint = {
            "phase": "synthesis",
            "completed_window_count": max(
                0,
                int(legacy_checkpoint.get("completed_window_count", 0)),
            ),
            "planned_window_count": max(
                0,
                int(legacy_checkpoint.get("planned_window_count", 0)),
            ),
            "next_candidate_index": max(
                0,
                int(legacy_checkpoint.get("next_candidate_index", 0)),
            ),
            "candidates": _restore_mapping_list(legacy_checkpoint.get("merged_candidates")),
        }
    else:
        persisted_checkpoint = None
    document: CharacterDocumentPayload = {
        "status": str(status),
        "source": resolved_source,
        "instructions": _normalized_additional_character_discovery_instructions(
            additional_character_discovery_instructions
        ),
        "token_usage": _persisted_character_token_usage(token_usage),
        "character_profile_id_last_used": profile_id,
        "rejected_candidates": persisted_rejected_candidates,
        "checkpoint": persisted_checkpoint,
        "failure": (
            {"phase": str(phase), "message": f"Character Discovery {phase} failed."}
            if status == "failed"
            else None
        ),
        "characters": nested_characters,
    }
    _validate_character_document(document)
    write_json_atomic(state_path, document)


def _persisted_character_token_usage(payload: object) -> TokenUsagePayload:
    """Normalize token usage to the zero-valued strict document contract."""
    normalized = token_usage_service.coerce_token_usage(payload)
    if bool(normalized.get("usage_available", False)):
        return normalized
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "usage_available": False,
    }


def _normalize_window_candidates(
    payload: object,
    chunk_map: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Normalize the window candidates.
    @param[in]  payload Optional payload processed by the helper.
    @param[in]  chunk_map Value for `chunk_map`.
    @return     Derived helper result.
    """
    if not isinstance(payload, list):
        return []
    normalized_candidates: list[dict[str, object]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        canonical_name = str(entry.get("canonical_name", "")).strip()
        if not canonical_name:
            continue
        evidence = _normalize_evidence(entry.get("evidence", []), chunk_map)
        gender_hint = str(entry.get("gender_hint", "")).strip()
        age_hint = str(entry.get("age_hint", "")).strip()
        normalized_candidates.append(
            {
                "canonical_name": canonical_name,
                "aliases": _normalize_string_list(entry.get("aliases", [])),
                "gender_hint": gender_hint,
                "gender_confidence": _demographic_confidence_for_hint(gender_hint, entry.get("gender_confidence")),
                "age_hint": age_hint,
                "age_confidence": _demographic_confidence_for_hint(age_hint, entry.get("age_confidence")),
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
    """
    groups: list[list[dict[str, object]]] = []
    group_index_by_alias_key: dict[str, int] = {}
    for candidate in candidates:
        alias_keys = {_normalize_identity(str(candidate.get("canonical_name", "")))}
        alias_keys.update(_normalize_identity(alias) for alias in list(candidate.get("aliases", [])))
        alias_keys.discard("")
        matching_group_indexes = [
            group_index_by_alias_key[alias_key] for alias_key in alias_keys if alias_key in group_index_by_alias_key
        ]
        if not matching_group_indexes:
            groups.append([dict(candidate)])
            target_group_index = len(groups) - 1
        else:
            target_group_index = min(matching_group_indexes)
            groups[target_group_index].append(dict(candidate))
        for alias_key in alias_keys:
            group_index_by_alias_key[alias_key] = target_group_index
    return groups


def _merge_candidate_identity_group(identity_group: list[dict[str, object]]) -> dict[str, object]:
    """
    @brief      Synthesize one candidate payload from an identity group.
    @param[in]  identity_group Candidates believed to represent the same character.
    @return     Merged candidate payload.
    @exception  None
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
        target["evidence"] = _dedupe_evidence(
            _restore_evidence(target.get("evidence", [])) + _restore_evidence(candidate.get("evidence", []))
        )
        target["has_dialogue_evidence"] = bool(target.get("has_dialogue_evidence")) or bool(
            candidate.get("has_dialogue_evidence")
        )
        _merge_confidence_field(target, candidate, "confidence")
        _merge_demographic_field(target, candidate, "gender")
        _merge_demographic_field(target, candidate, "age")
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
    """
    evidence = _restore_evidence(candidate.get("evidence", []))
    return {
        "canonical_name": str(candidate.get("canonical_name", "")).strip(),
        "reason": reason,
        "evidence_count": len(evidence),
        "identity_merge_count": int(candidate.get("identity_merge_count", 1)),
    }


def _merge_demographic_field(target: dict[str, object], candidate: dict[str, object], field_prefix: str) -> None:
    """
    @brief      Merge one demographic hint and confidence pair into an identity-group target.
    @param[in,out] target Merged candidate payload being built.
    @param[in]  candidate Candidate payload being folded into the target.
    @param[in]  field_prefix Demographic prefix, for example `gender` or `age`.
    @return     None.
    @exception  None
    """
    hint_field = f"{field_prefix}_hint"
    confidence_field = f"{field_prefix}_confidence"
    existing_hint = str(target.get(hint_field, "")).strip()
    candidate_hint = str(candidate.get(hint_field, "")).strip()
    existing_confidence = _normalize_demographic_confidence(target.get(confidence_field))
    candidate_confidence = _normalize_demographic_confidence(candidate.get(confidence_field))
    if not candidate_hint:
        return
    if (
        not existing_hint
        or _demographic_confidence_rank(candidate_confidence) > _demographic_confidence_rank(existing_confidence)
        or candidate_confidence == existing_confidence
        and len(candidate_hint) > len(existing_hint)
    ):
        target[hint_field] = candidate_hint
        target[confidence_field] = candidate_confidence


def _merge_confidence_field(target: dict[str, object], candidate: dict[str, object], field_name: str) -> None:
    """
    @brief      Merge one high-medium-low confidence field into an identity-group target.
    @param[in,out] target Merged candidate payload being built.
    @param[in]  candidate Candidate payload being folded into the target.
    @param[in]  field_name Confidence field to merge.
    @return     None.
    @exception  None
    """
    existing_value = str(target.get(field_name, "")).strip()
    candidate_value = str(candidate.get(field_name, "")).strip()
    if not candidate_value:
        return
    if not existing_value or _demographic_confidence_rank(candidate_value) > _demographic_confidence_rank(
        existing_value
    ):
        target[field_name] = candidate_value


def _normalize_demographic_confidence(value: object) -> str:
    """
    @brief      Normalize one demographic-confidence token.
    @param[in]  value Candidate confidence value.
    @return     Supported confidence token or an empty string.
    @exception  None
    """
    confidence = str(value or "").strip().casefold()
    return confidence if confidence in DEMOGRAPHIC_CONFIDENCE_VALUES else ""


def _demographic_confidence_for_hint(hint: object, confidence: object) -> str:
    """
    @brief      Normalize demographic confidence only when its matching hint exists.
    @param[in]  hint Matching demographic hint value.
    @param[in]  confidence Candidate confidence value.
    @return     Supported confidence token or an empty string.
    @exception  None
    """
    if not str(hint or "").strip():
        return ""
    return _normalize_demographic_confidence(confidence)


def _demographic_confidence_rank(value: object) -> int:
    """
    @brief      Rank one demographic-confidence token for merge precedence.
    @param[in]  value Candidate confidence value.
    @return     Numeric rank where larger is stronger.
    @exception  None
    """
    return {
        "": 0,
        EVIDENCE_CONFIDENCE_LOW: 1,
        EVIDENCE_CONFIDENCE_MEDIUM: 2,
        EVIDENCE_CONFIDENCE_HIGH: 3,
    }.get(_normalize_demographic_confidence(value), 0)


def _restore_evidence(payload: object) -> list[dict[str, object]]:
    """
    @brief      Restore the evidence.
    @param[in]  payload Optional payload processed by the helper.
    @return     Derived helper result.
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
    """
    return {
        "character_id": str(candidate.get("character_id", "")).strip(),
        "canonical_name": str(candidate.get("canonical_name", "")).strip(),
        "aliases": _normalize_string_list(candidate.get("aliases", [])),
        "gender_hint": str(candidate.get("gender_hint", "")).strip(),
        "gender_confidence": _demographic_confidence_for_hint(
            candidate.get("gender_hint", ""),
            candidate.get("gender_confidence"),
        ),
        "age_hint": str(candidate.get("age_hint", "")).strip(),
        "age_confidence": _demographic_confidence_for_hint(
            candidate.get("age_hint", ""),
            candidate.get("age_confidence"),
        ),
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
    """
    gender_hint = str(response_payload.get("gender_hint", candidate.get("gender_hint", ""))).strip()
    age_hint = str(response_payload.get("age_hint", candidate.get("age_hint", ""))).strip()
    return regenerate_character_voice_definition(
        {
            "character_id": str(candidate.get("character_id", "")),
            "canonical_name": str(response_payload.get("canonical_name", candidate.get("canonical_name", ""))).strip(),
            "aliases": _normalize_string_list(response_payload.get("aliases", candidate.get("aliases", []))),
            "gender_hint": gender_hint,
            "gender_confidence": _demographic_confidence_for_hint(
                gender_hint,
                response_payload.get("gender_confidence", candidate.get("gender_confidence", "")),
            ),
            "age_hint": age_hint,
            "age_confidence": _demographic_confidence_for_hint(
                age_hint,
                response_payload.get("age_confidence", candidate.get("age_confidence", "")),
            ),
            "voice_definition_prompt": str(response_payload.get("voice_definition_prompt", "")).strip(),
            CHARACTER_PREVIEW_TEXT_FIELD: _build_character_preview_text(response_payload, candidate),
            "confidence": str(response_payload.get("confidence", candidate.get("confidence", ""))).strip(),
            "review_status": _normalize_review_status(
                response_payload.get(
                    "review_status",
                    candidate.get("review_status", CHARACTER_REVIEW_STATUS_DISCOVERED),
                )
            ),
            "evidence": _restore_evidence(response_payload.get("evidence", candidate.get("evidence", [])))
            or _restore_evidence(candidate.get("evidence", [])),
        }
    )


def _normalize_character_profile(profile_payload: dict[str, object]) -> CharacterProfilePayload:
    """
    @brief      Normalize one compact stored character profile and backfill the voice prompt default.
    @param[in]  profile_payload Raw or partial character profile payload.
    @return     Normalized persisted profile payload.
    @exception  None
    """
    normalized_profile = _normalized_character_profile_core(profile_payload)
    normalized_voice_prompt = str(normalized_profile.get(CHARACTER_VOICE_PROMPT_FIELD, "")).strip()
    normalized_profile[CHARACTER_VOICE_PROMPT_FIELD] = _ensure_character_voice_prompt_instructions(
        normalized_voice_prompt or build_character_voice_definition_prompt(normalized_profile),
        normalized_profile,
    )
    return normalized_profile


def _normalize_review_status(raw_status: object) -> str:
    """
    @brief      Normalize one internal character review-status token.
    @param[in]  raw_status Raw review status.
    @return     Supported review-status token.
    @exception  None
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
    """
    existing_status = _normalize_review_status(existing_profile.get("review_status", ""))
    if existing_status == CHARACTER_REVIEW_STATUS_MANUAL:
        return CHARACTER_REVIEW_STATUS_MANUAL
    return CHARACTER_REVIEW_STATUS_EDITED


def _normalized_character_profile_core(profile_payload: dict[str, object]) -> CharacterProfilePayload:
    """
    @brief      Normalize one compact character profile payload without regenerating the final voice prompt.
    @param[in]  profile_payload Raw or partial character profile payload.
    @return     Core normalized profile payload.
    @exception  None
    """
    gender_hint = str(profile_payload.get("gender_hint", "")).strip()
    age_hint = str(profile_payload.get("age_hint", "")).strip()
    normalized_profile: CharacterProfilePayload = {
        "character_id": str(profile_payload.get("character_id", "")).strip(),
        "canonical_name": str(profile_payload.get("canonical_name", "")).strip(),
        "aliases": _normalize_string_list(profile_payload.get("aliases", [])),
        "gender_hint": gender_hint,
        "gender_confidence": _demographic_confidence_for_hint(
            gender_hint,
            profile_payload.get("gender_confidence"),
        ),
        "age_hint": age_hint,
        "age_confidence": _demographic_confidence_for_hint(age_hint, profile_payload.get("age_confidence")),
        CHARACTER_VOICE_PROMPT_FIELD: str(profile_payload.get(CHARACTER_VOICE_PROMPT_FIELD, "")).strip(),
        CHARACTER_PREVIEW_TEXT_FIELD: _normalized_character_preview_text(
            profile_payload.get(CHARACTER_PREVIEW_TEXT_FIELD, "")
        ),
        "confidence": str(profile_payload.get("confidence", "")).strip(),
        "review_status": _normalize_review_status(profile_payload.get("review_status", "")),
        "evidence": _restore_evidence(profile_payload.get("evidence", [])),
    }
    return normalized_profile


def _build_character_preview_text(
    response_payload: dict[str, object],
    candidate: dict[str, object],
) -> str:
    """
    @brief      Build a validated character sample preview from spoken dialogue evidence.
    @param[in]  response_payload AI synthesis response payload.
    @param[in]  candidate Merged character candidate payload.
    @return     Preview text meeting the configured minimum duration estimate, or an empty string.
    @exception  None
    """
    response_preview_text = _normalized_character_preview_text(response_payload.get(CHARACTER_PREVIEW_TEXT_FIELD, ""))
    if _is_valid_character_preview_text(response_preview_text) and _preview_text_supported_by_evidence(
        response_preview_text,
        candidate,
    ):
        return response_preview_text
    return _candidate_preview_text(candidate)


def _candidate_preview_text(candidate: dict[str, object]) -> str:
    """
    @brief      Derive a character preview text from ranked spoken-dialogue evidence excerpts.
    @param[in]  candidate Merged character candidate payload.
    @return     Preview text meeting the configured minimum duration estimate, or an empty string.
    @exception  None
    """
    fragments: list[str] = []
    preview_limit = max(1, int(config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT))
    for evidence_item in _rank_synthesis_evidence(_restore_evidence(candidate.get("evidence", []))):
        if not _evidence_has_direct_dialogue(evidence_item):
            continue
        fragment = _spoken_preview_fragment(str(evidence_item.get("source_excerpt", "")))
        if not fragment:
            continue
        current_text = " ".join(fragments).strip()
        proposed_text = " ".join(item for item in (current_text, fragment) if item).strip()
        if len(proposed_text) > preview_limit:
            if _is_valid_character_preview_text(current_text):
                return current_text
            continue
        fragments.append(fragment)
        if _is_valid_character_preview_text(proposed_text):
            return proposed_text
    return ""


def _preview_text_supported_by_evidence(preview_text: str, candidate: dict[str, object]) -> bool:
    """
    @brief      Verify a generated preview is extracted from spoken-dialogue evidence.
    @param[in]  preview_text Candidate preview text.
    @param[in]  candidate Merged character candidate payload.
    @return     True when the normalized preview appears in the normalized spoken evidence text.
    @exception  None
    """
    normalized_preview_text = _normalized_preview_support_text(preview_text)
    if not normalized_preview_text:
        return False
    evidence_fragments = [
        _spoken_preview_fragment(str(evidence_item.get("source_excerpt", "")))
        for evidence_item in _rank_synthesis_evidence(_restore_evidence(candidate.get("evidence", [])))
        if _evidence_has_direct_dialogue(evidence_item)
    ]
    normalized_evidence_text = _normalized_preview_support_text(" ".join(evidence_fragments))
    return normalized_preview_text in normalized_evidence_text


def _spoken_preview_fragment(text: str) -> str:
    """
    @brief      Normalize one spoken evidence excerpt for preview-sample use.
    @param[in]  text Source dialogue excerpt.
    @return     Excerpt with surrounding dialogue delimiters removed.
    @exception  None
    """
    normalized_text = " ".join(str(text).split()).strip()
    normalized_text = normalized_text.strip("\"'\u201c\u201d\u2018\u2019\u00ab\u00bb\u300c\u300d\u300e\u300f")
    normalized_text = normalized_text.lstrip("-\u2013\u2014").strip()
    return normalized_text


def _normalized_preview_support_text(text: str) -> str:
    """
    @brief      Normalize preview/evidence text for source-support checks.
    @param[in]  text Candidate text.
    @return     Lowercase alphanumeric support-check text with normalized spacing.
    @exception  None
    """
    return " ".join(re.sub(r"[^\w\s]", " ", str(text).casefold(), flags=re.UNICODE).split())


def _normalized_character_preview_text(preview_text: object) -> str:
    """
    @brief      Normalize one generated character preview text value.
    @param[in]  preview_text Candidate preview text.
    @return     Single-line preview text capped to the configured character limit.
    @exception  None
    """
    normalized_text = " ".join(str(preview_text or "").split()).strip()
    preview_limit = max(1, int(config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT))
    if len(normalized_text) <= preview_limit:
        return normalized_text
    return ""


def _is_valid_character_preview_text(preview_text: str) -> bool:
    """
    @brief      Decide whether preview text meets the configured Qwen TTS duration estimate.
    @param[in]  preview_text Candidate preview text.
    @return     True when the text is long enough and inside the preview character limit.
    @exception  None
    """
    normalized_text = _normalized_character_preview_text(preview_text)
    if not normalized_text:
        return False
    return tts_budget_service.estimated_word_count(normalized_text) >= _minimum_character_preview_word_count()


def _minimum_character_preview_word_count() -> int:
    """
    @brief      Estimate the minimum character-preview word count for useful Qwen TTS references.
    @return     Minimum preview word count.
    @exception  None
    """
    return max(
        1,
        int(
            float(config.DEFAULT_TTS_MIN_PREVIEW_AUDIO_SECONDS) * float(config.DEFAULT_TTS_WORDS_PER_AUDIO_SECOND)
            + 0.999
        ),
    )


def _character_voice_gender_instruction(profile_payload: dict[str, object]) -> str:
    """
    @brief      Build explicit sex/gender guidance for one character voice prompt.
    @param[in]  profile_payload Character profile payload.
    @return     Sex/gender instruction text without the field label.
    """
    gender_hint = str(profile_payload.get("gender_hint", "")).strip()
    if gender_hint:
        gender_confidence = _normalize_demographic_confidence(profile_payload.get("gender_confidence"))
        if gender_confidence in {EVIDENCE_CONFIDENCE_LOW, EVIDENCE_CONFIDENCE_MEDIUM}:
            return (
                f"{gender_hint} ({gender_confidence} confidence). Match this cautiously in the vocal identity and "
                "do not let it overpower clearer voice evidence."
            )
        return (
            f"{gender_hint}. Match this explicitly in the vocal identity and do not replace it with a different "
            "default."
        )
    return (
        "not specified in the source. Use a neutral or androgynous vocal identity and do not default to a male voice."
    )


def _character_voice_age_instruction(profile_payload: dict[str, object]) -> str:
    """
    @brief      Build explicit age-domain guidance for one character voice prompt.
    @param[in]  profile_payload Character profile payload.
    @return     Age-domain instruction text without the field label.
    """
    age_hint = str(profile_payload.get("age_hint", "")).strip()
    if age_hint:
        age_confidence = _normalize_demographic_confidence(profile_payload.get("age_confidence"))
        if age_confidence in {EVIDENCE_CONFIDENCE_LOW, EVIDENCE_CONFIDENCE_MEDIUM}:
            return (
                f"{age_hint} ({age_confidence} confidence). Match this cautiously in the vocal age and do not let it "
                "overpower clearer voice evidence."
            )
        return (
            f"{age_hint}. Match this explicitly in the vocal age and do not replace it with a younger or older default."
        )
    return "not specified in the source. Use an age-neutral adult voice and do not default to a young voice."


def _ensure_character_voice_prompt_instructions(prompt_text: str, profile_payload: dict[str, object]) -> str:
    """
    @brief      Add required character voice guidance to one voice-definition prompt.
    @param[in]  prompt_text Candidate voice-definition prompt.
    @param[in]  profile_payload Character profile payload.
    @return     Prompt text containing explicit sex/gender and age-domain guidance.
    """
    prompt_with_gender = _ensure_character_voice_prompt_gender_instruction(prompt_text, profile_payload)
    return _ensure_character_voice_prompt_age_instruction(prompt_with_gender, profile_payload)


def _ensure_character_voice_prompt_gender_instruction(prompt_text: str, profile_payload: dict[str, object]) -> str:
    """
    @brief      Add explicit sex/gender guidance to one character voice-definition prompt.
    @param[in]  prompt_text Candidate voice-definition prompt.
    @param[in]  profile_payload Character profile payload.
    @return     Prompt text containing explicit sex/gender guidance.
    """
    normalized_prompt = str(prompt_text).strip()
    if _prompt_has_explicit_gender_instruction(normalized_prompt):
        return normalized_prompt
    return f"{normalized_prompt} Sex/Gender: {_character_voice_gender_instruction(profile_payload)}".strip()


def _ensure_character_voice_prompt_age_instruction(prompt_text: str, profile_payload: dict[str, object]) -> str:
    """
    @brief      Add explicit age-domain guidance to one character voice-definition prompt.
    @param[in]  prompt_text Candidate voice-definition prompt.
    @param[in]  profile_payload Character profile payload.
    @return     Prompt text containing explicit age-domain guidance.
    """
    normalized_prompt = str(prompt_text).strip()
    if _prompt_has_explicit_age_instruction(normalized_prompt):
        return normalized_prompt
    return f"{normalized_prompt} Age Domain: {_character_voice_age_instruction(profile_payload)}".strip()


def _prompt_has_explicit_gender_instruction(prompt_text: str) -> bool:
    """
    @brief      Return whether a prompt already carries explicit sex/gender guidance.
    @param[in]  prompt_text Candidate voice-definition prompt.
    @return     True when explicit sex or gender guidance is already present.
    """
    normalized_prompt = str(prompt_text).casefold()
    return bool(
        re.search(r"\b(sex/gender|gender hint|gender)\s*:", normalized_prompt)
        or re.search(r"\b(female|male|woman|man|girl|boy|androgynous)\b", normalized_prompt)
    )


def _prompt_has_explicit_age_instruction(prompt_text: str) -> bool:
    """
    @brief      Return whether a prompt already carries explicit age-domain guidance.
    @param[in]  prompt_text Candidate voice-definition prompt.
    @return     True when explicit age-domain guidance is already present.
    """
    normalized_prompt = str(prompt_text).casefold()
    return bool(re.search(r"\b(age domain|age hint|age)\s*:", normalized_prompt))


def _normalize_identity(value: str) -> str:
    """
    @brief      Build the shared Unicode character-identity comparison key.
    @param[in]  value Candidate canonical name or alias.
    @return     Case-folded alphanumeric Unicode identity key.
    """
    decomposed_value = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(character for character in decomposed_value if character.isalnum())


def _slugify_character_id(name: str, fallback_index: int) -> str:
    """
    @brief      Execute the slugify character id helper.
    @param[in]  name Value for `name`.
    @param[in]  fallback_index Value for `fallback_index`.
    @return     Helper result.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    return slug or f"character_{fallback_index:04d}"


def _candidate_sort_key(candidate: dict[str, object]) -> tuple[int, str]:
    """
    @brief      Execute the candidate sort key helper.
    @param[in]  candidate Value for `candidate`.
    @return     Helper result.
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
    """
    evidence = _restore_evidence(profile.get("evidence", []))
    if not evidence:
        return 999999, str(profile.get("canonical_name", "")).casefold()
    return (
        min(int(item.get("sequence_index", 0)) for item in evidence),
        str(profile.get("canonical_name", "")).casefold(),
    )


def _nested_profile_sort_key(profile: dict[str, object]) -> tuple[int, str]:
    """
    @brief      Derive deterministic inventory order without rewriting a nested record.
    @param[in]  profile Authoritative nested character record.
    @return     Existing profile order key.
    """
    return _profile_sort_key(_flat_character_profile(profile))


def _candidate_has_spoken_dialogue(candidate: dict[str, object]) -> bool:
    """
    @brief      Execute the candidate has spoken dialogue helper.
    @param[in]  candidate Value for `candidate`.
    @return     Helper result.
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
    """
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


# END OF FILE
