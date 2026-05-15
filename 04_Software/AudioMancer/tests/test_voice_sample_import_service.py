#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_voice_sample_import_service.py
@brief Focused tests for imported voice sample validation.
@details Verifies WAV type, duration, and silence checks before imported
         narrator or character samples enter project storage.
@author Eng. Dan Dumitru Pasare
@date 2026-05-15
@version 0.1.0
"""

# IMPORTS

from pathlib import Path
import wave

import pytest

from audiomancer import config
from audiomancer.services import voice_sample_import_service


def test_validate_imported_wav_sample_accepts_valid_sample(tmp_path) -> None:
    """
    @brief      Verify a readable non-silent WAV at or above the minimum duration is accepted.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    sample_path = tmp_path / "valid.wav"
    _write_test_wav(sample_path, duration_seconds=3.2, amplitude=4000)

    report = voice_sample_import_service.validate_imported_wav_sample(sample_path)

    assert report["duration_seconds"] >= config.DEFAULT_IMPORTED_VOICE_SAMPLE_MIN_SECONDS
    assert report["sample_rate"] == 16_000
    assert report["peak_amplitude"] > report["silence_peak_threshold"]


def test_validate_imported_wav_sample_rejects_short_sample(tmp_path) -> None:
    """
    @brief      Verify WAV samples shorter than three seconds are rejected.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    sample_path = tmp_path / "short.wav"
    _write_test_wav(sample_path, duration_seconds=1.0, amplitude=4000)

    with pytest.raises(ValueError, match="sample_too_short"):
        voice_sample_import_service.validate_imported_wav_sample(sample_path)


def test_validate_imported_wav_sample_rejects_silent_sample(tmp_path) -> None:
    """
    @brief      Verify silent WAV samples are rejected.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    sample_path = tmp_path / "silent.wav"
    _write_test_wav(sample_path, duration_seconds=3.2, amplitude=0)

    with pytest.raises(ValueError, match="sample_silent"):
        voice_sample_import_service.validate_imported_wav_sample(sample_path)


def test_validate_imported_wav_sample_rejects_non_wav(tmp_path) -> None:
    """
    @brief      Verify non-WAV file extensions are rejected before audio parsing.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    sample_path = tmp_path / "sample.mp3"
    sample_path.write_bytes(b"not a wav")

    with pytest.raises(ValueError, match="unsupported_file_type"):
        voice_sample_import_service.validate_imported_wav_sample(sample_path)


def test_validate_imported_wav_sample_rejects_unreadable_wav(tmp_path) -> None:
    """
    @brief      Verify unreadable WAV payloads are rejected.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    sample_path = tmp_path / "broken.wav"
    sample_path.write_bytes(b"not a wav")

    with pytest.raises(ValueError, match="invalid_wav"):
        voice_sample_import_service.validate_imported_wav_sample(sample_path)


def _write_test_wav(path: Path, duration_seconds: float, amplitude: int) -> None:
    """
    @brief      Write one small mono PCM WAV fixture.
    @param[in]  path Output path.
    @param[in]  duration_seconds Desired duration in seconds.
    @param[in]  amplitude Constant signed PCM amplitude.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    sample_rate = 16_000
    frame_count = int(sample_rate * duration_seconds)
    frame = int(amplitude).to_bytes(2, byteorder="little", signed=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frame * frame_count)


# END OF FILE
