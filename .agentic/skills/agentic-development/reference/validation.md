<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: Validation

Load this module only while in the `validation` stage.

- Run `<workflow> verify run`. This performs impact selection, enabled build,
  typecheck, lint, test, and security gates, invariants, traceability, coverage,
  and working-tree review in deterministic order.
- Run `$documentation-audit` or perform the same documentation review manually
  when the target repo has no documentation audit tooling.
- Run `$python-codestyle-audit` when Python files changed and the target repo has
  applicable style rules.
- Review the generated validation summary, then perform the interpretive diff
  review. Deterministic verification always comes first.
- If evidence is stale, use `<workflow> evidence prepare supersede`, edit the
  generated form, and run `<workflow> evidence apply`.
- Inspect diff for scope creep, weakened assertions, missing traceability, and
  secrets.
- Stop with a validation summary.

After validation passes, delivery is a separate gate: invoke the
`agentic-delivery` skill for preflight, reports, commits, and PR/push/merge.
