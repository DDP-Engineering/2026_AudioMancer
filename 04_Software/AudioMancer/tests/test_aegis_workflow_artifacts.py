#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_aegis_workflow_artifacts.py
@brief Regression coverage for repository-owned AEGIS workflow artifacts.
@details Verifies deleted-source traceability behavior and the source hygiene
         contract carried by the migrated AEGIS requirements.
"""

# IMPORTS

import importlib.util
from pathlib import Path

# CONSTANTS

_REPO_ROOT = Path(__file__).resolve().parents[3]
_AEGIS_PATH = _REPO_ROOT / ".agentic" / "aegis.py"
_HYGIENE_PATHS = (
    "04_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py",
    "04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py",
    "04_Software/AudioMancer/src/audiomancer/services/__init__.py",
    "04_Software/AudioMancer/src/audiomancer/services/text_cleanup_service.py",
    "04_Software/AudioMancer/src/audiomancer/ui/__init__.py",
    "04_Software/AudioMancer/src/audiomancer/ui/controllers/__init__.py",
    "04_Software/AudioMancer/src/audiomancer/ui/pages/__init__.py",
    "04_Software/AudioMancer/tests/test_logging_service.py",
)


# PUBLIC API


def test_uncovered_source_check_ignores_deleted_source(monkeypatch) -> None:
    """
    @brief      Verify a deleted source path is not reported as uncovered current source.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    """
    aegis = _load_aegis_module()
    deleted_path = "04_Software/AudioMancer/src/audiomancer/services/deleted_service.py"
    findings: list[tuple[str, str, str, str]] = []
    config = {
        "layout": {
            "source": ["04_Software/AudioMancer/src/"],
            "tests": ["04_Software/AudioMancer/tests/"],
        },
        "check": {},
    }
    monkeypatch.setattr(
        aegis,
        "collect_diff",
        lambda _config: ([deleted_path], [], [], ""),
    )

    aegis.check_diff(
        lambda *finding: findings.append(finding),
        lambda _path: False,
        config,
        [],
        [],
        None,
    )

    assert not any(
        check == "uncovered-source" and path == deleted_path
        for _level, check, path, _message in findings
    )


def test_requirement_source_hygiene_paths_follow_repository_conventions() -> None:
    """
    @brief      Verify listed maintenance files follow encoding and module-tag rules.
    @return     None.
    @exception  None.
    """
    for relative_path in _HYGIENE_PATHS:
        content = (_REPO_ROOT / relative_path).read_bytes()
        assert not content.startswith(b"\xef\xbb\xbf"), relative_path
        text = content.decode("utf-8")
        assert "@author" not in text, relative_path
        assert "@date" not in text, relative_path
        assert "@version" not in text, relative_path


# LOCAL HELPERS


def _load_aegis_module():
    """
    @brief      Load the repository-local AEGIS companion as a test module.
    @return     Imported AEGIS module.
    @exception  AssertionError Raised when the module loader cannot be created.
    """
    spec = importlib.util.spec_from_file_location("audiomancer_aegis", _AEGIS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# END OF FILE
