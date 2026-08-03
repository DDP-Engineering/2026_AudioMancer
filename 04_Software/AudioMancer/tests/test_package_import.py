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
"""

# IMPORTS

from pathlib import Path
import tomllib

import audiomancer

# CONSTANTS

APP_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "2.0.0"
EXPECTED_RELEASE_DATE = "2026-07-30"
CHANGELOG_PATH = APP_ROOT.parents[1] / "CHANGELOG.md"
USER_GUIDE_PATHS = (
    APP_ROOT.parents[1] / "05_SoftwareDocu" / "UserGuide" / "index.html",
    APP_ROOT.parents[1] / "05_SoftwareDocu" / "UserGuide_ro" / "index.html",
)

# PUBLIC API


def test_package_exposes_main_and_release_version_metadata() -> None:
    """
    @brief      Verify every release surface exports one aligned release version.
    @return     None.
    @exception  None
    """
    # REQ-REL-6347c5a6-71bf-4d9b-8197-cddae2ccfcd2; S-0001..S-0004.
    pyproject_payload = tomllib.loads((APP_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock_payload = tomllib.loads((APP_ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_audiomancer_package = next(
        package for package in lock_payload["package"] if package["name"] == "audiomancer"
    )

    assert callable(audiomancer.main)
    assert audiomancer.__version__ == EXPECTED_VERSION
    assert pyproject_payload["project"]["version"] == EXPECTED_VERSION
    assert locked_audiomancer_package["version"] == EXPECTED_VERSION
    changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
    unreleased_heading = "## [Unreleased]"
    release_heading = f"## [{EXPECTED_VERSION}] - {EXPECTED_RELEASE_DATE}"
    assert changelog.count(unreleased_heading) == 1
    assert changelog.count(release_heading) == 1
    assert changelog.index(unreleased_heading) < changelog.index(release_heading)
    for user_guide_path in USER_GUIDE_PATHS:
        user_guide = user_guide_path.read_text(encoding="utf-8")
        assert f"v{EXPECTED_VERSION}</title>" in user_guide
        assert user_guide.count(EXPECTED_VERSION) == 3


# END OF FILE
