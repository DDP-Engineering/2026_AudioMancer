<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: adoption-alignment

Load this module only while in the `adoption-alignment` stage.

- Record the structured understanding checkpoint with:
  `<workflow> alignment --source "<prompt-or-ticket>" --understanding "<one paragraph>" --scope "<adoption slice>" --acceptance "<criterion>" --risk low|medium|high --decision proceed|pause --reason "<reason>"`.
  Add repeatable `--assumption`, `--question`, and `--planned-path` values when
  applicable. For each question in an automated flow, add a matching
  `--recommended-response` with the answer the agent will assume.
- Use `decision proceed` only when the command accepts it under
  `.agentic/workflow.toml` policy. If policy requires `pause`, stop and ask the
  human to answer or approve the risk.
- Stop after alignment is recorded or skipped by config.
