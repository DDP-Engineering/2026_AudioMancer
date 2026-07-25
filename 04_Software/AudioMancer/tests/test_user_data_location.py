#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_user_data_location.py
@brief Contract tests for the resolved writable application data location.
@details Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b,
         REQ-PLAT-574da6b6-8902-4e99-aad7-30383dc1db64 and
         REQ-PLAT-f18086ef-3896-4be9-8afa-580b00534dbd against
         .agentic/specs/user_data_location.spec.md (S-0001, S-0002, S-0003):
         where settings and logs live for portable, override and read-only
         installation layouts.
@author Eng. Dan Dumitru Pasare
@date 2026-07-25
@version 0.1.0
"""

# IMPORTS

import importlib
import json
from pathlib import Path
import sys

from audiomancer import config
from audiomancer.services import logging_service, settings_service

# CONSTANTS

# @brief Environment variables the resolver consults, cleared before each scenario.
_DATA_LOCATION_ENVIRONMENT_VARIABLES = (
    "AUDIOMANCER_DATA_DIR",
    "LOCALAPPDATA",
    "APPDATA",
    "XDG_DATA_HOME",
)


# HELPER FUNCTIONS


def _isolate_data_location_environment(monkeypatch) -> None:
    """
    @brief      Remove every environment variable that steers data-root resolution.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    for variable_name in _DATA_LOCATION_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)


def _unwritable_application_root(tmp_path: Path) -> Path:
    """
    @brief      Build an application root that cannot accept a probe file.
    @param[in]  tmp_path Pytest temporary directory fixture value.
    @return     Path to a non-existent installation root.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    return tmp_path / "read_only_install_root"


# PUBLIC API


def test_resolve_user_data_root_prefers_environment_override(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify AUDIOMANCER_DATA_DIR wins over every other candidate.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    writable_application_root = tmp_path / "portable_install"
    writable_application_root.mkdir()
    override_root = tmp_path / "pinned_data"
    monkeypatch.setenv("AUDIOMANCER_DATA_DIR", str(override_root))

    resolved_root = config.resolve_user_data_root(writable_application_root)

    assert resolved_root == override_root.resolve()


def test_resolve_user_data_root_ignores_blank_environment_override(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a blank override is skipped instead of resolving to the process directory.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    writable_application_root = tmp_path / "portable_install"
    writable_application_root.mkdir()
    monkeypatch.setenv("AUDIOMANCER_DATA_DIR", "   ")

    resolved_root = config.resolve_user_data_root(writable_application_root)

    assert resolved_root == writable_application_root.resolve()


def test_resolve_user_data_root_uses_writable_application_root(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a writable application root keeps data beside the application.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001. The
                write probe runs for real here, so a genuinely writable folder is
                required to select the portable branch.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    writable_application_root = tmp_path / "portable_install"
    writable_application_root.mkdir()

    resolved_root = config.resolve_user_data_root(writable_application_root)

    assert resolved_root == writable_application_root.resolve()
    assert list(writable_application_root.iterdir()) == []


def test_resolve_user_data_root_rejects_a_non_directory_application_root(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify an application root that is not a directory falls back to per-user data.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    file_application_root = tmp_path / "not_a_directory"
    file_application_root.write_text("", encoding="utf-8")
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    resolved_root = config.resolve_user_data_root(file_application_root)

    assert resolved_root == (local_app_data / config.APP_NAME).resolve()


def test_resolve_user_data_root_falls_back_to_local_appdata_on_windows(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a read-only Windows install root resolves to %LOCALAPPDATA%.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    local_app_data = tmp_path / "LocalAppData"
    roaming_app_data = tmp_path / "RoamingAppData"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("APPDATA", str(roaming_app_data))

    resolved_root = config.resolve_user_data_root(_unwritable_application_root(tmp_path))

    assert resolved_root == (local_app_data / config.APP_NAME).resolve()


def test_resolve_user_data_root_falls_back_to_roaming_appdata_on_windows(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify %APPDATA% is used when %LOCALAPPDATA% is unset.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    roaming_app_data = tmp_path / "RoamingAppData"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(roaming_app_data))

    resolved_root = config.resolve_user_data_root(_unwritable_application_root(tmp_path))

    assert resolved_root == (roaming_app_data / config.APP_NAME).resolve()


def test_resolve_user_data_root_falls_back_to_xdg_data_home_on_linux(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a read-only Linux install root resolves to $XDG_DATA_HOME.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    xdg_data_home = tmp_path / "xdg_data_home"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))

    resolved_root = config.resolve_user_data_root(_unwritable_application_root(tmp_path))

    assert resolved_root == (xdg_data_home / config.APP_NAME).resolve()


def test_resolve_user_data_root_falls_back_to_local_share_on_linux(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify ~/.local/share is used on Linux when $XDG_DATA_HOME is unset.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    monkeypatch.setattr(sys, "platform", "linux")

    resolved_root = config.resolve_user_data_root(_unwritable_application_root(tmp_path))

    assert resolved_root == (Path.home() / ".local" / "share" / config.APP_NAME).resolve()


def test_resolve_user_data_root_falls_back_to_application_support_on_macos(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a read-only macOS bundle resolves to ~/Library/Application Support.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    monkeypatch.setattr(sys, "platform", "darwin")

    resolved_root = config.resolve_user_data_root(_unwritable_application_root(tmp_path))

    assert resolved_root == (Path.home() / "Library" / "Application Support" / config.APP_NAME).resolve()


def test_resolve_user_data_root_rejects_frozen_extraction_directory(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify the writable PyInstaller extraction folder is never used for data.
    @details    Covers REQ-PLAT-7c255c35-f7e7-4d44-8513-42f480d07d6b / S-0001. A
                onefile bootloader deletes _MEIPASS on exit, so selecting it would
                silently discard operator settings on every run.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    _isolate_data_location_environment(monkeypatch)
    extraction_root = tmp_path / "_MEI123456"
    extraction_root.mkdir()
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraction_root), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    resolved_root = config.resolve_user_data_root(extraction_root)

    assert resolved_root == (local_app_data / config.APP_NAME).resolve()


def test_settings_and_log_paths_follow_the_resolved_data_root(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify the module constants and the log directory derive from the resolved root.
    @details    Covers REQ-PLAT-574da6b6-8902-4e99-aad7-30383dc1db64 / S-0002.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    pinned_data_root = tmp_path / "pinned_data"

    try:
        with monkeypatch.context() as override_patch:
            override_patch.setenv("AUDIOMANCER_DATA_DIR", str(pinned_data_root))
            importlib.reload(config)
            importlib.reload(logging_service)

            assert pinned_data_root.resolve() == config.APP_USER_DATA_ROOT
            assert pinned_data_root.resolve() / "settings.json" == config.APP_SETTINGS_PATH
            assert config.APP_DEFAULT_SETTINGS_PATH == config.APP_ROOT / "settings.json"
            assert config.APP_SETTINGS_PATH != config.APP_DEFAULT_SETTINGS_PATH
            assert logging_service._log_directory_path() == (
                pinned_data_root.resolve() / config.APP_LOG_DIRECTORY_NAME
            )
    finally:
        importlib.reload(config)
        importlib.reload(logging_service)


def test_read_only_application_root_keeps_settings_and_logs_under_the_data_root(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a read-only installation root is never written to at runtime.
    @details    Covers REQ-PLAT-574da6b6-8902-4e99-aad7-30383dc1db64 and
                REQ-PLAT-f18086ef-3896-4be9-8afa-580b00534dbd / S-0002, S-0003.
                Reproduces the Program Files layout: packaged resources and the
                bundled default settings stay under the install root while every
                write lands under the per-user data root.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    installation_root = tmp_path / "Program Files" / "AudioMancer"
    installation_root.mkdir(parents=True)
    bundled_settings_path = installation_root / "settings.json"
    bundled_payload = settings_service.build_default_settings()
    bundled_payload["language"] = "ro"
    bundled_settings_path.write_text(json.dumps(bundled_payload, indent=2), encoding="utf-8")
    bundled_settings_bytes = bundled_settings_path.read_bytes()

    user_data_root = tmp_path / "LocalAppData" / "AudioMancer"
    monkeypatch.setattr(config, "APP_ROOT", installation_root)
    monkeypatch.setattr(config, "APP_DEFAULT_SETTINGS_PATH", bundled_settings_path)
    monkeypatch.setattr(config, "APP_USER_DATA_ROOT", user_data_root)
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", user_data_root / "settings.json")

    loaded_settings = settings_service.load_settings()
    log_file_path = logging_service.initialize_logging()
    logging_service.get_component_logger("app").info(
        "read-only install record",
        extra={"func_name": "test", "event": "check"},
    )
    logging_service.shutdown_logging()

    assert loaded_settings["language"] == "ro"
    assert (user_data_root / "settings.json").is_file()
    assert log_file_path is not None
    assert log_file_path.parent == user_data_root / config.APP_LOG_DIRECTORY_NAME
    assert log_file_path.is_file()
    assert bundled_settings_path.read_bytes() == bundled_settings_bytes
    assert sorted(entry.name for entry in installation_root.iterdir()) == ["settings.json"]


# END OF FILE
