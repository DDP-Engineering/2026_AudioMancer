<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: Design

The authoritative artifact is `.agentic/runs/<run-id>/design.md`.

Discuss alternatives with the user, then record the requirement summary and IDs,
existing architecture, constraints, alternatives and trade-offs, selected design
and rationale, affected components, internal interfaces/data, compatibility
implications, implementation sequence, validation approach, risks, and open
decisions.

Set `selected_option` in `design.toml`, cite the exact durable requirement IDs,
and leave no blocking question unresolved. Run `stage apply`, review the
proposal, then ask the human to run `stage close`. Any later design or cited
requirement digest change invalidates approval.
