<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AEGIS Prompt Cheat Sheet

This is a human operator flyer. Use these prompts in an agentic development tool
after the target repo has AEGIS installed. Replace text in
`<angle brackets>`.

The authoritative agent workflow rules live in `AGENTS.md`, `.agentic/`
configuration, and the platform skill/adaptor files. This cheat sheet provides
ready-to-use prompts for the human user; it is not an agentic delivery contract,
gate input, evidence source, or instruction hierarchy for the agent.

In copied target projects, use `<workflow>` as the workflow command placeholder:

- Windows: `.\.agentic\tools\run.ps1`
- Ubuntu: `bash .agentic/tools/run.sh`
- Windows after optional install: `.\.agentic\.venv\Scripts\aegis.exe`
- Ubuntu after optional install: `.agentic/.venv/bin/aegis`

## Create A New Project From This Template

Use the helper script from the template repository:

```powershell
python 02_Tools\create_project_from_template.py D:\Path\To\NewProject
```

Or copy the contents of `template/` into the new project root manually. The
new project should receive:

- `.agentic/` workflow state, hooks, requirements, documents, and config.
- `.agentic/cli/` bundled Python CLI for the workflow.
- `.agentic/tools/` Windows and Bash scripts for local run/install.
- `.agentic/skills/` shared, platform-neutral skill procedures.
- `.codex/` Codex config, hooks config, and thin skill adapters.
- `.claude/` Claude Code settings, hooks config, and thin skill adapters.
- `.pi/` Pi adapter and Pi package: a bridge extension plus a `pi.skills`
  manifest reusing `.agentic/skills/`.
- `AGENTS.md` repository workflow instructions.
- `CLAUDE.md` Claude Code adapter note that points back to `AGENTS.md`.
- `CHANGELOG.md` starter release/change log.
- `.agentic/documents/PROMPT_CHEATSHEET.md` human operator prompts for the copied workflow.
- `.agentic/knowledge/components/` component documentation template and index.

After copying, adjust `.agentic/workflow.toml` for the target repository's real
source roots, test roots, gate commands, write zones, and documentation roots.
The copied workflow can be run immediately with:

```powershell
.\.agentic\tools\run.ps1 --help
```

```bash
bash .agentic/tools/run.sh --help
```

For a project-local virtual environment, use:

```powershell
.\.agentic\tools\install.ps1
```

```bash
bash .agentic/tools/install.sh
```

Use this prompt in the new project:

```text
Use the agentic development workflow installed in this repository.
Read AGENTS.md and .agentic/workflow.toml.
Inspect the configured source, test, requirement, and documentation roots.
Tell me whether the workflow configuration matches this project and list any
paths or gate commands that need adjustment.
Do not edit files yet.
```

For Claude Code, open the copied project and let `CLAUDE.md` point the session
to `AGENTS.md`. Direct Claude skill invocations use `/agentic-development`,
`/agentic-adoption`, `/agentic-delivery`, `/documentation-audit`,
`/write-component-documentation`, `/regression-traceability`, and
`/python-codestyle-audit`.

For Pi, run `pi install ./.pi` and trust the project (Pi must be installed
beforehand). The same skills are invoked as `/skill:agentic-development`,
`/skill:agentic-adoption`, `/skill:agentic-delivery`,
`/skill:documentation-audit`, `/skill:write-component-documentation`,
`/skill:regression-traceability`, and `/skill:python-codestyle-audit`.

## Adopt An Existing Project

Start adoption mode:

```text
Use $agentic-adoption.
Adopt this existing project into the agentic workflow.
Rules:
- No application behavior changes during adoption.
- Start with adoption-intake and adoption-alignment, then repo-discovery and
  component-map before changing adoption artifacts.
- Default to one component at a time unless I approve a named bundle.
- Establish local scope before change for each component-adoption slice.
Stop after adoption-alignment and tell me the proposed scope, open questions,
recommended default responses, risk, and planned discovery path.
```

Approve the component map:

```text
The component map is approved.
Continue the adoption run to component-adoption for <component name>.
Keep the scope local to that component.
Do not change runtime behavior.
Stop after reporting adopted artifacts, baseline status, and remaining gaps.
```

Review adoption baseline:

```text
Continue to baseline-review.
Run:
<workflow> adoption baseline
<workflow> adoption component-status

Tell me which components are baseline-usable, which are blocked, and what
single-component adoption slice should run next.
Do not edit application behavior.
```

If a feature run is blocked by adoption:

```text
This feature touches <component/path>.
Before behavior-changing work, inspect .agentic/components.toml.
If the target component is below baseline-usable, stop the feature run and use
$agentic-adoption to propose the smallest component adoption slice needed to
unblock it.
Do not implement the feature until I approve the adoption result.
```

## Start A Feature

```text
Use the agentic development workflow.
Implement feature: <feature description>.
Before drafting requirements, complete Intent Alignment: record what you
understood, scope, assumptions, open questions with recommended default
responses, risk, decision, reason, and planned paths.
Then run traceability and coverage audits, and map impact for likely changed files.
If .agentic/components.toml exists, check whether the target component is
baseline-usable before behavior-changing work.
Stop at each gate and wait for my approval.
```

More explicit:

```text
Use the agentic development workflow.
Start a feature run for: <feature description>.
At intake, start the run. At alignment, inspect the repo, record understanding,
scope, assumptions, open questions with recommended default responses, risk,
decision, reason, and planned paths.
Do not create requirements, tests, or implementation yet.
Stop after the alignment gate.
```

## Start A Bug Fix

```text
Use the agentic development workflow.
Fix bug: <bug description>.
First determine whether an existing spec covers the expected behavior.
Run traceability audit, coverage audit, and impact analysis before editing code.
If yes, create a reproduction check first.
If no, draft the missing spec before creating the check.
Stop at each gate and wait for my approval.
```

## Requirement Gate

Ask the agentic assistant to draft requirements:

```text
Continue to the requirement gate.
Draft the minimal spec items for <feature or fix>.
Allowed spec tags are only behavior and property.
Use one testable sentence per spec item.
Also draft/update the durable requirement rows under .agentic/requirements/.
If this creates or materially changes a component, include the expected
.agentic/knowledge/components component-documentation update in the acceptance
notes.
New requirement rows start as Planned.
Do not implement anything.
Stop after showing me the drafted spec items for approval.
```

Approve requirements:

```text
The requirement spec is approved.
Record each accepted spec item into the active workflow graph using:
<workflow> add-spec
Then run status and invariants.
Do not implement anything.
Stop after reporting the expected missing-check invariant state.
```

Revise requirements:

```text
Revise the requirement spec.
Change <specific issue>.
Keep spec IDs stable unless a spec must be retired and replaced.
Do not implement anything.
Stop after showing the revised spec.
```

## Check Gate

```text
Approved. Continue to the check gate.
Create the minimal deterministic checks/tests for the accepted spec items.
Rules:
- Create tests/checks only.
- Do not edit source implementation.
- Each check must cite the spec ID it verifies.
- New checks must run red/failing before implementation.
Record each check and red evidence in the workflow graph.
Stop before implementation and report check IDs, red evidence IDs, and invariant status.
```

If a test looks wrong:

```text
Pause at the check gate.
Explain why <test/check> may not match the approved spec.
Suggest a revised check and wait for approval before editing it.
```

## Implementation Gate

```text
Approved. Continue to the implementation gate.
Implement only what is needed to make the red checks pass.
Rules:
- Edit source/docs/config files only as needed.
- If a new component is created or a component contract materially changes, use
  $write-component-documentation in Codex or `/write-component-documentation`
  in Claude Code and update `.agentic/knowledge/components` in the same change.
- Do not edit tests unless you stop and ask first.
- Run linked tests reported by impact analysis for changed files.
- If impact reports untraced coverable files, run full regression and author missing requirements/checks.
- Run the relevant tests until the new checks pass.
- Record touched paths and passing evidence in the workflow graph.
Stop after reporting artifacts changed, green evidence IDs, and invariant status.
```

If implementation needs a test change:

```text
Stop implementation.
Explain why the current check appears wrong or incomplete.
Route back to the check gate and propose the exact test revision.
Do not edit the test until I approve.
```

Command shape after approval:

```text
<workflow> set-stage check --reason "<why this test revision is approved>"
```

## Scope Advisory

Declare intentional extra roots when starting the run:

```text
<workflow> start --kind feature --statement "<feature>" --scope-hint generated/client --scope-hint tools/codegen
```

`--scope-hint` is repeatable and journaled. It extends the INV-5 advisory scope
for the new run, but does not relax write zones, protected-file controls, or
host permissions.

Accept intentional scope overflow:

```text
The scope advisory is accepted.
Record a decision that <paths> are intentional touched paths because <spec IDs/reason>.
Do not change source or tests.
Run status and invariants.
Stop after reporting the decision and invariant status.
```

Reject scope overflow:

```text
The scope advisory is not accepted.
Revert or revise the out-of-scope changes to stay within the approved scope.
Do not change requirements or tests unless you ask first.
Stop after reporting the revised diff and invariant status.
```

## Small Change / Docs-Only Recipe

Use this named light path for an approved low-risk maintenance change that does
not alter runtime behavior. It keeps the same evidence and delivery controls
without inventing feature requirements or tests that do not apply:

```text
Use the agentic development workflow for a small change / docs-only run.
Run:
<workflow> start --kind change --statement "<small change>"
<workflow> set-access-mode repo-wide --reason "Approved maintenance across <paths>"

Confirm the intent, exact paths, acceptance result, and that runtime behavior is
out of scope. Make only the approved edits, then run:
<workflow> record-change --id CU-0001 --path <changed-path> [--path <changed-path>]
<workflow> record-evidence --kind note --result pass --summary "<manual or automated verification>"
<workflow> delivery-preflight

Do not commit, push, create a PR, merge, publish, or deploy. Stop after reporting
the changed paths, verification, preflight result, and any remaining human step.
```

Use focused automated validation when the repository provides it. For a purely
textual change, a documented manual verification is acceptable; red-before-green
still applies whenever an executable behavior check is introduced or changed.

## Parallel Work Guidance

Use one Git worktree per active run. The current selector under
`.agentic/current_run` is worktree-local in practice but represents only one
active run, so two agents must not share the same worktree and mutate the same
workflow state concurrently. Automation should pin every invocation to its
dedicated worktree and run from that repository tree.

The ratified future design is
`AEGIS_Parallel_Branch_Merge_Simplification_Plan.md`. It introduces an optional
global `--run-id` override for automation; the current CLI does not expose that
flag yet. Until that plan is implemented, do not script `--run-id` against the
current CLI and do not add locking or multi-run state to one worktree.

## Validation Gate

```text
Approved. Continue to validation.
Do not edit files.
Run:
<workflow> invariants
<workflow> impact
<workflow> audit traceability
<workflow> audit coverage
<python> -m pytest -q

Also run $documentation-audit or perform the same manual documentation review
if the repository has no documentation audit tooling. Run $python-codestyle-audit
when Python files changed and the repository has Python style rules.

Then inspect the diff read-only for:
- scope creep
- weakened or deleted tests
- missing spec citations
- missing or stale `.agentic/knowledge/components` component documentation
- secrets or credential files
- mismatch between approved specs and implementation

Record validation evidence.
Stop after reporting whether delivery can be prepared.
```

If a failing validation entry is later proven external or stale:

```text
Record the passing rerun evidence, then run:
<workflow> supersede-evidence --id <old-evidence-id> --by <new-evidence-id> --reason "<why the old failure is non-blocking>"
```

## Delivery Gate

Prepare delivery only:

```text
Approved to run delivery preflight and generate the report.
Do not commit, push, or create a PR.
Run:
<workflow> registry sync
<workflow> registry audit
<workflow> working-tree audit
<workflow> delivery-preflight
<workflow> report

Run $documentation-audit or an equivalent manual documentation review before
delivery. Confirm new or materially changed components have matching
`.agentic/knowledge/components` documentation. Review broad README, overview,
setup, or validation docs only when this change affects their scope.

Then inspect git status read-only.
Stop after reporting preflight result, report path, git status summary, and whether the change is ready for a human-approved commit.
```

## Component Documentation

Create or update component docs:

```text
Use $write-component-documentation.
Create or update the `.agentic/knowledge/components` component document for
<component>.
Read the current implementation files first, follow
`.agentic/knowledge/components/component_template.md`, update
`.agentic/knowledge/components/index.md` if adding a new page, and do not
describe planned behavior as implemented.
```

Audit documentation:

```text
Use $documentation-audit.
Review current implementation changes against relevant
`.agentic/knowledge/components` component docs. Review broad README, overview,
setup, or validation docs only
when explicitly requested or when this change affects their scope. Run any
repository documentation audit tool in changed-only mode if present; otherwise
perform the manual review from the skill.
```

## Repo-Wide Maintenance Access

Enable broad maintenance access only when the task needs edits across normal
repo folders:

```text
Start or switch this workflow run to repo-wide access mode.
Reason: <why broad repo maintenance is needed>.
Scope: <folders or categories expected to change>.
Keep protected Git, secret, environment, and key files blocked.
```

Audit Python style:

```text
Use $python-codestyle-audit.
Review changed Python files against AGENTS.md and repository style docs. Run a
deterministic Python style audit if present; otherwise perform the manual review
from the skill and validate the changed files.
```

Approve commit:

```text
Approved for commit.
Stage the completed workflow change and create a commit with message:
<commit message>

Do not push or create a PR.
Stop after reporting the commit result and git status.
```

Approve PR:

```text
Approved to create a PR.
Before creating it, rerun delivery preflight and report.
If preflight passes, create the PR.
Stop after reporting the PR URL and final status.
```

## Resume Or Inspect A Run

```text
Use the agentic development workflow.
Inspect the active run with:
<workflow> status
<workflow> invariants

Tell me the current stage, blocking failures, and the next safe prompt.
Do not edit files.
```

## Park Or Abort

```text
Park this workflow run.
Do not edit files.
Summarize current stage, completed gates, open decisions, and the exact prompt I should use to resume later.
```

```text
Abort this workflow run.
Do not delete artifacts.
Record why the run is being aborted, summarize current state, and stop.
```

## Portable Command Reminder

Prefer the copied project-local runner when `aegis` is not on PATH.
Use the matching local wrapper command wherever a prompt says `<workflow>`.

Common Windows examples:

```text
Use this command form for workflow operations:
.\.agentic\tools\run.ps1
```

```text
Use this command form for workflow operations after optional local install:
.\.agentic\.venv\Scripts\aegis.exe
```

Common Ubuntu examples:

```text
Use this command form for workflow operations:
bash .agentic/tools/run.sh
```

```text
Use this command form for workflow operations after optional local install:
.agentic/.venv/bin/aegis
```
