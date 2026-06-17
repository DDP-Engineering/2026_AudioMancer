<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Requirements Registers

These Markdown registers are the durable AudioMancer project contract. The
active workflow run graph records what happened in one run; these registers
record what the project promises over time.

## Registers And ID Prefixes

| File | Prefix | Scope |
| --- | --- | --- |
| `functional.md` | `REQ-FUNC` | Observable product behavior |
| `ux_workflow.md` | `REQ-UX` | User-facing flows and interaction contracts |
| `non_functional.md` | `REQ-NFR` | Performance, robustness, determinism, quality |
| `security.md` | `REQ-SEC` | Access, secrets, threat boundaries |
| `data_privacy.md` | `REQ-DATA` | Persistence, privacy, retention, sensitive values |
| `platform.md` | `REQ-PLAT` | OS, runtime, and toolchain targets |
| `release.md` | `REQ-REL` | Packaging and delivery constraints |
| `testing.md` | `REQ-TEST` | Verification process rules and gates |

IDs use `PREFIX-NNN`, are stable forever, and are never reused after
retirement.

## Normative Table Schema

Every register uses exactly this header:

```text
| ID | Status | Priority | Requirement | Rationale | Related Components | Verification Method | Linked Tests | Created On | Last Updated |
```

- `Status`: `Planned`, `Active`, or `Retired`.
- `Priority`: `Must`, `Should`, or `Could`.
- `Related Components`: repository paths in backticks, separated by `;`.
- `Verification Method`: `Automated test`, `Manual <description>`, or
  `Automated test and inspection`.
- `Linked Tests`: exact test identifiers in backticks, separated by `;`.
- `Created On` / `Last Updated`: `YYYY-MM-DD HH:MM`.

`Active` rows need at least one resolvable linked test or an explicit manual
verification method. New rows normally start as `Planned` and become `Active`
only after their linked check passes.
