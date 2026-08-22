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

  stage         frame | specify | design | build | validate | deliver | done
                (adoption journals: survey | components | close | done)
  type          feature | fix | change | adopt
  path          full | quick
  requirements  comma-separated requirement IDs, empty until specify
  branch        the branch this task is delivered on
  base          the commit this task started from, filled in at creation;
                the delivery report and `check --task` measure the diff
                against it, so leave it alone once it is written. Empty
                when the repository had no history yet.
  opened        YYYY-MM-DD

Header lines are edited in place; log lines are only ever appended.
Keep each log line to one sentence.
-->

# TASK-be95a1a6 — Adapt AudioMancer to the simplified VoiceWeaver REST API

stage: build
type: change
path: full
requirements: REQ-FUNC-636da15e, REQ-FUNC-1562fca1, REQ-FUNC-b3c6df2a, REQ-FUNC-a24e14cb, REQ-FUNC-6606ebfa
branch: master
base: f668be5f0002c50396f96b62cf283afafa21e229
opened: 2026-08-22

## Done checklist (current stage)

- [ ] each automated requirement has a pre-implementation red record with
      exact selector or command, non-zero exit, and expected failure reason;
      each manual requirement has a post-implementation observation
- [ ] repository anchor recorded after red and evolution reviewed after implementation
- [ ] implementation makes those tests pass
- [ ] `test --impacted` green
- [ ] `affected_paths` and `linked_tests` updated on every requirement
- [ ] `status = "active"` on every requirement this task delivers - or
      `"retired"`, with the reason in its prose, where this task
      deliberately removed the behavior
- [ ] `check` clean, or each remaining warning explained in the log
- [ ] `stage: validate`

## Log

- 2026-08-22 frame: Scope is to replace AudioMancer's VoiceWeaver client, orchestration, settings, tests, knowledge, changelog, and both user guides with the new unversioned eleven-route REST contract while preserving the current voice models and project artifacts.
- 2026-08-22 frame: Exclusions are VoiceWeaver implementation changes, model changes, AudioMancer release versioning, delivery package rebuilding, and all pre-existing delivery-artifact and VoiceWeaver-document edits.
- 2026-08-22 frame: Full path selected because this intentionally breaks an external REST interface, removes authentication and legacy management surfaces, changes required request fields and capabilities, and affects cancellation and error handling.
- 2026-08-22 frame: DEVIATION remaining on default branch master because the user explicitly required this work on the same branch and prohibited commit or push.
- 2026-08-22 frame: Proposed update to REQ-FUNC-636da15e covers unauthenticated runtime discovery through GET /models and GET /status with exact error-envelope handling.
- 2026-08-22 frame: Proposed update to REQ-FUNC-1562fca1 covers root generation routes, voice_design capability naming, mandatory supported language fields, client-owned clone prompts, and the single GET /audio result route.
- 2026-08-22 frame: Proposed replacement of REQ-FUNC-b3c6df2a covers removal of every /v1, health, server, catalog, rescan, remote model-management, authentication, and generated-voice compatibility surface from AudioMancer.
- 2026-08-22 frame: Proposed update to REQ-FUNC-a24e14cb covers cooperative POST /cancel only for runtime operations advertised as cancellable while retaining bounded local cancellation for non-cancellable Qwen work.
- 2026-08-22 frame: Scope confirmed by the user and advanced to specify.
- 2026-08-22 specify: Updated five existing VoiceWeaver client requirements for discovery, generation, route removal, cancellation, and the single generated-audio download.
- 2026-08-22 specify: Created REQ-UX-c32703fe for the authentication-free TTS Settings surface and REQ-PLAT-05691181 for removal of the deprecated persisted API-key field.
- 2026-08-22 specify: No additional spec is needed because the supplied VoiceWeaver REST interface defines the wire contract and each AudioMancer requirement is independently buildable from that contract.
- 2026-08-22 specify: AEGIS check reported no format errors and retained one unrelated ticket-pattern warning plus six protected pre-existing outside-layout changes.

## Design

- Components: TTS Audio Blocks, Voice Profiles, Character Voices, and Platform Settings keep their existing ownership while the shared runtime client becomes the sole simplified-contract boundary.
- Interface: use the documented simplified routes and exact `voice_design`, `clone`, and `sound_prompt` modes throughout the shared runtime boundary (REQ-FUNC-b3c6df2a, REQ-FUNC-636da15e).
- Generation: always send the selected voice language, send `device_mode = auto` on model load, and collect both voice and sound WAVs through one `/audio` helper (REQ-FUNC-1562fca1, REQ-FUNC-6606ebfa).
- Cancellation: retain the last polled operation and call `/cancel` only when it reports `cancellable = true`; non-cancellable Qwen work retains bounded local cancellation (REQ-FUNC-a24e14cb).
- Data: keep existing project `voice_clone_profiles.json` artifacts unchanged and configure the runtime through the base URL plus runtime-derived probe state (REQ-FUNC-636da15e).
- UI: present Base URL, Test Connection, models, runtime limits, and status behavior for the simplified local service (REQ-FUNC-636da15e).
- Rejected alternative: a dual `/v1` and root-route adapter was rejected because the requested hard break forbids compatibility and would retain ambiguous mode aliases (REQ-FUNC-b3c6df2a).
- Test seams: request-capture tests cover discovery and all runtime routes (REQ-FUNC-636da15e, REQ-FUNC-1562fca1, REQ-FUNC-b3c6df2a).
- Test seams: polling cancellation and byte-read timeout injections cover cancellation and `/audio` error translation (REQ-FUNC-a24e14cb, REQ-FUNC-6606ebfa).
- Test seams: positive TTS Settings connection-state, settings-scaffold parity, and runtime cache tests cover the simplified connection flow (REQ-FUNC-636da15e).
- Expected implementation surfaces: runtime, audio-block, settings, and shared TTS controllers/services; TTS Settings page and localization; settings scaffold; English/Romanian help; changelog; focused tests and knowledge pages.

- 2026-08-22 design: The four affected knowledge pages have no `## Architecture` diagram and the component ownership graph is unchanged, so no intended-shape diagram revision is owed.
- 2026-08-22 design: AEGIS check repeated only the seven already accepted pre-existing warnings and the design advanced to build.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_voiceweaver_runtime_service.py::test_probe_runtime_normalizes_models_and_capabilities`; exit=1; expected missing behavior=client still requested obsolete `/v1/health` before `/v1/models` and `/v1/status`.
- 2026-08-22 build red: command=`python .agentic/aegis.py test --impacted --base HEAD`; exit=1; expected missing behavior=legacy `base`, `voice_designer`, and definition-oriented capability fixtures/keys failed after current-mode normalization stopped accepting aliases.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_voiceweaver_runtime_service.py::test_voiceweaver_runtime_service_generation_payloads_use_current_contract tests/test_voiceweaver_runtime_service.py::test_voiceweaver_runtime_service_clone_prompt_wrappers_use_documented_contract tests/test_voiceweaver_runtime_service.py::test_voiceweaver_runtime_service_sound_prompt_wrappers_use_documented_contract tests/test_voiceweaver_runtime_service.py::test_voiceweaver_runtime_service_direct_clone_sends_selected_language`; exit=1; expected missing behavior=generation helpers still required removed API-key arguments and used `/v1` routes while omitting required Romanian language fields.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_voiceweaver_runtime_service.py::test_voiceweaver_runtime_service_exposes_only_simplified_route_helpers`; exit=1; expected missing behavior=status/model helpers still accepted API keys, targeted `/v1`, and exposed removed management compatibility functions.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_voiceweaver_runtime_service.py::test_generated_wav_downloads_translate_direct_timeouts`; exit=1; expected missing behavior=the remaining generated-audio helper still requested `/v1/audio` instead of the single `/audio` route.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_voiceweaver_runtime_service.py::test_wait_for_terminal_operation_posts_cancel_for_cancellable_runtime_operation`; exit=1; expected missing behavior=local cancellation still ended polling without submitting `/cancel` for a runtime-advertised cancellable operation.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_tts_settings_page.py::test_tts_settings_page_omits_voiceweaver_authentication`; exit=1; expected missing behavior=TTS Settings still constructed API-key widgets and rebuilt the deprecated settings field.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_settings_service.py::test_settings_remove_deprecated_voiceweaver_api_key`; exit=1; expected missing behavior=factory defaults, validation, config, and the committed scaffold still retained `tts_runtime_api_key`.
- 2026-08-22 build: Repository anchor recorded after the expected-red contract tests and before implementation edits.
- 2026-08-22 build: DEVIATION focused Audio Blocks regression exposed 13 stale API-key-shaped test doubles and the combined controller set exposed one stale shared-load expectation; all were corrected and focused reruns passed.
- 2026-08-22 build: Implemented the unauthenticated simplified client, exact capability and generation contracts, automatic model-load device selection, single generated-audio download, runtime-aware cancellation, settings/UI key removal, consumers, documentation, and migration coverage.
- 2026-08-22 build: `python .agentic/aegis.py test --impacted --base HEAD` passed with 1085 passed, 1 skipped, and 1 deselected in 1356.52 seconds.
- 2026-08-22 build: Evolution review found 30 expected non-AEGIS candidate files with no additions or removals; protected user documentation and delivery artifacts remained outside the implementation set.
- 2026-08-22 build: DEVIATION AEGIS check retained 11 accepted warnings with zero errors: one unrelated pre-existing ticket reference, six protected pre-existing user inputs or delivery artifacts, and four intentional task delivery files outside the configured layout.
- 2026-08-22 validate: Semantic error-path review returned the task to build because cancellation immediately after observing a cancellable status could end locally without submitting the required remote cancellation.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_voiceweaver_runtime_service.py::test_wait_for_terminal_operation_posts_cancel_when_requested_after_status_read`; exit=1; expected missing behavior=the post-status cancellation check raised before applying `/cancel` to the last observed cancellable operation.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_settings_service.py::test_settings_remove_deprecated_voiceweaver_api_key`; exit=1; expected missing behavior=future Linux and Windows package sanitizers still reintroduced the retired VoiceWeaver API-key field as an empty string.
- 2026-08-22 build: Packaged VoiceWeaver 1.0.0 smoke passed through AudioMancer's real client with three current-mode models, runtime version 1.0.0, idle status, and a ready capability matrix; the launcher-owned process was stopped without loading a model or generating audio.
- 2026-08-22 build: DEVIATION the first packaged-runtime smoke wrapper was command-policy rejected before execution; the documented direct launcher command then passed.
- 2026-08-22 build: DEVIATION the full screenshot tool stopped on a stale sample-project character document after six unrelated captures; those six were restored exactly from HEAD, and the new task-scoped dialog option produced and mirrored only the visually verified TTS screenshot.
- 2026-08-22 build: DEVIATION two read-only screenshot mirror checks hit one PowerShell syntax error and one constrained-language custom-object restriction before the plain hash check succeeded.
- 2026-08-22 build: DEVIATION recursive temporary restore cleanup was command-policy rejected; the exact temporary extraction and archive remain under `F:/Temp/AudioMancer-help-restore-20260822-1235*` outside the repository.
- 2026-08-22 build: Final focused lint and compilation passed, and `python .agentic/aegis.py test --impacted --base HEAD` passed with 1086 passed, 1 skipped, and 1 deselected in 1353.54 seconds.
- 2026-08-22 build: Refreshed evolution review found 35 expected non-AEGIS candidate files with no additions or removals, including only the two required TTS screenshot assets.
- 2026-08-22 build: DEVIATION AEGIS check retained 16 accepted warnings with zero errors: one unrelated ticket, six protected pre-existing user inputs or delivery artifacts, and nine intentional task files outside the configured layout.
- 2026-08-22 validate: User correction returned the task to build and clarified that the hard break must contain no legacy VoiceWeaver key migration, recognition, or absence tests.
- 2026-08-22 build: Deleted the two migration/absence requirements and their tests, removed legacy key recognition from settings, UI merge, packaging, and log redaction, and rewrote the remaining requirements around positive simplified-contract behavior.
- 2026-08-22 build: DEVIATION the in-progress impacted suite was interrupted after the acceptance criterion changed; its partial result describes an obsolete candidate and is not used as validation evidence.
