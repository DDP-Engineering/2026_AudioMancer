---
name: agentic-adoption
description: Existing-project adoption workflow for mapping repository components, establishing baseline status, and preparing safe agentic workflow use before feature, fix, or behavior-change work.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# Agentic Adoption

Use this skill when the human asks to adopt an existing project into the agentic
workflow, map legacy components, review baseline status, or unblock a feature run
that touches a component below the configured adoption baseline.

No application behavior changes during adoption. Adoption work may update
workflow configuration, component maps, requirements, documentation, test
inventory, and baseline records, but it must not change runtime product behavior
unless the human stops adoption and starts a normal development run.

This file is a thin router. Load only the reference module for the stage you are
in, so a session — including a fresh one resuming an existing run — carries just
the guidance that stage needs rather than the whole adoption workflow.

## Ground Rules

- Before repository inspection or edits, run `<workflow> config validate --json`
  and `<workflow> config show --effective --json`. Report the effective write,
  protected-read/path, scope, secret, gate, coverage, and delivery modes and
  active rule counts; state the selected run and distinguish AEGIS policy from
  external platform safety.
- Treat validated `.agentic/workflow.toml` as the only AEGIS repository-policy
  source; never infer fallback restrictions from language or adapter settings.
- Treat `.agentic/components.toml` as the component map when present.
- Use `<workflow>` in the modules as the project-local workflow runner:
  `.\.agentic\tools\run.ps1` on Windows or `bash .agentic/tools/run.sh` on POSIX
  shells.
- Before moving from `adoption-alignment` to discovery, record Intent Alignment
  with `<workflow> alignment`. If there are questions, include recommended
  responses that state what the agent will assume in an automated flow. If the
  decision is `pause`, stop in adoption-alignment and ask for human answers
  before discovery work.
- Keep adoption evidence factual. Distinguish discovered behavior from desired
  future behavior.
- Prefer one component at a time. The default adoption slice is a single
  component.
- Use an approved bundle exception only when the human explicitly approves a
  named bundle and the component map shows that the components move together.
- Establish local scope before change: identify the component, paths, tests,
  docs, requirements, and risks for the intended slice before editing any
  adoption artifacts.
- Stop for human approval after the component-map gate before component adoption
  work continues.
- Stop if adoption reveals missing ownership, unclear scope, or a proposed
  behavior change.

## Session Resume

When you continue an existing adoption run in a fresh session (a new agent with
no prior chat context), reconstruct state before acting:

1. Run the mandatory bootstrap (`<workflow> config validate --json` and
   `<workflow> config show --effective --json`).
2. Run `<workflow> resume` to load the current stage and computed next stage, the
   intent, and recorded alignment.
3. Review `.agentic/components.toml` and any adoption artifacts for the slice in
   progress.
4. Load the reference module for the reported stage and continue there. Do not
   redo earlier stages that already have approved artifacts unless the human
   routes back with `set-stage`.

## Stage Modules

The adoption required order is adoption-intake, adoption-alignment,
repo-discovery, component-map, component-adoption, baseline-review,
adoption-delivery. Load only the module for the current stage:

| Stage | Module |
| --- | --- |
| `adoption-intake` | `reference/adoption-intake.md` |
| `adoption-alignment` | `reference/adoption-alignment.md` |
| `repo-discovery` | `reference/repo-discovery.md` |
| `component-map` | `reference/component-map.md` |
| `component-adoption` | `reference/component-adoption.md` |
| `baseline-review` | `reference/baseline-review.md` |
| `adoption-delivery` | `reference/adoption-delivery.md` |

Each module lists the actions and the stop condition for that adoption stage.

## Required Gate Summary Format

End each adoption stage with:

```text
Stage: <adoption-intake|adoption-alignment|repo-discovery|component-map|component-adoption|baseline-review|adoption-delivery>
Adoption scope: <single component, approved bundle, or discovery scope>
Artifacts changed: <paths or none>
Behavior-change check: No application behavior changes during adoption / blocker found
Component map status: <missing|drafted|approved|updated>
Baseline status: <summary>
Evidence: <commands, outputs, or manual review notes>
Needs human: <questions or approval needed>
Next prompt options:
- Continue to <next adoption stage>
- Revise <specific adoption artifact>
- Switch to agentic-development for behavior-changing work
- Park or abort this adoption run
```
