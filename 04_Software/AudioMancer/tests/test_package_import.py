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
import re
import tomllib

import audiomancer

# CONSTANTS

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
USER_GUIDE_PATHS = (
    REPO_ROOT / "05_SoftwareDocu" / "UserGuide" / "index.html",
    REPO_ROOT / "05_SoftwareDocu" / "UserGuide_ro" / "index.html",
)
UNRELEASED_HEADING = "## [Unreleased]"
# @brief Semantic version accepted on every release surface.
SEMANTIC_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
# @brief Expected number of version occurrences per offline help bundle: the
#        document title, the help version line, and the application version line.
HELP_VERSION_OCCURRENCES = 3

# PUBLIC API


def test_package_exposes_main_and_release_version_metadata() -> None:
    """
    @brief      Verify every release surface declares one identical version.
    @details    The version is read from `pyproject.toml`, which is what builds
                the package, and every other surface must agree with it. No
                version is written here, so a release bump needs no test edit
                and any surface left behind fails this test.
    @return     None.
    @exception  None
    """
    # REQ-REL-6347c5a6-71bf-4d9b-8197-cddae2ccfcd2; S-0001..S-0004.
    pyproject_payload = tomllib.loads((APP_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    release_version = pyproject_payload["project"]["version"]
    assert SEMANTIC_VERSION_PATTERN.match(release_version), (
        f"pyproject.toml version {release_version!r} is not a semantic X.Y.Z version"
    )

    lock_payload = tomllib.loads((APP_ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_audiomancer_package = next(
        package for package in lock_payload["package"] if package["name"] == "audiomancer"
    )

    assert callable(audiomancer.main)
    assert audiomancer.__version__ == release_version, (
        f"audiomancer.__version__ is {audiomancer.__version__!r}, but pyproject.toml declares {release_version!r}"
    )
    assert locked_audiomancer_package["version"] == release_version, (
        f"uv.lock pins audiomancer {locked_audiomancer_package['version']!r}, "
        f"but pyproject.toml declares {release_version!r}. Run `uv lock` after a version bump."
    )

    changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
    assert changelog.count(UNRELEASED_HEADING) == 1, f"CHANGELOG.md must carry exactly one {UNRELEASED_HEADING} section"
    release_headings = re.findall(
        rf"^## \[{re.escape(release_version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})$",
        changelog,
        flags=re.MULTILINE,
    )
    assert len(release_headings) == 1, (
        f"CHANGELOG.md must carry exactly one dated '## [{release_version}] - YYYY-MM-DD' "
        f"heading, found {len(release_headings)}"
    )
    release_heading = f"## [{release_version}] - {release_headings[0]}"
    assert changelog.index(UNRELEASED_HEADING) < changelog.index(release_heading), (
        f"{UNRELEASED_HEADING} must appear above the {release_version} release section"
    )

    for user_guide_path in USER_GUIDE_PATHS:
        user_guide = user_guide_path.read_text(encoding="utf-8")
        assert f"v{release_version}</title>" in user_guide, (
            f"{user_guide_path.parent.name} title does not declare v{release_version}"
        )
        assert user_guide.count(release_version) == HELP_VERSION_OCCURRENCES, (
            f"{user_guide_path.parent.name} mentions {release_version} "
            f"{user_guide.count(release_version)} times, expected {HELP_VERSION_OCCURRENCES}"
        )


# END OF FILE
