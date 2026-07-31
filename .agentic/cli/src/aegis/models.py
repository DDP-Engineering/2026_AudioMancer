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
@brief Data models used by the schema-version-3 workflow state graph.
@details Defines the authoritative full, quick, and adoption run graphs.
         Schema-version-2 graphs and legacy fields are rejected rather than
         migrated.
"""

# IMPORTS

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# DATA MODELS / TYPEDEFINITIONS

RunKind = Literal["feature", "fix", "change", "adoption"]
RunProfile = Literal["full", "quick"]

Stage = Literal[
    "intake",
    "alignment",
    "requirement",
    "design",
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
    "design",
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

QUICK_STAGES: list[Stage] = [
    "intake",
    "implementation",
    "validation",
    "delivery",
]

ALL_STAGES: list[Stage] = [*STAGES, *ADOPTION_STAGES]

# HELPER FUNCTIONS


def now_iso() -> str:
    """
    @brief      Return the current UTC time as a second-precision ISO 8601 string.
    @return     Timezone-aware ISO 8601 timestamp with microseconds stripped.
    @exception  None
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# DATA MODELS / TYPEDEFINITIONS


@dataclass
class Intent:
    """
    @brief      One captured run intent: kind, statement, and scope hints.
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
    @brief      One behavior or property specification item with acceptance state.
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
    @brief      One imported check definition, its command, and its red/green state.
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
    contract_variants: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    parity_targets: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    """
    @brief      One recorded evidence item (test run, diff, scan, gate, decision, or note).
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
    check_id: str | None = None
    gate_name: str | None = None
    exit_status: int | None = None
    output_log: str | None = None
    created_at: str = field(default_factory=now_iso)


@dataclass
class ChangeUnit:
    """
    @brief      One identified change unit and the repository paths it touches.
    """
    id: str
    touched_paths: list[str]


@dataclass
class Decision:
    """
    @brief      One human-approved decision record with question, choice, and rationale.
    """
    id: str
    question: str
    chosen: str
    rationale: str
    approver: str = "human"
    created_at: str = field(default_factory=now_iso)


@dataclass
class Waiver:
    """
    @brief Represent one human-approved, run-local blocker waiver.
    @details State digests pin the approval to the exact blocker inputs that
             were current when the CLI minted the record.
    """

    id: str
    blocker_id: str
    reason: str
    state_digests: dict[str, str]
    approver: Literal["human"] = "human"
    created_at: str = field(default_factory=now_iso)


@dataclass
class StageRecord:
    """
    @brief      Represent the authoritative imported state for one stage.
    @details    The captured interface policy applies to this prepared revision
                even when workspace configuration changes before import.
    """

    stage: Stage
    revision: int
    status: Literal["prepared", "applied", "closed"]
    retention: Literal["versioned", "latest", "discard"]
    check_execution: Literal["external", "managed"]
    digest: str = ""
    artifact: str = ""
    summary: str = ""
    unresolved_questions: list[str] = field(default_factory=list)
    requested_access_mode: str = ""
    access_rationale: str = ""
    route_to: str = ""
    route_rationale: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    prepared_at: str = field(default_factory=now_iso)
    applied_at: str | None = None
    closed_at: str | None = None


@dataclass
class SolutionDesign:
    """
    @brief      Represent one authoritative solution-design proposal.
    """

    revision: int
    status: Literal["proposed", "approved", "stale"]
    document_path: str
    document_digest: str
    requirement_digests: dict[str, str]
    selected_option: str
    open_questions: list[str] = field(default_factory=list)
    approval: Literal["none", "human", "stale"] = "none"
    proposed_at: str = field(default_factory=now_iso)
    approved_at: str | None = None


@dataclass
class Graph:
    """
    @brief      The complete schema-version-3 run state: stage, intent, and all
                accumulated specs, checks, evidence, decisions, and stage records.
    """
    run_id: str
    stage: Stage
    intent: Intent
    profile: RunProfile = "full"
    schema_version: int = 3
    access_mode: AccessMode = "standard"
    complete: bool = False
    alignment: IntentAlignment | None = None
    design: SolutionDesign | None = None
    spec_items: list[SpecItem] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    change_units: list[ChangeUnit] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    stage_records: dict[str, StageRecord] = field(default_factory=dict)
    waivers: list[Waiver] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        @brief      Serialize this graph to a JSON-compatible mapping.
        @return     Dataclass fields as a dict, with `profile` omitted when it
                    equals the "full" default and `waivers` omitted when empty.
        @exception  None
        """
        payload = asdict(self)
        if self.profile == "full":
            payload.pop("profile")
        if not self.waivers:
            payload.pop("waivers")
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        """
        @brief      Load one strict schema-version-3 graph mapping.
        @param[in]  data Candidate JSON-compatible graph mapping to validate and parse.
        @return     Parsed graph using only the current persisted contract.
        @exception  ValueError If the graph is not an exact schema-3 document.
        """
        required = {
            "run_id",
            "stage",
            "intent",
            "schema_version",
            "access_mode",
            "complete",
            "alignment",
            "design",
            "spec_items",
            "checks",
            "evidence",
            "change_units",
            "decisions",
            "stage_records",
        }
        allowed = {*required, "profile", "waivers"}
        if data.get("schema_version") != 3:
            raise ValueError(
                "unsupported run graph schema; AEGIS requires schema_version 3"
            )
        unknown = sorted(set(data) - allowed)
        missing = sorted(required - set(data))
        if unknown or missing:
            detail = (
                f"unknown keys: {', '.join(unknown)}"
                if unknown
                else f"missing keys: {', '.join(missing)}"
            )
            raise ValueError(f"invalid schema-3 run graph: {detail}")
        alignment = data["alignment"]
        design = data["design"]
        profile = data.get("profile", "full")
        if not isinstance(profile, str) or profile not in {"full", "quick"}:
            raise ValueError(
                "graph record does not match schema 3: "
                "profile must be full or quick"
            )
        waivers = data.get("waivers", [])
        if not isinstance(waivers, list):
            raise ValueError(
                "graph record does not match schema 3: waivers must be a list"
            )
        try:
            return cls(
                run_id=data["run_id"],
                stage=data["stage"],
                intent=Intent(**data["intent"]),
                profile=profile,
                schema_version=3,
                access_mode=data["access_mode"],
                complete=data["complete"],
                alignment=IntentAlignment(**alignment) if alignment else None,
                design=SolutionDesign(**design) if design else None,
                spec_items=[SpecItem(**item) for item in data["spec_items"]],
                checks=[Check(**item) for item in data["checks"]],
                evidence=[Evidence(**item) for item in data["evidence"]],
                change_units=[ChangeUnit(**item) for item in data["change_units"]],
                decisions=[Decision(**item) for item in data["decisions"]],
                stage_records={
                    name: StageRecord(**record)
                    for name, record in data["stage_records"].items()
                },
                waivers=[_waiver_from_dict(item) for item in waivers],
            )
        except TypeError as exc:
            # Nested records with unknown/missing keys otherwise surface as a
            # raw TypeError, escaping the strict-schema ValueError contract.
            raise ValueError(f"graph record does not match schema 3: {exc}") from exc


def _waiver_from_dict(data: Any) -> Waiver:
    """
    @brief Parse one closed-schema persisted waiver record.
    @param[in] data Candidate JSON-compatible waiver mapping.
    @return Validated waiver data model.
    @exception ValueError If keys, value types, or approval provenance differ.
    """
    required = {
        "id",
        "blocker_id",
        "reason",
        "state_digests",
        "approver",
        "created_at",
    }
    if not isinstance(data, dict):
        raise ValueError(
            "graph record does not match schema 3: waiver must be an object"
        )
    unknown = sorted(set(data) - required)
    missing = sorted(required - set(data))
    if unknown or missing:
        detail = (
            f"unknown keys: {', '.join(unknown)}"
            if unknown
            else f"missing keys: {', '.join(missing)}"
        )
        raise ValueError(
            f"graph record does not match schema 3: invalid waiver: {detail}"
        )
    for key in ("id", "blocker_id", "reason", "created_at"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(
                "graph record does not match schema 3: "
                f"waiver {key} must be a non-empty string"
            )
    digests = data["state_digests"]
    if not isinstance(digests, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in digests.items()
    ):
        raise ValueError(
            "graph record does not match schema 3: "
            "waiver state_digests must map strings to strings"
        )
    if data["approver"] != "human":
        raise ValueError(
            "graph record does not match schema 3: waiver approver must be human"
        )
    return Waiver(
        id=data["id"],
        blocker_id=data["blocker_id"],
        reason=data["reason"],
        state_digests=dict(digests),
        approver="human",
        created_at=data["created_at"],
    )


# END OF FILE
