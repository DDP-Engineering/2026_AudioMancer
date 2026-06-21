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
@details Provides reusable implementation behavior for the standalone workflow template.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Stage = Literal[
    "intake",
    "requirement",
    "check",
    "implementation",
    "validation",
    "delivery",
]

AccessMode = Literal["standard", "repo-wide"]

STAGES: list[Stage] = [
    "intake",
    "requirement",
    "check",
    "implementation",
    "validation",
    "delivery",
]


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


@dataclass
class Intent:
    """
    @brief      Represent Intent data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    id: str
    kind: Literal["feature", "fix", "change"]
    statement: str
    scope_hint: list[str] = field(default_factory=list)
    status: str = "draft"
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
    @date       2026-06-20
    @version    0.1.0
    """
    id: str
    touched_paths: list[str]
    evidence: list[str] = field(default_factory=list)


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
class Defect:
    """
    @brief      Represent Defect data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    id: str
    statement: str
    violates_spec: str | None = None
    reproduced_by: str | None = None
    status: str = "open"


@dataclass
class Graph:
    """
    @brief      Represent Graph data used by the workflow.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    run_id: str
    stage: Stage
    intent: Intent
    access_mode: AccessMode = "standard"
    spec_items: list[SpecItem] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    change_units: list[ChangeUnit] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    defects: list[Defect] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        @brief      Handle to dict workflow behavior.
        @return     Result produced by the workflow helper.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-20
        @version    0.1.0
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        """
        @brief      Handle from dict workflow behavior.
        @param[in]  data Input value used by the workflow helper.
        @return     Result produced by the workflow helper.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-20
        @version    0.1.0
        """
        return cls(
            run_id=data["run_id"],
            stage=data["stage"],
            intent=Intent(**data["intent"]),
            access_mode=data.get("access_mode", "standard"),
            spec_items=[SpecItem(**item) for item in data.get("spec_items", [])],
            checks=[Check(**item) for item in data.get("checks", [])],
            evidence=[Evidence(**item) for item in data.get("evidence", [])],
            change_units=[ChangeUnit(**item) for item in data.get("change_units", [])],
            decisions=[Decision(**item) for item in data.get("decisions", [])],
            defects=[Defect(**item) for item in data.get("defects", [])],
        )
