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
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    audio_assembly_service,
    operation_runtime_service,
    project_workspace_service,
    settings_service,
    text_cleanup_service,
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
        """
        write_calls.append((Path(target_path), payload))

    monkeypatch.setattr(operation_runtime_service, "write_json_atomic", _capture_atomic_write)

    output_path = operation_runtime_service.write_operation_json_artifact(
        project_root,
        "translation",
        config.TRANSLATED_CHUNKS_FILE_NAME,
        payload,
    )

    assert output_path == project_root / config.TRANSLATED_CHUNKS_FILE_NAME
    assert write_calls == [(output_path, payload)]


def test_manual_cleaned_text_edit_uses_atomic_writers(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify manual cleaned-text edits use atomic text and manifest writers.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("AtomicManualCleanup", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("Old text.", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": source_path.name,
        "stored_relative_path": source_path.name,
        "file_type": "txt",
        "imported_at": "2026-07-27T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, project_root)
    text_extraction_service.extract_text(project_root, manifest)
    text_cleanup_service.clean_text(project_root, manifest)
    cleaned_path = project_root / config.CLEANED_TEXT_FILE_NAME
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
        """
        json_calls.append((Path(target_path), payload))
        operation_runtime_service.write_json_atomic(target_path, payload)

    monkeypatch.setattr(text_cleanup_service, "write_text_atomic", _capture_text_write)
    monkeypatch.setattr(text_cleanup_service, "write_json_atomic", _capture_json_write)
    monkeypatch.setattr(project_workspace_service, "write_json_atomic", _capture_json_write)

    text_cleanup_state_service.save_cleaned_text_edit(project_root, "Edited text.\n")

    assert text_calls[0] == (cleaned_path, "Edited text.\n")
    assert any(
        path == project_root / config.CLEANUP_DOCUMENT_FILE_NAME
        for path, _payload in json_calls
    )
    assert any(path == project_root / config.PROJECT_MANIFEST_FILE_NAME for path, _payload in json_calls)


def test_audio_assembly_state_uses_atomic_json_writer(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Assembly report and state persistence route through the atomic JSON writer.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
        """
        write_calls.append((Path(target_path), payload))

    monkeypatch.setattr(audio_assembly_service, "write_json_atomic", _capture_atomic_write)

    audio_assembly_service._persist_state(project_root, report, state)

    assert write_calls == [
        (project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME, report),
        (project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME, state),
    ]


# END OF FILE
