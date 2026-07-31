#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file waivers.py
@brief Exact-state blocker and waiver matching helpers.
@details Waivers remain honest failed results and become active only when their
         blocker identity and complete state-digest mapping still match.
"""

# IMPORTS

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .models import Graph, Waiver

# CONSTANTS

MISSING_FILE_DIGEST = "missing"
UNREADABLE_FILE_DIGEST = "unreadable"

# DATA MODELS / TYPEDEFINITIONS


@dataclass(frozen=True)
class Blocker:
    """
    @brief Identify one concrete process block and its current state.
    """

    id: str
    description: str
    state_digests: dict[str, str]


# PUBLIC API


def state_digests(namespace: str, payload: Any) -> dict[str, str]:
    """
    @brief Digest one JSON-compatible blocker state canonically.
    @param[in] namespace Stable name for the digested state.
    @param[in] payload JSON-compatible state whose ordering must not matter.
    @return One exact namespace-to-SHA-256 mapping.
    @exception TypeError If the payload is not JSON-compatible.
    @exception ValueError If the payload contains a non-finite number.
    """
    return {namespace: sha256(_canonical_json_bytes(payload)).hexdigest()}


def current_file_digest(path: Path) -> str:
    """
    @brief Return a file digest or a stable unavailable-state sentinel.
    @param[in] path File whose current bytes define blocker state.
    @return SHA-256 hex digest, ``missing``, or ``unreadable``.
    """
    try:
        if not path.is_file():
            return MISSING_FILE_DIGEST
        return sha256(path.read_bytes()).hexdigest()
    except OSError:
        return UNREADABLE_FILE_DIGEST


def active_waiver(graph: Graph, blocker: Blocker) -> Waiver | None:
    """
    @brief Find the newest waiver that exactly covers current blocker state.
    @param[in] graph Run-local graph carrying human approval records.
    @param[in] blocker Concrete blocker and its freshly computed state.
    @return Matching waiver, or ``None`` when absent or stale.
    """
    return next(
        (
            waiver
            for waiver in reversed(graph.waivers)
            if waiver.blocker_id == blocker.id
            and waiver.state_digests == blocker.state_digests
        ),
        None,
    )


def waiver_metadata(waiver: Waiver) -> dict[str, str]:
    """
    @brief Return public approval metadata without disguising blocker state.
    @param[in] waiver Active human-approved waiver.
    @return Stable report metadata.
    """
    return {
        "id": waiver.id,
        "reason": waiver.reason,
        "created_at": waiver.created_at,
        "approver": waiver.approver,
    }


def blocker_to_dict(blocker: Blocker, graph: Graph) -> dict[str, Any]:
    """
    @brief Serialize a blocker and conditionally expose active waiver metadata.
    @param[in] blocker Concrete current blocker.
    @param[in] graph Run-local graph carrying waiver records.
    @return Blocker mapping with waiver data only when exact state is covered.
    """
    payload: dict[str, Any] = {
        "id": blocker.id,
        "description": blocker.description,
        "state_digests": dict(blocker.state_digests),
    }
    waiver = active_waiver(graph, blocker)
    if waiver is not None:
        payload["waived"] = True
        payload["waiver"] = waiver_metadata(waiver)
    return payload


def red_before_green_blocker(
    graph: Graph,
    check_id: str,
    description: str = "red-before-green",
) -> Blocker:
    """
    @brief Build shared exact state for one red-before-green blocker.
    @param[in] graph Graph containing the check and active evidence.
    @param[in] check_id Concrete check identity.
    @param[in] description Human-readable blocker description.
    @return Digest-pinned ``red-before-green:<check-id>`` blocker.
    @details Check evidence identifiers and stage provenance are deliberately
             excluded. The same unchanged blocker therefore remains covered
             after lifecycle advancement, while definition, state, or active
             evidence changes make the waiver stale.
    """
    check = next((item for item in graph.checks if item.id == check_id), None)
    check_state: dict[str, Any] | None = None
    if check is not None:
        check_state = asdict(check)
        check_state["red_evidence"] = bool(check.red_evidence)
        check_state["green_evidence"] = bool(check.green_evidence)
    evidence_states: list[dict[str, Any]] = []
    for evidence in graph.evidence:
        if (
            evidence.status != "active"
            or evidence.check_id != check_id
            or evidence.result not in {"fail", "pass"}
        ):
            continue
        evidence_state = asdict(evidence)
        evidence_state.pop("id")
        evidence_state.pop("stage")
        evidence_states.append(evidence_state)
    evidence_states.sort(key=_canonical_json_bytes)
    blocker_id = f"red-before-green:{check_id}"
    return Blocker(
        id=blocker_id,
        description=description,
        state_digests=state_digests(
            blocker_id,
            {
                "check": check_state,
                "active_evidence": evidence_states,
            },
        ),
    )


# LOCAL HELPERS


def _canonical_json_bytes(payload: Any) -> bytes:
    """
    @brief Encode JSON-compatible state in a deterministic canonical form.
    @param[in] payload JSON-compatible value.
    @return Compact, key-sorted UTF-8 JSON bytes.
    """
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


# END OF FILE
