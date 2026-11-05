#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_chunking_contract.py
@brief Red-first checks for consuming completed typed Cleanup metadata.
@details Verifies hash/status gating, role propagation, scene-separator
         filtering, and resumable deterministic materialization.
"""

# IMPORTS

from __future__ import annotations

import json

import pytest

from audiomancer import config
from audiomancer.cleanup import text as cleanup_text_analysis_service
from audiomancer.services import (
    deterministic_chunking_service,
)
from chunking_test_support import write_chunking_document
from cleanup_test_support import build_ledger, build_project, write_completed_cleanup


def test_chunking_rejects_noncompleted_cleanup_even_when_text_exists(tmp_path) -> None:
    """@brief Cover S-0008/S-0011 and REQ-FUNC-bd7cd503-2d84-4adb-94bc-d8f31d297368."""
    canonical_text, ledger = build_ledger(["Paragraph one.", "Paragraph two."])
    project_root, manifest = build_project(tmp_path, "PausedCleanup", canonical_text, ledger)
    document = write_completed_cleanup(
        project_root,
        canonical_text,
        ledger,
        "Paragraph one.\n\nParagraph two.\n",
        [("Paragraph one.", "body"), ("Paragraph two.", "body")],
    )
    document["status"] = "paused"
    document["phase"] = "adjudication"
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="completed Cleanup"):
        deterministic_chunking_service.chunk_text(project_root, manifest)

    assert not (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists()


def test_chunking_rejects_clean_text_hash_mismatch(tmp_path) -> None:
    """@brief Cover S-0008 and REQ-FUNC-bd7cd503-2d84-4adb-94bc-d8f31d297368."""
    canonical_text, ledger = build_ledger(["Paragraph one."])
    project_root, manifest = build_project(tmp_path, "HashMismatch", canonical_text, ledger)
    write_completed_cleanup(
        project_root,
        canonical_text,
        ledger,
        "Paragraph one.\n",
        [("Paragraph one.", "body")],
    )
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Changed text.\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match cleanup.json"):
        deterministic_chunking_service.chunk_text(project_root, manifest)


def test_chunking_slices_cleanup_paragraph_offsets_and_propagates_roles(tmp_path) -> None:
    """@brief Cover S-0011/S-0014/S-0016 and the Cleanup-Chunking requirements."""
    cleaned_text = (
        "CHAPTER ONE\n\n"
        "The opening paragraph ends here.\n\n"
        "* * *\n\n"
        "The moon is low\nThe river holds its light\nA quiet road\n"
    )
    paragraphs = [
        ("CHAPTER ONE", "heading"),
        ("The opening paragraph ends here.", "body"),
        ("* * *", "scene_separator"),
        ("The moon is low\nThe river holds its light\nA quiet road", "verse"),
    ]
    canonical_text, ledger = build_ledger(
        [item[0] for item in paragraphs],
        kinds=[item[1] for item in paragraphs],
        boundaries=[("\n\n", "native_paragraph")] * 3,
        origins=["native"] * 4,
        structure_quality="native",
    )
    project_root, manifest = build_project(tmp_path, "TypedChunking", canonical_text, ledger)
    write_completed_cleanup(project_root, canonical_text, ledger, cleaned_text, paragraphs)

    deterministic_chunking_service.chunk_text(project_root, manifest)

    payload = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert [item["cleanup_role"] for item in payload["chunks"]] == [
        "heading",
        "body",
        "verse",
    ]
    assert [item["starts_after_scene_separator"] for item in payload["chunks"]] == [
        False,
        False,
        True,
    ]
    assert payload["chunks"][-1]["text"] == paragraphs[-1][0]
    assert "\n".join(item["text"] for item in payload["chunks"]).replace("\n\n", "\n") == (
        "\n".join(item[0] for item in (paragraphs[0], paragraphs[1], paragraphs[3]))
    )


@pytest.mark.parametrize(
    "separator_text",
    [
        "***",
        "* * *",
        "---",
        "– – –",
        "— — —",
        "___",
        "~~~",
        "###",
        "===",
        "• • •",
        "◆ ◆ ◆",
        "◇◇◇",
        "⁂",
        "❦",
        "❧",
        "☙",
        "※",
        "⁕",
        "✦",
        "✧",
    ],
)
def test_scene_separator_artifact_recognition_is_conservative(separator_text) -> None:
    """@brief Cover S-0014 and REQ-FUNC-24dd4710-058c-481e-a207-a8252fff8e65."""
    assert cleanup_text_analysis_service.is_scene_separator_artifact(separator_text)


@pytest.mark.parametrize(
    "narratable_text",
    ["...", "…", "—", "### Title", "x x x", "o0o", "*** text", "*"],
)
def test_ambiguous_punctuation_is_not_a_scene_separator_artifact(narratable_text) -> None:
    """@brief Cover S-0014 and REQ-FUNC-24dd4710-058c-481e-a207-a8252fff8e65."""
    assert not cleanup_text_analysis_service.is_scene_separator_artifact(narratable_text)


def test_chunking_omits_scene_separator_artifacts_and_preserves_conservative_punctuation(
    tmp_path,
) -> None:
    """@brief Cover S-0014 and REQ-FUNC-24dd4710-058c-481e-a207-a8252fff8e65."""
    paragraphs = [
        ("Opening narration.", "body"),
        ("* * *", "body"),
        ("Second scene.", "body"),
        ("⁂", "body"),
        ("...", "body"),
        ("### Title", "body"),
        ("x x x", "body"),
        ("—", "body"),
        ("Editorial separator label", "scene_separator"),
        ("Closing narration.", "body"),
    ]
    cleaned_text = "\n\n".join(item[0] for item in paragraphs) + "\n"
    canonical_text, ledger = build_ledger(
        [item[0] for item in paragraphs],
        boundaries=[("\n\n", "native_paragraph")] * (len(paragraphs) - 1),
    )
    project_root, manifest = build_project(tmp_path, "SeparatorFiltering", canonical_text, ledger)
    write_completed_cleanup(project_root, canonical_text, ledger, cleaned_text, paragraphs)

    deterministic_chunking_service.chunk_text(project_root, manifest)

    payload = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert [item["sequence_index"] for item in payload["chunks"]] == list(
        range(1, len(payload["chunks"]) + 1)
    )
    assert [item["text"] for item in payload["chunks"]] == [
        "Opening narration.",
        "Second scene.",
        "...",
        "### Title",
        "x x x",
        "—",
        "Closing narration.",
    ]
    assert [item["starts_after_scene_separator"] for item in payload["chunks"]] == [
        False,
        True,
        True,
        False,
        False,
        False,
        True,
    ]


def test_chunking_rejects_separator_only_cleanup(tmp_path) -> None:
    """@brief Cover S-0014 and REQ-FUNC-24dd4710-058c-481e-a207-a8252fff8e65."""
    paragraphs = [("* * *", "body"), ("⁂", "scene_separator")]
    cleaned_text = "\n\n".join(item[0] for item in paragraphs) + "\n"
    canonical_text, ledger = build_ledger(
        [item[0] for item in paragraphs],
        boundaries=[("\n\n", "native_paragraph")],
    )
    project_root, manifest = build_project(tmp_path, "OnlySeparators", canonical_text, ledger)
    write_completed_cleanup(project_root, canonical_text, ledger, cleaned_text, paragraphs)

    with pytest.raises(ValueError, match="narratable paragraphs"):
        deterministic_chunking_service.chunk_text(project_root, manifest)

    assert not (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists()


def test_chunking_resume_counts_processed_separator_without_persisting_it(
    tmp_path,
) -> None:
    """@brief Cover S-0014 and REQ-FUNC-24dd4710-058c-481e-a207-a8252fff8e65."""
    paragraphs = [
        ("Opening narration.", "body"),
        ("* * *", "body"),
        ("Closing narration.", "body"),
    ]
    cleaned_text = "\n\n".join(item[0] for item in paragraphs) + "\n"
    canonical_text, ledger = build_ledger(
        [item[0] for item in paragraphs],
        boundaries=[("\n\n", "native_paragraph")] * 2,
    )
    project_root, manifest = build_project(tmp_path, "SeparatorResume", canonical_text, ledger)
    write_completed_cleanup(project_root, canonical_text, ledger, cleaned_text, paragraphs)
    write_chunking_document(
        project_root,
        [{"text": "Opening narration.", "cleanup_role": "body"}],
        mode="deterministic",
        source_text=cleaned_text,
        status="cancelled",
        next_paragraph=3,
    )

    deterministic_chunking_service.chunk_text(project_root, manifest)

    payload = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert [item["text"] for item in payload["chunks"]] == [
        "Opening narration.",
        "Closing narration.",
    ]
    assert [item["sequence_index"] for item in payload["chunks"]] == [1, 2]
    assert [item["starts_after_scene_separator"] for item in payload["chunks"]] == [False, True]


# END OF FILE
