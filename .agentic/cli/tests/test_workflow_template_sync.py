#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
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
from agentic_workflow.models import Graph
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


def test_next_enters_alignment_when_enabled(tmp_path: Path) -> None:
    run_cli(tmp_path, "start", "--kind", "feature", "--statement", "Add export")
    run_cli(tmp_path, "next")

    graph = load_graph(tmp_path)

    assert graph.stage == "alignment"


def test_next_skips_alignment_when_disabled(tmp_path: Path) -> None:
    agentic = tmp_path / ".agentic"
    agentic.mkdir()
    (agentic / "workflow.toml").write_text(
        """
[alignment]
enabled = false
""",
        encoding="utf-8",
    )

    run_cli(tmp_path, "start", "--kind", "feature", "--statement", "Add export")
    run_cli(tmp_path, "next")

    graph = load_graph(tmp_path)

    assert graph.stage == "requirement"


def test_alignment_records_graph_and_journal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(tmp_path, "start", "--kind", "feature", "--statement", "Add export")
    run_cli(tmp_path, "next")
    capsys.readouterr()
    run_cli(
        tmp_path,
        "alignment",
        "--source",
        "human prompt",
        "--understanding",
        "Add export support.",
        "--scope",
        "in: export command; out: billing changes",
        "--assumption",
        "CSV is acceptable.",
        "--acceptance",
        "Export command writes a CSV file.",
        "--question",
        "Should the first export be CSV or JSON?",
        "--recommended-response",
        "Use CSV because it matches the requested export workflow.",
        "--planned-path",
        "src/exporter.py",
        "--risk",
        "low",
        "--decision",
        "proceed",
        "--reason",
        "Question has a default response and risk is low.",
    )
    output = json.loads(capsys.readouterr().out)

    graph = load_graph(tmp_path)
    journal = tmp_path / ".agentic" / "runs" / graph.run_id / "journal.jsonl"
    events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]

    assert graph.alignment is not None
    assert graph.alignment.source == "human prompt"
    assert graph.alignment.recommended_responses == [
        "Use CSV because it matches the requested export workflow."
    ]
    assert output["decision"] == "proceed"
    assert events[-1]["event"] == "alignment.recorded"


def test_alignment_status_and_report_include_record(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(tmp_path, "start", "--kind", "feature", "--statement", "Add export")
    run_cli(tmp_path, "next")
    run_cli(
        tmp_path,
        "alignment",
        "--source",
        "ISSUE-1",
        "--understanding",
        "Add export support.",
        "--scope",
        "in: exporter",
        "--acceptance",
        "Exporter has a passing check.",
        "--risk",
        "low",
        "--decision",
        "proceed",
        "--reason",
        "Low risk.",
    )
    capsys.readouterr()

    run_cli(tmp_path, "status")
    status = json.loads(capsys.readouterr().out)
    run_cli(tmp_path, "report")
    report = capsys.readouterr().out

    assert status["alignment"]["source"] == "ISSUE-1"
    assert status["alignment"]["decision"] == "proceed"
    assert "## Intent Alignment" in report
    assert "Add export support." in report


def test_alignment_requires_pause_for_threshold_risk(tmp_path: Path) -> None:
    run_cli(tmp_path, "start", "--kind", "feature", "--statement", "Change auth")
    run_cli(tmp_path, "next")

    with pytest.raises(SystemExit, match="risk medium meets threshold medium"):
        run_cli(
            tmp_path,
            "alignment",
            "--source",
            "human prompt",
            "--understanding",
            "Change authentication behavior.",
            "--scope",
            "in: auth flow",
            "--acceptance",
            "Existing auth checks pass.",
            "--risk",
            "medium",
            "--decision",
            "proceed",
            "--reason",
            "Trying to proceed.",
        )


def test_old_graph_with_intake_triage_loads_as_alignment() -> None:
    graph = Graph.from_dict(
        {
            "run_id": "feature-1",
            "stage": "alignment",
            "intent": {
                "id": "I-0001",
                "kind": "feature",
                "statement": "Old graph",
            },
            "intake_triage": {
                "source": "old prompt",
                "understanding": "Old understanding.",
                "scope": ["in: exporter"],
                "assumptions": [],
                "acceptance": ["Exporter works."],
                "open_questions": [],
                "recommended_responses": [],
                "risk": "low",
                "decision": "proceed",
                "reason": "Old run data.",
            },
        }
    )

    assert graph.alignment is not None
    assert graph.alignment.source == "old prompt"


def test_adoption_stage_sequence_and_set_stage(tmp_path: Path) -> None:
    run_cli(tmp_path, "start", "--kind", "adoption", "--statement", "Adopt existing project")
    graph = load_graph(tmp_path)

    assert graph.stage == "adoption-intake"

    run_cli(tmp_path, "next")
    graph = load_graph(tmp_path)
    assert graph.stage == "adoption-alignment"

    run_cli(tmp_path, "set-stage", "repo-discovery", "--reason", "Human-approved discovery")
    graph = load_graph(tmp_path)

    assert graph.stage == "repo-discovery"
    assert graph.decisions[-1].chosen == "repo-discovery"


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


def test_guard_write_zone_handles_qwen_writefile_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_cli(tmp_path, "start", "--kind", "change", "--statement", "Maintain source")
    run_cli(tmp_path, "set-stage", "implementation", "--reason", "Testing Qwen write tool")

    output = run_hook(
        load_hook("guard_write_zone").main,
        file_edit_payload(tmp_path, "WriteFile", "src/app.py"),
        monkeypatch,
    )

    assert output == ""
