#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_blocks_artifact_service.py
@brief Focused tests for Audio Blocks artifact helpers.
@details Verifies generated-audio naming and WAV validation outside the large
         Audio Blocks orchestration service.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.2.0
"""

# IMPORTS

from pathlib import Path
import wave

import pytest

from audiomancer import config
from audiomancer.services import audio_blocks_artifact_service


def test_audio_blocks_artifact_paths_are_deterministic(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-df8987d1 derives artifact paths from speech_block_id alone.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    speaker_name = audio_blocks_artifact_service.normalize_speaker_name(" Maria-Elena ÃˆËœtefan!? ")
    audio_path = audio_blocks_artifact_service.audio_artifact_path(tmp_path, "0007-000003")
    part_path = audio_blocks_artifact_service.audio_part_artifact_path(tmp_path, "0007-000003", 0)

    # Speaker normalization survives for display only; it no longer reaches artifact names.
    assert speaker_name == "maria_elena_stefan"
    generated_root = tmp_path / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    assert audio_path == generated_root / "0007-000003.wav"
    assert part_path == generated_root / "parts" / "0007-000003_part001.wav"
    assert speaker_name not in audio_path.name


def test_audio_blocks_artifact_wav_validation_and_stitching(tmp_path) -> None:
    """
    @brief      Verify artifact WAV helpers reject invalid payloads and stitch compatible parts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.2.0
    """
    first_part = tmp_path / "part1.wav"
    second_part = tmp_path / "part2.wav"
    output_path = tmp_path / "stitched.wav"
    _write_wav(first_part, 8)
    _write_wav(second_part, 12)

    assert audio_blocks_artifact_service.is_valid_wav_path(first_part) is True
    assert audio_blocks_artifact_service.wav_duration_seconds(first_part) == 8 / 24_000
    assert audio_blocks_artifact_service.wav_duration_seconds(tmp_path / "missing.wav") is None
    with pytest.raises(RuntimeError, match="invalid WAV audio"):
        audio_blocks_artifact_service.validate_wav_bytes(b"not-wav")

    audio_blocks_artifact_service.stitch_wav_parts([first_part, second_part], output_path)

    with wave.open(str(output_path), "rb") as wav_file:
        assert wav_file.getnframes() == 20


def _write_wav(path: Path, frame_count: int) -> None:
    """
    @brief      Write one small mono PCM WAV test file.
    @param[in]  path Destination WAV path.
    @param[in]  frame_count Number of silent frames to write.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24_000)
        wav_file.writeframes(b"\x00\x00" * frame_count)


# END OF FILE
