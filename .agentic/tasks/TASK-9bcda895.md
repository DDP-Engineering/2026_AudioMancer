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

# TASK-9bcda895 — Unify VoiceWeaver model and provider URL normalization

stage: done
type: change
path: full
requirements: REQ-FUNC-9757d967, REQ-FUNC-1fef6b33, REQ-FUNC-9273a9ed
branch: ddp/x1-x2-model-url-normalization
opened: 2026-08-09

## Done checklist (current stage)

- [x] strict static AEGIS check and user-directed scoped validation recorded honestly
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and code style
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report included in the delivery commit
- [x] delivery commit created on the task branch without push
- [x] guarded local fast-forward into `AudioMancer_V2` preserves the six user-owned paths
- [x] close-out journal committed only after the delivery outcome succeeds
- [x] `CHANGELOG.md` Unreleased section describes the change in user language
- [x] release version and help-file workflow not applicable because this task is not a release

## Design

- Components: VoiceWeaver runtime normalization, settings persistence, cached TTS budgeting, shared URL joining, LLM chat generation, and OpenAI-compatible model probing.
- Interface [REQ-FUNC-9757d967]: promote the runtime model normalizer as `normalize_model`; settings imports the acyclic runtime service and calls that exact function for every cached model.
- Interface [REQ-FUNC-9757d967]: expose the runtime diagnostics normalizer too, replacing the proven settings-only duplicate without adding a shared abstraction module.
- Data [REQ-FUNC-9757d967]: retain the established known model keys and defaults, normalize scalar parameter/range metadata and status, deep-copy retained diagnostics/issues, and continue dropping unknown model fields.
- Data [REQ-FUNC-1fef6b33]: persist normalized range defaults unchanged through settings save/load so the existing TTS budget resolver can select `range_default` without downstream service changes.
- Interface [REQ-FUNC-9273a9ed]: chat and model probing call `join_endpoint_url` with `/v1/chat/completions` and `/v1/models`, both with duplicate-version collapse enabled.
- Data [REQ-FUNC-9273a9ed]: preserve the shared helper's proxy-path, query, and fragment semantics; profile schema, headers, authentication, timeouts, and errors remain unchanged.
- Rejected alternative: a new shared normalization module would add indirection when `settings_service` can import `voiceweaver_runtime_service` without a reverse dependency.
- Test seams [REQ-FUNC-9757d967]: settings/runtime parity and input-alias regressions in `test_settings_service.py`, plus runtime effective-parameter filtering in `test_voiceweaver_runtime_service.py`.
- Test seam [REQ-FUNC-1fef6b33]: a save/load-to-budget regression in `test_settings_service.py` using a temporary explicit settings path.
- Test seams [REQ-FUNC-9273a9ed]: table-driven helper-level URL assertions in provider tests and request-level chat/probe URL capture in `test_llm_provider_service.py` and `test_ai_backend_service.py`.
- Expected source files: `settings_service.py`, `voiceweaver_runtime_service.py`, `llm_provider_service.py`, and `ai_backend_service.py`; `url_service.py` should remain unchanged if its established contract proves sufficient.
- Expected delivery files: the linked tests, three requirements, this journal, `AI_Runtime.md`, `Platform_Settings_UI.md`, `TTS_Audio_Blocks.md`, and `CHANGELOG.md`.

## Log

- 2026-08-09 frame: scope is one service-owned canonical VoiceWeaver discovered-model contract across runtime, settings persistence, and cached TTS budgets plus one shared endpoint derivation policy for chat generation and OpenAI-compatible model probing.
- 2026-08-09 frame: exclusions are provider redesign, planning and settings-file edits, settings bootstrap, dependency changes, full-suite execution, commits before approval, push, and main-worktree mutation.
- 2026-08-09 frame: the full path is required because this change makes a service interface public, corrects a persisted data contract, and changes provider-visible request URLs.
- 2026-08-09 frame: the delegated instruction confirms the exact scope, validation policy, branch, and final approval checkpoint, so implementation may proceed without a separate frame pause.
- 2026-08-09 frame: propose one requirement for canonical model normalization, one for persisted range-driven TTS budget recovery, and one for unified provider endpoint derivation.
- 2026-08-09 specify: created REQ-FUNC-9757d967, REQ-FUNC-1fef6b33, and REQ-FUNC-9273a9ed with no separate specs because their contracts and table-driven observations are self-contained.
- 2026-08-09 specify: advisory check reported zero errors and only the repository's 31 existing global layout and ticket-reference warnings.
- 2026-08-09 design: direct settings-to-runtime imports are acyclic from source inspection, and the existing URL helper already defines the required proxy, query, fragment, and duplicate-version behavior.
- 2026-08-09 build: `test_validate_settings_uses_canonical_voiceweaver_model_normalization_without_aliases` red as expected because no public runtime normalizer existed.
- 2026-08-09 build: `test_voiceweaver_range_budget_survives_settings_save_and_load` red as expected because settings discarded `generation_parameter_ranges`.
- 2026-08-09 build: provider endpoint regressions red as expected because chat discarded query and fragment data while model probing omitted `/v1` for root and proxy bases.
- 2026-08-09 build: canonical model, persisted range-budget, effective-parameter, and provider endpoint regressions are green after the minimal shared-contract changes.
- 2026-08-09 build: direct linked-selector validation used the required shared interpreter instead of the `uv`-based AEGIS impacted wrapper and passed 20 unique cases.
- 2026-08-09 build: scoped modules produced 185 passes and 19 linked-case deselections, with the missing ignored settings scaffold deferred under the no-bootstrap instruction and one unrelated Speech Blocks fixture failure.
- 2026-08-09 build: the Speech Blocks Scene Ambience playability failure reproduced individually and is pre-existing because its fixture omits `audio_relative_path` while none of its test or service paths are changed here.
- 2026-08-09 build: Ruff passed all nine changed Python files, py_compile passed, both settings-first and runtime-first import smokes passed, and no settings file was created.
- 2026-08-09 build: strict static AEGIS exited 0 with `strict: ok`; its 85 warnings are repository-wide existing ticket, layout, and uncovered-source inventory rather than task diff defects.
- 2026-08-09 deliver: scoped logging coverage and Ruff passed; the code-style audit reports only 20 pre-existing missing-docstring findings outside the added test hunks, so its non-zero result is accepted as unchanged test debt.
- 2026-08-09 deliver: the full suite is intentionally deferred by user direction, and no settings bootstrap, `uv`, worktree virtual environment, push, main-worktree edit, or planning-file edit was performed.
- 2026-08-09 deliver: independent root review approved cached diff fingerprint `773d6fc4501fc9ba018b17726a3f2d8dbd76f7b9` after independently rerunning all 20 new regression cases successfully.
- 2026-08-09 deliver: delivery commit `02953a8a6784f822886f0e1251a6c3959fd24340` was created without push and fast-forwarded from the verified base while preserving identical hashes for the six user-owned main-worktree paths.
- 2026-08-09 close: delivery and guarded local integration succeeded, so the task is done and this journal-only close-out commit completes the AEGIS lifecycle.

## Delivery report (2026-08-09)

- stage: deliver; type: change; path: full; branch: ddp/x1-x2-model-url-normalization
- requirements:
  - REQ-FUNC-9757d967 - Canonicalize VoiceWeaver discovered models once
  - REQ-FUNC-1fef6b33 - Preserve cached VoiceWeaver range budgets
  - REQ-FUNC-9273a9ed - Derive provider chat and model endpoints uniformly
- diff vs task base: 18 file(s) changed, 755 line(s) added, 130 line(s) removed
- checks: errors=0 warnings=86 notes=0
- checklist: 8/11 done; open: delivery commit created on the task branch without push; guarded local fast-forward into `AudioMancer_V2` preserves the six user-owned paths; close-out journal committed only after the delivery outcome succeeds
