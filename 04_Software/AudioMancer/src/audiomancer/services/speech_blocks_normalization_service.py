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
@version 0.3.0
"""

# IMPORTS

from dataclasses import dataclass
import re

from audiomancer import config
from audiomancer.services import cleanup_text_analysis_service, tts_budget_service
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if content_kind != CONTENT_KIND_DIALOGUE:
        return str(text).strip()
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
        CONTENT_KIND_SCENE_AMBIENCE: "Scene Ambience",
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


@dataclass(frozen=True)
class SourceSpan:
    """
    @brief      One deterministic selectable source span inside a Speech Blocks chunk.
    @param[in]  source_span_id Stable span identifier exposed to the model.
    @param[in]  start_offset Inclusive character offset in the source chunk.
    @param[in]  end_offset Exclusive character offset in the source chunk.
    @param[in]  text Exact source text covered by the span.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """

    source_span_id: str
    start_offset: int
    end_offset: int
    text: str


@dataclass(frozen=True)
class AtomicSpeechUnit:
    """
    @brief      One deterministic atomic Speech Blocks unit inside a chunk.
    @param[in]  atomic_unit_id Stable unit identifier exposed to the model.
    @param[in]  source_span_id Parent source-span identifier.
    @param[in]  start_offset Inclusive character offset in the source chunk.
    @param[in]  end_offset Exclusive character offset in the source chunk.
    @param[in]  text Exact source text covered by the unit.
    @param[in]  structural_kind Atomic structure: dialogue, attribution, narration, separator, or mixed.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """

    atomic_unit_id: str
    source_span_id: str
    start_offset: int
    end_offset: int
    text: str
    structural_kind: str


@dataclass(frozen=True)
class SpeechBlockModelSelection:
    """
    @brief      Model-owned span and speaker selection without final saved text.
    @param[in]  source_span_ids Ordered selected source-span identifiers.
    @param[in]  speaker_id Requested speaker identifier.
    @param[in]  content_kind Requested Speech Blocks content kind.
    @param[in]  confidence Model confidence token.
    @param[in]  warning_flags Model warning flags.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """

    source_span_ids: tuple[str, ...]
    speaker_id: str
    content_kind: str
    confidence: str
    warning_flags: tuple[str, ...]


@dataclass(frozen=True)
class SpeechBlockSelectionValidationResult:
    """
    @brief      Validated span-selection result or the warning that caused fallback.
    @param[in]  ai_blocks Reconstructed AI-block-like payloads.
    @param[in]  warning_flag Blocking warning flag when validation failed.
    @param[in]  reason Human-readable validation detail.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """

    ai_blocks: tuple[dict[str, object], ...]
    warning_flag: str = ""
    reason: str = ""

    @property
    def is_valid(self) -> bool:
        """
        @brief      Return whether validation produced reconstructed blocks.
        @return     True when the model selection can be persisted.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-01
        @version    0.1.0
        """
        return not self.warning_flag


def source_span_selection_contract_requested(
    source_chunk: dict[str, object],
    candidate_blocks: list[object],
) -> bool:
    """
    @brief      Return whether the current response uses the span-selection contract.
    @param[in]  source_chunk Current source chunk payload.
    @param[in]  candidate_blocks Raw model block candidates.
    @return     True when app-owned source spans are present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    _ = candidate_blocks
    return "source_spans" in source_chunk


def normalize_source_span_selection_chunk_blocks(
    source_chunk: dict[str, object],
    candidate_blocks: list[object],
    speaker_catalog: dict[str, dict[str, object]],
    source_language: str,
    narrator_only: bool,
    tts_budget: dict[str, object] | None,
    require_confidence: bool = True,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """
    @brief      Normalize span-id model selections into persisted Speech Blocks payloads.
    @param[in]  source_chunk Current source chunk payload.
    @param[in]  candidate_blocks Raw model block candidates.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  source_language Active source language code.
    @param[in]  narrator_only True when the project uses one narrator voice.
    @param[in]  tts_budget Optional narrator-only TTS budget metadata.
    @param[in]  require_confidence True when the active response contract requires confidence.
    @return     Tuple of normalized chunk blocks and warning entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    chunk_id = str(source_chunk.get("chunk_id", "")).strip()
    chunk_text = str(source_chunk.get("text", ""))
    source_spans, source_span_error = parse_source_spans(source_chunk, chunk_text)
    if source_span_error:
        return source_span_selection_fallback(
            chunk_id,
            chunk_text,
            source_language,
            "source_span_selection_invalid",
            source_span_error,
        )

    if any(isinstance(candidate_block, dict) and "unit_ids" in candidate_block for candidate_block in candidate_blocks):
        atomic_units, atomic_unit_error = parse_atomic_units(source_chunk, chunk_text)
        if atomic_unit_error:
            return source_span_selection_fallback(
                chunk_id,
                chunk_text,
                source_language,
                "atomic_unit_selection_invalid",
                atomic_unit_error,
            )
        validation_result = validate_atomic_unit_model_selections(
            candidate_blocks,
            atomic_units,
            speaker_catalog,
            require_confidence=require_confidence,
        )
        if not validation_result.is_valid:
            return source_span_selection_fallback(
                chunk_id,
                chunk_text,
                source_language,
                validation_result.warning_flag,
                validation_result.reason,
            )
        ai_blocks = [dict(ai_block) for ai_block in validation_result.ai_blocks]
        warning_entries = warning_entries_from_ai_blocks(chunk_id, ai_blocks)
        ai_blocks, split_warnings = split_over_budget_ai_blocks(chunk_id, ai_blocks, tts_budget)
        warning_entries.extend(split_warnings)
        if narrator_only:
            warning_entries.extend(validate_narrator_only_budget(chunk_id, ai_blocks, tts_budget))

        normalized_blocks: list[dict[str, object]] = []
        for local_sequence_index, ai_block in enumerate(ai_blocks, start=1):
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

    validation_result = validate_source_span_model_selections(
        candidate_blocks,
        source_spans,
        speaker_catalog,
        require_confidence=require_confidence,
    )
    if not validation_result.is_valid:
        return source_span_selection_fallback(
            chunk_id,
            chunk_text,
            source_language,
            validation_result.warning_flag,
            validation_result.reason,
        )

    ai_blocks = [dict(ai_block) for ai_block in validation_result.ai_blocks]
    warning_entries = warning_entries_from_ai_blocks(chunk_id, ai_blocks)
    ai_blocks, split_warnings = split_over_budget_ai_blocks(chunk_id, ai_blocks, tts_budget)
    warning_entries.extend(split_warnings)
    if narrator_only:
        warning_entries.extend(validate_narrator_only_budget(chunk_id, ai_blocks, tts_budget))

    normalized_blocks: list[dict[str, object]] = []
    for local_sequence_index, ai_block in enumerate(ai_blocks, start=1):
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


def source_span_response_requires_confidence(response_payload: dict[str, object]) -> bool:
    """
    @brief      Return whether a response payload is using the strict source-span contract.
    @param[in]  response_payload Raw model response payload.
    @return     True for the new `blocks` contract, false for legacy `speech_blocks` fixtures.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    return "blocks" in response_payload or "speech_blocks" not in response_payload


def source_span_candidate_blocks(response_payload: dict[str, object]) -> list[object]:
    """
    @brief      Extract source-span block candidates from a model response payload.
    @param[in]  response_payload Raw model response payload.
    @return     Candidate block list or an empty list for malformed roots.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    candidate_blocks = response_payload.get("speech_blocks", response_payload.get("blocks", []))
    if not isinstance(candidate_blocks, list):
        return []
    return list(candidate_blocks)


def parse_source_spans(
    source_chunk: dict[str, object],
    chunk_text: str,
) -> tuple[list[SourceSpan], str]:
    """
    @brief      Parse and validate deterministic source spans from one chunk.
    @param[in]  source_chunk Current source chunk payload.
    @param[in]  chunk_text Exact source chunk text.
    @return     Tuple of source spans and an error string when invalid.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.1
    """
    chunk_id = str(source_chunk.get("chunk_id", "")).strip()
    raw_spans = source_chunk.get("source_spans", [])
    if not isinstance(raw_spans, list) or not raw_spans:
        return [], "source_spans missing from the source chunk."

    source_spans: list[SourceSpan] = []
    seen_span_ids: set[str] = set()
    for raw_span in raw_spans:
        if not isinstance(raw_span, dict):
            return [], "source_spans contains a non-object entry."
        source_span_id = str(raw_span.get("source_span_id", raw_span.get("id", ""))).strip()
        if not source_span_id:
            return [], "source_spans contains an entry without source_span_id."
        if source_span_id in seen_span_ids:
            return [], f"source_span_id {source_span_id} appears more than once."
        try:
            start_offset = int(raw_span.get("start_offset"))
            end_offset = int(raw_span.get("end_offset"))
        except (TypeError, ValueError):
            _SPEECH_BLOCKS_NORMALIZATION_LOGGER.warning(
                "speech_blocks_source_span_parse_failed chunk_id=%s source_span_id=%s reason=invalid_offsets",
                chunk_id or "<unknown>",
                source_span_id or "<missing>",
            )
            return [], f"source_span_id {source_span_id} has invalid offsets."
        if start_offset < 0 or end_offset <= start_offset or end_offset > len(chunk_text):
            return [], f"source_span_id {source_span_id} has offsets outside the chunk."
        span_text = str(raw_span.get("text", chunk_text[start_offset:end_offset]))
        if span_text != chunk_text[start_offset:end_offset]:
            return [], f"source_span_id {source_span_id} text does not match chunk offsets."
        seen_span_ids.add(source_span_id)
        source_spans.append(SourceSpan(source_span_id, start_offset, end_offset, span_text))

    source_spans.sort(key=lambda source_span: (source_span.start_offset, source_span.end_offset))
    cursor = 0
    for source_span in source_spans:
        if source_span.start_offset != cursor:
            return [], "source_spans do not cover the source chunk contiguously."
        cursor = source_span.end_offset
    if cursor != len(chunk_text):
        return [], "source_spans do not cover the full source chunk."
    return source_spans, ""


def parse_atomic_units(
    source_chunk: dict[str, object],
    chunk_text: str,
) -> tuple[list[AtomicSpeechUnit], str]:
    """
    @brief      Parse and validate deterministic atomic speech units from one chunk.
    @param[in]  source_chunk Current source chunk payload.
    @param[in]  chunk_text Exact source chunk text.
    @return     Tuple of atomic units and an error string when invalid.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    raw_units = source_chunk.get("atomic_units", [])
    if not isinstance(raw_units, list) or not raw_units:
        return [], "atomic_units missing from the source chunk."

    atomic_units: list[AtomicSpeechUnit] = []
    seen_unit_ids: set[str] = set()
    for raw_unit in raw_units:
        if not isinstance(raw_unit, dict):
            return [], "atomic_units contains a non-object entry."
        atomic_unit_id = str(raw_unit.get("atomic_unit_id", raw_unit.get("unit_id", ""))).strip()
        if not atomic_unit_id:
            return [], "atomic_units contains an entry without atomic_unit_id."
        if atomic_unit_id in seen_unit_ids:
            return [], f"atomic_unit_id {atomic_unit_id} appears more than once."
        try:
            start_offset = int(raw_unit.get("start_offset"))
            end_offset = int(raw_unit.get("end_offset"))
        except (TypeError, ValueError):
            return [], f"atomic_unit_id {atomic_unit_id} has invalid offsets."
        if start_offset < 0 or end_offset <= start_offset or end_offset > len(chunk_text):
            return [], f"atomic_unit_id {atomic_unit_id} has out-of-range offsets."
        unit_text = str(raw_unit.get("text", ""))
        if unit_text != chunk_text[start_offset:end_offset]:
            return [], f"atomic_unit_id {atomic_unit_id} text does not match chunk offsets."
        structural_kind = str(raw_unit.get("structural_kind", "")).strip() or CONTENT_KIND_NARRATION
        seen_unit_ids.add(atomic_unit_id)
        atomic_units.append(
            AtomicSpeechUnit(
                atomic_unit_id,
                str(raw_unit.get("source_span_id", "")).strip(),
                start_offset,
                end_offset,
                unit_text,
                structural_kind,
            )
        )

    atomic_units.sort(key=lambda atomic_unit: (atomic_unit.start_offset, atomic_unit.end_offset))
    cursor = 0
    for atomic_unit in atomic_units:
        if atomic_unit.start_offset != cursor:
            return [], "atomic_units do not cover the source chunk contiguously."
        cursor = atomic_unit.end_offset
    if cursor != len(chunk_text):
        return [], "atomic_units do not cover the full source chunk."
    return atomic_units, ""


def validate_atomic_unit_model_selections(
    candidate_blocks: list[object],
    atomic_units: list[AtomicSpeechUnit],
    speaker_catalog: dict[str, dict[str, object]],
    require_confidence: bool = True,
) -> SpeechBlockSelectionValidationResult:
    """
    @brief      Validate model atomic-unit selections and reconstruct AI-block-like payloads.
    @param[in]  candidate_blocks Raw model block candidates.
    @param[in]  atomic_units Atomic units available for the active chunk.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  require_confidence True when missing confidence should invalidate the selection.
    @return     Validation result with reconstructed blocks or a fallback reason.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    unit_by_id = {atomic_unit.atomic_unit_id: atomic_unit for atomic_unit in atomic_units}
    selectable_unit_ids = {
        atomic_unit.atomic_unit_id for atomic_unit in atomic_units if selectable_atomic_unit(atomic_unit)
    }
    used_unit_ids: set[str] = set()
    last_selected_start_offset = -1
    ai_blocks: list[dict[str, object]] = []

    for candidate_block in candidate_blocks:
        if not isinstance(candidate_block, dict):
            return SpeechBlockSelectionValidationResult(
                (),
                "atomic_unit_selection_invalid",
                "Model block selection is not an object.",
            )
        raw_unit_ids = candidate_block.get("unit_ids")
        if not isinstance(raw_unit_ids, (list, tuple)):
            return SpeechBlockSelectionValidationResult(
                (),
                "atomic_unit_selection_invalid",
                "Model block selection did not include unit_ids.",
            )
        unit_ids = tuple(str(unit_id).strip() for unit_id in raw_unit_ids if str(unit_id).strip())
        confidence = str(candidate_block.get("confidence", "")).strip()
        if require_confidence and not confidence:
            return SpeechBlockSelectionValidationResult(
                (),
                "atomic_unit_selection_invalid",
                "missing_confidence: Model block selection did not include confidence.",
            )
        if not unit_ids:
            return SpeechBlockSelectionValidationResult(
                (),
                "atomic_unit_selection_invalid",
                "Model block selection did not include unit_ids.",
            )
        if len(set(unit_ids)) != len(unit_ids):
            return SpeechBlockSelectionValidationResult(
                (),
                "atomic_unit_selection_invalid",
                "Model block selection reused an atomic unit id inside one block.",
            )

        selected_units: list[AtomicSpeechUnit] = []
        for unit_id in unit_ids:
            if re.fullmatch(r"u\d{3}", unit_id) is None:
                return SpeechBlockSelectionValidationResult(
                    (),
                    "atomic_unit_selection_invalid",
                    f"illegal_unit_id: Model selected malformed unit_id {unit_id}.",
                )
            atomic_unit = unit_by_id.get(unit_id)
            if atomic_unit is None:
                return SpeechBlockSelectionValidationResult(
                    (),
                    "atomic_unit_selection_invalid",
                    f"unavailable_unit_id: Model selected unavailable unit_id {unit_id}.",
                )
            if not selectable_atomic_unit(atomic_unit):
                return SpeechBlockSelectionValidationResult(
                    (),
                    "atomic_unit_selection_invalid",
                    f"non_selectable_unit_id: Model selected separator or whitespace-only atomic_unit_id {unit_id}.",
                )
            if unit_id in used_unit_ids:
                return SpeechBlockSelectionValidationResult(
                    (),
                    "atomic_unit_selection_invalid",
                    f"Model selected atomic_unit_id {unit_id} more than once.",
                )
            if atomic_unit.start_offset <= last_selected_start_offset:
                return SpeechBlockSelectionValidationResult(
                    (),
                    "atomic_unit_selection_invalid",
                    "Model selected unit_ids outside source reading order.",
                )
            selected_units.append(atomic_unit)
            used_unit_ids.add(unit_id)
            last_selected_start_offset = atomic_unit.start_offset

        content_kind = normalize_content_kind(candidate_block.get("content_kind", CONTENT_KIND_NARRATION))
        structural_kinds = {atomic_unit.structural_kind for atomic_unit in selected_units}
        if content_kind == CONTENT_KIND_DIALOGUE and structural_kinds != {"dialogue"}:
            return SpeechBlockSelectionValidationResult(
                (),
                "atomic_unit_selection_invalid",
                "Dialogue block selected attribution or narration atomic units.",
            )
        if content_kind == CONTENT_KIND_NARRATION and "dialogue" in structural_kinds:
            return SpeechBlockSelectionValidationResult(
                (),
                "atomic_unit_selection_invalid",
                "Narration block selected dialogue atomic units.",
            )

        speaker_id = str(candidate_block.get("speaker_id", "")).strip()
        speaker_entry = strict_speaker_entry(speaker_id, content_kind, speaker_catalog)
        if speaker_entry is None:
            return SpeechBlockSelectionValidationResult(
                (),
                "speaker_selection_invalid",
                f"Model selected unknown speaker_id {speaker_id}.",
            )
        if content_kind == CONTENT_KIND_NARRATION and str(speaker_entry.get("speaker_id")) != NARRATOR_SPEAKER_ID:
            return SpeechBlockSelectionValidationResult(
                (),
                "speaker_selection_invalid",
                "Narration or attribution atomic units must use narrator.",
            )

        source_text = "".join(atomic_unit.text for atomic_unit in selected_units)
        ai_blocks.append(
            {
                "speaker_kind": str(speaker_entry.get("speaker_kind", SPEAKER_KIND_NARRATOR)),
                "speaker_id": str(speaker_entry.get("speaker_id", NARRATOR_SPEAKER_ID)),
                "speaker_display_name": str(speaker_entry.get("display_name", NARRATOR_DISPLAY_NAME)),
                "content_kind": content_kind,
                "source_text": source_text,
                "text": normalize_block_text(source_text.strip(), content_kind),
                "warning_flags": list(
                    normalize_warning_flags(candidate_block.get("warning_flags", candidate_block.get("warnings")))
                ),
            }
        )

    if not ai_blocks:
        return SpeechBlockSelectionValidationResult(
            (),
            "atomic_unit_selection_invalid",
            "Model response did not contain usable atomic unit selections.",
        )
    if used_unit_ids != selectable_unit_ids:
        return SpeechBlockSelectionValidationResult(
            (),
            "atomic_unit_selection_invalid",
            "Model unit selections did not cover every selectable atomic unit.",
        )
    return SpeechBlockSelectionValidationResult(tuple(ai_blocks))


def selectable_atomic_unit(atomic_unit: AtomicSpeechUnit) -> bool:
    """
    @brief      Decide whether an atomic unit is selectable model-owned audiobook content.
    @param[in]  atomic_unit Parsed deterministic atomic unit.
    @return     True for speakable units; False for separator-only or whitespace-only provenance.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    return atomic_unit.structural_kind.strip().casefold() != "separator" and bool(atomic_unit.text.strip())


def validate_source_span_model_selections(
    candidate_blocks: list[object],
    source_spans: list[SourceSpan],
    speaker_catalog: dict[str, dict[str, object]],
    require_confidence: bool = True,
) -> SpeechBlockSelectionValidationResult:
    """
    @brief      Validate model span selections and reconstruct AI-block-like payloads.
    @param[in]  candidate_blocks Raw model block candidates.
    @param[in]  source_spans Source spans available for the active chunk.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @param[in]  require_confidence True when missing confidence should invalidate the selection.
    @return     Validation result with reconstructed blocks or a fallback reason.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    span_by_id = {source_span.source_span_id: source_span for source_span in source_spans}
    used_span_ids: set[str] = set()
    last_selected_start_offset = -1
    ai_blocks: list[dict[str, object]] = []

    for candidate_block in candidate_blocks:
        if not isinstance(candidate_block, dict):
            return SpeechBlockSelectionValidationResult(
                (),
                "source_span_selection_invalid",
                "Model block selection is not an object.",
            )
        selection = speech_block_model_selection(candidate_block)
        if require_confidence and not selection.confidence:
            return SpeechBlockSelectionValidationResult(
                (),
                "source_span_selection_invalid",
                "missing_confidence: Model block selection did not include confidence.",
            )
        if not selection.source_span_ids:
            return SpeechBlockSelectionValidationResult(
                (),
                "source_span_selection_invalid",
                "Model block selection did not include source_span_ids.",
            )
        if len(set(selection.source_span_ids)) != len(selection.source_span_ids):
            return SpeechBlockSelectionValidationResult(
                (),
                "source_span_selection_invalid",
                "Model block selection reused a source span id inside one block.",
            )
        selected_spans: list[SourceSpan] = []
        for source_span_id in selection.source_span_ids:
            if re.fullmatch(r"s\d{3}", source_span_id) is None:
                return SpeechBlockSelectionValidationResult(
                    (),
                    "source_span_selection_invalid",
                    f"illegal_span_id: Model selected malformed source_span_id {source_span_id}.",
                )
            source_span = span_by_id.get(source_span_id)
            if source_span is None:
                return SpeechBlockSelectionValidationResult(
                    (),
                    "source_span_selection_invalid",
                    f"halo_span_id: Model selected unavailable source_span_id {source_span_id}.",
                )
            if source_span_id in used_span_ids:
                return SpeechBlockSelectionValidationResult(
                    (),
                    "source_span_selection_invalid",
                    f"Model selected source_span_id {source_span_id} more than once.",
                )
            if source_span.start_offset <= last_selected_start_offset:
                return SpeechBlockSelectionValidationResult(
                    (),
                    "source_span_selection_invalid",
                    "Model selected source_span_ids outside source reading order.",
                )
            selected_spans.append(source_span)
            used_span_ids.add(source_span_id)
            last_selected_start_offset = source_span.start_offset

        content_kind = normalize_content_kind(selection.content_kind)
        speaker_entry = strict_speaker_entry(selection.speaker_id, content_kind, speaker_catalog)
        if speaker_entry is None:
            return SpeechBlockSelectionValidationResult(
                (),
                "speaker_selection_invalid",
                f"Model selected unknown speaker_id {selection.speaker_id}.",
            )
        source_text = "".join(source_span.text for source_span in selected_spans)
        ai_blocks.append(
            {
                "speaker_kind": str(speaker_entry.get("speaker_kind", SPEAKER_KIND_NARRATOR)),
                "speaker_id": str(speaker_entry.get("speaker_id", NARRATOR_SPEAKER_ID)),
                "speaker_display_name": str(speaker_entry.get("display_name", NARRATOR_DISPLAY_NAME)),
                "content_kind": content_kind,
                "source_text": source_text,
                "text": normalize_block_text(source_text.strip(), content_kind),
                "warning_flags": list(selection.warning_flags),
            }
        )

    if not ai_blocks:
        return SpeechBlockSelectionValidationResult(
            (),
            "source_span_selection_invalid",
            "Model response did not contain usable span selections.",
        )
    if used_span_ids != set(span_by_id):
        return SpeechBlockSelectionValidationResult(
            (),
            "source_span_selection_invalid",
            "Model span selections did not cover the full source chunk.",
        )
    return SpeechBlockSelectionValidationResult(tuple(ai_blocks))


def speech_block_model_selection(candidate_block: dict[str, object]) -> SpeechBlockModelSelection:
    """
    @brief      Parse a raw model block as a span-selection payload.
    @param[in]  candidate_block Raw model block payload.
    @return     Parsed model selection.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    raw_source_span_ids = candidate_block.get("source_span_ids")
    source_span_ids: tuple[str, ...] = ()
    if isinstance(raw_source_span_ids, (list, tuple)):
        source_span_ids = tuple(
            str(source_span_id).strip() for source_span_id in raw_source_span_ids if str(source_span_id).strip()
        )
    raw_warning_flags = candidate_block.get("warning_flags")
    if raw_warning_flags is None:
        raw_warning_flags = candidate_block.get("warnings")
    return SpeechBlockModelSelection(
        source_span_ids,
        str(candidate_block.get("speaker_id", "")).strip(),
        str(candidate_block.get("content_kind", CONTENT_KIND_NARRATION)).strip(),
        str(candidate_block.get("confidence", "")).strip(),
        tuple(normalize_warning_flags(raw_warning_flags)),
    )


def strict_speaker_entry(
    speaker_id: str,
    content_kind: str,
    speaker_catalog: dict[str, dict[str, object]],
) -> dict[str, object] | None:
    """
    @brief      Resolve only exact contract speaker ids for span-selection output.
    @param[in]  speaker_id Model-selected speaker id.
    @param[in]  content_kind Normalized content kind.
    @param[in]  speaker_catalog Allowed speaker catalog.
    @return     Speaker entry when exact, otherwise None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    if is_operation_content_kind(content_kind):
        return operation_speaker_entry(content_kind)
    normalized_speaker_id = str(speaker_id).strip()
    if normalized_speaker_id == NARRATOR_SPEAKER_ID:
        return speaker_catalog.get(
            NARRATOR_SPEAKER_ID,
            {
                "speaker_id": NARRATOR_SPEAKER_ID,
                "speaker_kind": SPEAKER_KIND_NARRATOR,
                "display_name": NARRATOR_DISPLAY_NAME,
            },
        )
    speaker_entry = speaker_catalog.get(normalized_speaker_id)
    if not isinstance(speaker_entry, dict):
        return None
    if str(speaker_entry.get("speaker_id", "")).strip() != normalized_speaker_id:
        return None
    return speaker_entry


def source_span_selection_fallback(
    chunk_id: str,
    chunk_text: str,
    source_language: str,
    warning_flag: str,
    validation_reason: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """
    @brief      Build a deterministic narrator fallback for invalid span-selection output.
    @param[in]  chunk_id Source chunk identifier.
    @param[in]  chunk_text Full source chunk text.
    @param[in]  source_language Active source language code.
    @param[in]  warning_flag Blocking validation warning flag.
    @param[in]  validation_reason Human-readable validation detail.
    @return     Tuple of one narrator block and warning entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    normalized_warning_flag = str(warning_flag).strip() or "source_span_selection_invalid"
    reason = f"{normalized_warning_flag}: {validation_reason or speech_block_warning_reason(normalized_warning_flag)}"
    fallback_text = re.sub(r'"([^"]*)"', r"\1", chunk_text.strip())
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
                normalize_block_text(fallback_text, CONTENT_KIND_NARRATION),
                [normalized_warning_flag],
                source_text=chunk_text,
            )
        ],
        [{"chunk_id": chunk_id, "reason": reason}],
    )


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    warning_entries: list[dict[str, object]] = []
    for ai_block in ai_blocks:
        for warning_flag in normalize_warning_flags(ai_block.get("warning_flags")):
            warning_entries.append({"chunk_id": chunk_id, "reason": speech_block_warning_reason(warning_flag)})
    return warning_entries


def resolve_narrator_only_budget(settings_payload: dict[str, object] | None) -> dict[str, object]:
    """
    @brief      Resolve TTS budget metadata for narrator-only splitting.
    @details    The model budget is the hard cap; the operator's preferred block duration can
                only narrow it further.
    @param[in]  settings_payload Optional application settings payload.
    @return     TTS budget payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.2.0
    """
    discovered_models = []
    if isinstance(settings_payload, dict):
        discovered_models = [
            dict(model)
            for model in settings_payload.get("tts_runtime_discovered_models", [])
            if isinstance(model, dict)
        ]
    return tts_budget_service.apply_block_target_audio_seconds(
        tts_budget_service.resolve_cached_tts_budget(discovered_models),
        settings_payload,
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    narrator_only = str(voice_assignment_mode).strip() == "same_narrator"
    candidate_blocks = response_payload.get("speech_blocks", response_payload.get("blocks", []))
    if not isinstance(candidate_blocks, list):
        candidate_blocks = []

    if source_span_selection_contract_requested(source_chunk, candidate_blocks):
        require_confidence = source_span_response_requires_confidence(response_payload)
        return normalize_source_span_selection_chunk_blocks(
            source_chunk,
            candidate_blocks,
            speaker_catalog,
            source_language,
            narrator_only,
            tts_budget,
            require_confidence=require_confidence,
        )

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
    sentence_parts = [
        span.strip()
        for span in cleanup_text_analysis_service.sentence_spans(normalized_text, include_clause_marks=True)
        if span.strip()
    ]
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
