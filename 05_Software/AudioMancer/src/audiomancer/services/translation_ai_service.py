#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file translation_ai_service.py
@brief Send and verify budgeted translation requests.
@details Owns prompt rendering, request policy identity, response shape and usage accounting.
"""

# IMPORTS

from hashlib import sha256
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import ai_budget_service, llm_provider_service, prompt_template_service, token_usage_service
from audiomancer.services.operation_runtime_service import emit_progress_update as _emit_progress
from audiomancer.services.operation_runtime_service import raise_if_cancelled
from audiomancer.translation.planning import (
    _join_translation_text_segments,
    _split_translation_source_text,
    _TranslationTextSegment,
    paragraph_count,
)

# CONSTANTS

_TRANSLATION_REPLY_SCHEMA = {
    "type": "object",
    "properties": {"translated_text": {"type": "string"}},
    "required": ["translated_text"],
    "additionalProperties": False,
}
# @brief Correction prompt appended only when a valid reply changes the source paragraph count.
_PARAGRAPH_CORRECTION = (
    "\n\nCorrect the paragraph layout: return exactly {expected} paragraphs separated by blank lines. "
    "Keep titles, bylines, and dialogue in the same paragraphs as in the source."
)
TokenUsagePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]

# PUBLIC API


def request_fingerprint(profile, system_prompt, language, instructions, budget) -> str:
    """@brief Hash request-affecting settings without storing credentials or profile data."""
    fields = (
        "backend_kind",
        "base_url",
        "model_name",
        "temperature",
        "context_window",
        "output_reserve_tokens",
        "reasoning_mode",
        "reasoning_effort",
        "supports_structured_output",
    )
    policy = [
        "translation-request-1",
        {field: profile.get(field) for field in fields},
        system_prompt,
        _render_translation_user_prompt(language, "(source)", instructions),
        budget,
        _TRANSLATION_REPLY_SCHEMA,
        _PARAGRAPH_CORRECTION,
    ]
    return "sha256:" + sha256(json.dumps(policy, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _translate_text_in_budgeted_segments(
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    source_text: str,
    target_language: str,
    system_prompt: str,
    chunk_sequence_index: int,
    total_chunks: int,
    log_path: Path,
    token_usage: TokenUsagePayload,
    budget_metadata: BudgetMetadataPayload,
    additional_translation_instructions: str,
    progress_callback=None,
    translated_chunk_count: int = 0,
    cancel_requested=None,
) -> tuple[str, TokenUsagePayload]:
    """
    @brief      Translate one chunk locally so partial segments never become checkpoints.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  source_text Canonical source text processed by the callable.
    @param[in]  target_language Requested translation target language.
    @param[in]  system_prompt Rendered system prompt for the AI request.
    @param[in]  chunk_sequence_index Zero-based position of the chunk in canonical order.
    @param[in]  total_chunks Total number of canonical chunks in the operation.
    @param[in]  log_path Filesystem path for log.
    @param[in]  token_usage Cumulative AI token-usage metadata.
    @param[in]  budget_metadata Context-window budgeting metadata for the selected profile.
    @param[in]  additional_translation_instructions Optional operator-supplied translation rules.
    @param[in]  progress_callback Optional callback receiving operation progress updates.
    @param[in]  translated_chunk_count Number of chunks with durable translated text.
    @param[in]  cancel_requested Optional callback used to query cancellation state.
    @return     Complete translated text and cumulative token-usage payload.
    @exception  ValueError Raised for invalid text-only JSON or a repeated paragraph count mismatch.
    """
    translated_segments: list[_TranslationTextSegment] = []
    cumulative_usage = token_usage
    for segment_index, source_segment in enumerate(
        _split_translation_source_text(source_text, int(budget_metadata["text_budget_tokens"])),
        start=1,
    ):
        raise_if_cancelled(cancel_requested)
        user_prompt = _render_translation_user_prompt(
            target_language,
            source_segment.text,
            additional_translation_instructions,
        )
        expected = paragraph_count(source_segment.text)
        strategy = f"{target_language}|segment {segment_index}"
        for correction in (False, True):
            if correction:
                raise_if_cancelled(cancel_requested)
                user_prompt += _PARAGRAPH_CORRECTION.format(expected=expected)
                strategy += "|paragraph correction"
            response_result = llm_provider_service.chat_json(
                ai_profile_payload,
                system_prompt,
                user_prompt,
                log_path=log_path,
                log_context={
                    "operation_kind": "translation",
                    "stage_label": "ai_translation",
                    "profile_id": str(ai_profile_payload.get("id", "")),
                    "strategy": strategy,
                    "window_index": chunk_sequence_index,
                    "window_total": total_chunks,
                    "project_id": str(manifest.get("project_id", "")),
                },
                cancel_requested=cancel_requested,
                response_schema=_TRANSLATION_REPLY_SCHEMA,
                response_schema_name="translated_text",
            )
            if isinstance(response_result, dict):
                merged_usage = token_usage_service.merge_token_usage(
                    cumulative_usage,
                    response_result.get("usage"),
                )
                cumulative_usage.clear()
                cumulative_usage.update(merged_usage)
            payload = response_result.get("payload") if isinstance(response_result, dict) else None
            if not isinstance(payload, dict) or set(payload) != {"translated_text"}:
                raise ValueError("AI translation returned an invalid text-only JSON object.")
            translated_value = payload["translated_text"]
            if not isinstance(translated_value, str) or not translated_value.strip():
                raise ValueError("AI translation returned an invalid or empty translated_text value.")
            actual = paragraph_count(translated_value)
            if actual == expected:
                break
            if correction:
                raise ValueError(
                    "AI translation returned a different number of paragraphs after retry "
                    f"(expected {expected}, received {actual})."
                )
            _emit_progress(
                progress_callback,
                translated_chunk_count,
                total_chunks,
                "AI translation is retrying a fragment to preserve paragraph breaks.",
                cumulative_usage,
            )
        translated_segments.append(
            _TranslationTextSegment(
                text=translated_value.strip(),
                continues_previous_paragraph=source_segment.continues_previous_paragraph,
            )
        )
        _emit_progress(
            progress_callback,
            translated_chunk_count,
            total_chunks,
            "AI translation in progress...",
            cumulative_usage,
        )
    return _join_translation_text_segments(translated_segments), cumulative_usage


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    target_language: str,
    system_prompt: str,
    additional_translation_instructions: str = "",
) -> BudgetMetadataPayload:
    """
    @brief      Build current-profile context budgeting for the translation request.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  target_language Requested translation target language.
    @param[in]  system_prompt Rendered system prompt for the AI request.
    @param[in]  additional_translation_instructions Optional operator-supplied translation rules.
    @return     Constructed budget metadata.
    @exception  ValueError Raised when the profile output limit cannot return one request's translation.
    """
    user_prompt_shell = _render_translation_user_prompt(
        target_language,
        "(none)",
        additional_translation_instructions,
    )
    # Reserve the correction text plus room for the paragraph-count digits.
    correction_shell = _PARAGRAPH_CORRECTION.format(expected=9_999_999_999)
    budget_metadata = ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{user_prompt_shell}{correction_shell}",
        config.DEFAULT_AI_TRANSLATION_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_AI_TRANSLATION_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_AI_TRANSLATION_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_AI_TRANSLATION_MIN_TEXT_BUDGET_TOKENS,
        "AI translation cannot run because the selected AI profile context window "
        "leaves too little room for translation input",
    )
    return {
        **budget_metadata,
        "text_budget_tokens": _reply_bounded_text_budget(
            int(budget_metadata["text_budget_tokens"]),
            int(budget_metadata["output_reserve_tokens"]),
        ),
    }


def _reply_bounded_text_budget(text_budget_tokens: int, output_reserve_tokens: int) -> int:
    """
    @brief      Bound one source-text budget by the translation its reply can return.
    @details    A translation is as long as its source, so source text the output
                limit cannot return is text the provider stops mid-reply. The
                shared budget helper reserves output tokens but never caps the
                input by them, which leaves a wide context window with a modest
                output limit asking for far more than it can answer.
    @param[in]  text_budget_tokens Source-text budget the shared helper allowed.
    @param[in]  output_reserve_tokens Reserved maximum output tokens for one request.
    @return     Source-text budget the reply can still return.
    @exception  ValueError Raised when that bound leaves less than one request needs.
    """
    reply_budget_tokens = int(output_reserve_tokens / config.DEFAULT_AI_TRANSLATION_OUTPUT_EXPANSION_FACTOR)
    if reply_budget_tokens >= text_budget_tokens:
        return text_budget_tokens
    if reply_budget_tokens < config.DEFAULT_AI_TRANSLATION_MIN_TEXT_BUDGET_TOKENS:
        raise ValueError(
            "AI translation needs more room for its reply. "
            f"The current context allows about {reply_budget_tokens} tokens for source text "
            f"and at least {config.DEFAULT_AI_TRANSLATION_MIN_TEXT_BUDGET_TOKENS} are needed. "
            "Use a larger context window."
        )
    return reply_budget_tokens


def _render_translation_user_prompt(
    target_language: str,
    source_text: str,
    additional_translation_instructions: str,
) -> str:
    """
    @brief      Render only per-request values into the translation user prompt.
    @param[in]  target_language Requested translation target language.
    @param[in]  source_text Canonical source text processed by the callable.
    @param[in]  additional_translation_instructions Optional operator-supplied translation rules.
    @return     Rendered translation user prompt.
    """
    instructions = _normalized_additional_translation_instructions(additional_translation_instructions)
    instruction_block = f"Additional translation instructions:\n{instructions}\n\n" if instructions else ""
    return prompt_template_service.render_prompt(
        "text_translation_user",
        {
            "target_language": target_language,
            "additional_translation_instructions_block": instruction_block,
            "source_text": source_text,
        },
    )


def _normalized_additional_translation_instructions(value: object) -> str:
    """@brief Normalize optional operator translation rules."""
    return "" if value is None else str(value).strip()


# END OF FILE
