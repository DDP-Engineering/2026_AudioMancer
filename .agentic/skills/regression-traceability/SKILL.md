---
name: regression-traceability
description: Map changes to durable requirements and checks, reproduce regressions red-before-green, cover contract variants, and choose focused or full deterministic regression.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Regression Traceability

1. Run `<workflow> config validate --json` and
   `<workflow> config show --json`.
2. Run `<workflow> verify traceability`, `<workflow> verify coverage`, and
   `<workflow> verify impact [paths-file]`.
3. Treat impacted requirements as observable contracts. Mutate them only
   through requirement-stage forms after human approval.
4. For a fix, reproduce the exact failure as red evidence before
   implementation. Assert observable responses, errors, state transitions, and
   cleanup, not implementation details.
5. Identify applicable production/mock/sandbox, feature-flag, role, platform,
   and persistence-adapter variants. Add parity checks where variants promise
   the same contract.
6. Cover response shape, stale-state cleanup, rollback, errors, boundaries,
   concurrency, and idempotency where applicable.
7. Run linked checks first. Run full regression for shared or cross-cutting
   changes, untraced paths, or paths where impact recommends it.
8. Run `<workflow> verify run` before the human interprets the diff.

Report impacted requirements, variants, linked checks, untraced paths,
regression selection, commands/evidence, and remaining findings. Do not invent
security commands, coverage targets, timers, or a second verification workflow.
