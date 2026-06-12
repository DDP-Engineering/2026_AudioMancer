# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_traceability.py
@brief Requirement traceability and coverage gate tests.
@details Activates REQ-AUDIO-TEST-006 and REQ-AUDIO-TEST-007 as automated gates.
         REQ-AUDIO-TEST-006: every linked test node in the registers resolves to
         a real test and every Active requirement declares a verification method.
         REQ-AUDIO-TEST-007: every service and controller module is covered by a
         test-linked requirement or a recorded waiver.
@author Eng. Dan Dumitru Pasare
@date 2026-06-09
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from pathlib import Path
import sys

import pytest

# CONSTANTS

REPO_MARKER_FILE = "AGENTS.md"
AUDIT_TOOLS_RELATIVE = Path("02_Tools/audits")


def _repository_root() -> Path:
    """
    @brief      Resolve the repository root from this test file location.
    @return     Repository root path containing the repository marker file.
    @exception  RuntimeError Raised when no repository marker is found.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / REPO_MARKER_FILE).is_file():
            return candidate
    raise RuntimeError(f"Could not locate repository root containing {REPO_MARKER_FILE}.")


_ROOT = _repository_root()
_AUDIT_TOOLS = _ROOT / AUDIT_TOOLS_RELATIVE
if str(_AUDIT_TOOLS) not in sys.path:
    sys.path.insert(0, str(_AUDIT_TOOLS))

import audit_requirement_coverage  # noqa: E402
import audit_traceability  # noqa: E402


# TESTS


@pytest.mark.service
def test_all_linked_requirement_tests_resolve() -> None:
    """
    @brief      Assert every linked requirement test node resolves to a test.
    @details    Verifies REQ-AUDIO-TEST-006 link integrity.
    @return     None.
    @exception  AssertionError Raised when a linked test node is unresolved.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    issues = audit_traceability.audit_issues(_ROOT)
    unresolved = [issue for issue in issues if issue.code == "REQ-LINK-MISSING"]
    assert not unresolved, "\n".join(
        f"{issue.path}:{issue.line} {issue.message}" for issue in unresolved
    )


@pytest.mark.service
def test_active_requirements_declare_verification() -> None:
    """
    @brief      Assert every Active requirement declares a verification method.
    @details    Verifies REQ-AUDIO-TEST-006 verification completeness.
    @return     None.
    @exception  AssertionError Raised when an Active requirement lacks verification.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    issues = audit_traceability.audit_issues(_ROOT)
    missing = [issue for issue in issues if issue.code == "REQ-NO-VERIFICATION"]
    assert not missing, "\n".join(
        f"{issue.path}:{issue.line} {issue.message}" for issue in missing
    )


@pytest.mark.service
def test_services_and_controllers_have_test_coverage() -> None:
    """
    @brief      Assert service and controller modules carry coverage or a waiver.
    @details    Verifies REQ-AUDIO-TEST-007 per-module coverage floor.
    @return     None.
    @exception  AssertionError Raised when a module is uncovered and unwaived.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    issues = audit_requirement_coverage.coverage_issues(_ROOT)
    assert not issues, "\n".join(
        f"{issue.path} [{issue.code}] {issue.message}" for issue in issues
    )


# END OF FILE
