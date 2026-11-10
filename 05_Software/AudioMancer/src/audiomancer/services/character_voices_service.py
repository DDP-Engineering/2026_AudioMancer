#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file character_voices_service.py
@brief Project-local character-voices persistence helpers for AudioMancer.
@details Persists character-voices voice targets, selected voice language,
         per-target sample artifacts, and deterministic character voice prompts
         for the Character Voices workflow.
"""

# IMPORTS

import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from audiomancer import config
from audiomancer.services import (
    narrator_definition_service,
    project_workspace_service,
    voice_sample_import_service,
    voiceweaver_runtime_service,
)
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.operation_runtime_service import optional_string as _optional_string
from audiomancer.services.persistence_service import replace_project_files, write_bytes_atomic, write_json_atomic

# CONSTANTS

_CHARACTER_VOICES_LOGGER = get_component_logger("character_voices")

TARGET_KIND_NARRATOR = "narrator"
TARGET_KIND_CHARACTER = "character"

TARGET_ID_NARRATOR = "narrator"

SAMPLE_SOURCE_VOICE_DESIGNER = "voice_designer"
SAMPLE_SOURCE_COPIED_NARRATOR = "copied_narrator"
SAMPLE_SOURCE_IMPORTED = voice_sample_import_service.IMPORTED_SAMPLE_SOURCE

DEFAULT_PREVIEW_TEXT_BY_LANGUAGE = {
    "en": (
        "The evening settled over the old house, and each voice carried a different shade of memory. "
        "No one spoke first, but the silence between them said enough for anyone still listening."
    ),
    "ro": (
        "Seara s-a asezat peste casa veche, iar fiecare glas purta o alta nuanta de amintire. "
        "Nimeni nu a vorbit primul, dar tacerea dintre ei spunea destul pentru oricine mai asculta."
    ),
    "de": (
        "Der Abend senkte sich ueber das alte Haus, und jede Stimme trug einen anderen Ton der Erinnerung. "
        "Niemand sprach zuerst, doch die Stille zwischen ihnen sagte genug fuer jeden, der noch zuhoerte."
    ),
    "fr": (
        "Le soir est tombe sur la vieille maison, et chaque voix portait une autre nuance de memoire. "
        "Personne n'a parle le premier, mais le silence entre eux en disait assez pour qui ecoutait encore."
    ),
    "ru": (
        "Вечер опустился на старый дом, и в каждом голосе звучал свой оттенок памяти. "
        "Никто не заговорил первым, но молчание между ними сказало достаточно тем, кто еще слушал."
    ),
    "pt": (
        "A noite pousou sobre a casa antiga, e cada voz carregava um tom diferente de memoria. "
        "Ninguem falou primeiro, mas o silencio entre eles dizia o bastante para quem ainda escutava."
    ),
    "es": (
        "La tarde cayo sobre la vieja casa, y cada voz llevaba un matiz distinto de memoria. "
        "Nadie hablo primero, pero el silencio entre ellos decia bastante para quien aun escuchaba."
    ),
    "it": (
        "La sera scese sulla vecchia casa, e ogni voce portava una diversa sfumatura di memoria. "
        "Nessuno parlo per primo, ma il silenzio tra loro diceva abbastanza per chi ancora ascoltava."
    ),
}


# PUBLIC API


def ensure_character_voices_files(project_root: str | Path) -> None:
    """
    @brief      Ensure character-voices files and sample folders exist for one project.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    """
    targets_path = _targets_path(project_root)
    if not targets_path.is_file():
        _write_json(targets_path, [])


def load_selected_voice_language(
    project_root: str | Path,
    fallback: str = narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
) -> str:
    """
    @brief      Load the persisted character-voices selected voice language.
    @param[in]  project_root Active project root folder.
    @param[in]  fallback Fallback language code used when the file is missing.
    @return     Canonical character-voices voice language code.
    @exception  None
    """
    try:
        payload = project_workspace_service.load_manifest(project_root)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return narrator_definition_service.narrator_language_code(fallback)
    return narrator_definition_service.narrator_language_code(
        payload.get("selected_voice_language"),
        narrator_definition_service.narrator_language_code(fallback),
    )


def save_selected_voice_language(project_root: str | Path, selected_voice_language: object) -> str:
    """
    @brief      Persist one character-voices voice language selection.
    @param[in]  project_root Active project root folder.
    @param[in]  selected_voice_language Candidate selected voice language value.
    @return     Persisted canonical voice language code.
    @exception  OSError Raised when an existing manifest cannot be read or saved.
    @exception  ValueError Raised when an existing manifest is invalid.
    """
    normalized_language = narrator_definition_service.narrator_language_code(selected_voice_language)
    try:
        manifest = project_workspace_service.load_manifest(project_root)
    except FileNotFoundError:
        ensure_character_voices_files(project_root)
        return normalized_language
    except (OSError, ValueError):
        _CHARACTER_VOICES_LOGGER.exception(
            "Cannot save Character Voices language because the project manifest could not be loaded."
        )
        raise
    ensure_character_voices_files(project_root)
    if isinstance(manifest, dict):
        if bool(manifest.get("project_options_locked", False)):
            normalized_language = narrator_definition_service.narrator_language_code(
                manifest.get("target_language", manifest.get("selected_voice_language")),
                normalized_language,
            )
        if (
            "selected_voice_language" in manifest
            and narrator_definition_service.narrator_language_code(manifest.get("selected_voice_language"))
            == normalized_language
        ):
            return normalized_language
        manifest["selected_voice_language"] = normalized_language
        project_workspace_service.save_manifest(manifest, project_root)
    return normalized_language


def load_voice_plan(project_root: str | Path, *, strict: bool = False) -> list[dict[str, object]]:
    """
    @brief      Load the persisted character-voices target list.
    @param[in]  project_root Active project root folder.
    @param[in]  strict Report invalid or unreadable data without initializing the plan.
    @return     Normalized ordered voice target payload list.
    @exception  OSError or ValueError in strict mode.
    """
    if not strict:
        ensure_character_voices_files(project_root)
    try:
        payload = json.loads(_targets_path(project_root).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        if strict:
            raise
        return []
    if not isinstance(payload, list):
        if strict:
            raise ValueError("Character Voices document must be a JSON array.")
        return []
    return [_normalize_voice_target(item) for item in payload if isinstance(item, dict)]


def save_voice_targets(project_root: str | Path, voice_targets: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Persist one character-voices target payload list.
    @param[in]  project_root Active project root folder.
    @param[in]  voice_targets Candidate voice target payload list.
    @return     Persisted normalized voice target list.
    @exception  None
    """
    ensure_character_voices_files(project_root)
    normalized_targets = [_normalize_voice_target(item) for item in voice_targets if isinstance(item, dict)]
    _write_json(_targets_path(project_root), normalized_targets)
    return normalized_targets


def sync_voice_plan(
    project_root: str | Path,
    character_profiles: list[dict[str, object]],
    narrator_profile: dict[str, object] | None,
    voice_language: object = narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE,
) -> list[dict[str, object]]:
    """
    @brief      Synchronize persisted character-voices targets against the current narrator and character state.
    @param[in]  project_root Active project root folder.
    @param[in]  character_profiles Persisted character profile payload list.
    @param[in]  narrator_profile Explicitly selected narrator profile payload or `None`.
    @param[in]  voice_language Selected audiobook voice language used for default preview text.
    @return     Persisted normalized character-voices target list.
    @exception  None
    """
    normalized_voice_language = narrator_definition_service.narrator_language_code(voice_language)
    existing_targets = load_voice_plan(project_root)
    existing_targets_by_id = {str(target.get("target_id", "")).strip(): dict(target) for target in existing_targets}
    synchronized_targets: list[dict[str, object]] = []
    if isinstance(narrator_profile, dict):
        existing_narrator_target = existing_targets_by_id.get(TARGET_ID_NARRATOR, {})
        synchronized_targets.append(
            _normalize_voice_target(
                {
                    **existing_narrator_target,
                    "target_id": TARGET_ID_NARRATOR,
                    "target_kind": TARGET_KIND_NARRATOR,
                    "display_name": "Narrator Voice",
                    "character_id": None,
                    "prompt_text": None,
                    "default_prompt_text": None,
                    "preview_text": None,
                    "editable": False,
                }
            )
        )
    for character_profile in character_profiles:
        normalized_character_id = str(character_profile.get("character_id", "")).strip()
        if not normalized_character_id:
            continue
        target_id = character_target_id(normalized_character_id)
        default_prompt_text = build_character_default_prompt(character_profile)
        existing_target = existing_targets_by_id.get(target_id, {})
        synchronized_targets.append(
            _normalize_voice_target(
                {
                    **existing_target,
                    "target_id": target_id,
                    "target_kind": TARGET_KIND_CHARACTER,
                    "display_name": str(character_profile.get("canonical_name", "")).strip() or target_id,
                    "character_id": normalized_character_id,
                    "prompt_text": _synchronized_character_prompt_text(
                        existing_target,
                        character_profile,
                        default_prompt_text,
                    ),
                    "default_prompt_text": default_prompt_text,
                    "preview_text": _synchronized_character_preview_text(
                        existing_target,
                        character_profile,
                        normalized_voice_language,
                    ),
                    "editable": True,
                }
            )
        )
    if synchronized_targets == existing_targets:
        return synchronized_targets
    return save_voice_targets(project_root, synchronized_targets)


def voice_target_by_id(
    project_root: str | Path,
    target_id: str | None,
    voice_targets: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    """
    @brief      Resolve one persisted character-voices target by identifier.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @param[in]  voice_targets Optional already-loaded target payload list.
    @return     Matching voice target payload or `None`.
    @exception  None
    """
    normalized_target_id = str(target_id or "").strip()
    if not normalized_target_id:
        return None
    return next(
        (
            target
            for target in (load_voice_plan(project_root) if voice_targets is None else voice_targets)
            if str(target.get("target_id", "")).strip() == normalized_target_id
        ),
        None,
    )


def mark_character_voice_target_stale(project_root: str | Path, character_id: str) -> str:
    """
    @brief      Clear generated sample metadata for one character voice target.
    @param[in]  project_root Active project root folder.
    @param[in]  character_id Character identifier whose voice definition changed.
    @return     Stable character voice target identifier.
    @exception  None
    """
    target_id = character_target_id(str(character_id).strip())
    if not _targets_path(project_root).is_file():
        return target_id
    if not voice_target_by_id(project_root, target_id):
        return target_id
    delete_target_sample(project_root, target_id)
    return target_id


def remove_character_voice_target(project_root: str | Path, character_id: str) -> str:
    """
    @brief      Remove one deleted character voice target and its generated sample.
    @param[in]  project_root Active project root folder.
    @param[in]  character_id Deleted character identifier.
    @return     Stable character voice target identifier.
    @exception  None
    """
    target_id = character_target_id(str(character_id).strip())
    if not _targets_path(project_root).is_file():
        return target_id
    if voice_target_by_id(project_root, target_id):
        delete_target_sample(project_root, target_id)
    save_voice_targets(
        project_root,
        [
            target_payload
            for target_payload in load_voice_plan(project_root)
            if str(target_payload.get("target_id", "")).strip() != target_id
        ],
    )
    return target_id


def save_target_prompt(
    project_root: str | Path,
    target_id: str,
    prompt_text: str,
    preview_text: str | None = None,
) -> dict[str, object]:
    """
    @brief      Persist one edited character-voices target prompt and clear any stale target sample.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @param[in]  prompt_text Edited voice-designer prompt text.
    @param[in]  preview_text Optional edited preview text stored with the target.
    @return     Persisted updated target payload.
    @exception  ValueError Raised when the prompt is empty or the target is not editable.
    """
    normalized_prompt = str(prompt_text).strip()
    if not normalized_prompt:
        raise ValueError("empty_prompt")
    normalized_preview_text = None if preview_text is None else str(preview_text).strip()
    if preview_text is not None and not normalized_preview_text:
        raise ValueError("empty_preview_text")
    root = Path(project_root).resolve()
    ensure_character_voices_files(root)
    original_document = _targets_path(root).read_bytes()
    targets = load_voice_plan(root)
    target = voice_target_by_id(root, target_id, targets)
    if target is None:
        raise ValueError("missing_target")
    if not target["editable"]:
        raise ValueError("readonly_target")
    if not target_prompt_changed(target, normalized_prompt, normalized_preview_text):
        return target
    updated_target = {
        **target,
        "prompt_text": normalized_prompt,
        "preview_text": target["preview_text"] if normalized_preview_text is None else normalized_preview_text,
        "sample_audio_path": None,
        "sample_metadata": None,
    }
    _publish_voice_targets(
        root,
        [updated_target if item is target else item for item in targets],
        original_document,
        _retired_sample(root, target_id, targets),
    )
    _CHARACTER_VOICES_LOGGER.info("Saved character voice target prompt target_id=%s", target_id)
    return updated_target


def target_prompt_changed(target: dict[str, object], prompt_text: str, preview_text: str | None) -> bool:
    """
    @brief      Compare a draft's editable fields with the current target.
    @param[in]  target Persisted voice target.
    @param[in]  prompt_text Candidate voice prompt.
    @param[in]  preview_text Candidate preview, or None to keep the current text.
    @return     Whether the draft changes either persisted field.
    """
    return prompt_text.strip() != target["prompt_text"] or (
        preview_text is not None and preview_text.strip() != target["preview_text"]
    )


def begin_target_prompt_edit(project_root: str | Path, target_id: str) -> dict[str, object]:
    """
    @brief      Read one editable target without changing its sample.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @return     Target payload prepared for edit mode.
    @exception  ValueError Raised when the target is missing or not editable.
    """
    if not _targets_path(project_root).is_file():
        raise ValueError("missing_target")
    target_payload = voice_target_by_id(project_root, target_id)
    if target_payload is None:
        raise ValueError("missing_target")
    if not bool(target_payload.get("editable", False)):
        raise ValueError("readonly_target")
    return target_payload


def voice_target_generation_request(
    target_payload: dict[str, object],
    discovered_models: list[dict[str, object]],
    voice_language: object,
) -> dict[str, object]:
    """
    @brief      Resolve the current runtime generation request for one character-voices target.
    @param[in]  target_payload Character-voices target payload.
    @param[in]  discovered_models Current normalized discovered runtime models.
    @param[in]  voice_language Selected character-voices voice language.
    @return     Generation-request payload with availability flags and model ids.
    @exception  None
    """
    normalized_language = narrator_definition_service.narrator_language_code(voice_language)
    prompt_text = str(target_payload.get("prompt_text", "")).strip()
    if str(target_payload.get("target_kind", "")).strip() != TARGET_KIND_CHARACTER:
        return _build_generation_request(
            False,
            False,
            "The selected voice target cannot generate a new sample on this page.",
            normalized_language,
            prompt_text,
        )
    voice_designer_model = voiceweaver_runtime_service.resolve_tts_model(
        discovered_models, "voice_design", normalized_language,
    )
    if voice_designer_model is None:
        return _build_generation_request(
            False,
            False,
            f"No healthy VoiceWeaver design model is available for {normalized_language}.",
            normalized_language,
            prompt_text,
        )
    resolved_model_id = str(voice_designer_model.get("model_id", "")).strip()
    return _build_generation_request(
        True,
        True,
        "",
        normalized_language,
        prompt_text,
        generation_mode="definition",
        model_id=resolved_model_id,
        source_model_id=resolved_model_id,
        runtime_language=voiceweaver_runtime_service.tts_language_for_model(
            normalized_language, voice_designer_model,
        ),
    )


def character_target_id(character_id: str) -> str:
    """
    @brief      Build the stable character-voices target identifier for one character.
    @param[in]  character_id Persisted character identifier.
    @return     Stable character-voices character target identifier.
    @exception  None
    """
    return f"character_{str(character_id).strip()}"


def build_character_default_prompt(character_profile: dict[str, object]) -> str:
    """
    @brief      Build one deterministic English voice-designer prompt from one persisted character profile.
    @param[in]  character_profile Persisted character profile payload.
    @return     Derived voice-designer prompt text.
    @exception  None
    """
    stored_voice_definition_prompt = str(character_profile.get("voice_definition_prompt", "")).strip()
    if stored_voice_definition_prompt:
        return _ensure_character_prompt_instructions(stored_voice_definition_prompt, character_profile)
    character_name = str(character_profile.get("canonical_name", "Character")).strip() or "Character"
    return (
        f"Create a consistent spoken voice for {character_name} with clear diction, stable identity, "
        "and delivery suitable for repeated dialogue narration. "
        f"{_character_voice_gender_instruction(character_profile)} "
        f"{_character_voice_age_instruction(character_profile)}"
    )


def preview_text_for_language(voice_language: object) -> str:
    """
    @brief      Resolve one deterministic sample preview text for the selected character-voices language.
    @param[in]  voice_language Candidate selected voice language.
    @return     Stable localized preview text.
    @exception  None
    """
    normalized_language = narrator_definition_service.narrator_language_code(voice_language)
    return DEFAULT_PREVIEW_TEXT_BY_LANGUAGE.get(
        normalized_language,
        DEFAULT_PREVIEW_TEXT_BY_LANGUAGE[narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE],
    )


def effective_target_preview_text(target_payload: dict[str, object], voice_language: object) -> str:
    """
    @brief      Resolve the preview text used by one character-voices target for UI display or generation.
    @param[in]  target_payload Character-voices target payload.
    @param[in]  voice_language Selected character-voices voice language.
    @return     Stored preview text or the deterministic language fallback.
    @exception  None
    """
    stored_preview_text = str(target_payload.get("preview_text", "")).strip()
    return stored_preview_text or preview_text_for_language(voice_language)


def target_sample_paths(
    project_root: str | Path,
    target_id: str,
    voice_targets: list[dict[str, object]] | None = None,
) -> tuple[Path, Path]:
    """
    @brief      Resolve the audio and aggregate metadata sample paths for one character-voices target.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @param[in]  voice_targets Optional already-loaded target payload list.
    @return     Tuple of WAV path and `characters_voice.json` metadata path.
    @exception  None
    """
    normalized_target_id = str(target_id).strip()
    target_payload = voice_target_by_id(project_root, normalized_target_id, voice_targets)
    if isinstance(target_payload, dict) and str(target_payload.get("sample_audio_path", "") or "").strip():
        audio_path = Path(project_root) / str(target_payload.get("sample_audio_path", "")).strip()
    else:
        audio_path = _sample_path(Path(project_root), normalized_target_id)
    return (
        audio_path,
        _targets_path(project_root),
    )


def load_target_sample_metadata(
    project_root: str | Path,
    target_id: str,
    voice_targets: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    """
    @brief      Load the persisted sample metadata for one character-voices target.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @param[in]  voice_targets Optional already-loaded target payload list.
    @return     Metadata payload or `None` when unavailable.
    @exception  None
    """
    target_payload = voice_target_by_id(project_root, target_id, voice_targets)
    if not isinstance(target_payload, dict):
        return None
    payload = target_payload.get("sample_metadata")
    return dict(payload) if isinstance(payload, dict) else None


def has_target_sample(
    project_root: str | Path,
    target_id: str,
    voice_targets: list[dict[str, object]] | None = None,
) -> bool:
    """
    @brief      Return whether one character-voices target currently has a persisted sample pair.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @param[in]  voice_targets Optional already-loaded target payload list.
    @return     `True` when the sample WAV exists and `characters_voice.json` has sample metadata.
    @exception  None
    """
    audio_path, _metadata_path = target_sample_paths(project_root, target_id, voice_targets)
    return audio_path.is_file() and load_target_sample_metadata(project_root, target_id, voice_targets) is not None


def delete_target_sample(
    project_root: str | Path,
    target_id: str,
) -> None:
    """
    @brief      Delete the persisted sample artifacts for one character-voices target.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @return     None.
    @exception  None
    """
    root = Path(project_root).resolve()
    ensure_character_voices_files(root)
    original_document = _targets_path(root).read_bytes()
    targets = load_voice_plan(root)
    updated = _target_sample_metadata_updated_targets(targets, target_id, None, None)
    if updated != targets:
        _publish_voice_targets(root, updated, original_document, _retired_sample(root, target_id, targets))


def store_target_sample(
    project_root: str | Path,
    target_payload: dict[str, object],
    voice_language: object,
    preview_text: str,
    generation_request: dict[str, object],
    runtime_result_summary: str,
    audio_bytes: bytes,
) -> dict[str, object]:
    """
    @brief      Persist one generated character-voices sample WAV and aggregate metadata payload.
    @param[in]  project_root Active project root folder.
    @param[in]  target_payload Character-voices target payload.
    @param[in]  voice_language Selected character-voices voice language code.
    @param[in]  preview_text Preview text synthesized for the sample.
    @param[in]  generation_request Resolved runtime generation-request payload.
    @param[in]  runtime_result_summary Operator-facing runtime summary text.
    @param[in]  audio_bytes Downloaded WAV bytes.
    @return     Persisted sample metadata payload.
    @exception  None
    """
    ensure_character_voices_files(project_root)
    target_id = str(target_payload.get("target_id", "")).strip()
    metadata_payload = {
        "target_id": target_id,
        "target_kind": str(target_payload.get("target_kind", "")).strip(),
        "display_name": str(target_payload.get("display_name", "")).strip(),
        "voice_language": narrator_definition_service.narrator_language_code(voice_language),
        "sample_source": SAMPLE_SOURCE_VOICE_DESIGNER,
        "copied_from_target_id": None,
        "source_model_id": str(generation_request.get("source_model_id", "")).strip() or None,
        "generation_mode": str(generation_request.get("generation_mode", "")).strip(),
        "prompt_text": str(target_payload.get("prompt_text", "")).strip(),
        "preview_text": str(preview_text).strip(),
        "runtime_result_summary": str(runtime_result_summary).strip(),
    }
    _replace_target_sample(Path(project_root).resolve(), target_id, metadata_payload, audio_bytes)
    _CHARACTER_VOICES_LOGGER.info("Persisted generated character voice sample target_id=%s", target_id)
    return metadata_payload


def import_target_sample(
    project_root: str | Path,
    target_payload: dict[str, object],
    voice_language: object,
    preview_text: str,
    source_audio_path: str | Path,
) -> dict[str, object]:
    """
    @brief      Validate and persist one imported character-voices WAV sample.
    @param[in]  project_root Active project root folder.
    @param[in]  target_payload Character-voices target payload.
    @param[in]  voice_language Selected character-voices voice language code.
    @param[in]  preview_text Transcript text spoken in the imported sample.
    @param[in]  source_audio_path Operator-selected WAV file path.
    @return     Persisted imported-sample metadata payload.
    @exception  ValueError Raised when the target, sample, or transcript is invalid.
    """
    ensure_character_voices_files(project_root)
    if str(target_payload.get("target_kind", "")).strip() != TARGET_KIND_CHARACTER:
        raise ValueError("readonly_target")
    normalized_preview_text = str(preview_text or "").strip()
    if not normalized_preview_text:
        raise ValueError("empty_preview_text")
    source_path = Path(source_audio_path)
    validation_report = voice_sample_import_service.validate_imported_wav_sample(source_path)
    target_id = str(target_payload.get("target_id", "")).strip()
    metadata_payload = {
        "target_id": target_id,
        "target_kind": str(target_payload.get("target_kind", "")).strip(),
        "display_name": str(target_payload.get("display_name", "")).strip(),
        "voice_language": narrator_definition_service.narrator_language_code(voice_language),
        "sample_source": SAMPLE_SOURCE_IMPORTED,
        "copied_from_target_id": None,
        "source_model_id": None,
        "generation_mode": voice_sample_import_service.IMPORTED_SAMPLE_GENERATION_MODE,
        "prompt_text": str(target_payload.get("prompt_text", "")).strip(),
        "preview_text": normalized_preview_text,
        "source_file_name": source_path.name,
        "audio_validation": dict(validation_report),
        "runtime_result_summary": "Imported WAV sample.",
    }
    _replace_target_sample(Path(project_root).resolve(), target_id, metadata_payload, source_path.read_bytes())
    _CHARACTER_VOICES_LOGGER.info("Imported character voice sample target_id=%s", target_id)
    return metadata_payload


def sync_same_narrator_samples(
    project_root: str | Path,
    character_targets: list[dict[str, object]],
    voice_language: object,
) -> None:
    """
    @brief      Synchronize narrator-derived copied samples for every character-voices character target.
    @param[in]  project_root Active project root folder.
    @param[in]  character_targets Current character-voices character targets.
    @param[in]  voice_language Current selected character-voices voice language.
    @return     None.
    @exception  None
    """
    ensure_character_voices_files(project_root)
    root = Path(project_root).resolve()
    original_document = _targets_path(root).read_bytes()
    voice_targets = load_voice_plan(root) or [_normalize_voice_target(target) for target in character_targets]
    narrator_audio_path = narrator_definition_service.selected_narrator_sample_path(project_root)
    narrator_metadata = narrator_definition_service.load_selected_narrator_sample_metadata(project_root)
    if narrator_audio_path is None or not narrator_audio_path.is_file() or narrator_metadata is None:
        removed_samples = 0
        for target_payload in character_targets:
            target_id = str(target_payload.get("target_id", "")).strip()
            sample_metadata = load_target_sample_metadata(project_root, target_id, voice_targets)
            if (
                isinstance(sample_metadata, dict)
                and sample_metadata.get("sample_source") == SAMPLE_SOURCE_COPIED_NARRATOR
            ):
                delete_target_sample(root, target_id)
                voice_targets = load_voice_plan(project_root)
                removed_samples += 1
        if removed_samples:
            _CHARACTER_VOICES_LOGGER.info(
                "Removed copied narrator character samples because selected narrator sample is unavailable: count=%s",
                removed_samples,
            )
        return
    narrator_audio_bytes = narrator_audio_path.read_bytes()
    narrator_language = narrator_definition_service.narrator_language_code(
        narrator_metadata.get("language", voice_language),
    )
    narrator_preview_text = str(narrator_metadata.get("preview_text", "")).strip()
    narrator_generation_mode = str(
        narrator_metadata.get("source_kind", "")
        or narrator_metadata.get("generation_mode", "")
        or narrator_metadata.get("sample_source", "")
    ).strip()
    narrator_source_model_id = str(narrator_metadata.get("source_model_id", "")).strip() or None
    narrator_runtime_summary = str(narrator_metadata.get("runtime_result_summary", "")).strip()
    copied_samples = 0
    sample_changes: dict[Path, bytes | None] = {}
    updated_targets = list(voice_targets)
    for target_payload in character_targets:
        target_id = str(target_payload.get("target_id", "")).strip()
        audio_path, _metadata_path = target_sample_paths(project_root, target_id, updated_targets)
        metadata_payload = {
            "target_id": target_id,
            "target_kind": TARGET_KIND_CHARACTER,
            "display_name": str(target_payload.get("display_name", "")).strip(),
            "voice_language": narrator_language,
            "sample_source": SAMPLE_SOURCE_COPIED_NARRATOR,
            "copied_from_target_id": TARGET_ID_NARRATOR,
            "source_model_id": narrator_source_model_id,
            "generation_mode": narrator_generation_mode,
            "prompt_text": str(target_payload.get("prompt_text", "")).strip(),
            "preview_text": narrator_preview_text,
            "runtime_result_summary": narrator_runtime_summary,
        }
        if _copied_narrator_sample_is_current(
            audio_path,
            target_id,
            metadata_payload,
            narrator_audio_bytes,
            updated_targets,
        ):
            continue
        sample_changes.update(_retired_sample(root, target_id, updated_targets))
        audio_path = _sample_path(root, target_id)
        sample_changes[audio_path] = narrator_audio_bytes
        updated_targets = _target_sample_metadata_updated_targets(
            updated_targets,
            target_id,
            audio_path.relative_to(root).as_posix(),
            metadata_payload,
        )
        copied_samples += 1
    if sample_changes:
        _publish_voice_targets(root, updated_targets, original_document, sample_changes)
    _CHARACTER_VOICES_LOGGER.info(
        "Synchronized copied narrator character samples: count=%s language=%s",
        copied_samples,
        narrator_language,
    )


def sample_runtime_available(
    sample_metadata: dict[str, object] | None,
    discovered_models: list[dict[str, object]],
) -> bool:
    """
    @brief      Return whether one persisted character-voices sample still references
                a healthy discovered runtime model.
    @param[in]  sample_metadata Persisted sample metadata payload.
    @param[in]  discovered_models Current normalized discovered runtime models.
    @return     `True` when the sample still references a healthy available model.
    @exception  None
    """
    return narrator_definition_service.sample_runtime_available(sample_metadata, discovered_models)


def character_voices_is_ready(
    project_root: str | Path,
    voice_targets: list[dict[str, object]],
) -> bool:
    """
    @brief      Return whether the current character-voices state is ready for the future Speech Blocks workflow.
    @param[in]  project_root Active project root folder.
    @param[in]  voice_targets Current character-voices target list.
    @return     `True` when the selected narrator sample and every character sample exist.
    @exception  None
    """
    narrator_audio_path = narrator_definition_service.selected_narrator_sample_path(project_root)
    if (
        narrator_audio_path is None
        or not narrator_audio_path.is_file()
        or narrator_definition_service.load_selected_narrator_sample_metadata(project_root) is None
    ):
        return False
    character_targets = [
        target for target in voice_targets if str(target.get("target_kind", "")).strip() == TARGET_KIND_CHARACTER
    ]
    return bool(voice_targets) and all(
        has_target_sample(project_root, str(target.get("target_id", "")).strip(), voice_targets)
        for target in character_targets
    )


def character_voices_operation_summary(
    project_root: str | Path,
    voice_targets: list[dict[str, object]],
) -> dict[str, object]:
    """
    @brief      Build the compact manifest operation summary for Character Voices.
    @param[in]  project_root Active project root folder.
    @param[in]  voice_targets Current character-voices target list.
    @return     Project-manifest operation summary payload.
    @exception  None
    """
    targets = [target for target in voice_targets if isinstance(target, dict)]
    narrator_targets = [
        target for target in targets if str(target.get("target_kind", "")).strip() == TARGET_KIND_NARRATOR
    ]
    character_targets = [
        target for target in targets if str(target.get("target_kind", "")).strip() == TARGET_KIND_CHARACTER
    ]
    narrator_sample_count = 1 if narrator_targets and selected_narrator_sample_exists(project_root) else 0
    sampled_character_targets = [
        target
        for target in character_targets
        if has_target_sample(project_root, str(target.get("target_id", "")).strip(), targets)
    ]
    progress_current = narrator_sample_count + len(sampled_character_targets)
    progress_total = len(narrator_targets) + len(character_targets)
    ready = character_voices_is_ready(project_root, targets)
    if ready:
        status = "completed"
    elif progress_current > 0:
        status = "in_progress"
    else:
        status = "not_started"
    return {
        "status": status,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "mode": "manual" if progress_current > 0 else None,
        "warning_count": 0,
    }


def selected_narrator_sample_exists(project_root: str | Path) -> bool:
    """
    @brief      Return whether the selected narrator sample exists for the current project.
    @param[in]  project_root Active project root folder.
    @return     `True` when the selected narrator WAV and metadata are both present.
    @exception  None
    """
    audio_path = narrator_definition_service.selected_narrator_sample_path(project_root)
    return (
        audio_path is not None
        and audio_path.is_file()
        and narrator_definition_service.load_selected_narrator_sample_metadata(project_root) is not None
    )


def selected_narrator_sample_metadata(project_root: str | Path) -> dict[str, object] | None:
    """
    @brief      Load the selected narrator sample metadata reused by the Character Voices page.
    @param[in]  project_root Active project root folder.
    @return     Selected narrator metadata payload or `None`.
    @exception  None
    """
    return narrator_definition_service.load_selected_narrator_sample_metadata(project_root)


# LOCAL HELPERS


def _normalize_voice_target(target_payload: dict[str, object]) -> dict[str, object]:
    """
    @brief      Normalize the voice target.
    @param[in]  target_payload Payload for `target_payload`.
    @return     Derived helper result.
    """
    normalized_target_kind = (
        str(target_payload.get("target_kind", TARGET_KIND_CHARACTER)).strip() or TARGET_KIND_CHARACTER
    )
    normalized_target_id = str(target_payload.get("target_id", "")).strip() or TARGET_ID_NARRATOR
    normalized_display_name = str(target_payload.get("display_name", "")).strip() or normalized_target_id
    default_prompt_text = (
        None
        if normalized_target_kind == TARGET_KIND_NARRATOR
        else str(target_payload.get("default_prompt_text", "")).strip()
    )
    prompt_text = (
        None
        if normalized_target_kind == TARGET_KIND_NARRATOR
        else str(target_payload.get("prompt_text", default_prompt_text or "")).strip()
    )
    preview_text = (
        None if normalized_target_kind == TARGET_KIND_NARRATOR else str(target_payload.get("preview_text", "")).strip()
    )
    return {
        "target_id": normalized_target_id,
        "target_kind": normalized_target_kind,
        "display_name": normalized_display_name,
        "character_id": _optional_string(target_payload.get("character_id")),
        "prompt_text": prompt_text,
        "default_prompt_text": default_prompt_text,
        "preview_text": preview_text,
        "editable": bool(target_payload.get("editable", normalized_target_kind == TARGET_KIND_CHARACTER)),
        "sample_audio_path": _optional_string(target_payload.get("sample_audio_path")),
        "sample_metadata": (
            dict(target_payload.get("sample_metadata"))
            if isinstance(target_payload.get("sample_metadata"), dict)
            else None
        ),
    }


def _synchronized_character_preview_text(
    existing_target: dict[str, object],
    character_profile: dict[str, object],
    voice_language: str,
) -> str:
    """
    @brief      Resolve character preview text while preserving operator edits.
    @param[in]  existing_target Existing persisted target payload.
    @param[in]  character_profile Character Discovery profile payload.
    @param[in]  voice_language Selected audiobook voice language code.
    @return     Existing edited preview text, discovered dialogue preview, or the selected-language default.
    """
    localized_preview_text = preview_text_for_language(voice_language)
    discovered_preview_text = str(character_profile.get("preview_text", "")).strip()
    existing_preview_text = str(existing_target.get("preview_text", "")).strip()
    if not existing_preview_text:
        return discovered_preview_text or localized_preview_text
    if _is_unmodified_default_preview_text(existing_preview_text, localized_preview_text) and not (
        _optional_string(existing_target.get("sample_audio_path"))
        or isinstance(existing_target.get("sample_metadata"), dict)
    ):
        return discovered_preview_text or localized_preview_text
    return existing_preview_text


def _synchronized_character_prompt_text(
    existing_target: dict[str, object],
    character_profile: dict[str, object],
    default_prompt_text: str,
) -> str:
    """
    @brief      Resolve character prompt text while enforcing explicit voice guidance.
    @param[in]  existing_target Existing persisted target payload.
    @param[in]  character_profile Current persisted character profile payload.
    @param[in]  default_prompt_text Current derived default prompt text.
    @return     Prompt text safe to send to VoiceWeaver voice design.
    """
    existing_prompt_text = str(existing_target.get("prompt_text", "")).strip()
    existing_default_prompt_text = str(existing_target.get("default_prompt_text", "")).strip()
    if not existing_prompt_text:
        return default_prompt_text
    if existing_default_prompt_text and existing_prompt_text == existing_default_prompt_text:
        return default_prompt_text
    return _ensure_character_prompt_instructions(existing_prompt_text, character_profile)


def _ensure_character_prompt_instructions(prompt_text: str, character_profile: dict[str, object]) -> str:
    """
    @brief      Add required character voice guidance to one voice prompt.
    @param[in]  prompt_text Candidate voice-designer prompt.
    @param[in]  character_profile Character profile used for voice evidence.
    @return     Prompt text containing explicit sex/gender and age-domain guidance.
    """
    prompt_with_gender = _ensure_character_prompt_gender_instruction(prompt_text, character_profile)
    return _ensure_character_prompt_age_instruction(prompt_with_gender, character_profile)


def _ensure_character_prompt_gender_instruction(prompt_text: str, character_profile: dict[str, object]) -> str:
    """
    @brief      Add explicit sex/gender guidance to one voice prompt when missing.
    @param[in]  prompt_text Candidate voice-designer prompt.
    @param[in]  character_profile Character profile used for gender evidence.
    @return     Prompt text containing one explicit sex/gender instruction.
    """
    normalized_prompt = str(prompt_text).strip()
    if _prompt_has_explicit_gender_instruction(normalized_prompt):
        return normalized_prompt
    gender_instruction = _character_voice_gender_instruction(character_profile)
    if not normalized_prompt:
        return gender_instruction
    return f"{normalized_prompt} {gender_instruction}".strip()


def _ensure_character_prompt_age_instruction(prompt_text: str, character_profile: dict[str, object]) -> str:
    """
    @brief      Add explicit age-domain guidance to one voice prompt when missing.
    @param[in]  prompt_text Candidate voice-designer prompt.
    @param[in]  character_profile Character profile used for age evidence.
    @return     Prompt text containing one explicit age-domain instruction.
    """
    normalized_prompt = str(prompt_text).strip()
    if _prompt_has_explicit_age_instruction(normalized_prompt):
        return normalized_prompt
    age_instruction = _character_voice_age_instruction(character_profile)
    if not normalized_prompt:
        return age_instruction
    return f"{normalized_prompt} {age_instruction}".strip()


def _character_voice_gender_instruction(character_profile: dict[str, object]) -> str:
    """
    @brief      Build the mandatory sex/gender instruction for one character voice prompt.
    @param[in]  character_profile Character profile used for gender evidence.
    @return     Explicit sex/gender instruction sentence.
    """
    gender_hint = str(character_profile.get("gender_hint", "")).strip()
    if gender_hint:
        return (
            f"Sex/Gender: {gender_hint}. Match this explicitly in the vocal identity and do not replace it "
            "with a different default."
        )
    return (
        "Sex/Gender: not specified in the source. Use a neutral or androgynous vocal identity and do not "
        "default to a male voice."
    )


def _character_voice_age_instruction(character_profile: dict[str, object]) -> str:
    """
    @brief      Build the mandatory age-domain instruction for one character voice prompt.
    @param[in]  character_profile Character profile used for age evidence.
    @return     Explicit age-domain instruction sentence.
    """
    age_hint = str(character_profile.get("age_hint", "")).strip()
    if age_hint:
        return (
            f"Age Domain: {age_hint}. Match this explicitly in the vocal age and do not replace it with a younger "
            "or older default."
        )
    return (
        "Age Domain: not specified in the source. Use an age-neutral adult voice and do not default to a young voice."
    )


def _prompt_has_explicit_gender_instruction(prompt_text: str) -> bool:
    """
    @brief      Return whether a prompt already carries explicit sex/gender guidance.
    @param[in]  prompt_text Candidate voice-designer prompt.
    @return     True when a gender or sex instruction is already present.
    """
    normalized_prompt = str(prompt_text).casefold()
    return bool(
        re.search(r"\b(sex/gender|gender hint|gender)\s*:", normalized_prompt)
        or re.search(r"\b(female|male|woman|man|girl|boy|androgynous)\b", normalized_prompt)
    )


def _prompt_has_explicit_age_instruction(prompt_text: str) -> bool:
    """
    @brief      Return whether a prompt already carries explicit age-domain guidance.
    @param[in]  prompt_text Candidate voice-designer prompt.
    @return     True when an age instruction is already present.
    """
    normalized_prompt = str(prompt_text).casefold()
    return bool(re.search(r"\b(age domain|age hint|age)\s*:", normalized_prompt))


def _is_unmodified_default_preview_text(preview_text: str, localized_preview_text: str) -> bool:
    """
    @brief      Return whether preview text is one of the built-in defaults for another language.
    @param[in]  preview_text Candidate persisted preview text.
    @param[in]  localized_preview_text Current selected-language default preview text.
    @return     True when the candidate can be safely localized.
    """
    return preview_text != localized_preview_text and preview_text in DEFAULT_PREVIEW_TEXT_BY_LANGUAGE.values()


def _sample_path(root: Path, target_id: str) -> Path:
    """
    @brief      Resolve an ID-based WAV path in the character sample directory.
    @param[in]  root Active project root folder.
    @param[in]  target_id Stable voice target identifier.
    @return     Sample path with unsafe IDs encoded losslessly.
    """
    file_id = target_id if re.fullmatch(r"[a-z0-9_]+", target_id) else f"~{target_id.encode().hex()}"
    return root / "character_voice_samples" / f"{file_id}.wav"


def _retired_sample(root: Path, target_id: str, targets: list[dict[str, object]]) -> dict[Path, None]:
    """
    @brief      Plan deletion of a target's sample only when it owns the file exclusively.
    @param[in]  root Active project root folder.
    @param[in]  target_id Target whose sample changes.
    @param[in]  targets Current persisted targets.
    @return     A deletion entry, or an empty mapping for missing or shared paths.
    """
    target = voice_target_by_id(root, target_id, targets)
    if target is None or not target["sample_audio_path"]:
        return {}
    audio_path = root / str(target["sample_audio_path"])
    if not audio_path.is_file() or any(
        other is not target and other["sample_audio_path"] and root / str(other["sample_audio_path"]) == audio_path
        for other in targets
    ):
        return {}
    return {audio_path: None}


def _replace_target_sample(root: Path, target_id: str, metadata: dict[str, object], audio_bytes: bytes) -> None:
    """
    @brief      Publish one character sample and its transcript as a recoverable pair.
    @param[in]  root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @param[in]  metadata Complete sample metadata including the spoken transcript.
    @param[in]  audio_bytes Complete WAV payload.
    @exception  ValueError Raised when the target no longer exists.
    """
    original_document = _targets_path(root).read_bytes()
    targets = load_voice_plan(root)
    if voice_target_by_id(root, target_id, targets) is None:
        raise ValueError("missing_target")
    audio_path = _sample_path(root, target_id)
    updated = _target_sample_metadata_updated_targets(
        targets, target_id, audio_path.relative_to(root).as_posix(), metadata
    )
    sample_changes: dict[Path, bytes | None] = {**_retired_sample(root, target_id, targets), audio_path: audio_bytes}
    _publish_voice_targets(root, updated, original_document, sample_changes)


def _publish_voice_targets(
    root: Path,
    targets: list[dict[str, object]],
    original_document: bytes,
    sample_changes: dict[Path, bytes | None],
) -> None:
    """
    @brief      Stage and publish the target document and its changed WAV files.
    @param[in]  root Active project root folder.
    @param[in]  targets Replacement target document.
    @param[in]  original_document Original document bytes for concurrent-change detection.
    @param[in]  sample_changes WAV paths mapped to replacement bytes or None for deletion.
    """
    document = _targets_path(root)
    with TemporaryDirectory(prefix=".character-voices-stage-", dir=root) as temp_dir:
        stage = Path(temp_dir)
        changes: dict[Path, Path | None] = {}
        for path, audio_bytes in sample_changes.items():
            relative = path.relative_to(root)
            if audio_bytes is None:
                changes[relative] = None
            else:
                candidate = stage / relative
                write_bytes_atomic(candidate, audio_bytes)
                changes[relative] = candidate
        staged_document = stage / document.name
        _write_json(staged_document, targets)
        changes[document.relative_to(root)] = staged_document
        replace_project_files(root, changes, document, original_document, "character-voices")


def _target_sample_metadata_updated_targets(
    voice_targets: list[dict[str, object]],
    target_id: str,
    relative_path: str | None,
    metadata_payload: dict[str, object] | None,
) -> list[dict[str, object]]:
    """
    @brief      Build a target list with one sample metadata entry updated.
    @param[in]  voice_targets Already-loaded character-voices target payloads.
    @param[in]  target_id Target voice identifier.
    @param[in]  relative_path Project-relative sample WAV path or `None`.
    @param[in]  metadata_payload Sample metadata payload or `None` to clear it.
    @return     Updated target payload list.
    """
    normalized_target_id = str(target_id or "").strip()
    updated_targets: list[dict[str, object]] = []
    for target_payload in voice_targets:
        if str(target_payload.get("target_id", "")).strip() != normalized_target_id:
            updated_targets.append(target_payload)
            continue
        updated_targets.append(
            {
                **dict(target_payload),
                "sample_audio_path": relative_path,
                "sample_metadata": None if metadata_payload is None else dict(metadata_payload),
            }
        )
    return updated_targets


def _copied_narrator_sample_is_current(
    audio_path: Path,
    target_id: str,
    metadata_payload: dict[str, object],
    narrator_audio_bytes: bytes,
    voice_targets: list[dict[str, object]],
) -> bool:
    """
    @brief      Return whether one copied narrator sample already matches the current narrator audio and metadata.
    @param[in]  audio_path Character sample WAV path.
    @param[in]  target_id Target voice identifier.
    @param[in]  metadata_payload Expected copied narrator sample metadata.
    @param[in]  narrator_audio_bytes Current selected narrator WAV bytes.
    @param[in]  voice_targets Already-loaded character-voices target payloads.
    @return     True when the stored copied sample is already current.
    """
    target_payload = voice_target_by_id("", target_id, voice_targets)
    sample_metadata = None if not isinstance(target_payload, dict) else target_payload.get("sample_metadata")
    return (
        isinstance(sample_metadata, dict)
        and sample_metadata == metadata_payload
        and audio_path.is_file()
        and _safe_read_bytes(audio_path) == narrator_audio_bytes
    )


def _safe_read_bytes(path: Path) -> bytes | None:
    """
    @brief      Read bytes for equality checks without surfacing transient file errors.
    @param[in]  path Candidate file path.
    @return     File bytes or `None` when unavailable.
    @exception  None
    """
    try:
        return path.read_bytes()
    except OSError:
        return None


def _targets_path(project_root: str | Path) -> Path:
    """
    @brief      Execute the voice targets path helper.
    @param[in]  project_root Active project root folder.
    @return     Helper result.
    """
    return Path(project_root) / config.CHARACTER_VOICES_TARGETS_FILE_NAME


def _build_generation_request(
    runtime_available: bool,
    can_generate: bool,
    unavailable_reason: str,
    language: str,
    prompt_text: str,
    generation_mode: str | None = None,
    model_id: str | None = None,
    source_model_id: str | None = None,
    runtime_language: str | None = None,
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
    @param[in]  runtime_language Language sent to the selected VoiceWeaver model.
    @return     Derived helper result.
    """
    return {
        "runtime_available": runtime_available,
        "can_generate": can_generate,
        "unavailable_reason": unavailable_reason,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "source_model_id": source_model_id,
        "runtime_language": runtime_language,
        "language": language,
        "prompt_text": prompt_text,
    }



def _write_json(path: Path, payload: object) -> None:
    """
    @brief      Write the json.
    @param[in]  path Value for `path`.
    @param[in]  payload Optional payload processed by the helper.
    @return     None.
    """
    write_json_atomic(path, payload)


# END OF FILE
