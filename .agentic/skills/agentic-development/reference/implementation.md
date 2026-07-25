<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: Implementation

Load this module only while in the `implementation` stage.

- Edit only configured implementation/source roots.
- Reconfirm local scope before change by checking mapped component paths against
  `.agentic/components.toml` when present.
- Update required component documentation under
  `.agentic/knowledge/components/` in the same change when component boundaries,
  contracts, or behavior change.
- Use `$write-component-documentation` for new or materially changed components.
- Run linked tests reported by impact analysis for changed files.
- If impact reports untraced files, run full configured regression gates.
- Run relevant checks until the new checks pass and prior checks remain green.
- Record passing evidence with
  `<workflow> record-evidence --kind test-run --result pass --check-id <id>`.
- When a new requirement-linked check is green, activate the snapshot with
  `<workflow> requirement activate --id <requirement-id> --linked-test <test-id> --verification "<method>"`.
- Replace complete linked-test and affected-path sets when associations change;
  preserve the ID for revisions of the same behavioral contract.
- Record touched paths with `<workflow> record-change`.
- Stop for validation.
