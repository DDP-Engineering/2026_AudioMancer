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

Use this skill to run a manual, gate-by-gate development workflow. The human
stays in control. Complete one stage, summarize evidence, and stop with exact
next prompt options.

## Ground Rules

- Treat `.agentic/workflow.toml` as the project-specific source of truth.
- Treat `.agentic/requirements/` as the durable project contract.
- Use `<workflow>` in examples below as the project-local workflow runner:
  `.\.agentic\tools\run.ps1` on Windows or `bash .agentic/tools/run.sh` on
  POSIX shells. If the optional local install was run, the installed
  `.agentic/.venv` executable may also be used.
- Before any `add-spec` call, complete the Intent Alignment stage with
  `<workflow> alignment`. If there are questions, include recommended responses
  that state what the agent will assume in an automated flow. If the decision is
  `pause`, stop in alignment and ask for human answers before requirement work.
- Keep requirements/spec edits, check/test edits, source edits, validation, and
  delivery as separate manual gates.
- Use `$write-component-documentation` when a new component is created or when
  an existing component's behavior, contracts, responsibilities, data formats,
  dependencies, or workflow integration materially change.
- Before behavior-changing work, inspect `.agentic/components.toml` when it
  exists. If the target component is below `baseline-usable`, stop and ask the
  human to run `$agentic-adoption` or approve a component adoption slice before
  implementation.
- Use `$python-codestyle-audit` after Python implementation changes when the
  repository has Python style requirements or audit tooling.
- Do not skip red-before-green evidence for new or changed checks.
- Do not edit tests during implementation unless the human explicitly routes
  back to the check stage.
- Use `<workflow> set-stage <stage> --reason "<reason>"` for
  human-approved routing back to requirement or check gates.
- Use `<workflow> supersede-evidence --id <old-evidence-id> --by <new-evidence-id> --reason "<reason>"`
  when a later passing rerun proves a late failure was external or stale.
- Stop after each stage and report: stage, changed artifacts, evidence,
  invariant status, blockers, and suggested next prompts.

## Stage Procedure

1. Intake
   - Classify the request as `feature`, `fix`, or `change`.
   - Run `<workflow> start --kind <kind> --statement "<request>"` if no
     active run exists.
   - Run `<workflow> audit traceability` and `<workflow> audit coverage`
     to understand existing traceability debt.
   - Run `<workflow> impact <planned-files>` when likely files are known;
     otherwise inspect likely source areas and run impact after files are touched.
   - Inspect configured source/test/spec roots.
   - Ask clarification questions when behavior, scope, or acceptance criteria
     are ambiguous.
   - Run `<workflow> next` to enter `alignment` when alignment is enabled by
     `.agentic/workflow.toml`.
   - Stop after the intent is clear.

2. Intent Alignment
   - Record the structured understanding checkpoint with:
     `<workflow> alignment --source "<prompt-or-ticket>" --understanding "<one paragraph>" --scope "<in/out of scope>" --acceptance "<criterion>" --risk low|medium|high --decision proceed|pause --reason "<reason>"`.
     Add repeatable `--assumption`, `--question`, and `--planned-path` values
     when applicable. For each question in an automated flow, add a matching
     `--recommended-response` with the answer the agent will assume.
   - Use `decision proceed` only when the command accepts it under
     `.agentic/workflow.toml` policy. If policy requires `pause`, stop and ask
     the human to answer or approve the risk.
   - Report impacted existing requirements/tests and any uncovered modules.
   - Stop after alignment is recorded or skipped by config.

3. Requirement
   - Create or update minimal spec items: one testable sentence, `behavior` or
     `property`, examples or thresholds.
   - Create or update durable requirement rows in `.agentic/requirements/`.
   - If the work creates or materially changes a component, include the
     expected component documentation update in the scope and acceptance notes.
   - New rows start as `Planned`; flip to `Active` only after linked checks pass.
   - Record each item with `<workflow> add-spec`.
   - Run `<workflow> invariants`.
   - Stop and ask the human to review the spec.

4. Check
   - Add tests/checks that cite spec IDs.
   - Also cite durable requirement IDs in test comments, docstrings, or names
     where practical.
   - For new components, include checks or review expectations that make the
     required `.agentic/knowledge/components/` documentation visible before
     delivery.
   - Run the smallest relevant command and confirm new checks fail first.
   - Record checks with `<workflow> add-check`.
   - Record failing evidence with `<workflow> record-evidence --kind test-run --result fail --check-id <id>`.
   - Stop before source implementation.

5. Implementation
   - Edit only configured implementation/source roots.
   - Reconfirm local scope before change by checking mapped component paths
     against `.agentic/components.toml` when present.
   - Update required component documentation under
     `.agentic/knowledge/components/` in the same change when component
     boundaries, contracts, or behavior change.
   - Use `$write-component-documentation` for new or materially changed
     components.
   - Run linked tests reported by impact analysis for changed files.
   - If impact reports untraced files, run full configured regression gates.
   - Run relevant checks until the new checks pass and prior checks remain green.
   - Record passing evidence with `<workflow> record-evidence --kind test-run --result pass --check-id <id>`.
   - When a new requirement-linked check is green, activate the durable row with
     `<workflow> requirement activate --id <requirement-id> --linked-test <test-id> --verification "<method>"`.
   - Record touched paths with `<workflow> record-change`.
   - Stop for validation.

6. Validation
   - Run `<workflow> invariants`.
   - Run `<workflow> audit traceability`.
   - Run `<workflow> audit coverage`.
   - Run `$documentation-audit` or perform the same documentation review
     manually when the target repo has no documentation audit tooling.
   - Run `$python-codestyle-audit` when Python files changed and the target repo
     has applicable style rules.
   - Run `<workflow> impact` against the current Git working set and
     verify linked tests or full regression were run.
   - Run configured gates with `<workflow> gates run` when appropriate.
   - If a gate failure is caused by a wrong command or environment issue, rerun
     with the correct command, record the passing evidence, and supersede the
     stale failure with `<workflow> supersede-evidence`.
   - Inspect diff for scope creep, weakened assertions, missing traceability,
     and secrets.
   - Stop with a validation summary.

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
