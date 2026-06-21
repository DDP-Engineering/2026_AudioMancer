#!/usr/bin/env bash
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0

set -euo pipefail

# @brief Directory containing this installer after transboarding.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# @brief Root of the target repository after the template is transboarded.
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
# @brief Embedded CLI package installed by this helper.
CLI_ROOT="$PROJECT_ROOT/.agentic/cli"
# @brief Local virtual environment owned by the workflow template.
VENV_ROOT="$PROJECT_ROOT/.agentic/.venv"

# @brief Resolve a Python launcher available on PATH.
# @return Absolute path to a Python command, or a non-zero status when missing.
resolve_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  return 1
}

if command -v uv >/dev/null 2>&1; then
  uv venv --python 3.11 "$VENV_ROOT"
  uv pip install --python "$VENV_ROOT/bin/python" -e "$CLI_ROOT"
  exit 0
fi

PYTHON_BIN="$(resolve_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.11+ was not found. Install Python 3.11+ or install uv, then rerun this script." >&2
  exit 2
fi

"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || {
  echo "Python 3.11+ is required. Install Python 3.11+ or install uv, then rerun this script." >&2
  exit 2
}

"$PYTHON_BIN" -m venv "$VENV_ROOT"
"$VENV_ROOT/bin/python" -m pip install -e "$CLI_ROOT"
