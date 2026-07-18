#!/usr/bin/env bash
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0

set -euo pipefail

# @brief Directory containing this wrapper after transboarding.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# @brief Project-local Python launcher for the embedded workflow CLI.
LAUNCHER="$SCRIPT_DIR/run_aegis.py"

# @brief Resolve explicit, WAEGIS-registered, then system Python.
# @return Absolute path to a Python command, or a non-zero status when missing.
resolve_python() {
  if [ -n "${AEGIS_PYTHON:-}" ]; then
    printf '%s\n' "$AEGIS_PYTHON"
    return 0
  fi
  local waegis_home pointer registered
  waegis_home="${WAEGIS_HOME:-${HOME}/.config/waegis}"
  pointer="$waegis_home/runtime-python"
  if [ -f "$pointer" ]; then
    IFS= read -r registered < "$pointer" || true
    if [ -n "$registered" ] && [ -f "$registered" ]; then
      printf '%s\n' "$registered"
      return 0
    fi
  fi
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
  echo "No AEGIS Python runtime is available. Run a packaged WAEGIS command or set AEGIS_PYTHON." >&2
  exit 2
fi

exec "$PYTHON_BIN" "$LAUNCHER" "$@"
