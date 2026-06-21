#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file gates.py
@brief Gate execution helpers for workflow validation commands.
@details Provides reusable implementation behavior for the standalone workflow template.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from .config import load_config
from .models import Evidence
from .store import add_evidence, append_journal, load_graph, save_graph


def run_gates(repo_root: Path, names: list[str] | None = None, timeout: int = 300) -> int:
    """
    @brief      Run gates workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  names Input value used by the workflow helper.
    @param[in]  timeout Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    config = load_config(repo_root)
    graph = load_graph(repo_root)
    selected = names or list(config.gate_commands)
    if not selected:
        append_journal(repo_root, graph.run_id, "gates.skipped", {"reason": "no gates configured"})
        return 0

    exit_code = 0
    for name in selected:
        commands = config.gate_commands.get(name, [])
        for command in commands:
            result = _run_command(repo_root, command, timeout)
            evidence = Evidence(
                id=f"E-{len(graph.evidence) + 1:04d}",
                kind="gate",
                result="pass" if result.returncode == 0 else "fail",
                summary=f"{name}: {command}",
                command=command,
                stage=graph.stage,
            )
            graph = add_evidence(repo_root, graph, evidence)
            append_journal(
                repo_root,
                graph.run_id,
                "gate.output",
                {
                    "gate": name,
                    "command": command,
                    "returncode": result.returncode,
                    "stdout_tail": result.stdout[-4000:],
                    "stderr_tail": result.stderr[-4000:],
                },
            )
            if result.returncode != 0:
                exit_code = result.returncode
    save_graph(repo_root, graph)
    return exit_code


def _run_command(repo_root: Path, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    """
    @brief      Run command workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  command Input value used by the workflow helper.
    @param[in]  timeout Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    argv = _argv_for_simple_command(repo_root, command)
    if argv:
        return subprocess.run(
            argv,
            cwd=repo_root,
            shell=False,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    return subprocess.run(
        command,
        cwd=repo_root,
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _argv_for_simple_command(repo_root: Path, command: str) -> list[str] | None:
    """
    @brief      Handle argv for simple command workflow behavior.
    @param[in]  repo_root Input value used by the workflow helper.
    @param[in]  command Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    if any(token in command for token in ("&&", "||", "|", ">", "<", ";")):
        return None
    try:
        parts = [_strip_quotes(part) for part in shlex.split(command, posix=os.name != "nt")]
    except ValueError:
        return None
    if not parts:
        return None
    executable = Path(parts[0])
    if not executable.is_absolute() and any(sep in parts[0] for sep in ("/", "\\")):
        candidate = repo_root / executable
        if candidate.exists():
            parts[0] = str(candidate)
    return parts


def _strip_quotes(value: str) -> str:
    """
    @brief      Handle strip quotes workflow behavior.
    @param[in]  value Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
