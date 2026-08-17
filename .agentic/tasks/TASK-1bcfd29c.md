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

# TASK-1bcfd29c — Characters page left pane horizontal scrolling and wider minimum

stage: done
type: fix
path: full
requirements: REQ-UX-da69ce7f, REQ-UX-c42d3a75
branch: master
base: 1fda957d63a16013e896479d20c84e7f4f96d863
opened: 2026-08-17

## Done checklist (current stage)

- [x] validated candidate confirmed unchanged; otherwise returned to validate
- [x] validation evidence, diff, exclusions, and outcome presented
- [x] delivery confirmed by the human
- [x] journal and report included in the delivery commit
- [x] agreed outcome delivered, normally a PR
- [x] close-out committed after the outcome succeeded, or carried by the
      delivery commit where nothing could fail after it

## Design

Component: Character Discovery, UI layer only - one source file,
`04_Software/AudioMancer/src/audiomancer/ui/pages/characters_page.py`, plus
`04_Software/AudioMancer/tests/test_characters_page.py`. No public interface,
no persisted data, no new dependency; the design stage would qualify to be
skipped as a single-file change, and this note is kept short for that reason.

REQ-UX-da69ce7f. The Character Profile scroll area switches its horizontal
policy from `ScrollBarAlwaysOff` to `ScrollBarAsNeeded`. `setWidgetResizable`
stays on: it is what stretches the form when the pane is wide, and it is also
what pins the form at its own minimum when the pane is narrow, which is the
condition the bar now reports. The two settings are complementary rather than
in conflict, so no other property of the scroll area moves.

REQ-UX-c42d3a75. `_apply_main_splitter_minimums` currently derives one
`minimum_pane_width` and hands the same value to both panes. It gains two
values instead - the left pane at `width // 3`, the Evidence pane unchanged at
`width // 4` - and its docstring, plus the `resizeEvent` docstring that repeats
"one quarter", are corrected to say what the code now does.

Rejected alternative: giving the left pane a fixed pixel floor near the form's
~700-pixel need, so the bar would never appear. Rejected because it stops
scaling - on a narrow window that floor would exceed the whole splitter and
squeeze the Evidence pane out - whereas a proportional third degrades cleanly
and the scroll bar covers every width below it (REQ-UX-da69ce7f).

Test seams: both requirements attach to `test_characters_page.py` against a
real `CharactersPage` laid out at a known size - the scroll area's policy and
horizontal range for the first, `_apply_main_splitter_minimums` and the
resulting `minimumWidth` of `_left_splitter` and `_evidence_group` for the
second.

## Log

- 2026-08-17 frame scope: on the Characters page the Character Profile form is
  clipped when the main splitter is dragged left, with no way to reach the
  hidden part, and the left pane may shrink further than the operator wants.
- 2026-08-17 frame scope: in scope are the horizontal scroll policy of the
  Character Profile scroll area and the left-pane minimum width of the main
  splitter, both in `characters_page.py`.
- 2026-08-17 frame exclusions: the Evidence pane minimum stays at one quarter,
  the Evidence vertical splitter keeps its twenty percent rule
  (REQ-FUNC-7728b324), and the cramped Character List row - whose fixed
  206-pixel action-button column squeezes the list to 114 pixels - is left
  alone because that list carries its own scroll bar and nothing there is
  unreachable.
- 2026-08-17 frame measurements taken before any edit, on a page sized
  1400x900: main splitter 1378 wide, left-pane minimum 344 (1378//4), the
  Character Profile form widget minimum 676 wide against a viewport of about
  330 at the leftmost splitter position, and the horizontal scroll bar not
  visible because the policy is `ScrollBarAlwaysOff`.
- 2026-08-17 frame path: full, because no existing requirement covers either
  behaviour - a grep of `.agentic/requirements` found the Characters page
  named only for discovery, edit mode and the Evidence splitter - and both
  changes are externally observable.
- 2026-08-17 frame branch: the operator asked for the work to stay on `master`
  and for no task branch to be created, so step 4 of `1_frame.md` is
  deliberately not followed; `branch: master` records where the work lives.
- 2026-08-17 frame requirements proposed: one new REQ-UX for the Character
  Profile pane scrolling horizontally rather than hiding its content, and one
  new REQ-UX for the left pane keeping a minimum of one third of the main
  splitter width while the Evidence pane keeps one quarter.
- 2026-08-17 frame checkpoint: the operator reviewed the analysis of both
  causes in conversation and answered "Start implementation", so the scope
  above is confirmed and the task continues into specify.
- 2026-08-17 frame note: the two changes are complementary, not redundant - one
  third of 1378 is 459 pixels while the form needs about 700, so the wider
  minimum raises the floor and the scroll bar makes everything below that
  reachable; neither alone fixes the report.
- 2026-08-17 specify: wrote REQ-UX-da69ce7f for the Character Profile pane
  scrolling horizontally and REQ-UX-c42d3a75 for the one-third left-pane
  minimum, both `draft`; no spec was needed because neither behaviour has a
  format or an algorithm behind it.
- 2026-08-17 specify: reused nothing - a grep of `.agentic/requirements` for
  the Characters page found REQ-FUNC-7728b324 covering only the Evidence
  splitter's twenty percent vertical minimums, which this task does not touch.
- 2026-08-17 design: wrote a short note anyway although the single-file rule in
  `3_design.md` would allow skipping it, because the interaction between
  `setWidgetResizable` and the horizontal scroll policy is the non-obvious part
  a later reader will ask about.
- 2026-08-17 housekeeping: closed TASK-5d5aa922 to `stage: done`; it was
  delivered on `master` as 7442510 and merged by pull request #57, and its one
  unticked item is ticked as "recorded as NOT run and not claimed", which is
  what the journal already said.
- 2026-08-17 build red: command=`pytest -q
  tests/test_characters_page.py::test_characters_page_profile_pane_scrolls_horizontally_when_narrow`;
  exit=1; expected missing behavior=the Character Profile scroll area still
  reports `ScrollBarAlwaysOff`, so no horizontal bar exists to reach the
  clipped part of the form (REQ-UX-da69ce7f).
- 2026-08-17 build red: command=`pytest -q
  tests/test_characters_page.py::test_characters_page_left_pane_keeps_a_one_third_minimum`;
  exit=1; expected missing behavior=`assert 300 == 400`, the left pane still
  takes the shared one-quarter minimum of the 1200-wide splitter instead of one
  third (REQ-UX-c42d3a75).
- 2026-08-17 build: switched the Character Profile scroll area to `ScrollBarAsNeeded` (REQ-UX-da69ce7f) and split the shared `minimum_pane_width` into `splitter_width // 3` for the left pane and `splitter_width // 4` for the Evidence pane (REQ-UX-c42d3a75); `setWidgetResizable` is deliberately left on.
- 2026-08-17 build: corrected the two docstrings that still claimed "one quarter" for both panes - `_apply_main_splitter_minimums` and `resizeEvent` - so the prose matches the code.
- 2026-08-17 build honesty note: after the first red run the scrolling test was amended to show the page and pump the event loop, because a hidden widget never processes the resize; the amended test was then re-checked against the unmodified source with `git stash push` on `characters_page.py` and both tests still failed (exit 1), so the red record above holds for the test as delivered.
- 2026-08-17 build green: `pytest -q tests/test_characters_page.py` exit 0, 11 passed.
- 2026-08-17 build green: `aegis test --impacted --base HEAD` exit 0, 34 test refs selected, 49 passed in 10.85s.
- 2026-08-17 build: `ruff check src tests` clean; `aegis evolution` lists exactly the two expected files, `characters_page.py` and `test_characters_page.py`, with nothing added or removed.
- 2026-08-17 build: `check --task` exit 0 with errors=0 notes=0; the 9 warnings are all pre-existing and untouched by this task - the `ticket-ref` on REQ-UX-4753a4bf and the 8 untracked `0_Planning/` notes.
- 2026-08-17 validate review: the diff is four changed lines of behaviour plus two docstring corrections, all inside `characters_page.py`; it matches the frame scope, touches neither the Evidence pane minimum nor the Evidence vertical splitter, and adds nothing that was not asked for.
- 2026-08-17 validate portability and security: no paths, no I/O, no secrets and no error paths are involved - the change sets two Qt widget properties - so there is nothing platform-specific to weigh.
- 2026-08-17 validate operator feedback: the operator asked mid-stage for the code comments to be removed, so the four-line `#` block above the scroll policy and the `@details` paragraph added to `_apply_main_splitter_minimums` were deleted; the reasoning they carried lives in the two requirements' `rationale` fields and in `## Design` above, which is where it belongs.
- 2026-08-17 validate knowledge: `.agentic/knowledge/Character_Discovery.md` was re-read and left unchanged - it documents the discovery pipeline, its persisted document and its prompts, and says nothing about the page's splitter geometry, so no part of it became untrue.
- 2026-08-17 validate requirements: both re-read against the built code - REQ-UX-da69ce7f and REQ-UX-c42d3a75 are `active`, each names `characters_page.py` and exactly one linked test, and each verification describes the observation the test actually makes.
- 2026-08-17 validate: no `Manual:` or `Inspection:` verification exists on either requirement, so there is no manual observation owed.
- 2026-08-17 validate: after the comment removal, `ruff check src tests` clean, `pytest -q tests/test_characters_page.py` exit 0 with 11 passed, `aegis test --impacted --base HEAD` exit 0 with 49 passed, and `aegis evolution` refreshed to the final candidate - still the same two files.
- 2026-08-17 validate proof: `check --task TASK-1bcfd29c --strict` exit 0, `strict: ok`, errors=0 notes=0.
- 2026-08-17 validate limitation: `--run` was deliberately NOT used, so the full-suite half of `check --strict --run` is owed and is not claimed. The operator forbade running the full test suite in this session and said they would exercise the application by hand instead. What exists is the strict catalog at exit 0, ruff clean, and the 49-test impacted set green on the final tree.
- 2026-08-17 validate: the 9 remaining warnings are all pre-existing and none is in this task's diff - `ticket-ref` on REQ-UX-4753a4bf, which this task never opened, and `outside-layout` on the 8 untracked `0_Planning/Analysis_2026-08-10/` notes, which belong to no task.
- 2026-08-17 validate: recorded the two fixes under `## [Unreleased]` in `CHANGELOG.md` in operator language; no version was assigned, so this delivery is not a release and the version workflow is not triggered.

## Delivery report (2026-08-17)

- stage: deliver; type: fix; path: full; branch: master
- requirements:
  - REQ-UX-da69ce7f - The Characters page Character Profile pane shall scroll horizontally when narrower than its form
  - REQ-UX-c42d3a75 - The Characters page left pane shall keep a minimum of one third of the main splitter width
- diff vs task base 1fda957: 17 file(s) changed, 2715 line(s) added
- checks: errors=0 warnings=11 notes=0
- checklist: 7/8 done; open: final `check --strict --run` result recorded truthfully after all edits
- 2026-08-17 deliver: the candidate is unchanged since the recorded proof - the diff is still the same two source docstrings, the two behaviour lines in `characters_page.py` and the two new tests - so no revalidation was needed.
- 2026-08-17 deliver: the operator ran the application against this candidate and reported the Characters page behaves as asked, which is the approval this stage waits for.
- 2026-08-17 deliver outcome: a repository-local commit on `master` made by the operator, with no push, no pull request and no release; the agent was asked to stage the files and supply the message only.
- 2026-08-17 deliver: staged the two source and test files, `CHANGELOG.md`, both new requirement files, this journal with its anchor and evolution reports, and the TASK-5d5aa922 close-out; the untracked `0_Planning/Analysis_2026-08-10/` notes were deliberately left unstaged because they belong to no task.
- 2026-08-17 close: nothing can fail after this commit, so the task is closed to `stage: done` in the same commit; the full-suite half of `check --strict --run` remains owed and unclaimed, exactly as the validate limitation records.
