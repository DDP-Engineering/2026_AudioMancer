#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file store.py
@brief Persistence helpers for agentic workflow run state.
@details Mirrors the packaged CLI implementation shipped into generated projects.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .models import AccessMode, Evidence, Graph, Intent, Stage, now_iso


AGENTIC_DIR = ".agentic"
RUNS_DIR = "runs"
CURRENT_RUN = "current_run"
GRAPH_FILE = "graph.json"
JOURNAL_FILE = "journal.jsonl"


def repo_root_from(path: Path | None = None) -> Path:
    """
    @brief      Resolve repo root from workflow behavior.
    @param[in]  path Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return (path or Path.cwd()).resolve()


def agentic_root(repo_root: Path) -> Path:
    """
    @brief      Resolve agentic root workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return repo_root / AGENTIC_DIR


def runs_root(repo_root: Path) -> Path:
    """
    @brief      Handle runs root workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return agentic_root(repo_root) / RUNS_DIR


def current_run_path(repo_root: Path) -> Path:
    """
    @brief      Resolve current run path workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return agentic_root(repo_root) / CURRENT_RUN


def new_run_id(kind: str) -> str:
    """
    @brief      Create new run id workflow behavior.
    @param[in]  kind Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return f"{kind}-{now_iso().replace(':', '').replace('+0000', 'Z')}-{uuid4().hex[:8]}"


def run_dir(repo_root: Path, run_id: str) -> Path:
    """
    @brief      Run dir workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return runs_root(repo_root) / run_id


def graph_path(repo_root: Path, run_id: str) -> Path:
    """
    @brief      Resolve graph path workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return run_dir(repo_root, run_id) / GRAPH_FILE


def journal_path(repo_root: Path, run_id: str) -> Path:
    """
    @brief      Resolve journal path workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    return run_dir(repo_root, run_id) / JOURNAL_FILE


def write_current_run(repo_root: Path, run_id: str) -> None:
    """
    @brief      Write current run workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    agentic_root(repo_root).mkdir(parents=True, exist_ok=True)
    current_run_path(repo_root).write_text(run_id, encoding="utf-8")


def read_current_run(repo_root: Path) -> str:
    """
    @brief      Read current run workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    path = current_run_path(repo_root)
    if not path.exists():
        raise SystemExit("No active agentic run. Start one with: agentic-workflow start")
    return path.read_text(encoding="utf-8").strip()


def init_graph(
    repo_root: Path,
    kind: str,
    statement: str,
    access_mode: AccessMode = "standard",
) -> Graph:
    """
    @brief      Handle init graph workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  kind Input value used by the workflow helper.
    @param[in]  statement Input value used by the workflow helper.
    @param[in]  access_mode Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    run_id = new_run_id(kind)
    graph = Graph(
        run_id=run_id,
        stage="intake",
        intent=Intent(id="I-0001", kind=kind, statement=statement),
        access_mode=access_mode,
    )
    run_dir(repo_root, run_id).mkdir(parents=True, exist_ok=True)
    save_graph(repo_root, graph)
    write_current_run(repo_root, run_id)
    append_journal(
        repo_root,
        run_id,
        "run.started",
        {"kind": kind, "statement": statement, "access_mode": access_mode},
    )
    return graph


def load_graph(repo_root: Path, run_id: str | None = None) -> Graph:
    """
    @brief      Load graph workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    active_id = run_id or read_current_run(repo_root)
    path = graph_path(repo_root, active_id)
    if not path.exists():
        raise SystemExit(f"Graph not found for run {active_id}")
    return Graph.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_graph(repo_root: Path, graph: Graph) -> None:
    """
    @brief      Save graph workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    path = graph_path(repo_root, graph.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(graph.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def append_journal(repo_root: Path, run_id: str, event: str, data: dict) -> None:
    """
    @brief      Append journal workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  run_id Input value used by the workflow helper.
    @param[in]  event Input value used by the workflow helper.
    @param[in]  data Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    path = journal_path(repo_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"time": now_iso(), "event": event, "data": data}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def add_evidence(repo_root: Path, graph: Graph, evidence: Evidence) -> Graph:
    """
    @brief      Add evidence workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  evidence Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    graph.evidence.append(evidence)
    save_graph(repo_root, graph)
    append_journal(repo_root, graph.run_id, "evidence.recorded", evidence.__dict__)
    return graph


def set_stage(repo_root: Path, graph: Graph, stage: Stage) -> Graph:
    """
    @brief      Set stage workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  stage Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    graph.stage = stage
    save_graph(repo_root, graph)
    append_journal(repo_root, graph.run_id, "stage.set", {"stage": stage})
    return graph


def set_access_mode(
    repo_root: Path,
    graph: Graph,
    access_mode: AccessMode,
    reason: str,
) -> Graph:
    """
    @brief      Set access mode workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  graph Input value used by the workflow helper.
    @param[in]  access_mode Input value used by the workflow helper.
    @param[in]  reason Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    graph.access_mode = access_mode
    save_graph(repo_root, graph)
    append_journal(
        repo_root,
        graph.run_id,
        "access_mode.set",
        {"access_mode": access_mode, "reason": reason},
    )
    return graph
