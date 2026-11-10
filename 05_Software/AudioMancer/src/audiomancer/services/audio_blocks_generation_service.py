#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file       audio_blocks_generation_service.py
@brief      Render one Audio Block with VoiceWeaver.
@details    Writes validated candidate audio and reusable split parts. Project
            publication, approvals and checkpoint storage belong to the caller.
"""

# IMPORTS

from collections.abc import Callable
from pathlib import Path

from audiomancer.services import audio_blocks_artifact_service, voiceweaver_runtime_service
from audiomancer.services.operation_runtime_service import raise_if_cancelled
from audiomancer.services.persistence_service import write_bytes_atomic

# PUBLIC API


def render_spoken_wav(
    output_path: Path,
    parts: list[str],
    saved_parts: list[Path],
    part_path: Callable[[int], Path],
    submit_part: Callable[[str], object],
    base_url: str,
    timeout_seconds: int,
    cancel_requested=None,
    part_saved=None,
) -> str:
    """
    @brief      Synthesize missing parts and render a complete candidate WAV.
    @param[in]  output_path Staged destination for the complete WAV.
    @param[in]  parts Planned spoken text parts.
    @param[in]  saved_parts Validated existing prefix files in order.
    @param[in]  part_path Path resolver for additional part files.
    @param[in]  submit_part VoiceWeaver request callable for one spoken part.
    @param[in]  base_url VoiceWeaver runtime address.
    @param[in]  timeout_seconds Maximum runtime request wait.
    @param[in]  cancel_requested Optional cancellation callback.
    @param[in]  part_saved Optional callback after durable part storage.
    @return     Most recent provider result summary.
    """
    part_files = list(saved_parts)
    summary = ""
    for index in range(len(part_files), len(parts)):
        raise_if_cancelled(cancel_requested)
        submit_part(parts[index])
        destination = output_path if len(parts) == 1 else part_path(index)
        summary = download_wav(destination, base_url, timeout_seconds, cancel_requested)
        if len(parts) > 1:
            part_files.append(destination)
            if part_saved is not None:
                part_saved(index + 1, summary)
    if len(parts) > 1:
        audio_blocks_artifact_service.stitch_wav_parts(part_files, output_path)
    return summary


def download_wav(output_path: Path, base_url: str, timeout_seconds: int, cancel_requested=None) -> str:
    """
    @brief      Wait for the submitted runtime operation and save its validated WAV.
    @param[in]  output_path Candidate WAV or completed split-part path.
    @param[in]  base_url VoiceWeaver runtime address.
    @param[in]  timeout_seconds Maximum runtime request wait.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Provider result summary.
    @exception  RuntimeError Raised when there is no valid downloadable WAV.
    """
    status = voiceweaver_runtime_service.wait_for_terminal_operation(
        base_url, timeout_seconds=timeout_seconds, cancel_requested=cancel_requested,
    )
    operation = status.get("operation", {})
    if not isinstance(operation, dict) or str(operation.get("status", "")).strip().lower() != "completed":
        raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(status))
    result = status.get("result", {})
    if not isinstance(result, dict) or not bool(result.get("available", False)):
        raise RuntimeError("VoiceWeaver finished the request but did not report downloadable audio.")
    audio_bytes = voiceweaver_runtime_service.download_generated_audio(base_url, timeout_seconds=timeout_seconds)
    audio_blocks_artifact_service.validate_wav_bytes(audio_bytes)
    write_bytes_atomic(output_path, audio_bytes)
    return str(result.get("summary", "")).strip()


# END OF FILE
