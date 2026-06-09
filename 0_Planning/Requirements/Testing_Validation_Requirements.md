<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Testing And validation Requirements

| ID | Status | Priority | Requirement | Rationale | Related Components | Verification Method | Linked Tests | Created On | Last Updated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-AUDIO-TEST-001 | Active | Must | Package Import shall satisfy the behavior, state transitions, validation rules, and edge cases covered by the linked automated tests. | Preserves the tested application contract for the audiobook preparation workflow. | `04_Software/AudioMancer/src/audiomancer` | Automated test | `tests/test_package_import.py::test_package_exposes_main_and_release_version_metadata` | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-AUDIO-TEST-002 | Active | Must | Python implementation changes shall be validated with `python -m py_compile` for each changed Python file. | Catches syntax errors before delivery or review. | `AGENTS.md`; `04_Software/AudioMancer/README.MD` | Manual verification: final summary names compiled files, or states that no Python files changed. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-AUDIO-TEST-003 | Active | Must | Python changes inside `04_Software/AudioMancer/` shall run changed-file Ruff check and format commands. | Keeps code style consistent without broad unrelated churn. | `AGENTS.md`; `04_Software/AudioMancer/pyproject.toml` | Manual verification: final summary names Ruff commands, or states that no Python files changed. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-AUDIO-TEST-004 | Active | Must | Behavior changes shall add or update focused automated tests and state the validation performed and remaining gaps. | Requirements, implementation, and tests should evolve together. | `AGENTS.md`; `HowToTest.md`; `04_Software/AudioMancer/tests/` | Manual verification: review changed requirements, tests, and final summary for traceability. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-AUDIO-TEST-005 | Active | Should | Requirement changes shall preserve stable IDs, timestamps, status values, priority values, and linked automated or manual verification methods. | Stable records let future changes update requirements without losing history. | `0_Planning/Requirements/`; `.codex/skills/requirements-traceability/SKILL.md` | Manual verification: inspect requirement rows for schema consistency. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
