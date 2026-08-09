<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

<!--
Task journal. One file per task, at .agentic/tasks/TASK-<id>.md, kept
after delivery as the task's historical record.

The header is the block of "key: value" lines directly under the title.
Keep it exactly in that form — one key per line, no blank lines inside
the block, no comments between the lines — so it stays machine-readable.

  stage         frame | specify | design | build | deliver | done
                (adoption journals: survey | components | close | done)
  type          feature | fix | change | adopt
  path          full | quick
  requirements  comma-separated requirement IDs, empty until specify
  branch        the branch this task is delivered on
  opened        YYYY-MM-DD

Header lines are edited in place; log lines are only ever appended.
Keep each log line to one sentence.
-->

# TASK-1ec66c4a — Remove retired cross-cutting contracts X-8 through X-10

stage: done
type: change
path: full
requirements: REQ-PLAT-02331830, REQ-NFR-39f56048, REQ-NFR-6feb74e5, REQ-NFR-82f739cc, REQ-NFR-b3fb9944
branch: ddp/x8-x10-dead-contract-cleanup
opened: 2026-08-09

## Done checklist (current stage)

- [x] user-directed static `check --task TASK-1ec66c4a --strict` has no diff-introduced failure and evidence is logged
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and code style
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read and status, prose, verification, and links are true
- [x] `CHANGELOG.md` Unreleased section updated in user language
- [x] full-suite deferral and all user-directed scoped validation recorded honestly
- [x] delivery confirmed by the human before the commit
- [x] journal and report included in the delivery commit after approval
- [x] close-out stage and commit completed in the approved pre-integration sequence

## Design

- Components: Platform Settings UI owns the configuration, migration, and logging cleanup; Speech Blocks and Voice Profiles own the three page interfaces.
- Interface: remove only `DEFAULT_SCENE_AMBIENCE_GENERATION_ENABLED`, `DEFAULT_LOG_LEVEL_OVERRIDES`, `AVAILABLE_LOG_COMPONENTS`, the unreachable logging lookup, and the four named page methods (REQ-PLAT-02331830, REQ-NFR-82f739cc, REQ-NFR-b3fb9944).
- Compatibility: preserve `DEFAULT_SCENE_AMBIENCE_PLACEMENT`, deprecated-key removal, generation-context false fallbacks, the `get_component_logger` signature, logger identity/handlers/formatting/propagation, page getters, `update_speech_block_item`, and the three `set_*_state` full application methods (REQ-PLAT-02331830, REQ-NFR-82f739cc, REQ-NFR-b3fb9944).
- Data: make no schema or persisted-data change; the existing settings migration continues to discard only the deprecated Scene Ambience key (REQ-PLAT-02331830).
- Logging tests: retain the expired-file and JSON formatter regressions under their separated requirements, then replace the impossible override regression with explicit-level and global-default assertions (REQ-NFR-39f56048, REQ-NFR-6feb74e5, REQ-NFR-82f739cc).
- Removal tests: add focused configuration absence checks plus one structural page-class contract that also asserts the live selection/full-state methods remain callable (REQ-PLAT-02331830, REQ-NFR-82f739cc, REQ-NFR-b3fb9944).
- Rejected: wiring a new settings-backed logging override feature, reintroducing a global Scene Ambience switch, or refactoring UI state ownership would expand scope and alter behavior without a requirement.
- Expected production files: `config.py`, `logging_service.py`, `speech_blocks_page.py`, `character_voices_page.py`, and `narator_voice_page.py`.
- Expected test files: `test_config_contract.py`, `test_logging_service.py`, and a focused structural page-contract module.

## Log

- 2026-08-09 frame: Remove the retired Scene Ambience enablement constant, inert component logging override surface, and exactly four named dead UI page methods while preserving placement, migration, logger, getter, and full-page application contracts.
- 2026-08-09 frame: Exclude `0_Planning`, settings bootstrap, global-switch substitution, new logging settings, UI refactoring, visible behavior changes, the full suite, release versioning, commits, integration, and pushes before the requested checkpoint approval.
- 2026-08-09 frame: Use the full path because the batch retires documented interfaces, corrects an existing logging requirement, and must preserve a persisted-settings migration contract.
- 2026-08-09 frame: The user directed uninterrupted implementation through one exact pre-commit checkpoint, so the normal frame checkpoint is recorded here and deferred to that requested approval stop.
- 2026-08-09 frame: Propose one requirement for absence of retired Scene Ambience configuration while migration and placement remain authoritative.
- 2026-08-09 frame: Propose updating REQ-NFR-39f56048 so component logger levels use explicit per-call selection or the global default without an inert override surface.
- 2026-08-09 frame: Propose one requirement for absence of the four stale page methods while current selection getters and controller-driven full-page state application remain available.
- 2026-08-09 specify: Created REQ-PLAT-02331830, REQ-NFR-6feb74e5, REQ-NFR-82f739cc, and REQ-NFR-b3fb9944, and narrowed REQ-NFR-39f56048 to its live expired-log retention behavior.
- 2026-08-09 specify: Static AEGIS reported zero errors, with expected empty-linked-test warnings and pre-existing baseline warnings to be reassessed after build.
- 2026-08-09 design: Selected narrow symbol and method deletion with structural absence tests, retained live paths, and rejected new configuration or UI architecture.
- 2026-08-09 design: Static AEGIS again reported zero errors before implementation.
- 2026-08-09 build: `test_config_contract.py::test_config_omits_retired_scene_ambience_enablement_switch` red as expected because the retired global Scene Ambience attribute still existed.
- 2026-08-09 build: `test_config_contract.py::test_config_omits_retired_component_logging_overrides` red as expected because the inert override constants still existed.
- 2026-08-09 build: `test_ui_page_contract.py::test_workflow_pages_omit_retired_methods_and_keep_live_state_interfaces` red as expected because the four stale page methods still existed.
- 2026-08-09 build: Six preservation selectors were green before implementation, covering deprecated settings-key removal, placement authority, expired-log retention, JSON formatting, explicit logger levels, and global-default fallback.
- 2026-08-09 build: The nine linked selectors passed after the minimal constant, override-branch, and method deletions.
- 2026-08-09 build: Per user direction, direct venv selectors replace `aegis test --impacted` because the configured AEGIS test runner uses prohibited `uv` and would duplicate the requested verification.
- 2026-08-09 build: AEGIS static checking reported zero errors and only 31 baseline repository-layout or existing ticket-reference warnings before delivery.
- 2026-08-09 deliver: The consolidated 181-test scoped module run recorded 179 passes and two `FileNotFoundError` failures caused solely by the intentionally absent ignored `settings.json`, with no product assertion failure.
- 2026-08-09 deliver: A later scoped settings test generated ignored `settings.json`; it was proven ignored and run-owned from the prior absence evidence, then removed so the requested no-bootstrap end state is restored.
- 2026-08-09 deliver: The full pytest suite was not run by explicit user direction.
- 2026-08-09 deliver: Ruff, py_compile, import smoke, `git diff --check`, planning exclusion, settings absence, deleted-name source search, retained-fallback search, and live-path search all passed.
- 2026-08-09 deliver: `check --task TASK-1ec66c4a --strict` exited 0 with `strict: ok`, zero errors, and 86 non-promoted warnings from the intentional approval checkpoint, required CHANGELOG path, unrelated ticket reference, and predecessor branch divergence from configured origin.
- 2026-08-09 deliver: Hunk review confirmed exactly the requested symbol and method removals, preserved migrations and live interfaces, no new error or data path, portable imports, no secret material, and binding code-style compliance.
- 2026-08-09 deliver: Independent root review approved staged fingerprint `52f3eba5be1770d7e73fb22b0e2ced74e968178c1d3d7827007e41bfe9bfd9ca` after rerunning all nine linked selectors successfully.
- 2026-08-09 deliver: Generated the AEGIS report and corrected its configured-origin diff summary to distinguish predecessor history from the approved task-scoped staged diff.
- 2026-08-09 close-out: Delivery commit `0ac71db5fb4845affcfc1a3ff2424ae70bb2cc1f` succeeded, and the approved sequence requires this journal-only closeout before guarded local integration.

## Delivery report (2026-08-09)

- stage: deliver; type: change; path: full; branch: ddp/x8-x10-dead-contract-cleanup
- requirements:
  - REQ-PLAT-02331830 - Keep Scene Ambience placement authoritative
  - REQ-NFR-39f56048 - Remove only expired log files during logging initialization
  - REQ-NFR-6feb74e5 - Use the configured JSON log formatter
  - REQ-NFR-82f739cc - Resolve component logger levels without overrides
  - REQ-NFR-b3fb9944 - Keep retired workflow page methods absent
- approved task diff vs `f02bfcec065970d6ba7fe144b4e44b6c0e2b21cc`: 19 file(s) changed, 321 line(s) added, 156 line(s) removed; the configured-origin comparison additionally sees 404 predecessor-history files
- checks: errors=0 warnings=86 notes=0
- checklist: 8/9 done; open: close-out stage and commit completed only after guarded local integration succeeds
