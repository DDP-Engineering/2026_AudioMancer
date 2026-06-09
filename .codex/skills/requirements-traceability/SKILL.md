---
name: requirements-traceability
description: Create, update, review, or validate AudioMancer requirements traceability. Use when Codex changes behavior, adds tests, reviews coverage between requirements and tests, updates files under 0_Planning/Requirements/, or audits whether implementation, tests, documentation, and requirement IDs stay aligned.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Requirements Traceability

Use this workflow:

1. Read `AGENTS.md` and `0_Planning/Requirements/README.md`.
2. Identify the requirement type affected by the change and read only the relevant requirement files under `0_Planning/Requirements/`.
3. Read changed implementation files, changed tests, and relevant `05_SoftwareDocu/` component documents.
4. For behavior changes, add or update requirements in the relevant requirement-type file.
5. Preserve `Created On` for existing requirements. Set it only when a new requirement ID is introduced.
6. Update `Last Updated` only when the requirement row is materially changed.
7. Link each active requirement to an automated test node ID or an explicit manual verification method.
8. When adding or changing tests, mention relevant requirement IDs in test docstrings when practical.
9. Report uncovered requirements, stale links, or requirements that describe planned behavior as active implementation truth.

Requirement register files:

- `Functional_Requirements.md` for observable application behavior.
- `Non_Functional_Requirements.md` for quality constraints such as determinism, diagnostics, maintainability, and performance.
- `Security_Requirements.md` for security-sensitive constraints.
- `Platform_Requirements.md` for operating system and desktop runtime targets.
- `Packaging_Release_Requirements.md` for release and delivery constraints.
- `UX_Workflow_Requirements.md` for user-facing flows and interaction contracts.
- `Data_Privacy_Requirements.md` for local data, privacy, persistence, and sensitive-value handling.
- `Testing_Validation_Requirements.md` for verification process rules.

Formatting rules:

- Use stable IDs with the prefix documented in `0_Planning/Requirements/README.md`.
- Use status values `Active`, `Planned`, or `Retired`.
- Use priority values `Must`, `Should`, or `Could`.
- Use timestamp format `YYYY-MM-DD HH:MM` in repository local working time.
- Keep requirement text verifiable and concise.
- Do not scan or rewrite unrelated requirement files when one requirement type is enough.

Final response expectations:

- State which requirement IDs were added or updated.
- State what was validated.
- State any active requirements that still lack automated tests.
