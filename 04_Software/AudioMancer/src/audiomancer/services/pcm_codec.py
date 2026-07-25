#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file pcm_codec.py
@brief Linear PCM conversion helpers for AudioMancer.
@details Replaces the `audioop` standard-library module removed in Python 3.13
         with stdlib-only equivalents of the four conversions Audio Assembly and
         Scene Mix rely on: sample-width conversion, mono/stereo conversion and
         stateful rate conversion.

         Every function reproduces its `audioop` counterpart bit for bit, so
         moving off the removed module does not alter produced audio. Two
         `audioop` quirks are therefore reproduced deliberately rather than
         corrected here: samples are read as signed at every width including one
         byte, where WAV itself stores 8-bit PCM unsigned, and sample-width
         conversion is an arithmetic shift rather than a rounded rescale.
@author Eng. Dan Dumitru Pasare
@date 2026-07-25
@version 0.1.0
"""

# IMPORTS

from math import floor, gcd

# CONSTANTS

SUPPORTED_SAMPLE_WIDTHS = (1, 2, 3, 4)

_SCALE_SHIFT_BY_SAMPLE_WIDTH = {
    1: 24,
    2: 16,
    3: 8,
    4: 0,
}


def convert_sample_width(frame_data: bytes, sample_width: int, target_sample_width: int) -> bytes:
    """
    @brief      Convert linear PCM data between sample widths.
    @param[in]  frame_data Source PCM bytes.
    @param[in]  sample_width Source sample width in bytes.
    @param[in]  target_sample_width Target sample width in bytes.
    @return     PCM bytes at the target sample width.
    @exception  ValueError Raised when either sample width is unsupported.
    @details    Mirrors `audioop.lin2lin`. The conversion is a pure arithmetic
                shift between the widths, so widening never rounds and narrowing
                truncates toward negative infinity.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _require_sample_width(sample_width)
    _require_sample_width(target_sample_width)
    if not frame_data:
        return b""
    if sample_width == target_sample_width:
        return bytes(frame_data)
    shift = _SCALE_SHIFT_BY_SAMPLE_WIDTH[sample_width] - _SCALE_SHIFT_BY_SAMPLE_WIDTH[target_sample_width]
    converted = bytearray()
    for sample in _iter_samples(frame_data, sample_width):
        converted += _pack_sample(sample << shift if shift >= 0 else sample >> -shift, target_sample_width)
    return bytes(converted)


def mono_to_stereo(
    frame_data: bytes,
    sample_width: int,
    left_factor: float = 1.0,
    right_factor: float = 1.0,
) -> bytes:
    """
    @brief      Convert mono linear PCM data to stereo.
    @param[in]  frame_data Source mono PCM bytes.
    @param[in]  sample_width Sample width in bytes.
    @param[in]  left_factor Gain applied to the generated left channel.
    @param[in]  right_factor Gain applied to the generated right channel.
    @return     Stereo PCM bytes.
    @exception  ValueError Raised when the sample width is unsupported.
    @details    Mirrors `audioop.tostereo`, including its clip-then-floor rule.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _require_sample_width(sample_width)
    if not frame_data:
        return b""
    minimum, maximum = _sample_limits(sample_width)
    converted = bytearray()
    for sample in _iter_samples(frame_data, sample_width):
        converted += _pack_sample(_bound(sample * left_factor, minimum, maximum), sample_width)
        converted += _pack_sample(_bound(sample * right_factor, minimum, maximum), sample_width)
    return bytes(converted)


def stereo_to_mono(
    frame_data: bytes,
    sample_width: int,
    left_factor: float = 0.5,
    right_factor: float = 0.5,
) -> bytes:
    """
    @brief      Convert stereo linear PCM data to mono.
    @param[in]  frame_data Source stereo PCM bytes.
    @param[in]  sample_width Sample width in bytes.
    @param[in]  left_factor Gain applied to the left channel before mixing.
    @param[in]  right_factor Gain applied to the right channel before mixing.
    @return     Mono PCM bytes.
    @exception  ValueError Raised when the sample width is unsupported.
    @details    Mirrors `audioop.tomono`. Mixing happens in floating point and
                the result is clipped then floored, so an exact half such as
                100.5 becomes 100 rather than 101.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _require_sample_width(sample_width)
    if not frame_data:
        return b""
    minimum, maximum = _sample_limits(sample_width)
    frame_size = sample_width * 2
    converted = bytearray()
    for offset in range(0, len(frame_data) - frame_size + 1, frame_size):
        left = _unpack_sample(frame_data, offset, sample_width)
        right = _unpack_sample(frame_data, offset + sample_width, sample_width)
        mixed = left * left_factor + right * right_factor
        converted += _pack_sample(_bound(mixed, minimum, maximum), sample_width)
    return bytes(converted)


def convert_frame_rate(
    frame_data: bytes,
    sample_width: int,
    channels: int,
    source_rate: int,
    target_rate: int,
    state: object | None,
) -> tuple[bytes, object]:
    """
    @brief      Resample linear PCM data between sample rates.
    @param[in]  frame_data Source PCM bytes for this chunk.
    @param[in]  sample_width Sample width in bytes.
    @param[in]  channels Channel count.
    @param[in]  source_rate Source sample rate in hertz.
    @param[in]  target_rate Target sample rate in hertz.
    @param[in]  state Carry-over state from the previous chunk, or None to start.
    @return     Tuple of converted PCM bytes and the updated carry-over state.
    @exception  ValueError Raised on an unsupported sample width, a non-positive
                channel count, or a non-positive sample rate.
    @details    Mirrors `audioop.ratecv` with weightA=1 and weightB=0, including
                reduction of the rate pair by its greatest common divisor and the
                32-bit scaled samples held in the returned state. The caller
                threads the state through successive chunks so resampling stays
                continuous across chunk boundaries.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _require_sample_width(sample_width)
    if channels <= 0:
        raise ValueError(f"Channel count must be positive, received {channels}.")
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError(f"Sample rates must be positive, received {source_rate} and {target_rate}.")

    divisor = gcd(source_rate, target_rate)
    source_rate //= divisor
    target_rate //= divisor

    if state is None:
        position = -target_rate
        previous_samples = [0] * channels
        current_samples = [0] * channels
    else:
        position, channel_states = state
        previous_samples = [int(entry[0]) for entry in channel_states]
        current_samples = [int(entry[1]) for entry in channel_states]

    scale_shift = _SCALE_SHIFT_BY_SAMPLE_WIDTH[sample_width]
    frame_size = sample_width * channels
    frame_count = len(frame_data) // frame_size
    converted = bytearray()
    frame_index = 0

    while True:
        while position < 0:
            if frame_index >= frame_count:
                channel_states = tuple(
                    (previous_samples[channel], current_samples[channel]) for channel in range(channels)
                )
                return bytes(converted), (position, channel_states)
            offset = frame_index * frame_size
            for channel in range(channels):
                previous_samples[channel] = current_samples[channel]
                current_samples[channel] = _unpack_sample(
                    frame_data, offset + channel * sample_width, sample_width
                ) << scale_shift
            frame_index += 1
            position += target_rate
        while position >= 0:
            for channel in range(channels):
                mixed = (
                    previous_samples[channel] * position
                    + current_samples[channel] * (target_rate - position)
                )
                converted += _pack_sample(_truncating_divide(mixed, target_rate) >> scale_shift, sample_width)
            position -= source_rate


def _require_sample_width(sample_width: int) -> None:
    """
    @brief      Reject a sample width the codec cannot represent.
    @param[in]  sample_width Sample width in bytes.
    @return     None.
    @exception  ValueError Raised when the sample width is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    if sample_width not in _SCALE_SHIFT_BY_SAMPLE_WIDTH:
        raise ValueError(
            f"Unsupported PCM sample width {sample_width}; supported widths are {SUPPORTED_SAMPLE_WIDTHS}."
        )


def _sample_limits(sample_width: int) -> tuple[int, int]:
    """
    @brief      Return the signed value range for one sample width.
    @param[in]  sample_width Sample width in bytes.
    @return     Tuple of minimum and maximum signed sample values.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    maximum = (1 << (sample_width * 8 - 1)) - 1
    return -maximum - 1, maximum


def _iter_samples(frame_data: bytes, sample_width: int):
    """
    @brief      Iterate signed samples in little-endian PCM data.
    @param[in]  frame_data Source PCM bytes.
    @param[in]  sample_width Sample width in bytes.
    @return     Generator of signed integer samples.
    @exception  None
    @details    Trailing bytes that do not form a whole sample are ignored, which
                is how `audioop` treats a truncated fragment.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    for offset in range(0, len(frame_data) - sample_width + 1, sample_width):
        yield _unpack_sample(frame_data, offset, sample_width)


def _unpack_sample(frame_data: bytes, offset: int, sample_width: int) -> int:
    """
    @brief      Read one signed little-endian sample.
    @param[in]  frame_data Source PCM bytes.
    @param[in]  offset Byte offset of the sample.
    @param[in]  sample_width Sample width in bytes.
    @return     Signed integer sample value.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    return int.from_bytes(frame_data[offset : offset + sample_width], "little", signed=True)


def _pack_sample(value: int, sample_width: int) -> bytes:
    """
    @brief      Write one signed little-endian sample, truncating overflow.
    @param[in]  value Sample value to store.
    @param[in]  sample_width Sample width in bytes.
    @return     Little-endian signed sample bytes.
    @exception  None
    @details    Values outside the width are truncated to the low bytes rather
                than clipped, matching how `audioop` stores a scaled sample.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    bit_count = sample_width * 8
    truncated = int(value) & ((1 << bit_count) - 1)
    if truncated >= 1 << (bit_count - 1):
        truncated -= 1 << bit_count
    return truncated.to_bytes(sample_width, "little", signed=True)


def _bound(value: float, minimum: int, maximum: int) -> int:
    """
    @brief      Clip a mixed sample into range and round toward negative infinity.
    @param[in]  value Mixed sample value.
    @param[in]  minimum Minimum representable sample value.
    @param[in]  maximum Maximum representable sample value.
    @return     Clipped integer sample value.
    @exception  None
    @details    Reproduces `audioop`'s own bounding rule verbatim, including its
                `value < minimum + 1` comparison, which is deliberately not
                simplified to `value < minimum`.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    if value > maximum:
        value = maximum
    elif value < minimum + 1.0:
        value = minimum
    return int(floor(value))


def _truncating_divide(dividend: int, divisor: int) -> int:
    """
    @brief      Divide two integers rounding toward zero.
    @param[in]  dividend Value to divide.
    @param[in]  divisor Value to divide by.
    @return     Quotient truncated toward zero.
    @exception  None
    @details    C integer division truncates toward zero while Python's floor
                division rounds toward negative infinity. The resampler depends
                on the C behaviour, so negative samples would otherwise drift.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    quotient = abs(dividend) // abs(divisor)
    return -quotient if (dividend < 0) != (divisor < 0) else quotient


# END OF FILE
