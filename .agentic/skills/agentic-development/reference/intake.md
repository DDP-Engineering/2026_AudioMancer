<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: Intake

Load this module only while in the `intake` stage.

- Classify the request as `feature`, `fix`, or `change`.
- Run `<workflow> start --kind <kind> --statement "<request>"` if no active run
  exists.
- For automation that must pin an existing run, pass `--run-id <existing-run-id>`
  to each graph-dependent command. Never copy
  `.agentic/.workspace/state/current_run` between worktrees or stage
  `.agentic/.workspace/`.
- Run `<workflow> audit traceability` and `<workflow> audit coverage` to
  understand existing traceability debt.
- Run `<workflow> impact <planned-files>` when likely files are known; otherwise
  inspect likely source areas and run impact after files are touched.
- Inspect configured source/test/spec roots.
- Ask clarification questions when behavior, scope, or acceptance criteria are
  ambiguous.
- Run `<workflow> next` to enter `alignment` when alignment is enabled by
  `.agentic/workflow.toml`.
- Stop after the intent is clear.
