#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details.
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------

"""
@file test_hard_break_contract.py
@brief Repository contracts for canonical post-hard-break naming and assets.
@details Prevents product-generation labels and retired compatibility assets
         from returning after the hard break.
@author Eng. Dan Dumitru Pasare
@date 2026-07-30
@version 1.0.0
"""

# =============================================================================
# IMPORTS
# =============================================================================

from __future__ import annotations

from pathlib import Path
import re

# =============================================================================
# CONSTANTS
# =============================================================================

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_THIS_FILE = Path(__file__).resolve()
_ACTIVE_ROOTS = (
    _REPOSITORY_ROOT / "04_Software" / "AudioMancer" / "src" / "audiomancer",
    _REPOSITORY_ROOT / "04_Software" / "AudioMancer" / "tests",
    _REPOSITORY_ROOT / ".agentic" / "knowledge" / "components",
    _REPOSITORY_ROOT / ".agentic" / "requirements",
    _REPOSITORY_ROOT / ".agentic" / "specs",
)
_ACTIVE_FILES = (
    _REPOSITORY_ROOT / "HowToTest.md",
    _REPOSITORY_ROOT / "0_Planning" / "Overview.md",
    _REPOSITORY_ROOT / "0_Planning" / "PrompForCodeReview.txt",
)
_TEXT_SUFFIXES = {".json", ".md", ".py", ".toml", ".txt"}
_PRODUCT_GENERATION_PATTERNS = (
    re.compile(r"\bCleanup V" + "2\\b"),
    re.compile(r"\bText Extraction V" + "2\\b"),
    re.compile(r"cleanup_" + "v2"),
    re.compile(r"cleanup_chunking_" + "v2"),
    re.compile(r"\bAudioMancer V" + "2 branch\\b"),
    re.compile(r"\bV" + "1 remains on master\\b"),
)


def _active_text_files() -> list[Path]:
    """
    @brief Return active text artifacts governed by the hard-break contract.
    @return Canonical active text paths inspected for generation labels.
    @exception None
    @version 1.0.0
    """
    files = list(_ACTIVE_FILES)
    for root in _ACTIVE_ROOTS:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix in _TEXT_SUFFIXES and path != _THIS_FILE
        )
    return files


# =============================================================================
# TESTS
# =============================================================================

def test_active_artifacts_use_unversioned_product_generation_names() -> None:
    """
    @brief Verify S-0001 / REQ-NFR-339263e3-d501-4d2a-adb6-28c10e60c34a.
    @return None.
    @exception AssertionError Raised when an active artifact uses a retired label.
    @version 1.0.0
    """
    violations: list[str] = []
    for path in _active_text_files():
        text = path.read_text(encoding="utf-8")
        for pattern in _PRODUCT_GENERATION_PATTERNS:
            if pattern.search(text):
                violations.append(f"{path.relative_to(_REPOSITORY_ROOT)}: {pattern.pattern}")

    assert violations == []


def test_canonical_cleanup_assets_replace_generation_named_assets() -> None:
    """
    @brief Verify S-0002/S-0004 and the hard-break asset requirements.
    @return None.
    @exception AssertionError Raised when canonical assets are missing or retired assets remain.
    @version 1.0.0
    """
    tests_root = _REPOSITORY_ROOT / "04_Software" / "AudioMancer" / "tests"
    obsolete_paths = (
        tests_root / ("cleanup_" + "v2_test_support.py"),
        tests_root / "fixtures" / ("cleanup_" + "v2_corpus.json"),
        tests_root / ("test_cleanup_" + "v2_service.py"),
        tests_root / ("test_cleanup_" + "v2_quality_contract.py"),
        tests_root / ("test_cleanup_" + "v2_chunking_contract.py"),
        tests_root / ("test_cleanup_" + "v2_adjudication_contract.py"),
        tests_root / ("test_cleanup_" + "v2_acceptance_corpus.py"),
        _REPOSITORY_ROOT / ".agentic" / "specs" / ("cleanup_chunking_" + "v2.spec.md"),
    )
    canonical_paths = (
        tests_root / "cleanup_test_support.py",
        tests_root / "fixtures" / "cleanup_corpus.json",
        tests_root / "test_cleanup_service.py",
        tests_root / "test_cleanup_quality_contract.py",
        tests_root / "test_cleanup_chunking_contract.py",
        tests_root / "test_cleanup_adjudication_contract.py",
        tests_root / "test_cleanup_acceptance_corpus.py",
        _REPOSITORY_ROOT / ".agentic" / "specs" / "cleanup_chunking.spec.md",
    )
    audio_blocks_service = (
        _REPOSITORY_ROOT
        / "04_Software"
        / "AudioMancer"
        / "src"
        / "audiomancer"
        / "services"
        / "audio_blocks_service.py"
    )

    assert not any(path.exists() for path in obsolete_paths)
    assert all(path.is_file() for path in canonical_paths)
    assert "_LEGACY_ARTIFACT_FILE_NAMES" not in audio_blocks_service.read_text(encoding="utf-8")


# =============================================================================
# END OF FILE
# =============================================================================
