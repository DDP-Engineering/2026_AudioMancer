#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file       audio_assembly_plan.py
@brief      Plan ordered WAV outputs and their silence.
@details    Operates on measured composition blocks without reading or writing files.
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import speech_blocks_service

# CONSTANTS

OUTPUT_MODE_PER_CHUNK = "per_chunk"
OUTPUT_MODE_TIME_LIMIT = "time_limit"
OUTPUT_MODE_WHOLE_BOOK = "whole_book"


AudioAssemblySettings = dict[str, object]

# PUBLIC API


def build_output_plan(
    playable_blocks: list[dict[str, object]],
    settings: AudioAssemblySettings,
) -> list[dict[str, object]]:
    """
    @brief      Build ordered output-file composition groups from Audio Blocks and settings.
    @param[in]  playable_blocks Ordered WAV sources, scene mixes and explicit pauses.
    @param[in]  settings Normalized Audio Assembly settings.
    @return     Ordered output plan entries.
    @exception  ValueError Raised when no playable blocks exist.
    """
    if not playable_blocks:
        raise ValueError("Audio Assembly requires at least one generated speech audio block.")
    output_mode = str(settings["output_mode"])
    if output_mode == OUTPUT_MODE_PER_CHUNK:
        return _with_reference_audio_path(_plan_per_chunk_outputs(playable_blocks), playable_blocks)
    if output_mode == OUTPUT_MODE_TIME_LIMIT:
        return _with_reference_audio_path(
            _plan_time_limited_outputs(playable_blocks, int(settings["max_duration_minutes"]), settings),
            playable_blocks,
        )
    return _with_reference_audio_path(
        [
            {
                "output_key": "audiobook",
                "file_name": "audiobook.wav",
                "blocks": playable_blocks,
                "chunk_ids": sorted({str(block.get("chunk_id", "")) for block in playable_blocks}),
                "over_limit_warning": False,
            }
        ],
        playable_blocks,
    )


def _plan_per_chunk_outputs(blocks: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Build one output file per text chunk.
    @param[in]  blocks Playable Audio Blocks.
    @return     Ordered per-chunk output plan.
    @exception  None
    """
    grouped: dict[str, list[dict[str, object]]] = {}
    for block in blocks:
        grouped.setdefault(str(block.get("chunk_id", "")).strip(), []).append(block)
    output_plan = []
    for output_index, chunk_id in enumerate(grouped, start=1):
        output_plan.append(
            {
                "output_key": f"chunk-{output_index:04d}",
                "file_name": f"chunk-{output_index:04d}.wav",
                "blocks": grouped[chunk_id],
                "chunk_ids": [chunk_id],
                "over_limit_warning": False,
            }
        )
    return output_plan


def _plan_time_limited_outputs(
    blocks: list[dict[str, object]],
    max_minutes: int,
    settings: AudioAssemblySettings,
) -> list[dict[str, object]]:
    """
    @brief      Pack sequential blocks into duration-limited output parts.
    @param[in]  blocks Playable Audio Blocks.
    @param[in]  max_minutes Maximum requested part duration.
    @param[in]  settings Normalized Audio Assembly settings.
    @return     Ordered time-limited output plan.
    @exception  None
    """
    max_seconds = max(1, int(max_minutes) * 60)
    output_plan: list[dict[str, object]] = []
    current_blocks: list[dict[str, object]] = []
    current_seconds = 0.0
    for block in blocks:
        block_seconds = float(block.get("duration_seconds", 0.0))
        added_seconds = block_seconds
        if current_blocks:
            added_seconds += automatic_gap_ms(current_blocks[-1], block, settings) / 1000.0
        if current_blocks and current_seconds + added_seconds > max_seconds:
            output_plan.append(_time_part_record(len(output_plan) + 1, current_blocks, False))
            current_blocks = []
            current_seconds = 0.0
            added_seconds = block_seconds
        current_blocks.append(block)
        current_seconds += added_seconds
        if block_seconds > max_seconds:
            output_plan.append(_time_part_record(len(output_plan) + 1, current_blocks, True))
            current_blocks = []
            current_seconds = 0.0
    if current_blocks:
        output_plan.append(_time_part_record(len(output_plan) + 1, current_blocks, False))
    return output_plan


def _time_part_record(
    output_index: int,
    blocks: list[dict[str, object]],
    over_limit_warning: bool,
) -> dict[str, object]:
    """
    @brief      Build one time-limited output plan record.
    @param[in]  output_index Sequential output index.
    @param[in]  blocks Blocks assigned to the output.
    @param[in]  over_limit_warning True when one block exceeds the limit.
    @return     Output plan record.
    @exception  None
    """
    return {
        "output_key": f"part-{output_index:04d}",
        "file_name": f"part-{output_index:04d}.wav",
        "blocks": list(blocks),
        "chunk_ids": sorted({str(block.get("chunk_id", "")) for block in blocks}),
        "over_limit_warning": over_limit_warning,
    }


def _with_reference_audio_path(
    output_plan: list[dict[str, object]],
    blocks: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    @brief      Add a fallback source WAV reference to planned outputs.
    @param[in]  output_plan Planned output records.
    @param[in]  blocks Full composable Audio Block list.
    @return     Output plan with optional reference audio paths.
    @exception  None
    """
    reference_path = next(
        (
            str(block.get("audio_relative_path", "")).strip()
            for block in blocks
            if str(block.get("audio_relative_path", "") or "").strip()
        ),
        "",
    )
    for output_item in output_plan:
        output_item["reference_audio_relative_path"] = reference_path
    return output_plan


def automatic_gap_ms(
    previous_block: dict[str, object],
    current_block: dict[str, object],
    settings: AudioAssemblySettings,
) -> int:
    """
    @brief      Resolve automatic silence inserted between two adjacent blocks.
    @param[in]  previous_block Previous planned Audio Block.
    @param[in]  current_block Current planned Audio Block.
    @param[in]  settings Normalized Audio Assembly settings.
    @return     Automatic gap in milliseconds.
    @exception  None
    """
    if is_pause_block(previous_block) or is_pause_block(current_block):
        return 0
    if str(current_block.get("chunk_id", "")) != str(previous_block.get("chunk_id", "")):
        return int(settings["inter_chunk_silence_ms"])
    return int(settings["inter_block_silence_ms"])


def is_pause_block(audio_block: dict[str, object]) -> bool:
    """
    @brief      Return whether one Audio Block represents metadata-only pause silence.
    @param[in]  audio_block Audio Block payload.
    @return     True for pause content-kind blocks.
    @exception  None
    """
    return (
        bool(audio_block.get("metadata_only", False))
        and str(audio_block.get("content_kind", "")).strip() == speech_blocks_service.CONTENT_KIND_PAUSE
    )


def pause_duration_ms(audio_block: dict[str, object]) -> int:
    """
    @brief      Resolve one metadata-only pause block duration.
    @param[in]  audio_block Audio Block payload.
    @return     Positive pause duration in milliseconds.
    @exception  None
    """
    value = audio_block.get("pause_duration_ms")
    try:
        duration_ms = int(value)
    except (TypeError, ValueError):
        return config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS
    if duration_ms <= 0:
        return config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS
    return duration_ms


# END OF FILE
