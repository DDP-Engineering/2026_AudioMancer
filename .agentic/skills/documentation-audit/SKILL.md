---
name: documentation-audit
description: Review changed implementation files against relevant component knowledge under `05_SoftwareDocu`, updating broad README, overview, setup, or validation docs only when explicitly requested or when their scope changes.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# Documentation Audit

Use this workflow:

1. Read `AGENTS.md` and the repository's documentation/style guidance, if
   present.
2. If a deterministic documentation audit exists, run it in changed-only mode.
   Common examples:

   ```powershell
   python 02_Tools/audits/audit_documentation.py --changed-only
   ```

   Use a broad/full documentation option only when the user asks for broad
   documentation maintenance or when the change affects repository scope,
   setup/run commands, validation workflow, operator workflow, release/delivery
   notes, or first-reader navigation. Skip the command when the target
   repository does not provide it, and perform the manual review below instead.
3. Inspect implementation files changed in the current work.
4. Update stale or missing component documentation directly:
   - `05_SoftwareDocu/*.md` for new or materially changed components
   - `05_SoftwareDocu/README.md` when adding or renaming component pages
5. Update broad documentation only when the change materially affects that
   document's scope:
   - root or package README files for repository scope, setup, run command,
     package entry point, or first-reader navigation changes
   - planning or overview documents for planning overview changes
   - testing or validation guides for setup, validation, or operator workflow
     changes
6. For new components or material component changes, also use
   `$write-component-documentation`.
7. Do not describe planned behavior as implemented. Mark limitations and future
   work explicitly.
8. Re-run the deterministic audit when one exists and report remaining warnings
   that require human judgment.

Manual review checklist when no audit tool exists:

- changed component behavior is reflected in the appropriate component document
- new components have a `05_SoftwareDocu/*.md` page
- new component pages are listed in `05_SoftwareDocu/README.md`
- broad README, overview, setup, and validation docs are reviewed only when
  explicitly requested or when their scope changes
- docs do not duplicate obsolete behavior from older implementations
