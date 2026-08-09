#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file make_synthetic_project.py
@brief Build disposable large AudioMancer projects for block performance tests.
@details Creates project manifests and high-cardinality Speech Blocks and Audio
         Blocks artifacts without importing the desktop application package or
         using online services.
@author Eng. Dan Dumitru Pasare
@date 2026-06-10
@version 0.1.0
"""

# IMPORTS

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
import wave

# CONSTANTS

PROJECT_MANIFEST_FILE_NAME = "project.json"
CHUNK_ARTIFACT_FILE_NAME = "chunks_text.json"
SPEECH_BLOCKS_OUTPUT_FILE_NAME = "speech_blocks.json"
SPEECH_BLOCKS_REPORT_FILE_NAME = "speech_blocks_report.json"
SPEECH_BLOCKS_STATE_FILE_NAME = "speech_blocks_state.json"
AUDIO_BLOCKS_OUTPUT_FILE_NAME = "audio_blocks.json"
AUDIO_BLOCKS_REPORT_FILE_NAME = "audio_blocks_report.json"
AUDIO_BLOCKS_STATE_FILE_NAME = "audio_blocks_state.json"

DEFAULT_WORKFLOW_STAGE = "project_created"
DEFAULT_TRANSLATION_TARGET_LANGUAGE = "ro"
DEFAULT_TTS_VOICE_ASSIGNMENT_MODE = "same_narrator"
DEFAULT_AUDIO_ASSEMBLY_SETTINGS = {
    "output_mode": "whole_book",
    "max_duration_minutes": 30,
    "output_format": "wav",
    "inter_block_silence_ms": 250,
    "inter_chunk_silence_ms": 1000,
    "include_scene_ambience": True,
}
WORKFLOW_OPERATION_ORDER = (
    "extraction",
    "cleanup",
    "chunking",
    "translation",
    "character_discovery",
    "narrator_definition",
    "character_voices",
    "speech_blocks",
    "audio_blocks",
    "audio_assembly",
)

# PUBLIC API


def main() -> int:
    """
    @brief      Parse command-line options and create one synthetic project.
    @return     Process exit code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    parser = argparse.ArgumentParser(description="Create a disposable large AudioMancer project.")
    parser.add_argument("--blocks", type=int, default=3000, help="Total Speech Blocks to create.")
    parser.add_argument("--chunks", type=int, default=150, help="Source chunks to create.")
    parser.add_argument("--out", required=True, help="Output project folder.")
    args = parser.parse_args()
    project_root = build_synthetic_project(Path(args.out), blocks=args.blocks, chunks=args.chunks)
    print(project_root)
    return 0


def build_synthetic_project(out: Path, blocks: int = 3000, chunks: int = 150) -> Path:
    """
    @brief      Build one synthetic AudioMancer project folder.
    @param[in]  out Output project folder.
    @param[in]  blocks Total Speech Blocks to create.
    @param[in]  chunks Source chunks to create.
    @return     Created project root.
    @exception  ValueError Raised when counts are invalid.
    @exception  FileExistsError Raised when the output folder is not empty.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    if blocks <= 0 or chunks <= 0:
        raise ValueError("Synthetic project counts must be positive.")
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Output folder is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    now_iso = _utc_now_iso()
    manifest = _build_project_manifest(out.name, now_iso)
    manifest.update(
        {
            "current_stage": "audio_blocks_ready",
            "source_document": {
                "original_name": "synthetic_large_book.txt",
                "stored_relative_path": "synthetic_large_book.txt",
                "file_type": "txt",
                "imported_at": now_iso,
                "size_bytes": blocks * 32,
            },
            "project_options_locked": True,
            "target_language": "en",
            "original_language": "en",
            "selected_voice_language": "en",
            "voice_assignment_mode": "same_narrator",
        }
    )
    source_chunks = _build_chunks(blocks, chunks)
    speech_blocks = _build_speech_blocks(source_chunks, blocks)
    audio_blocks = _build_audio_blocks(out, speech_blocks, now_iso)
    source_text = "\n\n".join(str(chunk["text"]) for chunk in source_chunks)
    (out / "synthetic_large_book.txt").write_text(source_text, encoding="utf-8")
    _write_json(out / PROJECT_MANIFEST_FILE_NAME, manifest)
    _write_json(out / CHUNK_ARTIFACT_FILE_NAME, _chunking_document(source_chunks, source_text))
    _write_json(out / SPEECH_BLOCKS_OUTPUT_FILE_NAME, _speech_blocks_document(speech_blocks, source_chunks, now_iso))
    _write_json(out / AUDIO_BLOCKS_OUTPUT_FILE_NAME, audio_blocks)
    _write_json(out / AUDIO_BLOCKS_REPORT_FILE_NAME, _audio_blocks_report(audio_blocks, speech_blocks))
    _write_json(
        out / AUDIO_BLOCKS_STATE_FILE_NAME,
        _operation_state("completed", len(audio_blocks), len(speech_blocks)),
    )
    return out


# LOCAL HELPERS


def _utc_now_iso() -> str:
    """
    @brief      Build one current UTC timestamp in stable ISO-8601 format.
    @return     UTC timestamp string without microseconds.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _build_project_manifest(display_name: str, timestamp_iso: str) -> dict[str, object]:
    """
    @brief      Build the synthetic project manifest without importing the app package.
    @param[in]  display_name Operator-facing project name.
    @param[in]  timestamp_iso Shared creation timestamp.
    @return     Project manifest payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    return {
        "project_id": str(uuid4()),
        "display_name": display_name,
        "created_at": timestamp_iso,
        "updated_at": timestamp_iso,
        "current_stage": DEFAULT_WORKFLOW_STAGE,
        "source_document": None,
        "extraction_warning_count": 0,
        "operations": _build_default_operation_states(),
        "project_options_locked": False,
        "target_language": DEFAULT_TRANSLATION_TARGET_LANGUAGE,
        "original_language": None,
        "narrator_profile_name": None,
        "narrator_language": None,
        "selected_voice_language": None,
        "voice_assignment_mode": DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
        "audio_assembly_settings": dict(DEFAULT_AUDIO_ASSEMBLY_SETTINGS),
        "notes": "",
    }


def _build_default_operation_states() -> dict[str, dict[str, object]]:
    """
    @brief      Build the default operation-state mapping for one synthetic project.
    @return     Default project-local operation-state map.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    return {operation_kind: _operation_state("not_started", 0, 0) for operation_kind in WORKFLOW_OPERATION_ORDER}


def _write_json(path: Path, payload: object) -> None:
    """
    @brief      Write one JSON artifact for a synthetic project.
    @param[in]  path Destination JSON path.
    @param[in]  payload JSON-serializable payload.
    @return     None.
    @exception  TypeError Raised when the payload is not JSON-serializable.
    @exception  OSError Raised when the file cannot be written.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _build_chunks(blocks: int, chunks: int) -> list[dict[str, object]]:
    """
    @brief      Build deterministic source chunks for one synthetic project.
    @details    Chunk records carry the exact canonical chunk fields required by
                the strict `chunks_text.json` document contract.
    @param[in]  blocks Total Speech Blocks represented by the project.
    @param[in]  chunks Number of source chunks to create.
    @return     Ordered source chunk payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.2.0
    """
    _ = blocks
    return [
        {
            "chunk_id": f"chunk-{index:04d}",
            "sequence_index": index,
            "text": f"Synthetic source chunk {index} with enough text to produce review rows.",
            "cleanup_boundary_confidence": None,
            "cleanup_joined_across_page_break": False,
            "cleanup_warning_flags": [],
        }
        for index in range(1, chunks + 1)
    ]


def _build_speech_blocks(source_chunks: list[dict[str, object]], blocks: int) -> list[dict[str, object]]:
    """
    @brief      Build deterministic Speech Blocks for a synthetic project.
    @param[in]  source_chunks Source chunk payload list.
    @param[in]  blocks Total Speech Blocks to create.
    @return     Ordered Speech Blocks payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    speech_blocks: list[dict[str, object]] = []
    chunk_count = len(source_chunks)
    for index in range(blocks):
        chunk = source_chunks[index % chunk_count]
        chunk_id = str(chunk["chunk_id"])
        sequence_index = (index // chunk_count) + 1
        speech_blocks.append(
            {
                "speech_block_id": f"{int(chunk_id.split('-')[-1]):04d}-{sequence_index:06d}",
                "sequence_index": sequence_index,
                "chunk_id": chunk_id,
                "source_language": "en",
                "speaker_kind": "narrator",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": "narration",
                "source_text": f"Synthetic source text {index + 1}.",
                "text": f"Synthetic speech block {index + 1}.",
                "warning_flags": [],
                "approved": True,
                "approved_at": "2026-06-10T00:00:00Z",
            }
        )
    return speech_blocks


def _build_audio_blocks(
    project_root: Path,
    speech_blocks: list[dict[str, object]],
    generated_at: str,
) -> list[dict[str, object]]:
    """
    @brief      Build matching generated Audio Blocks and WAV stubs.
    @param[in]  project_root Synthetic project root folder.
    @param[in]  speech_blocks Speech Blocks payload list.
    @param[in]  generated_at Generation timestamp stored on each row.
    @return     Ordered Audio Blocks payload list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    audio_root = project_root / "generated_audio"
    audio_root.mkdir(parents=True, exist_ok=True)
    audio_blocks: list[dict[str, object]] = []
    for speech_block in speech_blocks:
        file_name = f"{speech_block['speech_block_id']}_narrator.wav"
        audio_path = audio_root / file_name
        _write_wav_stub(audio_path)
        audio_blocks.append(
            {
                "speech_block_id": speech_block["speech_block_id"],
                "chunk_id": speech_block["chunk_id"],
                "speaker_id": "narrator",
                "voice_target_id": "narrator",
                "audio_relative_path": f"generated_audio/{file_name}",
                "audio_can_play": True,
                "audio_duration_seconds": 0.01,
                "generated": generated_at,
                "approved": generated_at,
                "runtime_result_summary": "Synthetic WAV stub.",
                "split_part_count": 1,
                "split_strategy": "single",
                "generated_part_relative_paths": [],
                "generation_fingerprint": f"synthetic-{speech_block['speech_block_id']}",
                "split_plan_fingerprint": None,
            }
        )
    return audio_blocks


def _write_wav_stub(path: Path) -> None:
    """
    @brief      Write one tiny valid WAV file for generated-audio checks.
    @param[in]  path Destination WAV path.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\0\0")


def _chunking_document(source_chunks: list[dict[str, object]], source_text: str) -> dict[str, object]:
    """
    @brief      Build the single authoritative synthetic Chunking document.
    @details    Mirrors the exact root contract enforced by the application
                chunking document boundary: a completed deterministic document
                with no checkpoint and zeroed cumulative token usage. The report
                and operation-state views are derived at runtime and are never
                persisted, so no sidecar files are written.
    @param[in]  source_chunks Source chunk payload list.
    @param[in]  source_text Canonical source text represented by the chunks.
    @return     Chunking document payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    return {
        "status": "completed",
        "mode": "deterministic",
        "manual_adjusted": False,
        "source_fingerprint": f"sha256:{sha256(source_text.encode('utf-8')).hexdigest()}",
        "semantic_strategy": None,
        "additional_chunking_instructions": "",
        "token_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "usage_available": False,
        },
        "warnings": [],
        "next_paragraph": None,
        "context_window_fallback_count": 0,
        "chunks": source_chunks,
    }


def _speech_blocks_document(
    speech_blocks: list[dict[str, object]],
    source_chunks: list[dict[str, object]],
    now_iso: str,
) -> dict[str, object]:
    """
    @brief      Build the single authoritative synthetic Speech Blocks document.
    @param[in]  speech_blocks Speech Blocks payload list.
    @param[in]  source_chunks Source chunk payload list.
    @param[in]  now_iso Synthetic run timestamp.
    @return     Speech Blocks document payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.2.0
    """
    return {
        "status": "completed",
        "source": {"kind": "original", "language": "en", "fingerprint": "synthetic"},
        "ai_profile_id": "synthetic-profile",
        "instructions": "",
        "scene_ambience": {"enabled": False},
        "response_contract": "direct_blocks",
        "token_usage": {"input_tokens": None, "output_tokens": None, "total_tokens": None, "usage_available": False},
        "budget_metadata": {},
        "checkpoint": {
            "next_chunk_index": len(source_chunks),
            "run_token": now_iso,
            "log_relative_path": "speech_blocks_ai_transactions.jsonl",
            "source_snapshot_fingerprint": "synthetic",
            "source_language": "en",
            "ai_profile_id": "synthetic-profile",
            "additional_speech_block_instructions_fingerprint": "",
            "speech_blocks_response_contract": "direct_blocks",
        },
        "failure": None,
        "blocks": speech_blocks,
    }


def _audio_blocks_report(
    audio_blocks: list[dict[str, object]],
    speech_blocks: list[dict[str, object]],
) -> dict[str, object]:
    """
    @brief      Build a completed synthetic Audio Blocks report.
    @param[in]  audio_blocks Audio Blocks payload list.
    @param[in]  speech_blocks Speech Blocks payload list.
    @return     Audio Blocks report payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    return {
        "voice_language": "en",
        "audio_blocks_stage_status": "completed",
        "generated_block_count": len(audio_blocks),
        "approved_block_count": len(audio_blocks),
        "total_block_count": len(speech_blocks),
        "prompt_count": 0,
        "current_phase": "generate_blocks",
        "warning_count": 0,
        "warnings": [],
    }


def _operation_state(status: str, progress_current: int, progress_total: int) -> dict[str, object]:
    """
    @brief      Build a compact operation-state envelope for synthetic artifacts.
    @param[in]  status Persisted operation status.
    @param[in]  progress_current Current progress count.
    @param[in]  progress_total Total progress count.
    @return     Operation-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    return {
        "status": status,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "mode": None,
        "warning_count": 0,
        "metadata": {},
        "resume_checkpoint": None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
