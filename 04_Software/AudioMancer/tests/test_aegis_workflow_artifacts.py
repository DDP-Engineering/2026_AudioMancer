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
@brief Regression coverage for repository source hygiene conventions.
@details Verifies that the listed maintenance files carry no byte-order mark
         and none of the docstring tags the repository code style forbids.
"""

# IMPORTS

from pathlib import Path

# CONSTANTS

_REPO_ROOT = Path(__file__).resolve().parents[3]
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


# END OF FILE
