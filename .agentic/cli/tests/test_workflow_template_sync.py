#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""Regression tests for the synced embedded agentic workflow."""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from agentic_workflow.cli import main
from agentic_workflow.invariants import blocking_failures, evaluate
from agentic_workflow.store import load_graph


AGENTIC_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = AGENTIC_ROOT / "hooks"


def run_cli(tmp_path: Path, *args: str) -> None:
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        main(list(args))
    finally:
        os.chdir(cwd)


def load_hook(module_name: str) -> ModuleType:
    path = HOOKS_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"agentic_hook_{module_name}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_hook(func, payload: dict, monkeypatch: pytest.MonkeyPatch) -> str:
    stdin = io.StringIO(json.dumps(payload))
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    func()
    return stdout.getvalue()


def apply_patch_payload(tmp_path: Path, target: str) -> dict:
    command = f"*** Begin Patch\n*** Update File: {target}\n@@\n+change\n*** End Patch\n"
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "cwd": str(tmp_path),
        "tool_input": {"command": command},
    }


def file_edit_payload(tmp_path: Path, tool_name: str, target: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "cwd": str(tmp_path),
        "tool_input": {"file_path": target, "old_string": "a", "new_string": "b"},
    }


def init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)


def test_set_stage_records_decision_and_routes_run(tmp_path: Path) -> None:
    run_cli(tmp_path, "start", "--kind", "feature", "--statement", "Add discounts")
    run_cli(tmp_path, "set-stage", "check", "--reason", "Human-approved test revision")

    graph = load_graph(tmp_path)

    assert graph.stage == "check"
    assert graph.decisions[-1].question == "Workflow stage route"
    assert graph.decisions[-1].chosen == "check"


def test_superseded_late_failure_no_longer_blocks_no_regression(tmp_path: Path) -> None:
    run_cli(tmp_path, "start", "--kind", "feature", "--statement", "Add discounts")
    run_cli(tmp_path, "set-stage", "implementation", "--reason", "Testing supersede flow")
    run_cli(
        tmp_path,
        "record-evidence",
        "--kind",
        "test-run",
        "--result",
        "fail",
        "--failure-kind",
        "environment",
        "--summary",
        "Gate failed because the command used a bad interpreter path",
    )
    run_cli(
        tmp_path,
        "record-evidence",
        "--kind",
        "test-run",
        "--result",
        "pass",
        "--summary",
        "Same gate passed with the configured interpreter path",
    )
    run_cli(
        tmp_path,
        "supersede-evidence",
        "--id",
        "E-0001",
        "--by",
        "E-0002",
        "--reason",
        "Passing rerun proves the old failure was environmental",
    )

    graph = load_graph(tmp_path)

    assert blocking_failures(evaluate(tmp_path, graph)) == []
    assert graph.evidence[0].status == "superseded"
    assert graph.evidence[0].superseded_by == "E-0002"


def test_working_tree_audit_reports_arbitrary_untracked_files_without_failing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    init_repo(tmp_path)
    (tmp_path / "meeting-notes.md").write_text("Local notes.\n", encoding="utf-8")

    run_cli(tmp_path, "working-tree", "audit")
    report = json.loads(capsys.readouterr().out)

    assert report["blocking_findings"] == []
    assert report["untracked"] == [{"status": "??", "path": "meeting-notes.md"}]


def test_working_tree_audit_fails_for_configured_blocked_patterns(tmp_path: Path) -> None:
    init_repo(tmp_path)
    agentic = tmp_path / ".agentic"
    agentic.mkdir()
    (agentic / "workflow.toml").write_text(
        """
[working_tree]
blocked_patterns = ["generated/**"]
""",
        encoding="utf-8",
    )
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "artifact.txt").write_text("Generated delivery blocker.\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        run_cli(tmp_path, "working-tree", "audit")


def test_repo_wide_access_blocks_protected_codex_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_cli(tmp_path, "start", "--kind", "change", "--statement", "Maintain docs")
    run_cli(tmp_path, "set-access-mode", "repo-wide", "--reason", "Human-approved maintenance")

    output = run_hook(
        load_hook("guard_write_zone").main,
        apply_patch_payload(tmp_path, ".git/config"),
        monkeypatch,
    )

    assert "permissionDecision" in output
    assert "deny" in output
    assert ".git/config" in output


def test_guard_write_zone_handles_claude_multiedit_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_cli(tmp_path, "start", "--kind", "change", "--statement", "Maintain docs")
    run_cli(tmp_path, "set-access-mode", "repo-wide", "--reason", "Human-approved maintenance")

    output = run_hook(
        load_hook("guard_write_zone").main,
        file_edit_payload(tmp_path, "MultiEdit", "deploy/id_rsa"),
        monkeypatch,
    )

    assert "permissionDecision" in output
    assert "deny" in output
