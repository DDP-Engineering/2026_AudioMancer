<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: adoption-delivery

Load this module only while in the `adoption-delivery` stage.

- Run read-only validation appropriate for adoption artifacts:
  `<workflow> status`, `<workflow> invariants`, `<workflow> audit traceability`,
  `<workflow> audit coverage`, and `<workflow> adoption baseline` when available.
- Inspect the diff for behavior changes. Any runtime behavior change is a blocker
  for adoption delivery.
- Summarize adopted components, map updates, evidence, baseline state, and
  follow-up adoption slices.
- Ask the human before commit, PR creation, push, or merge.
