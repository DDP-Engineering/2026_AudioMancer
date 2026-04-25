#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_project_snapshot_service.py
@brief Whole-project ZIP snapshot service tests for AudioMancer.
@details Verifies full project archive creation, path safety, UTF-8 handling,
         extension helpers, and failure cleanup behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.1.0
"""

# IMPORTS

from datetime import datetime
from pathlib import Path
import zipfile

import pytest

from audiomancer import config
from audiomancer.services import project_snapshot_service, project_workspace_service

# PUBLIC API


def test_project_snapshot_service_creates_zip_with_top_level_project_folder(tmp_path) -> None:
    """
    @brief      Verify a snapshot archive includes project files under one top-level folder.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _build_snapshot_project(tmp_path)
    snapshot_path = tmp_path / "exports" / "snapshot.zip"

    result = project_snapshot_service.create_project_snapshot(project_root, snapshot_path)

    assert Path(str(result["snapshot_path"])) == snapshot_path
    assert result["archive_root"] == project_root.name
    assert result["file_count"] >= 6
    with zipfile.ZipFile(snapshot_path) as zip_file:
        names = set(zip_file.namelist())

    assert f"{project_root.name}/project.json" in names
    assert f"{project_root.name}/{config.CLEANED_TEXT_FILE_NAME}" in names
    assert f"{project_root.name}/audio_blocks/0001_000001_Narator.wav" in names
    assert f"{project_root.name}/reports/details.json" in names
    assert f"{project_root.name}/log_ai_cleanup_20260425.log" in names


def test_project_snapshot_service_preserves_utf8_filenames_and_content(tmp_path) -> None:
    """
    @brief      Verify snapshots preserve UTF-8 filenames and text payloads.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _build_snapshot_project(tmp_path)
    utf8_file = project_root / "știri_copilărie.txt"
    utf8_file.write_bytes("Ștefan intră în încăpere.\n".encode())
    snapshot_path = tmp_path / "snapshots" / "utf8.zip"

    project_snapshot_service.create_project_snapshot(project_root, snapshot_path)

    with zipfile.ZipFile(snapshot_path) as zip_file:
        archive_name = f"{project_root.name}/știri_copilărie.txt"
        assert archive_name in zip_file.namelist()
        assert zip_file.read(archive_name).decode("utf-8") == "Ștefan intră în încăpere.\n"


def test_project_snapshot_service_rejects_destination_inside_project(tmp_path) -> None:
    """
    @brief      Verify project snapshots cannot be written below the active project root.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  ValueError Expected for inside-project destinations.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _build_snapshot_project(tmp_path)

    with pytest.raises(ValueError, match="outside"):
        project_snapshot_service.create_project_snapshot(project_root, project_root / "snapshot.zip")


def test_project_snapshot_service_appends_zip_extension_and_default_name(tmp_path) -> None:
    """
    @brief      Verify snapshot extension and default file-name helpers.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("Snapshot Helper", tmp_path)

    assert project_snapshot_service.ensure_snapshot_extension(tmp_path / "backup").suffix == ".zip"
    assert (
        project_snapshot_service.default_snapshot_file_name(
            project_root,
            manifest,
            datetime(2026, 4, 25, 16, 45, 30),
        )
        == "Snapshot_Helper_snapshot_20260425_164530.zip"
    )


def test_project_snapshot_service_does_not_leave_final_zip_when_creation_fails(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify failed snapshot creation cleans the temporary archive and skips final replacement.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  FileNotFoundError Expected from the injected missing file.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _build_snapshot_project(tmp_path)
    snapshot_path = tmp_path / "exports" / "failed.zip"
    missing_file = project_root / "missing.txt"

    monkeypatch.setattr(project_snapshot_service, "_iter_project_files", lambda _project_root: iter([missing_file]))

    with pytest.raises(FileNotFoundError):
        project_snapshot_service.create_project_snapshot(project_root, snapshot_path)

    assert snapshot_path.exists() is False
    assert snapshot_path.with_name(f".{snapshot_path.name}.tmp").exists() is False


def test_project_snapshot_service_skips_symlink_directories_when_supported(tmp_path) -> None:
    """
    @brief      Verify symlink directories are not followed into the snapshot archive.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _build_snapshot_project(tmp_path)
    external_folder = tmp_path / "external_payload"
    external_folder.mkdir()
    (external_folder / "external.txt").write_text("outside\n", encoding="utf-8")
    link_path = project_root / "linked_external"
    try:
        link_path.symlink_to(external_folder, target_is_directory=True)
    except OSError:
        return

    snapshot_path = tmp_path / "exports" / "symlink.zip"
    project_snapshot_service.create_project_snapshot(project_root, snapshot_path)

    with zipfile.ZipFile(snapshot_path) as zip_file:
        assert f"{project_root.name}/linked_external/external.txt" not in zip_file.namelist()


# LOCAL HELPERS


def _build_snapshot_project(tmp_path) -> tuple[Path, dict[str, object]]:
    """
    @brief      Build one project containing representative runtime files.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     Tuple with project root and manifest.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("Snapshot Project", tmp_path)
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Clean text\n", encoding="utf-8")
    (project_root / "source.pdf").write_bytes(b"%PDF-1.4")
    (project_root / "log_ai_cleanup_20260425.log").write_text("log\n", encoding="utf-8")
    audio_folder = project_root / "audio_blocks"
    audio_folder.mkdir()
    (audio_folder / "0001_000001_Narator.wav").write_bytes(b"RIFF")
    report_folder = project_root / "reports"
    report_folder.mkdir()
    (report_folder / "details.json").write_text('{"ok": true}\n', encoding="utf-8")
    return project_root, manifest


# END OF FILE
