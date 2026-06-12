#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_package_import.py
@brief Focused smoke tests for the AudioMancer package scaffold.
@details Verifies that the package imports and keeps release version metadata aligned.
@author Eng. Dan Dumitru Pasare
@date 2026-05-14
@version 1.1.5
"""

# IMPORTS

from pathlib import Path
import tomllib

import audiomancer

# CONSTANTS

APP_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.5.8"

# PUBLIC API


def test_package_exposes_main_and_release_version_metadata() -> None:
    """
    @brief      Verify the package exports the entrypoint and aligned release version.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    1.1.0
    """
    pyproject_payload = tomllib.loads((APP_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock_payload = tomllib.loads((APP_ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_audiomancer_package = next(
        package for package in lock_payload["package"] if package["name"] == "audiomancer"
    )

    assert callable(audiomancer.main)
    assert audiomancer.__version__ == EXPECTED_VERSION
    assert pyproject_payload["project"]["version"] == EXPECTED_VERSION
    assert locked_audiomancer_package["version"] == EXPECTED_VERSION


# END OF FILE
