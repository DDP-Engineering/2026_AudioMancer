#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file tts_budget_service.py
@brief Shared TTS generation-budget helpers for AudioMancer.
@details Resolves a conservative text-splitting budget from cached VoiceWeaver
         model metadata, with configuration fallbacks before runtime generation.
"""

# IMPORTS

from math import ceil

from audiomancer import config
from audiomancer.services import voiceweaver_runtime_service

# PUBLIC API


def resolve_cached_tts_budget(
    discovered_models: list[dict[str, object]] | None,
    max_generation_tokens: int | None = None,
    *,
    voice_language: str | None = None,
    operation: str = "clone",
) -> dict[str, object]:
    """
    @brief      Resolve a cached or fallback TTS splitting budget.
    @param[in]  discovered_models Cached VoiceWeaver discovered-model payloads.
    @param[in]  max_generation_tokens Optional operator ceiling that may only lower the budget.
    @return     Budget metadata for prompt guidance and validation.
    @exception  None
    """
    if voice_language is not None:
        model = voiceweaver_runtime_service.resolve_tts_model(discovered_models or [], operation, voice_language)
        discovered_models = [model] if model is not None else []
    for model_payload in discovered_models or []:
        if not isinstance(model_payload, dict):
            continue
        recommended_tokens, audio_seconds_per_token = model_generation_limits(model_payload)
        hard_token_maximum = model_hard_token_maximum(model_payload)
        if recommended_tokens is not None:
            return _budget_payload(
                recommended_tokens,
                "range_recommended_maximum",
                audio_seconds_per_token,
                max_generation_tokens,
                hard_token_maximum,
            )
        for budget_source, parameters in (
            ("default_model_parameters", model_payload.get("default_model_parameters")),
            ("range_default", _parameter_range_default(model_payload.get("generation_parameter_ranges"))),
        ):
            token_budget = _positive_int_from_mapping(parameters, "max_new_tokens")
            if token_budget is not None:
                return _budget_payload(
                    token_budget,
                    budget_source,
                    audio_seconds_per_token,
                    max_generation_tokens,
                    hard_token_maximum,
                )
    return _budget_payload(
        config.DEFAULT_TTS_NARRATOR_ONLY_TOKEN_BUDGET,
        "config_default",
        None,
        max_generation_tokens,
        None,
    )


def resolve_generation_token_limit(settings_payload: dict[str, object] | None) -> int:
    """
    @brief      Resolve the operator ceiling on the generation-token budget for one block.
    @param[in]  settings_payload Optional application settings payload.
    @return     Positive operator token ceiling, clamped to the selectable range.
    @exception  None
    """
    configured_tokens = config.DEFAULT_SPEECH_BLOCK_MAX_GENERATION_TOKENS
    if isinstance(settings_payload, dict):
        try:
            configured_tokens = int(
                settings_payload.get(
                    "speech_block_max_generation_tokens",
                    config.DEFAULT_SPEECH_BLOCK_MAX_GENERATION_TOKENS,
                )
            )
        except (TypeError, ValueError):
            configured_tokens = config.DEFAULT_SPEECH_BLOCK_MAX_GENERATION_TOKENS
    return min(
        max(configured_tokens, int(config.SPEECH_BLOCK_MAX_GENERATION_TOKENS_MINIMUM)),
        int(config.SPEECH_BLOCK_MAX_GENERATION_TOKENS_MAXIMUM),
    )


def resolve_clone_sampling_parameters(settings_payload: dict[str, object] | None) -> dict[str, float | int]:
    """
    @brief      Resolve the operator sampling parameters sent with every clone-from-prompt request.
    @param[in]  settings_payload Optional application settings payload.
    @return     Talker temperature plus sub-talker temperature, top-k and top-p, clamped to their ranges.
    @exception  None
    """
    settings = settings_payload if isinstance(settings_payload, dict) else {}
    return {
        "temperature": _clamped_float(
            settings.get("speech_block_clone_temperature"),
            config.DEFAULT_SPEECH_BLOCK_CLONE_TEMPERATURE,
            config.SPEECH_BLOCK_CLONE_TEMPERATURE_RANGE,
        ),
        "subtalker_temperature": _clamped_float(
            settings.get("speech_block_clone_subtalker_temperature"),
            config.DEFAULT_SPEECH_BLOCK_CLONE_SUBTALKER_TEMPERATURE,
            config.SPEECH_BLOCK_CLONE_TEMPERATURE_RANGE,
        ),
        "subtalker_top_k": int(
            _clamped_float(
                settings.get("speech_block_clone_subtalker_top_k"),
                config.DEFAULT_SPEECH_BLOCK_CLONE_SUBTALKER_TOP_K,
                config.SPEECH_BLOCK_CLONE_TOP_K_RANGE,
            )
        ),
        "subtalker_top_p": _clamped_float(
            settings.get("speech_block_clone_subtalker_top_p"),
            config.DEFAULT_SPEECH_BLOCK_CLONE_SUBTALKER_TOP_P,
            config.SPEECH_BLOCK_CLONE_TOP_P_RANGE,
        ),
    }


def _clamped_float(value: object, default: float | int, value_range: tuple[float, float]) -> float:
    """
    @brief      Coerce one setting to a float inside its range, falling back to the default when malformed.
    @param[in]  value Candidate setting value.
    @param[in]  default Value used when the candidate is missing or not numeric.
    @param[in]  value_range Inclusive minimum and maximum.
    @return     Clamped float value.
    @exception  None
    """
    try:
        resolved = float(default) if value is None or isinstance(value, bool) else float(value)
    except (TypeError, ValueError):
        resolved = float(default)
    return min(max(resolved, float(value_range[0])), float(value_range[1]))


def model_generation_limits(model_payload: object) -> tuple[int | None, float | None]:
    """
    @brief      Extract the runtime-reported generation limits from one discovered-model payload.
    @details    The recommended maximum is the planning budget the runtime advertises for a model,
                bounded by the hard maximum it refuses to exceed.
    @param[in]  model_payload Candidate discovered-model payload.
    @return     Tuple of the recommended token budget and the audio seconds one token represents,
                each `None` when the runtime does not report it.
    @exception  None
    """
    token_range = _token_generation_range(model_payload)
    recommended_tokens = _positive_int_from_mapping(token_range, "recommended_maximum")
    hard_maximum_tokens = _positive_int_from_mapping(token_range, "hard_maximum")
    if recommended_tokens is not None and hard_maximum_tokens is not None:
        recommended_tokens = min(recommended_tokens, hard_maximum_tokens)
    return recommended_tokens, _positive_float_from_mapping(token_range, "approx_audio_seconds_per_token")


def model_hard_token_maximum(model_payload: object) -> int | None:
    """
    @brief      Extract the token maximum the runtime reports the model will not exceed.
    @details    This is the only length past which generation itself fails, so it is the only
                threshold that may divide an otherwise unbreakable span of text.
    @param[in]  model_payload Candidate discovered-model payload.
    @return     Positive hard token maximum, or `None` when the runtime does not report one.
    @exception  None
    """
    return _positive_int_from_mapping(_token_generation_range(model_payload), "hard_maximum")


def selected_text_character_limit(
    settings_payload: dict[str, object] | None, voice_language: str | None = None,
) -> int:
    """
    @brief      Resolve an approximate selected speech text limit in characters.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  voice_language Speech language of the current project, when known.
    @return     Approximate safe character limit for the selected clone model.
    @exception  None
    """
    discovered_models = []
    if isinstance(settings_payload, dict):
        raw_models = settings_payload.get("tts_runtime_discovered_models", [])
        if isinstance(raw_models, list):
            discovered_models = [model for model in raw_models if isinstance(model, dict)]
    budget_payload = resolve_cached_tts_budget(
        discovered_models,
        resolve_generation_token_limit(settings_payload),
        voice_language=voice_language,
    )
    return int(budget_payload.get("safe_word_count", 0) or 0) * 6


def estimated_safe_word_count(budget_payload: dict[str, object]) -> int:
    """
    @brief      Return the safe narrator-only word count from one budget payload.
    @param[in]  budget_payload Resolved TTS budget payload.
    @return     Safe word count.
    @exception  None
    """
    return max(1, int(float(budget_payload.get("split_audio_seconds_budget", 0.0)) * _words_per_audio_second()))


def estimated_word_count(text: str) -> int:
    """
    @brief      Estimate the spoken word count for validation.
    @param[in]  text Candidate text span.
    @return     Word count estimate.
    @exception  None
    """
    return len([word for word in str(text).split() if word.strip()])


def estimate_budget_units(text: str) -> int:
    """
    @brief      Estimate spoken budget units for one text span, in word-equivalents.
    @details    Supported Latin and Cyrillic target text is budgeted by word count.
    @param[in]  text Candidate text span.
    @return     Conservative budget-unit count.
    @exception  None
    """
    normalized_text = str(text).strip()
    if not normalized_text:
        return 0
    return max(1, estimated_word_count(normalized_text))


def preview_word_bounds() -> tuple[int, int]:
    """
    @brief      Resolve the accepted voice-preview length range, in estimated spoken words.
    @details    Shared by narrator generation, character synthesis, the canonical per-language
                defaults, and both profile editors, so one configured duration range governs every
                voice-clone reference.
    @return     Tuple of minimum and maximum accepted spoken-word counts.
    @exception  None
    """
    words_per_second = _words_per_audio_second()
    minimum_words = max(1, ceil(float(config.DEFAULT_VOICE_PREVIEW_MIN_AUDIO_SECONDS) * words_per_second))
    target_maximum_words = ceil(float(config.DEFAULT_VOICE_PREVIEW_TARGET_AUDIO_SECONDS) * words_per_second)
    maximum_words = target_maximum_words + int(config.DEFAULT_VOICE_PREVIEW_WORD_OVERAGE_TOLERANCE)
    return minimum_words, max(minimum_words, maximum_words)


def preview_text_range_error(preview_text: object) -> dict[str, int] | None:
    """
    @brief      Report why one voice preview text falls outside the accepted length range.
    @details    Only length is judged; line breaks are spoken as pauses and are accepted.
    @param[in]  preview_text Candidate voice preview text.
    @return     Mapping of the measured word count and accepted bounds, or None when acceptable.
    @exception  None
    """
    minimum_words, maximum_words = preview_word_bounds()
    word_count = estimated_word_count(str(preview_text or ""))
    if minimum_words <= word_count <= maximum_words:
        return None
    return {"word_count": word_count, "minimum_words": minimum_words, "maximum_words": maximum_words}


# LOCAL HELPERS


def _budget_payload(
    token_budget: int,
    budget_source: str,
    audio_seconds_per_token: float | None,
    max_generation_tokens: int | None,
    hard_token_maximum: int | None = None,
) -> dict[str, object]:
    """
    @brief      Build one normalized TTS budget payload carrying both splitting thresholds.
    @details    The operator ceiling is applied to the token budget before anything is derived
                from it, so audio seconds, split seconds and the safe word count all follow from
                the one token number the runtime is normally asked for. The hard maximum is
                derived separately and never lowered by the operator, because it marks where
                generation fails rather than where the operator prefers blocks to end.
    @param[in]  token_budget Positive model token budget.
    @param[in]  budget_source Stable source token.
    @param[in]  audio_seconds_per_token Runtime-reported per-token audio rate, or `None`.
    @param[in]  max_generation_tokens Optional operator ceiling that may only lower the budget.
    @param[in]  hard_token_maximum Runtime-reported hard token maximum, or `None` when unreported.
    @return     Budget payload.
    @exception  None
    """
    operator_token_maximum = max_generation_tokens if isinstance(max_generation_tokens, int) else 0
    model_token_budget = int(token_budget)
    effective_token_budget = model_token_budget
    if operator_token_maximum > 0:
        effective_token_budget = min(effective_token_budget, operator_token_maximum)
    hard_token_budget = max(model_token_budget, int(hard_token_maximum or 0))
    seconds_per_token = audio_seconds_per_token or _audio_seconds_per_token()
    audio_seconds_budget = effective_token_budget * seconds_per_token
    split_audio_seconds_budget = audio_seconds_budget * _split_safety_factor()
    hard_split_audio_seconds_budget = hard_token_budget * seconds_per_token * _split_safety_factor()
    return {
        "operator_token_maximum": operator_token_maximum,
        "model_token_budget": effective_token_budget,
        "hard_token_maximum": hard_token_budget,
        "model_audio_seconds_budget": audio_seconds_budget,
        "split_audio_seconds_budget": split_audio_seconds_budget,
        "hard_split_audio_seconds_budget": hard_split_audio_seconds_budget,
        "safe_word_count": max(1, int(split_audio_seconds_budget * _words_per_audio_second())),
        "hard_word_count": max(1, int(hard_split_audio_seconds_budget * _words_per_audio_second())),
        "approx_audio_seconds_per_token": seconds_per_token,
        "split_safety_factor": _split_safety_factor(),
        "model_budget_source": budget_source,
    }


def _parameter_range_default(value: object) -> dict[str, object]:
    """
    @brief      Extract default generation parameters from one model range payload.
    @param[in]  value Candidate generation-parameter range mapping.
    @return     Default parameter mapping.
    @exception  None
    """
    if not isinstance(value, dict):
        return {}
    default_parameters: dict[str, object] = {}
    for parameter_name, range_payload in value.items():
        if isinstance(range_payload, dict) and "default" in range_payload:
            default_parameters[str(parameter_name)] = range_payload["default"]
    return default_parameters


def _positive_int_from_mapping(value: object, field_name: str) -> int | None:
    """
    @brief      Resolve one positive integer field from a mapping.
    @param[in]  value Candidate mapping.
    @param[in]  field_name Field name to read.
    @return     Positive integer or `None`.
    @exception  None
    """
    if not isinstance(value, dict):
        return None
    try:
        candidate = int(value.get(field_name, 0))
    except (TypeError, ValueError):
        return None
    return candidate if candidate > 0 else None


def _positive_float_from_mapping(value: object, field_name: str) -> float | None:
    """
    @brief      Resolve one positive float field from a mapping.
    @param[in]  value Candidate mapping.
    @param[in]  field_name Field name to read.
    @return     Positive float or `None`.
    @exception  None
    """
    if not isinstance(value, dict):
        return None
    try:
        candidate = float(value.get(field_name, 0.0))
    except (TypeError, ValueError):
        return None
    return candidate if candidate > 0.0 else None


def _token_generation_range(model_payload: object) -> dict[str, object]:
    """
    @brief      Extract the reported `max_new_tokens` range from one discovered-model payload.
    @param[in]  model_payload Candidate discovered-model payload.
    @return     Token range mapping, or an empty mapping.
    @exception  None
    """
    if not isinstance(model_payload, dict):
        return {}
    parameter_ranges = model_payload.get("generation_parameter_ranges")
    if not isinstance(parameter_ranges, dict):
        return {}
    token_range = parameter_ranges.get("max_new_tokens")
    return dict(token_range) if isinstance(token_range, dict) else {}


def _audio_seconds_per_token() -> float:
    """
    @brief      Return configured audio seconds represented by one generation token.
    @return     Positive seconds-per-token estimate.
    @exception  None
    """
    return float(config.DEFAULT_TTS_APPROX_AUDIO_SECONDS_PER_TOKEN)


def _split_safety_factor() -> float:
    """
    @brief      Return configured TTS split safety factor.
    @return     Safety factor.
    @exception  None
    """
    return float(config.DEFAULT_TTS_SPLIT_SAFETY_FACTOR)


def _words_per_audio_second() -> float:
    """
    @brief      Return configured spoken words per generated audio second.
    @return     Words-per-second estimate.
    @exception  None
    """
    return float(config.DEFAULT_TTS_WORDS_PER_AUDIO_SECOND)


# END OF FILE
