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
from audiomancer.services import operation_runtime_service, project_workspace_service, settings_service

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


# END OF FILE
