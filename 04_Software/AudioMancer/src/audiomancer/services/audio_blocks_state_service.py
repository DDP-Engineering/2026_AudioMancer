#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audio_blocks_state_service.py
@brief Audio Blocks page state helpers for AudioMancer.
@details Builds the approval-aware Audio Blocks page state from persisted
         Speech Blocks, narrator plus character voice samples, current Audio
         Blocks output, and the resumable runtime operation state.
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 0.6.1
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    audio_blocks_artifact_service,
    audio_blocks_service,
    character_voices_service,
    chunking_document_service,
    home_presenter_service,
    narrator_definition_service,
    speech_blocks_service,
    tts_budget_service,
    ui_state_service,
)


def build_audio_blocks_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """
    @brief      Build the Audio Blocks page state from project artifacts.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Persisted application settings payload.
    @return     Page-state payload consumed by the Audio Blocks page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.5.2
    """
    if project_root is None or manifest is None:
        return _empty_state(language, settings_payload)

    speech_blocks = speech_blocks_service.sort_speech_blocks(speech_blocks_service.load_speech_blocks(project_root))
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    report = audio_blocks_service.load_audio_blocks_report(project_root)
    operation_state = audio_blocks_service.load_operation_state(project_root)
    operation_metadata = operation_state.get("metadata", {}) if isinstance(operation_state, dict) else {}
    if not isinstance(operation_metadata, dict):
        operation_metadata = {}
    merged_blocks = _merge_audio_block_state(project_root, speech_blocks, audio_blocks, operation_state)
    scene_ambience_audio_enabled = _scene_ambience_audio_enabled(settings_payload)
    current_block = _resolve_current_block(merged_blocks, operation_state)
    current_block_id = None if current_block is None else str(current_block.get("speech_block_id", "")).strip()
    generated_count = sum(1 for block in merged_blocks if audio_blocks_service.is_generated(block))
    approved_count = sum(1 for block in merged_blocks if audio_blocks_service.is_approved(block))
    total_count = len(merged_blocks)
    progress_current = generated_count if operation_state is None else int(operation_state.get("progress_current", 0))
    progress_total = total_count if operation_state is None else int(operation_state.get("progress_total", total_count))
    resolved_stage_status = _audio_blocks_stage_status(report, operation_state)
    prompt_count = int(
        operation_metadata.get("prompt_count", report.get("prompt_count", 0) if isinstance(report, dict) else 0)
    )
    current_phase = str(operation_metadata.get("current_phase", "")).strip() or None
    invalidation_reason = str(operation_metadata.get("invalidation_reason", "")).strip() or None
    notes = build_audio_blocks_notes(
        manifest,
        speech_blocks,
        merged_blocks,
        report,
        operation_state,
        language,
    )
    status_lines = [
        ui_state_service.translate("audio_blocks.status_generated", language).format(
            generated_count=generated_count,
            total_count=total_count,
        ),
        ui_state_service.translate("audio_blocks.status_approved", language).format(
            approved_count=approved_count,
            total_count=total_count,
        ),
        ui_state_service.translate("audio_blocks.status_voice_language", language).format(
            language_label=character_voices_service.load_selected_voice_language(
                project_root,
                narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
            )
        ),
        ui_state_service.translate("audio_blocks.status_prompts", language).format(
            prompt_count=prompt_count,
        ),
    ]
    return {
        "full_source_text": _build_full_source_text(project_root, manifest, speech_blocks),
        "speech_blocks": merged_blocks,
        "current_block_id": current_block_id,
        "current_block_speaker": "" if current_block is None else str(current_block.get("speaker_display_name", "")),
        "current_block_text": "" if current_block is None else str(current_block.get("text", "")),
        "notes": notes,
        "status_lines": status_lines,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "progress_percent": 0 if progress_total <= 0 else int((progress_current / max(progress_total, 1)) * 100),
        "current_phase": current_phase,
        "prompt_count": prompt_count,
        "invalidation_reason": invalidation_reason,
        "stage_status": resolved_stage_status,
        "can_start_or_continue": _can_start_or_continue_generation(
            speech_blocks,
            merged_blocks,
            resolved_stage_status,
            scene_ambience_audio_enabled,
        ),
        "can_reset": audio_blocks_service.has_persisted_audio_blocks(project_root),
        "can_approve_all": any(
            audio_blocks_service.is_generated(block) and not audio_blocks_service.is_approved(block)
            for block in merged_blocks
        ),
        "can_regenerate_selected": current_block is not None,
        "can_approve_selected": current_block is not None and audio_blocks_service.is_generated(current_block),
        "selected_text_character_limit": _selected_text_character_limit(settings_payload, merged_blocks),
        "scene_ambience_audio_enabled": scene_ambience_audio_enabled,
    }


def _can_start_or_continue_generation(
    speech_blocks: list[dict[str, object]],
    audio_blocks: list[dict[str, object]],
    stage_status: str,
    scene_ambience_audio_enabled: bool = False,
) -> bool:
    """
    @brief      Return whether Audio Blocks generation still has approved source work to process.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  audio_blocks Current merged Audio Blocks display payload list.
    @param[in]  stage_status Effective Audio Blocks stage token.
    @return     True when at least one approved Speech Block still lacks generated audio.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.1
    """
    _ = stage_status
    generated_by_speech_block_id = {
        str(block.get("speech_block_id", "")).strip(): audio_blocks_service.is_generated(block)
        for block in audio_blocks
    }
    for speech_block in speech_blocks:
        speech_block_id = str(speech_block.get("speech_block_id", "")).strip()
        if (
            not scene_ambience_audio_enabled
            and str(speech_block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
        ):
            continue
        if (
            speech_block_id
            and bool(speech_block.get("approved", False))
            and not generated_by_speech_block_id.get(
                speech_block_id,
                False,
            )
        ):
            return True
    return False


def _scene_ambience_audio_enabled(settings_payload: dict[str, object] | None) -> bool:
    """
    @brief      Resolve the default Audio Blocks scene-ambience audio selector state.
    @details    Scene Ambience placement owns enablement for the whole pipeline, so the Audio
                Blocks selector starts on whenever TTS Settings asks for ambience blocks at all.
                The operator can still switch it off for one run without changing settings.
    @param[in]  settings_payload Persisted application settings payload.
    @return     True when Scene Ambience audio generation is enabled by default.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.2.0
    """
    if not isinstance(settings_payload, dict):
        return False
    placement = str(
        settings_payload.get("scene_ambience_placement", config.DEFAULT_SCENE_AMBIENCE_PLACEMENT)
    ).strip()
    if placement not in config.SCENE_AMBIENCE_PLACEMENT_OPTIONS:
        placement = config.DEFAULT_SCENE_AMBIENCE_PLACEMENT
    return placement != "none"


def build_audio_blocks_notes(
    manifest: dict[str, object],
    speech_blocks: list[dict[str, object]],
    audio_blocks: list[dict[str, object]],
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing Audio Blocks notes for the active project.
    @param[in]  manifest Active project manifest payload.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  audio_blocks Current merged Audio Blocks payload list.
    @param[in]  report Persisted Audio Blocks report or `None`.
    @param[in]  operation_state Persisted Audio Blocks operation state or `None`.
    @param[in]  language Runtime UI language code.
    @return     Ordered Audio Blocks notes for the page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    if home_presenter_service.source_document_name(manifest) is None:
        return [ui_state_service.translate("audio_blocks.note_no_source", language)]
    if not speech_blocks:
        return [ui_state_service.translate("audio_blocks.note_missing_speech_blocks", language)]

    generated_count = sum(1 for block in audio_blocks if audio_blocks_service.is_generated(block))
    approved_count = sum(1 for block in audio_blocks if audio_blocks_service.is_approved(block))
    operation_metadata = operation_state.get("metadata", {}) if isinstance(operation_state, dict) else {}
    if not isinstance(operation_metadata, dict):
        operation_metadata = {}
    current_phase = str(operation_metadata.get("current_phase", "")).strip()
    prompt_count = int(
        operation_metadata.get("prompt_count", report.get("prompt_count", 0) if isinstance(report, dict) else 0)
    )
    invalidation_reason = str(operation_metadata.get("invalidation_reason", "")).strip()
    notes = [
        ui_state_service.translate("audio_blocks.note_summary", language).format(
            generated_count=generated_count,
            approved_count=approved_count,
            total_count=len(speech_blocks),
        )
    ]
    stage_status = _audio_blocks_stage_status(report, operation_state)
    if stage_status == "running":
        if current_phase == audio_blocks_service._PROFILE_PHASE:  # noqa: SLF001
            notes.append(
                ui_state_service.translate("audio_blocks.note_prepare_prompts", language).format(
                    prompt_count=prompt_count,
                )
            )
        elif current_phase == audio_blocks_service._GENERATE_PHASE:  # noqa: SLF001
            notes.append(ui_state_service.translate("audio_blocks.note_generating_blocks", language))
        notes.append(
            ui_state_service.translate("audio_blocks.note_in_progress", language).format(
                progress_current=0 if operation_state is None else int(operation_state.get("progress_current", 0)),
                progress_total=len(speech_blocks)
                if operation_state is None
                else int(operation_state.get("progress_total", len(speech_blocks))),
            )
        )
    elif stage_status in {"failed", "cancelled"}:
        notes.append(
            ui_state_service.translate("audio_blocks.note_resume", language).format(
                progress_current=0 if operation_state is None else int(operation_state.get("progress_current", 0)),
                progress_total=len(speech_blocks)
                if operation_state is None
                else int(operation_state.get("progress_total", len(speech_blocks))),
            )
        )
    elif (
        report is not None
        and str(report.get("audio_blocks_stage_status", "")).strip()
        == audio_blocks_service.AUDIO_BLOCKS_STAGE_COMPLETED
    ):
        notes.append(ui_state_service.translate("audio_blocks.note_ready_for_assembly", language))
    elif generated_count >= len(speech_blocks) and speech_blocks:
        notes.append(ui_state_service.translate("audio_blocks.note_waiting_for_approval", language))
    else:
        notes.append(ui_state_service.translate("audio_blocks.note_ready", language))
    if invalidation_reason:
        notes.append(
            ui_state_service.translate("audio_blocks.note_invalidated", language).format(
                invalidation_reason=invalidation_reason
            )
        )
    return notes


def _empty_state(language: str, settings_payload: dict[str, object] | None = None) -> dict[str, object]:
    """
    @brief      Build the default Audio Blocks page state when no active project exists.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Persisted application settings payload.
    @return     Empty default page-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.0
    """
    return {
        "full_source_text": "",
        "speech_blocks": [],
        "current_block_id": None,
        "current_block_speaker": "",
        "current_block_text": "",
        "notes": [ui_state_service.translate("audio_blocks.note_no_project", language)],
        "status_lines": [],
        "progress_current": 0,
        "progress_total": 0,
        "progress_percent": 0,
        "current_phase": None,
        "prompt_count": 0,
        "invalidation_reason": None,
        "stage_status": audio_blocks_service.AUDIO_BLOCKS_STAGE_NOT_STARTED,
        "can_start_or_continue": False,
        "can_reset": False,
        "can_approve_all": False,
        "can_regenerate_selected": False,
        "can_approve_selected": False,
        "selected_text_character_limit": _selected_text_character_limit(settings_payload, []),
        "scene_ambience_audio_enabled": _scene_ambience_audio_enabled(settings_payload),
    }


def _build_full_source_text(
    project_root: Path,
    manifest: dict[str, object],
    speech_blocks: list[dict[str, object]],
) -> str:
    """
    @brief      Build one read-only full-source text string for the Audio Blocks page.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @return     Full source text reconstructed from the selected source chunks.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    if not chunking_document_service.load_chunks(project_root) or not _source_chunks_are_resolvable(
        project_root,
        manifest,
    ):
        return "\n\n".join(str(block.get("text", "")) for block in speech_blocks)
    try:
        source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
        source_chunks = sorted(
            source_resolution.get("source_chunks", []),
            key=lambda item: int(item.get("sequence_index", 0)),
        )
        return "\n\n".join(str(chunk.get("text", "")) for chunk in source_chunks)
    except ValueError:
        return "\n\n".join(str(block.get("text", "")) for block in speech_blocks)


def _selected_text_character_limit(
    settings_payload: dict[str, object] | None,
    audio_blocks: list[dict[str, object]],
) -> int:
    """
    @brief      Resolve an approximate selected speech text limit in characters.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  audio_blocks Current merged Audio Blocks payload list.
    @return     Approximate safe character limit for the active TTS model.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-05
    @version    0.2.0
    """
    _ = audio_blocks
    discovered_models = []
    if isinstance(settings_payload, dict):
        raw_models = settings_payload.get("tts_runtime_discovered_models", [])
        if isinstance(raw_models, list):
            discovered_models = [model for model in raw_models if isinstance(model, dict)]
    budget_payload = tts_budget_service.resolve_cached_tts_budget(discovered_models)
    return int(budget_payload.get("safe_word_count", 0) or 0) * 6


def _merge_audio_block_state(
    project_root: Path,
    speech_blocks: list[dict[str, object]],
    audio_blocks: list[dict[str, object]],
    operation_state: dict[str, object] | None,
) -> list[dict[str, object]]:
    """
    @brief      Merge persisted Audio Blocks data onto the current Speech Blocks list for display.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_blocks Current Speech Blocks payload list.
    @param[in]  audio_blocks Persisted Audio Blocks payload list.
    @param[in]  operation_state Persisted Audio Blocks operation state or `None`.
    @return     Ordered display-model payload list for the Audio Blocks page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.5.1
    """
    audio_by_id = {str(block.get("speech_block_id", "")).strip(): dict(block) for block in audio_blocks}
    current_block_id = None
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
        if isinstance(metadata, dict):
            current_block_id = str(metadata.get("current_block_id", "")).strip() or None
    merged_blocks: list[dict[str, object]] = []
    for speech_block in speech_blocks:
        speech_block_id = str(speech_block.get("speech_block_id", "")).strip()
        persisted_audio_block = audio_by_id.get(speech_block_id, {})
        speaker_display_name = str(speech_block.get("speaker_display_name", "")).strip() or "Narrator"
        audio_file_name = _resolve_persisted_audio_file_name(persisted_audio_block)
        duration_seconds = _resolve_audio_duration_seconds(persisted_audio_block)
        merged_blocks.append(
            {
                "speech_block_id": speech_block_id,
                "sequence_index": int(speech_block.get("sequence_index", 0)),
                "chunk_id": str(speech_block.get("chunk_id", "")).strip(),
                "content_kind": str(speech_block.get("content_kind", "")).strip(),
                "speaker_display_name": speaker_display_name,
                "normalized_speaker_name": (
                    str(persisted_audio_block.get("normalized_speaker_name", "")).strip()
                    or audio_blocks_service.normalize_speaker_name(speaker_display_name)
                ),
                "text": str(speech_block.get("text", "")),
                "generated": audio_blocks_service.is_generated(persisted_audio_block),
                "approved": audio_blocks_service.is_approved(persisted_audio_block),
                "metadata_only": bool(persisted_audio_block.get("metadata_only", False))
                or str(speech_block.get("content_kind", "")).strip()
                in {
                    speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                    speech_blocks_service.CONTENT_KIND_PAUSE,
                    speech_blocks_service.CONTENT_KIND_INDICATION,
                },
                "special_block_status": str(persisted_audio_block.get("special_block_status", "") or ""),
                "audio_file_name": audio_file_name,
                "audio_duration_seconds": duration_seconds,
                "can_play": audio_blocks_service.audio_can_play(persisted_audio_block),
                "is_current": speech_block_id == current_block_id,
            }
        )
    return merged_blocks


def _resolve_audio_duration_seconds(
    audio_block: dict[str, object],
) -> float | None:
    """
    @brief      Resolve display duration for one generated Audio Block.
    @param[in]  audio_block Persisted Audio Blocks payload.
    @return     Duration in seconds, or `None` when no measurable duration exists.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.2.0
    """
    for field_name in ("audio_duration_seconds", "duration_seconds"):
        try:
            duration_seconds = float(audio_block.get(field_name))
        except (TypeError, ValueError):
            continue
        if duration_seconds >= 0.0:
            return duration_seconds
    if bool(audio_block.get("metadata_only", False)):
        try:
            pause_duration_ms = int(audio_block.get("pause_duration_ms"))
        except (TypeError, ValueError):
            pause_duration_ms = 0
        if pause_duration_ms > 0:
            return pause_duration_ms / 1000.0
    return None


def _source_chunks_are_resolvable(project_root: Path, manifest: dict[str, object]) -> bool:
    """
    @brief      Determine whether Speech Blocks source chunks can be resolved quietly.
    @param[in]  project_root Active project root.
    @param[in]  manifest Active project manifest payload.
    @return     True when original or approved translated source chunks are available.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    selected_voice_language = character_voices_service.load_selected_voice_language(
        project_root,
        narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
    )
    original_language = narrator_definition_service.narrator_language_code(
        manifest.get("original_language", narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE)
    )
    if selected_voice_language == original_language:
        return True

    try:
        translation_document = ai_translation_service.load_translation_document(project_root)
    except ai_translation_service.TranslationDocumentError:
        return False
    if translation_document is None:
        return False
    if selected_voice_language != str(translation_document["target_language"]).strip():
        return False
    return ai_translation_service.translation_is_completed(project_root)


def _resolve_persisted_audio_file_name(audio_block: dict[str, object]) -> str:
    """
    @brief      Resolve one display file name derived from the Speech Block identifier.
    @param[in]  audio_block Persisted Audio Blocks payload.
    @return     Display file name, or an empty string when no playable audio is recorded.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.2.0
    """
    if not audio_blocks_service.audio_can_play(audio_block):
        return ""
    speech_block_id = str(audio_block.get("speech_block_id", "")).strip()
    if not speech_block_id:
        return ""
    return f"{audio_blocks_artifact_service.audio_artifact_file_stem(speech_block_id)}.wav"


def _resolve_current_block(
    merged_blocks: list[dict[str, object]],
    operation_state: dict[str, object] | None,
) -> dict[str, object] | None:
    """
    @brief      Resolve the preferred selected Audio Blocks row from current runtime state.
    @param[in]  merged_blocks Current merged Audio Blocks display payload list.
    @param[in]  operation_state Persisted Audio Blocks operation state or `None`.
    @return     Preferred current block payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    _ = operation_state
    for block in merged_blocks:
        if bool(block.get("is_current", False)):
            return block
    return None if not merged_blocks else merged_blocks[0]


def _audio_blocks_stage_status(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str:
    """
    @brief      Resolve the effective Audio Blocks stage from report and runtime state.
    @param[in]  report Persisted Audio Blocks report or `None`.
    @param[in]  operation_state Persisted Audio Blocks operation state or `None`.
    @return     Effective Audio Blocks stage token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if isinstance(operation_state, dict):
        operation_status = str(operation_state.get("status", "")).strip()
        if operation_status in {"running", "failed", "cancelled"}:
            return operation_status
    if isinstance(report, dict):
        return str(
            report.get(
                "audio_blocks_stage_status",
                audio_blocks_service.AUDIO_BLOCKS_STAGE_NOT_STARTED,
            )
        )
    return audio_blocks_service.AUDIO_BLOCKS_STAGE_NOT_STARTED


# END OF FILE
