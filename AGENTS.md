<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AGENTS.md

Guidance for Codex and other AI agents in this repository.

## Agentic Development Workflow

This repository uses a manual, human-steered agentic development workflow.
When the user asks to implement a feature, fix a bug, or change behavior:

1. Start or resume an `.agentic` run.
2. Complete the `alignment` Intent Alignment stage before requirement/spec work
   when enabled.
3. Complete only one workflow gate at a time.
4. Keep intent/spec, checks/tests, source implementation, validation, and
   delivery as separate steps.
5. Stop after each gate with a concise summary and next prompt options.

Use the project-local wrappers when available:

```text
.\.agentic\tools\run.ps1 <command>
bash .agentic/tools/run.sh <command>
```

If the workflow package is installed in the active environment, `aegis`
or `python -m aegis` may also be used.

Examples below use `<workflow>` for the selected project-local or installed
workflow command.

## Pi Adapter

Under [Pi](https://pi.dev), this `AGENTS.md` contract applies unchanged (Pi reads
it natively). The `.pi/` directory is a thin adapter that bridges Pi tool events
to the same `.agentic/hooks/` guards used by the Codex and Claude adapters, so
write-zone, secret, delivery-preflight, protected-read, and evidence rules hold
identically. `<workflow>` still means the project-local runner under
`.agentic/tools/`. Shared skills are invoked as `/skill:<name>` (for example
`/skill:agentic-development`). Project-local Pi resources load only after the
project is trusted; see `.pi/README.md`.

## OpenCode Adapter

Under [OpenCode](https://opencode.ai), this `AGENTS.md` contract applies
unchanged. The project root `opencode.json` points OpenCode at this file and the
workflow CLI reference, and sets the default primary agent to
`aegis` for TUI, `opencode run`, desktop, and GitHub Action usage.
The `.opencode/` directory provides that workflow agent, native skill wrappers,
command prompts, and a local plugin that bridges OpenCode tool events to the
same `.agentic/hooks/` guards used by the Codex, Claude Code, and Pi adapters.
`<workflow>` still means the project-local runner under `.agentic/tools/`.
Shared skills are loaded with OpenCode's native `skill` tool (for example
`agentic-development`). Start OpenCode from the repository root so the project
config, agent, skills, commands, and plugin load together; see
`.opencode/README.md`.

## Qwen Code Adapter

Under [Qwen Code](https://github.com/QwenLM/qwen-code), this `AGENTS.md` contract
applies unchanged. The `.qwen/settings.json` file sets `context.fileName` to
`["AGENTS.md", "QWEN.md"]` so `AGENTS.md` loads first and stays authoritative, and
its native `PreToolUse`/`PostToolUse` command hooks call the same `.agentic/hooks/`
guards used by the Codex, Claude Code, Pi, and OpenCode adapters, so write-zone,
secret, delivery-preflight, protected-read, and evidence rules hold identically.
`<workflow>` still means the project-local runner under `.agentic/tools/`. Shared
skills are model-invoked or selected from Qwen's `/skills` picker (for example
`agentic-development`), and `.qwen/commands/` exposes `/workflow-status`,
`/workflow-preflight`, and `/workflow-report`. Start Qwen Code from the repository
root so the project settings, skills, and commands load together, and trust the
project on first start; see `.qwen/README.md`.

## Durable Requirements Contract

- Long-lived requirements live under `.agentic/requirements/`, one Markdown
  register per requirement type.
- The active run graph under `.agentic/runs/` records one workflow run; the
  requirement registers describe durable project behavior.
- Every behavior change starts by checking impact against existing requirement
  rows before implementation code is written.
- New requirement rows start as `Planned` and become `Active` only when a
  linked test exists and passes, or when an explicit manual verification method
  is documented.
- Activate proven requirement rows with
  `<workflow> requirement activate --id <requirement-id> --linked-test <test-id> --verification "<method>"`
  instead of editing workflow ledgers by hand.
- Link each active requirement to exact test identifiers when practical.
- When adding or changing tests, cite relevant requirement IDs in comments,
  docstrings, or test names where practical.
- New source files under configured `coverable_roots` need a file-level
  requirement row naming the file in `Related Components` and a linked check,
  unless the file is listed in `.agentic/requirements/coverage_waivers.txt`.
- Waivers are a legacy baseline only. Remove stale waivers once a module is
  covered or deleted.

## Component Documentation Contract

- New software components require a new or updated component document under
  `.agentic/knowledge/components/`.
- Material changes to a component's behavior, contracts, responsibilities, data
  formats, dependencies, or workflow integration require updating the matching
  `.agentic/knowledge/components/*.md` document in the same change.
- Component documents must follow
  `.agentic/knowledge/components/component_template.md`.
- When adding a new component page, update
  `.agentic/knowledge/components/index.md` in the same change.
- Component documentation complements requirements and tests. It does not
  replace durable requirement rows or linked verification.

## Required Order

1. Intake: classify request and inspect likely implementation impact.
2. Intent Alignment: record understanding, scope, acceptance, risk, and open
   questions with recommended responses when automated flow is acceptable; pause
   when policy or risk requires human input.
3. Requirement: create or update minimal spec items and durable requirement rows.
4. Check: create checks/tests that cite spec/requirement IDs and fail first.
5. Implementation: edit source and required component documentation until
   checks pass.
6. Validation: run deterministic gates, documentation review, and read-only
   review.
7. Delivery: run preflight and ask before PR/push/merge.

## Safety Rules

- Do not commit secrets, tokens, keys, `.env` files, or credential stores.
- Do not weaken or delete tests to make implementation pass.
- Do not edit specs during implementation unless the human routes back to the
  requirement stage with `<workflow> set-stage requirement --reason "<reason>"`.
- Do not edit tests during implementation unless the human routes back to the
  check stage with `<workflow> set-stage check --reason "<reason>"`.
- If a late failing evidence entry is proven to be an environment, command, or
  operator issue, record the passing rerun and use
  `<workflow> supersede-evidence --id <old-evidence-id> --by <new-evidence-id> --reason "<reason>"`.
- Record Intent Alignment with
  `<workflow> alignment --source "<ref>" --understanding "<text>" --scope "<scope>" --acceptance "<criterion>" --risk low|medium|high --decision proceed|pause --reason "<reason>"`.
  When questions exist, include `--recommended-response "<answer to assume>"`
  for each question if automated continuation is acceptable. Use `proceed` only
  when `.agentic/workflow.toml` policy allows it; otherwise stop in alignment
  and ask for human answers or risk approval.
- Treat arbitrary untracked human files as advisory delivery context unless
  they match protected paths, configured working-tree blockers, or secret
  patterns.
- Do not push, create a PR, merge, or publish until delivery preflight passes
  and the human explicitly approves that action.
- Do not report work complete while `<workflow> audit traceability` or
  `<workflow> audit coverage` has blocking findings.

## Stage Stop Format

End each workflow gate with:

```text
Stage: <stage>
Artifacts changed: <paths or none>
Evidence: <ids and short results>
Invariant status: <pass/fail summary>
Needs human: <questions or approval needed>
Next prompt options:
- Continue to <next stage>
- Revise <specific artifact>
- Abort or park this run
```
