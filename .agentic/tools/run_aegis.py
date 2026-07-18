#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file run_aegis.py
@brief Template launcher for the embedded agentic workflow CLI.
@details Bootstraps the embedded CLI from a generated project checkout.
@author Eng. Dan Dumitru Pasare
@date 2026-06-20
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

import sys
from pathlib import Path

# PUBLIC API


def main(argv: list[str] | None = None) -> int:
    """
    @brief      Run command-line entry point workflow behavior.
    @param[in]  argv Input value used by the workflow helper.
    @return     Result produced by the workflow helper.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-20
    @version    0.1.0
    """
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required for aegis.", file=sys.stderr)
        return 2

    project_root = Path(__file__).resolve().parents[2]
    cli_src = project_root / ".agentic" / "cli" / "src"
    if not cli_src.exists():
        print(f"Agentic workflow CLI source not found: {cli_src}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(cli_src))
    from aegis.cli import main as cli_main

    return cli_main(list(argv or sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())

# END OF FILE
