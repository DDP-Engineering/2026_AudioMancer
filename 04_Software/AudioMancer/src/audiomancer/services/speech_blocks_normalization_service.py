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
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.2.1
"""

# IMPORTS

import re

from audiomancer import config
from audiomancer.services import tts_budget_service

# CONSTANTS

SPEAKER_KIND_NARRATOR = "narrator"
SPEAKER_KIND_CHARACTER = "character"
SPEAKER_KIND_OPERATION = "operation"
CONTENT_KIND_NARRATION = "narration"
CONTENT_KIND_DIALOGUE = "dialogue"
CONTENT_KIND_BACKGROUND_NOISE = "background_noise"
CONTENT_KIND_PAUSE = "pause"
CONTENT_KIND_INDICATION = "indication"

SPEECH_BLOCK_CONTENT_KINDS = (
    CONTENT_KIND_NARRATION,
    CONTENT_KIND_DIALOGUE,
    CONTENT_KIND_BACKGROUND_NOISE,
    CONTENT_KIND_PAUSE,
    CONTENT_KIND_INDICATION,
)

NARRATOR_SPEAKER_ID = "narrator"
NARRATOR_DISPLAY_NAME = "Narrator"

# PUBLIC API


def block_text_key(text: str) -> str:
    """
    @brief      Normalize text for exact source-span matching.
    @param[in]  text Candidate text.
    @return     Matching key.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return " ".join(text.strip().split()).casefold()


def append_warning_flag(warning_flags: list[str], warning_flag: str) -> None:
    """
    @brief      Append one warning flag when it is not present already.
    @param[in]  warning_flags Warning flag list to mutate.
    @param[in]  warning_flag Warning flag token.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if warning_flag not in warning_flags:
        warning_flags.append(warning_flag)


def speech_block_warning_reason(warning_flag: str) -> str:
    """
    @brief      Resolve a report note for one Speech Blocks warning flag.
    @param[in]  warning_flag Warning flag token.
    @return     Human-readable warning reason.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.1
    """
    return {
        "ambiguous_speaker": "Speaker attribution was ambiguous and fell back to narrator.",
        "source_coverage_mismatch": "Model source spans do not fully cover the chunk in reading order.",
        "source_order_mismatch": "Model source spans are not in chunk reading order.",
        "model_text_modified": "Model audio text differs from the source span beyond delimiter cleanup.",
        "tts_budget_exceeded": "Narrator-only block exceeds the safe TTS word budget.",
        "tts_hard_split": "Speech Block was hard-split after no paragraph or sentence boundary fit the TTS budget.",
        "boundary_selection_fallback": (
            "Narrator-only AI boundary selection was unusable and deterministic TTS splitting was used."
        ),
    }.get(str(warning_flag).strip(), str(warning_flag).strip() or "Speech Block warning.")


def normalize_block_text(text: str, content_kind: str) -> str:
    """
    @brief      Normalize one Speech Blocks text span without changing wording.
    @param[in]  text Candidate block text.
    @param[in]  content_kind Block content-kind token.
    @return     Persisted block text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if content_kind != CONTENT_KIND_DIALOGUE:
        return text
    normalized_text = text.strip()
    normalized_text = re.sub(r"^[-–—]\s+", "", normalized_text, count=1)
    for opening_quote, closing_quote in (('"', '"'), ("“", "”"), ("‘", "’"), ("«", "»")):
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return str(content_kind).strip() in {
        CONTENT_KIND_BACKGROUND_NOISE,
        CONTENT_KIND_PAUSE,
        CONTENT_KIND_INDICATION,
    }


def operation_speaker_entry(content_kind: str) -> dict[str, object]:
    """
    @brief      Build the persisted speaker fields for one metadata-only operation.
    @param[in]  content_kind Normalized operation content-kind token.
    @return     Speaker-like operation entry used by JSON and list rendering.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return {
        CONTENT_KIND_BACKGROUND_NOISE: "Background Noise",
        CONTENT_KIND_PAUSE: "Pause",
        CONTENT_KIND_INDICATION: "Indication",
    }.get(str(content_kind).strip(), "Operation")


def speech_block_id(chunk_id: str, sequence_index: int) -> str:
    """
    @brief      Build the persisted `CCCC-BBBBBB` Speech Block identifier.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  sequence_index Chunk-local Speech Block sequence index.
    @return     Stable Speech Block identifier.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    chunk_number = chunk_order_from_id(chunk_id)
    return f"{chunk_number:04d}-{max(int(sequence_index), 0):06d}"


def chunk_order_from_id(chunk_id: str) -> int:
    """
    @brief      Resolve a numeric chunk-order token from one chunk identifier.
    @param[in]  chunk_id Source chunk identifier.
    @return     Positive chunk-order value or zero when no digits are present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    digits = "".join(character for character in str(chunk_id) if character.isdigit())
    return int(digits[-4:] or "0")


def normalize_warning_flags(value: object) -> list[str]:
    """
    @brief      Normalize one warning-flag list payload.
    @param[in]  value Candidate warning-flag value.
    @return     Ordered warning-flag string list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if not isinstance(value, list):
        return []
    normalized_flags: list[str] = []
    for item in value:
        flag = str(item).strip()
        if flag and flag not in normalized_flags:
            normalized_flags.append(flag)
    return normalized_flags


def resolve_narrator_only_budget(settings_payload: dict[str, object] | None) -> dict[str, object]:
    """
    @brief      Resolve TTS budget metadata for narrator-only splitting.
    @param[in]  settings_payload Optional application settings payload.
    @return     TTS budget payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    discovered_models = []
    if isinstance(settings_payload, dict):
        discovered_models = [
            dict(model)
            for model in settings_payload.get("tts_runtime_discovered_models", [])
            if isinstance(model, dict)
        ]
    return tts_budget_service.resolve_cached_tts_budget(discovered_models)


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    chunk_id = str(source_chunk.get("chunk_id", "")).strip()
    chunk_text = str(source_chunk.get("text", ""))
    narrator_only = str(voice_assignment_mode).strip() == "same_narrator"
    candidate_blocks = response_payload.get("speech_blocks", response_payload.get("blocks", []))
    if not isinstance(candidate_blocks, list):
        candidate_blocks = []

    ai_blocks: list[dict[str, object]] = []
    for candidate_block in candidate_blocks:
        if not isinstance(candidate_block, dict):
            continue
        ai_block = normalize_ai_block(candidate_block, speaker_catalog, narrator_only=narrator_only)
        if str(ai_block.get("text", "")).strip():
            ai_blocks.append(ai_block)

    normalized_blocks: list[dict[str, object]] = []
    if not ai_blocks:
        fallback_flags = ["source_coverage_mismatch"]
        if not narrator_only:
            fallback_flags.append("ambiguous_speaker")
        return (
            [
                build_speech_block_payload(
                    chunk_id,
                    1,
                    source_language,
                    SPEAKER_KIND_NARRATOR,
                    NARRATOR_SPEAKER_ID,
                    NARRATOR_DISPLAY_NAME,
                    CONTENT_KIND_NARRATION,
                    chunk_text,
                    fallback_flags,
                    source_text=chunk_text,
                )
            ],
            [
                {
                    "chunk_id": chunk_id,
                    "reason": "The model response did not contain usable Speech Blocks and fell back to narrator.",
                }
            ],
        )

    warning_entries = validate_ai_block_source_spans(chunk_id, chunk_text, ai_blocks)
    ai_blocks, split_warnings = split_over_budget_ai_blocks(chunk_id, ai_blocks, tts_budget)
    warning_entries.extend(split_warnings)
    if narrator_only:
        warning_entries.extend(validate_narrator_only_budget(chunk_id, ai_blocks, tts_budget))
    for local_sequence_index, ai_block in enumerate(ai_blocks, start=1):
        text = str(ai_block.get("text", ""))
        content_kind = str(ai_block.get("content_kind", CONTENT_KIND_NARRATION))
        warning_flags = list(ai_block.get("warning_flags", []))
        source_text = str(ai_block.get("source_text", text))
        normalized_blocks.append(
            build_speech_block_payload(
                chunk_id,
                local_sequence_index,
                source_language,
                str(ai_block.get("speaker_kind", SPEAKER_KIND_NARRATOR)),
                str(ai_block.get("speaker_id", NARRATOR_SPEAKER_ID)),
                str(ai_block.get("speaker_display_name", NARRATOR_DISPLAY_NAME)),
                content_kind,
                text,
                warning_flags,
                source_text=source_text,
            )
        )

    return normalized_blocks, warning_entries


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.2.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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


def validate_ai_block_source_spans(
    chunk_id: str,
    chunk_text: str,
    ai_blocks: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Validate AI-owned source spans without replacing model block boundaries.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  chunk_text Full source chunk text.
    @param[in]  ai_blocks Normalized AI blocks to validate and annotate.
    @return     Human-readable warning entries for the chunk.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    warning_entries: list[dict[str, object]] = []
    cursor = 0
    for ai_block in ai_blocks:
        source_text = str(ai_block.get("source_text", ""))
        text = str(ai_block.get("text", ""))
        content_kind = str(ai_block.get("content_kind", CONTENT_KIND_NARRATION))
        warning_flags = list(ai_block.get("warning_flags", []))

        if not source_text.strip():
            append_warning_flag(warning_flags, "source_coverage_mismatch")
        else:
            ordered_index = chunk_text.find(source_text, cursor)
            if ordered_index >= 0:
                if chunk_text[cursor:ordered_index].strip():
                    append_warning_flag(warning_flags, "source_coverage_mismatch")
                cursor = ordered_index + len(source_text)
            elif chunk_text.find(source_text) >= 0:
                append_warning_flag(warning_flags, "source_order_mismatch")
            else:
                append_warning_flag(warning_flags, "source_coverage_mismatch")

        expected_audio_text = normalize_block_text(source_text, content_kind)
        if block_text_key(text) != block_text_key(expected_audio_text):
            append_warning_flag(warning_flags, "model_text_modified")

        ai_block["warning_flags"] = warning_flags

    if ai_blocks and chunk_text[cursor:].strip():
        warning_flags = list(ai_blocks[-1].get("warning_flags", []))
        append_warning_flag(warning_flags, "source_coverage_mismatch")
        ai_blocks[-1]["warning_flags"] = warning_flags

    if block_text_key(" ".join(str(block.get("source_text", "")) for block in ai_blocks)) != block_text_key(chunk_text):
        warning_flags = list(ai_blocks[-1].get("warning_flags", []))
        append_warning_flag(warning_flags, "source_coverage_mismatch")
        ai_blocks[-1]["warning_flags"] = warning_flags

    for ai_block in ai_blocks:
        for warning_flag in normalize_warning_flags(ai_block.get("warning_flags")):
            warning_entries.append({"chunk_id": chunk_id, "reason": speech_block_warning_reason(warning_flag)})
    return warning_entries


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    safe_word_count = safe_tts_word_count(tts_budget)
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
        split_basis_text = source_text if source_text_matches_audio else audio_text
        split_text_parts, used_hard_split = split_text_for_tts_budget(
            split_basis_text,
            content_kind,
            safe_word_count,
        )
        if len(split_text_parts) <= 1:
            split_blocks.append(ai_block)
            continue

        warning_entries.append(
            {
                "chunk_id": chunk_id,
                "reason": (
                    f"Speech Block was split after AI output to fit the safe TTS budget of {safe_word_count} words."
                ),
            }
        )
        for text_part in split_text_parts:
            split_block = dict(ai_block)
            split_block["source_text"] = text_part
            split_block["text"] = normalize_block_text(text_part, content_kind)
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
    boundary_index: int = 0,
) -> tuple[list[str], bool]:
    """
    @brief      Split one text span using language-agnostic boundaries before hard fallbacks.
    @param[in]  text Text span to split.
    @param[in]  content_kind Current content-kind token.
    @param[in]  safe_word_count Maximum estimated budget units per part.
    @param[in]  boundary_index Preferred boundary level index.
    @return     Tuple of split text spans and whether a hard fallback was used.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    normalized_text = str(text).strip()
    if not normalized_text:
        return [], False
    if tts_budget_unit_count(normalize_block_text(normalized_text, content_kind)) <= safe_word_count:
        return [normalized_text], False

    boundary_splitters = (split_paragraph_spans, split_sentence_spans)
    for splitter in boundary_splitters[boundary_index:]:
        spans = splitter(normalized_text)
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
                boundary_index + 1,
            )
            split_parts.extend(span_parts)
            used_hard_split = used_hard_split or span_used_hard_split
        return pack_tts_split_parts(split_parts, content_kind, safe_word_count), used_hard_split

    return hard_split_text_for_tts_budget(normalized_text, content_kind, safe_word_count), True


def split_paragraph_spans(text: str) -> list[str]:
    """
    @brief      Split text into paragraph-like spans.
    @param[in]  text Text span to split.
    @return     Non-empty paragraph spans.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return [part.strip() for part in re.split(r"\n\s*\n+", str(text)) if part.strip()]


def split_sentence_spans(text: str) -> list[str]:
    """
    @brief      Split text into sentence-like spans using punctuation conventions from multiple scripts.
    @param[in]  text Text span to split.
    @return     Non-empty sentence-like spans.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    normalized_text = str(text).strip()
    sentence_end_pattern = r"[.!?;:。！？；：؟؛…]+[\"'”’»)\]]*(?=\s+|$)"
    sentence_parts: list[str] = []
    cursor = 0
    for match in re.finditer(sentence_end_pattern, normalized_text):
        sentence_part = normalized_text[cursor : match.end()].strip()
        if sentence_part:
            sentence_parts.append(sentence_part)
        cursor = match.end()
    tail_part = normalized_text[cursor:].strip()
    if tail_part:
        sentence_parts.append(tail_part)
    return sentence_parts if len(sentence_parts) > 1 else [normalized_text]


def pack_tts_split_parts(parts: list[str], content_kind: str, safe_word_count: int) -> list[str]:
    """
    @brief      Recombine adjacent split spans when their combined text remains inside the TTS budget.
    @param[in]  parts Candidate split spans.
    @param[in]  content_kind Current content-kind token.
    @param[in]  safe_word_count Maximum estimated budget units per part.
    @return     Packed split spans.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    packed_parts: list[str] = []
    current_part = ""
    for part in parts:
        candidate_part = part.strip()
        if not candidate_part:
            continue
        merged_part = f"{current_part} {candidate_part}".strip() if current_part else candidate_part
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    word_spans = re.findall(r"\S+", str(text))
    if len(word_spans) <= 1:
        return hard_split_text_by_characters(str(text), safe_word_count)

    split_parts: list[str] = []
    current_words: list[str] = []
    for word_span in word_spans:
        word_units = tts_budget_unit_count(normalize_block_text(word_span, content_kind))
        if word_units > safe_word_count:
            if current_words:
                split_parts.append(" ".join(current_words))
                current_words = []
            split_parts.extend(hard_split_text_by_characters(word_span, safe_word_count))
            continue

        candidate_words = [*current_words, word_span]
        candidate_text = " ".join(candidate_words)
        if tts_budget_unit_count(normalize_block_text(candidate_text, content_kind)) <= safe_word_count:
            current_words = candidate_words
            continue
        if current_words:
            split_parts.append(" ".join(current_words))
        current_words = [word_span]

    if current_words:
        split_parts.append(" ".join(current_words))
    return split_parts


def hard_split_text_by_characters(text: str, safe_word_count: int) -> list[str]:
    """
    @brief      Split one unbroken text span into deterministic character chunks.
    @param[in]  text Text span to split.
    @param[in]  safe_word_count Maximum estimated budget units per part.
    @return     Character chunks.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    normalized_text = str(text).strip()
    max_characters = max(1, int(safe_word_count) * 6)
    return [
        normalized_text[start_index : start_index + max_characters]
        for start_index in range(0, len(normalized_text), max_characters)
        if normalized_text[start_index : start_index + max_characters].strip()
    ]


def safe_tts_word_count(tts_budget: dict[str, object] | None) -> int:
    """
    @brief      Resolve the safe TTS word budget for deterministic post-AI splitting.
    @param[in]  tts_budget Optional TTS budget metadata.
    @return     Positive safe word count or zero when unavailable.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    budget_payload = tts_budget or resolve_narrator_only_budget(None)
    return max(0, int(budget_payload.get("safe_word_count", 0) or 0))


def tts_budget_unit_count(text: str) -> int:
    """
    @brief      Estimate spoken budget units with fallbacks for punctuation-heavy and no-space scripts.
    @param[in]  text Candidate text span.
    @return     Conservative budget-unit count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    normalized_text = str(text).strip()
    if not normalized_text:
        return 0
    word_like_count = len(re.findall(r"[^\W_]+(?:['’][^\W_]+)?", normalized_text, flags=re.UNICODE))
    compact_length_units = (len(re.sub(r"\s+", "", normalized_text)) + 5) // 6
    return max(1, word_like_count, compact_length_units)


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return " ".join(str(value).strip().replace("_", " ").replace("-", " ").casefold().split())


# END OF FILE
