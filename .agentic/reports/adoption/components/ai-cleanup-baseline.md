<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AI Cleanup Adoption Baseline

Date: 2026-07-14

Baseline level: `baseline-usable`

AI Cleanup is a single approved high-criticality component slice. Exact paths
are recorded in `.agentic/components.toml`; shared AI/config files are in scope
only when cleanup-specific contracts change.

Evidence supporting the baseline:

- active durable requirements cover cleanup behavior, budgeting, provider JSON
  handling, persistence/resume, atomic writes, and UI integration;
- focused deterministic tests cover service output, prompt/schema handling,
  window budgets, interruption/resume, state projection, UI orchestration, and
  atomic cleanup artifacts;
- `05_SoftwareDocu/AudioMancer_AI_Cleanup_Service.md` documents existing
  responsibilities and contracts;
- workflow traceability and coverage audits reported no issues on 2026-07-14;
- adoption changes are workflow metadata and documentation only.

Product changes are high risk because a cleanup error can remove meaningful
book text. Development must retain source artifacts, use deterministic
validation and conservative removal, surface prominent warnings, and preserve
human review before downstream trust.
