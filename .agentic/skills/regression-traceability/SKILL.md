---
name: regression-traceability
description: Audit durable requirements traceability, map changed files to existing requirements and linked tests, detect uncovered modules, manage coverage waivers, and decide focused versus full regression. Use when starting a new feature or bug fix in a repo with prior workflow history, changing existing files, reviewing regression risk, or preparing delivery.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# Regression Traceability

Use this skill to preserve old behavior before changing code.

This skill audits requirements and regression risk. Component documentation in
`05_SoftwareDocu/` complements this process, but it does not replace durable
requirement rows, linked tests, or explicit manual verification.

## Procedure

1. Read `AGENTS.md`, `.agentic/workflow.toml`, and
   `.agentic/requirements/README.md`.
2. Run:

   ```powershell
   .\.agentic\tools\run.ps1 audit traceability
   .\.agentic\tools\run.ps1 audit coverage
   ```

3. If planned or changed files are known, run:

   ```powershell
   .\.agentic\tools\run.ps1 impact <files>
   ```

   If not known, run impact after the first scoped file list is available.
4. Treat impacted requirement rows as existing contracts. Do not change them
   unless the human approves a requirement revision.
5. Run linked tests reported by impact analysis. If impact reports untraced
   coverable files, run full regression and author missing requirements/checks.
6. For pre-existing legacy files, add waivers only with human approval and keep
   them in `.agentic/requirements/coverage_waivers.txt`.
7. Before delivery, run registry sync/audit and both traceability audits.

Report impacted requirements, linked tests, untraced files, waivers touched,
commands run, and remaining audit findings.
