#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file audio_blocks_artifact_service.py
@brief Audio Blocks artifact path, naming, and WAV helpers.
@details Keeps deterministic generated-audio names and WAV validation helpers
         separate from Audio Blocks orchestration and persistence workflows.
"""

# IMPORTS

import io
from pathlib import Path
import re
import unicodedata
import wave

from audiomancer import config

# PUBLIC API


def generated_audio_root(project_root: Path) -> Path:
    """
    @brief      Resolve the generated-audio artifact root for Audio Blocks.
    @param[in]  project_root Active project root folder.
    @return     Absolute generated-audio folder path.
    @exception  None
    """
    return Path(project_root) / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME


def audio_artifact_path(project_root: Path, speech_block_id: str) -> Path:
    """
    @brief      Resolve one generated WAV path from the owning Speech Block identifier.
    @details    The name depends only on `speech_block_id`, which is the block's
                stable primary key, so it stays valid for the block's whole life
                and never needs to be stored or repaired.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Stable Speech Block identifier.
    @return     Absolute generated WAV path.
    @exception  None
    """
    return generated_audio_root(project_root) / f"{audio_artifact_file_stem(speech_block_id)}.wav"


def audio_part_artifact_path(project_root: Path, speech_block_id: str, part_index: int) -> Path:
    """
    @brief      Resolve one deterministic split-part WAV artifact path.
    @param[in]  project_root Active project root folder.
    @param[in]  speech_block_id Stable Speech Block identifier.
    @param[in]  part_index Zero-based split-part index.
    @return     Absolute split-part WAV path.
    @exception  None
    """
    file_stem = f"{audio_artifact_file_stem(speech_block_id)}_part{max(int(part_index), 0) + 1:03d}"
    return generated_audio_root(project_root) / "parts" / f"{file_stem}.wav"


def audio_artifact_file_stem(speech_block_id: str) -> str:
    """
    @brief      Build the Audio Blocks artifact file stem from the Speech Block identifier.
    @param[in]  speech_block_id Stable Speech Block identifier.
    @return     File stem equal to the sanitized `speech_block_id`.
    @exception  None
    """
    sanitized_id = re.sub(r"[^A-Za-z0-9_-]+", "", str(speech_block_id or "").strip())
    return sanitized_id or "block"


def normalize_speaker_name(value: str) -> str:
    """
    @brief      Build one filesystem-stable normalized speaker name token.
    @param[in]  value Raw speaker display name.
    @return     ASCII-safe normalized speaker token.
    @exception  None
    """
    normalized_value = str(value or "").replace("\u00c3\u02c6\u00cb\u0153", "\u0218").replace("\u00c8\u02dc", "\u0218")
    normalized_value = unicodedata.normalize("NFKD", normalized_value)
    ascii_value = normalized_value.encode("ascii", "ignore").decode("ascii")
    cleaned_value = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value).strip("_").lower()
    return cleaned_value or "speaker"


def validate_wav_bytes(audio_bytes: bytes) -> None:
    """
    @brief      Validate downloaded Audio Blocks WAV bytes before persistence.
    @param[in]  audio_bytes Candidate WAV payload.
    @return     None.
    @exception  RuntimeError Raised when the payload is not a readable non-empty WAV.
    """
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as audio_file:
            if audio_file.getnchannels() <= 0 or audio_file.getsampwidth() <= 0:
                raise RuntimeError
            if audio_file.getframerate() <= 0 or audio_file.getnframes() <= 0:
                raise RuntimeError
    except (EOFError, OSError, RuntimeError, wave.Error) as exc:
        raise RuntimeError("VoiceWeaver returned invalid WAV audio for Audio Blocks generation.") from exc


def is_valid_wav_path(audio_path: Path) -> bool:
    """
    @brief      Return whether one existing split-part file is a readable non-empty WAV.
    @param[in]  audio_path Candidate WAV path.
    @return     True when the path can be reused as a split checkpoint.
    @exception  None
    """
    try:
        with wave.open(str(audio_path), "rb") as audio_file:
            return (
                audio_file.getnchannels() > 0
                and audio_file.getsampwidth() > 0
                and audio_file.getframerate() > 0
                and audio_file.getnframes() > 0
            )
    except (EOFError, OSError, wave.Error):
        return False


def wav_duration_seconds(audio_path: Path) -> float | None:
    """
    @brief      Measure one readable WAV file duration in seconds.
    @param[in]  audio_path Candidate WAV path.
    @return     Duration in seconds, or `None` when the file cannot be measured.
    @exception  None
    """
    try:
        with wave.open(str(audio_path), "rb") as audio_file:
            frame_rate = audio_file.getframerate()
            if frame_rate <= 0:
                return None
            return audio_file.getnframes() / frame_rate
    except (EOFError, OSError, wave.Error):
        return None


def stitch_wav_parts(part_paths: list[Path], output_path: Path) -> None:
    """
    @brief      Concatenate compatible WAV part files into one final WAV.
    @param[in]  part_paths Ordered WAV part paths.
    @param[in]  output_path Final stitched WAV path.
    @return     None.
    @exception  RuntimeError Raised when part files have incompatible WAV parameters.
    """
    if not part_paths:
        raise RuntimeError("Cannot stitch split Audio Block because no generated part WAV files exist.")
    expected_params = None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as output_wav:
        for part_path in part_paths:
            with wave.open(str(part_path), "rb") as part_wav:
                part_params = part_wav.getparams()
                comparable_params = part_params[:3], part_params[4:]
                if expected_params is None:
                    expected_params = comparable_params
                    output_wav.setparams(part_params)
                elif comparable_params != expected_params:
                    raise RuntimeError("VoiceWeaver returned split WAV parts with incompatible audio parameters.")
                output_wav.writeframes(part_wav.readframes(part_wav.getnframes()))


# END OF FILE
