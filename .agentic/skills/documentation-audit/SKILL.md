---
name: documentation-audit
description: Review changed implementation files against relevant component knowledge under `.agentic/knowledge/components`, updating broad README, overview, setup, or validation docs only when explicitly requested or when their scope changes.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# Documentation Audit

Use this workflow:

1. Read `AGENTS.md`, then run `<workflow> config validate --json` and
   `<workflow> config show --effective --json`. Report the effective write,
   protected-read/path, scope, secret, gate, coverage, and delivery modes and
   active rule counts; state the selected run when graph state is needed and
   distinguish AEGIS policy from external platform safety.
2. Read the repository's documentation/style guidance, if present.
3. If a deterministic documentation audit exists, run the target repository's
   audit entry point in changed-only mode. For example:

   ```powershell
   python tools/audit_docs.py --changed-only
   ```

   Use a broad/full documentation option only when the user asks for broad
   documentation maintenance or when the change affects repository scope,
   setup/run commands, validation workflow, operator workflow, release/delivery
   notes, or first-reader navigation. Skip the command when the target
   repository does not provide it, and perform the manual review below instead.
4. Inspect implementation files changed in the current work.
5. Update stale or missing component documentation directly:
   - `.agentic/knowledge/components/*.md` for new or materially changed components
   - `.agentic/knowledge/components/index.md` when adding or renaming component pages
6. Update broad documentation only when the change materially affects that
   document's scope:
   - root or package README files for repository scope, setup, run command,
     package entry point, or first-reader navigation changes
   - planning or overview documents for planning overview changes
   - testing or validation guides for setup, validation, or operator workflow
     changes
7. For new components or material component changes, also use
   `$write-component-documentation`.
8. Do not describe planned behavior as implemented. Mark limitations and future
   work explicitly.
9. Re-run the deterministic audit when one exists and report remaining warnings
   that require human judgment.

Manual review checklist when no audit tool exists:

- changed component behavior is reflected in the appropriate component document
- new components have a `.agentic/knowledge/components/*.md` page
- new component pages are listed in `.agentic/knowledge/components/index.md`
- broad README, overview, setup, and validation docs are reviewed only when
  explicitly requested or when their scope changes
- docs do not duplicate obsolete behavior from older implementations
