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
@details Owns the strict authoritative Narrator Voice document, explicit
         profile selection, canonical per-profile WAV samples, project-local
         TTS plan data, and derived selected-sample views.
"""

# IMPORTS

from contextlib import suppress
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from audiomancer import config
from audiomancer.services import project_workspace_service, voice_sample_import_service, voiceweaver_runtime_service
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.operation_runtime_service import optional_string as _optional_string
from audiomancer.services.persistence_service import write_json_atomic

# CONSTANTS

_NARRATOR_DEFINITION_LOGGER = get_component_logger("narrator_definition")

NARRATOR_SAMPLE_SOURCE_VOICE_DESIGNER = "voice_designer"
NARRATOR_SAMPLE_SOURCE_IMPORTED = "imported"

NARRATOR_VOICE_STATUS_NOT_STARTED = "not_started"
NARRATOR_VOICE_STATUS_RUNNING = "running"
NARRATOR_VOICE_STATUS_CANCELLED = "cancelled"
NARRATOR_VOICE_STATUS_FAILED = "failed"
NARRATOR_VOICE_STATUS_COMPLETED = "completed"

_NARRATOR_VOICE_ROOT_FIELDS = {
    "status",
    "token_usage",
    "budget_metadata",
    "additional_profile_instructions",
    "selected_profile_id",
    "profiles",
    "resume",
}
_NARRATOR_VOICE_PROFILE_FIELDS = {
    "profile_id",
    "display_name",
    "language",
    "prompt_text",
    "preview_text",
    "sample",
}
_NARRATOR_VOICE_SAMPLE_FIELDS = {
    "source_kind",
    "preview_text",
    "language",
    "source_model_id",
}
_NARRATOR_VOICE_RESUME_FIELDS = {
    "resume_fingerprint",
    "requested_count",
    "gender_allocation",
    "completed_window_count",
    "total_window_count",
    "style_observations",
}
_NARRATOR_VOICE_GENDER_FIELDS = {"male", "female", "random", "random_gender"}
_NARRATOR_VOICE_STATUSES = {
    NARRATOR_VOICE_STATUS_NOT_STARTED,
    NARRATOR_VOICE_STATUS_RUNNING,
    NARRATOR_VOICE_STATUS_CANCELLED,
    NARRATOR_VOICE_STATUS_FAILED,
    NARRATOR_VOICE_STATUS_COMPLETED,
}

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


class NarratorVoiceDocumentContractError(ValueError):
    """
    @brief      Report a current Narrator Voice document that violates its strict contract.
    """


def default_narrator_voice_document() -> dict[str, object]:
    """
    @brief      Build the exact default authoritative Narrator Voice document.
    @return     New mutable default document payload.
    @exception  None
    """
    return {
        "status": NARRATOR_VOICE_STATUS_NOT_STARTED,
        "token_usage": {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "usage_available": False,
        },
        "budget_metadata": {},
        "additional_profile_instructions": "",
        "selected_profile_id": None,
        "profiles": [],
        "resume": None,
    }


def load_narrator_voice_document(project_root: str | Path) -> dict[str, object]:
    """
    @brief      Load and strictly validate the authoritative Narrator Voice document.
    @param[in]  project_root Active project root folder.
    @return     Validated document payload.
    @exception  NarratorVoiceDocumentContractError Raised for unreadable or invalid current data.
    """
    document_path = _document_path(project_root)
    if not document_path.is_file():
        ensure_narrator_voice_document(project_root)
    try:
        payload = json.loads(document_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NarratorVoiceDocumentContractError(
            f"Narrator Voice data is unreadable. Reset Narrator Voice to recover: {error}"
        ) from error
    return _validate_narrator_voice_document(payload)


def write_narrator_voice_document(project_root: str | Path, document: object) -> Path:
    """
    @brief      Strictly validate and atomically write the authoritative document.
    @param[in]  project_root Active project root folder.
    @param[in]  document Candidate complete document payload.
    @return     Written `narrator_voice.json` path.
    @exception  NarratorVoiceDocumentContractError Raised when the candidate is invalid.
    """
    validated_document = _validate_narrator_voice_document(document)
    document_path = _document_path(project_root)
    write_json_atomic(document_path, validated_document)
    return document_path


def ensure_narrator_voice_document(project_root: str | Path) -> Path:
    """
    @brief      Create the exact default document only when it is absent.
    @param[in]  project_root Active project root folder.
    @return     Authoritative document path.
    @exception  NarratorVoiceDocumentContractError Raised when existing current data is invalid.
    """
    document_path = _document_path(project_root)
    if document_path.is_file():
        load_narrator_voice_document(project_root)
        return document_path
    return write_narrator_voice_document(project_root, default_narrator_voice_document())


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
    @brief      Return one operator-facing narrator language label from one stored code or label.
    @param[in]  language_value Candidate narrator language value.
    @param[in]  fallback Fallback language code used when the value is missing or unsupported.
    @return     Narrator language label.
    @exception  None
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
    """
    normalized_language = narrator_language_code(language_value)
    return DEFAULT_PREVIEW_TEXT_BY_LANGUAGE.get(
        normalized_language,
        DEFAULT_PREVIEW_TEXT_BY_LANGUAGE[DEFAULT_NARRATOR_LANGUAGE],
    )


def apply_voice_language_to_profiles(project_root: str | Path, voice_language: object) -> str:
    """
    @brief      Apply one selected audiobook language without replacing authored preview text.
    @param[in]  project_root Active project root folder.
    @param[in]  voice_language Candidate selected audiobook voice language.
    @return     Persisted canonical voice language code.
    @exception  NarratorVoiceDocumentContractError Raised when current or migrated narrator data is invalid.
    @exception  OSError Raised when changed narrator data cannot be written atomically.
    """
    normalized_language = narrator_language_code(voice_language)
    localized_preview_text = preview_text_for_language(normalized_language)
    document = load_narrator_voice_document(project_root)
    profiles = []
    for profile in document["profiles"]:
        previous_language = narrator_language_code(profile.get("language", DEFAULT_NARRATOR_LANGUAGE))
        preview_text = str(profile["preview_text"])
        if (
            previous_language != normalized_language
            and preview_text == preview_text_for_language(previous_language)
        ):
            preview_text = localized_preview_text
        profiles.append(
            {
                **dict(profile),
                "language": normalized_language,
                "preview_text": preview_text,
            }
        )
    if profiles != document["profiles"]:
        document["profiles"] = profiles
        write_narrator_voice_document(project_root, document)
    return normalized_language


def load_profiles(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load narrator profiles from the authoritative document.
    @param[in]  project_root Active project root folder.
    @return     Ordered narrator-profile payload list.
    @exception  NarratorVoiceDocumentContractError Raised for invalid current data.
    """
    return [dict(profile) for profile in load_narrator_voice_document(project_root)["profiles"]]


def load_selected_profile_state(project_root: str | Path) -> dict[str, object]:
    """
    @brief      Derive the selected narrator-profile view from the authoritative document.
    @param[in]  project_root Active project root folder.
    @return     Selected narrator-profile state payload.
    @exception  None
    """
    document = load_narrator_voice_document(project_root)
    selected_profile_id = document["selected_profile_id"]
    selected_profile = next(
        (profile for profile in document["profiles"] if profile["profile_id"] == selected_profile_id),
        None,
    )
    return {
        "selected_profile_id": selected_profile_id,
        "selected_language": None if selected_profile is None else selected_profile["language"],
    }


def ensure_narrator_definition_files(project_root: str | Path) -> None:
    """
    @brief      Ensure the authoritative Narrator Voice document exists.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    """
    ensure_narrator_voice_document(project_root)


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
    """
    _ = selected_language
    normalized_profile_id = str(profile_id or "").strip()
    document = load_narrator_voice_document(project_root)
    selected_profile = next(
        (profile for profile in document["profiles"] if profile["profile_id"] == normalized_profile_id),
        None,
    )
    if selected_profile is None:
        raise ValueError("missing_profile")
    document["selected_profile_id"] = normalized_profile_id
    write_narrator_voice_document(project_root, document)
    return {
        "selected_profile_id": normalized_profile_id,
        "selected_language": selected_profile["language"],
    }


def clear_narrator_selection(project_root: str | Path) -> dict[str, object]:
    """
    @brief      Clear any explicitly selected narrator profile for one project.
    @param[in]  project_root Active project root folder.
    @return     Persisted empty selected-state payload.
    @exception  None
    """
    document = load_narrator_voice_document(project_root)
    document["selected_profile_id"] = None
    write_narrator_voice_document(project_root, document)
    return {"selected_profile_id": None, "selected_language": None}


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
    """
    document = load_narrator_voice_document(project_root)
    profiles = list(document["profiles"])
    normalized_name = validate_profile_name(profiles, display_name)
    custom_profile = _normalize_profile(
        {
            "profile_id": f"custom_{uuid4().hex}",
            "display_name": normalized_name,
            "language": narrator_language_code(language),
            "prompt_text": prompt_text,
            "preview_text": preview_text or DEFAULT_PREVIEW_TEXT,
        }
    )
    profiles.append(custom_profile)
    document["profiles"] = profiles
    write_narrator_voice_document(project_root, document)
    return custom_profile


def append_ai_generated_profiles(
    project_root: str | Path,
    profile_payloads: list[dict[str, object]],
    generation_metadata: dict[str, object],
    *,
    persist: bool = True,
) -> list[dict[str, object]]:
    """
    @brief      Append editable AI-generated narrator profiles without changing selection or samples.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_payloads Validated generated narrator-profile payloads.
    @param[in]  generation_metadata Shared metadata for the AI generation run.
    @param[in]  persist Whether to write immediately; false lets the caller commit profiles with attempt state.
    @return     Persisted generated narrator-profile payload list.
    @exception  ValueError Raised when no valid generated profiles are provided.
    """
    _ = generation_metadata
    if not profile_payloads:
        raise ValueError("No generated narrator profiles were provided.")
    document = load_narrator_voice_document(project_root)
    profiles = list(document["profiles"])
    existing_names = {display_profile_name(profile).casefold() for profile in profiles}
    created_profiles: list[dict[str, object]] = []
    for profile_payload in profile_payloads:
        display_name = _unique_display_name(profile_payload.get("display_name", ""), existing_names)
        generated_profile = _normalize_profile(
            {
                "profile_id": f"ai_narrator_{uuid4().hex}",
                "display_name": display_name,
                "language": narrator_language_code(profile_payload.get("language", DEFAULT_NARRATOR_LANGUAGE)),
                "prompt_text": profile_payload.get("prompt_text", ""),
                "preview_text": profile_payload.get("preview_text", DEFAULT_PREVIEW_TEXT),
                "sample": None,
            }
        )
        created_profiles.append(generated_profile)
        profiles.append(generated_profile)
        existing_names.add(display_profile_name(generated_profile).casefold())
    if persist:
        document["profiles"] = profiles
        write_narrator_voice_document(project_root, document)
    return created_profiles


def update_custom_profile(
    project_root: str | Path,
    profile_payload: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Update and persist one existing narrator profile.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_payload Updated narrator-profile payload.
    @return     The persisted updated narrator-profile payload.
    @exception  ValueError Raised when the profile is missing.
    """
    profile_id = str(profile_payload.get("profile_id", "")).strip()
    document = load_narrator_voice_document(project_root)
    profiles = list(document["profiles"])
    validate_profile_name(profiles, profile_payload.get("display_name"), profile_id)
    updated_profile = None
    normalized_profiles: list[dict[str, object]] = []
    for profile in profiles:
        if str(profile.get("profile_id", "")).strip() != profile_id:
            normalized_profiles.append(profile)
            continue
        updated_profile = _normalize_profile(
            {
                **dict(profile),
                "display_name": profile_payload.get("display_name"),
                "language": narrator_language_code(profile_payload.get("language"), str(profile.get("language", ""))),
                "prompt_text": profile_payload.get("prompt_text"),
                "preview_text": profile_payload.get("preview_text"),
            }
        )
        normalized_profiles.append(updated_profile)
    if updated_profile is None:
        raise ValueError("missing_profile")
    document["profiles"] = normalized_profiles
    write_narrator_voice_document(project_root, document)
    return updated_profile


def begin_profile_edit(project_root: str | Path, profile_id: str) -> dict[str, object]:
    """
    @brief      Prepare one narrator profile for editing by clearing sample and selection state.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     Updated target profile payload.
    @exception  ValueError Raised when the profile is missing.
    """
    target_profile = profile_by_id(project_root, profile_id)
    if target_profile is None:
        raise ValueError("missing_profile")

    delete_profile_sample(project_root, profile_id)
    selected_state = load_selected_profile_state(project_root)
    if str(selected_state.get("selected_profile_id", "") or "").strip() == str(profile_id).strip():
        clear_narrator_selection(project_root)
    return profile_by_id(project_root, profile_id) or target_profile


def delete_profile(project_root: str | Path, profile_id: str) -> list[dict[str, object]]:
    """
    @brief      Delete one existing narrator profile and repair selection.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     Remaining narrator-profile payload list.
    @exception  ValueError Raised when the target profile is missing.
    """
    document = load_narrator_voice_document(project_root)
    profiles = list(document["profiles"])
    remaining_profiles: list[dict[str, object]] = []
    deleted_profile = None
    for profile in profiles:
        if str(profile.get("profile_id", "")).strip() != str(profile_id).strip():
            remaining_profiles.append(profile)
            continue
        deleted_profile = profile
    if deleted_profile is None:
        raise ValueError("missing_profile")
    audio_path = _current_profile_sample_audio_path(project_root, profile_id)
    with suppress(OSError):
        audio_path.unlink(missing_ok=True)
    document["profiles"] = remaining_profiles
    if document["selected_profile_id"] == str(profile_id).strip():
        document["selected_profile_id"] = None
    write_narrator_voice_document(project_root, document)
    return [dict(profile) for profile in remaining_profiles]


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
    @return     Tuple of canonical WAV path and `narrator_voice.json` metadata path.
    @exception  None
    """
    normalized_profile_id = str(profile_id).strip()
    return _current_profile_sample_audio_path(project_root, normalized_profile_id), _document_path(project_root)


def has_profile_sample(project_root: str | Path, profile_id: str) -> bool:
    """
    @brief      Return whether one narrator profile currently has persisted sample artifacts.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     True when the canonical WAV and current profile sample metadata exist.
    @exception  None
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
    """
    profile_payload = profile_by_id(project_root, profile_id)
    if not isinstance(profile_payload, dict):
        return None
    payload = profile_payload.get("sample")
    return dict(payload) if isinstance(payload, dict) else None


def delete_profile_sample(project_root: str | Path, profile_id: str) -> None:
    """
    @brief      Delete the persisted sample artifacts for one narrator profile.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     None.
    @exception  None
    """
    audio_path, _metadata_path = profile_sample_paths(project_root, profile_id)
    if audio_path.exists():
        audio_path.unlink()
    _update_profile_sample_metadata(project_root, profile_id, None)


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
    """
    ensure_narrator_definition_files(project_root)
    profile_id = str(profile.get("profile_id", "")).strip()
    audio_path = _current_profile_sample_audio_path(project_root, profile_id)
    metadata_payload = {
        "source_kind": NARRATOR_SAMPLE_SOURCE_VOICE_DESIGNER,
        "preview_text": str(preview_text).strip(),
        "language": narrator_language_code(
            generation_request.get("language", profile.get("language", DEFAULT_NARRATOR_LANGUAGE))
        ),
        "source_model_id": _optional_string(
            generation_request.get("source_model_id") or generation_request.get("model_id")
        ),
    }
    _ = runtime_result_summary
    _write_bytes_atomic(audio_path, audio_bytes)
    _update_profile_sample_metadata(
        project_root,
        profile_id,
        metadata_payload=metadata_payload,
    )
    return metadata_payload


def import_profile_sample(
    project_root: str | Path,
    profile: dict[str, object],
    preview_text: str,
    source_audio_path: str | Path,
) -> dict[str, object]:
    """
    @brief      Validate and persist one imported narrator profile WAV sample.
    @param[in]  project_root Active project root folder.
    @param[in]  profile Narrator-profile payload.
    @param[in]  preview_text Transcript text spoken in the imported sample.
    @param[in]  source_audio_path Operator-selected WAV file path.
    @return     Persisted imported-sample metadata payload.
    @exception  ValueError Raised when the sample path or transcript is invalid.
    """
    ensure_narrator_definition_files(project_root)
    normalized_preview_text = str(preview_text or "").strip()
    if not normalized_preview_text:
        raise ValueError("empty_preview_text")
    source_path = Path(source_audio_path)
    voice_sample_import_service.validate_imported_wav_sample(source_path)
    profile_id = str(profile.get("profile_id", "")).strip()
    audio_path = _current_profile_sample_audio_path(project_root, profile_id)
    metadata_payload = {
        "source_kind": NARRATOR_SAMPLE_SOURCE_IMPORTED,
        "preview_text": normalized_preview_text,
        "language": narrator_language_code(profile.get("language", DEFAULT_NARRATOR_LANGUAGE)),
        "source_model_id": None,
        "source_file_name": source_path.name,
    }
    _write_bytes_atomic(audio_path, source_path.read_bytes())
    _update_profile_sample_metadata(
        project_root,
        profile_id,
        metadata_payload=metadata_payload,
    )
    return metadata_payload


def selected_narrator_sample_path(project_root: str | Path) -> Path | None:
    """
    @brief      Resolve the selected profile-owned narrator sample WAV.
    @param[in]  project_root Active project root folder.
    @return     Canonical selected profile WAV path or `None` when unavailable.
    @exception  None
    """
    document = load_narrator_voice_document(project_root)
    selected_profile_id = document["selected_profile_id"]
    if selected_profile_id is None:
        return None
    selected_profile = next(
        (profile for profile in document["profiles"] if profile["profile_id"] == selected_profile_id),
        None,
    )
    if selected_profile is None or selected_profile["sample"] is None:
        return None
    return _current_profile_sample_audio_path(project_root, selected_profile_id)


def load_selected_narrator_sample_metadata(project_root: str | Path) -> dict[str, object] | None:
    """
    @brief      Derive selected narrator sample metadata from the authoritative document.
    @param[in]  project_root Active project root folder.
    @return     Selected narrator sample metadata payload or None when unavailable.
    @exception  None
    """
    document = load_narrator_voice_document(project_root)
    selected_profile_id = document["selected_profile_id"]
    if selected_profile_id is None:
        return None
    selected_profile = next(
        (profile for profile in document["profiles"] if profile["profile_id"] == selected_profile_id),
        None,
    )
    if selected_profile is None or not isinstance(selected_profile["sample"], dict):
        return None
    return {
        "profile_id": selected_profile_id,
        **dict(selected_profile["sample"]),
    }


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
    """
    if not isinstance(sample_metadata, dict):
        return False
    if _sample_metadata_is_imported(sample_metadata):
        return True
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


def _sample_metadata_is_imported(sample_metadata: dict[str, object]) -> bool:
    """
    @brief      Return whether sample metadata describes an operator-imported sample.
    @param[in]  sample_metadata Persisted sample metadata payload.
    @return     True when the sample came from local WAV import.
    @exception  None
    """
    return (
        str(sample_metadata.get("source_kind", "") or "").strip() == NARRATOR_SAMPLE_SOURCE_IMPORTED
        or str(sample_metadata.get("sample_source", "") or "").strip() == "imported_sample"
        or str(sample_metadata.get("generation_mode", "") or "").strip() == "imported_sample"
    )


def _document_path(project_root: str | Path) -> Path:
    """
    @brief      Resolve the authoritative Narrator Voice document path.
    @param[in]  project_root Active project root folder.
    @return     Project-root `narrator_voice.json` path.
    """
    return Path(project_root) / config.NARRATOR_VOICE_FILE_NAME


def _normalized_audio_name(value: object) -> str:
    """
    @brief      Normalize one narrator profile value for a root-level audio file name.
    @param[in]  value Candidate profile identifier or name.
    @return     Filesystem-safe lowercase token.
    """
    normalized = "".join(character.lower() if character.isalnum() else "_" for character in str(value).strip())
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or "narator"


def _normalize_profile(profile: dict[str, object]) -> dict[str, object]:
    """
    @brief      Normalize the profile.
    @param[in]  profile Value for `profile`.
    @return     Derived helper result.
    """
    profile_payload = dict(profile)
    sample_payload = profile_payload.get("sample")
    if not isinstance(sample_payload, dict):
        sample_payload = profile_payload.get("sample_metadata")
    return {
        "profile_id": str(profile_payload.get("profile_id", "")).strip() or f"profile_{uuid4().hex}",
        "display_name": display_profile_name(profile_payload.get("display_name", "")) or "Unnamed Narrator",
        "language": narrator_language_code(profile_payload.get("language", DEFAULT_NARRATOR_LANGUAGE)),
        "prompt_text": str(profile_payload.get("prompt_text", "")).strip(),
        "preview_text": str(profile_payload.get("preview_text", DEFAULT_PREVIEW_TEXT)).strip() or DEFAULT_PREVIEW_TEXT,
        "sample": _normalize_sample_payload(sample_payload),
    }


def _normalize_sample_payload(payload: object) -> dict[str, object] | None:
    """
    @brief      Normalize one compact narrator sample payload.
    @param[in]  payload Candidate compact sample payload.
    @return     Compact sample payload or `None` when incomplete.
    @exception  None
    """
    if not isinstance(payload, dict):
        return None
    generation_mode = str(payload.get("generation_mode", "") or "").strip()
    source_kind = str(payload.get("source_kind", "") or payload.get("sample_source", "") or generation_mode).strip()
    if source_kind in {
        voice_sample_import_service.IMPORTED_SAMPLE_GENERATION_MODE,
        voice_sample_import_service.IMPORTED_SAMPLE_SOURCE,
    }:
        source_kind = NARRATOR_SAMPLE_SOURCE_IMPORTED
    if generation_mode and source_kind not in {
        NARRATOR_SAMPLE_SOURCE_IMPORTED,
        NARRATOR_SAMPLE_SOURCE_VOICE_DESIGNER,
    }:
        source_kind = NARRATOR_SAMPLE_SOURCE_VOICE_DESIGNER
    preview_text = str(payload.get("preview_text", "") or "").strip()
    if not source_kind or not preview_text:
        return None
    normalized_payload: dict[str, object] = {
        "source_kind": source_kind,
        "preview_text": preview_text,
        "language": narrator_language_code(payload.get("language", DEFAULT_NARRATOR_LANGUAGE)),
        "source_model_id": _optional_string(payload.get("source_model_id")),
    }
    source_file_name = _optional_string(payload.get("source_file_name"))
    if source_file_name is not None:
        normalized_payload["source_file_name"] = source_file_name
    return normalized_payload


def _unique_display_name(display_name: object, existing_names: set[str]) -> str:
    """
    @brief      Build one unique narrator display name using numeric suffixes.
    @param[in]  display_name Candidate display name.
    @param[in]  existing_names Case-folded names already present in the project.
    @return     Unique non-empty display name.
    @exception  None
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
    metadata_payload: dict[str, object] | None,
) -> None:
    """
    @brief      Store or clear one profile sample entry in the authoritative document.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @param[in]  metadata_payload Sample payload or `None` to clear it.
    @return     None.
    """
    normalized_profile_id = str(profile_id or "").strip()
    document = load_narrator_voice_document(project_root)
    profiles = list(document["profiles"])
    updated_profiles: list[dict[str, object]] = []
    for profile in profiles:
        if str(profile.get("profile_id", "")).strip() != normalized_profile_id:
            updated_profiles.append(profile)
            continue
        updated_profiles.append(
            {
                **dict(profile),
                "sample": None if metadata_payload is None else dict(metadata_payload),
            }
        )
    document["profiles"] = updated_profiles
    write_narrator_voice_document(project_root, document)


def _clear_profile_sample_metadata(project_root: str | Path) -> None:
    """
    @brief      Clear every narrator profile sample entry in the authoritative document.
    @param[in]  project_root Active project root folder.
    @return     None.
    """
    document = load_narrator_voice_document(project_root)
    profiles = [
        {
            **dict(profile),
            "sample": None,
        }
        for profile in document["profiles"]
    ]
    document["profiles"] = profiles
    write_narrator_voice_document(project_root, document)


def _validate_narrator_voice_document(payload: object) -> dict[str, object]:
    """
    @brief      Validate the complete authoritative Narrator Voice data contract.
    @param[in]  payload Candidate document payload.
    @return     Validated detached document dictionary.
    @exception  NarratorVoiceDocumentContractError Raised for any contract violation.
    """
    if not isinstance(payload, dict) or set(payload) != _NARRATOR_VOICE_ROOT_FIELDS:
        raise NarratorVoiceDocumentContractError("Narrator Voice document root fields do not match the contract.")
    status = payload.get("status")
    if status not in _NARRATOR_VOICE_STATUSES:
        raise NarratorVoiceDocumentContractError("Narrator Voice status is unsupported.")
    token_usage = _validate_token_usage(payload.get("token_usage"))
    budget_metadata = payload.get("budget_metadata")
    if not isinstance(budget_metadata, dict):
        raise NarratorVoiceDocumentContractError("Narrator Voice budget_metadata must be an object.")
    instructions = payload.get("additional_profile_instructions")
    if not isinstance(instructions, str):
        raise NarratorVoiceDocumentContractError("Narrator Voice instructions must be a string.")
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raise NarratorVoiceDocumentContractError("Narrator Voice profiles must be an array.")
    profiles = [_validate_persisted_profile(profile) for profile in raw_profiles]
    profile_ids = [profile["profile_id"] for profile in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        raise NarratorVoiceDocumentContractError("Narrator Voice profile ids must be unique.")
    folded_names = [profile["display_name"].casefold() for profile in profiles]
    if len(folded_names) != len(set(folded_names)):
        raise NarratorVoiceDocumentContractError("Narrator Voice display names must be unique.")
    selected_profile_id = payload.get("selected_profile_id")
    if selected_profile_id is not None and (
        not isinstance(selected_profile_id, str)
        or not selected_profile_id.strip()
        or selected_profile_id not in profile_ids
    ):
        raise NarratorVoiceDocumentContractError("Narrator Voice selected_profile_id is invalid.")
    resume = payload.get("resume")
    if status in {NARRATOR_VOICE_STATUS_NOT_STARTED, NARRATOR_VOICE_STATUS_COMPLETED}:
        if resume is not None:
            raise NarratorVoiceDocumentContractError("Completed or not-started Narrator Voice data cannot resume.")
        validated_resume = None
    else:
        validated_resume = _validate_resume(resume)
    return {
        "status": status,
        "token_usage": token_usage,
        "budget_metadata": dict(budget_metadata),
        "additional_profile_instructions": instructions,
        "selected_profile_id": selected_profile_id,
        "profiles": profiles,
        "resume": validated_resume,
    }


def _validate_token_usage(payload: object) -> dict[str, object]:
    """
    @brief      Validate the shared four-field token-usage payload.
    """
    expected_fields = {"input_tokens", "output_tokens", "total_tokens", "usage_available"}
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise NarratorVoiceDocumentContractError("Narrator Voice token_usage does not match the shared contract.")
    usage_available = payload.get("usage_available")
    if not isinstance(usage_available, bool):
        raise NarratorVoiceDocumentContractError("Narrator Voice usage_available must be boolean.")
    normalized: dict[str, object] = {"usage_available": usage_available}
    for field_name in ("input_tokens", "output_tokens", "total_tokens"):
        value = payload.get(field_name)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise NarratorVoiceDocumentContractError(f"Narrator Voice {field_name} must be non-negative or null.")
        normalized[field_name] = value
    return {
        "input_tokens": normalized["input_tokens"],
        "output_tokens": normalized["output_tokens"],
        "total_tokens": normalized["total_tokens"],
        "usage_available": normalized["usage_available"],
    }


def _validate_persisted_profile(payload: object) -> dict[str, object]:
    """
    @brief      Validate one exact persisted Narrator Voice profile.
    """
    if not isinstance(payload, dict) or set(payload) != _NARRATOR_VOICE_PROFILE_FIELDS:
        raise NarratorVoiceDocumentContractError("Narrator Voice profile fields do not match the contract.")
    profile_id = payload.get("profile_id")
    display_name = payload.get("display_name")
    language = payload.get("language")
    prompt_text = payload.get("prompt_text")
    preview_text = payload.get("preview_text")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise NarratorVoiceDocumentContractError("Narrator Voice profile_id must be a non-empty string.")
    if not isinstance(display_name, str) or not display_name.strip():
        raise NarratorVoiceDocumentContractError("Narrator Voice display_name must be non-empty.")
    if language not in _NARRATOR_LANGUAGE_LABELS:
        raise NarratorVoiceDocumentContractError("Narrator Voice profile language is unsupported.")
    if not isinstance(prompt_text, str):
        raise NarratorVoiceDocumentContractError("Narrator Voice prompt_text must be a string.")
    if not isinstance(preview_text, str) or not preview_text.strip():
        raise NarratorVoiceDocumentContractError("Narrator Voice preview_text must be non-empty.")
    sample = None if payload.get("sample") is None else _validate_persisted_sample(payload.get("sample"))
    return {
        "profile_id": profile_id,
        "display_name": display_name,
        "language": language,
        "prompt_text": prompt_text,
        "preview_text": preview_text,
        "sample": sample,
    }


def _validate_persisted_sample(payload: object) -> dict[str, object]:
    """
    @brief      Validate one exact compact generated or imported sample payload.
    """
    if not isinstance(payload, dict):
        raise NarratorVoiceDocumentContractError("Narrator Voice sample must be an object or null.")
    source_kind = payload.get("source_kind")
    expected_fields = set(_NARRATOR_VOICE_SAMPLE_FIELDS)
    if source_kind == NARRATOR_SAMPLE_SOURCE_IMPORTED:
        expected_fields.add("source_file_name")
    if set(payload) != expected_fields:
        raise NarratorVoiceDocumentContractError("Narrator Voice sample fields do not match its source kind.")
    preview_text = payload.get("preview_text")
    language = payload.get("language")
    source_model_id = payload.get("source_model_id")
    if source_kind not in {NARRATOR_SAMPLE_SOURCE_VOICE_DESIGNER, NARRATOR_SAMPLE_SOURCE_IMPORTED}:
        raise NarratorVoiceDocumentContractError("Narrator Voice sample source_kind is unsupported.")
    if not isinstance(preview_text, str) or not preview_text.strip():
        raise NarratorVoiceDocumentContractError("Narrator Voice sample preview_text must be non-empty.")
    if language not in _NARRATOR_LANGUAGE_LABELS:
        raise NarratorVoiceDocumentContractError("Narrator Voice sample language is unsupported.")
    if source_kind == NARRATOR_SAMPLE_SOURCE_IMPORTED:
        source_file_name = payload.get("source_file_name")
        if source_model_id is not None or not isinstance(source_file_name, str) or not source_file_name.strip():
            raise NarratorVoiceDocumentContractError("Imported narrator sample provenance is invalid.")
        return {
            "source_kind": source_kind,
            "preview_text": preview_text,
            "language": language,
            "source_model_id": None,
            "source_file_name": source_file_name,
        }
    if not isinstance(source_model_id, str) or not source_model_id.strip():
        raise NarratorVoiceDocumentContractError("Generated narrator samples require source_model_id.")
    return {
        "source_kind": source_kind,
        "preview_text": preview_text,
        "language": language,
        "source_model_id": source_model_id,
    }


def _validate_resume(payload: object) -> dict[str, object]:
    """
    @brief      Validate one exact unfinished AI style-analysis checkpoint.
    """
    if not isinstance(payload, dict) or set(payload) != _NARRATOR_VOICE_RESUME_FIELDS:
        raise NarratorVoiceDocumentContractError("Narrator Voice resume fields do not match the contract.")
    fingerprint = payload.get("resume_fingerprint")
    requested_count = payload.get("requested_count")
    completed_count = payload.get("completed_window_count")
    total_count = payload.get("total_window_count")
    observations = payload.get("style_observations")
    if not isinstance(fingerprint, str) or not fingerprint.strip():
        raise NarratorVoiceDocumentContractError("Narrator Voice resume fingerprint is required.")
    if not isinstance(requested_count, int) or isinstance(requested_count, bool) or requested_count <= 0:
        raise NarratorVoiceDocumentContractError("Narrator Voice requested_count must be positive.")
    if not isinstance(completed_count, int) or isinstance(completed_count, bool) or completed_count < 0:
        raise NarratorVoiceDocumentContractError("Narrator Voice completed_window_count is invalid.")
    if not isinstance(total_count, int) or isinstance(total_count, bool) or total_count < completed_count:
        raise NarratorVoiceDocumentContractError("Narrator Voice total_window_count is invalid.")
    if not isinstance(observations, list) or len(observations) != completed_count:
        raise NarratorVoiceDocumentContractError("Narrator Voice resume observations are inconsistent.")
    if not all(isinstance(observation, dict) for observation in observations):
        raise NarratorVoiceDocumentContractError("Narrator Voice style observations must be objects.")
    allocation = payload.get("gender_allocation")
    if not isinstance(allocation, dict) or set(allocation) != _NARRATOR_VOICE_GENDER_FIELDS:
        raise NarratorVoiceDocumentContractError("Narrator Voice gender allocation is invalid.")
    for field_name in ("male", "female", "random"):
        value = allocation.get(field_name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise NarratorVoiceDocumentContractError("Narrator Voice gender allocation counts are invalid.")
    random_gender = allocation.get("random_gender")
    if not isinstance(random_gender, str):
        raise NarratorVoiceDocumentContractError("Narrator Voice random_gender must be a string.")
    if allocation["male"] + allocation["female"] != requested_count:
        raise NarratorVoiceDocumentContractError("Narrator Voice gender allocation does not match requested_count.")
    return {
        "resume_fingerprint": fingerprint,
        "requested_count": requested_count,
        "gender_allocation": dict(allocation),
        "completed_window_count": completed_count,
        "total_window_count": total_count,
        "style_observations": [dict(observation) for observation in observations],
    }


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
    """
    return None if not model_entries else dict(model_entries[0])


def _current_profile_sample_audio_path(project_root: str | Path, profile_id: str) -> Path:
    """
    @brief      Resolve the current profile-id-based sample WAV path for a narrator profile.
    @param[in]  project_root Active project root folder.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     Current profile sample WAV path.
    @exception  None
    """
    return Path(project_root) / f"audio_narator_{_normalized_audio_name(profile_id)}.wav"


def _write_bytes_atomic(target_path: str | Path, payload: bytes) -> None:
    """
    @brief      Write bytes through a same-directory temporary file and atomic replacement.
    @param[in]  target_path Final file path to replace.
    @param[in]  payload Complete byte payload to persist.
    @return     None.
    @exception  OSError Raised when the temporary write or replacement fails.
    """
    resolved_path = Path(target_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=resolved_path.parent,
            prefix=f".{resolved_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, resolved_path)
    except OSError:
        if temporary_path is not None:
            _unlink_temporary_file(temporary_path)
        raise


def _unlink_temporary_file(temporary_path: Path) -> None:
    """
    @brief      Best-effort cleanup for temporary byte persistence files.
    @param[in]  temporary_path Temporary file path to remove.
    @return     None.
    @exception  None
    """
    with suppress(OSError):
        temporary_path.unlink(missing_ok=True)


# END OF FILE
