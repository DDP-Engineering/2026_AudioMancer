<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Requirements

This folder contains the active AudioMancer requirements registers. These requirements are verification targets for implementation, tests, documentation, and agentic development work.

## Requirement Registers

Use one register per requirement type so agents can parse only the requirement area relevant to a change.

| Requirement Type | File | ID Prefix |
| --- | --- | --- |
| Functional | `Functional_Requirements.md` | `REQ-AUDIO-FUNC` |
| Non-functional | `Non_Functional_Requirements.md` | `REQ-AUDIO-NFR` |
| Security | `Security_Requirements.md` | `REQ-AUDIO-SEC` |
| Platform | `Platform_Requirements.md` | `REQ-AUDIO-PLAT` |
| Packaging and release | `Packaging_Release_Requirements.md` | `REQ-AUDIO-REL` |
| UX and workflow | `UX_Workflow_Requirements.md` | `REQ-AUDIO-UX` |
| Data and privacy | `Data_Privacy_Requirements.md` | `REQ-AUDIO-DATA` |
| Testing and validation | `Testing_Validation_Requirements.md` | `REQ-AUDIO-TEST` |

## Table Schema

Every register uses the same compact table schema:

| Column | Purpose |
| --- | --- |
| ID | Stable requirement identifier. Do not reuse retired IDs. |
| Status | `Active`, `Planned`, or `Retired`. |
| Priority | `Must`, `Should`, or `Could`. |
| Requirement | Verifiable statement of expected behavior or constraint. |
| Rationale | Why the requirement exists. |
| Related Components | Repository paths or components affected by the requirement. |
| Verification Method | Automated test, inspection, review, or manual check. |
| Linked Tests | Test node IDs when automated coverage exists. Use `N/A` when verification is manual only. |
| Created On | Local timestamp when the requirement ID was introduced. |
| Last Updated | Local timestamp for the last material row change. |

Use timestamp format `YYYY-MM-DD HH:MM` in repository local working time. Preserve `Created On` for existing requirements. Update `Last Updated` only when the requirement row is materially changed.

## Maintenance Workflow

When behavior changes, update the relevant requirement-type file in the same change. Each active requirement must link to at least one automated test or name a manual verification method. New or changed tests should mention relevant requirement IDs in their test docstrings when practical.
