#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_atomic_io_contracts.py
@brief Atomic persistence routing tests for high-value JSON artifacts.
@details Verifies project manifests, app settings, and operation JSON artifacts
         are persisted through the shared atomic writer.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.1.0
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    audio_assembly_service,
    cleanup_metadata_service,
    operation_runtime_service,
    project_workspace_service,
    settings_service,
    text_cleanup_state_service,
    text_extraction_service,
)

# PUBLIC API


def test_project_manifest_save_uses_atomic_json_writer(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify project manifest persistence routes through the atomic JSON writer.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("AtomicManifest", tmp_path)
    write_calls: list[tuple[Path, object]] = []

    def _capture_atomic_write(target_path: str | Path, payload: object) -> None:
        """
        @brief      Capture one atomic writer call.
        @param[in]  target_path Requested target path.
        @param[in]  payload JSON payload passed to the writer.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
        """
        write_calls.append((Path(target_path), payload))

    monkeypatch.setattr(project_workspace_service, "write_json_atomic", _capture_atomic_write)

    project_workspace_service.save_manifest(manifest, project_root)

    assert len(write_calls) == 1
    assert write_calls[0][0] == project_root / config.PROJECT_MANIFEST_FILE_NAME
    assert write_calls[0][1]["project_id"] == manifest["project_id"]


def test_settings_save_uses_atomic_json_writer(monkeypatch, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify application settings persistence routes through the atomic JSON writer.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Shared valid settings fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    settings_path = tmp_path / "settings.json"
    write_calls: list[tuple[Path, object]] = []

    def _capture_atomic_write(target_path: str | Path, payload: object) -> None:
        """
        @brief      Capture one atomic writer call.
        @param[in]  target_path Requested target path.
        @param[in]  payload JSON payload passed to the writer.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
        """
        write_calls.append((Path(target_path), payload))

    monkeypatch.setattr(config, "APP_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(settings_service, "write_json_atomic", _capture_atomic_write)

    settings_service.save_settings(default_settings_payload)

    assert len(write_calls) == 1
    assert write_calls[0][0] == settings_path
    assert write_calls[0][1]["language"] == default_settings_payload["language"]


def test_operation_state_artifact_save_uses_atomic_json_writer(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify operation JSON artifact persistence routes through the atomic JSON writer.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root = tmp_path / "AtomicOperation"
    payload = {"status": "completed"}
    write_calls: list[tuple[Path, object]] = []

    def _capture_atomic_write(target_path: str | Path, payload: object) -> None:
        """
        @brief      Capture one atomic writer call.
        @param[in]  target_path Requested target path.
        @param[in]  payload JSON payload passed to the writer.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
        """
        write_calls.append((Path(target_path), payload))

    monkeypatch.setattr(operation_runtime_service, "write_json_atomic", _capture_atomic_write)

    output_path = operation_runtime_service.write_operation_json_artifact(
        project_root,
        "cleanup",
        config.CLEANUP_STATE_FILE_NAME,
        payload,
    )

    assert output_path == project_root / config.CLEANUP_STATE_FILE_NAME
    assert write_calls == [(output_path, payload)]


def test_cleanup_metadata_uses_atomic_json_writer(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify cleanup metadata sidecar persistence routes through the atomic JSON writer.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    project_root = tmp_path / "AtomicCleanupMetadata"
    write_calls: list[tuple[Path, object]] = []

    def _capture_atomic_write(target_path: str | Path, payload: object) -> None:
        """
        @brief      Capture one atomic writer call.
        @param[in]  target_path Requested target path.
        @param[in]  payload JSON payload passed to the writer.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-12
        @version    0.1.0
        """
        write_calls.append((Path(target_path), payload))

    monkeypatch.setattr(cleanup_metadata_service, "write_json_atomic", _capture_atomic_write)

    cleanup_metadata_service.write_cleanup_metadata(
        project_root,
        None,
        project_root / config.CLEANED_TEXT_FILE_NAME,
        [{"paragraph_id": "paragraph-0001", "text": "Story paragraph."}],
        "deterministic",
    )

    assert len(write_calls) == 1
    assert write_calls[0][0] == project_root / config.CLEANED_TEXT_METADATA_FILE_NAME
    assert write_calls[0][1]["cleanup_mode"] == "deterministic"


def test_manual_cleaned_text_edit_uses_atomic_writers(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify manual cleaned-text edits use atomic text and manifest writers.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("AtomicManualCleanup", tmp_path)
    cleaned_path = project_root / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.write_text("Old text.\n", encoding="utf-8")
    text_calls: list[tuple[Path, str]] = []
    json_calls: list[tuple[Path, object]] = []

    def _capture_text_write(target_path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
        """
        @brief      Capture and perform one atomic text writer call.
        @param[in]  target_path Requested target path.
        @param[in]  text Text payload.
        @param[in]  encoding Text encoding.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-12
        @version    0.1.0
        """
        text_calls.append((Path(target_path), text))
        Path(target_path).write_text(text, encoding=encoding)

    def _capture_json_write(target_path: str | Path, payload: object) -> None:
        """
        @brief      Capture and perform one atomic JSON writer call.
        @param[in]  target_path Requested target path.
        @param[in]  payload JSON payload passed to the writer.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-12
        @version    0.1.0
        """
        json_calls.append((Path(target_path), payload))
        operation_runtime_service.write_json_atomic(target_path, payload)

    monkeypatch.setattr(text_cleanup_state_service, "write_text_atomic", _capture_text_write)
    monkeypatch.setattr(project_workspace_service, "write_json_atomic", _capture_json_write)

    text_cleanup_state_service.save_cleaned_text_edit(project_root, manifest, "Edited text.\n")

    assert text_calls[0] == (cleaned_path, "Edited text.\n")
    assert any(path == project_root / config.PROJECT_MANIFEST_FILE_NAME for path, _payload in json_calls)


def test_audio_assembly_state_uses_atomic_json_writer(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Assembly report and state persistence route through the atomic JSON writer.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    project_root = tmp_path / "AtomicAssembly"
    report = {"operation_status": "running"}
    state = {"status": "running"}
    write_calls: list[tuple[Path, object]] = []

    def _capture_atomic_write(target_path: str | Path, payload: object) -> None:
        """
        @brief      Capture one atomic writer call.
        @param[in]  target_path Requested target path.
        @param[in]  payload JSON payload passed to the writer.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-12
        @version    0.1.0
        """
        write_calls.append((Path(target_path), payload))

    monkeypatch.setattr(audio_assembly_service, "write_json_atomic", _capture_atomic_write)

    audio_assembly_service._persist_state(project_root, report, state)

    assert write_calls == [
        (project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME, report),
        (project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME, state),
    ]


def test_text_extraction_running_state_uses_atomic_json_writer(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Text Extraction running state persistence routes through the atomic JSON writer.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    state_path = tmp_path / config.EXTRACTION_STATE_FILE_NAME
    input_path = tmp_path / "story.txt"
    output_path = tmp_path / config.EXTRACTED_TEXT_FILE_NAME
    write_calls: list[tuple[Path, object]] = []

    def _capture_atomic_write(target_path: str | Path, payload: object) -> None:
        """
        @brief      Capture one atomic writer call.
        @param[in]  target_path Requested target path.
        @param[in]  payload JSON payload passed to the writer.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-12
        @version    0.1.0
        """
        write_calls.append((Path(target_path), payload))

    monkeypatch.setattr(text_extraction_service, "write_json_atomic", _capture_atomic_write)

    text_extraction_service._write_running_state(
        state_path,
        input_path,
        output_path,
        "run-token",
        1,
        2,
        ["warning"],
        "txt",
        None,
    )

    assert write_calls[0][0] == state_path
    assert write_calls[0][1]["status"] == "running"


# END OF FILE
