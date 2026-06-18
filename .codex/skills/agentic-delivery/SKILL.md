---
name: agentic-delivery
description: Manual agentic delivery workflow for preparing a PR, creating a PR, publishing a branch, or finalizing an agentic development run. Use when the user asks to create PR, prepare PR, deliver the change, publish, push, merge, or produce the final report for an agentic workflow run.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->


# Agentic Delivery

Use this skill when the human asks to prepare delivery. Delivery never skips
the final preflight.

## Procedure

1. Load the active run with `agentic-workflow status`.
2. Run `agentic-workflow registry sync`.
3. Run `agentic-workflow registry audit`.
4. Run `agentic-workflow impact` against the Git working set.
5. Run `agentic-workflow audit traceability`.
6. Run `agentic-workflow audit coverage`.
7. Run `$documentation-audit` or perform the same documentation review manually
   when the target repo has no documentation audit tooling.
   Treat broad README, overview, setup, and validation docs as opt-in or
   scope-triggered maintenance, not a default delivery blocker.
8. Confirm component documents under `05_SoftwareDocu/` were added or updated
   for new or materially changed components.
9. Run `agentic-workflow delivery-preflight`.
10. If preflight fails, stop and report failed invariants or audit findings.
11. If preflight passes, run or refresh `agentic-workflow report`.
12. Run the configured test gates if they were not already run in this turn.
13. Summarize the branch status, report path, gate results, traceability status,
   documentation status, and remaining risks.
14. Ask the human for explicit approval before push, PR creation, merge, or any
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
