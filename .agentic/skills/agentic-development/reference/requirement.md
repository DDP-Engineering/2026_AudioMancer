<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: Requirement

Run `stage prepare`, then `stage add` for each additional atomic requirement.
AEGIS generates every requirement ID and companion specification.

Each requirement states one independently observable contract: behavior,
acceptance criterion, format, error, user-facing text, or non-functional
constraint. Split success, rejection, boundary, and state-effect contracts when
they can pass or fail independently. Cover applicable functional, UX,
non-functional, security, data/privacy, platform, release, and testing
dimensions.

Use the companion Markdown for observable response shapes, state transitions,
exact text, errors, boundaries, and worked examples. Identify applicable
production/mock/sandbox, feature-flag, role, platform, and persistence variants.
Do not put algorithms, component boundaries, internal data structures, or the
implementation sequence here; those belong to design.

Run `stage apply` to validate the complete directory atomically. Review the
imported requirement list and unresolved questions, then ask the human to run
`stage close`. Requirements remain Planned until validation closes with green
linked check evidence.
