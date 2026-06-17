# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import load_config
from .models import Evidence
from .store import add_evidence, append_journal, load_graph, save_graph


def run_gates(repo_root: Path, names: list[str] | None = None, timeout: int = 300) -> int:
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
            result = subprocess.run(
                command,
                cwd=repo_root,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
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
