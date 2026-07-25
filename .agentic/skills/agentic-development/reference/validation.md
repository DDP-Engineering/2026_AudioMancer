<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: Validation

Load this module only while in the `validation` stage.

- Run `<workflow> invariants`.
- Run `<workflow> audit traceability`.
- Run `<workflow> audit coverage`.
- Run `$documentation-audit` or perform the same documentation review manually
  when the target repo has no documentation audit tooling.
- Run `$python-codestyle-audit` when Python files changed and the target repo has
  applicable style rules.
- Run `<workflow> impact` against the current Git working set and verify linked
  tests or full regression were run.
- Run configured gates with `<workflow> gates run` when appropriate.
- If a gate failure is caused by a wrong command or environment issue, rerun with
  the correct command, record the passing evidence, and supersede the stale
  failure with `<workflow> supersede-evidence`.
- Inspect diff for scope creep, weakened assertions, missing traceability, and
  secrets.
- Stop with a validation summary.

After validation passes, delivery is a separate gate: invoke the
`agentic-delivery` skill for preflight, reports, commits, and PR/push/merge.
