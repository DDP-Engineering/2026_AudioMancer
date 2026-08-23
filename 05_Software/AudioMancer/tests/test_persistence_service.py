#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_persistence_service.py
@brief Focused tests for atomic file persistence helpers.
@details Verifies JSON files are replaced atomically and that replacement
         failures preserve the last complete payload.
"""

# IMPORTS

import json
from pathlib import Path

import pytest

from audiomancer.services import persistence_service

# PUBLIC API


def test_write_json_atomic_replaces_file_with_valid_json(tmp_path) -> None:
    """
    @brief      Verify atomic JSON persistence replaces the target with valid JSON.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    target_path = tmp_path / "settings.json"
    target_path.write_text('{"version": 1}\n', encoding="utf-8")

    persistence_service.write_json_atomic(target_path, {"version": 2, "items": ["ready"]})

    assert json.loads(target_path.read_text(encoding="utf-8")) == {"version": 2, "items": ["ready"]}


def test_write_json_atomic_failed_replace_leaves_previous_json_intact(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a replacement failure preserves the previously complete JSON file.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    target_path = tmp_path / "project.json"
    original_payload = {"project_id": "before", "status": "complete"}
    target_path.write_text(json.dumps(original_payload, indent=2) + "\n", encoding="utf-8")

    def _raise_replace_error(source_path: Path, destination_path: Path) -> None:
        """
        @brief      Simulate a platform-level replace failure.
        @param[in]  source_path Temporary source path passed to replacement.
        @param[in]  destination_path Final destination path passed to replacement.
        @return     None.
        @exception  OSError Always raised to simulate failed replacement.
        """
        _ = source_path
        _ = destination_path
        raise OSError("replace failed")

    monkeypatch.setattr(persistence_service.os, "replace", _raise_replace_error)

    with pytest.raises(OSError, match="replace failed"):
        persistence_service.write_json_atomic(target_path, {"project_id": "after", "status": "partial"})

    assert json.loads(target_path.read_text(encoding="utf-8")) == original_payload
    assert list(tmp_path.glob(".project.json.*.tmp")) == []


def test_write_bytes_atomic_creates_parent_and_replaces_complete_payload(tmp_path) -> None:
    """
    @brief      Verify atomic byte persistence creates parents and replaces complete payloads.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    target_path = tmp_path / "generated" / "voice.wav"

    persistence_service.write_bytes_atomic(target_path, b"RIFF-first")
    assert target_path.read_bytes() == b"RIFF-first"

    persistence_service.write_bytes_atomic(target_path, b"RIFF-second")

    assert target_path.read_bytes() == b"RIFF-second"
    assert list(target_path.parent.glob(".voice.wav.*.tmp")) == []


def test_write_bytes_atomic_failed_replace_preserves_target_and_cleans_temporary_file(
    tmp_path,
    monkeypatch,
) -> None:
    """
    @brief      Verify atomic byte replacement propagates failure without torn or orphan files.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    target_path = tmp_path / "voice.wav"
    target_path.write_bytes(b"RIFF-before")
    expected_error = PermissionError("replace failed")

    def _raise_replace_error(source_path: Path, destination_path: Path) -> None:
        """
        @brief      Simulate a platform-level byte replacement failure.
        @param[in]  source_path Temporary source path passed to replacement.
        @param[in]  destination_path Final destination path passed to replacement.
        @return     None.
        @exception  PermissionError Always raised to simulate failed replacement.
        """
        _ = source_path
        _ = destination_path
        raise expected_error

    monkeypatch.setattr(persistence_service.os, "replace", _raise_replace_error)

    with pytest.raises(PermissionError, match="replace failed") as error_info:
        persistence_service.write_bytes_atomic(target_path, b"RIFF-after")

    assert error_info.value is expected_error
    assert target_path.read_bytes() == b"RIFF-before"
    assert list(tmp_path.glob(".voice.wav.*.tmp")) == []


# END OF FILE
