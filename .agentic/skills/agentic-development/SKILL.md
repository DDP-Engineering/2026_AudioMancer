---
name: agentic-development
description: Manual agentic development workflow for implementing features, fixing bugs, or changing behavior with requirement/spec creation, clarification asks, red-before-green checks, implementation, validation, and evidence capture. Use when the user asks to implement a feature, fix a defect, change behavior, add tests for a planned change, or continue an agentic development run.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# Agentic Development

Run a manual, gate-by-gate development workflow. The human stays in control.
Complete one stage, summarize evidence, and stop with exact next prompt options.

This file is a thin router. Load only the reference module for the stage you are
in, so a session — including a fresh one resuming an existing run — carries just
the guidance that stage needs rather than the whole workflow.

## Ground Rules

- Before repository inspection or edits, run `<workflow> config validate --json`
  and `<workflow> config show --effective --json`. Report the effective write,
  protected-read/path, scope, secret, gate, coverage, and delivery modes and
  active rule counts. State the selected worktree run or explicit `--run-id`.
- Treat validated `.agentic/workflow.toml` as the only AEGIS repository-policy
  source. Do not infer defaults from code or adapters. External host safety and
  approval controls remain separate and always apply.
- Treat `.agentic/requirements/` as the durable project contract.
- Use `<workflow>` in the modules as the project-local workflow runner:
  `.\.agentic\tools\run.ps1` on Windows or `bash .agentic/tools/run.sh` on POSIX
  shells. If the optional local install was run, the installed `.agentic/.venv`
  executable may also be used.
- Before any `add-spec` call, complete the Intent Alignment stage with
  `<workflow> alignment`. If there are questions, include recommended responses
  that state what the agent will assume in an automated flow. If the decision is
  `pause`, stop in alignment and ask for human answers before requirement work.
- Keep requirements/spec edits, check/test edits, source edits, validation, and
  delivery as separate manual gates. Complete one gate at a time.
- Use `$write-component-documentation` when a new component is created or when an
  existing component's behavior, contracts, responsibilities, data formats,
  dependencies, or workflow integration materially change.
- Before behavior-changing work, inspect `.agentic/components.toml` when it
  exists. If the target component is below `baseline-usable`, stop and ask the
  human to run `$agentic-adoption` or approve a component adoption slice before
  implementation.
- Use `$python-codestyle-audit` after Python implementation changes when the
  repository has Python style requirements or audit tooling.
- Do not skip red-before-green evidence for new or changed checks.
- Do not edit tests during implementation unless the human explicitly routes back
  to the check stage.
- Use `<workflow> set-stage <stage> --reason "<reason>"` for human-approved
  routing back to requirement or check gates.
- Use `<workflow> supersede-evidence --id <old-evidence-id> --by <new-evidence-id> --reason "<reason>"`
  when a later passing rerun proves a late failure was external or stale.
- Stop after each stage and report using the stop format below.

## Session Resume

When you continue an existing run in a fresh session (a new agent with no prior
chat context), reconstruct state before acting:

1. Run the mandatory bootstrap (`<workflow> config validate --json` and
   `<workflow> config show --effective --json`).
2. Run `<workflow> resume` to load the current stage and computed next stage, the
   intent and recorded alignment, spec items, checks, recent evidence, and the
   run's cited requirements with their `spec_ref`.
3. Open each `spec_ref` file for the concrete data structures, interface formats,
   dialog text, and worked examples that pin the work.
4. Load the reference module for the reported stage and continue there. Do not
   redo earlier stages that already have recorded artifacts unless the human
   routes back with `set-stage`.

## Stage Modules

The seven-stage required order is Intake, Intent Alignment, Requirement, Check,
Implementation, Validation, Delivery. Load only the module for the current stage:

| Stage | Module |
| --- | --- |
| `intake` | `reference/intake.md` |
| `alignment` | `reference/alignment.md` |
| `requirement` | `reference/requirement.md` |
| `check` | `reference/check.md` |
| `implementation` | `reference/implementation.md` |
| `validation` | `reference/validation.md` |
| `delivery` | invoke the `agentic-delivery` skill |

Each module lists the actions and the stop condition for that stage. The
`requirement` module also carries the requirement-stage review checklist.

## Required Stop Format

End each stage with:

```text
Stage: <stage>
Artifacts changed: <paths or none>
Evidence: <ids and short results>
Invariant status: <pass/fail summary>
Traceability status: <audit/impact summary>
Documentation status: <component docs/audit summary>
Needs human: <questions or approval needed>
Next prompt options:
- Continue to <next stage>
- Revise <specific artifact>
- Abort or park this run
```
