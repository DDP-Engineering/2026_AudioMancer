#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file voice_sample_import_service.py
@brief Shared voice-sample import validation helpers for AudioMancer.
@details Validates operator-provided WAV reference samples before they are
         copied into narrator or character voice sample storage.
@author Eng. Dan Dumitru Pasare
@date 2026-05-15
@version 0.1.0
"""

# IMPORTS

from pathlib import Path
import wave

from audiomancer import config

# CONSTANTS

IMPORTED_SAMPLE_SOURCE = "imported_sample"
IMPORTED_SAMPLE_GENERATION_MODE = "imported_sample"

_SILENCE_RMS_RATIO = 0.003
_SILENCE_PEAK_RATIO = 0.01


def validate_imported_wav_sample(sample_path: str | Path) -> dict[str, object]:
    """
    @brief      Validate one imported WAV sample and return audio metadata.
    @param[in]  sample_path Candidate WAV file path.
    @return     Normalized validation report.
    @exception  ValueError Raised when the file is missing, unsupported, too short, or silent.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    path = Path(sample_path)
    if path.suffix.casefold() != ".wav":
        raise ValueError("unsupported_file_type")
    if not path.is_file():
        raise ValueError("missing_file")
    try:
        with wave.open(str(path), "rb") as wav_file:
            channel_count = int(wav_file.getnchannels())
            sample_width_bytes = int(wav_file.getsampwidth())
            sample_rate = int(wav_file.getframerate())
            frame_count = int(wav_file.getnframes())
            audio_bytes = wav_file.readframes(frame_count)
    except (EOFError, OSError, wave.Error) as exc:
        raise ValueError("invalid_wav") from exc
    if channel_count <= 0 or sample_width_bytes <= 0 or sample_rate <= 0 or frame_count <= 0:
        raise ValueError("invalid_wav")
    duration_seconds = frame_count / sample_rate
    min_duration_seconds = float(config.DEFAULT_IMPORTED_VOICE_SAMPLE_MIN_SECONDS)
    if duration_seconds < min_duration_seconds:
        raise ValueError("sample_too_short")
    audio_metrics = _audio_level_metrics(audio_bytes, sample_width_bytes)
    if _is_effectively_silent(audio_metrics):
        raise ValueError("sample_silent")
    return {
        "duration_seconds": duration_seconds,
        "frame_count": frame_count,
        "sample_rate": sample_rate,
        "channel_count": channel_count,
        "sample_width_bytes": sample_width_bytes,
        "peak_amplitude": audio_metrics["peak_amplitude"],
        "rms_amplitude": audio_metrics["rms_amplitude"],
        "silence_peak_threshold": audio_metrics["silence_peak_threshold"],
        "silence_rms_threshold": audio_metrics["silence_rms_threshold"],
    }


def _audio_level_metrics(audio_bytes: bytes, sample_width_bytes: int) -> dict[str, float]:
    """
    @brief      Measure simple peak and RMS audio levels for PCM WAV data.
    @param[in]  audio_bytes Raw interleaved PCM sample bytes.
    @param[in]  sample_width_bytes WAV sample width in bytes.
    @return     Audio level metrics and silence thresholds.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    max_amplitude = float(_maximum_amplitude(sample_width_bytes))
    if max_amplitude <= 0.0:
        return {
            "peak_amplitude": 0.0,
            "rms_amplitude": 0.0,
            "silence_peak_threshold": 0.0,
            "silence_rms_threshold": 0.0,
        }
    peak_amplitude = 0
    square_sum = 0
    sample_count = 0
    step = sample_width_bytes
    usable_length = len(audio_bytes) - (len(audio_bytes) % step)
    for offset in range(0, usable_length, step):
        sample_value = _pcm_sample_value(audio_bytes[offset : offset + step], sample_width_bytes)
        absolute_value = abs(sample_value)
        peak_amplitude = max(peak_amplitude, absolute_value)
        square_sum += absolute_value * absolute_value
        sample_count += 1
    rms_amplitude = (square_sum / sample_count) ** 0.5 if sample_count else 0.0
    return {
        "peak_amplitude": float(peak_amplitude),
        "rms_amplitude": float(rms_amplitude),
        "silence_peak_threshold": max_amplitude * _SILENCE_PEAK_RATIO,
        "silence_rms_threshold": max_amplitude * _SILENCE_RMS_RATIO,
    }


def _is_effectively_silent(audio_metrics: dict[str, float]) -> bool:
    """
    @brief      Return whether measured audio levels are below the import floor.
    @param[in]  audio_metrics Level metrics from `_audio_level_metrics`.
    @return     True when the sample is silent or too close to silence.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    return float(audio_metrics.get("peak_amplitude", 0.0)) <= float(
        audio_metrics.get("silence_peak_threshold", 0.0)
    ) or float(audio_metrics.get("rms_amplitude", 0.0)) <= float(audio_metrics.get("silence_rms_threshold", 0.0))


def _maximum_amplitude(sample_width_bytes: int) -> int:
    """
    @brief      Resolve the maximum absolute PCM sample value for a sample width.
    @param[in]  sample_width_bytes WAV sample width in bytes.
    @return     Maximum signed PCM amplitude.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    if sample_width_bytes == 1:
        return 128
    return (1 << ((sample_width_bytes * 8) - 1)) - 1


def _pcm_sample_value(sample_bytes: bytes, sample_width_bytes: int) -> int:
    """
    @brief      Decode one PCM sample value from little-endian WAV bytes.
    @param[in]  sample_bytes One sample of PCM data.
    @param[in]  sample_width_bytes WAV sample width in bytes.
    @return     Signed sample value.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    if sample_width_bytes == 1:
        return int(sample_bytes[0]) - 128
    return int.from_bytes(sample_bytes, byteorder="little", signed=True)


# END OF FILE
