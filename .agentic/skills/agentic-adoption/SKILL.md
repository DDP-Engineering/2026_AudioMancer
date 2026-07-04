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

Use this skill when the human asks to adopt an existing project into the
agentic workflow, map legacy components, review baseline status, or unblock a
feature run that touches a component below the configured adoption baseline.

No application behavior changes during adoption. Adoption work may update
workflow configuration, component maps, requirements, documentation, test
inventory, and baseline records, but it must not change runtime product
behavior unless the human stops adoption and starts a normal development run.

## Ground Rules

- Treat `.agentic/workflow.toml` as the project-specific source of truth.
- Treat `.agentic/components.toml` as the component map when present.
- Use `<workflow>` as the project-local workflow runner:
  `.\.agentic\tools\run.ps1` on Windows or `bash .agentic/tools/run.sh` on
  POSIX shells.
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
- Stop for human approval after the component-map gate before component
  adoption work continues.
- Stop if adoption reveals missing ownership, unclear scope, or a proposed
  behavior change.

## Stage Procedure

1. adoption-intake
   - Classify the request as existing-project adoption, component adoption, or
     feature work blocked by adoption.
   - Run `<workflow> start --kind adoption --statement "<request>"` if no
     active adoption run exists.
   - Read `AGENTS.md`, `.agentic/workflow.toml`, and existing adoption or
     component files when present.
   - Confirm the intended adoption slice. Default to one component.
   - If a bundle is requested, ask for explicit approval and record why the
     bundled components must be adopted together.
   - Run `<workflow> next` to enter `adoption-alignment` when alignment is
     enabled by `.agentic/workflow.toml`.
   - Stop with the current scope, uncertainties, and next prompt options.

2. adoption-alignment
   - Record the structured understanding checkpoint with:
     `<workflow> alignment --source "<prompt-or-ticket>" --understanding "<one paragraph>" --scope "<adoption slice>" --acceptance "<criterion>" --risk low|medium|high --decision proceed|pause --reason "<reason>"`.
     Add repeatable `--assumption`, `--question`, and `--planned-path` values
     when applicable. For each question in an automated flow, add a matching
     `--recommended-response` with the answer the agent will assume.
   - Use `decision proceed` only when the command accepts it under
     `.agentic/workflow.toml` policy. If policy requires `pause`, stop and ask
     the human to answer or approve the risk.
   - Stop after alignment is recorded or skipped by config.

3. repo-discovery
   - Inventory configured source roots, test roots, requirement registers,
     documentation roots, gate commands, and adapters.
   - Run `<workflow> audit traceability` and `<workflow> audit coverage` when
     the current configuration can support them.
   - Identify likely components, owners, boundaries, external dependencies,
     important entry points, and existing tests.
   - Do not rewrite application code while discovering.
   - Stop with the discovered repo shape and recommended component-map updates.

4. component-map
   - Create or update `.agentic/components.toml` with component names, paths,
     status, baseline notes, and approved bundles when applicable.
   - Use `<workflow> adoption component-status` and `<workflow> adoption baseline`
     to review the map when those commands are available.
   - Mark unknown or risky areas honestly instead of stretching a component
     boundary to make the map look complete.
   - Present the component map approval gate. Do not continue to
     component-adoption until the human approves the map or a specific slice.
   - Stop with the proposed map, unresolved questions, and exact approval
     prompt.

5. component-adoption
   - Work only inside the approved local component scope or approved bundle
     exception.
   - Run `<workflow> adoption scope-check <paths>` for planned touched paths
     when the component manifest is available.
   - Add or update component documentation, requirement links, known test
     commands, and adoption notes for the approved slice.
   - Preserve behavior. If implementation changes appear necessary, stop and
     ask to switch to an `agentic-development` run.
   - Record what was adopted and which gaps remain.

6. baseline-review
   - Run `<workflow> adoption baseline` when available.
   - Review whether each adopted component meets the configured baseline, such
     as documented ownership, mapped paths, known gates, and traceability.
   - Classify remaining gaps as blocking, follow-up, or accepted legacy risk.
   - If a future behavior-changing run targets a component below
     `baseline-usable`, stop and recommend a component adoption slice first.
   - Stop with baseline status and the next safe feature or adoption prompt.

7. adoption-delivery
   - Run read-only validation appropriate for adoption artifacts:
     `<workflow> status`, `<workflow> invariants`, `<workflow> audit traceability`,
     `<workflow> audit coverage`, and `<workflow> adoption baseline` when
     available.
   - Inspect the diff for behavior changes. Any runtime behavior change is a
     blocker for adoption delivery.
   - Summarize adopted components, map updates, evidence, baseline state, and
     follow-up adoption slices.
   - Ask the human before commit, PR creation, push, or merge.

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
