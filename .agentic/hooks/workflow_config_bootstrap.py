#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file workflow_config_bootstrap.py
@brief Shared hook bootstrap for the canonical AEGIS configuration parser.
@details Locates the delivered `.agentic/cli/src` package without interpreting
         workflow policy, imports `aegis.config`, and exposes consistent typed
         errors to standalone hook processes.
"""

# IMPORTS

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

# PUBLIC API


def find_repository_root(start: Path | None = None) -> Path:
    """
    @brief      Find the nearest repository containing the delivered AEGIS CLI.
    @param[in]  start Starting directory; defaults to the process directory.
    @return     Repository root containing `.agentic/cli/src/aegis`.
    @exception  RuntimeError If the delivered parser package cannot be found.
    """
    candidate = (start or Path.cwd()).resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if (directory / ".agentic" / "cli" / "src" / "aegis").is_dir():
            return directory
    raise RuntimeError(
        "AEGIS hook bootstrap could not find .agentic/cli/src/aegis; "
        "run the hook from inside an installed AEGIS repository."
    )


def load_workflow_config(start: Path | None = None):  # type: ignore[no-untyped-def]
    """
    @brief      Import and invoke the canonical strict workflow parser.
    @param[in]  start Starting path used for repository discovery.
    @return     `aegis.config.WorkflowConfig` for the discovered repository.
    @exception  aegis.config.ConfigurationError If workflow.toml is invalid.
    @exception  RuntimeError If the delivered AEGIS package is unavailable.
    """
    repo_root = find_repository_root(start)
    source_root = repo_root / ".agentic" / "cli" / "src"
    source_text = str(source_root)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    from aegis.config import load_config

    return load_config(repo_root)


def configuration_error_payload(error: BaseException) -> dict[str, Any]:
    """
    @brief      Convert canonical configuration errors into hook-safe payloads.
    @param[in]  error Exception raised while loading workflow configuration.
    @return     Stable error mapping; unknown bootstrap failures are identified.
    """
    serializer = getattr(error, "to_dict", None)
    if callable(serializer):
        payload = serializer()
        if isinstance(payload, dict):
            return payload
    return {
        "code": "CONFIG-BOOTSTRAP-FAILED",
        "config_path": None,
        "key_path": "",
        "received": type(error).__name__,
        "expected": "the delivered canonical AEGIS configuration parser",
        "message": str(error),
        "remediation": (
            "Restore .agentic/cli/src/aegis and .agentic/workflow.toml, "
            "then run `aegis config validate`."
        ),
    }


def configuration_error_json(error: BaseException) -> str:
    """
    @brief      Render one hook-safe configuration error as JSON.
    @param[in]  error Configuration or bootstrap failure.
    @return     Deterministic JSON text.
    """
    return json.dumps(configuration_error_payload(error), sort_keys=True)


# END OF FILE
