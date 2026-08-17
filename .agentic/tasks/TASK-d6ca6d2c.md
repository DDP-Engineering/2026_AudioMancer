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

# TASK-d6ca6d2c — Regenerate both user guides from the implemented frontend

stage: done
type: change
path: full
requirements: REQ-UX-f6ddf594
branch: master
base: f86b943088b7ab789cd32a2703886543dda82218
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

The regeneration is a rewrite of prose, not of structure. Both guides keep
their section ids, their table of contents, their `help.css` classes and
their existing screenshots, because those are the anchors the packaged Help
action opens and the operator navigates by. What changes is the body of every
section: each statement is rewritten from the widget that implements it.

**Evidence rule.** A control may be described only when a page module
constructs the widget and adds it to a layout. The runtime English string is
then read from the `translate()` key that widget uses, and the Romanian
string from the same key in the `ro` half of the catalog, so the two guides
name the same control in each language without inventing a translation.

The reverse direction is forbidden. `services/ui_state_service.py` carries
dead keys for controls that were removed — a whole theme editor
(`settings.theme_new`, `theme_duplicate`, `theme_delete`, `theme_import`,
`theme_export`), the cleanup spacing controls (`text_cleanup.spacing_*`,
`apply_spacing`), a separate `text_cleanup.ai_clean` button, the per-page
status groups, and the Character Voices assignment boxes. The previous guide
described several of these, which is how the drift is best explained: the
catalog was treated as the inventory. It is not one.

**What the audit established.** Statements that describe controls the
frontend never builds: the Text Cleanup spacing categories and Apply
Spacing; a Cleanup instructions prompt; a cleaned-text edit confirmation;
operator approval on Text Cleanup, Text Chunking, Characters and Character
Voices; a Characters voice-definition regeneration button. Wrong labels:
Save vs **Apply** in AI and TTS Settings, Generate Narrator Profiles vs
**Generate Narrators**, Re-split vs **Split Chunk**, Restart vs **Reset
Translation**, "Automatic (model limit)" vs **Auto**, Play/Stop vs **Play
Audio**/**Stop Playing**, and a "Default Light" theme that is not among the
eleven built-ins. Wrong geometry: the cleanup panes use a shared size-hint
minimum rather than one third, Audio Blocks uses one quarter, Speech Blocks
uses `max(300, min(480, 40%))` against a zero minimum, and the narrator
profile pane is a fixed 220 px with a maximum the guide never mentioned.

**The approve question, decided.** Cleanup, Chunking, Characters and
Character Voices genuinely have no approval control; downstream work unlocks
from operation status. The guides now say so. The gap is recorded in the
changelog so the absence can be judged on its own, rather than being hidden
behind documentation that quietly asserts the feature exists.

**Rejected alternative — correct only the false sentences.** That keeps the
guides internally consistent but leaves them incomplete: whole features
carry no documentation at all, including the Find/Find Next context menus,
the Play Audiobook sequential playback with timed pause silence, the Home
workflow pipeline and export format selector, the Approve All controls, and
the debounced translation autosave that clears approval. An operator cannot
discover those from a guide that omits them, so the rewrite adds them.

**Verification seam.** REQ-UX-f6ddf594 is settled by inspection, not by a
test: the observation is that each named control resolves to a constructing
widget. There is no automated assertion to write, and inventing one that
greps the catalog would test the wrong artifact — the catalog is exactly the
source that misled the previous guide.

## Log

- 2026-08-17 frame: scope is a full rewrite of the section prose in
  `05_SoftwareDocu/UserGuide/index.html` and `05_SoftwareDocu/UserGuide_ro/index.html`
  from the implemented frontend, keeping section ids, the table of contents,
  `help.css` and the existing screenshots.
- 2026-08-17 frame: out of scope are the application code, the screenshot
  images themselves, `help.css`, the two model-recommendation documents in
  `05_SoftwareDocu/`, and any version bump — this is not a release.
- 2026-08-17 frame: full path, because the operator-visible content of a
  shipped artifact changes wholesale and no existing requirement covered
  guide accuracy.
- 2026-08-17 frame: stayed on `master` at the operator's standing
  instruction for this repository rather than opening a task branch.
- 2026-08-17 frame: expected one new requirement — both guides describe only
  controls the frontend presents.
- 2026-08-17 frame: operator chose full rewrite from the code, chose to
  document the missing approval controls as they actually are, and chose to
  keep the existing screenshots and correct their captions.
- 2026-08-17 specify: created REQ-UX-f6ddf594, verified by inspection
  because the behavior is a property of prose against widgets.
- 2026-08-17 design: recorded the evidence rule, the dead-catalog-key trap
  that explains the drift, and the rejected minimal-correction alternative.
- 2026-08-17 build: audited all fifteen page modules, the shell, both
  dialogs and every controller against both guides before editing, and
  recorded the false statements, the wrong labels, the wrong geometry and
  the undocumented features in the design note above.
- 2026-08-17 build: rewrote every section of both guides from that audit,
  keeping the section ids, the table of contents, `help.css` and the
  screenshots unchanged.
- 2026-08-17 build: REQ-UX-f6ddf594 is verified by inspection, so there is no
  red record to show; the observation is recorded under validate below.
- 2026-08-17 build: process defect - the repository anchor was taken after
  the edits rather than before them, so `TASK-d6ca6d2c.evolution.json` reports
  0 changed files and carries no evidence; `git diff --stat` against the task
  base f86b943 is the honest substitute and is recorded under validate.
- 2026-08-17 validate: inspection of REQ-UX-f6ddf594 - every control, label,
  option list, numeric limit and dialog named in either guide was traced to
  the page module that constructs it, and the runtime string read from the
  `translate()` key that widget uses; no statement survived that lacks a
  constructing widget.
- 2026-08-17 validate: confirmed the drift cause and removed it from both
  guides - the previous text described controls that exist only as dead
  `_UI_STRINGS` keys, including the theme editor, the Text Cleanup spacing
  categories and the per-page status panes.
- 2026-08-17 validate: recorded the four pages with no approval control
  (Text Cleanup, Text Chunking, Characters, Character Voices) as they are,
  and named the gap in `CHANGELOG.md` so it can be judged separately.
- 2026-08-17 validate: both files parse with matched section, figure, table,
  list and div tags; every table-of-contents anchor resolves to a section in
  the same order; all thirteen referenced screenshots exist in both bundles.
- 2026-08-17 validate: normalized both guides to pure ASCII with `&mdash;`
  entities, matching the convention of the files they replace, and normalized
  the knowledge page and the new requirement to LF endings.
- 2026-08-17 validate: `uv run pytest tests/test_package_import.py` - 1 passed,
  exit 0; all six version surfaces across the two guides still read 2.0.0 and
  agree with `pyproject.toml`.
- 2026-08-17 validate: `git diff --stat` vs f86b943 - 4 files changed, 1468
  insertions, 777 deletions, across the two guides, the knowledge page and
  the changelog.
- 2026-08-17 validate: `check --task TASK-d6ca6d2c --strict` - errors=0
  warnings=12 notes=1, strict ok; eleven warnings are `outside-layout` on
  documentation paths this task exists to change, one is a pre-existing
  ticket-ref warning on the unrelated REQ-UX-4753a4bf.
- 2026-08-17 validate: `check --strict --run` and the full suite were not run,
  at the operator's standing instruction for this repository; this task
  changes no application code, and the one code-adjacent surface it could
  affect - the release-version test - was run directly and passed. The full
  suite remains owed and unclaimed.
- 2026-08-17 deliver: no version assigned - the guides were corrected against
  the shipped 2.0.0 application, so this is not a release and the four version
  surfaces are deliberately untouched.
- 2026-08-17 deliver: `0_Planning/Analysis_2026-08-10/` stays untracked and
  out of the delivery; it belongs to no task here.
- 2026-08-17 deliver: reported to the operator that the Character Voices
  screenshot predates commits 9bd5cc2 and 8187391 and still shows the removed
  language boxes and the old button order - its caption now says so, and the
  image itself is left for the operator to recapture.
- 2026-08-17 deliver: reported two Romanian catalog strings that read wrongly
  in the running interface - `character_voices.readiness_not_ready` renders
  "negata" for "not ready", and `audio_blocks.marker_pending` renders the
  token "in_asteptare" with an underscore. Both are application strings, out
  of this task's scope, and are not repeated in the Romanian guide.

- 2026-08-17 deliver: operator extended the scope to fix the Romanian strings
  reported above, in this task and on this branch, so the work returned to
  build for a three-line correction before delivery is confirmed.
- 2026-08-17 build: corrected `audio_blocks.marker_pending` from the raw token
  "in_asteptare" to "in asteptare", and the Character Voices readiness pair
  from "gata"/"negata" to "pregatit"/"nepregatit" - "negata" reads as *denied*
  rather than *not ready*, and the new pair matches the wording already used by
  `home.export_status.not_ready` and `audio_assembly.scene_mix_ready`.
- 2026-08-17 build: changed the "ready" half as well as the "not ready" half
  the operator named, because "gata"/"nepregatit" would have been a mismatched
  pair on one status line; recorded here as a deliberate third edit rather
  than left silent.
- 2026-08-17 build: no new requirement raised - the change corrects three
  presentation strings, adds no behavior, and both keys are display-only
  (`character_voices_state_service.py:347-349` composes a status note,
  `audio_blocks_page.py:753-755` composes a list row); neither value is parsed
  or compared anywhere.
- 2026-08-17 validate: `uv run pytest tests/test_localization_parity.py
  tests/test_ui_state_service.py tests/test_ui_localization_coverage.py
  tests/test_character_voices_service.py tests/test_audio_blocks_state_service.py
  tests/test_settings_page.py` - 69 passed, exit 0; the parity test compares
  catalog keys rather than values, so it constrains the fix not at all and is
  named here as weak evidence.
- 2026-08-17 validate: `uv run ruff check` on the changed module - all checks
  passed; `git diff --stat` shows 3 insertions, 3 deletions in that file.
- 2026-08-17 validate: the full suite was again not run, at the operator's
  instruction, and remains owed and unclaimed.
- 2026-08-17 deliver: the delivery report below predates this correction, so
  its file and line counts describe the guides-only candidate; the current
  candidate is that plus the three-line change to `ui_state_service.py` and one
  changelog bullet.

- 2026-08-17 deliver: operator confirmed delivery after reviewing the rewritten
  guides and the Romanian string correction.
- 2026-08-17 deliver: outcome is a repository-local commit the operator makes
  themselves on `master` - no push, no PR, no release - so close-out is written
  before the commit and the same commit carries it.
- 2026-08-17 deliver: staged nine files by explicit path - both guides, the
  knowledge page, the changelog, `ui_state_service.py`, the new requirement,
  and the three task artifacts; `0_Planning/Analysis_2026-08-10/` was left
  untracked because it belongs to no task here.
- 2026-08-17 deliver: closing evidence for the final candidate - 69 targeted
  tests passed, `ruff check` clean on the one changed module,
  `check --task TASK-d6ca6d2c --strict` errors=0 warnings=15 notes=1 strict ok,
  and `test_package_import.py` passed with all six guide version surfaces
  reading 2.0.0.
- 2026-08-17 deliver: the fifteen check warnings are fourteen `outside-layout`
  notices on documentation paths - the guides, the changelog and the untracked
  planning folder - plus one pre-existing ticket-ref warning on the unrelated
  REQ-UX-4753a4bf; none are introduced defects.
- 2026-08-17 deliver: two debts leave this task open in the repository, both
  named rather than closed - the full suite was never run, and the Character
  Voices screenshot in both bundles still shows the four removed language boxes
  and the old button order, with its caption saying so until the operator
  recaptures it.

## Delivery report (2026-08-17)

- stage: deliver; type: change; path: full; branch: master
- requirements:
  - REQ-UX-f6ddf594 - Both offline user guides shall describe only controls the frontend actually presents
- diff vs task base f86b943: 16 file(s) changed, 4156 line(s) added
- checks: errors=0 warnings=13 notes=1
- checklist: 3/6 done; open: delivery confirmed by the human; agreed outcome delivered, normally a PR; close-out committed after the outcome succeeded, or carried by the
