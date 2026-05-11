#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file narrator_definition_service.py
@brief Project-local narrator-definition persistence helpers for AudioMancer.
@details Persists narrator profiles, explicit selection state, project-local
         TTS plan data, AI-generated text-only profile suggestions, and one
         per-profile sample artifact set whose JSON metadata records whether
         that sample is selected.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 3.14.0
"""

# IMPORTS

import json
from pathlib import Path
from uuid import uuid4

from audiomancer import config
from audiomancer.services import project_workspace_service, voiceweaver_runtime_service
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.operation_runtime_service import optional_string as _optional_string
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

_NARRATOR_DEFINITION_LOGGER = get_component_logger("narrator_definition")

NARRATOR_PROFILE_KIND_CUSTOM = "custom"

NARRATOR_PROFILE_ORIGIN_CUSTOM_USER = "custom_user"

NARRATOR_PROFILE_ORIGIN_AI_GENERATED = "ai_generated"

NARRATOR_PROVIDER_FAMILY_QWEN_VOICE_DESIGNER = "qwen3_tts_voice_designer_1_7b"

DEFAULT_NARRATOR_LANGUAGE = "en"
DEFAULT_PREVIEW_TEXT = (
    "The hall fell silent as the final lantern dimmed, and every step carried the weight of an unspoken decision."
)
DEFAULT_PREVIEW_TEXT_BY_LANGUAGE = {
    "en": DEFAULT_PREVIEW_TEXT,
    "ro": "Sala a amutit cand ultimul felinar s-a stins, iar fiecare pas purta greutatea unei hotarari nerostite.",
    "ja": "最後のランタンが暗くなると広間は静まり返り、一歩ごとに言葉にならない決断の重みが宿っていた。",
    "ko": "마지막 등불이 어두워지자 홀은 고요해졌고, 걸음마다 말하지 못한 결정의 무게가 실려 있었다.",
    "zh": "最后一盏灯笼暗下去时，大厅陷入寂静，每一步都承载着未出口决定的重量。",
    "de": (
        "Der Saal wurde still, als die letzte Laterne erlosch, "
        "und jeder Schritt trug das Gewicht einer unausgesprochenen Entscheidung."
    ),
    "fr": (
        "La salle devint silencieuse lorsque la derniere lanterne faiblit, "
        "et chaque pas portait le poids d'une decision tue."
    ),
    "ru": "Зал затих, когда последний фонарь померк, и каждый шаг нес тяжесть невысказанного решения.",
    "pt": (
        "O salao ficou em silencio quando a ultima lanterna se apagou, "
        "e cada passo carregava o peso de uma decisao nao dita."
    ),
    "es": (
        "El salon quedo en silencio cuando la ultima linterna se apago, "
        "y cada paso llevaba el peso de una decision no pronunciada."
    ),
    "it": (
        "La sala cadde nel silenzio quando l'ultima lanterna si affievoli, "
        "e ogni passo portava il peso di una decisione non detta."
    ),
}
_NARRATOR_LANGUAGE_LABELS = dict(config.TRANSLATION_LANGUAGE_OPTIONS)


def load_tts_plan(
    project_root: str | Path,
    discovered_models: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """
    @brief      Load or repair the persisted project-local TTS plan.
    @param[in]  project_root Active project root folder.
    @param[in]  discovered_models Optional normalized discovered-model cache.
    @return     Normalized persisted TTS plan payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.2.0
    """
    ensure_narrator_definition_files(project_root)
    manifest_payload = project_workspace_service.load_manifest(project_root)
    normalized_plan = validate_tts_plan(manifest_payload, discovered_models)
    if manifest_payload.get("voice_assignment_mode") != normalized_plan["voice_assignment_mode"]:
        manifest_payload["voice_assignment_mode"] = normalized_plan["voice_assignment_mode"]
        project_workspace_service.save_manifest(manifest_payload, project_root)
    return normalized_plan


def save_tts_plan(
    project_root: str | Path,
    plan_payload: dict[str, object],
    discovered_models: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """
    @brief      Validate and persist one project-local TTS plan payload.
    @param[in]  project_root Active project root folder.
    @param[in]  plan_payload Candidate TTS plan payload.
    @param[in]  discovered_models Optional normalized discovered-model cache.
    @return     Persisted normalized TTS plan payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.2.0
    """
    ensure_narrator_definition_files(project_root)
    normalized_plan = validate_tts_plan(plan_payload, discovered_models)
    manifest_payload = project_workspace_service.load_manifest(project_root)
    manifest_payload["voice_assignment_mode"] = normalized_plan["voice_assignment_mode"]
    project_workspace_service.save_manifest(manifest_payload, project_root)
    return normalized_plan


def validate_tts_plan(
    plan_payload: object,
    discovered_models: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """
    @brief      Normalize one persisted project-local TTS plan payload.
    @param[in]  plan_payload Candidate TTS plan payload.
    @param[in]  discovered_models Optional normalized discovered-model cache.
    @return     Normalized TTS plan payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    _ = discovered_models
    normalized_payload = dict(plan_payload) if isinstance(plan_payload, dict) else {}
    voice_assignment_mode = str(
        normalized_payload.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)
    ).strip()
    if voice_assignment_mode not in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS:
        voice_assignment_mode = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE
    return {"voice_assignment_mode": voice_assignment_mode}


def narrator_language_code(language_value: object, fallback: str = DEFAULT_NARRATOR_LANGUAGE) -> str:
    """
    @brief      Normalize one narrator language value into the VoiceWeaver language-code contract.
    @param[in]  language_value Candidate narrator language value as one code or operator-facing label.
    @param[in]  fallback Fallback language code used when the value is missing or unsupported.
    @return     Canonical narrator language code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.1.0
    """
    normalized_fallback = str(fallback or DEFAULT_NARRATOR_LANGUAGE).strip() or DEFAULT_NARRATOR_LANGUAGE
    normalized_value = str(language_value or "").strip()
    if not normalized_value:
        return normalized_fallback
    if normalized_value in _NARRATOR_LANGUAGE_LABELS:
        return normalized_value
    normalized_casefold = normalized_value.casefold()
    for language_code, language_label in _NARRATOR_LANGUAGE_LABELS.items():
        if normalized_casefold == str(language_label).casefold():
            return str(language_code)
    return normalized_fallback


def narrator_language_label(language_value: object, fallback: str = DEFAULT_NARRATOR_LANGUAGE) -> str:
    """
    @brief      Return one operator-facing narrator language label from one stored code or legacy label.
    @param[in]  language_value Candidate narrator language value.
    @param[in]  fallback Fallback language code used when the value is missing or unsupported.
    @return     Narrator language label.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    normalized_value = str(language_value or "").strip()
    if not normalized_value:
        return str(_NARRATOR_LANGUAGE_LABELS.get(narrator_language_code(fallback), _NARRATOR_LANGUAGE_LABELS["en"]))
    if normalized_value in _NARRATOR_LANGUAGE_LABELS:
        return str(_NARRATOR_LANGUAGE_LABELS[normalized_value])
    normalized_casefold = normalized_value.casefold()
    for _language_code, language_label in _NARRATOR_LANGUAGE_LABELS.items():
        if normalized_casefold == str(language_label).casefold():
            return str(language_label)
    return normalized_value


def preview_text_for_language(language_value: object) -> str:
    """
    @brief      Resolve the default narrator preview text for one selected audiobook language.
    @param[in]  language_value Candidate selected voice language.
    @return     Stable localized narrator preview text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized_language = narrator_language_code(language_value)
    return DEFAULT_PREVIEW_TEXT_BY_LANGUAGE.get(
        normalized_language,
        DEFAULT_PREVIEW_TEXT_BY_LANGUAGE[DEFAULT_NARRATOR_LANGUAGE],
    )


def apply_voice_language_to_profiles(project_root: str | Path, voice_language: object) -> str:
    """
    @brief      Apply one selected audiobook language to narrator profiles and their default preview text.
    @param[in]  project_root Active project root folder.
    @param[in]  voice_language Candidate selected audiobook voice language.
    @return     Persisted canonical voice language code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized_language = narrator_language_code(voice_language)
    localized_preview_text = preview_text_for_language(normalized_language)
    profiles = []
    for profile in load_profiles(project_root):
        previous_language = narrator_language_code(profile.get("language", DEFAULT_NARRATOR_LANGUAGE))
        profiles.append(
            _normalize_profile(
                {
                    **dict(profile),
                    "language": normalized_language,
                    "preview_text": (
                        localized_preview_text
                        if previous_language != normalized_language
                        else profile.get("preview_text", localized_preview_text)
                    ),
                }
            )
        )
    _write_json(_profiles_path(project_root), profiles)
    return normalized_language


def load_profiles(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load or repair narrator profiles for one project.
    @param[in]  project_root Active project root folder.
    @return     Ordered narrator-profile payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.8.0
    """
    profile_path = _profiles_path(project_root)
    if not profile_path.is_file():
        ensure_narrator_definition_files(project_root)
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    normalized_profiles = (
        [_normalize_profile(profile) for profile in payload if isinstance(profile, dict)]
        if isinstance(payload, list)
        else []
    )
    normalized_profiles = _repair_selected_profile_flags(normalized_profiles)
    _write_json(profile_path, normalized_profiles)
    return normalized_profiles


def load_selected_profile_state(project_root: str | Path) -> dict[str, object]:
    """
    @brief      Load or repair the selected narrator-profile state for one project.
    @param[in]  project_root Active project root folder.
    @return     Selected narrator-profile state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.4.1
    """
    ensure_narrator_definition_files(project_root)
    profiles = load_profiles(project_root)
    selection_path = _selection_path(project_root)
    payload = json.loads(selection_path.read_text(encoding="utf-8")) if selection_path.is_file() else {}
    normalized_state, normalized_profiles = _normalize_selected_state(payload, profiles)
    _write_json(_profiles_path(project_root), normalized_profiles)
    _write_json(selection_path, normalized_state)
    return normalized_state


def ensure_narrator_definition_files(project_root: str | Path) -> None:
    """
    @brief      Ensure narrator-definition files and sample folders exist for one project.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.6.0
    """
    profile_path = _profiles_path(project_root)
    if not profile_path.is_file():
        _write_json(profile_path, [])

    selection_path = _selection_path(project_root)
    if not selection_path.is_file():
        _write_json(selection_path, {"selected_profile_id": None, "selected_language": None})


def select_narrator_profile(
    project_root: str | Path,
    profile_id: str,
    selected_language: str | None = None,
) -> dict[str, object]:
    """
    @brief      Persist the explicitly selected narrator profile and narrator language.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Selected narrator-profile identifier.
    @param[in]  selected_language Selected narrator language code or label.
    @return     Persisted selected narrator-profile state payload.
    @exception  ValueError Raised when the target profile is missing.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.4.0
    """
    normalized_profile_id = str(profile_id or "").strip()
    profiles = load_profiles(project_root)
    if not any(str(profile.get("profile_id", "")).strip() == normalized_profile_id for profile in profiles):
        raise ValueError("missing_profile")

    normalized_profiles: list[dict[str, object]] = []
    for profile in profiles:
        normalized_profiles.append(
            {
                **dict(profile),
                "is_selected": str(profile.get("profile_id", "")).strip() == normalized_profile_id,
            }
        )
    _write_json(_profiles_path(project_root), normalized_profiles)

    selected_profile = profile_by_id(project_root, normalized_profile_id)
    normalized_state = {
        "selected_profile_id": normalized_profile_id,
        "selected_language": narrator_language_code(
            selected_language or (selected_profile or {}).get("language", DEFAULT_NARRATOR_LANGUAGE)
        ),
    }
    _write_json(_selection_path(project_root), normalized_state)
    _delete_legacy_selected_narrator_sample_files(project_root)
    _set_profile_sample_selection_flags(project_root, normalized_profile_id)
    return normalized_state


def clear_narrator_selection(project_root: str | Path) -> dict[str, object]:
    """
    @brief      Clear any explicitly selected narrator profile for one project.
    @param[in]  project_root Active project root folder.
    @return     Persisted empty selected-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    profiles = [
        {
            **dict(profile),
            "is_selected": False,
        }
        for profile in load_profiles(project_root)
    ]
    _write_json(_profiles_path(project_root), profiles)
    normalized_state = {"selected_profile_id": None, "selected_language": None}
    _write_json(_selection_path(project_root), normalized_state)
    _set_profile_sample_selection_flags(project_root, None)
    return normalized_state


def validate_profile_name(
    existing_profiles: list[dict[str, object]],
    display_name: object,
    exclude_profile_id: str | None = None,
) -> str:
    """
    @brief      Validate one narrator profile display name for uniqueness and usability.
    @param[in]  existing_profiles Existing narrator-profile payload list.
    @param[in]  display_name Candidate display name.
    @param[in]  exclude_profile_id Optional profile identifier excluded from duplicate checks.
    @return     Normalized display name.
    @exception  ValueError Raised when the name is empty or duplicates an existing profile.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    normalized_name = display_profile_name(display_name)
    if not normalized_name:
        raise ValueError("empty_name")
    reserved_profile_id = str(exclude_profile_id or "").strip()
    for profile in existing_profiles:
        profile_id = str(profile.get("profile_id", "")).strip()
        if reserved_profile_id and profile_id == reserved_profile_id:
            continue
        if display_profile_name(profile).casefold() == normalized_name.casefold():
            raise ValueError("duplicate_name")
    return normalized_name


def create_custom_profile(
    project_root: str | Path,
    display_name: str,
    language: str,
    prompt_text: str,
    preview_text: str | None = None,
) -> dict[str, object]:
    """
    @brief      Create and persist one new custom narrator profile.
    @param[in]  project_root Active project root folder.
    @param[in]  display_name Validated custom profile display name.
    @param[in]  language Selected narrator language code or label.
    @param[in]  prompt_text Narrator-definition prompt text.
    @param[in]  preview_text Optional stored preview text for the new profile.
    @return     The persisted custom narrator-profile payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    profiles = load_profiles(project_root)
    custom_profile = _normalize_profile(
        {
            "profile_id": f"custom_{uuid4().hex}",
            "speaker_id": None,
            "source_model_id": None,
            "display_name": display_name,
            "language": narrator_language_code(language),
            "prompt_text": prompt_text,
            "preview_text": preview_text or DEFAULT_PREVIEW_TEXT,
            "profile_kind": NARRATOR_PROFILE_KIND_CUSTOM,
            "profile_origin": NARRATOR_PROFILE_ORIGIN_CUSTOM_USER,
            "provider_family": NARRATOR_PROVIDER_FAMILY_QWEN_VOICE_DESIGNER,
            "editable": True,
            "protected": False,
            "is_selected": False,
            "updated_at": _utc_now_iso(),
        }
    )
    profiles.append(custom_profile)
    _write_json(_profiles_path(project_root), profiles)
    return custom_profile


def append_ai_generated_profiles(
    project_root: str | Path,
    profile_payloads: list[dict[str, object]],
    generation_metadata: dict[str, object],
) -> list[dict[str, object]]:
    """
    @brief      Append editable AI-generated narrator profiles without changing selection or samples.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_payloads Validated generated narrator-profile payloads.
    @param[in]  generation_metadata Shared metadata for the AI generation run.
    @return     Persisted generated narrator-profile payload list.
    @exception  ValueError Raised when no valid generated profiles are provided.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    if not profile_payloads:
        raise ValueError("No generated narrator profiles were provided.")
    profiles = load_profiles(project_root)
    existing_names = {display_profile_name(profile).casefold() for profile in profiles}
    created_profiles: list[dict[str, object]] = []
    for profile_payload in profile_payloads:
        display_name = _unique_display_name(profile_payload.get("display_name", ""), existing_names)
        generated_profile = _normalize_profile(
            {
                "profile_id": f"ai_narrator_{uuid4().hex}",
                "speaker_id": None,
                "source_model_id": None,
                "display_name": display_name,
                "language": narrator_language_code(profile_payload.get("language", DEFAULT_NARRATOR_LANGUAGE)),
                "prompt_text": profile_payload.get("prompt_text", ""),
                "preview_text": profile_payload.get("preview_text", DEFAULT_PREVIEW_TEXT),
                "profile_kind": NARRATOR_PROFILE_KIND_CUSTOM,
                "profile_origin": NARRATOR_PROFILE_ORIGIN_AI_GENERATED,
                "provider_family": NARRATOR_PROVIDER_FAMILY_QWEN_VOICE_DESIGNER,
                "editable": True,
                "protected": False,
                "is_selected": False,
                "sample_audio_path": None,
                "sample_metadata": None,
                "generation_metadata": {
                    **dict(generation_metadata),
                    "gender": str(profile_payload.get("gender", "")).strip(),
                    "style_label": str(profile_payload.get("style_label", "")).strip(),
                },
                "updated_at": _utc_now_iso(),
            }
        )
        created_profiles.append(generated_profile)
        profiles.append(generated_profile)
        existing_names.add(display_profile_name(generated_profile).casefold())
    _write_json(_profiles_path(project_root), profiles)
    return created_profiles


def update_custom_profile(
    project_root: str | Path,
    profile_payload: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Update and persist one existing editable narrator profile.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_payload Updated narrator-profile payload.
    @return     The persisted updated narrator-profile payload.
    @exception  ValueError Raised when the profile is missing or not editable.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    profile_id = str(profile_payload.get("profile_id", "")).strip()
    profiles = load_profiles(project_root)
    updated_profile = None
    normalized_profiles: list[dict[str, object]] = []
    for profile in profiles:
        if str(profile.get("profile_id", "")).strip() != profile_id:
            normalized_profiles.append(profile)
            continue
        if not bool(profile.get("editable", False)):
            raise ValueError("readonly_profile")
        updated_profile = _normalize_profile(
            {
                **dict(profile),
                "display_name": profile_payload.get("display_name"),
                "language": narrator_language_code(profile_payload.get("language"), str(profile.get("language", ""))),
                "prompt_text": profile_payload.get("prompt_text"),
                "preview_text": profile_payload.get("preview_text"),
                "updated_at": _utc_now_iso(),
            }
        )
        normalized_profiles.append(updated_profile)
    if updated_profile is None:
        raise ValueError("missing_profile")
    _write_json(_profiles_path(project_root), normalized_profiles)
    return updated_profile


def begin_profile_edit(project_root: str | Path, profile_id: str) -> dict[str, object]:
    """
    @brief      Prepare one narrator profile for editing by clearing sample and selection state.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     Updated target profile payload.
    @exception  ValueError Raised when the profile is missing or not editable.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    target_profile = profile_by_id(project_root, profile_id)
    if target_profile is None:
        raise ValueError("missing_profile")
    if not bool(target_profile.get("editable", False)):
        raise ValueError("readonly_profile")

    delete_profile_sample(project_root, profile_id)
    if bool(target_profile.get("is_selected", False)):
        clear_narrator_selection(project_root)
    return profile_by_id(project_root, profile_id) or target_profile


def delete_profile(project_root: str | Path, profile_id: str) -> list[dict[str, object]]:
    """
    @brief      Delete one existing non-protected narrator profile and repair selection.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     Remaining narrator-profile payload list.
    @exception  ValueError Raised when the target profile is missing or protected.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    profiles = load_profiles(project_root)
    remaining_profiles: list[dict[str, object]] = []
    deleted_profile = None
    for profile in profiles:
        if str(profile.get("profile_id", "")).strip() != str(profile_id).strip():
            remaining_profiles.append(profile)
            continue
        deleted_profile = profile
    if deleted_profile is None:
        raise ValueError("missing_profile")
    if bool(deleted_profile.get("protected", False)):
        raise ValueError("protected_profile")

    delete_profile_sample(project_root, profile_id)
    _write_json(_profiles_path(project_root), _repair_selected_profile_flags(remaining_profiles))
    if bool(deleted_profile.get("is_selected", False)):
        clear_narrator_selection(project_root)
    return load_profiles(project_root)


def delete_custom_profile(project_root: str | Path, profile_id: str) -> list[dict[str, object]]:
    """
    @brief      Backward-compatible wrapper for narrator-profile deletion.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     Remaining narrator-profile payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    return delete_profile(project_root, profile_id)


def profile_by_id(
    project_root: str | Path,
    profile_id: str | None,
) -> dict[str, object] | None:
    """
    @brief      Resolve one narrator profile by identifier.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     Matching narrator-profile payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    if profile_id in (None, ""):
        return None
    normalized_profile_id = str(profile_id).strip()
    for profile in load_profiles(project_root):
        if str(profile.get("profile_id", "")).strip() == normalized_profile_id:
            return profile
    return None


def display_profile_name(profile_or_name: object) -> str:
    """
    @brief      Return one operator-facing narrator profile display name.
    @param[in]  profile_or_name Narrator-profile payload or raw display-name value.
    @return     Sanitized display name.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    if isinstance(profile_or_name, dict):
        normalized_name = str(profile_or_name.get("display_name", "")).strip()
    else:
        normalized_name = str(profile_or_name or "").strip()
    return normalized_name


def profile_generation_request(
    profile: dict[str, object],
    tts_plan: dict[str, object],
    discovered_models: list[dict[str, object]],
) -> dict[str, object]:
    """
    @brief      Resolve the current runtime generation request for one narrator profile.
    @param[in]  profile Narrator-profile payload.
    @param[in]  tts_plan Normalized project-local TTS plan payload.
    @param[in]  discovered_models Current normalized discovered runtime models.
    @return     Generation-request payload with availability flags and model ids.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.4.0
    """
    _ = tts_plan
    capability_matrix = voiceweaver_runtime_service.build_capability_matrix(discovered_models)
    language = narrator_language_code(profile.get("language", DEFAULT_NARRATOR_LANGUAGE))
    prompt_text = str(profile.get("prompt_text", "")).strip()

    if not bool(capability_matrix.get("minimum_qwen_ready", False)):
        missing_capabilities = list(capability_matrix.get("missing_qwen_capabilities", []))
        unavailable_reason = (
            "Cannot generate a sample because Qwen3 TTS minimum capabilities are missing: "
            + ", ".join(missing_capabilities)
            + "."
        )
        return _build_generation_request(False, False, unavailable_reason, language, prompt_text)

    voice_designer_model = _first_model(capability_matrix.get("qwen_voice_designer_models", []))
    if voice_designer_model is None:
        return _build_generation_request(
            False,
            False,
            "No healthy Qwen3 Voice Designer model is currently available.",
            language,
            prompt_text,
        )
    resolved_model_id = str(voice_designer_model.get("model_id", "")).strip()
    return _build_generation_request(
        True,
        True,
        "",
        language,
        prompt_text,
        generation_mode="definition",
        model_id=resolved_model_id,
        source_model_id=resolved_model_id,
        speaker_id=None,
        supported_languages=[
            str(item).strip() for item in voice_designer_model.get("supported_languages", []) if str(item).strip()
        ],
    )


def profile_sample_paths(project_root: str | Path, profile_id: str) -> tuple[Path, Path]:
    """
    @brief      Resolve the per-profile narrator sample audio and aggregate metadata paths.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     Tuple of WAV path and `audio_profiles.json` metadata path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    normalized_profile_id = str(profile_id).strip()
    profile_payload = profile_by_id(project_root, normalized_profile_id)
    if isinstance(profile_payload, dict):
        stored_relative_path = _optional_string(profile_payload.get("sample_audio_path"))
        if stored_relative_path is not None:
            stored_audio_path = Path(project_root) / stored_relative_path
            return stored_audio_path, _profiles_path(project_root)
    normalized_name = _normalized_audio_name(
        profile_payload.get("display_name", normalized_profile_id) if profile_payload else normalized_profile_id
    )
    return (
        Path(project_root) / f"audio_narator_{normalized_name}.wav",
        _profiles_path(project_root),
    )


def has_profile_sample(project_root: str | Path, profile_id: str) -> bool:
    """
    @brief      Return whether one narrator profile currently has persisted sample artifacts.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     True when the WAV exists and `audio_profiles.json` has sample metadata.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    audio_path, _metadata_path = profile_sample_paths(project_root, profile_id)
    return audio_path.is_file() and load_profile_sample_metadata(project_root, profile_id) is not None


def load_profile_sample_metadata(project_root: str | Path, profile_id: str) -> dict[str, object] | None:
    """
    @brief      Load the persisted sample metadata for one narrator profile.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     Sample metadata payload or None when missing or invalid.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    profile_payload = profile_by_id(project_root, profile_id)
    if not isinstance(profile_payload, dict):
        return None
    payload = profile_payload.get("sample_metadata")
    return dict(payload) if isinstance(payload, dict) else None


def delete_profile_sample(project_root: str | Path, profile_id: str) -> None:
    """
    @brief      Delete the persisted sample artifacts for one narrator profile.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    audio_path, _metadata_path = profile_sample_paths(project_root, profile_id)
    if audio_path.exists():
        audio_path.unlink()
    _update_profile_sample_metadata(project_root, profile_id, None, None)


def store_profile_sample(
    project_root: str | Path,
    profile: dict[str, object],
    preview_text: str,
    generation_request: dict[str, object],
    runtime_result_summary: str,
    audio_bytes: bytes,
) -> dict[str, object]:
    """
    @brief      Persist one generated narrator profile sample WAV and aggregate metadata payload.
    @param[in]  project_root Active project root folder.
    @param[in]  profile Narrator-profile payload.
    @param[in]  preview_text Text synthesized for the sample.
    @param[in]  generation_request Resolved runtime generation-request payload.
    @param[in]  runtime_result_summary Operator-facing runtime summary text.
    @param[in]  audio_bytes Downloaded WAV bytes.
    @return     Persisted sample metadata payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.6.0
    """
    ensure_narrator_definition_files(project_root)
    profile_id = str(profile.get("profile_id", "")).strip()
    delete_profile_sample(project_root, profile_id)
    audio_path, _metadata_path = profile_sample_paths(project_root, profile_id)
    selected_state = load_selected_profile_state(project_root)
    selected_profile_id = str(selected_state.get("selected_profile_id", "") or "").strip()
    metadata_payload = {
        "profile_id": profile_id,
        "is_selected": bool(selected_profile_id and selected_profile_id == profile_id),
        "display_name": display_profile_name(profile),
        "profile_kind": str(profile.get("profile_kind", "")).strip(),
        "profile_origin": str(profile.get("profile_origin", "")).strip(),
        "source_model_id": _optional_string(
            generation_request.get("source_model_id") or profile.get("source_model_id")
        ),
        "speaker_id": _optional_string(profile.get("speaker_id")),
        "generation_mode": str(generation_request.get("generation_mode", "")).strip(),
        "language": narrator_language_code(
            generation_request.get("language", profile.get("language", DEFAULT_NARRATOR_LANGUAGE))
        ),
        "prompt_text": str(profile.get("prompt_text", "")).strip(),
        "preview_text": str(preview_text).strip(),
        "generated_at": _utc_now_iso(),
        "runtime_result_summary": str(runtime_result_summary).strip(),
    }
    audio_path.write_bytes(audio_bytes)
    _update_profile_sample_metadata(
        project_root,
        profile_id,
        relative_path=str(audio_path.relative_to(Path(project_root))),
        metadata_payload=metadata_payload,
    )
    return metadata_payload


def clear_all_profile_samples(project_root: str | Path) -> None:
    """
    @brief      Delete every persisted narrator profile sample artifact from the project root.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    for child_path in Path(project_root).glob("audio_narator_*"):
        if child_path.is_file():
            child_path.unlink()
    _clear_profile_sample_metadata(project_root)


def selected_narrator_sample_paths(project_root: str | Path) -> tuple[Path, Path]:
    """
    @brief      Resolve the selected narrator profile sample audio and metadata paths.
    @param[in]  project_root Active project root folder.
    @return     Tuple of WAV path and metadata JSON path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.4.0
    """
    return (
        Path(project_root) / config.SELECTED_NARRATOR_AUDIO_FILE_NAME,
        Path(project_root) / config.SELECTED_NARRATOR_METADATA_FILE_NAME,
    )


def load_selected_narrator_sample_metadata(project_root: str | Path) -> dict[str, object] | None:
    """
    @brief      Load selected narrator sample metadata with profile-owned fallback.
    @param[in]  project_root Active project root folder.
    @return     Selected narrator sample metadata payload or None when unavailable.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    ensure_narrator_definition_files(project_root)
    _audio_path, metadata_path = selected_narrator_sample_paths(project_root)
    if metadata_path.is_file():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and str(payload.get("preview_text", "")).strip():
            return dict(payload)

    selected_state = load_selected_profile_state(project_root)
    selected_profile_id = str(selected_state.get("selected_profile_id", "") or "").strip()
    if not selected_profile_id:
        return None
    profile_metadata = load_profile_sample_metadata(project_root, selected_profile_id)
    if not isinstance(profile_metadata, dict):
        return None
    return {
        **dict(profile_metadata),
        "selected_profile_id": selected_profile_id,
        "is_selected": True,
        "role": "narrator",
    }


def clear_selected_narrator_sample(project_root: str | Path) -> None:
    """
    @brief      Clear selected-sample markers without deleting profile-owned sample audio.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.7.0
    """
    clear_selected_narrator_sample_artifacts(project_root)
    clear_narrator_selection(project_root)


def clear_selected_narrator_sample_artifacts(project_root: str | Path) -> None:
    """
    @brief      Clear selected-sample audio and metadata without clearing the selected profile.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-05
    @version    0.1.0
    """
    audio_path, metadata_path = selected_narrator_sample_paths(project_root)
    if audio_path.exists():
        audio_path.unlink()
    if metadata_path.exists():
        metadata_path.unlink()


def copy_selected_narrator_sample(project_root: str | Path, profile_id: str) -> dict[str, object] | None:
    """
    @brief      Mark one per-profile sample as the selected narrator sample.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Selected narrator-profile identifier.
    @return     Selected narrator metadata payload or None when unavailable.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.5.0
    """
    ensure_narrator_definition_files(project_root)
    normalized_profile_id = str(profile_id).strip()
    profile_audio_path, _profile_metadata_path = profile_sample_paths(project_root, normalized_profile_id)
    profile_metadata = load_profile_sample_metadata(project_root, profile_id)
    if not profile_audio_path.is_file() or profile_metadata is None:
        clear_selected_narrator_sample_artifacts(project_root)
        return None
    select_narrator_profile(project_root, normalized_profile_id, str(profile_metadata.get("language", "")).strip())
    _delete_legacy_selected_narrator_sample_files(project_root)
    selected_metadata = {
        **dict(profile_metadata),
        "selected_profile_id": normalized_profile_id,
        "is_selected": True,
        "role": "narrator",
        "selected_at": _utc_now_iso(),
    }
    _set_profile_sample_selection_flags(project_root, normalized_profile_id)
    _update_profile_sample_metadata(
        project_root,
        normalized_profile_id,
        relative_path=str(profile_audio_path.relative_to(Path(project_root))),
        metadata_payload=selected_metadata,
    )
    selected_audio_path, selected_metadata_path = selected_narrator_sample_paths(project_root)
    selected_audio_path.write_bytes(profile_audio_path.read_bytes())
    _write_json(selected_metadata_path, selected_metadata)
    return selected_metadata


def sample_runtime_available(
    sample_metadata: dict[str, object] | None,
    discovered_models: list[dict[str, object]],
) -> bool:
    """
    @brief      Return whether a persisted sample still references a healthy discovered runtime model.
    @param[in]  sample_metadata Persisted profile sample metadata payload.
    @param[in]  discovered_models Current normalized discovered runtime models.
    @return     True when the referenced model is still reported healthy.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.2.0
    """
    if not isinstance(sample_metadata, dict):
        return False
    source_model_id = str(sample_metadata.get("source_model_id", "") or "").strip()
    if not source_model_id:
        _NARRATOR_DEFINITION_LOGGER.debug("Narrator sample runtime unavailable: missing source_model_id.")
        return False
    capability_matrix = voiceweaver_runtime_service.build_capability_matrix(discovered_models)
    healthy_models = [
        *capability_matrix.get("voice_designer_models", []),
        *capability_matrix.get("base_models", []),
    ]
    referenced_model = _model_by_id(healthy_models, source_model_id)
    if referenced_model is None:
        _NARRATOR_DEFINITION_LOGGER.debug(
            "Narrator sample runtime unavailable: source_model_id=%s not discovered.",
            source_model_id,
        )
        return False
    return True


def seeded_narrator_profiles() -> list[dict[str, object]]:
    """
    @brief      Return one detached copy of the built-in narrator profile seed list.
    @return     Seeded narrator-profile payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.1.0
    """
    return []


def _profiles_path(project_root: str | Path) -> Path:
    """
    @brief      Execute the profiles path helper.
    @param[in]  project_root Active project root folder.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return Path(project_root) / config.NARRATOR_PROFILE_FILE_NAME


def _selection_path(project_root: str | Path) -> Path:
    """
    @brief      Execute the selection path helper.
    @param[in]  project_root Active project root folder.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return Path(project_root) / config.NARRATOR_SELECTION_FILE_NAME


def _profile_audio_samples_root(project_root: str | Path) -> Path:
    """
    @brief      Execute the profile audio samples root helper.
    @param[in]  project_root Active project root folder.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return Path(project_root)


def _normalized_audio_name(value: object) -> str:
    """
    @brief      Normalize one narrator profile value for a root-level audio file name.
    @param[in]  value Candidate profile identifier or name.
    @return     Filesystem-safe lowercase token.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    normalized = "".join(character.lower() if character.isalnum() else "_" for character in str(value).strip())
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or "narator"


def _selected_audio_samples_root(project_root: str | Path) -> Path:
    """
    @brief      Resolve the selected narrator sample root as the shared narrator audio-sample folder.
    @param[in]  project_root Active project root folder.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    return _profile_audio_samples_root(project_root)


def _normalize_profile(profile: dict[str, object]) -> dict[str, object]:
    """
    @brief      Normalize the profile.
    @param[in]  profile Value for `profile`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    profile_payload = dict(profile)
    profile_kind = NARRATOR_PROFILE_KIND_CUSTOM
    profile_origin = str(profile_payload.get("profile_origin", NARRATOR_PROFILE_ORIGIN_CUSTOM_USER)).strip()
    if profile_origin not in {NARRATOR_PROFILE_ORIGIN_CUSTOM_USER, NARRATOR_PROFILE_ORIGIN_AI_GENERATED}:
        profile_origin = NARRATOR_PROFILE_ORIGIN_CUSTOM_USER
    provider_family = str(profile_payload.get("provider_family", NARRATOR_PROVIDER_FAMILY_QWEN_VOICE_DESIGNER)).strip()
    if not provider_family:
        provider_family = NARRATOR_PROVIDER_FAMILY_QWEN_VOICE_DESIGNER
    editable_default = True
    return {
        "profile_id": str(profile_payload.get("profile_id", "")).strip() or f"profile_{uuid4().hex}",
        "speaker_id": None,
        "source_model_id": _optional_string(profile_payload.get("source_model_id")),
        "display_name": display_profile_name(profile_payload.get("display_name", "")) or "Unnamed Narrator",
        "language": narrator_language_code(profile_payload.get("language", DEFAULT_NARRATOR_LANGUAGE)),
        "prompt_text": str(profile_payload.get("prompt_text", "")).strip(),
        "preview_text": str(profile_payload.get("preview_text", DEFAULT_PREVIEW_TEXT)).strip() or DEFAULT_PREVIEW_TEXT,
        "profile_kind": profile_kind,
        "profile_origin": profile_origin,
        "provider_family": provider_family,
        "editable": bool(profile_payload.get("editable", editable_default)),
        "protected": False,
        "is_selected": bool(profile_payload.get("is_selected", False)),
        "sample_audio_path": _optional_string(profile_payload.get("sample_audio_path")),
        "sample_metadata": (
            dict(profile_payload.get("sample_metadata"))
            if isinstance(profile_payload.get("sample_metadata"), dict)
            else None
        ),
        "generation_metadata": (
            dict(profile_payload.get("generation_metadata"))
            if isinstance(profile_payload.get("generation_metadata"), dict)
            else None
        ),
        "updated_at": (
            None if profile_payload.get("updated_at") in (None, "") else str(profile_payload.get("updated_at"))
        ),
    }


def _unique_display_name(display_name: object, existing_names: set[str]) -> str:
    """
    @brief      Build one unique narrator display name using numeric suffixes.
    @param[in]  display_name Candidate display name.
    @param[in]  existing_names Case-folded names already present in the project.
    @return     Unique non-empty display name.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    base_name = display_profile_name(display_name) or "AI Narrator"
    candidate_name = base_name
    suffix_index = 2
    while candidate_name.casefold() in existing_names:
        candidate_name = f"{base_name} ({suffix_index})"
        suffix_index += 1
    return candidate_name


def _update_profile_sample_metadata(
    project_root: str | Path,
    profile_id: str,
    relative_path: str | None,
    metadata_payload: dict[str, object] | None,
) -> None:
    """
    @brief      Store or clear one narrator profile sample metadata entry in `audio_profiles.json`.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @param[in]  relative_path Project-relative sample WAV path or `None`.
    @param[in]  metadata_payload Sample metadata payload or `None` to clear it.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    normalized_profile_id = str(profile_id or "").strip()
    profiles = load_profiles(project_root)
    updated_profiles: list[dict[str, object]] = []
    for profile in profiles:
        if str(profile.get("profile_id", "")).strip() != normalized_profile_id:
            updated_profiles.append(profile)
            continue
        updated_profiles.append(
            {
                **dict(profile),
                "sample_audio_path": relative_path,
                "sample_metadata": None if metadata_payload is None else dict(metadata_payload),
            }
        )
    _write_json(_profiles_path(project_root), updated_profiles)


def _clear_profile_sample_metadata(project_root: str | Path) -> None:
    """
    @brief      Clear every narrator profile sample metadata entry from `audio_profiles.json`.
    @param[in]  project_root Active project root folder.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    profiles = [
        {
            **dict(profile),
            "sample_audio_path": None,
            "sample_metadata": None,
        }
        for profile in load_profiles(project_root)
    ]
    _write_json(_profiles_path(project_root), profiles)


def _set_profile_sample_selection_flags(project_root: str | Path, selected_profile_id: str | None) -> None:
    """
    @brief      Update narrator sample metadata selection markers in-place.
    @param[in]  project_root Active project root folder.
    @param[in]  selected_profile_id Selected profile identifier, or None to clear all sample selections.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    normalized_selected_profile_id = str(selected_profile_id or "").strip()
    profiles = []
    for profile in load_profiles(project_root):
        payload = profile.get("sample_metadata")
        if not isinstance(payload, dict):
            profiles.append(profile)
            continue
        profile_id = str(payload.get("profile_id", profile.get("profile_id", "")) or "").strip()
        is_selected = bool(normalized_selected_profile_id and profile_id == normalized_selected_profile_id)
        updated_payload = {
            **dict(payload),
            "is_selected": is_selected,
        }
        if not is_selected:
            updated_payload.pop("role", None)
            updated_payload.pop("selected_at", None)
            updated_payload.pop("selected_profile_id", None)
            updated_payload.pop("copied_at", None)
        profiles.append({**dict(profile), "sample_metadata": updated_payload})
    _write_json(_profiles_path(project_root), profiles)


def _delete_legacy_selected_narrator_sample_files(project_root: str | Path) -> None:
    """
    @brief      Delete legacy duplicate selected narrator sample files when present.
    @param[in]  project_root Active project root folder.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    _ = project_root


def _normalize_selected_state(
    payload: object,
    profiles: list[dict[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """
    @brief      Normalize the selected state.
    @param[in]  payload Optional payload processed by the helper.
    @param[in]  profiles Value for `profiles`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    selected_profiles = [profile for profile in profiles if bool(profile.get("is_selected", False))]
    if len(selected_profiles) > 1:
        profiles = _repair_selected_profile_flags(profiles)
        selected_profiles = [profile for profile in profiles if bool(profile.get("is_selected", False))]

    selected_profile = selected_profiles[0] if selected_profiles else None
    normalized_payload = dict(payload) if isinstance(payload, dict) else {}
    fallback_selected_profile_id = str(normalized_payload.get("selected_profile_id", "") or "").strip()
    if selected_profile is None and fallback_selected_profile_id:
        profiles = [
            {
                **dict(profile),
                "is_selected": str(profile.get("profile_id", "")).strip() == fallback_selected_profile_id,
            }
            for profile in profiles
        ]
        selected_profile = next((profile for profile in profiles if bool(profile.get("is_selected", False))), None)

    selected_language = narrator_language_code(
        normalized_payload.get("selected_language", "")
        or (
            selected_profile.get("language", DEFAULT_NARRATOR_LANGUAGE) if isinstance(selected_profile, dict) else None
        ),
        DEFAULT_NARRATOR_LANGUAGE,
    )
    normalized_state = {
        "selected_profile_id": (
            None if selected_profile is None else str(selected_profile.get("profile_id", "")).strip()
        ),
        "selected_language": selected_language if selected_profile is not None else None,
    }
    return normalized_state, profiles


def _repair_selected_profile_flags(profiles: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Execute the repair selected profile flags helper.
    @param[in]  profiles Value for `profiles`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    first_selected_profile_id = next(
        (str(profile.get("profile_id", "")).strip() for profile in profiles if bool(profile.get("is_selected", False))),
        None,
    )
    return [
        {
            **dict(profile),
            "is_selected": first_selected_profile_id is not None
            and str(profile.get("profile_id", "")).strip() == first_selected_profile_id,
        }
        for profile in profiles
    ]


def _build_generation_request(
    runtime_available: bool,
    can_generate: bool,
    unavailable_reason: str,
    language: str,
    prompt_text: str,
    generation_mode: str | None = None,
    model_id: str | None = None,
    source_model_id: str | None = None,
    speaker_id: str | None = None,
    supported_languages: list[str] | None = None,
) -> dict[str, object]:
    """
    @brief      Build the generation request.
    @param[in]  runtime_available Value for `runtime_available`.
    @param[in]  can_generate Boolean flag for `can_generate`.
    @param[in]  unavailable_reason Value for `unavailable_reason`.
    @param[in]  language Language code.
    @param[in]  prompt_text Text value for `prompt_text`.
    @param[in]  generation_mode Value for `generation_mode`.
    @param[in]  model_id Identifier for `model_id`.
    @param[in]  source_model_id Identifier for `source_model_id`.
    @param[in]  speaker_id Identifier for `speaker_id`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    return {
        "runtime_available": runtime_available,
        "can_generate": can_generate,
        "unavailable_reason": unavailable_reason,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "source_model_id": source_model_id,
        "speaker_id": speaker_id,
        "supported_languages": [] if supported_languages is None else list(supported_languages),
        "language": language,
        "prompt_text": prompt_text,
    }


def _model_by_id(model_entries: list[dict[str, object]], model_id: str) -> dict[str, object] | None:
    """
    @brief      Execute the model by id helper.
    @param[in]  model_entries Value for `model_entries`.
    @param[in]  model_id Identifier for `model_id`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_model_id = str(model_id or "").strip()
    if not normalized_model_id:
        return None
    for model_entry in model_entries:
        if str(model_entry.get("model_id", "")).strip() == normalized_model_id:
            return model_entry
    return None


def _first_model(model_entries: list[dict[str, object]]) -> dict[str, object] | None:
    """
    @brief      Return the first model.
    @param[in]  model_entries Value for `model_entries`.
    @return     Resolved helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return None if not model_entries else dict(model_entries[0])


def _write_json(path: Path, payload: object) -> None:
    """
    @brief      Write the json.
    @param[in]  path Value for `path`.
    @param[in]  payload Optional payload processed by the helper.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# END OF FILE
