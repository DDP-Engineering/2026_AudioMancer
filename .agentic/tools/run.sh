#!/usr/bin/env bash
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

set -euo pipefail

# @brief Directory containing this wrapper after transboarding.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# @brief Project-local Python launcher for the embedded workflow CLI.
LAUNCHER="$SCRIPT_DIR/run_agentic_workflow.py"

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

PYTHON_BIN="$(resolve_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.11+ was not found. Install Python 3.11+ or install uv, then rerun this script." >&2
  exit 2
fi

exec "$PYTHON_BIN" "$LAUNCHER" "$@"
