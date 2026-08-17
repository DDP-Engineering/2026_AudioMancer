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

# TASK-70ede2d5 — AI Translation chunk list resizable against the chunk text panes

stage: done
type: change
path: full
requirements: REQ-UX-dc3def51, REQ-UX-d6fc781d, REQ-UX-3a39f53e
branch: master
base: 86f63a1125d109dac032bdc04047c255745a8515
opened: 2026-08-17

## Done checklist (current stage)

- [x] the candidate is unchanged since the validate proof, or the proof was rerun
- [x] operator approval recorded
- [x] delivery report generated and read
- [x] changelog entry written under `## [Unreleased]`
- [x] outcome recorded in the log
- [x] `stage: done`

## Design

Component: AI Translation, page surface only. One file changes,
`04_Software/AudioMancer/src/audiomancer/ui/pages/ai_translation_page.py`, plus
its focused test module. No service, controller, document or signal is touched,
so the component's public interface is unchanged and no data or storage
decision arises.

Shape (REQ-UX-dc3def51). The page's `QVBoxLayout` currently holds the Chunk List
group inside a single-widget `QHBoxLayout` at stretch 1 and the existing
Original/Translated `QSplitter` at stretch 7. That fixed ratio is what makes the
boundary immovable. Replace both entries with one vertical `QSplitter`,
`_page_splitter`, whose first widget is `_chunk_list_group` and whose second is
the existing `_chunk_text_splitter`; the one-widget `QHBoxLayout` disappears
because it now carries nothing. `setChildrenCollapsible(False)` on the new
splitter, and stretch 0 on the list against 1 on the text panes so a window
resize is absorbed by the text rather than the list.

Limits (REQ-UX-d6fc781d, REQ-UX-3a39f53e). Two private module constants,
`_CHUNK_LIST_MINIMUM_HEIGHT = 150` and `_CHUNK_LIST_MAXIMUM_HEIGHT_FRACTION =
0.5`, replace the two bare literals 150 and 176 in the constructor. The standing
`setMaximumHeight(176)` is removed - it is precisely what pins the pane today -
and a new `_apply_page_splitter_limits` sets the maximum from the splitter's
live height on every resize, `max(minimum, int(height * fraction))`. The `max`
is the collision rule of REQ-UX-3a39f53e written literally: on a short window
the floor wins.

This mirrors `narator_voice_page.py`, which already floors a pane at a constant
and ceilings it at a fraction of its splitter from `resizeEvent`; following the
existing precedent rather than inventing a second idiom for the same problem.

Rejected: keeping the layout and giving the Chunk List a taller fixed maximum.
It is a smaller edit, but it delivers none of REQ-UX-dc3def51 - the operator
still cannot choose, only the developer can, and the next request would be a
different fixed number.

Test seams, all in `tests/test_ai_translation_page.py` against `_build_page`:
`_page_splitter.orientation`/`widget(0)`/`widget(1)` and a `setSizes` round trip
for REQ-UX-dc3def51; `_chunk_list_group.minimumHeight()` plus a `setSizes([1,
...])` squeeze for REQ-UX-d6fc781d; `maximumHeight()` after a known-height
resize plus a `setSizes` stretch for REQ-UX-3a39f53e. The page must be shown and
events processed before geometry is read - a hidden widget never lays out.

Risks. Reading `_page_splitter.height()` inside the page's `resizeEvent` can
see a stale height if the child has not been laid out yet; mitigated by the
narrator/characters precedent doing the same thing successfully and by the
tests asserting on real rendered geometry rather than on the setter arguments.
Second, `_chunk_text_splitter` is reparented into the new splitter rather than
into the page layout, so `_apply_chunk_text_splitter_minimums` now reads a
width set by the splitter; its existing thirty-percent tests cover that and
must stay green.


## Log

- 2026-08-17 frame: scope is the AI Translation page vertical geometry only - put the Chunk List group and the existing Original/Translated chunk splitter into one horizontal-handle splitter so the operator can drag the boundary between them, with the Chunk List floored at the height it renders at today and ceilinged at half of the space the two share.
- 2026-08-17 frame: out of scope are the existing Original/Translated left-right splitter and its thirty-percent minimums, the Chunk List internal layout and its action button column, every other page, and all translation behavior - document schema, worker dispatch, editing, approval and status are untouched.
- 2026-08-17 frame: measured the page as built today at 1400x900 - the Chunk List group renders at 150 px, which is its own `setMinimumHeight(150)` floor and not its `setMaximumHeight(176)` ceiling, because the fixed 1:7 layout stretch would only grant it 98 px; the chunk text splitter takes the remaining 634 px and neither boundary can be moved by the operator.
- 2026-08-17 frame: 150 px is therefore the "actual height" the ask asks to preserve as the minimum, and the shared span is the 790 px the two currently occupy together, making the ceiling 395 px at this window size.
- 2026-08-17 frame: full path chosen - this adds externally observable behavior (a draggable boundary that does not exist today) and no current requirement covers the vertical geometry of this page, so `specify` must write the requirement rather than promote one.
- 2026-08-17 frame: path deviation - the operator directed the work to stay on `master` rather than a `task/` branch, so step 4 of `1_frame.md` is knowingly not followed; `branch: master` matches the checkout.
- 2026-08-17 frame: constraints from the operator - no commit, no push, no full test suite (targeted tests only), stop at every stage checkpoint, and the operator will verify by running the app.
- 2026-08-17 frame: expected requirements - one new REQ-UX for the Chunk List floor at its present rendered height, and one new REQ-UX for the ceiling at half the shared span; both may end up as a single requirement if `specify` finds the split artificial.
- 2026-08-17 specify: wrote three new UX requirements - REQ-UX-dc3def51 for the vertical splitter that makes the boundary movable at all, REQ-UX-d6fc781d for the one hundred and fifty pixel floor, and REQ-UX-3a39f53e for the ceiling at half the shared height.
- 2026-08-17 specify: kept them as three rather than one because each is arranged and observed on its own - the splitter exists or it does not, the floor is read at the top of the drag, the ceiling at the bottom - and a single sentence covering all three would need two 'and's.
- 2026-08-17 specify: searched the requirement set for existing coverage of this page's geometry and found none; the AI Translation requirements cover document schema, editing, approval and busy state only, and nothing names the chunk list or either splitter, so there was nothing to update instead.
- 2026-08-17 specify: the floor-versus-ceiling collision on a short window is written into REQ-UX-3a39f53e as an explicit exception with the floor winning, per the frame checkpoint, rather than left to whichever Qt rule happens to apply.
- 2026-08-17 specify: no spec written - the requirements name widget, direction and quantity, and there is no format, protocol or non-obvious algorithm left to pin down.
- 2026-08-17 specify: `check --task` reports errors=0; the nine warnings are all pre-existing - eight untracked planning notes outside the source layout and one ticket pattern in another task's requirement - and the anchor note is cleared by anchoring at 86f63a1 over 332 files.
- 2026-08-17 design: note written - one vertical splitter replaces the fixed one-to-seven layout split, with the floor as a constant and the ceiling as a fraction of the splitter height applied on resize.
- 2026-08-17 design: adopted the `narator_voice_page.py` idiom deliberately, where a pane is floored at a pixel constant and ceilinged at a fraction of its splitter from `resizeEvent`, rather than writing a second pattern for the same problem.
- 2026-08-17 design: rejected simply raising the existing fixed maximum height, because it leaves the choice with the developer instead of the operator and delivers none of REQ-UX-dc3def51.
- 2026-08-17 design: `affected_paths` on all three requirements already name the single source file the design touches, so no update was needed.
- 2026-08-17 build red: command=`pytest -q tests/test_ai_translation_page.py::test_translation_page_splits_chunk_list_from_chunk_text`; exit=1; expected missing behavior=AttributeError, the page has no `_page_splitter` because the chunk list and the chunk text panes are still joined by a fixed layout stretch (REQ-UX-dc3def51).
- 2026-08-17 build red: command=`pytest -q tests/test_ai_translation_page.py::test_translation_page_chunk_list_keeps_its_minimum_height`; exit=1; expected missing behavior=AttributeError on `_page_splitter`, so there is no boundary to squeeze the chunk list against and the floor cannot be exercised (REQ-UX-d6fc781d).
- 2026-08-17 build red: command=`pytest -q tests/test_ai_translation_page.py::test_translation_page_chunk_list_stops_at_half_the_splitter`; exit=1; expected missing behavior=AttributeError on `_page_splitter`, and no `_apply_page_splitter_limits` exists to derive a ceiling from the shared height (REQ-UX-3a39f53e).
- 2026-08-17 build red: command=`pytest -q tests/test_ai_translation_page.py::test_translation_page_chunk_list_minimum_wins_on_a_short_page`; exit=1; expected missing behavior=AttributeError on `_page_splitter`, so the short-window collision between floor and ceiling cannot be observed (REQ-UX-3a39f53e).
- 2026-08-17 build: all four reds are the same missing attribute rather than four independent reasons, which is expected - the splitter is the seam every other behavior hangs off - and each test's second half still exercises its own requirement once the attribute exists.
- 2026-08-17 build: implemented the design as written - a vertical `_page_splitter` holding the chunk list group over the existing chunk text splitter, the two module constants replacing the bare 150 and 176 literals, the standing `setMaximumHeight(176)` removed, and `_apply_page_splitter_limits` called from the constructor and from `resizeEvent`.
- 2026-08-17 build: the single-widget `QHBoxLayout` that used to wrap the chunk list group is gone rather than reparented, because with the group moved into the splitter it carried nothing; `QHBoxLayout` is still imported for the header, chunk list and action rows.
- 2026-08-17 build: `pytest -q tests/test_ai_translation_page.py` exit=0, 14 passed, which is the four new tests plus the ten that already covered editing, flushing, control state and language display on this page.
- 2026-08-17 build: `test --impacted --base HEAD` exit=0, 32 test refs, 36 passed - including the existing chunk text splitter and localization coverage tests, which is the risk the design flagged about reparenting `_chunk_text_splitter` under the new splitter.
- 2026-08-17 build: measured the delivered page at 1400x900 - the page splitter spans 790 px, the chunk list opens at its 150 px floor with a 395 px ceiling, dragging fully down stops it at 395 and fully up at 150, and on a 420 px window the splitter falls to 366 px so the ceiling would be 183 and the floor still holds the pane at 150.
- 2026-08-17 build: `evolution --task` reports one modified source file and nothing added or removed, which is expected - the anchor was taken after the red tests and before implementation, so the test module was already inside it.
- 2026-08-17 build: all three requirements set to `active` with their linked tests filled; REQ-UX-3a39f53e carries two, one for the ceiling itself and one for the short-window case where the floor prevails.
- 2026-08-17 build: `ruff check src tests` passes, and `check --task` reports errors=0 with nine warnings, all pre-existing and unrelated - eight untracked planning notes outside the source layout and one ticket pattern in another task's requirement.
- 2026-08-17 validate: reviewed the diff hunk by hunk - one source file, thirty lines - against the frame scope and found nothing outside it; no service, controller, signal, document or string is touched, there is no I/O, no secret, no platform-specific call, and nothing was built that no requirement asked for.
- 2026-08-17 validate: `_apply_page_splitter_limits` guards both a missing attribute and a non-positive height exactly as its sibling `_apply_chunk_text_splitter_minimums` does, so a call during construction returns early rather than reading geometry that does not exist yet.
- 2026-08-17 validate: noted honestly that the constructor's call to `_apply_page_splitter_limits` always takes that early return, because the splitter has no height until the first show; it is kept for symmetry with the sibling call on the line above rather than removed, and the initial `setSizes` already opens the pane at its floor.
- 2026-08-17 validate: updated `.agentic/knowledge/AI_Translation.md` - the three new requirement IDs in Key Behaviors and one sentence in Usage describing the draggable split and its two bounds; nothing else in the page changed, so Purpose, Public Interface and Files stayed true.
- 2026-08-17 validate: re-read all three requirements against what was built - each prose statement, its verification and its affected path and linked tests describe the delivered behavior, and no correction was needed.
- 2026-08-17 validate: no `Manual:` or `Inspection:` verification exists on these requirements, so there is no manual observation owed; the operator will separately confirm the feel of the drag by running the app.
- 2026-08-17 validate: wrote the changelog entry under `## [Unreleased]` in Changed, in operator language, and assigned no version - this delivery is not a release.
- 2026-08-17 validate: refreshed `evolution --task` after the changelog edit; the final candidate is two modified files, the page source and CHANGELOG.md, with nothing added or removed.
- 2026-08-17 validate: rebuilt proof after those edits - `test --impacted --base HEAD` exit=0 with 32 refs and 36 passed, and `check --task TASK-70ede2d5 --strict` exit=0 reporting `strict: ok`, errors=0, warnings=10.
- 2026-08-17 validate limitation: `check --strict --run` was NOT run, because the operator excluded the full test suite for this task; the strict catalog half of step 8 passed and the full-suite half is owed, so no claim of a green full suite is made here.
- 2026-08-17 validate: of the ten warnings, nine are pre-existing and unrelated - eight untracked planning notes and one ticket pattern in another task's requirement - and the tenth is CHANGELOG.md sitting outside the source and tests globs, which is where the changelog belongs and is accepted.
- 2026-08-17 deliver: returned to `validate` at step 1 of `6_deliver.md` before presenting, because the operator asked whether the help files were updated and they were not - the candidate had to change after the recorded proof, so the proof had to be rebuilt.
- 2026-08-17 validate: the miss was real - `05_SoftwareDocu/UserGuide/index.html` and `UserGuide_ro/index.html` document operator-visible page behavior, and commit f9e55c9 set the precedent by adding exactly one list item to each guide for the same draggable chunk list on the Speech Blocks page.
- 2026-08-17 validate: added one list item to the AI Translation section of each guide, English and Romanian, describing the drag and both bounds in operator language; no version number was touched in either guide, because assigning a version is what makes a delivery a release and this task is not one.
- 2026-08-17 validate: `pytest -q tests/test_package_import.py` exit=0, which is the authoritative release-version test, confirming the guide edits left the four version surfaces in agreement.
- 2026-08-17 validate: searching for that precedent surfaced a second and more serious finding - the f9e55c9 commit message records that a nested splitter has no final geometry during the page resize event, which is exactly the risk the design note raised about `_chunk_text_splitter` and then waved through on the strength of an unrelated precedent.
- 2026-08-17 validate: measured it rather than assuming - resized the page across 1400, 900, 1600 and 700 pixels wide and 900, 500, 1000 and 400 tall, and the Original Chunk minimum width and the chunk list maximum height matched their computed values at every step with no stale reading.
- 2026-08-17 validate: the reason the Speech Blocks failure does not apply here is that this page nests the chunk text splitter inside a vertical splitter, so its width is set by the page and is already final in the page resize event, whereas the Speech Blocks lower splitter took its width from a splitter that had not been laid out yet.
- 2026-08-17 validate: deliberately did not copy the `eventFilter` machinery from `speech_blocks_page.py`, because it would add a code path that fixes a defect this page does not have; the design note's risk line is now settled by measurement instead of by analogy.
- 2026-08-17 validate: rebuilt the proof on the final four-file candidate - `test --impacted --base HEAD` exit=0 with 32 refs and 36 passed, and `check --task TASK-70ede2d5 --strict` exit=0 reporting `strict: ok`, errors=0, warnings=13.
- 2026-08-17 validate: the three warnings added since the previous run are the two guide files and nothing else, both flagged only as sitting outside the source and tests globs, which is where the user guides belong and is accepted.
- 2026-08-17 validate limitation: `check --strict --run` is still NOT run and the full suite is still owed and unclaimed, unchanged from the earlier record.
- 2026-08-17 validate: the `assets/screenshots/ai-translation.png` image embedded in both guides still shows the page without the new divider; the operator has taken regenerating the help images as their own follow-up, so it is deliberately outside this task and the guide text was updated without it.
- 2026-08-17 deliver: the candidate is unchanged since the validate proof - the last edit was the two guide files, and the impacted set and strict check were both rerun after it, so no re-proof was owed here.
- 2026-08-17 deliver: the operator ran the application, exercised the new divider on the AI Translation page and approved the delivery.
- 2026-08-17 deliver: outcome is a repository-local commit made by the operator themselves - no push, no pull request, no release - so `6_deliver.md` step 6 applies in its second form and close-out happens before the commit rather than in a second one.
- 2026-08-17 deliver: staged the six modified files, the three new requirement files and the three task journal files, and deliberately left `0_Planning/Analysis_2026-08-10/` untracked because it belongs to no task; the delivery report's count of twenty changed files includes those eight untracked notes.
- 2026-08-17 deliver: the report was generated before the checklist was ticked, so its snapshot reads 0/6 while the checklist above is complete; the report's own counts are a report-time advisory snapshot and the validation evidence stands in the log.
- 2026-08-17 deliver: closing with the full suite still owed - `check --strict --run` was never run in this task because the operator excluded it, and nothing here claims a green full suite; the evidence backing this delivery is the thirty-six test impacted set, ruff, the release-version test and the strict catalog at exit 0, plus the operator's own run of the application.
- 2026-08-17 deliver: regenerating `assets/screenshots/ai-translation.png` in both guides remains open and is owned by the operator, who chose to do it separately.

## Delivery report (2026-08-17)

- stage: deliver; type: change; path: full; branch: master
- requirements:
  - REQ-UX-dc3def51 - The AI Translation page shall let the operator resize the Chunk List against the chunk text panes
  - REQ-UX-d6fc781d - The AI Translation Chunk List pane shall keep a minimum height of one hundred fifty pixels
  - REQ-UX-3a39f53e - The AI Translation Chunk List pane shall not exceed half of the height it shares with the chunk text panes
- diff vs task base 86f63a1: 20 file(s) changed, 2835 line(s) added
- checks: errors=0 warnings=13 notes=0
- checklist: 0/6 done; open: the candidate is unchanged since the validate proof, or the proof was rerun; operator approval recorded; delivery report generated and read; changelog entry written under `## [Unreleased]`; outcome recorded in the log; `stage: done`
