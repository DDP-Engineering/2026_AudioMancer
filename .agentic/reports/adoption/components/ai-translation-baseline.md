<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AI Translation Adoption Baseline

Date: 2026-07-16

Baseline level: `baseline-usable`

AI Translation is one approved high-criticality component slice. Exact paths
are recorded in `.agentic/components.toml`; shared AI, configuration, export,
and downstream consumer files are in scope only when Translation-specific
contracts change.

Evidence supporting the baseline:

- active durable requirements cover translation generation, review, resume,
  atomic persistence, UI orchestration, and prompt preservation behavior;
- focused deterministic tests cover service output, operator instructions,
  same-language provider use, token budgeting, chunk-level resume, terminal
  cancellation/failure, page state, controller reset, and review actions;
- `05_SoftwareDocu/AudioMancer_AI_Translation_Service.md` documents the current
  component responsibilities, artifacts, and downstream gate;
- workflow traceability and coverage audits reported no issues on 2026-07-16;
- adoption changes are workflow metadata and documentation only.

Product changes are high risk because the translation artifact is resumable
paid AI output and the approval boundary controls downstream narrator,
character, speech, export, and audio workflows. Development must preserve
completed chunks across interruption, keep persistence atomic, fail explicitly
on incompatible data, and retain human approval before downstream trust.
