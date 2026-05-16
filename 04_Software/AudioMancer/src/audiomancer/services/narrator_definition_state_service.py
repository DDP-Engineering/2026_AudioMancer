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
         persisted narrator artifacts, narrator-generation AI profile settings,
         per-profile sample state, and the cached VoiceWeaver runtime discovery data.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 3.14.2
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    character_voices_service,
    cleanup_metadata_service,
    deterministic_chunking_service,
    deterministic_cleanup_service,
    home_presenter_service,
    narrator_definition_service,
    tts_budget_service,
    ui_state_service,
    voiceweaver_runtime_service,
)


def build_narrator_profile_generation_profile_state(
    settings_payload: dict[str, object] | None,
    project_root: Path | None = None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build the AI-profile selector state for narrator profile generation.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  project_root Optional active project root used to gate generation readiness.
    @param[in]  selected_profile_id Preferred profile identifier if available.
    @return     Selector entries, selected profile id, and source-text readiness flag.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    if not isinstance(settings_payload, dict):
        return {"entries": [], "selected_profile_id": None, "can_generate_profiles": False}
    raw_profiles = settings_payload.get("llm_profiles", [])
    if not isinstance(raw_profiles, list):
        return {"entries": [], "selected_profile_id": None, "can_generate_profiles": False}
    entries: list[tuple[str, str | None]] = []
    enabled_ids: list[str] = []
    for profile in raw_profiles:
        if not isinstance(profile, dict) or not bool(profile.get("enabled", True)):
            continue
        profile_id = str(profile.get("id", "")).strip()
        if not profile_id:
            continue
        entries.append((str(profile.get("label", "")).strip() or profile_id, profile_id))
        enabled_ids.append(profile_id)
    default_profile_id = settings_payload.get("default_narrator_profile_generation_profile_id")
    resolved_selected_id = (
        selected_profile_id
        if selected_profile_id in enabled_ids
        else (
            str(default_profile_id) if default_profile_id in enabled_ids else (enabled_ids[0] if enabled_ids else None)
        )
    )
    return {
        "entries": entries,
        "selected_profile_id": resolved_selected_id,
        "can_generate_profiles": bool(entries) and _has_narrator_generation_source_text(project_root),
    }


def build_narrator_definition_state(
    project_root: Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings_payload: dict[str, object] | None = None,
    inspected_profile_id: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build the full Narator Voice page state from project-local artifacts.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  language Runtime UI language code.
    @param[in]  settings_payload Optional persisted application settings payload.
    @param[in]  inspected_profile_id Optional currently inspected narrator-profile identifier.
    @return     Page-state payload consumed by the Narator Voice page.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    2.3.0
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
            "profile_name": "",
            "prompt_text": "",
            "preview_text": narrator_definition_service.DEFAULT_PREVIEW_TEXT,
            "preview_text_character_limit": preview_text_character_limit,
            "is_editable": False,
            "can_edit": False,
            "can_delete": False,
            "can_generate": False,
            "can_select": False,
            "preview_available": False,
            "status_lines": [ui_state_service.translate("narator_voice.note_no_project", language)],
        }
    if not (Path(project_root) / config.NARRATOR_PROFILE_FILE_NAME).is_file():
        narrator_definition_service.ensure_narrator_definition_files(project_root)

    discovered_models = (
        settings_payload.get("tts_runtime_discovered_models", []) if isinstance(settings_payload, dict) else []
    )
    preview_budget = tts_budget_service.resolve_cached_tts_budget(discovered_models)
    preview_safe_word_limit = tts_budget_service.estimated_safe_word_count(preview_budget)
    runtime_probe_succeeded = bool(
        settings_payload.get("tts_runtime_probe_succeeded", False) if isinstance(settings_payload, dict) else False
    )
    capability_matrix = voice_capability_matrix(discovered_models)
    profiles = narrator_definition_service.load_profiles(project_root)
    tts_plan = narrator_definition_service.load_tts_plan(project_root, discovered_models)
    selected_state = narrator_definition_service.load_selected_profile_state(project_root)
    selected_profile_id = str(selected_state.get("selected_profile_id", "") or "").strip() or None
    selectable_language_codes, selected_voice_language = _voice_language_state(project_root, manifest)
    saved_language = character_voices_service.load_selected_voice_language(project_root, selected_voice_language)
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
        "preview_text_safe_word_limit": preview_safe_word_limit,
        "is_editable": bool(current_profile) and bool(current_profile.get("editable", False)),
        "can_edit": bool(current_profile) and bool(current_profile.get("editable", False)),
        "can_delete": bool(current_profile),
        "can_generate": bool(current_profile) and bool(current_profile.get("can_generate", False)),
        "can_select": bool(current_profile) and bool(current_profile.get("can_select", False)),
        "preview_available": bool(current_profile) and bool(current_profile.get("has_sample", False)),
        "status_lines": build_status_lines(
            profile_entries,
            notes,
            capability_matrix,
            language,
            runtime_probe_succeeded,
            settings_payload,
            current_profile,
            preview_safe_word_limit,
        ),
    }


def _preview_text_character_limit(settings_payload: dict[str, object] | None) -> int:
    """
    @brief      Resolve the configured TTS preview text character limit.
    @param[in]  settings_payload Optional persisted application settings payload.
    @return     Positive preview text character limit.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.4.0
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
                profile_kind=ui_state_service.translate("narator_voice.profile_kind_custom", language),
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
    runtime_probe_succeeded: bool = False,
    settings_payload: dict[str, object] | None = None,
    current_profile: dict[str, object] | None = None,
    preview_safe_word_limit: int = 0,
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
    @version    1.3.0
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
    active_model_id = _active_model_id_from_settings(settings_payload)
    preview_word_count = (
        tts_budget_service.estimated_word_count(str(current_profile.get("preview_text", "")))
        if isinstance(current_profile, dict)
        else 0
    )
    lines = [
        ui_state_service.translate("narator_voice.status_profile_count", language).format(profile_count=len(profiles)),
        ui_state_service.translate("narator_voice.status_sample_count", language).format(sample_count=sample_count),
        ui_state_service.translate("narator_voice.status_selected_count", language).format(
            selected_count=selected_count,
        ),
        ui_state_service.translate(
            "narator_voice.status_runtime_connected"
            if runtime_probe_succeeded
            else "narator_voice.status_runtime_not_connected",
            language,
        ),
        ui_state_service.translate(
            "narator_voice.status_active_model" if active_model_id else "narator_voice.status_active_model_none",
            language,
        ).format(model_id=active_model_id or ""),
        ui_state_service.translate("narator_voice.status_preview_budget", language).format(
            word_count=preview_word_count,
            safe_word_count=max(0, int(preview_safe_word_limit)),
        ),
        qwen_status,
    ]
    lines.extend(note for note in notes if note.strip())
    return lines


def _active_model_id_from_settings(settings_payload: dict[str, object] | None) -> str:
    """
    @brief      Resolve the cached VoiceWeaver active model identifier from settings.
    @param[in]  settings_payload Current application settings payload.
    @return     Active model identifier or an empty string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    if not isinstance(settings_payload, dict):
        return ""
    for field_name in ("tts_runtime_active_model_id", "active_model_id"):
        active_model_id = str(settings_payload.get(field_name, "") or "").strip()
        if active_model_id:
            return active_model_id
    status_payload = settings_payload.get("tts_runtime_status")
    if not isinstance(status_payload, dict):
        return ""
    active_model_payload = status_payload.get("active_model")
    if isinstance(active_model_payload, dict):
        return str(active_model_payload.get("model_id", "") or "").strip()
    return str(active_model_payload or "").strip()


def _has_narrator_generation_source_text(project_root: Path | None) -> bool:
    """
    @brief      Return whether text exists for AI narrator profile generation.
    @param[in]  project_root Optional active project root.
    @return     True when translation, chunking, metadata, or cleaned text can be analyzed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    if project_root is None:
        return False
    if deterministic_chunking_service.load_chunks(project_root):
        return True
    translated_report = ai_translation_service.load_translation_report(project_root)
    if isinstance(translated_report, dict) and int(translated_report.get("approved_chunk_count", 0) or 0) > 0:
        return True
    cleanup_metadata = cleanup_metadata_service.load_cleanup_metadata(project_root)
    if isinstance(cleanup_metadata, dict) and cleanup_metadata.get("paragraphs"):
        return True
    cleaned_path = Path(project_root) / config.CLEANED_TEXT_FILE_NAME
    try:
        return cleaned_path.is_file() and bool(cleaned_path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


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
        "profile_kind_label": ui_state_service.translate("narator_voice.profile_kind_custom", language),
        "selected_label": ui_state_service.translate("narator_voice.list_selected", language),
        "is_selected": is_selected,
        "has_sample": has_sample,
        "runtime_available": runtime_available,
        "can_generate": True,
        "can_select": not is_selected,
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


def _voice_language_state(project_root: Path, manifest: dict[str, object]) -> tuple[list[str], str]:
    """
    @brief      Resolve locked audiobook voice-language codes for narrator operations.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @return     Selectable language codes and selected code.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.4.0
    """
    translation_report = ai_translation_service.load_translation_report(project_root)
    original_language_code = narrator_definition_service.narrator_language_code(
        _resolved_original_language_code(project_root, manifest),
        narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
    )
    selected_language_code = narrator_definition_service.narrator_language_code(
        manifest.get("selected_voice_language"),
        original_language_code,
    )
    selectable_codes = [original_language_code]
    if isinstance(translation_report, dict):
        translated_language_code = str(translation_report.get("target_language", "")).strip()
        translated_total_count = int(translation_report.get("total_chunk_count", 0))
        translated_approved_count = int(translation_report.get("approved_chunk_count", 0))
        if translated_language_code in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
            translation_ready = translated_total_count > 0 and translated_total_count == translated_approved_count
            if translation_ready and translated_language_code != original_language_code:
                selectable_codes.append(translated_language_code)
    if selected_language_code not in selectable_codes:
        selected_language_code = original_language_code
    return selectable_codes, selected_language_code


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
