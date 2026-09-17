#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file speech_blocks_state_service.py
@brief Speech Blocks page state helpers for AudioMancer.
@details Builds Speech Blocks page state from Character Voices language
         selection, resolved chunk sources, persisted Speech Blocks output,
         current operation state, and enabled AI profile settings.
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_state_note_service,
    ai_translation_service,
    audio_blocks_service,
    character_voices_service,
    chunking_document_service,
    home_presenter_service,
    narrator_definition_service,
    speech_blocks_service,
    tts_budget_service,
    ui_state_service,
)


def build_speech_blocks_profile_state(
    settings_payload: dict[str, object] | None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build the enabled AI-profile selector state for Speech Blocks.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  selected_profile_id Preferred profile identifier if available.
    @return     Selector entries plus one resolved selected profile id.
    @exception  None
    """
    return ai_state_note_service.build_llm_profile_selector_state(
        settings_payload,
        "default_speech_blocks_profile_id",
        selected_profile_id,
    )


def build_speech_blocks_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """
    @brief      Build the Speech Blocks page state from project artifacts.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Persisted application settings payload.
    @return     Page-state payload consumed by the Speech Blocks page.
    @exception  None
    """
    if project_root is None or manifest is None:
        return {
            "source_chunks": [],
            "speech_blocks": [],
            "notes": [ui_state_service.translate("speech_blocks.note_no_project", language)],
            "selected_profile_id": None,
            "stage_status": speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED,
            "selected_source_language": "",
            "processed_chunk_count": 0,
            "total_chunk_count": 0,
            "approved_block_count": 0,
            "total_block_count": 0,
            "voice_assignment_mode": config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
            "speaker_catalog": [],
            "content_kind_options": _content_kind_options(language),
            "can_reset": False,
            "can_approve_all": False,
            "can_resplit_selected": False,
            "selected_text_character_limit": tts_budget_service.selected_text_character_limit(settings_payload),
        }

    try:
        speech_blocks_service.load_speech_blocks_document(project_root)
        audio_blocks_service.load_audio_blocks_document(project_root)
    except speech_blocks_service.SpeechBlocksDocumentError as error:
        return _invalid_block_document_state(
            manifest,
            language,
            settings_payload,
            error,
            can_reset=True,
        )
    except audio_blocks_service.AudioBlocksDocumentError as error:
        return _invalid_block_document_state(
            manifest,
            language,
            settings_payload,
            error,
            can_reset=False,
        )

    source_chunks: list[dict[str, object]] = []
    selected_source_language = ""
    source_is_resolvable, translation_document = _source_chunks_are_resolvable(project_root, manifest)
    if source_is_resolvable:
        try:
            if translation_document is None:
                source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
            else:
                source_resolution = speech_blocks_service.resolve_source_chunks(
                    project_root,
                    manifest,
                    translation_document=translation_document,
                )
            if _resolved_source_matches_page_language(project_root, manifest, source_resolution):
                source_chunks = list(source_resolution["source_chunks"])
                selected_source_language = str(source_resolution["selected_source_language"])
        except (KeyError, TypeError, ValueError):
            pass
    source_chunk_count = len(source_chunks)
    report = speech_blocks_service.load_speech_blocks_report(project_root, source_chunk_count)
    operation_state = speech_blocks_service.load_operation_state(project_root, source_chunk_count)
    speech_blocks = _merge_audio_preview_state(project_root, speech_blocks_service.load_speech_blocks(project_root))
    selected_profile_id = _persisted_profile_id(report, operation_state)
    profile_state = build_speech_blocks_profile_state(settings_payload, selected_profile_id)
    if not selected_source_language:
        selected_source_language = _persisted_source_language(report, operation_state)

    return {
        "source_chunks": source_chunks,
        "speech_blocks": speech_blocks,
        "notes": build_speech_blocks_notes(
            manifest,
            source_chunks,
            report,
            operation_state,
            bool(profile_state["entries"]),
            language,
        ),
        "selected_profile_id": selected_profile_id or profile_state["selected_profile_id"],
        "stage_status": _speech_blocks_stage_status(report, operation_state),
        "selected_source_language": selected_source_language,
        "processed_chunk_count": 0 if report is None else int(report.get("processed_chunk_count", 0)),
        "total_chunk_count": len(source_chunks),
        "approved_block_count": 0 if report is None else int(report.get("approved_block_count", 0)),
        "total_block_count": len(speech_blocks),
        "voice_assignment_mode": speech_blocks_service.voice_assignment_mode(manifest),
        "speaker_catalog": _speaker_catalog_entries(project_root, manifest),
        "content_kind_options": _content_kind_options(language),
        "can_reset": bool(speech_blocks),
        "can_approve_all": any(not bool(block.get("approved", False)) for block in speech_blocks),
        "can_resplit_selected": bool(source_chunks),
        "selected_text_character_limit": tts_budget_service.selected_text_character_limit(settings_payload),
    }


def _invalid_block_document_state(
    manifest: dict[str, object],
    language: str,
    settings_payload: dict[str, object] | None,
    error: ValueError,
    *,
    can_reset: bool,
) -> dict[str, object]:
    """
    @brief      Build a recovery-only Speech Blocks page state for one invalid strict document.
    @param[in]  manifest Active project manifest payload.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  error Typed document failure carrying reset guidance.
    @param[in]  can_reset True when the Speech Blocks reset on this page owns the failed document.
    @return     Complete non-generatable page-state payload.
    @exception  None
    """
    profile_state = build_speech_blocks_profile_state(settings_payload)
    return {
        "source_chunks": [],
        "speech_blocks": [],
        "notes": [str(error)],
        "selected_profile_id": profile_state["selected_profile_id"],
        "stage_status": "failed",
        "selected_source_language": "",
        "processed_chunk_count": 0,
        "total_chunk_count": 0,
        "approved_block_count": 0,
        "total_block_count": 0,
        "voice_assignment_mode": speech_blocks_service.voice_assignment_mode(manifest),
        "speaker_catalog": [],
        "content_kind_options": _content_kind_options(language),
        "can_reset": can_reset,
        "can_approve_all": False,
        "can_resplit_selected": False,
        "selected_text_character_limit": tts_budget_service.selected_text_character_limit(settings_payload),
    }


def build_speech_blocks_notes(
    manifest: dict[str, object],
    source_chunks: list[dict[str, object]],
    report: dict[str, object] | None,
    operation_state: dict[str, object] | None,
    has_ai_profiles: bool,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing Speech Blocks notes for the active project.
    @param[in]  manifest Active project manifest payload.
    @param[in]  source_chunks Resolved source chunk payloads.
    @param[in]  report Persisted Speech Blocks report or `None`.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @param[in]  has_ai_profiles True when at least one enabled AI profile exists.
    @param[in]  language Runtime UI language code.
    @return     Ordered Speech Blocks notes for the page.
    @exception  None
    """
    if home_presenter_service.source_document_name(manifest) is None:
        return [ui_state_service.translate("speech_blocks.note_no_source", language)]
    if not source_chunks:
        return [ui_state_service.translate("speech_blocks.note_missing_source", language)]

    stage_status = _speech_blocks_stage_status(report, operation_state)
    processed_chunk_count = 0 if report is None else int(report.get("processed_chunk_count", 0))
    speech_block_count = 0 if report is None else int(report.get("speech_block_count", 0))
    approved_block_count = 0 if report is None else int(report.get("approved_block_count", 0))
    notes = [
        ui_state_service.translate("speech_blocks.note_summary", language).format(
            block_count=speech_block_count,
            processed_chunk_count=processed_chunk_count,
            total_chunk_count=len(source_chunks),
        )
    ]
    if speech_block_count > 0:
        notes.append(
            ui_state_service.translate("speech_blocks.note_approval_summary", language).format(
                approved_block_count=approved_block_count,
                total_block_count=speech_block_count,
            )
        )
    notes.extend(ai_state_note_service.build_token_usage_notes(report, operation_state, language))
    warning_count = 0 if report is None else int(report.get("warning_count", 0))
    if warning_count > 0:
        notes.append(
            ui_state_service.translate("speech_blocks.note_warning_summary", language).format(
                warning_count=warning_count
            )
        )
        for warning_entry in list(report.get("warnings", [])):
            if not isinstance(warning_entry, dict):
                continue
            notes.append(
                ui_state_service.translate("speech_blocks.note_warning_entry", language).format(
                    chunk_id=str(warning_entry.get("chunk_id", "")),
                    reason=str(warning_entry.get("reason", "")),
                )
            )
    skipped_chunk_ids = _skipped_chunk_ids(operation_state)
    if skipped_chunk_ids:
        notes.append(
            ui_state_service.translate("speech_blocks.note_skipped_summary", language).format(
                skipped_count=max(0, len(source_chunks) - processed_chunk_count)
            )
        )
        notes.extend(
            ui_state_service.translate("speech_blocks.note_skipped_entry", language).format(chunk_id=chunk_id)
            for chunk_id in skipped_chunk_ids
        )
    if not has_ai_profiles:
        notes.append(ui_state_service.translate("speech_blocks.note_no_profile", language))
        return notes
    if stage_status == "running":
        notes.append(
            ui_state_service.translate("speech_blocks.note_in_progress", language).format(
                progress_current=0 if operation_state is None else int(operation_state.get("progress_current", 0)),
                progress_total=len(source_chunks)
                if operation_state is None
                else int(operation_state.get("progress_total", len(source_chunks))),
            )
        )
    elif stage_status == "failed":
        notes.append(
            ui_state_service.translate("speech_blocks.note_resume", language).format(
                progress_current=0 if operation_state is None else int(operation_state.get("progress_current", 0)),
                progress_total=len(source_chunks)
                if operation_state is None
                else int(operation_state.get("progress_total", len(source_chunks))),
            )
        )
    elif (
        report is not None
        and str(report.get("speech_blocks_stage_status", "")) == speech_blocks_service.SPEECH_BLOCKS_STAGE_COMPLETED
    ):
        notes.append(ui_state_service.translate("speech_blocks.note_ready_for_audio", language))
    elif speech_block_count > 0:
        notes.append(ui_state_service.translate("speech_blocks.note_waiting_for_approval", language))
    else:
        notes.append(ui_state_service.translate("speech_blocks.note_ready", language))
    return notes


def _skipped_chunk_ids(operation_state: dict[str, object] | None) -> list[str]:
    """
    @brief      Return the source chunk identifiers the AI provider refused during generation.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @return     Ordered skipped source chunk identifiers.
    @exception  None
    """
    metadata = {} if operation_state is None else operation_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return []
    recorded = metadata.get("skipped_chunk_ids", [])
    if not isinstance(recorded, list):
        return []
    return [str(chunk_id).strip() for chunk_id in recorded if str(chunk_id).strip()]


def _merge_audio_preview_state(project_root: Path, speech_blocks: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Add selected-audio preview fields to Speech Blocks page payloads.
    @param[in]  project_root Active project root.
    @param[in]  speech_blocks Persisted Speech Blocks payload list.
    @return     Speech Blocks payloads with audio preview state flags.
    @exception  None
    """
    audio_blocks_by_id = {
        str(audio_block.get("speech_block_id", "")).strip(): audio_block
        for audio_block in audio_blocks_service.load_audio_blocks(project_root)
    }
    merged_blocks: list[dict[str, object]] = []
    for speech_block in speech_blocks:
        merged_block = dict(speech_block)
        audio_block = audio_blocks_by_id.get(str(merged_block.get("speech_block_id", "")).strip(), {})
        merged_block["audio_generated"] = bool(audio_block.get("generated", False))
        merged_block["audio_approved"] = bool(audio_block.get("approved", False))
        merged_block["audio_metadata_only"] = _is_metadata_only_speech_block(merged_block, audio_block)
        merged_block["audio_can_play"] = _audio_path_for_block(project_root, audio_block) is not None
        merged_blocks.append(merged_block)
    return merged_blocks


def _is_metadata_only_speech_block(speech_block: dict[str, object], audio_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Speech Block is represented only by metadata in Audio Blocks.
    @param[in]  speech_block Speech Blocks payload.
    @param[in]  audio_block Matching Audio Blocks payload when available.
    @return     True when no generated WAV should exist for the block.
    @exception  None
    """
    if str(speech_block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE:
        return False
    if bool(audio_block.get("metadata_only", False)):
        return True
    return str(speech_block.get("content_kind", "")).strip() in {
        speech_blocks_service.CONTENT_KIND_PAUSE,
        speech_blocks_service.CONTENT_KIND_INDICATION,
    }


def _audio_path_for_block(project_root: Path, audio_block: dict[str, object]) -> Path | None:
    """
    @brief      Resolve an existing generated audio path for one Audio Blocks payload.
    @param[in]  project_root Active project root.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @return     Existing audio file path or `None`.
    @exception  None
    """
    if not audio_blocks_service.audio_can_play(audio_block):
        return None
    relative_path = str(audio_block.get("audio_relative_path", "")).strip()
    if not relative_path:
        return None
    return project_root / relative_path


def _speech_blocks_stage_status(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str:
    """
    @brief      Resolve the effective Speech Blocks stage from report and runtime state.
    @param[in]  report Persisted Speech Blocks report or `None`.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @return     Effective Speech Blocks stage token.
    @exception  None
    """
    if isinstance(operation_state, dict):
        operation_status = str(operation_state.get("status", "")).strip()
        if operation_status in {"running", "failed"}:
            return operation_status
    if isinstance(report, dict):
        return str(
            report.get(
                "speech_blocks_stage_status",
                speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED,
            )
        )
    return speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED


def _source_chunks_are_resolvable(
    project_root: Path,
    manifest: dict[str, object],
) -> tuple[bool, dict[str, object] | None]:
    """
    @brief      Determine whether source chunks can be resolved without prerequisite errors.
    @param[in]  project_root Active project root.
    @param[in]  manifest Active project manifest payload.
    @return     Gate result and an approved translation document already loaded by the gate.
    @exception  None
    """
    if not chunking_document_service.document_path(project_root).is_file():
        return False, None
    selected_voice_language = character_voices_service.load_selected_voice_language(
        project_root,
        narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
    )
    original_language = narrator_definition_service.narrator_language_code(
        manifest.get("original_language", narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE)
    )
    if selected_voice_language == original_language:
        return True, None
    try:
        translation_document = ai_translation_service.load_translation_document(project_root)
    except ai_translation_service.TranslationDocumentError:
        return False, None
    if translation_document is None:
        return False, None
    if selected_voice_language != str(translation_document["target_language"]).strip():
        return False, None
    if str(translation_document["status"]).strip() != ai_translation_service.TRANSLATION_STATUS_COMPLETED:
        return False, None
    return True, translation_document


def _resolved_source_matches_page_language(
    project_root: Path,
    manifest: dict[str, object],
    source_resolution: dict[str, object],
) -> bool:
    """
    @brief      Confirm resolved source still satisfies the page's selected-language gate.
    @param[in]  project_root Active project root.
    @param[in]  manifest Active project manifest payload.
    @param[in]  source_resolution Source context resolved from canonical chunks.
    @return     True when the resolved original or translated source remains eligible.
    @exception  None
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
    return (
        str(source_resolution.get("source_kind", "")).strip() == "translated"
        and selected_voice_language == str(source_resolution.get("selected_source_language", "")).strip()
    )


def _persisted_profile_id(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str | None:
    """
    @brief      Resolve the persisted Speech Blocks profile identifier if available.
    @param[in]  report Persisted Speech Blocks report or `None`.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @return     Persisted profile identifier or `None`.
    @exception  None
    """
    if isinstance(report, dict):
        profile_id = report.get("ai_profile_id")
        if profile_id not in (None, ""):
            return str(profile_id)
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
        if isinstance(metadata, dict):
            profile_id = metadata.get("ai_profile_id")
            if profile_id not in (None, ""):
                return str(profile_id)
    return None


def _persisted_source_language(report: dict[str, object] | None, operation_state: dict[str, object] | None) -> str:
    """
    @brief      Resolve the persisted Speech Blocks source language when available.
    @param[in]  report Persisted Speech Blocks report or `None`.
    @param[in]  operation_state Persisted Speech Blocks operation state or `None`.
    @return     Persisted source language code or one empty string.
    @exception  None
    """
    if isinstance(report, dict):
        source_language = str(report.get("source_language", "")).strip()
        if source_language:
            return source_language
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
        if isinstance(metadata, dict):
            source_language = str(metadata.get("source_language", "")).strip()
            if source_language:
                return source_language
    return ""


def _speaker_catalog_entries(project_root: Path, manifest: dict[str, object]) -> list[dict[str, object]]:
    """
    @brief      Build speaker selector entries for the current voice-assignment mode.
    @param[in]  project_root Active project root.
    @param[in]  manifest Active project manifest payload.
    @return     Ordered speaker selector entries.
    @exception  None
    """
    speaker_entries = speech_blocks_service.speaker_catalog_entries(project_root)
    if speech_blocks_service.voice_assignment_mode(manifest) != "same_narrator":
        return speaker_entries
    return [
        entry
        for entry in speaker_entries
        if str(entry.get("speaker_id", "")).strip() == speech_blocks_service.SPEAKER_KIND_NARRATOR
    ]


def _content_kind_options(language: str) -> list[tuple[str, str]]:
    """
    @brief      Build localized Speech Blocks content-kind selector options.
    @param[in]  language Runtime UI language code.
    @return     Ordered content-kind value/label pairs.
    @exception  None
    """
    return [
        (
            speech_blocks_service.CONTENT_KIND_NARRATION,
            ui_state_service.translate("speech_blocks.content_narration", language),
        ),
        (
            speech_blocks_service.CONTENT_KIND_DIALOGUE,
            ui_state_service.translate("speech_blocks.content_dialogue", language),
        ),
        (
            speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
            ui_state_service.translate("speech_blocks.content_scene_ambience", language),
        ),
        (
            speech_blocks_service.CONTENT_KIND_PAUSE,
            ui_state_service.translate("speech_blocks.content_pause", language),
        ),
        (
            speech_blocks_service.CONTENT_KIND_INDICATION,
            ui_state_service.translate("speech_blocks.content_indication", language),
        ),
    ]


# END OF FILE
