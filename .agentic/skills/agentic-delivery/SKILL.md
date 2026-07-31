---
name: agentic-delivery
description: AEGIS 2.1 delivery-stage validation and human handoff. Use for final reports and for separately approved Git push, PR, merge, or publication work.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Agentic Delivery

1. Run `<workflow> config validate --json` and
   `<workflow> config show --json`.
2. Run `<workflow> run resume` or pin the run with `--run <run-id>`.
3. If validation is not closed, run `<workflow> verify run`, review its summary,
   perform the interpretive diff/documentation/style review, complete the
   validation form, apply it, and ask for `stage close` approval.
4. In delivery, prepare and complete the delivery form with preflight/report
   references, remaining risks, and the human handoff decision.
5. Run `<workflow> delivery show` and `<workflow> delivery report`.
6. Run `stage apply`, review the imported delivery state, then ask the human to
   run `stage close`.

Closing delivery marks the run complete. It performs no Git push, PR, merge, or
publication.

After AEGIS completion, stage only explicitly intended paths. Ask for separate,
explicit approval before any outward action. Report the run, report path, gate
states (including disabled groups), traceability, documentation status, risks,
and exact proposed Git action.
