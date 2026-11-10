#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file       speech_blocks_generation_service.py
@brief      Generate reviewable Speech Blocks for one chunk.
@details    Owns model request preparation, deterministic narration and optional ambience.
            Project persistence is delegated to the caller through a progress callback.
"""

# IMPORTS

from dataclasses import dataclass
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    ai_budget_service,
    llm_provider_service,
    narrator_definition_service,
    prompt_template_service,
    speech_blocks_narrator_split_service,
    speech_blocks_normalization_service,
    speech_blocks_text_split_service,
    token_usage_service,
)
from audiomancer.services.operation_runtime_service import OperationCancelledError, raise_if_cancelled

# CONSTANTS

_SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT = "direct_blocks"
_DIRECT_BLOCK_PROMPT_NAMES = ("speech_blocks_system", "speech_blocks_user")
_SPEECH_BLOCKS_DIRECT_SOURCE_TOKEN_CAP = 2000
_NARRATOR_SPEAKER_ID = speech_blocks_normalization_service.NARRATOR_SPEAKER_ID
_NARRATOR_DISPLAY_NAME = speech_blocks_normalization_service.NARRATOR_DISPLAY_NAME
SPEAKER_KIND_NARRATOR = speech_blocks_normalization_service.SPEAKER_KIND_NARRATOR
SPEAKER_KIND_OPERATION = speech_blocks_normalization_service.SPEAKER_KIND_OPERATION
CONTENT_KIND_NARRATION = speech_blocks_normalization_service.CONTENT_KIND_NARRATION
CONTENT_KIND_SCENE_AMBIENCE = speech_blocks_normalization_service.CONTENT_KIND_SCENE_AMBIENCE
_build_speech_block_payload = speech_blocks_normalization_service.build_speech_block_payload
_normalize_chunk_blocks = speech_blocks_normalization_service.normalize_chunk_blocks
_normalize_warning_flags = speech_blocks_normalization_service.normalize_warning_flags
_operation_display_name = speech_blocks_normalization_service.operation_display_name
_renumber_single_chunk_blocks = speech_blocks_normalization_service.renumber_chunk_blocks
_resolve_narrator_only_budget = speech_blocks_normalization_service.resolve_narrator_only_budget
_safe_tts_word_count = speech_blocks_normalization_service.safe_tts_word_count
_speech_block_warning_reason = speech_blocks_normalization_service.speech_block_warning_reason
_split_text_for_ai_context_budget = speech_blocks_text_split_service.split_text_for_ai_context_budget

# DATA MODELS

SpeechBlockPayload = dict[str, object]
TokenUsagePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]


@dataclass(frozen=True)
class ChunkGeneration:
    """@brief Prepared inputs reused by every chunk in one generation operation."""

    ai_profile: dict[str, object]
    system_prompt: str
    source_language: str
    speaker_catalog: dict[str, dict[str, object]]
    voice_assignment_mode: str
    tts_budget: dict[str, object]
    budget_metadata: BudgetMetadataPayload
    instructions: str
    scene_ambience_settings: dict[str, object]


class ChunkGenerationRefusedError(RuntimeError):
    """@brief Identify a chunk whose speech request was refused."""

    def __init__(self, chunk_id: str) -> None:
        """
        @brief      Carry the refused source chunk identifier.
        @param[in]  chunk_id Source chunk identifier the provider refused.
        @return     None.
        @exception  None
        """
        self.chunk_id = str(chunk_id).strip()
        super().__init__(self.chunk_id)



# PUBLIC API


def requires_ai_profile(voice_assignment_mode: str, scene_ambience_enabled: bool) -> bool:
    """@brief Return whether speech or optional ambience needs a model."""
    return voice_assignment_mode != "same_narrator" or scene_ambience_enabled


def prepare_chunk_generation(
    ai_profile: dict[str, object],
    source_language: str,
    speaker_catalog: dict[str, dict[str, object]],
    voice_assignment_mode: str,
    settings_payload: dict[str, object] | None,
    instructions: str,
    scene_ambience_settings: dict[str, object],
) -> ChunkGeneration:
    """
    @brief      Prepare the common model prompts and budgets for batch or selected-chunk generation.
    @param[in]  ai_profile Selected model profile, or an empty mapping for local narration.
    @param[in]  source_language Source language code.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  voice_assignment_mode Project narration mode.
    @param[in]  settings_payload Application settings with cached TTS budgets.
    @param[in]  instructions Operator-supplied model instructions.
    @param[in]  scene_ambience_settings Normalized optional ambience settings.
    @return     Prepared chunk generation inputs.
    @exception  ValueError Raised when a required model profile or input budget is invalid.
    """
    narrator_only = voice_assignment_mode == "same_narrator"
    ambience_enabled = bool(scene_ambience_settings["enabled"])
    if requires_ai_profile(voice_assignment_mode, ambience_enabled) and not all(
        str(ai_profile.get(key, "")).strip() for key in ("id", "model_name", "base_url")
    ):
        raise ValueError("Speech Blocks generation requires a valid enabled AI profile.")

    tts_budget = _resolve_narrator_only_budget(settings_payload)
    system_prompt = ""
    budget_metadata: BudgetMetadataPayload = {}
    if not narrator_only:
        prompt_template_service.validate_required_prompts(list(_DIRECT_BLOCK_PROMPT_NAMES))
        system_prompt = prompt_template_service.render_prompt(_DIRECT_BLOCK_PROMPT_NAMES[0], {})
        budget_metadata = _build_budget_metadata(
            ai_profile, system_prompt, _DIRECT_BLOCK_PROMPT_NAMES[1], source_language, speaker_catalog,
            voice_assignment_mode, tts_budget, instructions,
        )
    if ambience_enabled:
        prompt_template_service.validate_required_prompts(["scene_ambience_system", "scene_ambience_user"])
    return ChunkGeneration(
        ai_profile, system_prompt, source_language, speaker_catalog, voice_assignment_mode,
        tts_budget, budget_metadata, instructions, scene_ambience_settings,
    )


def generate_chunk(
    generation: ChunkGeneration,
    source_chunk: dict[str, object],
    log_path: Path,
    log_context: dict[str, object],
    cancel_requested,
    *,
    source_offset: int = 0,
    prefix_blocks: list[SpeechBlockPayload] | None = None,
    segment_progress_callback=None,
) -> tuple[list[SpeechBlockPayload], TokenUsagePayload]:
    """
    @brief      Generate one complete speech chunk and optionally augment it with ambience.
    @param[in]  generation Prepared generation settings.
    @param[in]  source_chunk Full source chunk payload.
    @param[in]  log_path Operation-local AI log path.
    @param[in]  log_context Base request log context.
    @param[in]  cancel_requested Optional cancellation callback.
    @param[in]  source_offset Exact consumed character count.
    @param[in]  prefix_blocks Already persisted blocks in the active chunk.
    @param[in]  segment_progress_callback Optional checkpoint callback.
    @return     Current chunk rows and usage from new requests.
    @exception  OperationCancelledError Raised on operator cancellation.
    @exception  ChunkGenerationRefusedError Raised when the provider refuses speech segmentation.
    """
    blocks, usage = _generate_budgeted_chunk_blocks(
        generation, source_chunk, log_path, log_context, cancel_requested,
        source_offset, prefix_blocks, segment_progress_callback,
    )
    if not blocks or not generation.scene_ambience_settings["enabled"]:
        return blocks, usage
    ambience_context = {
        **log_context,
        "stage_label": str(log_context["stage_label"]).replace("speech_blocks_", "scene_ambience_", 1),
    }
    try:
        ambience, ambience_usage = _generate_scene_ambience_blocks(
            generation.ai_profile, source_chunk, generation.source_language, blocks,
            generation.scene_ambience_settings, log_path, ambience_context, cancel_requested,
        )
    except OperationCancelledError:
        raise
    except (RuntimeError, ValueError):
        speech = blocks[0]
        speech["warning_flags"] = _normalize_warning_flags(
            [*speech["warning_flags"], "scene_ambience_failed", "needs_review"]
        )
        return blocks, usage
    raise_if_cancelled(cancel_requested)
    return _insert_scene_ambience_blocks(blocks, ambience), token_usage_service.merge_token_usage(usage, ambience_usage)


# LOCAL HELPERS


def _chunk_user_prompt(
    source_chunk: dict[str, object],
    source_language: str,
    speaker_catalog: dict[str, dict[str, object]],
    voice_assignment_mode: str = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
    tts_budget: dict[str, object] | None = None,
    prompt_name: str = "speech_blocks_user",
    additional_speech_block_instructions: str = "",
) -> str:
    """
    @brief      Render the chunk-specific Speech Blocks user prompt.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  source_language Active source language code.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  voice_assignment_mode Active project voice-assignment mode.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @param[in]  prompt_name Prompt template name.
    @param[in]  additional_speech_block_instructions Optional operator-supplied Speech Blocks rules.
    @return     Rendered prompt text.
    @exception  None
    """
    budget_payload = tts_budget or _resolve_narrator_only_budget(None)
    return _render_speech_blocks_user_prompt(
        prompt_name,
        {
            "source_language": narrator_definition_service.narrator_language_label(source_language),
            "chunk_id": str(source_chunk.get("chunk_id", "")),
            "chunk_text": str(source_chunk.get("text", "")),
            "source_context_json": json.dumps(
                _compact_source_context_for_prompt(source_chunk),
                indent=2,
                ensure_ascii=False,
            ),
            "speaker_catalog_json": json.dumps(list(speaker_catalog.values()), indent=2, ensure_ascii=False),
            "voice_assignment_mode": voice_assignment_mode,
            "max_tts_tokens": str(int(budget_payload.get("model_token_budget", 0))),
            "safe_tts_words": str(int(budget_payload.get("safe_word_count", 0))),
            "tts_budget_source": str(budget_payload.get("model_budget_source", "")),
            "additional_speech_block_instructions": additional_speech_block_instructions,
        },
    )


def _render_speech_blocks_user_prompt(prompt_name: str, variables: dict[str, object]) -> str:
    """
    @brief      Render one Speech Blocks user prompt with optional operator rules.
    @param[in]  prompt_name Prompt template identifier.
    @param[in]  variables Prompt variables.
    @return     Rendered Speech Blocks prompt.
    @exception  None
    """
    template = prompt_template_service.load_prompt(prompt_name)
    placeholder_names = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", template))
    rendered_prompt = prompt_template_service.render_prompt(
        prompt_name,
        {key: value for key, value in variables.items() if key in placeholder_names},
    )
    additional_speech_block_instructions = normalize_instructions(
        variables.get("additional_speech_block_instructions")
    )
    if additional_speech_block_instructions and "additional_speech_block_instructions" not in placeholder_names:
        rendered_prompt = _append_additional_speech_block_instructions(
            rendered_prompt,
            additional_speech_block_instructions,
        )
    return rendered_prompt


def normalize_instructions(value: object) -> str:
    """
    @brief      Normalize optional operator Speech Blocks rules for prompts and state storage.
    @param[in]  value Candidate instruction text.
    @return     Trimmed instruction text.
    @exception  None
    """
    if value is None:
        return ""
    return str(value).strip()


def _append_additional_speech_block_instructions(prompt_text: str, additional_speech_block_instructions: str) -> str:
    """
    @brief      Append operator Speech Blocks rules to one rendered prompt.
    @param[in]  prompt_text Rendered prompt template text.
    @param[in]  additional_speech_block_instructions Normalized operator rules.
    @return     Prompt text with an additional-rules section.
    @exception  None
    """
    if not additional_speech_block_instructions:
        return prompt_text
    return (
        f"{prompt_text.rstrip()}\n\n"
        f"Additional operator Speech Blocks instructions:\n{additional_speech_block_instructions}\n"
    )


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    system_prompt: str,
    prompt_name: str,
    source_language: str,
    speaker_catalog: dict[str, dict[str, object]],
    voice_assignment_mode: str,
    tts_budget: dict[str, object] | None,
    additional_speech_block_instructions: str = "",
) -> BudgetMetadataPayload:
    """
    @brief      Build context-window budget metadata for AI Speech Blocks requests.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  system_prompt Rendered Speech Blocks system prompt.
    @param[in]  prompt_name Active Speech Blocks user prompt template name.
    @param[in]  source_language Active source language code.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  voice_assignment_mode Active project voice-assignment mode.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @param[in]  additional_speech_block_instructions Optional operator-supplied Speech Blocks rules.
    @return     Context-budget metadata used for source chunk segmentation.
    @exception  ValueError Raised when context and output settings leave too little input room.
    """
    prompt_shell = _chunk_user_prompt(
        {"chunk_id": "", "text": ""},
        source_language,
        speaker_catalog,
        voice_assignment_mode,
        tts_budget,
        prompt_name,
        additional_speech_block_instructions,
    )
    return ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{prompt_shell}",
        config.DEFAULT_SPEECH_BLOCKS_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_SPEECH_BLOCKS_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_SPEECH_BLOCKS_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_SPEECH_BLOCKS_MIN_TEXT_BUDGET_TOKENS,
        "AI-assisted Speech Blocks generation cannot run because the selected AI profile context window "
        "leaves too little room for source chunk input",
        online_text_context_fraction=config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION,
    )


def _generate_budgeted_chunk_blocks(
    generation: ChunkGeneration,
    source_chunk: dict[str, object],
    log_path: Path,
    log_context: dict[str, object],
    cancel_requested,
    source_offset: int,
    prefix_blocks: list[SpeechBlockPayload] | None,
    segment_progress_callback,
) -> tuple[list[SpeechBlockPayload], TokenUsagePayload]:
    """
    @brief      Generate the remaining speech in a chunk and checkpoint complete request slices.
    @param[in]  generation Prepared generation settings.
    @param[in]  source_chunk Full source chunk payload.
    @param[in]  log_path Operation-local AI log path.
    @param[in]  log_context Base request log context.
    @param[in]  cancel_requested Optional cancellation callback.
    @param[in]  source_offset Exact consumed character count.
    @param[in]  prefix_blocks Existing rows in the active chunk.
    @param[in]  segment_progress_callback Optional checkpoint callback.
    @return     Current chunk rows and usage from new requests.
    @exception  ChunkGenerationRefusedError Raised when the provider refuses speech segmentation.
    """
    source_text = str(source_chunk["text"])
    if generation.voice_assignment_mode == "same_narrator":
        raise_if_cancelled(cancel_requested)
        usage = token_usage_service.empty_token_usage()
        if source_offset:
            return list(prefix_blocks or []), usage
        chunk_blocks, _ = _deterministic_narrator_chunk_blocks(
            source_chunk,
            generation.source_language,
            generation.tts_budget,
        )
        if segment_progress_callback is not None and generation.scene_ambience_settings["enabled"]:
            segment_progress_callback(chunk_blocks, usage, len(source_text))
        return chunk_blocks, usage

    chunk_segments = (
        _budgeted_source_chunk_segments(
            {**source_chunk, "text": source_text[source_offset:]},
            generation.budget_metadata,
            source_token_cap=_SPEECH_BLOCKS_DIRECT_SOURCE_TOKEN_CAP,
        )
        if not source_offset or source_offset < len(source_text)
        else []
    )
    combined_blocks = list(prefix_blocks or [])
    chunk_token_usage = token_usage_service.empty_token_usage()
    for segment_index, segment_chunk in enumerate(chunk_segments, start=1):
        user_prompt = _chunk_user_prompt(
            segment_chunk,
            generation.source_language,
            generation.speaker_catalog,
            generation.voice_assignment_mode,
            generation.tts_budget,
            _DIRECT_BLOCK_PROMPT_NAMES[1],
            generation.instructions,
        )
        try:
            response_result = _generate_direct_block_response(
                generation.ai_profile,
                generation.system_prompt,
                user_prompt,
                segment_chunk,
                log_path=log_path,
                log_context={
                    **dict(log_context),
                    "segment_index": segment_index,
                    "segment_total": len(chunk_segments),
                    "response_contract": _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT,
                },
                cancel_requested=cancel_requested,
            )
        except OperationCancelledError as error:
            raise OperationCancelledError("Speech Blocks generation cancelled during a model request.") from error
        except (RuntimeError, llm_provider_service.ProviderRefusalError) as error:
            raise ChunkGenerationRefusedError(str(source_chunk.get("chunk_id", "")).strip()) from error
        chunk_token_usage = token_usage_service.merge_token_usage(chunk_token_usage, response_result.get("usage"))
        segment_blocks, _ = _normalize_chunk_blocks(
            segment_chunk,
            dict(response_result.get("payload", {})),
            generation.speaker_catalog,
            generation.source_language,
            voice_assignment_mode=generation.voice_assignment_mode,
            tts_budget=generation.tts_budget,
        )
        combined_blocks.extend(segment_blocks)
        combined_blocks = _renumber_single_chunk_blocks(
            str(source_chunk.get("chunk_id", "")).strip(),
            combined_blocks,
        )
        source_offset += len(str(segment_chunk["text"]))
        if segment_progress_callback is not None:
            segment_progress_callback(list(combined_blocks), dict(chunk_token_usage), source_offset)
            raise_if_cancelled(cancel_requested)
    return combined_blocks, chunk_token_usage


def _deterministic_narrator_chunk_blocks(
    source_chunk: dict[str, object],
    source_language: str,
    tts_budget: dict[str, object] | None,
) -> tuple[list[SpeechBlockPayload], list[dict[str, object]]]:
    """
    @brief      Segment one source chunk into same-narrator Speech Blocks without any model call.
    @details    Every block keeps whole sentences and the narrator voice, so the only decision
                left is where to place block boundaries, which is purely structural. Blocks the
                TTS budget cannot hold are flagged rather than cut, because Audio Blocks splits
                them again at generation time against the real loaded-model budget.
    @param[in]  source_chunk Source chunk payload, normally one cleaned paragraph.
    @param[in]  source_language Active source language code.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @return     Generated Speech Blocks plus warning entries.
    @exception  ValueError Raised when segmentation would not reproduce the source chunk.
    """
    chunk_id = str(source_chunk.get("chunk_id", "")).strip()
    planned_blocks = speech_blocks_narrator_split_service.plan_narrator_blocks(
        str(source_chunk.get("text", "")),
        _safe_tts_word_count(tts_budget),
    )
    review_flags = _cleanup_review_warning_flags(source_chunk)

    speech_blocks: list[SpeechBlockPayload] = []
    warning_entries: list[dict[str, object]] = []
    for sequence_index, planned_block in enumerate(planned_blocks, start=1):
        warning_flags = [*list(planned_block.get("warning_flags", [])), *review_flags]
        if speech_blocks_narrator_split_service.NARRATOR_BUDGET_EXCEEDED_FLAG in warning_flags:
            warning_entries.append(
                {
                    "chunk_id": chunk_id,
                    "reason": _speech_block_warning_reason(
                        speech_blocks_narrator_split_service.NARRATOR_BUDGET_EXCEEDED_FLAG
                    ),
                }
            )
        speech_blocks.append(
            _build_speech_block_payload(
                chunk_id,
                sequence_index,
                source_language,
                SPEAKER_KIND_NARRATOR,
                _NARRATOR_SPEAKER_ID,
                _NARRATOR_DISPLAY_NAME,
                CONTENT_KIND_NARRATION,
                str(planned_block.get("text", "")),
                _normalize_warning_flags(warning_flags),
                source_text=str(planned_block.get("source_text", "")),
            )
        )
    if review_flags and speech_blocks:
        warning_entries.append({"chunk_id": chunk_id, "reason": _speech_block_warning_reason("weak_source_boundary")})
    return speech_blocks, warning_entries


def _cleanup_review_warning_flags(source_chunk: dict[str, object]) -> list[str]:
    """
    @brief      Surface uncertain upstream paragraph boundaries as Speech Block review flags.
    @details    Cleanup already decides whether a paragraph was stitched back together across a
                page break and how confident that decision was. Carrying the verdict here is
                what makes a sentence broken by a page separator visible to the operator.
    @param[in]  source_chunk Source chunk payload carrying cleanup provenance.
    @return     Warning flags to attach to every block of this chunk.
    @exception  None
    """
    boundary_confidence = str(source_chunk.get("cleanup_boundary_confidence", "") or "").strip()
    joined_across_page_break = bool(source_chunk.get("cleanup_joined_across_page_break", False))
    if not joined_across_page_break and boundary_confidence in {"", "strong"}:
        return []
    return ["weak_source_boundary", "needs_review"]


def _generate_direct_block_response(
    ai_profile_payload: dict[str, object],
    system_prompt: str,
    user_prompt: str,
    source_chunk: dict[str, object],
    log_path: Path,
    log_context: dict[str, object],
    cancel_requested,
) -> dict[str, object]:
    """
    @brief      Request one direct Speech Blocks response without repair.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  system_prompt Rendered Speech Blocks system prompt.
    @param[in]  user_prompt Rendered Speech Blocks user prompt.
    @param[in]  source_chunk Source chunk or source segment.
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  log_context Base AI transaction log context.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Provider result or deterministic segment fallback payload.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @exception  ProviderRefusalError Raised for an explicit provider refusal.
    """
    response_schema = _direct_block_response_schema()
    response_schema_name = "speech_blocks_direct_blocks"
    raise_if_cancelled(cancel_requested)
    try:
        response_result = llm_provider_service.chat_json(
            ai_profile_payload,
            system_prompt,
            user_prompt,
            log_path=log_path,
            log_context=log_context,
            cancel_requested=cancel_requested,
            structured_output=True,
            response_schema=response_schema,
            response_schema_name=response_schema_name,
        )
    except llm_provider_service.ProviderRefusalError:
        raise
    except ValueError:
        return {
            "payload": {
                "blocks": [
                    {
                        "text": str(source_chunk.get("text", "")),
                        "speaker_id": _NARRATOR_SPEAKER_ID,
                        "content_kind": CONTENT_KIND_NARRATION,
                        "confidence": "low",
                        "warning_flags": ["speech_blocks_ai_parse_failed", "needs_review"],
                    }
                ]
            },
            "usage": token_usage_service.empty_token_usage(),
        }
    raise_if_cancelled(cancel_requested)
    return response_result


def _direct_block_response_schema() -> dict[str, object]:
    """
    @brief      Build the structured-output schema for direct Speech Blocks responses.
    @return     JSON Schema payload.
    @exception  None
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["blocks"],
        "properties": {
            "blocks": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "speaker_id", "content_kind", "confidence", "warning_flags"],
                    "properties": {
                        "text": {"type": "string"},
                        "speaker_id": {"type": "string"},
                        "content_kind": {"type": "string", "enum": ["narration", "dialogue"]},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "warning_flags": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    }


def _compact_source_context_for_prompt(source_chunk: dict[str, object]) -> dict[str, object]:
    """
    @brief      Build non-selectable attribution context for a Speech Blocks prompt.
    @param[in]  source_chunk Source chunk or AI-budget segment payload.
    @return     Previous/next context rows marked as non-selectable.
    @exception  None
    """
    return {
        "previous_context": {
            "available": bool(str(source_chunk.get("previous_context", "")).strip()),
            "selectable": False,
            "text": str(source_chunk.get("previous_context", "")).strip(),
        },
        "next_context": {
            "available": bool(str(source_chunk.get("next_context", "")).strip()),
            "selectable": False,
            "text": str(source_chunk.get("next_context", "")).strip(),
        },
        "rule": "This context may help attribution only. It is not selectable source text.",
    }


def _generate_scene_ambience_blocks(
    ai_profile_payload: dict[str, object],
    source_chunk: dict[str, object],
    source_language: str,
    speech_blocks: list[SpeechBlockPayload],
    scene_ambience_settings: dict[str, object],
    log_path: Path,
    log_context: dict[str, object],
    cancel_requested,
) -> tuple[list[SpeechBlockPayload], TokenUsagePayload]:
    """
    @brief      Generate prompt-based scene ambience blocks for one completed source chunk.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  source_language Active source language code.
    @param[in]  speech_blocks Chunk-local narration and dialogue Speech Blocks.
    @param[in]  scene_ambience_settings Normalized scene-ambience policy payload.
    @param[in]  log_path Operation-local AI transaction log path.
    @param[in]  log_context Base AI transaction log context.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Scene ambience blocks and provider token usage.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    if not speech_blocks:
        return [], token_usage_service.empty_token_usage()
    system_prompt = prompt_template_service.render_prompt("scene_ambience_system", {})
    user_prompt = _scene_ambience_user_prompt(
        source_chunk,
        source_language,
        speech_blocks,
        scene_ambience_settings,
    )
    try:
        response_result = llm_provider_service.chat_json(
            ai_profile_payload,
            system_prompt,
            user_prompt,
            log_path=log_path,
            log_context={**dict(log_context), "response_contract": "scene_ambience_blocks"},
            cancel_requested=cancel_requested,
        )
    except OperationCancelledError as error:
        raise OperationCancelledError(
            "Speech Blocks generation cancelled while waiting for scene ambience analysis."
        ) from error
    return (
        _normalize_scene_ambience_response(
            dict(response_result.get("payload", {})),
            str(source_chunk.get("chunk_id", "")).strip(),
            source_language,
            scene_ambience_settings,
        ),
        token_usage_service.restore_token_usage(response_result.get("usage")),
    )


def _scene_ambience_user_prompt(
    source_chunk: dict[str, object],
    source_language: str,
    speech_blocks: list[SpeechBlockPayload],
    scene_ambience_settings: dict[str, object],
) -> str:
    """
    @brief      Render the scene-ambience chunk prompt.
    @param[in]  source_chunk Source chunk payload.
    @param[in]  source_language Active source language code.
    @param[in]  speech_blocks Chunk-local Speech Blocks.
    @param[in]  scene_ambience_settings Normalized scene-ambience policy payload.
    @return     Rendered scene-ambience prompt text.
    @exception  None
    """
    compact_blocks = [
        {
            "speech_block_id": str(block.get("speech_block_id", "")).strip(),
            "sequence_index": int(block.get("sequence_index", 0)),
            "speaker": str(block.get("speaker_display_name", "")).strip(),
            "content_kind": str(block.get("content_kind", "")).strip(),
            "text": str(block.get("text", "")),
        }
        for block in speech_blocks
    ]
    allowed_positions = list(scene_ambience_settings.get("allowed_positions", []))
    return prompt_template_service.render_prompt(
        "scene_ambience_user",
        {
            "source_language": narrator_definition_service.narrator_language_label(source_language),
            "chunk_id": str(source_chunk.get("chunk_id", "")),
            "chunk_text": str(source_chunk.get("text", "")),
            "placement_policy": str(scene_ambience_settings.get("placement_policy", "")),
            "duration_seconds": str(float(scene_ambience_settings.get("duration_seconds", 10.0))),
            "max_blocks_per_sequence": str(int(scene_ambience_settings.get("max_blocks_per_sequence", 6))),
            "allowed_positions": ", ".join(allowed_positions),
            "negative_prompt_core": _scene_ambience_negative_prompt_core(scene_ambience_settings),
            "speech_blocks_json": json.dumps(compact_blocks, indent=2, ensure_ascii=False),
        },
    )


def _normalize_scene_ambience_response(
    payload: dict[str, object],
    chunk_id: str,
    source_language: str,
    scene_ambience_settings: dict[str, object],
) -> list[SpeechBlockPayload]:
    """
    @brief      Normalize one scene-ambience LLM response into operation Speech Blocks.
    @param[in]  payload Raw JSON response payload.
    @param[in]  chunk_id Current source chunk identifier.
    @param[in]  source_language Active source language code.
    @param[in]  scene_ambience_settings Normalized scene-ambience policy payload.
    @return     Normalized scene-ambience Speech Blocks.
    @exception  None
    """
    raw_blocks = payload.get("scene_ambience_blocks", [])
    if not isinstance(raw_blocks, list):
        return []
    allowed_positions = {str(item) for item in scene_ambience_settings.get("allowed_positions", [])}
    max_sequence_duration = float(scene_ambience_settings.get("duration_seconds", 10.0))
    max_blocks_per_sequence = int(scene_ambience_settings.get("max_blocks_per_sequence", 6))
    normalized_blocks: list[SpeechBlockPayload] = []
    sequence_counts: dict[tuple[str, str], int] = {}
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict):
            continue
        ambience_position = str(raw_block.get("ambience_position", "")).strip()
        if ambience_position not in allowed_positions:
            continue
        after_speech_block_id = str(raw_block.get("after_speech_block_id", "")).strip()
        sound_prompt = str(raw_block.get("sound_prompt", raw_block.get("text", ""))).strip()
        if not sound_prompt:
            continue
        sequence_key = (ambience_position, after_speech_block_id if ambience_position == "scene_change" else "")
        negative_prompt = str(raw_block.get("negative_prompt", "")).strip()
        if not negative_prompt:
            negative_prompt = _scene_ambience_negative_prompt_core(scene_ambience_settings)
        remaining_slots = max_blocks_per_sequence - sequence_counts.get(sequence_key, 0)
        if remaining_slots <= 0:
            continue
        split_prompts = _split_composed_scene_ambience_prompt(sound_prompt)[:remaining_slots]
        if not split_prompts:
            continue
        for split_prompt in split_prompts:
            sequence_counts[sequence_key] = sequence_counts.get(sequence_key, 0) + 1
            normalized_blocks.append(
                {
                    "speech_block_id": "",
                    "sequence_index": 0,
                    "chunk_id": chunk_id,
                    "source_language": source_language,
                    "speaker_kind": SPEAKER_KIND_OPERATION,
                    "speaker_id": CONTENT_KIND_SCENE_AMBIENCE,
                    "speaker_display_name": _operation_display_name(CONTENT_KIND_SCENE_AMBIENCE),
                    "content_kind": CONTENT_KIND_SCENE_AMBIENCE,
                    "source_text": "",
                    "text": split_prompt,
                    "sound_prompt": split_prompt,
                    "negative_prompt": negative_prompt,
                    "duration_seconds": max_sequence_duration,
                    "ambience_position": ambience_position,
                    "after_speech_block_id": after_speech_block_id,
                    "warning_flags": [],
                    "approved": False,
                    "approved_at": None,
                }
            )
    return normalized_blocks


def _scene_ambience_negative_prompt_core(scene_ambience_settings: dict[str, object]) -> str:
    """
    @brief      Resolve the exclusions applied to every Scene Ambience block whatever the scene.
    @param[in]  scene_ambience_settings Normalized scene-ambience policy payload.
    @return     Universal exclusion list.
    @exception  None
    """
    configured_core = str(scene_ambience_settings.get("negative_prompt", "")).strip()
    return configured_core or config.DEFAULT_SCENE_AMBIENCE_NEGATIVE_PROMPT


def _split_composed_scene_ambience_prompt(sound_prompt: str) -> list[str]:
    """
    @brief      Split one composed Scene Ambience prompt into simple sound-source prompts.
    @param[in]  sound_prompt Candidate sound prompt.
    @return     One or more simple sound prompts.
    @exception  None
    """
    normalized_prompt = " ".join(str(sound_prompt).strip().split())
    if not normalized_prompt:
        return []
    separators = (
        r"\s*;\s*",
        r"\s*,\s*(?=(?:a |an |the |low-volume |subtle |soft |occasional |intermittent |sparse |"
        r"irregular |distant |muffled |fading |shifting |approaching |receding |quiet |faint |"
        r"very faint |steady |sudden |heavy |rapid |rhythmic ))",
        r"\s+(?:and|plus)\s+(?=(?:a |an |the |low-volume |subtle |soft |occasional |intermittent |"
        r"sparse |irregular |distant |muffled |fading |shifting |approaching |receding |quiet |"
        r"faint |very faint |steady |sudden |heavy |rapid |rhythmic ))",
    )
    parts = [normalized_prompt]
    for separator in separators:
        split_parts: list[str] = []
        for part in parts:
            split_parts.extend(re.split(separator, part, flags=re.IGNORECASE))
        parts = split_parts
    normalized_parts: list[str] = []
    for part in parts:
        normalized_part = " ".join(str(part).strip(" .").split())
        if normalized_part and normalized_part not in normalized_parts:
            normalized_parts.append(normalized_part)
    return normalized_parts or [normalized_prompt]


def _insert_scene_ambience_blocks(
    speech_blocks: list[SpeechBlockPayload],
    scene_ambience_blocks: list[SpeechBlockPayload],
) -> list[SpeechBlockPayload]:
    """
    @brief      Insert scene ambience blocks at chunk-local opener, closer, and scene-change positions.
    @param[in]  speech_blocks Chunk-local spoken Speech Blocks.
    @param[in]  scene_ambience_blocks Scene ambience operation Speech Blocks.
    @return     Renumbered chunk-local Speech Blocks including scene ambience.
    @exception  None
    """
    if not scene_ambience_blocks:
        return speech_blocks
    chunk_id = str(speech_blocks[0]["chunk_id"])
    used_ids = {str(block["speech_block_id"]) for block in speech_blocks}
    assigned_ambience = []
    for block in scene_ambience_blocks:
        block_id = speech_blocks_normalization_service.next_unused_speech_block_id(chunk_id, used_ids)
        used_ids.add(block_id)
        assigned_ambience.append({**block, "speech_block_id": block_id})
    opener_blocks = [
        block for block in assigned_ambience if str(block.get("ambience_position", "")) == "opener"
    ]
    closer_blocks = [
        block for block in assigned_ambience if str(block.get("ambience_position", "")) == "closer"
    ]
    scene_change_blocks = [
        block for block in assigned_ambience if str(block.get("ambience_position", "")) == "scene_change"
    ]
    ordered_blocks: list[SpeechBlockPayload] = [*opener_blocks]
    spoken_block_positions: list[tuple[str, int]] = []
    pending_scene_changes = list(scene_change_blocks)
    for speech_block in speech_blocks:
        spoken_block_positions.append(
            (str(speech_block.get("speech_block_id", "")).strip(), len(ordered_blocks))
        )
        ordered_blocks.append(dict(speech_block))
        speech_block_id = str(speech_block.get("speech_block_id", "")).strip()
        matching_changes = [
            block
            for block in pending_scene_changes
            if str(block.get("after_speech_block_id", "")).strip() == speech_block_id
        ]
        ordered_blocks.extend(matching_changes)
        pending_scene_changes = [block for block in pending_scene_changes if block not in matching_changes]
    ordered_blocks.extend(pending_scene_changes)
    ordered_blocks.extend(closer_blocks)
    renumbered_blocks = _renumber_single_chunk_blocks(chunk_id, ordered_blocks)
    spoken_id_remap = {
        old_id: str(renumbered_blocks[position].get("speech_block_id", "")).strip()
        for old_id, position in spoken_block_positions
        if old_id
    }
    for block in renumbered_blocks:
        if str(block.get("content_kind", "")).strip() != CONTENT_KIND_SCENE_AMBIENCE:
            continue
        after_speech_block_id = str(block.get("after_speech_block_id", "")).strip()
        if after_speech_block_id in spoken_id_remap:
            block["after_speech_block_id"] = spoken_id_remap[after_speech_block_id]
    return renumbered_blocks


def _budgeted_source_chunk_segments(
    source_chunk: dict[str, object],
    budget_metadata: BudgetMetadataPayload,
    source_token_cap: int | None = None,
) -> list[dict[str, object]]:
    """
    @brief      Split one source chunk into AI-context-budgeted request segment payloads.
    @param[in]  source_chunk Full source chunk payload.
    @param[in]  budget_metadata Context-budget metadata.
    @return     Ordered source chunk segment payloads using the original chunk id.
    @exception  None
    """
    text_budget_tokens = int(budget_metadata["text_budget_tokens"])
    if source_token_cap is not None:
        text_budget_tokens = min(text_budget_tokens, max(1, int(source_token_cap)))
    source_text = str(source_chunk.get("text", ""))
    text_segments = _split_text_for_ai_context_budget(source_text, text_budget_tokens)
    if not text_segments:
        return [dict(source_chunk)]
    return [{**dict(source_chunk), "text": text_segment} for text_segment in text_segments]



# END OF FILE
