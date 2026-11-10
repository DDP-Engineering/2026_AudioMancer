#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_assembly_sample_widths.py
@brief Tests for the PCM sample widths Audio Assembly accepts.
@details Audio Assembly treats every sample width as signed, so unsigned 8-bit
         PCM must be rejected rather than rendered with DC-offset silence.
"""

# IMPORTS

import wave

import pytest

from audiomancer.services import audio_assembly_service, audio_assembly_wav, operation_runtime_service


def test_eight_bit_source_is_rejected_by_input_validation(tmp_path) -> None:
    """
    @brief      Verify an 8-bit WAV block is refused with the unsupported-PCM error.
    @details    Covers REQ-FUNC-5f68f94c-8485-4e04-88c1-28c34b42ca18 / S-PCM-REJECT8.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path
    _write_wav(project_root / "audio_block.wav", sample_width=1)
    audio_blocks = [{"audio_relative_path": "audio_block.wav"}]

    try:
        audio_assembly_service._validate_compatible_wav_inputs(project_root, audio_blocks)  # noqa: SLF001
    except RuntimeError as error:
        assert "uncompressed PCM WAV" in str(error)
    else:
        raise AssertionError("8-bit PCM source was accepted by Audio Assembly input validation")


def test_sixteen_bit_source_stays_accepted(tmp_path) -> None:
    """
    @brief      Verify the width the TTS pipeline emits is still accepted.
    @details    Covers REQ-FUNC-5f68f94c-8485-4e04-88c1-28c34b42ca18 / S-PCM-KEEP16.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path
    _write_wav(project_root / "audio_block.wav", sample_width=2)

    audio_assembly_service._validate_compatible_wav_inputs(  # noqa: SLF001
        project_root,
        [{"audio_relative_path": "audio_block.wav"}],
    )


def test_silence_at_retained_widths_is_zero_filled_and_frame_exact(tmp_path) -> None:
    """
    @brief      Verify gap silence stays all-zero and exactly the requested length.
    @details    Covers REQ-FUNC-5f68f94c-8485-4e04-88c1-28c34b42ca18 / S-PCM-KEEP16. Zero
                is true silence for the signed widths that remain supported.
    @param[in]  tmp_path Temporary project root fixture.
    @return     None.
    @exception  None
    """
    output_path = tmp_path / "silence.wav"
    with wave.open(str(output_path), "wb") as output_wav:
        output_wav.setnchannels(2)
        output_wav.setsampwidth(2)
        output_wav.setframerate(8000)
        output_wav.setcomptype("NONE", "not compressed")
        params = output_wav.getparams()
        written_frames = audio_assembly_wav.append_silence(output_wav, 100, params)

    assert written_frames == 800
    with wave.open(str(output_path), "rb") as rendered_wav:
        assert rendered_wav.getnframes() == 800
        assert rendered_wav.readframes(800) == b"\x00" * 800 * 2 * 2


# HELPER FUNCTIONS


def _write_wav(path, sample_width: int) -> None:
    """
    @brief      Write one short PCM WAV file at the requested sample width.
    @param[in]  path Destination WAV path.
    @param[in]  sample_width Sample width in bytes.
    @return     None.
    @exception  None
    """
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00" * 64 * sample_width)


def test_long_silence_checks_cancellation_between_frame_chunks(tmp_path) -> None:
    """
    @brief      Cancel long silence after writing one bounded chunk.
    @param[in]  tmp_path Temporary WAV directory.
    """
    output = tmp_path / "silence.wav"
    checks = 0

    def cancel_after_one_chunk():
        """@brief Cancel at the second cancellation check."""
        nonlocal checks
        checks += 1
        return checks == 2

    params = wave._wave_params(1, 2, 24_000, 0, "NONE", "not compressed")  # noqa: SLF001
    with wave.open(str(output), "wb") as wav:
        wav.setparams(params)
        with pytest.raises(operation_runtime_service.OperationCancelledError):
            audio_assembly_wav.append_silence(wav, 60_000, params, cancel_after_one_chunk)
    with wave.open(str(output), "rb") as wav:
        assert 0 < wav.getnframes() < 24_000 * 60


# END OF FILE
