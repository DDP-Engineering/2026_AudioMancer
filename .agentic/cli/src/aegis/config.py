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
@details Provides reusable implementation behavior for the standalone AEGIS system.
@details Gate values (0.4.0, analysis-review follow-up) are normalized on
         load: a scalar ``[gates]`` string becomes a one-command list —
         previously ``test = "pytest"`` became ``list("pytest")`` and ran each
         character as its own command — and any non-string, non-string-list
         value exits with a message naming the offending key instead of
         surfacing later as a raw traceback.
@author Eng. Dan Dumitru Pasare
@date 2026-07-20
@version 0.4.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib

# DATA MODELS / TYPEDEFINITIONS


@dataclass
class WorkflowConfig:
    """
    @brief      Represent WorkflowConfig data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.3.0
    """
    # @brief Repository paths treated as implementation source roots.
    source_roots: list[str] = field(default_factory=lambda: ["src", "app", "lib"])

    # @brief Repository paths scanned for executable or manually cited tests.
    test_roots: list[str] = field(default_factory=lambda: ["tests", "test"])

    # @brief Markdown requirement-register roots used by traceability audits.
    requirement_roots: list[str] = field(default_factory=lambda: [".agentic/requirements"])

    # @brief Component documentation roots expected to track implementation changes.
    documentation_roots: list[str] = field(default_factory=lambda: [".agentic/knowledge/components"])

    # @brief Template file agents should follow when creating component docs.
    component_documentation_template: str = ".agentic/knowledge/components/component_template.md"

    # @brief Component manifest path used during existing-project adoption.
    component_manifest: str = ".agentic/components.toml"

    # @brief Default adoption completion level expected for usable components.
    adoption_default_completion_level: str = "baseline-usable"

    # @brief Whether adoption runs may group related components into bundles.
    adoption_allow_component_bundles: bool = True

    # @brief Maximum number of components allowed in one adoption bundle.
    adoption_max_bundle_components: int = 5

    # @brief Whether adoption work may include behavior changes by default.
    adoption_behavior_changes_allowed: bool = False

    # @brief Knowledge roots used by adoption and documentation workflows.
    knowledge_roots: list[str] = field(default_factory=lambda: [".agentic/knowledge"])

    # @brief Root path for adoption reports.
    adoption_report_root: str = ".agentic/reports/adoption"

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

    # @brief Named validation commands executed by `aegis gates run`.
    gate_commands: dict[str, list[str]] = field(default_factory=dict)

    # @brief Regular expressions treated as secret-like content during scans.
    secret_patterns: list[str] = field(default_factory=list)

    # @brief Git status path globs that should block delivery preflight.
    working_tree_blocked_patterns: list[str] = field(default_factory=list)

    # @brief Stage-to-path edit allowlists consumed by the write-zone hook.
    write_zones: dict[str, list[str]] = field(default_factory=dict)

    # @brief Whether intent-alignment stages should run after intake stages.
    alignment_enabled: bool = True

    # @brief Whether open questions force a pause decision during alignment.
    alignment_pause_on_open_questions: bool = True

    # @brief Minimum risk level that forces a pause decision during alignment.
    alignment_risk_threshold: str = "medium"

    # @brief Whether complete recommended responses let question-bearing alignment proceed.
    alignment_allow_recommended_responses: bool = True

    # @brief Planned-path globs that force a pause decision during alignment.
    alignment_protected_scope_patterns: list[str] = field(default_factory=list)


# HELPER FUNCTIONS


def _gate_command_list(name: str, value: object) -> list[str]:
    """
    @brief      Normalize one ``[gates]`` value into a list of command strings.
    @param[in]  name Gate key name, used in the error message.
    @param[in]  value Raw TOML value for the gate.
    @return     List of command strings (a scalar string becomes a one-item list).
    @details    Guards the most common hand-edit mistake: ``test = "pytest"``
                would otherwise become ``list("pytest")`` and run each character
                as its own command.
    @exception  SystemExit Raised when the value is neither a string nor a list
                of strings, naming the offending key.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.1.0
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise SystemExit(
        f".agentic/workflow.toml [gates] {name} must be a command string or a "
        "list of command strings."
    )


# PUBLIC API


def load_config(repo_root: Path) -> WorkflowConfig:
    """
    @brief      Load config workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.3.0
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
    adoption = data.get("adoption", {})
    components = data.get("components", {})
    knowledge = data.get("knowledge", {})
    reports = data.get("reports", {})
    alignment = data.get("alignment", {})

    return WorkflowConfig(
        # Root sections identify where the workflow should look for project
        # sources, tests, requirements, and documentation.
        source_roots=list(data.get("source", {}).get("roots", ["src", "app", "lib"])),
        test_roots=list(data.get("tests", {}).get("roots", ["tests", "test"])),
        requirement_roots=list(data.get("requirements", {}).get("roots", [".agentic/requirements"])),
        documentation_roots=list(documentation.get("roots", [".agentic/knowledge/components"])),
        component_documentation_template=str(
            documentation.get("component_template", ".agentic/knowledge/components/component_template.md")
        ),
        component_manifest=str(components.get("manifest", ".agentic/components.toml")),
        adoption_default_completion_level=str(adoption.get("default_completion_level", "baseline-usable")),
        adoption_allow_component_bundles=bool(adoption.get("allow_component_bundles", True)),
        adoption_max_bundle_components=int(adoption.get("max_bundle_components", 5)),
        adoption_behavior_changes_allowed=bool(adoption.get("behavior_changes_allowed", False)),
        knowledge_roots=list(knowledge.get("roots", [".agentic/knowledge"])),
        adoption_report_root=str(reports.get("adoption_root", ".agentic/reports/adoption")),

        # Traceability settings control linked-test resolution and which source
        # files must be covered by durable requirement rows or explicit waivers.
        traceability_language=str(traceability.get("language", "python")),
        source_extensions=list(traceability.get("source_extensions", [".py"])),
        coverable_roots=list(traceability.get("coverable_roots", data.get("source", {}).get("roots", ["src", "app", "lib"]))),
        coverable_exclude=list(traceability.get("coverable_exclude", ["__init__.py"])),
        test_file_patterns=list(traceability.get("test_file_patterns", ["test_*.py", "*_test.py"])),

        # Gate, secret, working-tree, and write-zone settings affect validation,
        # delivery preflight, and stage-specific edit permissions.
        gate_commands={key: _gate_command_list(key, value) for key, value in gates.items()},
        secret_patterns=list(data.get("secrets", {}).get("patterns", [])),
        working_tree_blocked_patterns=list(data.get("working_tree", {}).get("blocked_patterns", [])),
        write_zones={
            key: list(value)
            for key, value in data.get("write_zones", {}).items()
        },
        alignment_enabled=bool(alignment.get("enabled", True)),
        alignment_pause_on_open_questions=bool(alignment.get("pause_on_open_questions", True)),
        alignment_risk_threshold=str(alignment.get("risk_threshold", "medium")),
        alignment_allow_recommended_responses=bool(alignment.get("allow_recommended_responses", True)),
        alignment_protected_scope_patterns=list(alignment.get("protected_scope_patterns", [])),
    )


# END OF FILE
