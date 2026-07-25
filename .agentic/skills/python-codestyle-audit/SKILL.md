---
name: python-codestyle-audit
description: Review and update Python code style for repositories using AEGIS, including module prologues, documentation comments, public callable docstrings, and local style rules. Use after Python implementation changes or before delivery when Python files changed.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# Python Code Style Audit

Use this workflow:

1. Read `AGENTS.md`, then run `<workflow> config validate --json` and
   `<workflow> config show --effective --json`. Report the effective write,
   protected-read/path, scope, secret, gate, coverage, and delivery modes and
   active rule counts; state the selected run when graph state is needed and
   distinguish AEGIS policy from external platform safety.
2. Read the repository's Python style documentation, if present.
3. If a deterministic Python style audit exists, run the target repository's
   audit entry point in changed-only mode. For example:

   ```powershell
   python tools/audit_python_style.py --changed-only
   ```

   Skip this command when the target repository does not provide it, and perform
   the manual review below instead.
4. Fix reported Python style issues directly when they are mechanical and within
   the approved change scope:
   - required module prologue or license header
   - module-level documentation tags required by the repository
   - meaningful section markers required by the repository
   - public or non-trivial callable docstrings
   - local version tags when the repository requires them
5. When changing callable implementation or documentation, update any
   repository-required callable-local version metadata.
6. When adding or removing a function, class, or documented nested helper,
   update any repository-required module-level version metadata.
7. Validate changed Python files with the repository's configured commands.
   Prefer focused commands first, for example:

   ```powershell
   python -m py_compile <changed_file.py>
   python -m pytest -q <targeted_tests>
   ```

   If the repository uses `uv`, prefer its documented command form.
8. Re-run the audit when one exists and report remaining issues.

Manual review checklist when no audit tool exists:

- changed Python files follow local naming, formatting, and import conventions
- public APIs and non-trivial helpers have useful docstrings where expected
- comments explain intent instead of restating code
- tests or validation evidence cover the changed behavior
- formatting tools were not run across unrelated files
