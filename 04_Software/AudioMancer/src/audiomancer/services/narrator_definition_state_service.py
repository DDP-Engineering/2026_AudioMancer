#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file narrator_definition_state_service.py
@brief Narator Voice page state helpers for AudioMancer.
@details Builds project-local Narator Voice page state from manifest summary fields,
         persisted narrator artifacts, per-profile sample state, and the cached
         VoiceWeaver runtime discovery data.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 3.9.0
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    character_voices_service,
    deterministic_cleanup_service,
    home_presenter_service,
    narrator_definition_service,
    ui_state_service,
    voiceweaver_runtime_service,
)


def build_narrator_definition_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
    inspected_profile_id: str | None = None,
    initialize_defaults: bool = False,
) -> dict[str, object]:
    """
    @brief      Build the full Narator Voice page state from project-local artifacts.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Optional persisted application settings payload.
    @param[in]  inspected_profile_id Optional currently inspected narrator-profile identifier.
    @param[in]  initialize_defaults True when opening the page may create default narrator metadata.
    @return     Page-state payload consumed by the Narator Voice page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.9.0
    """
    preview_text_character_limit = _preview_text_character_limit(settings_payload)
    if project_root is None or manifest is None:
        return {
            "profiles": [],
            "notes": [ui_state_service.translate("narator_voice.note_no_project", language)],
            "current_profile_id": None,
            "selected_profile_id": None,
            "effective_language": narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
            "selected_voice_language": narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
            "language_entries": [],
            "original_language": ui_state_service.translate("narator_voice.language_unknown", language),
            "translated_language": ui_state_service.translate("narator_voice.language_not_translated", language),
            "profile_name": "",
            "prompt_text": "",
            "preview_text": narrator_definition_service.DEFAULT_PREVIEW_TEXT,
            "preview_text_character_limit": preview_text_character_limit,
            "is_editable": False,
            "is_preset": False,
            "can_edit": False,
            "can_delete": False,
            "can_generate": False,
            "can_select": False,
            "preview_available": False,
            "status_lines": [ui_state_service.translate("narator_voice.note_no_project", language)],
        }
    if not initialize_defaults and not (Path(project_root) / config.NARRATOR_PROFILE_FILE_NAME).is_file():
        return _empty_project_state(project_root, manifest, language, preview_text_character_limit)

    discovered_models = (
        settings_payload.get("tts_runtime_discovered_models", []) if isinstance(settings_payload, dict) else []
    )
    runtime_probe_succeeded = bool(
        settings_payload.get("tts_runtime_probe_succeeded", False) if isinstance(settings_payload, dict) else False
    )
    capability_matrix = voice_capability_matrix(discovered_models)
    narrator_definition_service.sync_runtime_qwen_presets(project_root, discovered_models)
    profiles = narrator_definition_service.load_profiles(project_root)
    tts_plan = narrator_definition_service.load_tts_plan(project_root, discovered_models)
    selected_state = narrator_definition_service.load_selected_profile_state(project_root)
    selected_profile_id = str(selected_state.get("selected_profile_id", "") or "").strip() or None
    language_entries, selected_voice_language, original_language, translated_language, _translation_ready = (
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
    narrator_definition_service.apply_voice_language_to_profiles(project_root, selected_voice_language)
    profiles = narrator_definition_service.load_profiles(project_root)
    original_language = _original_language_label(project_root, manifest, language)
    translated_language = narrator_definition_service.narrator_language_label(selected_voice_language)
    effective_language = selected_voice_language

    profile_entries = [
        _build_profile_entry(
            project_root,
            profile,
            selected_profile_id,
            tts_plan,
            discovered_models,
            selected_voice_language,
            language,
        )
        for profile in profiles
    ]
    current_profile = _resolve_current_profile(profile_entries, inspected_profile_id, selected_profile_id)
    notes = build_narrator_definition_notes(
        manifest,
        current_profile,
        selected_profile_id,
        language,
        runtime_probe_succeeded,
        profile_entries,
        capability_matrix,
    )

    return {
        "profiles": profile_entries,
        "notes": notes,
        "current_profile_id": None if current_profile is None else current_profile.get("profile_id"),
        "selected_profile_id": selected_profile_id,
        "effective_language": effective_language,
        "selected_voice_language": selected_voice_language,
        "language_entries": language_entries,
        "original_language": original_language,
        "translated_language": translated_language,
        "profile_name": ""
        if current_profile is None
        else narrator_definition_service.display_profile_name(current_profile),
        "prompt_text": "" if current_profile is None else str(current_profile.get("prompt_text", "")),
        "preview_text": narrator_definition_service.preview_text_for_language(selected_voice_language)
        if current_profile is None
        else str(
            current_profile.get(
                "preview_text",
                narrator_definition_service.preview_text_for_language(selected_voice_language),
            )
        ),
        "preview_text_character_limit": preview_text_character_limit,
        "is_editable": bool(current_profile) and bool(current_profile.get("editable", False)),
        "is_preset": bool(current_profile)
        and str(current_profile.get("profile_kind", "")) == narrator_definition_service.NARRATOR_PROFILE_KIND_PRESET,
        "can_edit": bool(current_profile) and bool(current_profile.get("editable", False)),
        "can_delete": bool(current_profile) and not bool(current_profile.get("protected", False)),
        "can_generate": bool(current_profile) and bool(current_profile.get("can_generate", False)),
        "can_select": bool(current_profile) and bool(current_profile.get("can_select", False)),
        "preview_available": bool(current_profile) and bool(current_profile.get("has_sample", False)),
        "status_lines": build_status_lines(profile_entries, notes, capability_matrix, language),
    }


def _empty_project_state(
    project_root: Path,
    manifest: dict[str, object],
    language: str,
    preview_text_character_limit: int,
) -> dict[str, object]:
    """
    @brief      Build a read-only Narator Voice state before page metadata is initialized.
    @param[in]  project_root Active project root.
    @param[in]  manifest Active project manifest payload.
    @param[in]  language Runtime UI language code.
    @param[in]  preview_text_character_limit Configured preview character limit.
    @return     Page-state payload without creating narrator metadata files.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    selected_voice_language = narrator_definition_service.narrator_language_code(
        manifest.get("target_language", manifest.get("selected_voice_language")),
        narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
    )
    return {
        "profiles": [],
        "notes": build_narrator_definition_notes(
            manifest,
            None,
            None,
            language,
            False,
            [],
            voiceweaver_runtime_service.build_capability_matrix([]),
        ),
        "current_profile_id": None,
        "selected_profile_id": None,
        "effective_language": selected_voice_language,
        "selected_voice_language": selected_voice_language,
        "language_entries": _voice_language_state(project_root, manifest, language)[0],
        "original_language": _original_language_label(project_root, manifest, language),
        "translated_language": narrator_definition_service.narrator_language_label(selected_voice_language),
        "profile_name": "",
        "prompt_text": "",
        "preview_text": narrator_definition_service.preview_text_for_language(selected_voice_language),
        "preview_text_character_limit": preview_text_character_limit,
        "is_editable": False,
        "is_preset": False,
        "can_edit": False,
        "can_delete": False,
        "can_generate": False,
        "can_select": False,
        "preview_available": False,
        "status_lines": [ui_state_service.translate("narator_voice.note_no_selected_profile", language)],
    }


def _preview_text_character_limit(settings_payload: dict[str, object] | None) -> int:
    """
    @brief      Resolve the configured TTS preview text character limit.
    @param[in]  settings_payload Optional persisted application settings payload.
    @return     Positive preview text character limit.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    if not isinstance(settings_payload, dict):
        return config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT
    try:
        configured_limit = int(
            settings_payload.get(
                "tts_preview_text_character_limit",
                config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT,
            )
        )
    except (TypeError, ValueError):
        return config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT
    return configured_limit if configured_limit > 0 else config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT


def build_narrator_definition_notes(
    manifest: dict[str, object],
    current_profile: dict[str, object] | None,
    selected_profile_id: str | None,
    language: str,
    runtime_probe_succeeded: bool,
    profiles: list[dict[str, object]],
    capability_matrix: dict[str, object],
) -> list[str]:
    """
    @brief      Build operator-facing notes for the Narator Voice page.
    @param[in]  manifest Active project manifest payload.
    @param[in]  current_profile Currently inspected narrator-profile payload or `None`.
    @param[in]  selected_profile_id Explicitly selected narrator-profile identifier.
    @param[in]  language Runtime UI language code.
    @param[in]  runtime_probe_succeeded True when the VoiceWeaver probe cache is valid.
    @param[in]  profiles Narrator profile list enriched with state flags.
    @param[in]  capability_matrix Current normalized runtime capability matrix.
    @return     Ordered Narator Voice page notes.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.3.1
    """
    if home_presenter_service.source_document_name(manifest) is None:
        return [ui_state_service.translate("narator_voice.note_no_source", language)]

    notes: list[str] = []
    if not runtime_probe_succeeded:
        notes.append(ui_state_service.translate("narator_voice.note_runtime_not_connected", language))
    elif not bool(capability_matrix.get("minimum_qwen_ready", False)):
        notes.append(
            ui_state_service.translate("narator_voice.note_qwen_capabilities_missing", language).format(
                missing_capabilities=", ".join(capability_matrix.get("missing_qwen_capabilities", [])),
            )
        )
    else:
        notes.append(ui_state_service.translate("narator_voice.note_qwen_capabilities_ready", language))

    current_stage = str(manifest.get("current_stage", ""))
    if current_stage not in {"character_discovery_ready", "narrator_definition_ready", "character_voices_ready"}:
        notes.append(ui_state_service.translate("narator_voice.note_upstream_not_ready", language))

    selected_profile = _profile_by_id(profiles, selected_profile_id)
    if selected_profile is None:
        notes.append(ui_state_service.translate("narator_voice.note_no_selected_profile", language))
    else:
        notes.append(
            ui_state_service.translate("narator_voice.note_selected_profile", language).format(
                profile_name=narrator_definition_service.display_profile_name(selected_profile),
                profile_kind=ui_state_service.translate(
                    "narator_voice.profile_kind_preset"
                    if str(selected_profile.get("profile_kind", ""))
                    == narrator_definition_service.NARRATOR_PROFILE_KIND_PRESET
                    else "narator_voice.profile_kind_custom",
                    language,
                ),
            )
        )
        if not bool(selected_profile.get("has_sample", False)):
            notes.append(ui_state_service.translate("narator_voice.note_selected_profile_missing_sample", language))

    if current_profile is not None:
        if not bool(current_profile.get("has_sample", False)):
            notes.append(ui_state_service.translate("narator_voice.note_generate_sample_required", language))
        availability_note = str(current_profile.get("availability_note", "")).strip()
        if availability_note:
            notes.append(availability_note)
    return notes


def build_status_lines(
    profiles: list[dict[str, object]],
    notes: list[str],
    capability_matrix: dict[str, object],
    language: str,
) -> list[str]:
    """
    @brief      Build the bottom status-window lines for the Narator Voice page.
    @param[in]  profiles Current enriched narrator profile entries.
    @param[in]  notes Operator-facing page notes.
    @param[in]  capability_matrix Current runtime capability matrix.
    @param[in]  language Runtime UI language code.
    @return     Ordered status-window lines.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    sample_count = sum(1 for profile in profiles if bool(profile.get("has_sample", False)))
    selected_count = sum(1 for profile in profiles if bool(profile.get("is_selected", False)))
    qwen_status = (
        ui_state_service.translate("narator_voice.status_qwen_ready", language)
        if bool(capability_matrix.get("minimum_qwen_ready", False))
        else ui_state_service.translate("narator_voice.status_qwen_missing", language).format(
            missing_capabilities=", ".join(capability_matrix.get("missing_qwen_capabilities", [])),
        )
    )
    lines = [
        ui_state_service.translate("narator_voice.status_profile_count", language).format(profile_count=len(profiles)),
        ui_state_service.translate("narator_voice.status_sample_count", language).format(sample_count=sample_count),
        ui_state_service.translate("narator_voice.status_selected_count", language).format(
            selected_count=selected_count,
        ),
        qwen_status,
    ]
    lines.extend(note for note in notes if note.strip())
    return lines


def voice_capability_matrix(discovered_models: list[dict[str, object]]) -> dict[str, object]:
    """
    @brief      Build the narrator-facing VoiceWeaver capability matrix wrapper.
    @param[in]  discovered_models Current normalized discovered runtime models.
    @return     Capability matrix used by narrator state shaping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    return voiceweaver_runtime_service.build_capability_matrix(discovered_models)


def _build_profile_entry(
    project_root: Path,
    profile: dict[str, object],
    selected_profile_id: str | None,
    tts_plan: dict[str, object],
    discovered_models: list[dict[str, object]],
    selected_voice_language: str,
    language: str,
) -> dict[str, object]:
    """
    @brief      Build the profile entry.
    @param[in]  project_root Active project root folder.
    @param[in]  profile Value for `profile`.
    @param[in]  selected_profile_id Selected profile identifier.
    @param[in]  tts_plan Value for `tts_plan`.
    @param[in]  discovered_models Value for `discovered_models`.
    @param[in]  selected_voice_language Current selected audiobook voice language.
    @param[in]  language Language code.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.3.0
    """
    generation_request = narrator_definition_service.profile_generation_request(
        {**dict(profile), "language": selected_voice_language},
        tts_plan,
        discovered_models,
    )
    sample_metadata = narrator_definition_service.load_profile_sample_metadata(
        project_root, str(profile.get("profile_id", ""))
    )
    has_sample = narrator_definition_service.has_profile_sample(project_root, str(profile.get("profile_id", "")))
    runtime_available = narrator_definition_service.sample_runtime_available(sample_metadata, discovered_models)
    is_selected = str(profile.get("profile_id", "")).strip() == str(selected_profile_id or "").strip()
    availability_note = ""
    if has_sample and not runtime_available:
        availability_note = ui_state_service.translate("narator_voice.note_profile_runtime_missing", language)
    elif not bool(generation_request.get("can_generate", False)):
        availability_note = str(generation_request.get("unavailable_reason", "")).strip()

    return {
        **dict(profile),
        "profile_kind_label": ui_state_service.translate(
            "narator_voice.profile_kind_preset"
            if str(profile.get("profile_kind", "")) == narrator_definition_service.NARRATOR_PROFILE_KIND_PRESET
            else "narator_voice.profile_kind_custom",
            language,
        ),
        "selected_label": ui_state_service.translate("narator_voice.list_selected", language),
        "is_selected": is_selected,
        "has_sample": has_sample,
        "runtime_available": runtime_available,
        "can_generate": bool(generation_request.get("can_generate", False)),
        "can_select": has_sample and not is_selected,
        "availability_note": availability_note,
        "sample_metadata": sample_metadata,
        "generation_request": generation_request,
    }


def _resolve_current_profile(
    profiles: list[dict[str, object]],
    inspected_profile_id: str | None,
    selected_profile_id: str | None,
) -> dict[str, object] | None:
    """
    @brief      Resolve the current profile.
    @param[in]  profiles Value for `profiles`.
    @param[in]  inspected_profile_id Identifier for `inspected_profile_id`.
    @param[in]  selected_profile_id Selected profile identifier.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    for preferred_profile_id in (inspected_profile_id, selected_profile_id):
        if preferred_profile_id:
            current_profile = _profile_by_id(profiles, preferred_profile_id)
            if current_profile is not None:
                return current_profile
    return None if not profiles else profiles[0]


def _profile_by_id(profiles: list[dict[str, object]], profile_id: str | None) -> dict[str, object] | None:
    """
    @brief      Execute the profile by id helper.
    @param[in]  profiles Value for `profiles`.
    @param[in]  profile_id Profile identifier.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_profile_id = str(profile_id or "").strip()
    if not normalized_profile_id:
        return None
    for profile in profiles:
        if str(profile.get("profile_id", "")).strip() == normalized_profile_id:
            return profile
    return None


def _original_language_label(project_root: Path, manifest: dict[str, object], language: str) -> str:
    """
    @brief      Resolve the original-language label from manifest or cleanup detection.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  language Language code.
    @return     Resolved original-language label.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    original_language = _resolved_original_language_code(project_root, manifest)
    if original_language:
        return narrator_definition_service.narrator_language_label(original_language)
    return ui_state_service.translate("narator_voice.language_unknown", language)


def _translated_language_label(project_root: Path, language: str) -> str:
    """
    @brief      Execute the translated language label helper.
    @param[in]  project_root Active project root folder.
    @param[in]  language Language code.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    translation_report = ai_translation_service.load_translation_report(project_root)
    if not isinstance(translation_report, dict):
        return ui_state_service.translate("narator_voice.language_not_translated", language)
    target_language = str(translation_report.get("target_language", "")).strip()
    if target_language in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
        return narrator_definition_service.narrator_language_label(target_language)
    return ui_state_service.translate("narator_voice.language_not_translated", language)


def _effective_narration_language(project_root: Path, manifest: dict[str, object]) -> str:
    """
    @brief      Resolve the effective narrator language from translation or source-language data.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @return     Effective narrator language code.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    translation_report = ai_translation_service.load_translation_report(project_root)
    if isinstance(translation_report, dict):
        target_language = str(translation_report.get("target_language", "")).strip()
        if target_language in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
            return narrator_definition_service.narrator_language_code(target_language)
    original_language = _resolved_original_language_code(project_root, manifest)
    normalized_original_language = str(original_language or "").strip()
    if not normalized_original_language:
        return narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE
    if normalized_original_language in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
        return normalized_original_language
    resolved_language_code = narrator_definition_service.narrator_language_code(normalized_original_language, "")
    if resolved_language_code:
        return resolved_language_code
    return normalized_original_language.casefold()


def _voice_language_state(
    project_root: Path,
    manifest: dict[str, object],
    language: str,
) -> tuple[list[tuple[str, str]], str, str, str, bool]:
    """
    @brief      Resolve locked audiobook voice-language state for the Narator Voice page.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  language Runtime UI language code.
    @return     Language entries, selected code, original label, target label, and translation-ready flag.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    translation_report = ai_translation_service.load_translation_report(project_root)
    original_language_code = narrator_definition_service.narrator_language_code(
        _resolved_original_language_code(project_root, manifest),
        narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
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
    if isinstance(translation_report, dict):
        translated_language_code = str(translation_report.get("target_language", "")).strip()
        translated_total_count = int(translation_report.get("total_chunk_count", 0))
        translated_approved_count = int(translation_report.get("approved_chunk_count", 0))
        if translated_language_code in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
            translated_language_label = narrator_definition_service.narrator_language_label(translated_language_code)
            translation_ready = translated_total_count > 0 and translated_total_count == translated_approved_count
    return (
        language_entries,
        target_language_code,
        original_language_label,
        translated_language_label,
        translation_ready,
    )


def _resolved_original_language_code(project_root: Path, manifest: dict[str, object]) -> str:
    """
    @brief      Resolve the original-language code from manifest and cleanup artifacts.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @return     Source-language code when available, else an empty string.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    original_language = str(manifest.get("original_language", "") or "").strip()
    if original_language:
        return original_language
    cleanup_report = deterministic_cleanup_service.load_cleanup_report(project_root)
    if isinstance(cleanup_report, dict):
        return str(cleanup_report.get("detected_language", "") or "").strip()
    return ""


# END OF FILE
