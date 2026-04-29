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
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.1.0
"""

# IMPORTS

import io
from pathlib import Path
import re
import unicodedata
import wave

from audiomancer import config
from audiomancer.services import speech_blocks_service

# PUBLIC API


def generated_audio_root(project_root: Path) -> Path:
    """
    @brief      Resolve the generated-audio artifact root for Audio Blocks.
    @param[in]  project_root Active project root folder.
    @return     Absolute generated-audio folder path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return Path(project_root) / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME


def audio_artifact_paths(
    project_root: Path,
    chunk_id: str,
    sequence_index: int,
    normalized_speaker_name: str,
) -> tuple[Path, Path]:
    """
    @brief      Resolve one stable WAV and JSON metadata path pair for a speech block.
    @param[in]  project_root Active project root folder.
    @param[in]  chunk_id Stable source chunk identifier.
    @param[in]  sequence_index Stable chunk-local speech-block sequence index.
    @param[in]  normalized_speaker_name Stable normalized speaker-name token.
    @return     Tuple of WAV path and metadata JSON path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    file_stem = audio_artifact_file_stem(chunk_id, sequence_index, normalized_speaker_name)
    audio_root = generated_audio_root(project_root)
    return audio_root / f"{file_stem}.wav", audio_root / f"{file_stem}.json"


def audio_part_artifact_path(project_root: Path, audio_block: dict[str, object], part_index: int) -> Path:
    """
    @brief      Resolve one deterministic split-part WAV artifact path.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_block Current Audio Blocks entry.
    @param[in]  part_index Zero-based split-part index.
    @return     Absolute split-part WAV path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    file_stem = audio_artifact_file_stem(
        str(audio_block.get("chunk_id", "")).strip(),
        int(audio_block.get("sequence_index", 0)),
        str(audio_block.get("normalized_speaker_name", "")),
    )
    file_stem = f"{file_stem}_part{part_index + 1:03d}"
    return generated_audio_root(project_root) / "parts" / f"{file_stem}.wav"


def audio_artifact_file_stem(chunk_id: str, sequence_index: int, normalized_speaker_name: str) -> str:
    """
    @brief      Build the compact Audio Blocks artifact file stem.
    @param[in]  chunk_id Stable source chunk identifier.
    @param[in]  sequence_index Stable chunk-local speech-block sequence index.
    @param[in]  normalized_speaker_name Stable normalized speaker-name token.
    @return     File stem in `<chunk_no_4digits>_<block_no_6digits>_<character_normalized_name>` format.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    chunk_sort_key = speech_blocks_service.speech_block_book_sort_key({"chunk_id": chunk_id, "sequence_index": 0})
    safe_chunk = f"{chunk_sort_key[0]:04d}"
    safe_sequence = f"{max(int(sequence_index), 0):06d}"
    safe_name = str(normalized_speaker_name or "").strip() or "speaker"
    return f"{safe_chunk}_{safe_sequence}_{safe_name}"


def normalize_speaker_name(value: str) -> str:
    """
    @brief      Build one filesystem-stable normalized speaker name token.
    @param[in]  value Raw speaker display name.
    @return     ASCII-safe normalized speaker token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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


def stitch_wav_parts(part_paths: list[Path], output_path: Path) -> None:
    """
    @brief      Concatenate compatible WAV part files into one final WAV.
    @param[in]  part_paths Ordered WAV part paths.
    @param[in]  output_path Final stitched WAV path.
    @return     None.
    @exception  RuntimeError Raised when part files have incompatible WAV parameters.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
