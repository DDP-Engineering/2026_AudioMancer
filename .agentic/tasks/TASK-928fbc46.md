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

# TASK-928fbc46 — Remove the preview text limit and narration block target settings and read TTS budget limits from the runtime

stage: done
type: change
path: full
requirements: REQ-FUNC-82401294, REQ-FUNC-9029b464, REQ-UX-571c3e2f, REQ-FUNC-361ae600
branch: master
base: 1df2c2564cd41b2609f73d45d5ffe538c4f66876
opened: 2026-08-20

## Done checklist (current stage)

- [x] candidate reviewed against every listed requirement
- [x] knowledge pages updated for the components touched
- [x] `check --task --strict` read and self-corrected
- [x] full suite result recorded
- [x] deviations recorded and spoken

## Design

Components touched: Platform Settings UI (configuration, settings validation,
TTS settings page), Speech Blocks and TTS Audio Blocks (budget resolution),
Voice Profiles (narrator preview plumbing).

Budget resolution, REQ-FUNC-82401294 and REQ-FUNC-9029b464. Both budget paths
read the same runtime mapping, `generation_parameter_ranges.max_new_tokens`.
A new public helper on `tts_budget_service` extracts the two values from one
discovered-model payload - the token budget, taken from `recommended_maximum`
and bounded by `hard_maximum`, and the per-token audio rate. Both fall back to
what they use today when the runtime reports neither. `resolve_cached_tts_budget`
consults the helper before its existing default-parameter sources;
`audio_blocks_service._resolve_model_budget` gains the same source ahead of its
`runtime_effective` chain, because the loaded model reports its own default as
effective and would otherwise mask the recommended maximum. `audio_blocks_service`
imports `tts_budget_service` for the first time; no cycle is possible, since that
module imports only `config`.

Preview text limit, REQ-UX-571c3e2f. The setting, its configuration constant, its
persisted key and the narrator editor's silent truncation are deleted rather than
defaulted, so nothing keeps a second opinion about preview length. The
`preview_text_character_limit` parameter is removed from the narrator state
payload and from generated-profile validation, which already reject on the word
range.

Narration block target, REQ-FUNC-361ae600 retired. The control, three
configuration constants, the persisted key with its load-time normalization, both
`tts_budget_service` narrowing helpers and the localized strings are deleted.
`speech_blocks_normalization_service.resolve_narrator_only_budget` then returns
the cached budget directly.

`tts_runtime_device_diagnostics` is deleted end to end - the probe field,
`voiceweaver_runtime_service.normalize_device_diagnostics`, the settings key with
its normalization, and the page state - because nothing reads it. No requirement
governs it.

Rejected alternative: raising the preview character limit's minimum to about 256
instead of deleting the setting. It removes the lockout but leaves two authorities
over one quantity, and the surviving one can still contradict the word range.

Test seams: `tests/test_tts_budget_service.py` for both budget requirements;
`tests/test_settings_service.py` and `tests/test_narator_voice_page.py` for the
preview range being the only limit.

## Log

- 2026-08-20 frame: scope is removing two operator settings whose values cannot help and can harm - Preview Text Limit (chars) and Narration Block Target (s) - removing the unused `tts_runtime_device_diagnostics` persisted field, and resolving the TTS token budget from what the runtime reports instead of from hardcoded configuration.
- 2026-08-20 frame: Preview Text Limit is removed because the shared 25-44 word preview range already governs preview length on both voice pages, at save and at generation; the character limit is a second weaker authority that applies only to the narrator, truncates silently, and at any value below about 256 characters makes valid preview text impossible to write.
- 2026-08-20 frame: Narration Block Target is removed because it can only shorten and the model budget caps it, so with the 512-token clone budget every value at or above 33 seconds is identical to Auto - 267 of the control's 300 seconds are inert - and no operator value improves on Auto.
- 2026-08-20 frame: `tts_runtime_device_diagnostics` is captured from the probe, normalized on load and written back on save, but no consumer reads it and nothing renders it.
- 2026-08-20 frame: the live runtime was not reachable (curl exit 7), so the 1.7B-Base capability figures were read from the persisted probe in `settings.json`: default 512, minimum 128, recommended_maximum 2048, hard_maximum 8192, approx_audio_seconds_per_token 0.08333333333333333 - identical to the 0.6B figures documented in `01_Documentation/VoiceWeaver_REST_API_Interface.md`.
- 2026-08-20 frame: out of scope - raising the resolved token budget from the model's `default` to its `recommended_maximum`, which would lengthen every narration block about fourfold and needs generation-quality measurement on real hardware first.
- 2026-08-20 frame: out of scope - the Scene Ambience controls, the two timeout controls, and the `tts_runtime_probe_message` field, all of which have real consumers.
- 2026-08-20 frame: full path, because removing two settings is externally observable behavior, the persisted settings schema changes, and one requirement is retired.
- 2026-08-20 frame: expected requirements - retire REQ-FUNC-361ae600 (operator narration block target shall only shorten), new REQ-FUNC for resolving the audio-seconds-per-token rate from the runtime payload, new REQ-FUNC for clamping the resolved token budget to the runtime-reported ceiling, new REQ-UX for the preview range being the single authority on preview text length now that the character limit is gone.
- 2026-08-20 frame: DEVIATION frame - stayed on `master` instead of opening a task branch, on the operator's standing instruction for this repository; the cost is that this task's journal and code share history with any other work on master.
- 2026-08-20 specify: wrote REQ-FUNC-82401294 (token budget from the runtime recommended maximum, bounded by the hard maximum), REQ-FUNC-9029b464 (per-token audio rate from the runtime model payload), REQ-UX-571c3e2f (the accepted word range is the only limit on preview text length).
- 2026-08-20 specify: DEVIATION - retired REQ-FUNC-361ae600 with its three linked tests, because the narration block target control it governs is removed.
- 2026-08-20 specify: the operator chose to adopt the reported recommended maximum as the planning budget rather than only clamping to it, so narration blocks grow from about 81 words to about 341; recorded here because it changes generated output on every project.
- 2026-08-20 design: design note written; `audio_blocks_service` imports `tts_budget_service` for the first time, which is safe because that module imports only `config`.
- 2026-08-20 design: known limitation left in place - `resolve_cached_tts_budget` takes the first discovered model reporting a token budget rather than the first clone-capable one, so a runtime listing VoiceDesign before Base would plan Speech Blocks against the wrong model; unchanged by this task, and the Audio Blocks re-split still bounds the result.
- 2026-08-20 build: red first - three of the five new budget tests failed against the old resolver (recommended maximum ignored, configured rate returned instead of the reported 0.05).
- 2026-08-20 build: `tts_budget_service.model_generation_limits()` added as the single reader of the reported `max_new_tokens` range; `resolve_cached_tts_budget` and `audio_blocks_service._resolve_model_budget` both consult it before their existing sources.
- 2026-08-20 build: removed the preview text limit end to end - configuration constant, persisted key, settings control, narrator editor truncation, narrator state payload field, generation-service parameter - and the narration block target end to end, including three configuration constants and both budget-narrowing helpers.
- 2026-08-20 build: removed `tts_runtime_device_diagnostics` end to end, including `voiceweaver_runtime_service.normalize_device_diagnostics()` and the `device_diagnostics` field of the probe result.
- 2026-08-20 build: all three retired keys are purged from a persisted settings file on load, following the existing deprecated-field pattern, so an older settings file does not carry them forever.
- 2026-08-20 build: DEVIATION - edited the operator's own untracked `04_Software/AudioMancer/settings.json` to drop the three retired keys. In a source checkout that file is the bundled scaffold the scaffold tests read, and it would otherwise fail validation until the app next ran; the edit is exactly what the new load-time purge performs, and every other key is untouched.
- 2026-08-20 build: DEVIATION - no `anchor` was taken between the red run and the implementation, so no `evolution` report exists for this task; anchoring now would fingerprint the finished tree and prove nothing. Diff review at validate stands in for it.
- 2026-08-20 validate: DEVIATION - accepted two `uncovered-source` warnings, for `voiceweaver_runtime_service.py` and `tts_runtime_ui_support.py`. Both were touched only to delete the unused device-diagnostics plumbing, which no requirement governs and which needs none.
- 2026-08-20 validate: accepted the standing `outside-layout` warnings for `CHANGELOG.md`, both user guides, `settings.example.json` and the `07_Delivery` binaries; the repository keeps those paths outside the configured source and test globs by design.
- 2026-08-20 validate: `check --task TASK-928fbc46` reports errors=0.
- 2026-08-20 validate: impacted suite green - 294 passed across sixteen modules, pytest exit status 0 captured directly; a later one-word edit to `audio_blocks_service` was re-covered by a second run of its module plus the budget module, 56 passed.
- 2026-08-20 validate: the full suite was NOT run, on the operator's standing instruction; evidence for this task covers the sixteen impacted modules only.
- 2026-08-20 validate: `ruff check src/ tests/` clean; `check --task TASK-928fbc46 --strict` reports errors=0 and `strict: ok`.
- 2026-08-20 validate: diff review found one clarity fault of my own - the recommended-maximum budget candidate relied on `int(None)` raising inside the shared helper to mean "unreported"; made explicit with `or 0`.
- 2026-08-20 validate: `Platform_Settings_UI.md` needed no change; it does not enumerate the removed settings keys.
- 2026-08-20 validate: measured against the operator's own persisted 1.7B-Base payload, one narration block goes from 81 to 341 words - 2048 tokens, 170.67 model seconds, 136.53 after the safety factor.

## Delivery report (2026-08-20)

- stage: done; type: change; path: full; branch: master
- requirements:
  - REQ-FUNC-82401294 - The TTS token budget shall come from the runtime-reported recommended maximum
  - REQ-FUNC-9029b464 - The generated-audio rate per token shall come from the runtime model payload
  - REQ-UX-571c3e2f - Voice preview text length shall be governed only by the accepted word range
  - REQ-FUNC-361ae600 - The operator-selectable narration block target shall only shorten
- diff vs task base 1df2c25: 41 file(s) changed, 654 line(s) added
- checks: errors=0 warnings=11 notes=2
- checklist: 5/5 done
