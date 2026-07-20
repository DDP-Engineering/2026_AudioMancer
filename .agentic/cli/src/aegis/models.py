#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file models.py
@brief Data models used by the agentic workflow state graph.
@details Defines the persisted run graph while preserving read compatibility
with legacy graphs that contain retired, unconsumed fields.
@author Eng. Dan Dumitru Pasare
@date 2026-07-20
@version 0.5.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# DATA MODELS / TYPEDEFINITIONS

RunKind = Literal["feature", "fix", "change", "adoption"]

Stage = Literal[
    "intake",
    "alignment",
    "requirement",
    "check",
    "implementation",
    "validation",
    "delivery",
    "adoption-intake",
    "adoption-alignment",
    "repo-discovery",
    "component-map",
    "component-adoption",
    "baseline-review",
    "adoption-delivery",
]

AccessMode = Literal["standard", "repo-wide"]
AlignmentRisk = Literal["low", "medium", "high"]
AlignmentDecision = Literal["proceed", "pause"]

# CONSTANTS

STAGES: list[Stage] = [
    "intake",
    "alignment",
    "requirement",
    "check",
    "implementation",
    "validation",
    "delivery",
]

ADOPTION_STAGES: list[Stage] = [
    "adoption-intake",
    "adoption-alignment",
    "repo-discovery",
    "component-map",
    "component-adoption",
    "baseline-review",
    "adoption-delivery",
]

ALL_STAGES: list[Stage] = [*STAGES, *ADOPTION_STAGES]

# HELPER FUNCTIONS


def now_iso() -> str:
    """
    @brief      Handle now iso workflow behavior.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# DATA MODELS / TYPEDEFINITIONS


@dataclass
class Intent:
    """
    @brief      Represent Intent data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.2.0
    """
    id: str
    kind: RunKind
    statement: str
    scope_hint: list[str] = field(default_factory=list)
    status: str = "draft"
    created_at: str = field(default_factory=now_iso)


@dataclass
class IntentAlignment:
    """
    @brief      Represent an intent-alignment record for a workflow run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-03
    @version    0.1.0
    """
    source: str
    understanding: str
    scope: list[str]
    assumptions: list[str]
    acceptance: list[str]
    open_questions: list[str]
    recommended_responses: list[str]
    risk: AlignmentRisk
    decision: AlignmentDecision
    reason: str
    planned_paths: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)


@dataclass
class SpecItem:
    """
    @brief      Represent SpecItem data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    id: str
    tag: Literal["behavior", "property"]
    statement: str
    status: Literal["proposed", "accepted", "realized", "retired"] = "proposed"
    examples: list[str] = field(default_factory=list)
    threshold: str | None = None


@dataclass
class Check:
    """
    @brief      Represent Check data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    id: str
    level: str
    cites_spec: list[str]
    cites_requirement: list[str] = field(default_factory=list)
    command: str | None = None
    path: str | None = None
    state: Literal["red", "green", "unknown"] = "unknown"
    red_evidence: str | None = None
    green_evidence: str | None = None


@dataclass
class Evidence:
    """
    @brief      Represent Evidence data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    id: str
    kind: Literal["test-run", "diff", "scan", "gate", "decision", "note"]
    result: Literal["pass", "fail", "info"]
    summary: str
    status: Literal["active", "superseded"] = "active"
    failure_kind: str | None = None
    superseded_by: str | None = None
    supersede_reason: str | None = None
    command: str | None = None
    path: str | None = None
    stage: str | None = None
    created_at: str = field(default_factory=now_iso)


@dataclass
class ChangeUnit:
    """
    @brief      Represent ChangeUnit data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.2.0
    """
    id: str
    touched_paths: list[str]


@dataclass
class Decision:
    """
    @brief      Represent Decision data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    id: str
    question: str
    chosen: str
    rationale: str
    approver: str = "human"
    created_at: str = field(default_factory=now_iso)


@dataclass
class Graph:
    """
    @brief      Represent Graph data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-20
    @version    0.5.0
    """
    run_id: str
    stage: Stage
    intent: Intent
    access_mode: AccessMode = "standard"
    alignment: IntentAlignment | None = None
    spec_items: list[SpecItem] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    change_units: list[ChangeUnit] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        @brief      Handle to dict workflow behavior.
        @return     Result produced by the workflow helper.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-20
        @version    0.3.0
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        """
        @brief      Load current and legacy graph mappings into the active model.
        @param[in]  data Input value used by the workflow helper.
        @return     Graph with retired top-level and change-unit fields ignored.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-20
        @version    0.3.0
        """
        alignment = data.get("alignment") or data.get("intake_triage")
        if alignment and "recommended_responses" not in alignment:
            alignment = {**alignment, "recommended_responses": []}
        return cls(
            run_id=data["run_id"],
            stage=data["stage"],
            intent=Intent(**data["intent"]),
            access_mode=data.get("access_mode", "standard"),
            alignment=IntentAlignment(**alignment) if alignment else None,
            spec_items=[SpecItem(**item) for item in data.get("spec_items", [])],
            checks=[Check(**item) for item in data.get("checks", [])],
            evidence=[Evidence(**item) for item in data.get("evidence", [])],
            change_units=[
                ChangeUnit(**{key: value for key, value in item.items() if key != "evidence"})
                for item in data.get("change_units", [])
            ],
            decisions=[Decision(**item) for item in data.get("decisions", [])],
        )


# END OF FILE
