<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Project Lifecycle Component Adoption

Run: `adoption-2026-07-18T145821Z-782116f8`

Adoption date: 2026-07-18

## Approved Scope

The human approved the repository component map and selected
`project-lifecycle` as the first component-adoption slice. The approved owner
is DDP Engineering / Eng. Dan Dumitru Pasare.

The production boundary contains eight files:

- `04_Software/AudioMancer/src/audiomancer/services/home_presenter_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/import_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/persistence_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/project_export_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/project_snapshot_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/home_page.py`

Mapped tests remain listed in `.agentic/components.toml`. No bundle exception is
used.

## Characterized Behavior

The component owns project workspace creation, manifest validation and
metadata-only repair, source registration, atomic critical-file persistence,
Home status/presentation and controller actions, readiness-based external
exports, and whole-project external ZIP snapshots. Its detailed boundary,
contracts, dependencies, workflow integration, and limitations are recorded in
`.agentic/knowledge/components/Project_Lifecycle.md`.

Downstream workflow services remain separate components. Project lifecycle may
read their artifacts to present readiness, heal compact manifest summaries, or
produce external deliverables, but it does not execute or rewrite their domain
operations.

## Durable Requirements

Six current-behavior requirements were added as `Planned`, proven through their
exact linked tests, and activated with the workflow CLI:

| Requirement | Behavior |
| --- | --- |
| `REQ-FUNC-001` | Project create/open/validate/save/repair and Home lifecycle state |
| `REQ-FUNC-002` | Safe supported source import, replacement, metadata, and collision handling |
| `REQ-FUNC-003` | Readiness-based external text/Markdown/audio exports without project mutation |
| `REQ-FUNC-004` | Cancellable external whole-project snapshots with safe publication |
| `REQ-NFR-001` | Same-directory atomic text/JSON persistence and failure cleanup |
| `REQ-SEC-001` | Project path containment and external export/snapshot destinations |

Every production file in the approved component is named by at least one
active, test-linked requirement. Repository coverage findings therefore fell
from 88 to 80; the remaining findings belong to the other 12 discovered
components.

## Validation Evidence

- Requirement traceability audit: pass, no issues.
- Exact linked requirement tests: 24 passed, 1 skipped, 1 deprecation warning.
  The skip is the existing Windows symlink-capability case.
- Broader mapped component suite: 111 passed, 1 skipped, 2 failed, 1 warning.
- Coverage audit: expected repository-wide failure with 80 uncovered source
  files outside this adopted production boundary.
- Application behavior-change check: no files under
  `04_Software/AudioMancer` were modified.

The first broader-suite attempt used the sandbox-denied default Windows pytest
temporary directory and produced 29 passes plus 85 setup errors. The identical
command was rerun with `TEMP` and `TMP` redirected to a writable repository
temporary directory; that rerun supersedes the environment-only result.

## Known Baseline Gaps

The broader mapped suite exposes two existing failures that are not linked to
the new requirements:

1. `test_atomic_io_contracts.py::test_manual_cleaned_text_edit_uses_atomic_writers`
   expects `text_cleanup_state_service.write_json_atomic`, which the current
   text-cleanup module no longer exposes. This crosses into the separately
   discovered `text-cleanup` component.
2. `test_main_window_project_flow.py::test_main_window_initializes_step_state_only_when_page_is_opened`
   expects `cleanup_state.json` to be created when the Text Cleanup page opens;
   the current application creates extraction state but not that cleanup state.
   The owning implementation crosses `app-shell` and `text-cleanup` boundaries.

Adoption cannot change runtime behavior or rewrite tests to resolve these
differences. Baseline review must classify them as blocking, follow-up, or
accepted legacy risk before `project-lifecycle` can be considered
`baseline-usable`.

## Component Status

`project-lifecycle` is now `characterized`: its approved boundary, owner,
responsibilities, risks, requirements, tests, and remaining gaps are explicit.
It is intentionally not yet `baseline-usable`; that decision belongs to the
next `baseline-review` gate.
