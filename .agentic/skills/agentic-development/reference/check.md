<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: Check

Load this module only while in the `check` stage.

- Add tests/checks that cite spec IDs. For each `behavior` spec item cover the
  happy path *and* the failure paths it implies: invalid input, boundary and
  empty values, and the specific error or rejection the behavior is meant to
  produce. A single assertion of the obvious case rarely fixes the behavior or
  catches a regression.
- Prefer several small, focused checks over one broad one, so that when a check
  goes red later it names the specific behavior that broke. Match the depth of
  coverage to the risk in the spec item, not to a fixed count.
- Also cite durable requirement IDs in test comments, docstrings, or names where
  practical.
- For new components, include checks or review expectations that make the
  required `.agentic/knowledge/components/` documentation visible before
  delivery.
- Run the smallest relevant command and confirm new checks fail first.
- Record checks with `<workflow> add-check`.
- Record failing evidence with
  `<workflow> record-evidence --kind test-run --result fail --check-id <id>`.
- Stop before source implementation.
