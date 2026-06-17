# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

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

STAGES: list[Stage] = [
    "intake",
    "requirement",
    "check",
    "implementation",
    "validation",
    "delivery",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Intent:
    id: str
    kind: Literal["feature", "fix", "change"]
    statement: str
    scope_hint: list[str] = field(default_factory=list)
    status: str = "draft"
    created_at: str = field(default_factory=now_iso)


@dataclass
class SpecItem:
    id: str
    tag: Literal["behavior", "property"]
    statement: str
    status: Literal["proposed", "accepted", "realized", "retired"] = "proposed"
    examples: list[str] = field(default_factory=list)
    threshold: str | None = None


@dataclass
class Check:
    id: str
    level: str
    cites_spec: list[str]
    command: str | None = None
    path: str | None = None
    state: Literal["red", "green", "unknown"] = "unknown"
    red_evidence: str | None = None
    green_evidence: str | None = None


@dataclass
class Evidence:
    id: str
    kind: Literal["test-run", "diff", "scan", "gate", "decision", "note"]
    result: Literal["pass", "fail", "info"]
    summary: str
    command: str | None = None
    path: str | None = None
    stage: str | None = None
    created_at: str = field(default_factory=now_iso)


@dataclass
class ChangeUnit:
    id: str
    touched_paths: list[str]
    evidence: list[str] = field(default_factory=list)


@dataclass
class Decision:
    id: str
    question: str
    chosen: str
    rationale: str
    approver: str = "human"
    created_at: str = field(default_factory=now_iso)


@dataclass
class Defect:
    id: str
    statement: str
    violates_spec: str | None = None
    reproduced_by: str | None = None
    status: str = "open"


@dataclass
class Graph:
    run_id: str
    stage: Stage
    intent: Intent
    spec_items: list[SpecItem] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    change_units: list[ChangeUnit] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    defects: list[Defect] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        return cls(
            run_id=data["run_id"],
            stage=data["stage"],
            intent=Intent(**data["intent"]),
            spec_items=[SpecItem(**item) for item in data.get("spec_items", [])],
            checks=[Check(**item) for item in data.get("checks", [])],
            evidence=[Evidence(**item) for item in data.get("evidence", [])],
            change_units=[ChangeUnit(**item) for item in data.get("change_units", [])],
            decisions=[Decision(**item) for item in data.get("decisions", [])],
            defects=[Defect(**item) for item in data.get("defects", [])],
        )
