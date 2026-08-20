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

# TASK-cdb74e46 — Narrator preview text sized for 10-15 second clone references

stage: done
type: change
path: full
requirements: REQ-FUNC-1202a564, REQ-FUNC-fd4b9595, REQ-FUNC-1c0c97a6, REQ-FUNC-05eabf3a, REQ-UX-3cdcb2a3
branch: master
base: e47c624c92d802af663941e9bacb3f0129cf696a
opened: 2026-08-20

## Done checklist (current stage)

- [x] scope and exclusions written in the log
- [x] path chosen (`full` or `quick`) with its reason logged
- [x] task branch established; `branch:` header matches the checkout
- [x] task journal created with a complete header
- [x] expected requirements listed
- [x] scope confirmed (checkpoint mode) or logged (autopilot)
- [x] `stage:` advanced
- [x] every in-scope behavior has exactly one requirement
- [x] required fields filled and prose is self-contained
- [x] each requirement states one behavior (one "shall"), in an EARS shape where one fits
- [x] `affected_paths` set to the best current guess
- [x] specs written only where the requirement was not buildable alone
- [x] journal `requirements:` line lists every ID
- [x] `check` reports no format errors
- [x] design note written, interface/data/rejected alternative covered, decisions cite requirement IDs
- [x] test seams named for every requirement
- [x] each automated requirement has a pre-implementation red record
- [x] repository anchor recorded after red and evolution reviewed after implementation
- [x] implementation makes those tests pass
- [x] focused impacted set green
- [x] `affected_paths` and `linked_tests` updated on every requirement
- [x] `status = "active"` on every requirement this task delivers
- [x] `check` clean, or each remaining warning explained in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and unrequested work
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, paths, and links true
- [x] final evolution report refreshed after the last candidate edit
- [x] final check result recorded truthfully after all edits
- [x] remaining warnings and pre-existing failures explained
- [x] validated candidate confirmed unchanged; otherwise returned to validate
- [x] validation evidence, diff, exclusions, and outcome presented
- [x] delivery confirmed by the human
- [x] journal and report included in the delivery commit
- [x] agreed outcome delivered: files staged for the operator's own commit; no push, no PR
- [x] close-out carried by that commit, since nothing can fail after it

## Design

Components touched: Voice Profiles (narrator generation, narrator definition,
Narator Voice controller) and App Shell (the localized string catalog).

One source of truth. `config.py` gains
`DEFAULT_NARRATOR_PREVIEW_MIN_AUDIO_SECONDS = 10.0` and
`DEFAULT_NARRATOR_PREVIEW_TARGET_AUDIO_SECONDS = 15.0`, and
`narrator_definition_service` gains
`narrator_preview_word_bounds() -> tuple[int, int]` returning `(25, 44)` by
multiplying those by the existing `DEFAULT_TTS_WORDS_PER_AUDIO_SECOND` and
adding the existing 6-word overage to the upper bound. The bounds live in
`narrator_definition_service` because all three consumers already import it
and it owns the defaults the bounds must agree with (REQ-FUNC-1202a564,
REQ-FUNC-1c0c97a6, REQ-UX-3cdcb2a3). The shared
`DEFAULT_TTS_MIN_PREVIEW_AUDIO_SECONDS = 6.0` is left alone: character
discovery reads it and character voices are out of scope.

Interface changes, all additive: `narrator_preview_word_bounds()` and
`preview_text_range_error(preview_text)` on `narrator_definition_service`;
one new `narator_voice.error_preview_text_out_of_range` key in both `en` and
`ro`. No data format changes - `narrator_voice.json` keeps its exact seven
root fields and its profile field set, and the report payload's existing
`warnings`/`warning_count` fields carry the substitution notice rather than a
new field (REQ-FUNC-05eabf3a).

`_normalize_profile`'s silent `or DEFAULT_PREVIEW_TEXT` coercion stays, since
the persistence contract still needs a non-empty value, but the editor gate in
front of it validates the operator's own text rather than the coerced result,
so a cleared box is refused instead of silently refilled (REQ-UX-3cdcb2a3).

Rejected alternative: keeping a frozen table of superseded default preview
texts so a language switch would relengthen profiles written by an earlier
version. The operator stated compatibility with previous versions is not
required, so an old short preview is simply preserved as authored text.

Test seams. REQ-FUNC-1202a564 and REQ-FUNC-05eabf3a attach at
`_validated_generated_profiles` through the existing fake-LLM fixtures in
`tests/test_narrator_profile_generation_service.py`. REQ-FUNC-fd4b9595 attaches
at the shipped prompt file, read directly rather than through the stub prompts
those tests normally install. REQ-FUNC-1c0c97a6 attaches at
`DEFAULT_PREVIEW_TEXT_BY_LANGUAGE` in `tests/test_narrator_definition_service.py`.
REQ-UX-3cdcb2a3 attaches at `handle_save_profile_requested` in
`tests/test_narator_voice_ui_controller.py`, monkeypatching `QMessageBox.warning`
the way `test_narator_voice_edit_missing_profile_shows_localized_profile_error`
already does.

## Log

- 2026-08-20 frame: scope is the AI narrator profile generation operation only - raise the generated `preview_text` length window so a cloned Qwen reference lands above 10 seconds and stays well under 30 seconds, using the 2.5 words-per-second estimator already in `config.DEFAULT_TTS_WORDS_PER_AUDIO_SECOND`.
- 2026-08-20 frame: in scope are `services/narrator_profile_generation_service.py` (narrator preview budget constants and `_validated_generated_profiles` bounds), `prompts/narrator_profile_generation_user.txt` (the word-count guidance handed to the model), narrator-specific new constants in `config.py`, and `tests/test_narrator_profile_generation_service.py`.
- 2026-08-20 frame: explicitly out of scope are character voice previews (`character_discovery_service.py:2708` shares `DEFAULT_TTS_MIN_PREVIEW_AUDIO_SECONDS`, so that constant is left untouched and narrator gets its own), imported-WAV duration rules, Speech Blocks and Audio Assembly budgets, the 512-character preview cap, and the canonical per-language default preview texts in `narrator_definition_service.py` (raised as an open question, not changed).
- 2026-08-20 frame: full path chosen - the change alters externally observable behavior (generated narrator samples become materially longer), adds narrator-specific configuration constants, and restates the numeric contract of an existing active requirement, so `specify` is where the numbers get pinned before any code moves.
- 2026-08-20 frame: expected requirements - update `REQ-FUNC-1202a564` ("Narrator profile generation shall enforce preview-text bounds") to the new 10-15 second target window and its bounded overage; add a `REQ-FUNC` for the shipped narrator generation prompt instructing the model to a 30-38 spoken-word preview, since no test today asserts the real prompt file's wording; add a `REQ-FUNC` for canonical per-language defaults clearing the floor; add a `REQ-FUNC` for the generated-preview fallback to the canonical default with a reported warning; add a `REQ-UX` for the manual editor blocking an out-of-range preview with a localized dialog naming the range.
- 2026-08-20 frame: scope extended on operator request - the canonical per-language default preview texts in `narrator_definition_service.py:83-110` are lengthened into the same 12-15 second band, so manually created profiles clone as well as generated ones.
- 2026-08-20 frame: scope extended on operator request - a generated `preview_text` that fails its length bound no longer fails the whole batch; that one profile falls back to the canonical default preview text for the selected voice language, which is valid by construction once the defaults are lengthened.
- 2026-08-20 frame: the fallback needs no new dependency - `narrator_profile_generation_service` already imports `narrator_definition_service` (line 32) and can call `preview_text_for_language()` directly; `narrator_definition_service` does not import back, so no cycle.
- 2026-08-20 frame: lengthening the defaults breaks the exact-match test in `apply_voice_language_to_profiles` (`narrator_definition_service.py:323-326`) for projects holding a superseded default, which would then be preserved as authored text and silently stay too short.
- 2026-08-20 frame: operator confirmed compatibility with previous versions is not required, so no legacy-default table and no migration path is built - a project written by an earlier version keeps its short preview as authored text, and the operator relengthens it in the editor.
- 2026-08-20 frame: scope extended on operator request - a hand-written preview outside the accepted word range must block the manual save behind a dialog naming the allowed range, instead of the current silent coercion in `_normalize_profile` (`narrator_definition_service.py:961`), which quietly replaces an empty preview with the default.
- 2026-08-20 frame: one narrator preview word range is therefore shared by three call sites - the generated-profile validator, the canonical per-language defaults, and the manual editor gate - so the bound is defined once in `config.py` and read everywhere.
- 2026-08-20 frame: character voices are unaffected - `character_voices_service.py:48` owns a separate `DEFAULT_PREVIEW_TEXT_BY_LANGUAGE`, and the only test literal found (`tests/test_character_voices_service.py:274`) reads that character dict, not the narrator one.
- 2026-08-20 frame: substitution must be visible - the report payload already carries unused `warnings`/`warning_count` fields (`narrator_profile_generation_service.py:409-410`), so the fallback records one warning per substituted profile and the success handler reports it instead of staying silent.
- 2026-08-20 specify: updated REQ-FUNC-1202a564 to the ten-to-fifteen-second window and restated its verification as preservation rather than rejection, since out-of-range preview text is now substituted instead of refused; created REQ-FUNC-fd4b9595, REQ-FUNC-1c0c97a6, REQ-FUNC-05eabf3a and REQ-UX-3cdcb2a3 as drafts.
- 2026-08-20 design: note written under `## Design`; the accepted word range is defined once in `narrator_definition_service.narrator_preview_word_bounds()` because the generation validator, the canonical defaults and the editor gate all need the same two numbers.
- 2026-08-20 build red: command=`uv run pytest -q tests/test_narrator_profile_generation_service.py::test_narrator_generation_prompt_requests_preview_inside_accepted_range tests/test_narrator_definition_service.py::test_canonical_preview_defaults_clear_the_minimum_word_bound tests/test_narator_voice_ui_controller.py::test_narator_voice_save_blocks_out_of_range_preview_text`; exit=1; expected missing behavior=`narrator_preview_word_bounds()` does not exist, the canonical defaults are below the floor, and the out-of-range dialog key is unknown.
- 2026-08-20 build red: command=`uv run pytest -q tests/test_narrator_profile_generation_service.py::test_narrator_profile_generation_substitutes_short_preview_text tests/test_narrator_profile_generation_service.py::test_narrator_profile_generation_preserves_latin_preview_budget_boundaries`; exit=1; expected missing behavior=short preview text still raises instead of being substituted, the validator still enforces the old 15/30 bounds, and it returns a bare profile list rather than profiles plus warnings.
- 2026-08-20 build: implemented the shared range in `narrator_definition_service.narrator_preview_word_bounds()` (25 to 44 words, from the two new config durations at 2.5 words per second), lengthened all eight canonical defaults into the twelve-to-fifteen-second band, turned the generation validator's four preview rejections into one substitution path returning profiles plus warnings, rewrote the shipped prompt's preview rule to ask for 30-38 spoken words on one line, and added the editor gate with one new localized message in `en` and `ro`.
- 2026-08-20 build: two follow-up failures found and fixed - the Russian default came in at 24 words against the 25 floor, and the bounded-overage test passed a 220-character preview limit that a 42-word preview cannot fit, so that test now uses the shipped 512-character default.
- 2026-08-20 build: DEVIATION build: accepted `check` warning `outside-layout` on `prompts/narrator_profile_generation_user.txt` - the repository keeps prompts outside the configured source and tests globs, so every prompt edit reports this; the cost is that `check` cannot associate the file with a requirement, which REQ-FUNC-fd4b9595's test offsets by reading the shipped file directly.
- 2026-08-20 build: evolution reported the eight files the design note named and nothing else; the three test files edited before the anchor do not appear, because the anchor is taken after the red run as the step file prescribes.
- 2026-08-20 validate: diff reviewed hunk by hunk against scope; no secrets, no platform-specific paths, and the only behavior found outside the frame scope is the deliberate `warning_count` surface in the generation success message, which REQ-FUNC-05eabf3a requires.
- 2026-08-20 validate: recorded a limitation rather than widening scope - the preview character limit is operator-settable from 64 while the accepted word range needs about 250 characters, so a deliberately lowered limit makes every generated preview substitute a default that is itself over that limit; the shipped default of 512 leaves ample room, and raising the settings minimum is left as a separate decision.
- 2026-08-20 validate: updated the Voice Profiles knowledge page with the shared preview range, the substitution behavior and the editor gate, and recorded both known limitations under section 10; wrote the CHANGELOG `## [Unreleased]` entry in user language and added the new preview-length rules to both user guides, since this changes behavior an operator can see.
- 2026-08-20 validate: focused suite command=`uv run pytest -q tests/test_narrator_profile_generation_service.py tests/test_narrator_definition_service.py tests/test_narator_voice_ui_controller.py tests/test_narrator_voice_single_document_contract.py tests/test_narrator_definition_state_service.py tests/test_ui_state_service.py`; exit=0; 111 passed. Adjacent character-voice, discovery, config-contract, page, budget and import suites ran clean earlier in the stage at 64 and 121 passed. `uv run ruff check` and `uv run python -m py_compile` on all changed sources exit 0.
- 2026-08-20 validate: DEVIATION validate: the full repository proof `check --task --strict --run` was not run - the operator asked that the full suite be skipped because of its duration and will exercise the change in the running application instead; `check --task --strict` alone reports errors=0 and `strict: ok`, so the cost is that no automated evidence covers suites outside the narrator, character-voice and settings modules listed above.
- 2026-08-20 validate: no version was assigned, so this is a delivery and not a release; the four version surfaces are untouched and both guides carry updated text against their existing version numbers.
- 2026-08-20 validate: operator challenged the empty-preview carve-out and was right; returned to build for the fix. `build_narrator_definition_state` preloads the editor with the canonical default for the project language, so the editor is never empty in the application and a cleared box can only mean the operator deleted the text - the weakest case, not an exempt one. The carve-out had been shaped by a unit test that builds an editor payload directly, which is a test artifact rather than a real flow.
- 2026-08-20 build: dropped the `or DEFAULT_PREVIEW_TEXT` fallback from `_accepted_preview_text_range` so a cleared box reports zero words and blocks, added `test_narator_voice_save_blocks_cleared_preview_text` pinning it, and corrected the now-false "leaving the box empty is not an error" sentence in both user guides and the CHANGELOG entry.
- 2026-08-20 validate: reproof after the empty-preview fix - command=`uv run pytest -q tests/test_narator_voice_ui_controller.py`; exit=0; 35 passed, covering both gate tests. `uv run ruff check` on the changed controller and test exits 0, evolution refreshed to eleven files, and `check --task --strict` reports errors=0 with `strict: ok`; the eighteen warnings remain the untracked `07_Delivery` and `0_Planning` strays, another task's ticket reference, and the four `outside-layout` entries for the prompt file, both user guides and the CHANGELOG.
- 2026-08-20 frame: DEVIATION frame: work stays on `master` with no task branch and no commit or push - the operator asked for exactly that; the cost is that the journal and any build output are not isolated and cannot travel to another machine until the operator commits.

## Delivery report (2026-08-20)

- stage: deliver; type: change; path: full; branch: master
- requirements:
  - REQ-FUNC-1202a564 - Narrator profile generation shall enforce preview-text bounds
  - REQ-FUNC-fd4b9595 - Narrator generation prompt shall request a preview inside the accepted range
  - REQ-FUNC-1c0c97a6 - Canonical narrator preview defaults shall clear the clone floor
  - REQ-FUNC-05eabf3a - Out-of-range generated preview text shall fall back to the canonical default
  - REQ-UX-3cdcb2a3 - The narrator editor shall block an out-of-range preview text
- diff vs task base e47c624: 25 file(s) changed, 2539 line(s) added
- checks: errors=0 warnings=10 notes=1
- checklist: 29/30 done; open: deliver: operator approval, then commit (not requested this session)

- 2026-08-20 deliver: operator exercised the change in the running application and reported it correct; approved staging without a commit or push, so the eleven candidate files plus the journal, report, knowledge page and five requirements are staged for the operator's own commit and the task closes here.
- 2026-08-20 deliver: corrected two journal-only inaccuracies in `## Design` - the helper shipped as `preview_text_range_error()` rather than the drafted `validate_preview_text()`, and the note still described the editor gate as validating the coerced value, which the empty-preview fix changed to validating the operator's own text. No candidate file was touched.
- 2026-08-20 deliver: the four `07_Delivery` binaries and the untracked `0_Planning/Analysis_2026-08-10` folder were already modified in the working tree before this task opened and are deliberately left unstaged.
