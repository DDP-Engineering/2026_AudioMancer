---
name: agentic-delivery
description: Manual agentic delivery workflow for preparing a PR, creating a PR, publishing a branch, or finalizing an agentic development run. Use when the user asks to create PR, prepare PR, deliver the change, publish, push, merge, or produce the final report for an agentic workflow run.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# Agentic Delivery

Use this skill when the human asks to prepare delivery. Delivery never skips
the final preflight.

## Procedure

Use `<workflow>` as the project-local workflow runner: `.\.agentic\tools\run.ps1`
on Windows or `bash .agentic/tools/run.sh` on POSIX shells.

1. Run `<workflow> config validate --json` and
   `<workflow> config show --effective --json`. Report the effective write,
   protected-read/path, scope, secret, gate, coverage, and delivery modes and
   active rule counts; distinguish them from external platform safety.
2. Load the worktree-selected run with `<workflow> status`, or pin an existing
   run with `<workflow> status --run-id <existing-run-id>`. Report which
   selection is used and never stage `.agentic/.workspace/`.
3. Run `<workflow> impact` against the Git working set. Impact reads canonical
   requirement snapshots directly; no registry synchronization exists.
4. Run `<workflow> working-tree audit` and report untracked files as
   advisory context unless the audit reports blocking findings.
5. Run `<workflow> audit traceability`.
6. Run `<workflow> audit coverage`.
7. Run `$documentation-audit` or perform the same documentation review manually
   when the target repo has no documentation audit tooling.
   Treat broad README, overview, setup, and validation docs as opt-in or
   scope-triggered maintenance, not a default delivery blocker.
8. Confirm component documents under `.agentic/knowledge/components/` were
   added or updated for new or materially changed components.
9. Run `<workflow> delivery-preflight` with the same run selection.
10. If preflight fails, stop and report failed invariants or audit findings.
11. If preflight passes, run or refresh `<workflow> report` with the same run.
12. Run configured gates when `gates.mode = "enforce"`; report explicitly when
    gates are disabled.
13. Summarize the branch status, report path, gate results, traceability status,
   documentation status, and remaining risks.
14. Stage only explicit intended paths for commits or PRs; do not stage
   unrelated human notes, saved messages, meeting notes, or generated local
   artifacts unless the human explicitly includes them.
15. Ask the human for explicit approval before push, PR creation, merge, or any
   outward-facing action.

## Required Stop Format

```text
Delivery preflight: <pass/fail>
Report: <path>
Gate results: <summary>
Traceability status: <summary>
Documentation status: <summary>
Risks/open notes: <summary>
Approval needed: <exact action, e.g. create PR or push branch>
```
