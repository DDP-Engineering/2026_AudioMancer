#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""Adapter parity tests for the embedded AudioMancer workflow sync."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
OPENCODE_DIR = REPO_ROOT / ".opencode"
QWEN_DIR = REPO_ROOT / ".qwen"
WORKFLOW_AGENT = "agentic-workflow"
SKILL_NAMES = (
    "agentic-adoption",
    "agentic-development",
    "agentic-delivery",
    "regression-traceability",
    "documentation-audit",
    "python-codestyle-audit",
    "write-component-documentation",
)
COMMAND_NAMES = ("workflow-status", "workflow-preflight", "workflow-report")


def test_opencode_default_agent_and_commands_are_synced() -> None:
    config = json.loads((REPO_ROOT / "opencode.json").read_text(encoding="utf-8"))
    agent = OPENCODE_DIR / "agents" / f"{WORKFLOW_AGENT}.md"

    assert config["default_agent"] == WORKFLOW_AGENT
    assert ".agentic/documents/CLI_API_REFERENCE.md" in config["instructions"]
    assert agent.exists()
    assert "mode: primary" in agent.read_text(encoding="utf-8")
    for name in COMMAND_NAMES:
        text = (OPENCODE_DIR / "commands" / f"{name}.md").read_text(encoding="utf-8")
        assert f"agent: {WORKFLOW_AGENT}" in text
        assert ".agentic/tools/run_agentic_workflow.py" in text


def test_opencode_skills_and_plugin_are_synced() -> None:
    plugin = (OPENCODE_DIR / "plugins" / "agentic-guard.mjs").read_text(encoding="utf-8")

    for name in SKILL_NAMES:
        wrapper = (OPENCODE_DIR / "skills" / name / "SKILL.md")
        assert wrapper.exists()
        assert f".agentic/skills/{name}/SKILL.md" in wrapper.read_text(encoding="utf-8")
    for hook_name in (
        "guard_write_zone.py",
        "secret_scan.py",
        "delivery_preflight.py",
        "post_tool_evidence.py",
    ):
        assert hook_name in plugin


def test_qwen_settings_commands_and_skills_are_synced() -> None:
    settings = json.loads((QWEN_DIR / "settings.json").read_text(encoding="utf-8"))
    file_names = settings["context"]["fileName"]

    assert file_names[0] == "AGENTS.md"
    assert "QWEN.md" in file_names
    assert "WriteFile" in json.dumps(settings["hooks"]["PreToolUse"])
    for name in COMMAND_NAMES:
        assert (QWEN_DIR / "commands" / f"{name}.md").exists()
    for name in SKILL_NAMES:
        wrapper = (QWEN_DIR / "skills" / name / "SKILL.md")
        assert wrapper.exists()
        assert f".agentic/skills/{name}/SKILL.md" in wrapper.read_text(encoding="utf-8")
