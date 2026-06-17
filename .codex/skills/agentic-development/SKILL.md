---
name: agentic-development
description: Manual agentic development workflow for implementing features, fixing bugs, or changing behavior with requirement/spec creation, clarification asks, red-before-green checks, implementation, validation, and evidence capture. Use when the user asks to implement a feature, fix a defect, change behavior, add tests for a planned change, or continue an agentic development run.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->


# Agentic Development

Use this skill to run a manual, gate-by-gate development workflow. The human
stays in control. Complete one stage, summarize evidence, and stop with exact
next prompt options.

## Ground Rules

- Treat `.agentic/workflow.toml` as the project-specific source of truth.
- Treat `.agentic/requirements/` as the durable project contract.
- Use `agentic-workflow` commands when available; otherwise use
  `python -m agentic_workflow`.
- Keep requirements/spec edits, check/test edits, source edits, validation, and
  delivery as separate manual gates.
- Use `$write-component-documentation` when a new component is created or when
  an existing component's behavior, contracts, responsibilities, data formats,
  dependencies, or workflow integration materially change.
- Use `$python-codestyle-audit` after Python implementation changes when the
  repository has Python style requirements or audit tooling.
- Do not skip red-before-green evidence for new or changed checks.
- Do not edit tests during implementation unless the human explicitly routes
  back to the check stage.
- Stop after each stage and report: stage, changed artifacts, evidence,
  invariant status, blockers, and suggested next prompts.

## Stage Procedure

1. Intake
   - Classify the request as `feature`, `fix`, or `change`.
   - Run `agentic-workflow start --kind <kind> --statement "<request>"` if no
     active run exists.
   - Run `agentic-workflow audit traceability` and `agentic-workflow audit coverage`
     to understand existing traceability debt.
   - Run `agentic-workflow impact <planned-files>` when likely files are known;
     otherwise inspect likely source areas and run impact after files are touched.
   - Inspect configured source/test/spec roots.
   - Ask clarification questions when behavior, scope, or acceptance criteria
     are ambiguous.
   - Report impacted existing requirements/tests and any uncovered modules.
   - Stop after the intent is clear.

2. Requirement
   - Create or update minimal spec items: one testable sentence, `behavior` or
     `property`, examples or thresholds.
   - Create or update durable requirement rows in `.agentic/requirements/`.
   - If the work creates or materially changes a component, include the
     expected component documentation update in the scope and acceptance notes.
   - New rows start as `Planned`; flip to `Active` only after linked checks pass.
   - Record each item with `agentic-workflow add-spec`.
   - Run `agentic-workflow invariants`.
   - Stop and ask the human to review the spec.

3. Check
   - Add tests/checks that cite spec IDs.
   - Also cite durable requirement IDs in test comments, docstrings, or names
     where practical.
   - For new components, include checks or review expectations that make the
     required `05_SoftwareDocu/` documentation visible before delivery.
   - Run the smallest relevant command and confirm new checks fail first.
   - Record checks with `agentic-workflow add-check`.
   - Record failing evidence with `agentic-workflow record-evidence --kind test-run --result fail --check-id <id>`.
   - Stop before source implementation.

4. Implementation
   - Edit only configured implementation/source roots.
   - Update required component documentation under `05_SoftwareDocu/` in the
     same change when component boundaries, contracts, or behavior change.
   - Use `$write-component-documentation` for new or materially changed
     components.
   - Run linked tests reported by impact analysis for changed files.
   - If impact reports untraced files, run full configured regression gates.
   - Run relevant checks until the new checks pass and prior checks remain green.
   - Record passing evidence with `agentic-workflow record-evidence --kind test-run --result pass --check-id <id>`.
   - Record touched paths with `agentic-workflow record-change`.
   - Stop for validation.

5. Validation
   - Run `agentic-workflow invariants`.
   - Run `agentic-workflow audit traceability`.
   - Run `agentic-workflow audit coverage`.
   - Run `$documentation-audit` or perform the same documentation review
     manually when the target repo has no documentation audit tooling.
   - Run `$python-codestyle-audit` when Python files changed and the target repo
     has applicable style rules.
   - Run `agentic-workflow impact` against the current Git working set and
     verify linked tests or full regression were run.
   - Run configured gates with `agentic-workflow gates run` when appropriate.
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
