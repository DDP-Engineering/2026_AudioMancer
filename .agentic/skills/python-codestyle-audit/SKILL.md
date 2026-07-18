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

1. Read `AGENTS.md` and the repository's Python style documentation, if present.
2. If a deterministic Python style audit exists, run it in changed-only mode.
   Common examples:

   ```powershell
   python 02_Tools/audits/audit_codestyle.py --changed-only
   ```

   Skip this command when the target repository does not provide it, and perform
   the manual review below instead.
3. Fix reported Python style issues directly when they are mechanical and within
   the approved change scope:
   - required module prologue or license header
   - module-level documentation tags required by the repository
   - meaningful section markers required by the repository
   - public or non-trivial callable docstrings
   - local version tags when the repository requires them
4. When changing callable implementation or documentation, update any
   repository-required callable-local version metadata.
5. When adding or removing a function, class, or documented nested helper,
   update any repository-required module-level version metadata.
6. Validate changed Python files with the repository's configured commands.
   Prefer focused commands first, for example:

   ```powershell
   python -m py_compile <changed_file.py>
   python -m pytest -q <targeted_tests>
   ```

   If the repository uses `uv`, prefer its documented command form.
7. Re-run the audit when one exists and report remaining issues.

Manual review checklist when no audit tool exists:

- changed Python files follow local naming, formatting, and import conventions
- public APIs and non-trivial helpers have useful docstrings where expected
- comments explain intent instead of restating code
- tests or validation evidence cover the changed behavior
- formatting tools were not run across unrelated files
