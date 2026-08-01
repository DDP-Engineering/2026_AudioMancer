---
name: agentic-development
description: File-first AEGIS workflow for full feature, fix, and change runs across intake, alignment, requirement, design, check, implementation, validation, and delivery, plus proportional four-stage quick runs for small fixes and changes.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Agentic Development

For the purpose of the workflow and its vocabulary, read
`.agentic/documents/WHY_AEGIS.md` and `.agentic/documents/GLOSSARY.md` before
starting an unfamiliar run. Use `.agentic/documents/INVARIANTS.md` when
verification reports an `INV-*` result.

Use AEGIS as an eight-stage, file-first full lifecycle:

`intake → alignment → requirement → design → check → implementation → validation → delivery`

The human approves every transition. Host plan mode may support discussion but
does not replace the imported design or `stage close` approval journal.

## Bootstrap

1. Run `<workflow> config validate --json`.
2. Run `<workflow> config show --json`.
3. Start or resume:

   ```text
   <workflow> run start <feature|fix|change>
   <workflow> run start <fix|change> --quick
   <workflow> run resume
   ```

4. Open the returned artifact. Do not encode statements, paths, decisions, or
   evidence in CLI flags.

When the human describes a genuinely small fix, offer the route explicitly:
`small scope - suggest: aegis run start fix --quick`. A quick run is valid only
for `fix` and `change`, and its real lifecycle is intake, implementation,
validation, and delivery, with an explicit human close at every transition.

At intake close AEGIS journals alignment, requirement, design, and check as
`bypassed` by run type. Treat that as its own visible state, never as passed or
waived. The absent-stage invariants and audits report `not-applicable`; intake,
changed-path and evidence capture, enabled gates, secrets and working-tree
review, scope analysis, delivery reporting, and the four human closes remain
real. If scope grows, restart a full run and carry the recorded context forward.

For quick implementation, follow `<workflow> evidence prepare add`, apply the
manual-evidence form, and copy its CLI-minted active ID into the implementation
form's `linked_check_evidence` before `stage apply`. Do not invent or reuse a
superseded or other-stage evidence ID.

## Stage Lifecycle

For every stage:

```text
<workflow> stage prepare
# edit the generated TOML/Markdown
<workflow> stage apply
# show the imported state and request explicit human approval
<workflow> stage close
```

Use `stage add` for another atomic requirement or check in a full run. `stage apply` imports
the complete collection only after every file validates. Access changes and
human-approved earlier routing belong in the generated control section.

Load only the current reference:

| Stage | Reference |
| --- | --- |
| intake | `reference/intake.md` |
| alignment | `reference/alignment.md` |
| requirement | `reference/requirement.md` |
| design | `reference/design.md` |
| check | `reference/check.md` |
| implementation | `reference/implementation.md` |
| validation | `reference/validation.md` |
| delivery | `$agentic-delivery` |

## Non-Negotiable Rules

- Requirements define observable contracts; design owns internal structures,
  boundaries, algorithms, compatibility choices, and implementation sequence.
- A full fix needs a reproducing red check before implementation. For a quick
  fix, red-before-green is explicitly `not-applicable`, never passed.
- Record red and green check evidence through the configured external or managed
  path. Never invent IDs; AEGIS generates them.
- Do not edit check artifacts during implementation. Route back through a stage
  control form when the contract or check is wrong.
- Run deterministic verification before interpretive diff review.
- `stage close` at delivery completes AEGIS state only. It does not push,
  publish, merge, or create a pull request.
- For an eligible process blocker, offer the human the exact ID reported by
  `<workflow> waive list`. Only after explicit approval, record one run-local
  waiver with `<workflow> waive add <blocker-id> --reason "<reason>"`.
- Never treat a waiver as a pass. Preserve the failure as `WAIVED` with its
  reason and timestamp. Schema, graph, persistence-lock, and stale-update
  integrity failures are not waiver targets.
- Never treat a quick-run bypass as a waiver or a pass. Preserve `bypassed` in
  status, validation, and delivery reporting.

## Stop Format

```text
Stage: <stage>
Artifact: <path>
Imported revision: <number>
Evidence: <ids and results>
Blockers: <none or exact blockers>
Needs human: approve close, revise artifact, route earlier, add a recorded waiver for <blocker-id> where offered, or abort
Next command: <exact command>
```
