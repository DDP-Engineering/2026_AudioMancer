#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file character_voices_state_service.py
@brief Character Voices page state helpers for AudioMancer.
@details Builds Character Voices page state from persisted narrator selection,
         character-discovery artifacts, translation approval state, character-
         voices targets, and cached VoiceWeaver runtime discovery data.
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    character_discovery_service,
    character_voices_service,
    home_presenter_service,
    narrator_definition_service,
    ui_state_service,
    voiceweaver_runtime_service,
)


def build_character_voices_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
    inspected_target_id: str | None = None,
    initialize_defaults: bool = False,
) -> dict[str, object]:
    """
    @brief      Build the full Character Voices page state from project-local artifacts.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Optional persisted application settings payload.
    @param[in]  inspected_target_id Optional currently inspected character-voices target identifier.
    @param[in]  initialize_defaults True when opening the page may create default voice target metadata.
    @return     Page-state payload consumed by the Character Voices page.
    @exception  None
    """
    if project_root is None or manifest is None:
        return {
            "targets": [],
            "notes": [ui_state_service.translate("character_voices.note_no_project", language)],
            "current_target_id": None,
            "selected_voice_language": narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
            "language_entries": [],
            "original_language": ui_state_service.translate("narator_voice.language_unknown", language),
            "translated_language": ui_state_service.translate("narator_voice.language_not_translated", language),
            "assignment_mode_label": _assignment_mode_label(config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE, language),
            "target_name": "",
            "target_kind_label": "",
            "prompt_text": "",
            "preview_text": "",
            "is_editable": False,
            "can_import_sample": False,
            "can_edit_prompt": False,
            "can_generate_sample": False,
            "preview_available": False,
            "status_lines": [ui_state_service.translate("character_voices.note_no_project", language)],
            "missing_narrator_sample": False,
        }
    if not initialize_defaults and not (Path(project_root) / config.CHARACTER_VOICES_TARGETS_FILE_NAME).is_file():
        return _empty_project_state(manifest, language)

    discovered_models = (
        settings_payload.get("tts_runtime_discovered_models", []) if isinstance(settings_payload, dict) else []
    )
    runtime_probe_succeeded = bool(
        settings_payload.get("tts_runtime_probe_succeeded", False) if isinstance(settings_payload, dict) else False
    )
    capability_matrix = voiceweaver_runtime_service.build_capability_matrix(discovered_models)
    character_profiles = character_discovery_service.load_character_profiles(project_root)
    selected_narrator_state = narrator_definition_service.load_selected_profile_state(project_root)
    selected_narrator_id = str(selected_narrator_state.get("selected_profile_id", "") or "").strip() or None
    selected_narrator_profile = narrator_definition_service.profile_by_id(project_root, selected_narrator_id)
    assignment_mode = narrator_definition_service.load_tts_plan(project_root, discovered_models)[
        "voice_assignment_mode"
    ]
    language_entries, selected_voice_language, original_language, translated_language, translation_ready = (
        _voice_language_state(project_root, manifest, language)
    )
    saved_language = character_voices_service.load_selected_voice_language(project_root, selected_voice_language)
    selectable_language_codes = [language_code for _label, language_code in language_entries]
    selected_voice_language = (
        saved_language
        if saved_language in selectable_language_codes
        else (
            selected_voice_language
            if selected_voice_language in selectable_language_codes
            else narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE
        )
    )
    try:
        character_voices_service.save_selected_voice_language(project_root, selected_voice_language)
    except (OSError, ValueError) as error:
        return _manifest_error_state(manifest, language, error)
    voice_targets = character_voices_service.sync_voice_plan(
        project_root,
        character_profiles,
        selected_narrator_profile,
        selected_voice_language,
    )
    if assignment_mode == "same_narrator":
        character_targets = [
            target
            for target in voice_targets
            if str(target.get("target_kind", "")).strip() == character_voices_service.TARGET_KIND_CHARACTER
        ]
        character_voices_service.sync_same_narrator_samples(project_root, character_targets, selected_voice_language)
        voice_targets = character_voices_service.load_voice_plan(project_root)
    target_entries = [
        _build_target_entry(
            project_root,
            target_payload,
            voice_targets,
            assignment_mode,
            selected_voice_language,
            discovered_models,
            language,
        )
        for target_payload in voice_targets
    ]
    current_target = _resolve_current_target(target_entries, inspected_target_id)
    missing_narrator_sample = (
        selected_narrator_profile is not None
        and not character_voices_service.selected_narrator_sample_exists(project_root)
    )
    notes = build_character_voices_notes(
        manifest,
        target_entries,
        assignment_mode,
        current_target,
        runtime_probe_succeeded,
        capability_matrix,
        translation_ready,
        missing_narrator_sample,
        selected_narrator_profile is not None,
        language,
    )
    return {
        "targets": target_entries,
        "notes": notes,
        "current_target_id": None if current_target is None else current_target.get("target_id"),
        "selected_voice_language": selected_voice_language,
        "language_entries": language_entries,
        "original_language": original_language,
        "translated_language": translated_language,
        "assignment_mode_label": _assignment_mode_label(assignment_mode, language),
        "target_name": "" if current_target is None else str(current_target.get("display_name", "")),
        "target_kind_label": (
            ""
            if current_target is None
            else ui_state_service.translate(
                "character_voices.target_kind_narrator"
                if str(current_target.get("target_kind", "")) == character_voices_service.TARGET_KIND_NARRATOR
                else "character_voices.target_kind_character",
                language,
            )
        ),
        "prompt_text": "" if current_target is None else str(current_target.get("prompt_text", "") or ""),
        "preview_text": (
            ""
            if current_target is None
            else str(
                current_target.get(
                    "preview_text",
                    character_voices_service.preview_text_for_language(selected_voice_language),
                )
                or ""
            )
        ),
        "is_editable": bool(current_target) and bool(current_target.get("editable", False)),
        "can_import_sample": bool(current_target) and bool(current_target.get("can_import_sample", False)),
        "can_edit_prompt": bool(current_target) and bool(current_target.get("can_edit_prompt", False)),
        "can_generate_sample": bool(current_target) and bool(current_target.get("can_generate_sample", False)),
        "preview_available": bool(current_target) and bool(current_target.get("can_preview", False)),
        "status_lines": build_status_lines(
            project_root,
            target_entries,
            assignment_mode,
            selected_voice_language,
            language,
        ),
        "missing_narrator_sample": missing_narrator_sample,
    }


def _empty_project_state(manifest: dict[str, object], language: str) -> dict[str, object]:
    """
    @brief      Build a read-only Character Voices state before page metadata is initialized.
    @param[in]  manifest Active project manifest payload.
    @param[in]  language Runtime UI language code.
    @return     Page-state payload without creating character voice metadata files.
    @exception  None
    """
    selected_voice_language = narrator_definition_service.narrator_language_code(
        manifest.get("target_language", manifest.get("selected_voice_language")),
        narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
    )
    language_label = narrator_definition_service.narrator_language_label(selected_voice_language)
    assignment_mode = str(manifest.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)).strip()
    if assignment_mode not in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS:
        assignment_mode = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE
    return {
        "targets": [],
        "notes": build_character_voices_notes(
            manifest,
            [],
            assignment_mode,
            None,
            False,
            voiceweaver_runtime_service.build_capability_matrix([]),
            False,
            False,
            False,
            language,
        ),
        "current_target_id": None,
        "selected_voice_language": selected_voice_language,
        "language_entries": [(language_label, selected_voice_language)],
        "original_language": ui_state_service.translate("narator_voice.language_unknown", language),
        "translated_language": language_label,
        "assignment_mode_label": _assignment_mode_label(assignment_mode, language),
        "target_name": "",
        "target_kind_label": "",
        "prompt_text": "",
        "preview_text": character_voices_service.preview_text_for_language(selected_voice_language),
        "is_editable": False,
        "can_import_sample": False,
        "can_edit_prompt": False,
        "can_generate_sample": False,
        "preview_available": False,
        "status_lines": [ui_state_service.translate("character_voices.note_no_characters", language)],
        "missing_narrator_sample": False,
    }


def _manifest_error_state(
    manifest: dict[str, object],
    language: str,
    error: Exception,
) -> dict[str, object]:
    """
    @brief      Build non-mutating Character Voices recovery state after a manifest failure.
    @param[in]  manifest Last validated in-memory project manifest.
    @param[in]  language Runtime UI language code.
    @param[in]  error Manifest failure surfaced to the operator.
    @return     Complete read-only page-state payload.
    @exception  None
    """
    state = _empty_project_state(manifest, language)
    state["notes"] = [str(error)]
    state["status_lines"] = [str(error)]
    return state


def build_character_voices_notes(
    manifest: dict[str, object],
    target_entries: list[dict[str, object]],
    assignment_mode: str,
    current_target: dict[str, object] | None,
    runtime_probe_succeeded: bool,
    capability_matrix: dict[str, object],
    translation_ready: bool,
    missing_narrator_sample: bool,
    narrator_selected: bool,
    language: str,
) -> list[str]:
    """
    @brief      Build operator-facing notes for the Character Voices page.
    @param[in]  manifest Active project manifest payload.
    @param[in]  target_entries Current character-voices target list.
    @param[in]  assignment_mode Current project voice-assignment mode.
    @param[in]  current_target Currently inspected character-voices target.
    @param[in]  runtime_probe_succeeded True when the VoiceWeaver probe cache is valid.
    @param[in]  capability_matrix Current normalized runtime capability matrix.
    @param[in]  translation_ready True when translation exists and every chunk is approved.
    @param[in]  missing_narrator_sample True when the selected narrator sample is missing.
    @param[in]  narrator_selected True when one narrator profile is selected.
    @param[in]  language Runtime UI language code.
    @return     Ordered Character Voices notes.
    @exception  None
    """
    if home_presenter_service.source_document_name(manifest) is None:
        return [ui_state_service.translate("character_voices.note_no_source", language)]
    notes: list[str] = []
    if not narrator_selected:
        notes.append(ui_state_service.translate("character_voices.note_no_selected_narrator", language))
    elif missing_narrator_sample:
        notes.append(ui_state_service.translate("character_voices.note_missing_narrator_sample", language))
    if not any(
        str(target.get("target_kind", "")).strip() == character_voices_service.TARGET_KIND_CHARACTER
        for target in target_entries
    ):
        notes.append(ui_state_service.translate("character_voices.note_no_characters", language))
    if assignment_mode == "same_narrator":
        notes.append(ui_state_service.translate("character_voices.note_same_narrator_mode", language))
    if not runtime_probe_succeeded:
        notes.append(ui_state_service.translate("character_voices.note_runtime_not_connected", language))
    elif assignment_mode == "narrator_and_characters":
        if not bool(capability_matrix.get("minimum_qwen_ready", False)):
            notes.append(
                ui_state_service.translate("character_voices.note_qwen_capabilities_missing", language).format(
                    missing_capabilities=", ".join(capability_matrix.get("missing_qwen_capabilities", [])),
                )
            )
        else:
            notes.append(ui_state_service.translate("character_voices.note_qwen_capabilities_ready", language))
    if not translation_ready and _translation_exists(manifest):
        notes.append(ui_state_service.translate("character_voices.note_translation_not_fully_approved", language))
    if current_target is not None:
        availability_note = str(current_target.get("availability_note", "")).strip()
        if availability_note:
            notes.append(availability_note)
    return notes


def build_status_lines(
    project_root: Path,
    target_entries: list[dict[str, object]],
    assignment_mode: str,
    selected_voice_language: str,
    language: str,
) -> list[str]:
    """
    @brief      Build the bottom status-window lines for the Character Voices page.
    @param[in]  project_root Active project root folder.
    @param[in]  target_entries Current character-voices target entries.
    @param[in]  assignment_mode Current project voice-assignment mode.
    @param[in]  selected_voice_language Current selected character-voices voice language.
    @param[in]  language Runtime UI language code.
    @return     Ordered status-window lines.
    @exception  None
    """
    target_count = len(target_entries)
    sample_count = sum(1 for target in target_entries if bool(target.get("has_sample", False)))
    lines = [
        ui_state_service.translate("character_voices.status_total_targets", language).format(target_count=target_count),
        ui_state_service.translate("character_voices.status_targets_with_samples", language).format(
            sample_count=sample_count
        ),
        ui_state_service.translate("character_voices.status_assignment_mode", language).format(
            assignment_mode=_assignment_mode_label(assignment_mode, language)
        ),
        ui_state_service.translate("character_voices.status_voice_language", language).format(
            language_label=narrator_definition_service.narrator_language_label(selected_voice_language)
        ),
        ui_state_service.translate("character_voices.status_generation_ready", language).format(
            readiness=(
                ui_state_service.translate("character_voices.readiness_ready", language)
                if character_voices_service.character_voices_is_ready(project_root, target_entries)
                else ui_state_service.translate("character_voices.readiness_not_ready", language)
            )
        ),
    ]
    return lines


def _build_target_entry(
    project_root: Path,
    target_payload: dict[str, object],
    voice_targets: list[dict[str, object]],
    assignment_mode: str,
    selected_voice_language: str,
    discovered_models: list[dict[str, object]],
    language: str,
) -> dict[str, object]:
    """
    @brief      Build the target entry.
    @param[in]  project_root Active project root folder.
    @param[in]  target_payload Payload for `target_payload`.
    @param[in]  voice_targets Already-loaded Character Voices target payloads.
    @param[in]  assignment_mode Value for `assignment_mode`.
    @param[in]  selected_voice_language Value for `selected_voice_language`.
    @param[in]  discovered_models Value for `discovered_models`.
    @param[in]  language Language code.
    @return     Derived helper result.
    """
    target_kind = str(target_payload.get("target_kind", "")).strip()
    target_id = str(target_payload.get("target_id", "")).strip()
    if target_kind == character_voices_service.TARGET_KIND_NARRATOR:
        sample_metadata = character_voices_service.selected_narrator_sample_metadata(project_root)
        has_sample = character_voices_service.selected_narrator_sample_exists(project_root)
        runtime_available = character_voices_service.sample_runtime_available(sample_metadata, discovered_models)
        availability_note = ""
        if not has_sample:
            availability_note = ui_state_service.translate("character_voices.note_missing_narrator_sample", language)
        elif not runtime_available:
            availability_note = ui_state_service.translate("character_voices.note_profile_runtime_missing", language)
        return {
            **dict(target_payload),
            "target_kind_label": ui_state_service.translate("character_voices.target_kind_narrator", language),
            "sample_status_label": ui_state_service.translate(
                "character_voices.sample_present" if has_sample else "character_voices.sample_missing",
                language,
            ),
            "voice_language": narrator_definition_service.narrator_language_code(
                None
                if not isinstance(sample_metadata, dict)
                else sample_metadata.get("voice_language", sample_metadata.get("language", selected_voice_language))
            ),
            "preview_text": (
                narrator_definition_service.DEFAULT_PREVIEW_TEXT
                if not isinstance(sample_metadata, dict)
                else str(sample_metadata.get("preview_text", narrator_definition_service.DEFAULT_PREVIEW_TEXT))
            ),
            "has_sample": has_sample,
            "runtime_available": runtime_available,
            "availability_note": availability_note,
            "editable": False,
            "can_import_sample": False,
            "can_edit_prompt": False,
            "can_generate_sample": False,
            "can_preview": has_sample,
            "sample_metadata": sample_metadata,
        }

    sample_metadata = character_voices_service.load_target_sample_metadata(project_root, target_id, voice_targets)
    has_sample = character_voices_service.has_target_sample(project_root, target_id, voice_targets)
    runtime_available = character_voices_service.sample_runtime_available(sample_metadata, discovered_models)
    generation_request = character_voices_service.voice_target_generation_request(
        target_payload,
        discovered_models,
        selected_voice_language,
    )
    availability_note = ""
    if has_sample and not runtime_available:
        availability_note = ui_state_service.translate("character_voices.note_profile_runtime_missing", language)
    elif assignment_mode == "same_narrator":
        availability_note = ui_state_service.translate("character_voices.note_same_narrator_mode", language)
    elif not bool(generation_request.get("can_generate", False)):
        availability_note = str(generation_request.get("unavailable_reason", "")).strip()
    return {
        **dict(target_payload),
        "target_kind_label": ui_state_service.translate("character_voices.target_kind_character", language),
        "sample_status_label": ui_state_service.translate(
            "character_voices.sample_present" if has_sample else "character_voices.sample_missing",
            language,
        ),
        "voice_language": selected_voice_language,
        "preview_text": character_voices_service.effective_target_preview_text(target_payload, selected_voice_language),
        "has_sample": has_sample,
        "runtime_available": runtime_available,
        "availability_note": availability_note,
        "editable": assignment_mode == "narrator_and_characters" and bool(target_payload.get("editable", False)),
        "can_import_sample": assignment_mode == "narrator_and_characters"
        and bool(target_payload.get("editable", False)),
        "can_edit_prompt": assignment_mode == "narrator_and_characters" and bool(target_payload.get("editable", False)),
        "can_generate_sample": assignment_mode == "narrator_and_characters"
        and bool(generation_request.get("can_generate", False)),
        "can_preview": has_sample,
        "sample_metadata": sample_metadata,
        "generation_request": generation_request,
    }


def _resolve_current_target(
    target_entries: list[dict[str, object]],
    inspected_target_id: str | None,
) -> dict[str, object] | None:
    """
    @brief      Resolve the current target.
    @param[in]  target_entries Value for `target_entries`.
    @param[in]  inspected_target_id Identifier for `inspected_target_id`.
    @return     Derived helper result.
    """
    normalized_inspected_target_id = str(inspected_target_id or "").strip()
    if normalized_inspected_target_id:
        for target in target_entries:
            if str(target.get("target_id", "")).strip() == normalized_inspected_target_id:
                return target
    return None if not target_entries else target_entries[0]


def _voice_language_state(
    project_root: Path,
    manifest: dict[str, object],
    language: str,
) -> tuple[list[tuple[str, str]], str, str, str, bool]:
    """
    @brief      Resolve locked character-voices language state.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  language Language code.
    @return     Helper result.
    """
    try:
        translation_document = ai_translation_service.load_translation_document(project_root)
    except ai_translation_service.TranslationDocumentError:
        translation_document = None
    original_language_code = narrator_definition_service.narrator_language_code(
        manifest.get("original_language", narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE)
    )
    original_language_label = narrator_definition_service.narrator_language_label(original_language_code)
    target_language_code = narrator_definition_service.narrator_language_code(
        manifest.get("target_language", manifest.get("selected_voice_language")),
        narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
    )
    target_language_label = narrator_definition_service.narrator_language_label(target_language_code)
    language_entries = [(target_language_label, target_language_code)]
    translated_language_label = target_language_label
    translation_ready = False
    if translation_document is not None:
        translated_language_code = str(translation_document["target_language"]).strip()
        if translated_language_code in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
            translated_language_label = narrator_definition_service.narrator_language_label(translated_language_code)
            translation_ready = ai_translation_service.translation_is_completed(project_root)
    return (
        language_entries,
        target_language_code,
        original_language_label,
        translated_language_label,
        translation_ready,
    )


def _translation_exists(manifest: dict[str, object]) -> bool:
    """
    @brief      Execute the translation exists helper.
    @param[in]  manifest Active project manifest payload.
    @return     Helper result.
    """
    current_stage = str(manifest.get("current_stage", "")).strip()
    return current_stage in {
        "translation_ready",
        "character_discovery_ready",
        "narrator_definition_ready",
        "character_voices_ready",
        "speech_blocks_ready",
        "audio_blocks_ready",
        "audio_assembly_ready",
    }


def _assignment_mode_label(assignment_mode: str, language: str) -> str:
    """
    @brief      Execute the assignment mode label helper.
    @param[in]  assignment_mode Value for `assignment_mode`.
    @param[in]  language Language code.
    @return     Helper result.
    """
    return ui_state_service.translate(
        "character_voices.assignment_same_narrator"
        if assignment_mode == "same_narrator"
        else "character_voices.assignment_narrator_and_characters",
        language,
    )


# END OF FILE
