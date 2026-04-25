#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# ruff: noqa: E501
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
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version 1.3.1
"""

# IMPORTS

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import narrator_definition_service, project_workspace_service, voiceweaver_runtime_service

# CONSTANTS

TARGET_KIND_NARRATOR = "narrator"
TARGET_KIND_CHARACTER = "character"

TARGET_ID_NARRATOR = "narrator"

SAMPLE_MODE_NARRATOR_REFERENCE = "narrator_reference"
SAMPLE_MODE_VOICE_DESIGNER = "voice_designer"

SAMPLE_SOURCE_VOICE_DESIGNER = "voice_designer"
SAMPLE_SOURCE_COPIED_NARRATOR = "copied_narrator"

DEFAULT_PREVIEW_TEXT_BY_LANGUAGE = {
    "en": ("The evening settled over the old house, and each voice carried a different shade of memory."),
    "ro": ("Seara s-a asezat peste casa veche, iar fiecare glas purta o alta nuanta de amintire."),
    "ja": "å¤•æš®ã‚ŒãŒå¤ã„å®¶ã‚’åŒ…ã¿ã€ãã‚Œãžã‚Œã®å£°ãŒé•ã†è¨˜æ†¶ã®è‰²ã‚’å¸¯ã³ã¦ã„ãŸã€‚",
    "ko": "ì €ë…ì´ ì˜¤ëž˜ëœ ì§‘ ìœ„ë¡œ ë‚´ë ¤ì•‰ìž, ì €ë§ˆë‹¤ì˜ ëª©ì†Œë¦¬ëŠ” ë‹¤ë¥¸ ê¸°ì–µì˜ ë¹›ì„ í’ˆê³  ìžˆì—ˆë‹¤.",
    "de": ("Der Abend senkte sich uber das alte Haus, und jede Stimme trug einen anderen Ton der Erinnerung."),
    "fr": ("Le soir est tombe sur la vieille maison, et chaque voix portait une autre nuance de memoire."),
    "ru": "Ð’ÐµÑ‡ÐµÑ€ Ð¾Ð¿ÑƒÑÑ‚Ð¸Ð»ÑÑ Ð½Ð° ÑÑ‚Ð°Ñ€Ñ‹Ð¹ Ð´Ð¾Ð¼, Ð¸ Ð² ÐºÐ°Ð¶Ð´Ð¾Ð¼ Ð³Ð¾Ð»Ð¾ÑÐµ Ð·Ð²ÑƒÑ‡Ð°Ð» ÑÐ²Ð¾Ð¹ Ð¾Ñ‚Ñ‚ÐµÐ½Ð¾Ðº Ð¿Ð°Ð¼ÑÑ‚Ð¸.",
    "pt": "A noite pousou sobre a casa antiga, e cada voz carregava um tom diferente de memoria.",
    "es": ("La tarde cayo sobre la vieja casa, y cada voz llevaba un matiz distinto de memoria."),
    "it": "La sera scese sulla vecchia casa, e ogni voce portava una diversa sfumatura di memoria.",
}


# PUBLIC API


def ensure_character_voices_files(project_root: str | Path) -> None:
    """
    @brief      Ensure character-voices files and sample folders exist for one project.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.1
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
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
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    ensure_character_voices_files(project_root)
    normalized_language = narrator_definition_service.narrator_language_code(selected_voice_language)
    try:
        manifest = project_workspace_service.load_manifest(project_root)
    except Exception:
        manifest = None
    if isinstance(manifest, dict):
        manifest["selected_voice_language"] = normalized_language
        project_workspace_service.save_manifest(manifest, project_root)
    return normalized_language


def load_voice_plan(project_root: str | Path) -> list[dict[str, object]]:
    """
    @brief      Load the persisted character-voices target list.
    @param[in]  project_root Active project root folder.
    @return     Normalized ordered voice target payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    ensure_character_voices_files(project_root)
    payload = json.loads(_targets_path(project_root).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [_normalize_voice_target(item) for item in payload if isinstance(item, dict)]


def save_voice_targets(project_root: str | Path, voice_targets: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Persist one character-voices target payload list.
    @param[in]  project_root Active project root folder.
    @param[in]  voice_targets Candidate voice target payload list.
    @return     Persisted normalized voice target list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    ensure_character_voices_files(project_root)
    normalized_targets = [_normalize_voice_target(item) for item in voice_targets if isinstance(item, dict)]
    _write_json(_targets_path(project_root), normalized_targets)
    return normalized_targets


def sync_voice_plan(
    project_root: str | Path,
    character_profiles: list[dict[str, object]],
    narrator_profile: dict[str, object] | None,
) -> list[dict[str, object]]:
    """
    @brief      Synchronize persisted character-voices targets against the current narrator and character state.
    @param[in]  project_root Active project root folder.
    @param[in]  character_profiles Persisted character profile payload list.
    @param[in]  narrator_profile Explicitly selected narrator profile payload or `None`.
    @return     Persisted normalized character-voices target list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.1
    """
    existing_targets_by_id = {
        str(target.get("target_id", "")).strip(): dict(target) for target in load_voice_plan(project_root)
    }
    synchronized_targets: list[dict[str, object]] = []
    if isinstance(narrator_profile, dict):
        existing_narrator_target = existing_targets_by_id.get(TARGET_ID_NARRATOR, {})
        synchronized_targets.append(
            _normalize_voice_target(
                {
                    **existing_narrator_target,
                    "target_id": TARGET_ID_NARRATOR,
                    "target_kind": TARGET_KIND_NARRATOR,
                    "source_profile_id": str(narrator_profile.get("profile_id", "")).strip() or None,
                    "display_name": "Narator Voice",
                    "character_id": None,
                    "prompt_text": None,
                    "default_prompt_text": None,
                    "preview_text": None,
                    "editable": False,
                    "sample_mode": SAMPLE_MODE_NARRATOR_REFERENCE,
                    "updated_at": existing_narrator_target.get("updated_at"),
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
                    "source_profile_id": None,
                    "display_name": str(character_profile.get("canonical_name", "")).strip() or target_id,
                    "character_id": normalized_character_id,
                    "prompt_text": (str(existing_target.get("prompt_text", "")).strip() or default_prompt_text),
                    "default_prompt_text": default_prompt_text,
                    "preview_text": (
                        str(existing_target.get("preview_text", "")).strip()
                        or preview_text_for_language(narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE)
                    ),
                    "editable": True,
                    "sample_mode": SAMPLE_MODE_VOICE_DESIGNER,
                    "updated_at": existing_target.get("updated_at"),
                }
            )
        )
    return save_voice_targets(project_root, synchronized_targets)


def voice_target_by_id(project_root: str | Path, target_id: str | None) -> dict[str, object] | None:
    """
    @brief      Resolve one persisted character-voices target by identifier.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @return     Matching voice target payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    normalized_target_id = str(target_id or "").strip()
    if not normalized_target_id:
        return None
    return next(
        (
            target
            for target in load_voice_plan(project_root)
            if str(target.get("target_id", "")).strip() == normalized_target_id
        ),
        None,
    )


def reset_target_prompt(project_root: str | Path, target_id: str, default_prompt_text: str) -> dict[str, object]:
    """
    @brief      Reset one editable character target prompt to the current derived default and clear its sample.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @param[in]  default_prompt_text Derived default voice-designer prompt.
    @return     Persisted updated target payload.
    @exception  ValueError Raised when the target is missing or not editable.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    return _update_target_prompt(project_root, target_id, default_prompt_text, update_default_prompt=True)


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.2.0
    """
    return _update_target_prompt(
        project_root,
        target_id,
        prompt_text,
        update_default_prompt=False,
        preview_text=preview_text,
    )


def begin_target_prompt_edit(project_root: str | Path, target_id: str) -> dict[str, object]:
    """
    @brief      Prepare one editable target for prompt editing by clearing any stored sample.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @return     Target payload prepared for edit mode.
    @exception  ValueError Raised when the target is missing or not editable.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    target_payload = voice_target_by_id(project_root, target_id)
    if target_payload is None:
        raise ValueError("missing_target")
    if not bool(target_payload.get("editable", False)):
        raise ValueError("readonly_target")
    delete_target_sample(project_root, target_id)
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    capability_matrix = voiceweaver_runtime_service.build_capability_matrix(discovered_models)
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
    if not bool(capability_matrix.get("minimum_qwen_ready", False)):
        missing_capabilities = list(capability_matrix.get("missing_qwen_capabilities", []))
        return _build_generation_request(
            False,
            False,
            (
                "Cannot generate a sample because Qwen3 TTS minimum capabilities are missing: "
                + ", ".join(missing_capabilities)
                + "."
            ),
            normalized_language,
            prompt_text,
        )
    voice_designer_model = _first_model(capability_matrix.get("qwen_voice_designer_models", []))
    if voice_designer_model is None:
        return _build_generation_request(
            False,
            False,
            "No healthy Qwen3 Voice Designer model is currently available.",
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
    )


def character_target_id(character_id: str) -> str:
    """
    @brief      Build the stable character-voices target identifier for one character.
    @param[in]  character_id Persisted character identifier.
    @return     Stable character-voices character target identifier.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    return f"character_{str(character_id).strip()}"


def build_character_default_prompt(character_profile: dict[str, object]) -> str:
    """
    @brief      Build one deterministic English voice-designer prompt from one persisted character profile.
    @param[in]  character_profile Persisted character profile payload.
    @return     Derived voice-designer prompt text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    stored_voice_definition_prompt = str(character_profile.get("voice_definition_prompt", "")).strip()
    if stored_voice_definition_prompt:
        return stored_voice_definition_prompt
    character_name = str(character_profile.get("canonical_name", "Character")).strip() or "Character"
    descriptor_parts = [
        _prefixed_text("Gender hint", character_profile.get("gender_hint")),
        _prefixed_text("Age band", character_profile.get("age_band")),
        _prefixed_text("Role", character_profile.get("role_summary")),
        _prefixed_text("Description", character_profile.get("description")),
        _prefixed_text("Temperament", character_profile.get("temperament")),
        _prefixed_text("Social status", character_profile.get("social_status")),
        _prefixed_text("Speaking style", character_profile.get("speaking_style")),
        _prefixed_text("Accent or dialect", character_profile.get("accent_or_dialect_hints")),
        _prefixed_text("Voice notes", character_profile.get("voice_notes")),
    ]
    cleaned_descriptors = [part for part in descriptor_parts if part]
    if cleaned_descriptors:
        return (
            f"Create a consistent spoken voice for {character_name}. "
            + " ".join(cleaned_descriptors)
            + " Keep the delivery suitable for repeated dialogue narration, with clear diction and stable identity."
        ).strip()
    return (
        f"Create a consistent spoken voice for {character_name} with clear diction, stable identity, "
        "and delivery suitable for repeated dialogue narration."
    )


def preview_text_for_language(voice_language: object) -> str:
    """
    @brief      Resolve one deterministic sample preview text for the selected character-voices language.
    @param[in]  voice_language Candidate selected voice language.
    @return     Stable localized preview text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    stored_preview_text = str(target_payload.get("preview_text", "")).strip()
    return stored_preview_text or preview_text_for_language(voice_language)


def target_sample_paths(project_root: str | Path, target_id: str) -> tuple[Path, Path]:
    """
    @brief      Resolve the audio and aggregate metadata sample paths for one character-voices target.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @return     Tuple of WAV path and `characters_voice.json` metadata path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    normalized_target_id = str(target_id).strip()
    target_payload = voice_target_by_id(project_root, normalized_target_id)
    if isinstance(target_payload, dict) and str(target_payload.get("sample_audio_path", "") or "").strip():
        audio_path = Path(project_root) / str(target_payload.get("sample_audio_path", "")).strip()
    else:
        audio_name_source = (
            target_payload.get("display_name", normalized_target_id) if isinstance(target_payload, dict) else target_id
        )
        audio_path = Path(project_root) / f"audio_{_normalized_audio_name(audio_name_source)}.wav"
    return (
        audio_path,
        _targets_path(project_root),
    )


def load_target_sample_metadata(project_root: str | Path, target_id: str) -> dict[str, object] | None:
    """
    @brief      Load the persisted sample metadata for one character-voices target.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @return     Metadata payload or `None` when unavailable.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    target_payload = voice_target_by_id(project_root, target_id)
    if not isinstance(target_payload, dict):
        return None
    payload = target_payload.get("sample_metadata")
    return dict(payload) if isinstance(payload, dict) else None


def has_target_sample(project_root: str | Path, target_id: str) -> bool:
    """
    @brief      Return whether one character-voices target currently has a persisted sample pair.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @return     `True` when the sample WAV exists and `characters_voice.json` has sample metadata.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    audio_path, _metadata_path = target_sample_paths(project_root, target_id)
    return audio_path.is_file() and load_target_sample_metadata(project_root, target_id) is not None


def delete_target_sample(project_root: str | Path, target_id: str) -> None:
    """
    @brief      Delete the persisted sample artifacts for one character-voices target.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    audio_path, _metadata_path = target_sample_paths(project_root, target_id)
    if audio_path.exists():
        audio_path.unlink()
    _update_target_sample_metadata(project_root, target_id, None, None)


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    ensure_character_voices_files(project_root)
    target_id = str(target_payload.get("target_id", "")).strip()
    delete_target_sample(project_root, target_id)
    audio_path, _metadata_path = target_sample_paths(project_root, target_id)
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
        "generated_at": _utc_now_iso(),
        "runtime_result_summary": str(runtime_result_summary).strip(),
    }
    audio_path.write_bytes(audio_bytes)
    _update_target_sample_metadata(
        project_root,
        target_id,
        relative_path=str(audio_path.relative_to(Path(project_root))),
        metadata_payload=metadata_payload,
    )
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    ensure_character_voices_files(project_root)
    if not load_voice_plan(project_root):
        save_voice_targets(project_root, character_targets)
    narrator_audio_path, _narrator_metadata_path = narrator_definition_service.selected_narrator_sample_paths(
        project_root
    )
    narrator_metadata = narrator_definition_service.load_selected_narrator_sample_metadata(project_root)
    if not narrator_audio_path.is_file() or narrator_metadata is None:
        for target_payload in character_targets:
            target_id = str(target_payload.get("target_id", "")).strip()
            sample_metadata = load_target_sample_metadata(project_root, target_id)
            if (
                isinstance(sample_metadata, dict)
                and sample_metadata.get("sample_source") == SAMPLE_SOURCE_COPIED_NARRATOR
            ):
                delete_target_sample(project_root, target_id)
        return
    narrator_audio_bytes = narrator_audio_path.read_bytes()
    narrator_language = narrator_definition_service.narrator_language_code(
        narrator_metadata.get("language", voice_language),
    )
    narrator_preview_text = str(narrator_metadata.get("preview_text", "")).strip()
    narrator_generation_mode = str(narrator_metadata.get("generation_mode", "")).strip()
    narrator_source_model_id = str(narrator_metadata.get("source_model_id", "")).strip() or None
    narrator_runtime_summary = str(narrator_metadata.get("runtime_result_summary", "")).strip()
    narrator_generated_at = str(narrator_metadata.get("generated_at", "")).strip() or _utc_now_iso()
    for target_payload in character_targets:
        target_id = str(target_payload.get("target_id", "")).strip()
        audio_path, _metadata_path = target_sample_paths(project_root, target_id)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
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
            "generated_at": narrator_generated_at,
            "runtime_result_summary": narrator_runtime_summary,
        }
        audio_path.write_bytes(narrator_audio_bytes)
        _update_target_sample_metadata(
            project_root,
            target_id,
            relative_path=str(audio_path.relative_to(Path(project_root))),
            metadata_payload=metadata_payload,
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    narrator_audio_path, _narrator_metadata_path = narrator_definition_service.selected_narrator_sample_paths(
        project_root
    )
    if (
        not narrator_audio_path.is_file()
        or narrator_definition_service.load_selected_narrator_sample_metadata(project_root) is None
    ):
        return False
    character_targets = [
        target for target in voice_targets if str(target.get("target_kind", "")).strip() == TARGET_KIND_CHARACTER
    ]
    return all(
        has_target_sample(project_root, str(target.get("target_id", "")).strip()) for target in character_targets
    )


def selected_narrator_sample_exists(project_root: str | Path) -> bool:
    """
    @brief      Return whether the selected narrator sample exists for the current project.
    @param[in]  project_root Active project root folder.
    @return     `True` when the selected narrator WAV and metadata are both present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    audio_path, _metadata_path = narrator_definition_service.selected_narrator_sample_paths(project_root)
    return (
        audio_path.is_file()
        and narrator_definition_service.load_selected_narrator_sample_metadata(project_root) is not None
    )


def selected_narrator_sample_metadata(project_root: str | Path) -> dict[str, object] | None:
    """
    @brief      Load the selected narrator sample metadata reused by the Character Voices page.
    @param[in]  project_root Active project root folder.
    @return     Selected narrator metadata payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    return narrator_definition_service.load_selected_narrator_sample_metadata(project_root)


# LOCAL HELPERS


def _update_target_prompt(
    project_root: str | Path,
    target_id: str,
    prompt_text: str,
    update_default_prompt: bool,
    preview_text: str | None = None,
) -> dict[str, object]:
    """
    @brief      Update the target prompt.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target identifier.
    @param[in]  prompt_text Text value for `prompt_text`.
    @param[in]  update_default_prompt Value for `update_default_prompt`.
    @param[in]  preview_text Text value for `preview_text`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_prompt = str(prompt_text).strip()
    if not normalized_prompt:
        raise ValueError("empty_prompt")
    normalized_preview_text = None if preview_text is None else str(preview_text).strip()
    if preview_text is not None and not normalized_preview_text:
        raise ValueError("empty_preview_text")
    voice_targets = load_voice_plan(project_root)
    updated_target = None
    normalized_targets: list[dict[str, object]] = []
    for target_payload in voice_targets:
        if str(target_payload.get("target_id", "")).strip() != str(target_id).strip():
            normalized_targets.append(target_payload)
            continue
        if not bool(target_payload.get("editable", False)):
            raise ValueError("readonly_target")
        updated_target = _normalize_voice_target(
            {
                **dict(target_payload),
                "prompt_text": normalized_prompt,
                "default_prompt_text": (
                    normalized_prompt if update_default_prompt else target_payload.get("default_prompt_text")
                ),
                "preview_text": (
                    target_payload.get("preview_text") if preview_text is None else normalized_preview_text
                ),
                "updated_at": _utc_now_iso(),
            }
        )
        normalized_targets.append(updated_target)
    if updated_target is None:
        raise ValueError("missing_target")
    save_voice_targets(project_root, normalized_targets)
    delete_target_sample(project_root, target_id)
    return updated_target


def _normalize_voice_target(target_payload: dict[str, object]) -> dict[str, object]:
    """
    @brief      Normalize the voice target.
    @param[in]  target_payload Payload for `target_payload`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
        "source_profile_id": _optional_string(target_payload.get("source_profile_id")),
        "display_name": normalized_display_name,
        "character_id": _optional_string(target_payload.get("character_id")),
        "prompt_text": prompt_text,
        "default_prompt_text": default_prompt_text,
        "preview_text": preview_text,
        "editable": bool(target_payload.get("editable", normalized_target_kind == TARGET_KIND_CHARACTER)),
        "sample_mode": str(
            target_payload.get(
                "sample_mode",
                SAMPLE_MODE_NARRATOR_REFERENCE
                if normalized_target_kind == TARGET_KIND_NARRATOR
                else SAMPLE_MODE_VOICE_DESIGNER,
            )
        ).strip(),
        "sample_audio_path": _optional_string(target_payload.get("sample_audio_path")),
        "sample_metadata": (
            dict(target_payload.get("sample_metadata"))
            if isinstance(target_payload.get("sample_metadata"), dict)
            else None
        ),
        "updated_at": None if target_payload.get("updated_at") in (None, "") else str(target_payload.get("updated_at")),
    }


def _update_target_sample_metadata(
    project_root: str | Path,
    target_id: str,
    relative_path: str | None,
    metadata_payload: dict[str, object] | None,
) -> None:
    """
    @brief      Store or clear one character-voices sample metadata entry in `characters_voice.json`.
    @param[in]  project_root Active project root folder.
    @param[in]  target_id Target voice identifier.
    @param[in]  relative_path Project-relative sample WAV path or `None`.
    @param[in]  metadata_payload Sample metadata payload or `None` to clear it.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    normalized_target_id = str(target_id or "").strip()
    voice_targets = load_voice_plan(project_root)
    updated_targets: list[dict[str, object]] = []
    target_found = False
    for target_payload in voice_targets:
        if str(target_payload.get("target_id", "")).strip() != normalized_target_id:
            updated_targets.append(target_payload)
            continue
        target_found = True
        updated_targets.append(
            {
                **dict(target_payload),
                "sample_audio_path": relative_path,
                "sample_metadata": None if metadata_payload is None else dict(metadata_payload),
            }
        )
    if not target_found and metadata_payload is not None:
        updated_targets.append(
            _normalize_voice_target(
                {
                    **dict(metadata_payload),
                    "target_id": normalized_target_id,
                    "sample_audio_path": relative_path,
                    "sample_metadata": dict(metadata_payload),
                }
            )
        )
    save_voice_targets(project_root, updated_targets)


def _targets_path(project_root: str | Path) -> Path:
    """
    @brief      Execute the voice targets path helper.
    @param[in]  project_root Active project root folder.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return Path(project_root) / config.CHARACTER_VOICES_TARGETS_FILE_NAME


def _selected_language_path(project_root: str | Path) -> Path:
    """
    @brief      Execute the selected language path helper.
    @param[in]  project_root Active project root folder.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return Path(project_root) / config.PROJECT_MANIFEST_FILE_NAME


def _audio_samples_root(project_root: str | Path) -> Path:
    """
    @brief      Execute the audio samples root helper.
    @param[in]  project_root Active project root folder.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return Path(project_root)


def _normalized_audio_name(value: object) -> str:
    """
    @brief      Normalize one voice target value for a root-level audio file name.
    @param[in]  value Candidate target identifier or name.
    @return     Filesystem-safe lowercase token.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    normalized = "".join(character.lower() if character.isalnum() else "_" for character in str(value).strip())
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or "voice"


def _build_generation_request(
    runtime_available: bool,
    can_generate: bool,
    unavailable_reason: str,
    language: str,
    prompt_text: str,
    generation_mode: str | None = None,
    model_id: str | None = None,
    source_model_id: str | None = None,
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
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return {
        "runtime_available": runtime_available,
        "can_generate": can_generate,
        "unavailable_reason": unavailable_reason,
        "generation_mode": generation_mode,
        "model_id": model_id,
        "source_model_id": source_model_id,
        "language": language,
        "prompt_text": prompt_text,
    }


def _first_model(model_entries: list[dict[str, object]]) -> dict[str, object] | None:
    """
    @brief      Return the first model.
    @param[in]  model_entries Value for `model_entries`.
    @return     Resolved helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return None if not model_entries else deepcopy(model_entries[0])


def _optional_string(value: object) -> str | None:
    """
    @brief      Resolve the optional string.
    @param[in]  value Candidate value.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if value in (None, ""):
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def _prefixed_text(prefix: str, value: object) -> str:
    """
    @brief      Execute the prefixed text helper.
    @param[in]  prefix Value for `prefix`.
    @param[in]  value Candidate value.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    normalized_value = str(value or "").strip()
    return "" if not normalized_value else f"{prefix}: {normalized_value}."


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


def _utc_now_iso() -> str:
    """
    @brief      Execute the utc now iso helper.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# END OF FILE
