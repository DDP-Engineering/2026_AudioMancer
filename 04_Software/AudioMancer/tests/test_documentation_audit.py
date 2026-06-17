#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_documentation_audit.py
@brief Documentation audit behavior tests.
@details Verifies REQ-TEST-009: component documentation remains the default
         documentation audit gate, while broad documentation review is opt-in.
@author Eng. Dan Dumitru Pasare
@date 2026-06-17
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

import os
from pathlib import Path
import sys

# CONSTANTS

REPO_MARKER_FILE = "AGENTS.md"
AUDIT_TOOLS_RELATIVE = Path("02_Tools/audits")


def _repository_root() -> Path:
    """
    @brief      Resolve the repository root from this test file location.
    @return     Repository root path containing the repository marker file.
    @exception  RuntimeError Raised when no repository marker is found.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
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

import audit_documentation  # noqa: E402

# TESTS


def test_changed_service_newer_than_component_doc_reports_stale(tmp_path) -> None:
    """
    @brief      Assert service changes newer than component docs are reported.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when no stale component finding is reported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
    @version    0.1.0
    """
    source_path = Path("04_Software/AudioMancer/src/audiomancer/services/ai_chunking_service.py")
    doc_path = Path("05_SoftwareDocu/AudioMancer_Text_Pipeline_Support_Services.md")
    _write_file(tmp_path / source_path, mtime=2000)
    _write_file(tmp_path / doc_path, mtime=1000)

    issues = audit_documentation._audit_service_component_docs(tmp_path, [source_path])

    assert _codes(issues) == ["DOC-COMPONENT-STALE-CHECK"]


def test_changed_service_without_component_doc_reports_missing(tmp_path) -> None:
    """
    @brief      Assert undocumented service modules require a SoftwareDocu component page.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  AssertionError Raised when no missing component finding is reported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
    @version    0.1.0
    """
    source_path = Path("04_Software/AudioMancer/src/audiomancer/services/new_feature_service.py")
    _write_file(tmp_path / source_path, mtime=2000)

    issues = audit_documentation._audit_service_component_docs(tmp_path, [source_path])

    assert _codes(issues) == ["DOC-COMPONENT-MISSING"]


def test_default_audit_does_not_require_broad_readme_refresh(tmp_path, monkeypatch, capsys) -> None:
    """
    @brief      Assert default documentation audit ignores broad README freshness.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  capsys Pytest output capture fixture.
    @return     None.
    @exception  AssertionError Raised when default audit reports broad documentation issues.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
    @version    0.1.0
    """
    _create_component_documentation_repo(tmp_path)
    monkeypatch.setattr(audit_documentation, "repository_root", lambda: tmp_path)

    status = audit_documentation.run_audit()
    output = capsys.readouterr().out

    assert status == 0
    assert "DOC-MISSING" not in output
    assert "DOC-STALE-CHECK" not in output


def test_include_broad_docs_preserves_broad_readme_findings(tmp_path, monkeypatch, capsys) -> None:
    """
    @brief      Assert explicit broad documentation review still reports broad missing docs.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  capsys Pytest output capture fixture.
    @return     None.
    @exception  AssertionError Raised when broad review no longer reports broad docs.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
    @version    0.1.0
    """
    _create_component_documentation_repo(tmp_path)
    monkeypatch.setattr(audit_documentation, "repository_root", lambda: tmp_path)

    status = audit_documentation.run_audit(include_broad_docs=True)
    output = capsys.readouterr().out

    assert status == 1
    assert "DOC-MISSING" in output


def test_changed_component_doc_absent_from_softwaredocu_readme_fails(tmp_path, monkeypatch, capsys) -> None:
    """
    @brief      Assert changed component pages must be listed in the SoftwareDocu README.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  capsys Pytest output capture fixture.
    @return     None.
    @exception  AssertionError Raised when an unlisted component page is accepted.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
    @version    0.1.0
    """
    doc_path = Path("05_SoftwareDocu/AudioMancer_New_Component_Service.md")
    _write_file(tmp_path / doc_path, "# New Component\n", mtime=2000)
    _write_file(tmp_path / "05_SoftwareDocu/README.md", "# 05_SoftwareDocu\n", mtime=1000)
    monkeypatch.setattr(audit_documentation, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(
        audit_documentation,
        "changed_files",
        lambda _root, suffix=None: [doc_path] if suffix == ".md" else [],
    )

    status = audit_documentation.run_audit(changed_only=True)
    output = capsys.readouterr().out

    assert status == 1
    assert "DOC-COMPONENT-README-MISSING" in output


# LOCAL HELPERS


def _create_component_documentation_repo(root: Path) -> None:
    """
    @brief      Create a minimal synthetic repository with current component documentation.
    @param[in]  root Synthetic repository root.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
    @version    0.1.0
    """
    source_path = root / "04_Software/AudioMancer/src/audiomancer/services/ai_chunking_service.py"
    doc_path = root / "05_SoftwareDocu/AudioMancer_Text_Pipeline_Support_Services.md"
    _write_file(source_path, mtime=2000)
    _write_file(doc_path, "# Text Pipeline\n", mtime=3000)
    _write_file(
        root / "05_SoftwareDocu/README.md",
        "# 05_SoftwareDocu\n\n- `AudioMancer_Text_Pipeline_Support_Services.md`\n",
        mtime=3000,
    )


def _write_file(path: Path, text: str = "", mtime: int = 1000) -> None:
    """
    @brief      Write a synthetic test file with a deterministic modification time.
    @param[in]  path File path to create.
    @param[in]  text File contents.
    @param[in]  mtime Modification timestamp to assign.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
    @version    0.1.0
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _codes(issues) -> list[str]:
    """
    @brief      Extract issue codes from documentation audit issues.
    @param[in]  issues Audit issues to inspect.
    @return     Issue code list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-17
    @version    0.1.0
    """
    return [issue.code for issue in issues]


# END OF FILE
