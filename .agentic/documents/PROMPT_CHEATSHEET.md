<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt file for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AEGIS Prompt Cheat Sheet

This is a human operator flyer. Use these prompts in an agentic development tool
after the target repo has AEGIS installed. Replace text in
`<angle brackets>`.

**New here, or just want to run a change?** Go straight to
[The Development Workflow, Stage By Stage](#the-development-workflow-stage-by-stage) —
the seven prompts, in order, that carry one change from request to delivery.
Everything else on this sheet is reference.

The authoritative agent workflow rules live in `AGENTS.md`, `.agentic/`
configuration, and the platform skill/adaptor files. This cheat sheet provides
ready-to-use prompts for the human user; it is not an agentic delivery contract,
gate input, evidence source, or instruction hierarchy for the agent.

In copied target projects, use `<workflow>` as the workflow command placeholder:

- Windows: `.\.agentic\tools\run.ps1`
- Ubuntu: `bash .agentic/tools/run.sh`
- Windows after optional install: `.\.agentic\.venv\Scripts\aegis.exe`
- Ubuntu after optional install: `.agentic/.venv/bin/aegis`

## Mandatory Session Bootstrap

Begin every procedure below with this prompt:

```text
Before inspecting or changing repository files, run:
<workflow> config validate --json
<workflow> config show --effective --json
Report the effective write-access, protected-read/path, scope, secret, gate,
coverage, and delivery modes and active rule counts. State whether the run is
selected by this worktree or by an explicit --run-id. Treat AEGIS repository
policy as separate from external host, sandbox, approval, and OS safety.
Stop on any configuration or run-resolution error; do not infer defaults or
guess a run ID.
```

## The Development Workflow, Stage By Stage

This is the fast path: **one prompt per stage, given in order.** After the
bootstrap above, paste the prompt for the stage you are on, read what the agent
reports, and only then approve the move to the next stage. The agent advances;
you decide when it may.

The golden rule for every prompt below: **do one stage, then stop and wait for
me.** That single instruction is what keeps a human in control of an AI that
would otherwise run to the end on its own.

Seven stages, start to finish:

```text
Intake → Alignment → Requirement → Check → Implementation → Validation → Delivery
```

Each block gives you the plain prompt to paste and the signal that the stage is
done. The detailed rules for each gate — exact commands, edge cases, revisions —
are in the per-gate sections further down; this spine is the everyday path.

### Stage 1 — Intake · commit to what you are doing

```text
Use the agentic development workflow.
I want to <feature / fix / behavior change, in one or two sentences>.
Start a run at intake. Inspect the repository and run impact analysis for the
files this is likely to touch. Ask me any clarifying questions now.
Do not write requirements, tests, or code yet. Stop and summarize your
understanding for my approval.
```

Move on when: the agent has restated the request and you agree it understood you.

### Stage 2 — Alignment · prove it understood you

```text
Continue to Intent Alignment.
Record: your understanding of the request, what is in and out of scope, your
assumptions, the acceptance target (how we will know it works), any open
questions with your recommended answers, a risk level, and the paths you plan
to touch. Decide proceed or pause.
If risk is high, questions are still open, or a protected area is in scope,
pause for me rather than proceeding.
Stop after recording alignment and show me the result.
```

Move on when: alignment is recorded and any pause has been resolved by you.

### Stage 3 — Requirement · make it testable

```text
Continue to the requirement gate.
Draft the minimal spec items (one testable sentence each, tagged behavior or
property). Check existing requirements first and reuse or revise where one
already covers this. Record accepted specs into the workflow graph.
Do not write tests or code yet. Stop and show me the specs and the invariant
status for approval.
```

Move on when: you approve the specs and the workflow reports the expected
missing-check state.

### Stage 4 — Check · write the tests, and watch them fail

```text
Approved. Continue to the check gate.
Write the minimal tests for the accepted specs. Each test must cite the spec it
verifies, and cover the failure paths too — invalid input, boundaries, and the
error the behavior should produce — not only the happy path.
Run them and confirm the new tests fail first. Record each test and its failing
evidence.
Do not touch source yet. Stop and report the test IDs, the red evidence, and the
invariant status.
```

Move on when: the new tests exist, cite their specs, and are recorded failing.

### Stage 5 — Implementation · write only enough to pass

```text
Approved. Continue to implementation.
Write only the code needed to make the failing tests pass. Stay inside the
source area; do not edit the tests. If a test turns out to be wrong, stop and
ask me to route back to the check gate rather than changing it quietly.
Run the linked tests until the new ones pass and the existing ones stay green.
Record the changed paths and the passing evidence.
Stop and report what changed, the green evidence, and the invariant status.
```

Move on when: the new tests pass, nothing else regressed, and evidence is recorded.

### Stage 6 — Validation · audit the whole change

```text
Approved. Continue to validation. Do not edit files.
Run the invariants, traceability audit, coverage audit, impact analysis, and the
full test suite. Then read the diff and check for scope creep, weakened or
deleted tests, missing spec citations, secrets, and any mismatch between the
approved specs and what was built.
Record the validation evidence. Stop and tell me whether this is ready to
prepare for delivery.
```

Move on when: the audits are clean and you are satisfied reading the diff.

### Stage 7 — Delivery · the final gate

```text
Approved to run delivery preflight and generate the report.
Do not commit, push, or open a PR.
Run delivery-preflight and the report, then show me the git status.
Stop and tell me the preflight result, the report location, and whether this is
ready for a human-approved commit.
```

Move on when: preflight passes — then **you** commit, push, or open the PR. A
clean preflight means the work is ready, not that it is authorized. That last
decision is always yours.

---

The rest of this sheet is reference: deployment and adoption, the detailed
version of each gate, scope and maintenance access, and how to resume, park, or
inspect a run.

## Create A New Project From This Template

Use WAEGIS as the recommended deployment and lifecycle tool. WAEGIS is a
separate, stdlib-only package: it configures and deploys the AEGIS payload but
is not copied into the target repository.

Preview and deploy a new project:

```powershell
waegis new D:\Path\To\NewProject --dry-run
waegis new D:\Path\To\NewProject
```

Preview and deploy AEGIS into an existing repository:

```powershell
waegis adopt D:\Path\To\ExistingRepo --dry-run
waegis adopt D:\Path\To\ExistingRepo
```

After deployment, use `waegis doctor --repo <path>` to verify installation
health. Use `waegis configure`, `waegis repair`, and `waegis upgrade` for the
managed lifecycle. When running WAEGIS from a source checkout, use that
checkout's documented environment runner, for example `uv run waegis ...`.

The deployed AEGIS payload contains:

- `.agentic/` workflow state, hooks, requirements, documents, and config.
- `.agentic/cli/` bundled Python CLI for the workflow.
- `.agentic/tools/` Windows and Bash scripts for local run/install.
- `.agentic/skills/` shared, platform-neutral skill procedures.
- `.codex/` Codex config, hooks config, and thin skill adapters.
- `.claude/` Claude Code settings, hooks config, and thin skill adapters.
- `.pi/` Pi adapter and Pi package: a bridge extension plus a `pi.skills`
  manifest reusing `.agentic/skills/`.
- `.opencode/` OpenCode skills, commands, agents, and the local guard plugin,
  plus the root `opencode.json` configuration.
- `.qwen/` Qwen Code settings, commands, hooks, and thin skill adapters, plus
  the root `QWEN.md` adapter note.
- `AGENTS.md` repository workflow instructions.
- `CLAUDE.md` Claude Code adapter note that points back to `AGENTS.md`.
- `CHANGELOG.md` starter release/change log.
- `.agentic/documents/PROMPT_CHEATSHEET.md` human operator prompts for the copied workflow.
- `.agentic/knowledge/components/` component documentation template and index.

After deployment, adjust `.agentic/workflow.toml` for the target repository's
real structural roots. The shipped schema-version-2 policy is explicitly
unrestricted/disabled; opt into gates and guardrails only by selecting a
restrictive mode and providing its required rules.
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
Read AGENTS.md, then run config validate --json and
config show --effective --json.
Inspect the configured source, test, requirement, and documentation roots.
Report every effective restriction mode and active rule count, distinguishing
AEGIS repository policy from external platform safety.
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

For OpenCode, start `opencode` from the repository root. The configured AEGIS
agent loads the shared skills by name. Use `/workflow-status`,
`/workflow-preflight`, and `/workflow-report` in the TUI, or run the matching
`opencode run --command <command>` form from the shell.

For Qwen Code, start `qwen` from the repository root and trust the project.
Confirm that `AGENTS.md` is loaded with `/memory show`; the shared skills appear
in `/skills`. The same `/workflow-status`, `/workflow-preflight`, and
`/workflow-report` command prompts are available.

## Adopt An Existing Project

Start adoption mode:

```text
Use $agentic-adoption.
Adopt this existing project into the agentic workflow.
Rules:
- No application behavior changes during adoption.
- Start with adoption-intake, then Intent Alignment, then repo-discovery and
  component-map before changing adoption artifacts.
- Default to one component at a time unless I approve a named bundle.
- Establish local scope before change for each component-adoption slice.
Stop after adoption-alignment and tell me the proposed scope, assumptions,
open questions, recommended default responses, risk, and proceed/pause decision.
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
Before drafting requirements, run traceability and coverage audits, then map
impact for likely changed files.
Complete Intent Alignment with your understanding, scope, assumptions,
acceptance target, open questions with recommended responses, risk, and
proceed/pause decision.
If .agentic/components.toml exists, check whether the target component is
baseline-usable before behavior-changing work.
Stop at each gate and wait for my approval.
```

More explicit:

```text
Use the agentic development workflow.
Start a feature run for: <feature description>.
At intake, inspect the repo and ask clarification questions if needed.
Then continue to Intent Alignment and record what you understood before
drafting requirements.
Do not create requirements, tests, or implementation yet.
Stop after the alignment gate.
```

## Start A Bug Fix

```text
Use the agentic development workflow.
Fix bug: <bug description>.
First determine whether an existing spec covers the expected behavior.
Run traceability audit, coverage audit, and impact analysis before editing code.
Complete Intent Alignment before drafting or updating specs.
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
Run <workflow> requirement list --json before creating anything and identify
semantically related current snapshots.
Use <workflow> requirement create for a new behavioral contract and use the
returned UUID-backed ID. Use <workflow> requirement update for a revision of
the same contract, preserving its ID and replacing complete linked-test or
affected-path sets when associations change.
If this creates or materially changes a component, include the expected
.agentic/knowledge/components component-documentation update in the acceptance
notes.
New requirement snapshots start as Planned.
Do not implement anything.
Stop after showing me the drafted spec items and requirement command results
for approval.
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
for the new run, but does not relax configured stage write access, protected
paths, or host permissions.

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

Use one Git worktree per active run. The selector under
`.agentic/.workspace/state/current_run` is ignored and explicitly local to that
worktree, but represents only one active run. Two agents must not share the
same worktree and mutate the same workflow state concurrently. Never copy or
stage `.agentic/.workspace/`.

Graph-dependent commands accept `--run-id <existing-run-id>`. Use it when
automation must pin a run; explicit selection wins over the pointer and does
not rewrite it. Run automation from its dedicated worktree and do not add
locking, caches, or multi-run pointer state to one worktree.

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
<workflow> impact
<workflow> working-tree audit
<workflow> audit traceability
<workflow> audit coverage
<workflow> delivery-preflight
<workflow> report

Traceability and impact read canonical requirement TOML snapshots directly.
There is no registry synchronization, registry audit, or generated cache.

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
Honor only restrictions active in validated workflow.toml; repo-wide access
never bypasses configured protected paths or external platform safety.
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

If I provide <existing-run-id>, append --run-id <existing-run-id> to both
commands. Tell me whether selection is explicit or worktree-local, the current
stage, blocking failures, and the next safe prompt.
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
