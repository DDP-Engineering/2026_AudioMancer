#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file       audio_assembly_wav.py
@brief      Render and publish Audio Assembly PCM WAV files.
@details    Mixes, copies and converts bounded frame chunks through the shared PCM codec.
"""

# IMPORTS

from collections.abc import Callable
from contextlib import ExitStack, suppress
from functools import partial
from pathlib import Path
from tempfile import NamedTemporaryFile
import wave

from audiomancer.services import pcm_codec
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import emit_progress_update, raise_if_cancelled
from audiomancer.services.persistence_service import validate_publication_path

# CONSTANTS

SUPPORTED_SAMPLE_WIDTHS = frozenset({2, 3, 4})
_WAV_COPY_FRAME_CHUNK_SIZE = 65_536
_LOGGER = get_component_logger("audio_assembly")
_emit_progress = partial(emit_progress_update, include_token_usage=False)

# PUBLIC API


@trace_function(_LOGGER)
def publish_wav(
    project_root: Path,
    output_path: Path,
    render: Callable[[Path], None],
    cancel_requested=None,
) -> None:
    """
    @brief      Publish a rendered sibling WAV, preserving the previous file if rendering fails.
    @param[in]  project_root Resolved active project root.
    @param[in]  output_path Canonical project-local output path.
    @param[in]  render Writer that closes the candidate before returning.
    @param[in]  cancel_requested Optional cancellation callback.
    @exception  OSError Raised when writing or replacing the candidate fails.
    """
    validate_publication_path(project_root, output_path, "Audio Assembly WAV")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raise_if_cancelled(cancel_requested)
    with NamedTemporaryFile(dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".tmp", delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        render(temp_path)
        raise_if_cancelled(cancel_requested)
        temp_path.replace(output_path)
    finally:
        with suppress(OSError):
            temp_path.unlink(missing_ok=True)


def mix_wav_sources(
    source_paths: list[Path],
    output_path: Path,
    duration_seconds: float,
    progress_callback=None,
    progress_start: int = 0,
    progress_end: int = 1,
    progress_total: int = 1,
    progress_message: str = "Mixing Scene Mix preview.",
    cancel_requested=None,
) -> None:
    """
    @brief      Overlay compatible PCM WAV sources into one fixed-duration WAV.
    @param[in]  source_paths Source WAV files.
    @param[in]  output_path Destination WAV file path.
    @param[in]  duration_seconds Target mix duration in seconds.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_start Completed progress units before mixing starts.
    @param[in]  progress_end Completed progress units after mixing ends.
    @param[in]  progress_total Total progress units for the parent operation.
    @param[in]  progress_message Operator-facing progress message.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     None.
    @exception  RuntimeError Raised when source WAV files are incompatible.
    """
    if not source_paths:
        raise RuntimeError("Scene Ambience mix requires at least one source WAV.")
    with ExitStack() as stack:
        sources = [stack.enter_context(wave.open(str(path), "rb")) for path in source_paths]
        reference_params = sources[0].getparams()
        expected_params = reference_params[:3], reference_params[4:]
        if reference_params.sampwidth not in SUPPORTED_SAMPLE_WIDTHS:
            raise RuntimeError("Audio Assembly supports uncompressed PCM WAV source files only.")
        for source_wav in sources[1:]:
            params = source_wav.getparams()
            if params.sampwidth not in SUPPORTED_SAMPLE_WIDTHS:
                raise RuntimeError("Audio Assembly supports uncompressed PCM WAV source files only.")
            if (params[:3], params[4:]) != expected_params:
                raise RuntimeError("Audio Assembly found incompatible source WAV parameters.")
        target_frames = scene_mix_target_frames(sources, reference_params.framerate, duration_seconds)
        last_progress_unit = -1
        with wave.open(str(output_path), "wb") as output_wav:
            output_wav.setparams(reference_params)
            remaining_frames = target_frames
            while remaining_frames > 0:
                raise_if_cancelled(cancel_requested)
                written_frames = target_frames - remaining_frames
                progress_unit = progress_start
                if target_frames > 0 and progress_end > progress_start:
                    progress_unit = progress_start + int(
                        ((progress_end - progress_start) * written_frames) / target_frames
                    )
                if progress_unit != last_progress_unit:
                    _emit_progress(progress_callback, progress_unit, progress_total, progress_message)
                    last_progress_unit = progress_unit
                frame_count = min(remaining_frames, _WAV_COPY_FRAME_CHUNK_SIZE)
                chunks = [_read_or_pad_wav_frames(source_wav, frame_count, reference_params) for source_wav in sources]
                output_wav.writeframes(_mix_pcm_chunks(chunks, frame_count, reference_params))
                remaining_frames -= frame_count
        _emit_progress(progress_callback, progress_end, progress_total, progress_message)


def scene_mix_target_frames(sources: list[wave.Wave_read], frame_rate: int, duration_seconds: float) -> int:
    """
    @brief      Resolve the fixed frame count for one Scene Ambience mix.
    @param[in]  sources Open source WAV readers.
    @param[in]  frame_rate Mix frame rate.
    @param[in]  duration_seconds Requested target duration.
    @return     Target frame count.
    @exception  None
    """
    if frame_rate > 0 and duration_seconds > 0.0:
        return max(1, int(round(frame_rate * duration_seconds)))
    return max((int(source.getnframes()) for source in sources), default=1)


def _read_or_pad_wav_frames(source_wav: wave.Wave_read, frame_count: int, params) -> bytes:
    """
    @brief      Read WAV frames and pad short sources with silence.
    @param[in]  source_wav Open source WAV reader.
    @param[in]  frame_count Requested frame count.
    @param[in]  params Reference WAV parameters.
    @return     Exactly `frame_count` frames of PCM bytes.
    @exception  None
    """
    frame_size = max(int(params.nchannels) * int(params.sampwidth), 1)
    frames_available = max(0, source_wav.getnframes() - source_wav.tell())
    data = _read_wav_frames(source_wav, min(frame_count, frames_available), frame_size)
    expected_size = frame_count * frame_size
    silence_byte = b"\x80" if int(params.sampwidth) == 1 else b"\x00"
    return data + (silence_byte * (expected_size - len(data)))


def _mix_pcm_chunks(chunks: list[bytes], frame_count: int, params) -> bytes:
    """
    @brief      Mix same-format PCM chunks with conservative gain reduction.
    @param[in]  chunks Source PCM chunks.
    @param[in]  frame_count Number of frames in each chunk.
    @param[in]  params Reference WAV parameters.
    @return     Mixed PCM byte chunk.
    @exception  None
    """
    channels = int(params.nchannels)
    sample_width = int(params.sampwidth)
    sample_count = frame_count * channels
    scale = 1.0 / max(len(chunks), 1)
    output = bytearray()
    for sample_index in range(sample_count):
        mixed_value = 0
        offset = sample_index * sample_width
        for chunk in chunks:
            mixed_value += _decode_pcm_sample(chunk[offset : offset + sample_width], sample_width)
        output.extend(_encode_pcm_sample(int(round(mixed_value * scale)), sample_width))
    return bytes(output)


def _decode_pcm_sample(sample_bytes: bytes, sample_width: int) -> int:
    """
    @brief      Decode one PCM sample to a signed integer.
    @param[in]  sample_bytes Raw PCM sample bytes.
    @param[in]  sample_width Sample width in bytes.
    @return     Signed sample value.
    @exception  None
    """
    if sample_width == 1:
        return int.from_bytes(sample_bytes or b"\x80", "little", signed=False) - 128
    return int.from_bytes(sample_bytes.ljust(sample_width, b"\x00"), "little", signed=True)


def _encode_pcm_sample(sample_value: int, sample_width: int) -> bytes:
    """
    @brief      Encode one signed integer as a clipped PCM sample.
    @param[in]  sample_value Signed sample value.
    @param[in]  sample_width Sample width in bytes.
    @return     Raw PCM sample bytes.
    @exception  None
    """
    if sample_width == 1:
        return int(max(0, min(sample_value + 128, 255))).to_bytes(1, "little", signed=False)
    minimum = -(1 << (8 * sample_width - 1))
    maximum = (1 << (8 * sample_width - 1)) - 1
    return int(max(minimum, min(sample_value, maximum))).to_bytes(sample_width, "little", signed=True)


def append_silence(output_wav: wave.Wave_write, gap_ms: int, params, cancel_requested=None) -> int:
    """
    @brief      Write PCM silence frames into one output WAV stream.
    @details    Zero bytes are silence only for signed PCM. That holds for every width
                in `SUPPORTED_SAMPLE_WIDTHS`, which excludes unsigned 8-bit for
                exactly this reason; do not re-admit one-byte PCM without also giving
                this function an unsigned zero level of 0x80.
    @param[in]  output_wav Active output WAV writer.
    @param[in]  gap_ms Gap length in milliseconds.
    @param[in]  params WAV params from the current source file.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Number of frames written.
    @exception  None
    """
    if gap_ms <= 0:
        return 0
    channels = int(params.nchannels)
    sample_width = int(params.sampwidth)
    frame_rate = int(params.framerate)
    frame_count = silence_frame_count(frame_rate, gap_ms)
    if frame_count <= 0:
        return 0
    frame_size = channels * sample_width
    chunk = bytes(min(frame_count, _WAV_COPY_FRAME_CHUNK_SIZE) * frame_size)
    remaining = frame_count
    while remaining:
        raise_if_cancelled(cancel_requested)
        frames = min(remaining, _WAV_COPY_FRAME_CHUNK_SIZE)
        output_wav.writeframes(chunk[: frames * frame_size])
        remaining -= frames
    return frame_count


def silence_frame_count(frame_rate: int, duration_ms: int) -> int:
    """
    @brief      Convert silence milliseconds to exact whole PCM frames.
    @param[in]  frame_rate Output sample rate.
    @param[in]  duration_ms Silence duration in milliseconds.
    @return     Whole silence frame count using floor semantics.
    @exception  None
    """
    if frame_rate <= 0 or duration_ms <= 0:
        return 0
    return frame_rate * duration_ms // 1000


def _copy_wav_frames(source_wav, output_wav: wave.Wave_write, cancel_requested=None) -> int:
    """
    @brief      Copy source WAV frames to the output in bounded chunks.
    @param[in]  source_wav Active source WAV reader.
    @param[in]  output_wav Active output WAV writer.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Number of frames copied.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    """
    frame_size = max(int(source_wav.getnchannels()) * int(source_wav.getsampwidth()), 1)
    remaining_frames = int(source_wav.getnframes())
    copied_frames = 0
    while remaining_frames > 0:
        raise_if_cancelled(cancel_requested)
        frames_to_read = min(remaining_frames, _WAV_COPY_FRAME_CHUNK_SIZE)
        frame_data = _read_wav_frames(source_wav, frames_to_read, frame_size)
        output_wav.writeframes(frame_data)
        copied_frames += frames_to_read
        remaining_frames -= frames_to_read
    return copied_frames


def copy_or_convert_wav_frames(
    source_wav,
    output_wav: wave.Wave_write,
    target_params,
    cancel_requested=None,
) -> int:
    """
    @brief      Copy or convert source WAV frames to the output WAV format.
    @param[in]  source_wav Active source WAV reader.
    @param[in]  output_wav Active output WAV writer.
    @param[in]  target_params Output WAV parameters.
    @param[in]  cancel_requested Optional cancellation callback.
    @return     Number of output frames written.
    @exception  RuntimeError Raised when source conversion is unsupported.
    """
    source_params = source_wav.getparams()
    if (source_params[:3], source_params[4:]) == (target_params[:3], target_params[4:]):
        return _copy_wav_frames(source_wav, output_wav, cancel_requested)
    if (
        source_params.sampwidth not in SUPPORTED_SAMPLE_WIDTHS
        or target_params.sampwidth not in SUPPORTED_SAMPLE_WIDTHS
    ):
        raise RuntimeError("Audio Assembly supports uncompressed PCM WAV source files only.")
    rate_state = None
    remaining_frames = int(source_wav.getnframes())
    output_frame_size = max(int(target_params.nchannels) * int(target_params.sampwidth), 1)
    source_frame_size = max(int(source_params.nchannels) * int(source_params.sampwidth), 1)
    written_frames = 0
    while remaining_frames > 0:
        raise_if_cancelled(cancel_requested)
        frames_to_read = min(remaining_frames, _WAV_COPY_FRAME_CHUNK_SIZE)
        frame_data = _read_wav_frames(source_wav, frames_to_read, source_frame_size)
        converted_data, rate_state = _convert_wav_frame_chunk(frame_data, source_params, target_params, rate_state)
        if converted_data:
            output_wav.writeframes(converted_data)
            written_frames += len(converted_data) // output_frame_size
        remaining_frames -= frames_to_read
    return written_frames


def _convert_wav_frame_chunk(frame_data: bytes, source_params, target_params, rate_state) -> tuple[bytes, object]:
    """
    @brief      Convert one PCM frame chunk between compatible WAV layouts.
    @param[in]  frame_data Source PCM bytes.
    @param[in]  source_params Source WAV parameters.
    @param[in]  target_params Target WAV parameters.
    @param[in]  rate_state Running resampler state from `pcm_codec.convert_frame_rate`.
    @return     Tuple of converted PCM bytes and updated rate-conversion state.
    @exception  RuntimeError Raised when channel conversion is unsupported.
    """
    converted_data = frame_data
    current_sample_width = int(source_params.sampwidth)
    current_channels = int(source_params.nchannels)
    target_sample_width = int(target_params.sampwidth)
    target_channels = int(target_params.nchannels)
    if current_sample_width != target_sample_width:
        converted_data = pcm_codec.convert_sample_width(converted_data, current_sample_width, target_sample_width)
        current_sample_width = target_sample_width
    converted_data = _convert_wav_channels(
        converted_data,
        current_sample_width,
        current_channels,
        target_channels,
    )
    current_channels = target_channels
    if int(source_params.framerate) != int(target_params.framerate):
        converted_data, rate_state = pcm_codec.convert_frame_rate(
            converted_data,
            current_sample_width,
            current_channels,
            int(source_params.framerate),
            int(target_params.framerate),
            rate_state,
        )
    return converted_data, rate_state


def can_convert_channels(source_channels: int, target_channels: int) -> bool:
    """
    @brief      Check whether the renderer can preserve or convert channel layout.
    @param[in]  source_channels Source channel count.
    @param[in]  target_channels Target channel count.
    @return     True when no conversion is needed or conversion is mono/stereo.
    """
    return source_channels == target_channels or {source_channels, target_channels} == {1, 2}


def _convert_wav_channels(frame_data: bytes, sample_width: int, source_channels: int, target_channels: int) -> bytes:
    """
    @brief      Convert PCM frame data between mono and stereo channel layouts.
    @param[in]  frame_data Source PCM bytes.
    @param[in]  sample_width Sample width in bytes.
    @param[in]  source_channels Source channel count.
    @param[in]  target_channels Target channel count.
    @return     PCM bytes with the target channel count.
    @exception  RuntimeError Raised when the channel conversion is unsupported.
    """
    if source_channels == target_channels:
        return frame_data
    if not can_convert_channels(source_channels, target_channels):
        raise RuntimeError("Audio Assembly supports WAV channel conversion only between mono and stereo.")
    if source_channels == 1:
        return pcm_codec.mono_to_stereo(frame_data, sample_width, 1.0, 1.0)
    return pcm_codec.stereo_to_mono(frame_data, sample_width, 0.5, 0.5)

def _read_wav_frames(source: wave.Wave_read, frame_count: int, frame_size: int) -> bytes:
    """
    @brief      Read exactly the requested declared frames or reject a shortened source.
    @param[in]  source Open PCM WAV reader.
    @param[in]  frame_count Requested frame count within the declared data.
    @param[in]  frame_size Bytes in one complete frame.
    @return     Complete PCM frames.
    @exception  EOFError Raised when the source ends before its declared length.
    """
    data = source.readframes(frame_count)
    if len(data) != frame_count * frame_size:
        raise EOFError("Audio Assembly source WAV ended before its declared frames.")
    return data


# END OF FILE
