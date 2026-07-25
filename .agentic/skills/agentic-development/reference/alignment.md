<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: Intent Alignment

Load this module only while in the `alignment` stage.

- Record the structured understanding checkpoint with:
  `<workflow> alignment --source "<prompt-or-ticket>" --understanding "<one paragraph>" --scope "<in/out of scope>" --acceptance "<criterion>" --risk low|medium|high --decision proceed|pause --reason "<reason>"`.
  Add repeatable `--assumption`, `--question`, and `--planned-path` values when
  applicable. For each question in an automated flow, add a matching
  `--recommended-response` with the answer the agent will assume.
- Enumerate acceptance criteria completely: pass `--acceptance` once per
  distinct, checkable outcome — success paths plus the failures and limits that
  define "done" — rather than one broad sentence. This list is the coverage
  checklist the requirement stage must satisfy one-to-one.
- Use `decision proceed` only when the command accepts it under
  `.agentic/workflow.toml` policy. If policy requires `pause`, stop and ask the
  human to answer or approve the risk.
- Report impacted existing requirements/tests and any uncovered modules.
- Stop after alignment is recorded or skipped by config.
