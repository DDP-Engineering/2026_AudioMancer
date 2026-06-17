<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Agentic Workflow Prompt Cheat Sheet

This is a human operator reference. Use these prompts in an agentic development
tool after the target repo has the workflow template installed. Replace text in
`<angle brackets>`.

The authoritative agent workflow rules live in `AGENTS.md`, `.agentic/`
configuration, and the platform skill/adaptor files. This cheat sheet provides
ready-to-use prompts for the human user; it does not define how the agent must
work.

In copied target projects, use `<workflow>` as the workflow command placeholder:

- Windows: `.\.agentic\tools\run.ps1`
- Ubuntu: `bash .agentic/tools/run.sh`
- Windows after optional install: `.\.agentic\.venv\Scripts\agentic-workflow.exe`
- Ubuntu after optional install: `.agentic/.venv/bin/agentic-workflow`

## Create A New Project From This Template

Use the helper script from the template repository:

```powershell
python 02_Tools\create_project_from_template.py D:\Path\To\NewProject
```

Or copy the contents of `template/` into the new project root manually. The
new project should receive:

- `.agentic/` workflow state, hooks, requirements, specs, and config.
- `.agentic/cli/` bundled Python CLI for the workflow.
- `.agentic/tools/` Windows and Bash scripts for local run/install.
- `.codex/` Codex config, hooks config, and bundled skills.
- `.claude/` Claude Code settings, hooks config, and thin skill wrappers.
- `AGENTS.md` repository workflow instructions.
- `CLAUDE.md` Claude Code adapter note that points back to `AGENTS.md`.
- `CHANGELOG.md` starter release/change log.
- `PROMPT_CHEATSHEET.md` human operator prompts for the copied workflow.
- `05_SoftwareDocu/` component documentation template and index.

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
`/agentic-delivery`, `/documentation-audit`,
`/write-component-documentation`, `/regression-traceability`, and
`/python-codestyle-audit`.

## Start A Feature

```text
Use the agentic development workflow.
Implement feature: <feature description>.
Before drafting requirements, run traceability and coverage audits, then map
impact for likely changed files.
Stop at each gate and wait for my approval.
```

More explicit:

```text
Use the agentic development workflow.
Start a feature run for: <feature description>.
At intake, inspect the repo and ask clarification questions if needed.
Do not create requirements, tests, or implementation yet.
Stop after the intake gate.
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
05_SoftwareDocu component-documentation update in the acceptance notes.
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
  in Claude Code and update 05_SoftwareDocu in the same change.
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

## Scope Advisory

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
- missing or stale 05_SoftwareDocu component documentation
- secrets or credential files
- mismatch between approved specs and implementation

Record validation evidence.
Stop after reporting whether delivery can be prepared.
```

## Delivery Gate

Prepare delivery only:

```text
Approved to run delivery preflight and generate the report.
Do not commit, push, or create a PR.
Run:
<workflow> registry sync
<workflow> registry audit
<workflow> delivery-preflight
<workflow> report

Run $documentation-audit or an equivalent manual documentation review before
delivery. Confirm new or materially changed components have matching
05_SoftwareDocu documentation.

Then inspect git status read-only.
Stop after reporting preflight result, report path, git status summary, and whether the change is ready for a human-approved commit.
```

## Component Documentation

Create or update component docs:

```text
Use $write-component-documentation.
Create or update the 05_SoftwareDocu component document for <component>.
Read the current implementation files first, follow
05_SoftwareDocu/component_documentation_template.md, update
05_SoftwareDocu/README.md if adding a new page, and do not describe planned
behavior as implemented.
```

Audit documentation:

```text
Use $documentation-audit.
Review the current implementation changes against README files,
05_SoftwareDocu component docs, planning/overview docs, and validation docs.
Run any repository documentation audit tool if present; otherwise perform the
manual review from the skill.
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

Prefer the copied project-local runner when `agentic-workflow` is not on PATH.
Use the matching local wrapper command wherever a prompt says `<workflow>`.

Common Windows examples:

```text
Use this command form for workflow operations:
.\.agentic\tools\run.ps1
```

```text
Use this command form for workflow operations after optional local install:
.\.agentic\.venv\Scripts\agentic-workflow.exe
```

Common Ubuntu examples:

```text
Use this command form for workflow operations:
bash .agentic/tools/run.sh
```

```text
Use this command form for workflow operations after optional local install:
.agentic/.venv/bin/agentic-workflow
```
