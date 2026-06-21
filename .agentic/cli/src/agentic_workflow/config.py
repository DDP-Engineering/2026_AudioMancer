#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file config.py
@brief Configuration loading helpers for agentic workflow repositories.
@details Provides reusable implementation behavior for the standalone workflow template.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass
class WorkflowConfig:
    """
    @brief      Represent WorkflowConfig data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    # @brief Repository paths treated as implementation source roots.
    source_roots: list[str] = field(default_factory=lambda: ["src", "app", "lib"])

    # @brief Repository paths scanned for executable or manually cited tests.
    test_roots: list[str] = field(default_factory=lambda: ["tests", "test"])

    # @brief Markdown requirement-register roots used by traceability audits.
    requirement_roots: list[str] = field(default_factory=lambda: [".agentic/requirements"])

    # @brief Component documentation roots expected to track implementation changes.
    documentation_roots: list[str] = field(default_factory=lambda: ["05_SoftwareDocu"])

    # @brief Template file agents should follow when creating component docs.
    component_documentation_template: str = "05_SoftwareDocu/component_documentation_template.md"

    # @brief Source language used when resolving linked test identifiers.
    traceability_language: str = "python"

    # @brief Source file extensions included in coverage and impact scans.
    source_extensions: list[str] = field(default_factory=lambda: [".py"])

    # @brief Source roots where files require requirement coverage or waivers.
    coverable_roots: list[str] = field(default_factory=lambda: ["src", "app", "lib"])

    # @brief File names or glob patterns excluded from coverable-source scans.
    coverable_exclude: list[str] = field(default_factory=lambda: ["__init__.py"])

    # @brief Test filename globs used when discovering candidate test files.
    test_file_patterns: list[str] = field(default_factory=lambda: ["test_*.py", "*_test.py"])

    # @brief Named validation commands executed by `agentic-workflow gates run`.
    gate_commands: dict[str, list[str]] = field(default_factory=dict)

    # @brief Regular expressions treated as secret-like content during scans.
    secret_patterns: list[str] = field(default_factory=list)

    # @brief Git status path globs that should block delivery preflight.
    working_tree_blocked_patterns: list[str] = field(default_factory=list)

    # @brief Stage-to-path edit allowlists consumed by the write-zone hook.
    write_zones: dict[str, list[str]] = field(default_factory=dict)


def load_config(repo_root: Path) -> WorkflowConfig:
    """
    @brief      Load config workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    path = repo_root / ".agentic" / "workflow.toml"
    if not path.exists():
        return WorkflowConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    # Optional sections are split out before constructing the normalized config
    # so missing TOML blocks fall back to the same defaults as an absent file.
    gates = data.get("gates", {})
    traceability = data.get("traceability", {})
    documentation = data.get("documentation", {})

    return WorkflowConfig(
        # Root sections identify where the workflow should look for project
        # sources, tests, requirements, and documentation.
        source_roots=list(data.get("source", {}).get("roots", ["src", "app", "lib"])),
        test_roots=list(data.get("tests", {}).get("roots", ["tests", "test"])),
        requirement_roots=list(data.get("requirements", {}).get("roots", [".agentic/requirements"])),
        documentation_roots=list(documentation.get("roots", ["05_SoftwareDocu"])),
        component_documentation_template=str(
            documentation.get("component_template", "05_SoftwareDocu/component_documentation_template.md")
        ),

        # Traceability settings control linked-test resolution and which source
        # files must be covered by durable requirement rows or explicit waivers.
        traceability_language=str(traceability.get("language", "python")),
        source_extensions=list(traceability.get("source_extensions", [".py"])),
        coverable_roots=list(traceability.get("coverable_roots", data.get("source", {}).get("roots", ["src", "app", "lib"]))),
        coverable_exclude=list(traceability.get("coverable_exclude", ["__init__.py"])),
        test_file_patterns=list(traceability.get("test_file_patterns", ["test_*.py", "*_test.py"])),

        # Gate, secret, working-tree, and write-zone settings affect validation,
        # delivery preflight, and stage-specific edit permissions.
        gate_commands={key: list(value) for key, value in gates.items()},
        secret_patterns=list(data.get("secrets", {}).get("patterns", [])),
        working_tree_blocked_patterns=list(data.get("working_tree", {}).get("blocked_patterns", [])),
        write_zones={
            key: list(value)
            for key, value in data.get("write_zones", {}).items()
        },
    )
