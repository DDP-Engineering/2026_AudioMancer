# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required for agentic-workflow.", file=sys.stderr)
        return 2

    project_root = Path(__file__).resolve().parents[2]
    cli_src = project_root / ".agentic" / "cli" / "src"
    if not cli_src.exists():
        print(f"Agentic workflow CLI source not found: {cli_src}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(cli_src))
    from agentic_workflow.cli import main as cli_main

    return cli_main(list(argv or sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
