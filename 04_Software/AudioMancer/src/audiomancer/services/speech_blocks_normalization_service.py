#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file speech_blocks_normalization_service.py
@brief Speech Blocks normalization helpers.
@details Provides reusable Speech Blocks content-kind, operation-row, warning,
         text, and identifier normalization outside the orchestration service.
"""

# IMPORTS

import re

from audiomancer import config
from audiomancer.services import speech_blocks_text_split_service, tts_budget_service
from audiomancer.services.logging_service import get_component_logger

# CONSTANTS

SPEAKER_KIND_NARRATOR = "narrator"
SPEAKER_KIND_CHARACTER = "character"
SPEAKER_KIND_OPERATION = "operation"
CONTENT_KIND_NARRATION = "narration"
CONTENT_KIND_DIALOGUE = "dialogue"
CONTENT_KIND_SCENE_AMBIENCE = "scene_ambience"
CONTENT_KIND_PAUSE = "pause"
CONTENT_KIND_INDICATION = "indication"

SPEECH_BLOCK_CONTENT_KINDS = (
    CONTENT_KIND_NARRATION,
    CONTENT_KIND_DIALOGUE,
    CONTENT_KIND_SCENE_AMBIENCE,
    CONTENT_KIND_PAUSE,
    CONTENT_KIND_INDICATION,
)

NARRATOR_SPEAKER_ID = "narrator"
NARRATOR_DISPLAY_NAME = "Narrator"
_SPEECH_BLOCKS_NORMALIZATION_LOGGER = get_component_logger("speech_blocks")

# PUBLIC API


def block_text_key(text: str) -> str:
    """
    @brief      Normalize text for exact source matching.
    @param[in]  text Candidate text.
    @return     Matching key.
    @exception  None
    """
    return " ".join(text.strip().split()).casefold()


def append_warning_flag(warning_flags: list[str], warning_flag: str) -> None:
    """
    @brief      Append one warning flag when it is not present already.
    @param[in]  warning_flags Warning flag list to mutate.
    @param[in]  warning_flag Warning flag token.
    @return     None.
    @exception  None
    """
    if warning_flag not in warning_flags:
        warning_flags.append(warning_flag)


def speech_block_warning_reason(warning_flag: str) -> str:
    """
    @brief      Resolve a report note for one Speech Blocks warning flag.
    @param[in]  warning_flag Warning flag token.
    @return     Human-readable warning reason.
    @exception  None
    """
    return {
        "ambiguous_speaker": "Speaker attribution was ambiguous and fell back to narrator.",
        "source_coverage_mismatch": "Model source spans do not fully cover the chunk in reading order.",
        "source_order_mismatch": "Model source spans are not in chunk reading order.",
        "model_text_modified": "Model audio text differs from the source span beyond delimiter cleanup.",
        "tts_budget_exceeded": "Narrator-only block exceeds the safe TTS word budget.",
        "tts_hard_split": "Speech Block was hard-split after no paragraph or sentence boundary fit the TTS budget.",
        "source_span_selection_invalid": ("Model source span selection was invalid and fell back to narrator."),
        "speaker_selection_invalid": "Model speaker selection was invalid and fell back to narrator.",
        "boundary_selection_fallback": (
            "Narrator-only AI boundary selection was unusable and deterministic TTS splitting was used."
        ),
        "atomic_unit_selection_invalid": ("Model atomic unit selection was invalid and fell back to narrator."),
        "needs_review": "Speech Block needs operator review.",
        "weak_source_boundary": (
            "Source paragraph was repaired across a page break during cleanup, so its boundaries are uncertain."
        ),
        "source_gap": "Source text was not covered by the model response and was preserved for review.",
        "unknown_speaker": "Model returned a speaker that is not in the allowed speaker catalog.",
        "unmatched_model_text": "Model text could not be aligned to the source and was not trusted.",
        "speech_blocks_ai_parse_failed": "Speech Blocks model response could not be parsed.",
    }.get(str(warning_flag).strip(), str(warning_flag).strip() or "Speech Block warning.")


def normalize_block_text(text: str, content_kind: str) -> str:
    """
    @brief      Normalize one Speech Blocks text span without changing wording.
    @param[in]  text Candidate block text.
    @param[in]  content_kind Block content-kind token.
    @return     Persisted block text.
    @exception  None
    """
    if content_kind != CONTENT_KIND_DIALOGUE:
        return str(text).strip()
    normalized_text = text.strip()
    normalized_text = re.sub(r"^[-–—]\s+", "", normalized_text, count=1)
    for opening_quote, closing_quote in speech_blocks_text_split_service.dialogue_quote_pairs():
        if (
            len(normalized_text) >= 2
            and normalized_text.startswith(opening_quote)
            and normalized_text.endswith(closing_quote)
        ):
            return normalized_text[1:-1].strip()
    return normalized_text


def normalize_content_kind(value: object) -> str:
    """
    @brief      Normalize one Speech Blocks content-kind token.
    @param[in]  value Candidate content-kind value.
    @return     Supported content-kind token.
    @exception  None
    """
    normalized = str(value).strip().casefold().replace(" ", "_").replace("-", "_")
    if normalized in SPEECH_BLOCK_CONTENT_KINDS:
        return normalized
    return CONTENT_KIND_NARRATION


def is_operation_content_kind(content_kind: str) -> bool:
    """
    @brief      Return whether one content kind is represented as an operation row.
    @param[in]  content_kind Normalized content-kind token.
    @return     True for metadata-only operation content kinds.
    @exception  None
    """
    return str(content_kind).strip() in {
        CONTENT_KIND_SCENE_AMBIENCE,
        CONTENT_KIND_PAUSE,
        CONTENT_KIND_INDICATION,
    }


def operation_speaker_entry(content_kind: str) -> dict[str, object]:
    """
    @brief      Build the persisted speaker fields for one metadata-only operation.
    @param[in]  content_kind Normalized operation content-kind token.
    @return     Speaker-like operation entry used by JSON and list rendering.
    @exception  None
    """
    normalized_content_kind = normalize_content_kind(content_kind)
    return {
        "speaker_kind": SPEAKER_KIND_OPERATION,
        "speaker_id": normalized_content_kind,
        "display_name": operation_display_name(normalized_content_kind),
    }


def operation_display_name(content_kind: str) -> str:
    """
    @brief      Resolve the stable persisted display name for a metadata-only operation.
    @param[in]  content_kind Normalized operation content-kind token.
    @return     Operator-facing operation name.
    @exception  None
    """
    return {
        CONTENT_KIND_SCENE_AMBIENCE: "Scene Ambience",
        CONTENT_KIND_PAUSE: "Pause",
        CONTENT_KIND_INDICATION: "Indication",
    }.get(str(content_kind).strip(), "Operation")


def speech_block_id(chunk_id: str, sequence_index: int) -> str:
    """
    @brief      Build the persisted minimum-width `CCCC-BBBBBB` Speech Block identifier.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  sequence_index Chunk-local Speech Block sequence index.
    @return     Stable Speech Block identifier.
    @exception  None
    """
    chunk_number = chunk_order_from_id(chunk_id)
    return f"{chunk_number:04d}-{max(int(sequence_index), 0):06d}"


def chunk_order_from_id(chunk_id: str) -> int:
    """
    @brief      Resolve a numeric chunk-order token from one chunk identifier.
    @param[in]  chunk_id Source chunk identifier.
    @return     Positive chunk-order value or zero when no digits are present.
    @exception  None
    """
    digits = "".join(character for character in str(chunk_id) if character.isdigit())
    return int(digits or "0")


def normalize_warning_flags(value: object) -> list[str]:
    """
    @brief      Normalize one warning-flag list payload.
    @param[in]  value Candidate warning-flag value.
    @return     Ordered warning-flag string list.
    @exception  None
    """
    if not isinstance(value, list):
        return []
    normalized_flags: list[str] = []
    for item in value:
        flag = str(item).strip()
        if flag and flag not in normalized_flags:
            normalized_flags.append(flag)
    return normalized_flags



def warning_entries_from_ai_blocks(
    chunk_id: str,
    ai_blocks: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Build warning entries from already-normalized AI-block warning flags.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  ai_blocks AI-block-like payloads.
    @return     Human-readable warning entries.
    @exception  None
    """
    warning_entries: list[dict[str, object]] = []
    for ai_block in ai_blocks:
        for warning_flag in normalize_warning_flags(ai_block.get("warning_flags")):
            warning_entries.append({"chunk_id": chunk_id, "reason": speech_block_warning_reason(warning_flag)})
    return warning_entries


def resolve_narrator_only_budget(settings_payload: dict[str, object] | None) -> dict[str, object]:
    """
    @brief      Resolve TTS budget metadata for narrator-only splitting.
    @param[in]  settings_payload Optional application settings payload.
    @return     TTS budget payload.
    @exception  None
    """
    discovered_models = []
    if isinstance(settings_payload, dict):
        discovered_models = [
            dict(model)
            for model in settings_payload.get("tts_runtime_discovered_models", [])
            if isinstance(model, dict)
        ]
    return tts_budget_service.resolve_cached_tts_budget(
        discovered_models,
        tts_budget_service.resolve_generation_token_limit(settings_payload),
    )


def normalize_direct_block_chunk_blocks(
    source_chunk: dict[str, object],
    candidate_blocks: list[object],
    speaker_catalog: dict[str, dict[str, object]],
    source_language: str,
    narrator_only: bool,
    tts_budget: dict[str, object] | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """
    @brief      Normalize direct LLM block output by aligning returned text to source.
    @param[in]  source_chunk Current source chunk payload.
    @param[in]  candidate_blocks Raw direct block payload list.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  source_language Active source language code.
    @param[in]  narrator_only True when all spoken text uses narrator voice.
    @param[in]  tts_budget Optional TTS budget metadata.
    @return     Tuple of normalized chunk blocks and warning entries.
    @exception  None
    """
    chunk_id = str(source_chunk.get("chunk_id", "")).strip()
    chunk_text = str(source_chunk.get("text", ""))
    aligned_ai_blocks: list[dict[str, object]] = []
    warning_entries: list[dict[str, object]] = []
    cursor = 0
    for candidate_block in candidate_blocks:
        if not isinstance(candidate_block, dict):
            continue
        model_text = str(candidate_block.get("source_text", candidate_block.get("text", "")))
        if not model_text.strip():
            continue
        match_index = chunk_text.find(model_text, cursor)
        if match_index < 0:
            warning_reason = speech_block_warning_reason("unmatched_model_text")
            warning_entries.append(
                {"chunk_id": chunk_id, "reason": f"unmatched_model_text: {warning_reason}"}
            )
            continue
        if chunk_text[cursor:match_index].strip():
            aligned_ai_blocks.append(direct_source_gap_block(chunk_text[cursor:match_index]))
        source_slice = chunk_text[match_index : match_index + len(model_text)]
        aligned_ai_blocks.append(direct_aligned_ai_block(candidate_block, source_slice, speaker_catalog, narrator_only))
        cursor = match_index + len(model_text)

    if chunk_text[cursor:].strip():
        aligned_ai_blocks.append(direct_source_gap_block(chunk_text[cursor:]))
    if not aligned_ai_blocks:
        aligned_ai_blocks.append(direct_source_gap_block(chunk_text))

    warning_entries.extend(warning_entries_from_ai_blocks(chunk_id, aligned_ai_blocks))
    aligned_ai_blocks, split_warnings = split_over_budget_ai_blocks(chunk_id, aligned_ai_blocks, tts_budget)
    warning_entries.extend(split_warnings)
    if narrator_only:
        warning_entries.extend(validate_narrator_only_budget(chunk_id, aligned_ai_blocks, tts_budget))
    normalized_blocks: list[dict[str, object]] = []
    for local_sequence_index, ai_block in enumerate(aligned_ai_blocks, start=1):
        normalized_blocks.append(
            build_speech_block_payload(
                chunk_id,
                local_sequence_index,
                source_language,
                str(ai_block.get("speaker_kind", SPEAKER_KIND_NARRATOR)),
                str(ai_block.get("speaker_id", NARRATOR_SPEAKER_ID)),
                str(ai_block.get("speaker_display_name", NARRATOR_DISPLAY_NAME)),
                str(ai_block.get("content_kind", CONTENT_KIND_NARRATION)),
                str(ai_block.get("text", "")),
                list(ai_block.get("warning_flags", [])),
                source_text=str(ai_block.get("source_text", "")),
            )
        )
    return normalized_blocks, warning_entries


def direct_aligned_ai_block(
    candidate_block: dict[str, object],
    source_text: str,
    speaker_catalog: dict[str, dict[str, object]],
    narrator_only: bool,
) -> dict[str, object]:
    """
    @brief      Build one trusted direct AI block from an aligned source slice.
    @param[in]  candidate_block Raw model block.
    @param[in]  source_text Exact source slice aligned from the chunk.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  narrator_only True when all speech uses narrator voice.
    @return     AI block ready for final payload building.
    @exception  None
    """
    aligned_candidate = dict(candidate_block)
    aligned_candidate["source_text"] = source_text
    aligned_candidate["text"] = source_text
    ai_block = normalize_ai_block(aligned_candidate, speaker_catalog, narrator_only=narrator_only)
    warning_flags = list(ai_block.get("warning_flags", []))
    requested_speaker_id = str(candidate_block.get("speaker_id", "")).strip()
    resolved_speaker_id = str(ai_block.get("speaker_id", NARRATOR_SPEAKER_ID)).strip()
    if (
        requested_speaker_id
        and requested_speaker_id.casefold() != NARRATOR_SPEAKER_ID
        and resolved_speaker_id == NARRATOR_SPEAKER_ID
        and not narrator_only
    ):
        append_warning_flag(warning_flags, "unknown_speaker")
        append_warning_flag(warning_flags, "needs_review")
    if str(candidate_block.get("confidence", "")).strip().casefold() == "low":
        append_warning_flag(warning_flags, "needs_review")
    ai_block["warning_flags"] = normalize_warning_flags(warning_flags)
    return ai_block


def direct_source_gap_block(source_text: str) -> dict[str, object]:
    """
    @brief      Build one narrator review block for source text missed by the model.
    @param[in]  source_text Exact missed source text.
    @return     AI-block-like narrator review payload.
    @exception  None
    """
    return {
        "speaker_kind": SPEAKER_KIND_NARRATOR,
        "speaker_id": NARRATOR_SPEAKER_ID,
        "speaker_display_name": NARRATOR_DISPLAY_NAME,
        "content_kind": CONTENT_KIND_NARRATION,
        "source_text": str(source_text),
        "text": str(source_text).strip(),
        "warning_flags": ["source_gap", "needs_review"],
    }


def normalize_chunk_blocks(
    source_chunk: dict[str, object],
    response_payload: dict[str, object],
    speaker_catalog: dict[str, dict[str, object]],
    source_language: str,
    voice_assignment_mode: str = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
    tts_budget: dict[str, object] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """
    @brief      Normalize one AI response into persisted Speech Blocks payloads.
    @param[in]  source_chunk Current source chunk payload.
    @param[in]  response_payload Raw model response payload.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  source_language Active source language code.
    @param[in]  voice_assignment_mode Active project voice-assignment mode.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @return     Tuple of normalized chunk blocks and warning entries.
    @exception  None
    """
    narrator_only = str(voice_assignment_mode).strip() == "same_narrator"
    candidate_blocks = response_payload.get("speech_blocks", response_payload.get("blocks", []))
    if not isinstance(candidate_blocks, list):
        candidate_blocks = []

    return normalize_direct_block_chunk_blocks(
        source_chunk,
        candidate_blocks,
        speaker_catalog,
        source_language,
        narrator_only,
        tts_budget,
    )


def build_speech_block_payload(
    chunk_id: str,
    sequence_index: int,
    source_language: str,
    speaker_kind: str,
    speaker_id: str,
    speaker_display_name: str,
    content_kind: str,
    text: str,
    warning_flags: list[str],
    source_text: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build one persisted Speech Blocks payload with current editable fields.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  sequence_index Chunk-local block index.
    @param[in]  source_language Active source language code.
    @param[in]  speaker_kind Current speaker kind token.
    @param[in]  speaker_id Current speaker identifier.
    @param[in]  speaker_display_name Current speaker display label.
    @param[in]  content_kind Current content-kind token.
    @param[in]  text Current block text.
    @param[in]  warning_flags Current warning flags.
    @param[in]  source_text Exact source text span represented by this block.
    @return     Persisted Speech Blocks payload.
    @exception  None
    """
    normalized_content_kind = normalize_content_kind(content_kind)
    normalized_warning_flags = normalize_warning_flags(warning_flags)
    if is_operation_content_kind(normalized_content_kind):
        speaker_entry = operation_speaker_entry(normalized_content_kind)
        normalized_speaker_kind = str(speaker_entry["speaker_kind"])
        normalized_speaker_id = str(speaker_entry["speaker_id"])
        normalized_speaker_display_name = str(speaker_entry["display_name"])
    else:
        normalized_speaker_kind = str(speaker_kind).strip() or SPEAKER_KIND_NARRATOR
        normalized_speaker_id = str(speaker_id).strip() or NARRATOR_SPEAKER_ID
        normalized_speaker_display_name = str(speaker_display_name).strip() or NARRATOR_DISPLAY_NAME
    normalized_text = str(text)
    normalized_source_text = normalized_text if source_text is None else str(source_text)
    return {
        "speech_block_id": speech_block_id(chunk_id, sequence_index),
        "sequence_index": int(sequence_index),
        "chunk_id": str(chunk_id).strip(),
        "source_language": str(source_language).strip(),
        "speaker_kind": normalized_speaker_kind,
        "speaker_id": normalized_speaker_id,
        "speaker_display_name": normalized_speaker_display_name,
        "content_kind": normalized_content_kind,
        "source_text": normalized_source_text,
        "text": normalized_text,
        "warning_flags": normalized_warning_flags,
        "approved": False,
        "approved_at": None,
    }


def normalize_ai_block(
    candidate_block: dict[str, object],
    speaker_catalog: dict[str, dict[str, object]],
    narrator_only: bool = False,
) -> dict[str, object]:
    """
    @brief      Normalize one model-supplied Speech Blocks payload before source-span reconciliation.
    @param[in]  candidate_block Raw model-supplied block payload.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  narrator_only True when the project uses one narrator voice for all text.
    @return     Normalized AI block with resolved speaker metadata.
    @exception  None
    """
    content_kind = normalize_content_kind(candidate_block.get("content_kind", CONTENT_KIND_NARRATION))
    if narrator_only and not is_operation_content_kind(content_kind):
        content_kind = CONTENT_KIND_NARRATION
    source_text = str(candidate_block.get("source_text", candidate_block.get("text", "")))
    raw_text = str(candidate_block.get("text", source_text))
    if not raw_text.strip():
        raw_text = source_text
    text = raw_text.strip() if narrator_only else normalize_block_text(raw_text, content_kind)
    if is_operation_content_kind(content_kind):
        speaker_entry = operation_speaker_entry(content_kind)
        return {
            "speaker_kind": str(speaker_entry["speaker_kind"]),
            "speaker_id": str(speaker_entry["speaker_id"]),
            "speaker_display_name": str(speaker_entry["display_name"]),
            "content_kind": content_kind,
            "source_text": source_text,
            "text": text,
            "warning_flags": normalize_warning_flags(candidate_block.get("warning_flags")),
        }
    if narrator_only:
        warning_flags = normalize_warning_flags(candidate_block.get("warning_flags"))
        return {
            "speaker_kind": SPEAKER_KIND_NARRATOR,
            "speaker_id": NARRATOR_SPEAKER_ID,
            "speaker_display_name": NARRATOR_DISPLAY_NAME,
            "content_kind": CONTENT_KIND_NARRATION,
            "source_text": source_text,
            "text": text,
            "warning_flags": warning_flags,
        }
    requested_speaker_id = str(candidate_block.get("speaker_id", "")).strip()
    speaker_entry, ambiguous_speaker = resolve_speaker_entry(requested_speaker_id, speaker_catalog)
    warning_flags = normalize_warning_flags(candidate_block.get("warning_flags"))
    if ambiguous_speaker:
        append_warning_flag(warning_flags, "ambiguous_speaker")
    return {
        "speaker_kind": str(speaker_entry.get("speaker_kind", SPEAKER_KIND_NARRATOR)),
        "speaker_id": str(speaker_entry.get("speaker_id", NARRATOR_SPEAKER_ID)),
        "speaker_display_name": str(speaker_entry.get("display_name", NARRATOR_DISPLAY_NAME)),
        "content_kind": content_kind,
        "source_text": source_text,
        "text": text,
        "warning_flags": warning_flags,
    }


def validate_narrator_only_budget(
    chunk_id: str,
    ai_blocks: list[dict[str, object]],
    tts_budget: dict[str, object] | None,
) -> list[dict[str, object]]:
    """
    @brief      Flag narrator-only blocks that exceed the safe cached TTS word budget.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  ai_blocks Normalized AI blocks to validate and annotate.
    @param[in]  tts_budget Optional TTS budget metadata.
    @return     Human-readable warning entries.
    @exception  None
    """
    budget_payload = tts_budget or resolve_narrator_only_budget(None)
    safe_word_count = int(budget_payload.get("safe_word_count", 0) or 0)
    if safe_word_count <= 0:
        return []
    warning_entries: list[dict[str, object]] = []
    for ai_block in ai_blocks:
        if is_operation_content_kind(str(ai_block.get("content_kind", ""))):
            continue
        text = str(ai_block.get("text", ""))
        if tts_budget_unit_count(text) <= safe_word_count:
            continue
        warning_flags = list(ai_block.get("warning_flags", []))
        append_warning_flag(warning_flags, "tts_budget_exceeded")
        ai_block["warning_flags"] = warning_flags
        warning_entries.append(
            {
                "chunk_id": chunk_id,
                "reason": (f"Narrator-only block may exceed the safe cached TTS budget of {safe_word_count} words."),
            }
        )
    return warning_entries


def split_over_budget_ai_blocks(
    chunk_id: str,
    ai_blocks: list[dict[str, object]],
    tts_budget: dict[str, object] | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """
    @brief      Split oversized AI blocks after model output as a deterministic TTS safety net.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  ai_blocks Normalized AI blocks to split when needed.
    @param[in]  tts_budget Optional TTS budget metadata.
    @return     Tuple of split AI blocks and human-readable warning entries.
    @exception  None
    """
    safe_word_count = safe_tts_word_count(tts_budget)
    hard_word_count = hard_tts_word_count(tts_budget)
    if safe_word_count <= 0:
        return ai_blocks, []

    split_blocks: list[dict[str, object]] = []
    warning_entries: list[dict[str, object]] = []
    for ai_block in ai_blocks:
        content_kind = normalize_content_kind(ai_block.get("content_kind", CONTENT_KIND_NARRATION))
        if is_operation_content_kind(content_kind):
            split_blocks.append(ai_block)
            continue

        source_text = str(ai_block.get("source_text", ai_block.get("text", "")))
        audio_text = str(ai_block.get("text", source_text))
        if tts_budget_unit_count(audio_text) <= safe_word_count:
            split_blocks.append(ai_block)
            continue

        source_audio_text = normalize_block_text(source_text, content_kind)
        source_text_matches_audio = block_text_key(source_audio_text) == block_text_key(audio_text)
        audio_parts, used_hard_split = split_text_for_tts_budget(
            source_text if source_text_matches_audio else audio_text,
            content_kind,
            safe_word_count,
            hard_word_count,
        )
        if len(audio_parts) <= 1:
            split_blocks.append(ai_block)
            continue
        source_parts = (
            audio_parts
            if source_text_matches_audio
            else _partition_source_provenance(source_text, [len(audio_part) for audio_part in audio_parts])
        )

        warning_entries.append(
            {
                "chunk_id": chunk_id,
                "reason": (
                    f"Speech Block was split after AI output to fit the safe TTS budget of {safe_word_count} words."
                ),
            }
        )
        for source_part, audio_part in zip(source_parts, audio_parts, strict=True):
            split_block = dict(ai_block)
            split_block["source_text"] = source_part
            split_block["text"] = normalize_block_text(audio_part, content_kind)
            if used_hard_split:
                warning_flags = list(split_block.get("warning_flags", []))
                append_warning_flag(warning_flags, "tts_hard_split")
                split_block["warning_flags"] = warning_flags
            split_blocks.append(split_block)
    return split_blocks, warning_entries


def split_text_for_tts_budget(
    text: str,
    content_kind: str,
    safe_word_count: int,
    hard_word_count: int = 0,
    boundary_index: int = 0,
) -> tuple[list[str], bool]:
    """
    @brief      Split one text span using language-agnostic boundaries before hard fallbacks.
    @details    The safe count is a packing target: spans are combined up to it, but a span with
                no boundary left to divide on is emitted whole while it stays inside the hard
                count. Only a span past the hard count is cut where no boundary exists.
    @param[in]  text Text span to split.
    @param[in]  content_kind Current content-kind token.
    @param[in]  safe_word_count Preferred maximum estimated budget units per part.
    @param[in]  hard_word_count Budget units past which an indivisible span must be cut anyway.
    @param[in]  boundary_index Preferred boundary level index.
    @return     Tuple of split text spans and whether a hard fallback was used.
    @exception  None
    """
    source_text = str(text)
    hard_unit_limit = max(int(hard_word_count or 0), int(safe_word_count))
    if not source_text.strip():
        return [source_text], False
    if tts_budget_unit_count(normalize_block_text(source_text, content_kind)) <= safe_word_count:
        return [source_text], False

    boundary_splitters = (split_paragraph_spans, split_sentence_spans)
    for splitter in boundary_splitters[boundary_index:]:
        spans = splitter(source_text)
        if len(spans) <= 1:
            boundary_index += 1
            continue

        split_parts: list[str] = []
        used_hard_split = False
        for span in spans:
            span_parts, span_used_hard_split = split_text_for_tts_budget(
                span,
                content_kind,
                safe_word_count,
                hard_unit_limit,
                boundary_index + 1,
            )
            split_parts.extend(span_parts)
            used_hard_split = used_hard_split or span_used_hard_split
        return pack_tts_split_parts(split_parts, content_kind, safe_word_count), used_hard_split

    if tts_budget_unit_count(normalize_block_text(source_text, content_kind)) <= hard_unit_limit:
        return [source_text], False
    return hard_split_text_for_tts_budget(source_text, content_kind, hard_unit_limit), True


def split_paragraph_spans(text: str) -> list[str]:
    """
    @brief      Split text into paragraph-like spans.
    @param[in]  text Text span to split.
    @return     Non-empty paragraph spans.
    @exception  None
    """
    source_text = str(text)
    spans: list[str] = []
    cursor = 0
    for separator in re.finditer(r"\n\s*\n+", source_text):
        if separator.start() <= cursor:
            continue
        spans.append(source_text[cursor : separator.end()])
        cursor = separator.end()
    if cursor < len(source_text):
        spans.append(source_text[cursor:])
    return spans if spans else [source_text]


def split_sentence_spans(text: str) -> list[str]:
    """
    @brief      Split text into sentence-like spans using punctuation conventions from multiple scripts.
    @param[in]  text Text span to split.
    @return     Non-empty sentence-like spans.
    @exception  None
    """
    source_text = str(text)
    sentence_parts = speech_blocks_text_split_service.ai_sentence_spans(source_text)
    return sentence_parts if len(sentence_parts) > 1 else [source_text]


def pack_tts_split_parts(parts: list[str], content_kind: str, safe_word_count: int) -> list[str]:
    """
    @brief      Recombine adjacent split spans when their combined text remains inside the TTS budget.
    @param[in]  parts Candidate split spans.
    @param[in]  content_kind Current content-kind token.
    @param[in]  safe_word_count Maximum estimated budget units per part.
    @return     Packed split spans.
    @exception  None
    """
    packed_parts: list[str] = []
    current_part = ""
    for part in parts:
        candidate_part = str(part)
        if not candidate_part:
            continue
        merged_part = f"{current_part}{candidate_part}" if current_part else candidate_part
        if tts_budget_unit_count(normalize_block_text(merged_part, content_kind)) <= safe_word_count:
            current_part = merged_part
            continue
        if current_part:
            packed_parts.append(current_part)
        current_part = candidate_part
    if current_part:
        packed_parts.append(current_part)
    return packed_parts


def hard_split_text_for_tts_budget(text: str, content_kind: str, safe_word_count: int) -> list[str]:
    """
    @brief      Split text without semantic boundaries using word groups and character chunks.
    @param[in]  text Text span to split.
    @param[in]  content_kind Current content-kind token.
    @param[in]  safe_word_count Maximum estimated budget units per part.
    @return     Hard-split text spans.
    @exception  None
    """
    source_text = str(text)
    word_spans = [match.group(0) for match in re.finditer(r"\s*\S+\s*", source_text)]
    if len(word_spans) <= 1:
        return hard_split_text_by_characters(source_text, safe_word_count)

    split_parts: list[str] = []
    current_part = ""
    for word_span in word_spans:
        word_units = tts_budget_unit_count(normalize_block_text(word_span, content_kind))
        if word_units > safe_word_count:
            if current_part:
                split_parts.append(current_part)
                current_part = ""
            split_parts.extend(hard_split_text_by_characters(word_span, safe_word_count))
            continue

        candidate_text = f"{current_part}{word_span}"
        if tts_budget_unit_count(normalize_block_text(candidate_text, content_kind)) <= safe_word_count:
            current_part = candidate_text
            continue
        if current_part:
            split_parts.append(current_part)
        current_part = word_span

    if current_part:
        split_parts.append(current_part)
    return split_parts


def hard_split_text_by_characters(text: str, safe_word_count: int) -> list[str]:
    """
    @brief      Split one unbroken text span into deterministic character chunks.
    @param[in]  text Text span to split.
    @param[in]  safe_word_count Maximum estimated budget units per part.
    @return     Character chunks.
    @exception  None
    """
    source_text = str(text)
    max_characters = max(1, int(safe_word_count) * 6)
    return [
        source_text[start_index : start_index + max_characters]
        for start_index in range(0, len(source_text), max_characters)
        if source_text[start_index : start_index + max_characters]
    ]


def _partition_source_provenance(source_text: str, part_weights: list[int]) -> list[str]:
    """
    @brief      Partition source provenance into exact ordered slices for independently split audio.
    @param[in]  source_text Original block source provenance.
    @param[in]  part_weights Relative lengths of independently split spoken parts.
    @return     One contiguous source slice per spoken part without loss or duplication.
    @exception  None
    """
    source = str(source_text)
    if not part_weights:
        return []
    total_weight = max(1, sum(max(0, int(weight)) for weight in part_weights))
    boundaries = [0]
    cumulative_weight = 0
    for weight in part_weights[:-1]:
        cumulative_weight += max(0, int(weight))
        boundaries.append(round(len(source) * cumulative_weight / total_weight))
    boundaries.append(len(source))
    return [source[start:end] for start, end in zip(boundaries[:-1], boundaries[1:], strict=True)]


def safe_tts_word_count(tts_budget: dict[str, object] | None) -> int:
    """
    @brief      Resolve the safe TTS word budget for deterministic post-AI splitting.
    @param[in]  tts_budget Optional TTS budget metadata.
    @return     Positive safe word count or zero when unavailable.
    @exception  None
    """
    budget_payload = tts_budget or resolve_narrator_only_budget(None)
    return max(0, int(budget_payload.get("safe_word_count", 0) or 0))


def hard_tts_word_count(tts_budget: dict[str, object] | None) -> int:
    """
    @brief      Resolve the word count past which an indivisible span must be cut anyway.
    @param[in]  tts_budget Optional TTS budget metadata.
    @return     Hard word count, never below the safe count.
    @exception  None
    """
    budget_payload = tts_budget or resolve_narrator_only_budget(None)
    safe_word_count = safe_tts_word_count(budget_payload)
    return max(safe_word_count, int(budget_payload.get("hard_word_count", 0) or 0))


def tts_budget_unit_count(text: str) -> int:
    """
    @brief      Estimate spoken budget units with fallbacks for punctuation-heavy and no-space scripts.
    @param[in]  text Candidate text span.
    @return     Conservative budget-unit count.
    @exception  None
    """
    return tts_budget_service.estimate_budget_units(text)


def resolve_speaker_entry(
    requested_speaker_id: str,
    speaker_catalog: dict[str, dict[str, object]],
) -> tuple[dict[str, object], bool]:
    """
    @brief      Resolve one model-requested speaker id against the allowed catalog.
    @param[in]  requested_speaker_id Candidate model speaker id.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @return     Speaker entry and ambiguity flag.
    @exception  None
    """
    normalized_request = speaker_match_key(requested_speaker_id)
    if not normalized_request:
        return speaker_catalog[NARRATOR_SPEAKER_ID], False
    for speaker_id, speaker_entry in speaker_catalog.items():
        if normalized_request == speaker_match_key(speaker_id):
            return speaker_entry, False
    display_matches = [
        speaker_entry
        for speaker_entry in speaker_catalog.values()
        if normalized_request == speaker_match_key(str(speaker_entry.get("display_name", "")))
    ]
    if len(display_matches) == 1:
        return display_matches[0], False
    suffix_matches = [
        speaker_entry
        for speaker_entry in speaker_catalog.values()
        if normalized_request
        and normalized_request in speaker_match_key(str(speaker_entry.get("display_name", ""))).split()
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0], False
    if normalized_request == NARRATOR_SPEAKER_ID:
        return speaker_catalog[NARRATOR_SPEAKER_ID], False
    return speaker_catalog[NARRATOR_SPEAKER_ID], True


def speaker_match_key(value: str) -> str:
    """
    @brief      Build a conservative speaker matching key.
    @param[in]  value Candidate speaker id or display name.
    @return     Normalized speaker matching key.
    @exception  None
    """
    return " ".join(str(value).strip().replace("_", " ").replace("-", " ").casefold().split())


# END OF FILE
