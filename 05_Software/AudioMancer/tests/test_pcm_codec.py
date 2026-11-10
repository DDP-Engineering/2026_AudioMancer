#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_pcm_codec.py
@brief Internal PCM codec tests for AudioMancer.
@details Verifies the internal PCM conversions used by Audio Assembly. Golden
         cases pin the specified semantics on every interpreter; differential
         cases use audioop as a reference oracle where it is available.
         Covers S-WIDTH, S-CHANNELS, S-RATE, S-PARITY, S-SIGNED, S-REJECT,
         S-EMPTY, S-PIN and S-SKIP.
"""

# IMPORTS

from pathlib import Path
import random
import sys
import tomllib

import pytest

from audiomancer.services import audio_assembly_service, audio_assembly_wav, pcm_codec

# The optional reference implementation is available on Python 3.12. Everything
# guarded by `requires_audioop` runs there as an additional differential oracle.
# See REQ-TEST-29d60d25-64ce-49bb-ac6d-24764f80eb37.
try:  # pragma: no cover - import guard depends on interpreter version
    import audioop
except ImportError:  # pragma: no cover - Python 3.13 and newer
    audioop = None

requires_audioop = pytest.mark.skipif(
    audioop is None,
    reason="audioop reference implementation is unavailable on this interpreter",
)

_SAMPLE_WIDTHS = (1, 2, 3, 4)
_RATE_PAIRS = ((44100, 22050), (22050, 44100), (44100, 48000), (48000, 44100), (8000, 8000))


def _sample_limits(sample_width: int) -> tuple[int, int]:
    """
    @brief      Return the signed sample range for one sample width.
    @param[in]  sample_width Sample width in bytes.
    @return     Tuple of minimum and maximum signed sample values.
    @exception  None
    """
    maximum = (1 << (sample_width * 8 - 1)) - 1
    return -maximum - 1, maximum


def _build_pcm(sample_width: int, channels: int, frames: int, seed: int = 20260725) -> bytes:
    """
    @brief      Build deterministic pseudo-random PCM data including the extremes.
    @param[in]  sample_width Sample width in bytes.
    @param[in]  channels Channel count.
    @param[in]  frames Frame count to generate.
    @param[in]  seed Deterministic random seed.
    @return     Little-endian signed PCM bytes.
    @exception  None
    """
    minimum, maximum = _sample_limits(sample_width)
    generator = random.Random(seed)
    values = [minimum, maximum, 0, -1, 1, minimum + 1, maximum - 1]
    while len(values) < frames * channels:
        values.append(generator.randint(minimum, maximum))
    values = values[: frames * channels]
    return b"".join(value.to_bytes(sample_width, "little", signed=True) for value in values)


# GOLDEN CASES - measured from audioop on Python 3.12 and asserted on every interpreter.


@pytest.mark.parametrize(
    ("source_width", "target_width", "source_hex", "expected_hex"),
    [
        (1, 2, "0180", "00010080"),
        (2, 1, "ff010080", "0180"),
        (2, 3, "ff01", "00ff01"),
        (2, 4, "ff01", "0000ff01"),
        (4, 2, "0000ff01", "ff01"),
    ],
)
def test_pcm_codec_sample_width_conversion_matches_measured_audioop_bytes(
    source_width: int,
    target_width: int,
    source_hex: str,
    expected_hex: str,
) -> None:
    """
    @brief      Verify sample-width conversion reproduces measured audioop output.
    @param[in]  source_width Source sample width in bytes.
    @param[in]  target_width Target sample width in bytes.
    @param[in]  source_hex Source PCM bytes as hex.
    @param[in]  expected_hex Expected PCM bytes as hex.
    @return     None.
    @exception  None
    @details    Covers S-WIDTH and REQ-FUNC-6228f441-c9fa-4018-ad8d-7a2fefd67f44.
                Conversion is a pure arithmetic shift, so widening never rounds.
    """
    converted = pcm_codec.convert_sample_width(bytes.fromhex(source_hex), source_width, target_width)
    assert converted.hex() == expected_hex


def test_pcm_codec_sample_width_conversion_reads_single_byte_samples_as_signed() -> None:
    """
    @brief      Verify width-1 samples are read signed, matching audioop not WAV.
    @return     None.
    @exception  None
    @details    Covers S-SIGNED and REQ-FUNC-6228f441-c9fa-4018-ad8d-7a2fefd67f44.
                WAV stores 8-bit PCM unsigned, but audioop reads it signed, so
                0x80 must widen to -32768 rather than to +128.
    """
    converted = pcm_codec.convert_sample_width(b"\x80", 1, 2)
    assert int.from_bytes(converted, "little", signed=True) == -32768


def test_pcm_codec_stereo_to_mono_floors_instead_of_rounding() -> None:
    """
    @brief      Verify stereo-to-mono mixing floors the averaged sample.
    @return     None.
    @exception  None
    @details    Covers S-CHANNELS and REQ-FUNC-2a5a861a-8f08-46e0-834f-4ba125864d7d.
                Mixing 100 and 101 at 0.5/0.5 yields 100.5, which audioop floors
                to 100 rather than rounding to 101.
    """
    frame = (100).to_bytes(2, "little", signed=True) + (101).to_bytes(2, "little", signed=True)
    mixed = pcm_codec.stereo_to_mono(frame, 2)
    assert int.from_bytes(mixed, "little", signed=True) == 100


def test_pcm_codec_stereo_to_mono_clips_to_the_sample_width_maximum() -> None:
    """
    @brief      Verify channel mixing clips instead of wrapping on overflow.
    @return     None.
    @exception  None
    @details    Covers S-CHANNELS and REQ-FUNC-2a5a861a-8f08-46e0-834f-4ba125864d7d.
                Mixing 100 and 100 at unity factors yields 200, which must clip
                to 127 for a one-byte sample rather than wrap to a negative value.
    """
    mixed = pcm_codec.stereo_to_mono(b"\x64\x64", 1, 1.0, 1.0)
    assert mixed == b"\x7f"


def test_pcm_codec_mono_to_stereo_duplicates_each_sample() -> None:
    """
    @brief      Verify mono-to-stereo duplicates every sample at unity factors.
    @return     None.
    @exception  None
    @details    Covers S-CHANNELS and REQ-FUNC-2a5a861a-8f08-46e0-834f-4ba125864d7d.
    """
    assert pcm_codec.mono_to_stereo(b"\x01\xfe", 1).hex() == "0101fefe"


def test_pcm_codec_rate_conversion_reduces_the_rate_pair_by_greatest_common_divisor() -> None:
    """
    @brief      Verify the initial resampler state reflects the reduced rate pair.
    @return     None.
    @exception  None
    @details    Covers S-RATE and REQ-FUNC-999d448a-6629-45b2-a2c3-a2dfecaa2ee9.
                44100/22050 reduces to 2/1, so the fractional counter starts at
                -1 rather than at -22050.
    """
    converted, state = pcm_codec.convert_frame_rate(b"", 2, 1, 44100, 22050, None)
    assert converted == b""
    assert state == (-1, ((0, 0),))


def test_pcm_codec_rate_conversion_state_holds_samples_scaled_to_32_bit() -> None:
    """
    @brief      Verify carry-over state stores 32-bit scaled samples.
    @return     None.
    @exception  None
    @details    Covers S-RATE and REQ-FUNC-999d448a-6629-45b2-a2c3-a2dfecaa2ee9.
                Two-byte samples are held shifted left by 16, so trailing samples
                2000 and 3000 appear as 131072000 and 196608000.
    """
    frame_data = b"".join((value * 1000).to_bytes(2, "little", signed=True) for value in range(-4, 4))
    _, state = pcm_codec.convert_frame_rate(frame_data, 2, 1, 44100, 22050, None)
    assert state == (-1, ((131072000, 196608000),))


# STREAMING - provable without the reference implementation.


@pytest.mark.parametrize(("source_rate", "target_rate"), _RATE_PAIRS)
def test_pcm_codec_chunked_rate_conversion_matches_single_call(source_rate: int, target_rate: int) -> None:
    """
    @brief      Verify chunked resampling equals converting the stream at once.
    @param[in]  source_rate Source sample rate.
    @param[in]  target_rate Target sample rate.
    @return     None.
    @exception  None
    @details    Covers S-RATE and REQ-FUNC-999d448a-6629-45b2-a2c3-a2dfecaa2ee9.
                Final assembly streams WAV data in chunks, so a discontinuity at
                a chunk boundary would be an audible defect.
    """
    frame_data = _build_pcm(2, 1, 600)
    whole, _ = pcm_codec.convert_frame_rate(frame_data, 2, 1, source_rate, target_rate, None)
    chunk_size = 2 * 97
    streamed = b""
    state = None
    for offset in range(0, len(frame_data), chunk_size):
        converted, state = pcm_codec.convert_frame_rate(
            frame_data[offset : offset + chunk_size],
            2,
            1,
            source_rate,
            target_rate,
            state,
        )
        streamed += converted
    assert streamed == whole


# REJECTION AND BOUNDARY CASES.


@pytest.mark.parametrize("bad_width", [0, 5, -1, 8])
def test_pcm_codec_rejects_unsupported_sample_width(bad_width: int) -> None:
    """
    @brief      Verify an unsupported sample width raises ValueError.
    @param[in]  bad_width Unsupported sample width in bytes.
    @return     None.
    @exception  None
    @details    Covers S-REJECT and REQ-FUNC-2242c524-3b57-4460-afde-f6c97180c48a.
    """
    with pytest.raises(ValueError):
        pcm_codec.convert_sample_width(b"\x00\x00\x00\x00", bad_width, 2)
    with pytest.raises(ValueError):
        pcm_codec.convert_sample_width(b"\x00\x00\x00\x00", 2, bad_width)


def test_pcm_codec_rejects_non_positive_channel_and_rate_values() -> None:
    """
    @brief      Verify non-positive channel counts and rates raise ValueError.
    @return     None.
    @exception  None
    @details    Covers S-REJECT and REQ-FUNC-2242c524-3b57-4460-afde-f6c97180c48a.
    """
    with pytest.raises(ValueError):
        pcm_codec.convert_frame_rate(b"", 2, 0, 44100, 22050, None)
    with pytest.raises(ValueError):
        pcm_codec.convert_frame_rate(b"", 2, 1, 0, 22050, None)
    with pytest.raises(ValueError):
        pcm_codec.convert_frame_rate(b"", 2, 1, 44100, 0, None)


@pytest.mark.parametrize("sample_width", _SAMPLE_WIDTHS)
def test_pcm_codec_returns_empty_output_for_empty_input(sample_width: int) -> None:
    """
    @brief      Verify every conversion tolerates an empty chunk.
    @param[in]  sample_width Sample width in bytes.
    @return     None.
    @exception  None
    @details    Covers S-EMPTY and REQ-FUNC-be94fb5d-88d2-40dc-9c8a-65bd2aab79b8.
    """
    assert pcm_codec.convert_sample_width(b"", sample_width, 2) == b""
    assert pcm_codec.mono_to_stereo(b"", sample_width) == b""
    assert pcm_codec.stereo_to_mono(b"", sample_width) == b""
    converted, state = pcm_codec.convert_frame_rate(b"", sample_width, 2, 44100, 22050, None)
    assert converted == b""
    assert state is not None


def test_audio_assembly_rejects_unsupported_channel_conversion() -> None:
    """
    @brief      Verify Audio Assembly still refuses non mono/stereo conversions.
    @return     None.
    @exception  None
    @details    Covers S-REJECT and REQ-FUNC-7b43e8a3-c9aa-4e22-8b57-171bfb723fee.
                This pre-existing contract must survive the move off audioop.
    """
    with pytest.raises(RuntimeError, match="only between mono and stereo"):
        audio_assembly_wav._convert_wav_channels(b"\x00\x00" * 6, 2, 3, 2)


# DIFFERENTIAL PARITY - optional oracle comparisons.


@requires_audioop
@pytest.mark.parametrize("source_width", _SAMPLE_WIDTHS)
@pytest.mark.parametrize("target_width", _SAMPLE_WIDTHS)
def test_pcm_codec_sample_width_conversion_is_byte_identical_to_audioop(source_width: int, target_width: int) -> None:
    """
    @brief      Verify sample-width conversion matches audioop.lin2lin exactly.
    @param[in]  source_width Source sample width in bytes.
    @param[in]  target_width Target sample width in bytes.
    @return     None.
    @exception  None
    @details    Covers S-PARITY and REQ-FUNC-6228f441-c9fa-4018-ad8d-7a2fefd67f44
                for every ordered width pair drawn from {1,2,3,4}.
    """
    frame_data = _build_pcm(source_width, 1, 256)
    expected = audioop.lin2lin(frame_data, source_width, target_width)
    assert pcm_codec.convert_sample_width(frame_data, source_width, target_width) == expected


@requires_audioop
@pytest.mark.parametrize("sample_width", _SAMPLE_WIDTHS)
def test_pcm_codec_channel_conversion_is_byte_identical_to_audioop(sample_width: int) -> None:
    """
    @brief      Verify channel conversion matches audioop.tostereo and tomono.
    @param[in]  sample_width Sample width in bytes.
    @return     None.
    @exception  None
    @details    Covers S-PARITY and REQ-FUNC-2a5a861a-8f08-46e0-834f-4ba125864d7d
                at the exact factors Audio Assembly uses.
    """
    mono_data = _build_pcm(sample_width, 1, 256)
    stereo_data = _build_pcm(sample_width, 2, 256, seed=99)
    assert pcm_codec.mono_to_stereo(mono_data, sample_width) == audioop.tostereo(mono_data, sample_width, 1.0, 1.0)
    assert pcm_codec.stereo_to_mono(stereo_data, sample_width) == audioop.tomono(stereo_data, sample_width, 0.5, 0.5)


@requires_audioop
@pytest.mark.parametrize("sample_width", _SAMPLE_WIDTHS)
@pytest.mark.parametrize("channels", [1, 2])
@pytest.mark.parametrize(("source_rate", "target_rate"), _RATE_PAIRS)
def test_pcm_codec_rate_conversion_is_byte_identical_to_audioop(
    sample_width: int,
    channels: int,
    source_rate: int,
    target_rate: int,
) -> None:
    """
    @brief      Verify rate conversion matches audioop.ratecv bytes and state.
    @param[in]  sample_width Sample width in bytes.
    @param[in]  channels Channel count.
    @param[in]  source_rate Source sample rate.
    @param[in]  target_rate Target sample rate.
    @return     None.
    @exception  None
    @details    Covers S-PARITY and REQ-FUNC-999d448a-6629-45b2-a2c3-a2dfecaa2ee9.
                The returned state is compared too, because a divergent state
                would corrupt only later chunks of a long audiobook.
    """
    frame_data = _build_pcm(sample_width, channels, 300)
    expected_bytes, expected_state = audioop.ratecv(
        frame_data, sample_width, channels, source_rate, target_rate, None
    )
    actual_bytes, actual_state = pcm_codec.convert_frame_rate(
        frame_data, sample_width, channels, source_rate, target_rate, None
    )
    assert actual_bytes == expected_bytes
    assert actual_state == expected_state


@requires_audioop
def test_pcm_codec_chunked_rate_conversion_is_byte_identical_to_audioop() -> None:
    """
    @brief      Verify chunked resampling matches audioop chunk for chunk.
    @return     None.
    @exception  None
    @details    Covers S-PARITY and REQ-FUNC-999d448a-6629-45b2-a2c3-a2dfecaa2ee9.
                State is threaded through both implementations so divergence in
                the carry-over samples is caught, not just in the first chunk.
    """
    frame_data = _build_pcm(2, 2, 900)
    chunk_size = 4 * 61
    codec_state = None
    reference_state = None
    for offset in range(0, len(frame_data), chunk_size):
        chunk = frame_data[offset : offset + chunk_size]
        expected, reference_state = audioop.ratecv(chunk, 2, 2, 44100, 48000, reference_state)
        actual, codec_state = pcm_codec.convert_frame_rate(chunk, 2, 2, 44100, 48000, codec_state)
        assert actual == expected
        assert codec_state == reference_state


# PLATFORM CONTRACTS.


def test_audiomancer_sources_use_internal_pcm_codec() -> None:
    """
    @brief      Verify source modules use the internal PCM codec.
    @return     None.
    @exception  None
    @details    Covers REQ-PLAT-483bf463-b356-480b-ac4a-a2be60d5a9e5 and keeps
                Audio Assembly importable throughout the supported interpreter range.
    """
    source_root = Path(audio_assembly_service.__file__).resolve().parents[1]
    offenders = [
        path.name
        for path in source_root.rglob("*.py")
        if any(
            line.startswith(("import audioop", "from audioop"))
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert offenders == []


def test_audiomancer_declares_python_3_13_as_supported() -> None:
    """
    @brief      Verify the declared interpreter range admits Python 3.13.
    @return     None.
    @exception  None
    @details    Covers REQ-PLAT-50f144d0-0798-4aa8-8a70-cdc14fa3cf28. The upper
                bound stays exclusive so Python 3.14 remains a deliberate
                decision rather than an accidental one.
    """
    project_file = Path(audio_assembly_service.__file__).resolve().parents[3] / "pyproject.toml"
    metadata = tomllib.loads(project_file.read_text(encoding="utf-8"))
    assert metadata["project"]["requires-python"] == ">=3.12,<3.14"


def test_pcm_codec_parity_suite_skips_when_reference_is_unavailable() -> None:
    """
    @brief      Verify the parity guard reflects reference availability.
    @return     None.
    @exception  None
    @details    Covers S-SKIP and REQ-TEST-29d60d25-64ce-49bb-ac6d-24764f80eb37.
                On Python 3.13 audioop is gone, so the oracle comparison must
                skip rather than fail and redden the suite.
    """
    reference_expected = sys.version_info < (3, 13)
    assert (audioop is not None) is reference_expected


# END OF FILE
