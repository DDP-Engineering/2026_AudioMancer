#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file       test_access_mode.py
@brief      Tests for workflow access-mode persistence and write-zone behavior.
@details    Covers the repo-wide maintenance mode added to the embedded
            agentic workflow CLI and guard hook. The tests verify that legacy
            run graphs remain standard, broad access requires a human reason,
            and protected paths remain blocked even when normal repo files are
            allowed.
@author     Eng. Dan Dumitru Pasare
@date       2026-06-18
@version    1.0.0
"""

from __future__ import annotations

# -----------------------------------------------------------------------------
# IMPORTS
# -----------------------------------------------------------------------------

import io
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

from agentic_workflow.cli import main as cli_main
from agentic_workflow.store import (
    agentic_root,
    graph_path,
    journal_path,
    load_graph,
    write_current_run,
)


AGENTIC_ROOT = Path(__file__).resolve().parents[2]
GUARD_HOOK = AGENTIC_ROOT / "hooks" / "guard_write_zone.py"


def _load_guard_main():
    spec = importlib.util.spec_from_file_location("agentic_guard_write_zone", GUARD_HOOK)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


guard_main = _load_guard_main()


# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------


def run_cli(tmp_path: Path, *args: str) -> None:
    """
    @brief      Run the workflow CLI with a temporary repository root.
    @param[in]  tmp_path Temporary repository root used as the current directory.
    @param[in]  args CLI arguments forwarded to `agentic-workflow`.
    @return     None.
    @version    1.0.0
    """
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        cli_main(list(args))
    finally:
        os.chdir(cwd)


def run_guard_hook(
    tmp_path: Path, command: str, monkeypatch: pytest.MonkeyPatch
) -> str:
    """
    @brief      Run the write-zone guard hook against one patch command.
    @param[in]  tmp_path Temporary repository root used by the hook payload.
    @param[in]  command Patch command text that names edited paths.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     Hook stdout.
    @version    1.0.0
    """
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "cwd": str(tmp_path),
        "tool_input": {"command": command},
    }
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", stdout)
    guard_main()
    return stdout.getvalue()


def write_legacy_graph(tmp_path: Path) -> str:
    """
    @brief      Write a pre-access-mode graph for migration compatibility tests.
    @param[in]  tmp_path Temporary repository root.
    @return     Run identifier for the legacy graph.
    @version    1.0.0
    """
    run_id = "change-legacy"
    agentic_root(tmp_path).mkdir(parents=True, exist_ok=True)
    write_current_run(tmp_path, run_id)
    path = graph_path(tmp_path, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "stage": "intake",
                "intent": {
                    "id": "I-0001",
                    "kind": "change",
                    "statement": "Legacy graph",
                    "scope_hint": [],
                    "status": "draft",
                    "created_at": "2026-06-18T00:00:00+00:00",
                },
                "spec_items": [],
                "checks": [],
                "evidence": [],
                "change_units": [],
                "decisions": [],
                "defects": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_id


# -----------------------------------------------------------------------------
# TESTS
# -----------------------------------------------------------------------------


def test_default_start_reports_standard_access_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief Verify that new workflow runs start in standard access mode."""
    run_cli(tmp_path, "start", "--kind", "change", "--statement", "Maintain workflow")
    start_data = json.loads(capsys.readouterr().out)

    run_cli(tmp_path, "status")
    status_data = json.loads(capsys.readouterr().out)

    assert start_data["access_mode"] == "standard"
    assert status_data["access_mode"] == "standard"


def test_legacy_graph_loading_defaults_to_standard_access_mode(tmp_path: Path) -> None:
    """@brief Verify that pre-existing graph files remain loadable."""
    write_legacy_graph(tmp_path)

    graph = load_graph(tmp_path)

    assert graph.access_mode == "standard"


def test_repo_wide_start_requires_access_reason(tmp_path: Path) -> None:
    """@brief Verify broad access cannot be started without a human reason."""
    with pytest.raises(SystemExit):
        run_cli(
            tmp_path,
            "start",
            "--kind",
            "change",
            "--statement",
            "Maintain workflow",
            "--access-mode",
            "repo-wide",
        )


def test_set_access_mode_records_decision_and_journal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief Verify broad access is persisted with an auditable reason."""
    reason = "Human-approved broad workflow maintenance"
    run_cli(tmp_path, "start", "--kind", "change", "--statement", "Maintain workflow")
    capsys.readouterr()
    run_cli(tmp_path, "set-access-mode", "repo-wide", "--reason", reason)
    data = json.loads(capsys.readouterr().out)
    graph = load_graph(tmp_path)
    journal = journal_path(tmp_path, graph.run_id).read_text(encoding="utf-8")

    assert data["access_mode"] == "repo-wide"
    assert graph.access_mode == "repo-wide"
    assert graph.decisions[-1].chosen == "repo-wide"
    assert graph.decisions[-1].rationale == reason
    assert '"event": "access_mode.set"' in journal
    assert reason in journal


def test_standard_access_denies_out_of_stage_normal_repo_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief Verify standard mode keeps stage write-zone restrictions."""
    run_cli(tmp_path, "start", "--kind", "change", "--statement", "Maintain workflow")

    output = run_guard_hook(
        tmp_path,
        "*** Begin Patch\n*** Update File: README.md\n@@\n+docs\n*** End Patch\n",
        monkeypatch,
    )

    assert "permissionDecision" in output
    assert "deny" in output
    assert "README.md" in output


def test_repo_wide_access_allows_normal_repo_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief Verify repo-wide mode allows normal repository maintenance files."""
    run_cli(tmp_path, "start", "--kind", "change", "--statement", "Maintain workflow")
    run_cli(
        tmp_path,
        "set-access-mode",
        "repo-wide",
        "--reason",
        "Human-approved broad workflow maintenance",
    )

    output = run_guard_hook(
        tmp_path,
        "*** Begin Patch\n*** Update File: README.md\n@@\n+docs\n*** End Patch\n",
        monkeypatch,
    )

    assert output == ""


@pytest.mark.parametrize("path", [".git/config", ".env"])
def test_repo_wide_access_blocks_protected_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """@brief Verify repo-wide mode still denies protected paths."""
    run_cli(tmp_path, "start", "--kind", "change", "--statement", "Maintain workflow")
    run_cli(
        tmp_path,
        "set-access-mode",
        "repo-wide",
        "--reason",
        "Human-approved broad workflow maintenance",
    )

    output = run_guard_hook(
        tmp_path,
        f"*** Begin Patch\n*** Update File: {path}\n@@\n+blocked\n*** End Patch\n",
        monkeypatch,
    )

    assert "permissionDecision" in output
    assert "deny" in output
    assert path in output


# -----------------------------------------------------------------------------
# END OF FILE
# -----------------------------------------------------------------------------
