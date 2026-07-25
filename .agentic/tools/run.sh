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

# @brief Resolved interpreter command and any leading arguments.
# @details An array because a candidate may carry an argument (`py -3`).
PYTHON_CMD=()

# @brief Strip leading and trailing whitespace from one value.
# @details Matches the `.trim()` the Node and PowerShell launchers apply, so a
#          pointer file written with a trailing newline, or an `AEGIS_PYTHON`
#          holding only spaces, is treated identically everywhere. Interior
#          spaces are preserved: an interpreter path may legitimately contain
#          them.
trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

# @brief Directory holding the per-user WAEGIS runtime pointer.
# @details Mirrors `run_hook.mjs`: explicit `WAEGIS_HOME`, then the Windows
#          roaming profile, then the POSIX config directory. The Windows branch
#          matters because this script does run there — Git Bash is a bash on
#          Windows — and packaged WAEGIS registers its runtime under `APPDATA`.
#          Resolving only the POSIX path there silently missed the registered
#          interpreter and fell through to the system candidates.
waegis_home() {
  if [ -n "${WAEGIS_HOME:-}" ]; then
    printf '%s' "$WAEGIS_HOME"
  elif [ "${OS:-}" = "Windows_NT" ]; then
    printf '%s' "${APPDATA:-$HOME/AppData/Roaming}/waegis"
  else
    printf '%s' "$HOME/.config/waegis"
  fi
}

# @brief System launcher candidates, in order, one per line.
# @details The same ordered list as `run_hook.mjs` and `run.ps1`. On Windows
#          `py -3` must be tried before bare `python`: with no real interpreter
#          installed, `python` resolves to the Microsoft Store alias stub, which
#          launches, exits non-zero and writes nothing.
python_candidates() {
  if [ "${OS:-}" = "Windows_NT" ]; then
    printf '%s\n' "py -3" "python"
  else
    printf '%s\n' "python3" "python"
  fi
}

# @brief Resolve explicit, WAEGIS-registered, then system Python into PYTHON_CMD.
# @return Zero when an interpreter was resolved, non-zero when none is available.
resolve_python() {
  local explicit pointer registered candidate name
  explicit="$(trim "${AEGIS_PYTHON:-}")"
  if [ -n "$explicit" ]; then
    PYTHON_CMD=("$explicit")
    return 0
  fi
  pointer="$(waegis_home)/runtime-python"
  if [ -f "$pointer" ]; then
    IFS= read -r registered < "$pointer" || true
    registered="$(trim "${registered:-}")"
    # Packaged WAEGIS writes a native path, so on Windows the pointer holds a
    # backslash path (`C:\...\python.exe`). This script also runs under Git
    # Bash there, where `[ -f ]` and `exec` handle a forward-slash `C:/...`
    # path reliably but treat backslashes inconsistently. Folding them to `/`
    # is a no-op for a genuine POSIX path (which contains none) and removes the
    # ambiguity on Windows. The Node and PowerShell readers accept the native
    # form as-is, so only this wrapper needs the conversion.
    registered="${registered//\\//}"
    if [ -n "$registered" ] && [ -f "$registered" ]; then
      PYTHON_CMD=("$registered")
      return 0
    fi
  fi
  while IFS= read -r candidate; do
    name="${candidate%% *}"
    if command -v "$name" >/dev/null 2>&1; then
      # Intentional word split: a candidate may be "py -3".
      # shellcheck disable=SC2206
      PYTHON_CMD=($candidate)
      return 0
    fi
  done < <(python_candidates)
  return 1
}

if ! resolve_python; then
  echo "No AEGIS Python runtime is available. Run a packaged WAEGIS command or set AEGIS_PYTHON." >&2
  exit 2
fi

exec "${PYTHON_CMD[@]}" "$LAUNCHER" "$@"
