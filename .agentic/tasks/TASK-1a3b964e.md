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

# TASK-1a3b964e — Character Voices action row: reorder and shorten the button labels

stage: done
type: change
path: full
requirements: REQ-UX-880bcda6, REQ-UX-10020786
branch: master
base: 9bd5cc228e2763fea2d0b5e86552fdbf805db8fc
opened: 2026-08-17

## Done checklist (current stage)

- [x] validated candidate confirmed unchanged; otherwise returned to validate
- [x] validation evidence, diff, exclusions, and outcome presented
- [x] delivery confirmed by the human
- [x] journal and report included in the delivery commit
- [x] agreed outcome delivered, normally a PR
- [x] close-out committed after the outcome succeeded, or carried by the delivery commit where nothing could fail after it

## Design

Components touched: the Character Voices page widget and the interface
string tables. No service, controller, or persisted payload changes -
the buttons keep their objects, their signals, and their enable rules.

Interface change (REQ-UX-880bcda6): the five `actions_row.addWidget`
calls in `CharacterVoicesPage.__init__` are reordered to edit, save,
import, generate, preview. Construction order stays where it is; only
the insertion order into the layout carries the requirement, so the
attribute names and the `clicked` connections are untouched.

Interface change (REQ-UX-10020786): the English table maps
`character_voices.edit_prompt` to "Edit" and `character_voices.save_prompt`
to "Save"; the Romanian table maps them to "Editeaza" and "Salveaza".
The keys stay, because `apply_language` already routes both buttons
through them and no other page reads them - grepped, they are used by
the Character Voices page alone. The constructor placeholders get the
same short words so an untranslated page never shows the old phrase.

Data and storage: none. Nothing here reaches a manifest or a document.

Rejected alternative: renaming the two localization keys to
`character_voices.edit` and `character_voices.save` to match the new
words. It would touch both tables, the page, and the localization parity
test for no behavior gain, and the keys already name the action rather
than the label.

Test seams: `test_character_voices_page.py` builds a page under `qtbot`,
so REQ-UX-880bcda6 attaches to `actions_row` read back through
`page._preview_group.layout()` and its `indexOf` positions, and
REQ-UX-10020786 attaches to the button `text()` after `apply_language`
for each of "en" and "ro".

Files expected to change: `character_voices_page.py`,
`ui_state_service.py`, `test_character_voices_page.py`, and
`test_ui_localization_coverage.py` where it asserts the old Romanian
phrases.

## Log

- 2026-08-17 frame: scope is the action row under the Preview Text box on the Character Voices page - the five buttons run left to right as Edit, Save, Import Sample, Generate Sample, Preview, and the first two carry the short labels Edit and Save instead of Edit Voice Prompt and Save Voice Prompt, in both interface languages, because the long labels do not fit the row.
- 2026-08-17 frame: out of scope - the Narrator Voice page action row (it owns its own buttons and no shared label keys), the enable/disable rules, the signal wiring, the Preview/Stop Preview toggle wording, and the three unchanged labels.
- 2026-08-17 frame: path is full - the visible label text and the button order are externally observable and no existing requirement records either, so the change needs its own requirements rather than an update to one.
- 2026-08-17 frame: work stays on master with no commit and no push, and validation runs targeted tests only; the operator runs the application afterwards.
- 2026-08-17 frame: expected requirements - one UX requirement for the left-to-right order of the five actions, one UX requirement for the two shortened prompt-button labels in English and Romanian.
- 2026-08-17 specify: created REQ-UX-880bcda6 for the left-to-right order of the five action buttons and REQ-UX-10020786 for the short Edit and Save labels in both languages; no existing requirement described either, and no spec was needed.
- 2026-08-17 design: wrote the note above - two source files, no service or payload change, and the localization keys keep their names because they name the action rather than the label.
- 2026-08-17 build red: command=`pytest -q 04_Software/AudioMancer/tests/test_character_voices_page.py::test_character_voices_action_row_orders_edit_save_import_generate_preview`; exit=1; expected missing behavior=the action row still opens with Import Sample, so the edit button reports layout position 1 instead of 0.
- 2026-08-17 build red: command=`pytest -q 04_Software/AudioMancer/tests/test_character_voices_page.py::test_character_voices_prompt_buttons_carry_short_edit_and_save_labels`; exit=1; expected missing behavior=the English table still reads "Edit Voice Prompt" for the edit button instead of "Edit".
- 2026-08-17 build: the two reds are independent - one reads layout positions, the other reads button text - so neither masks the other.
- 2026-08-17 build: reordered the five `actions_row.addWidget` calls and shortened the two prompt labels in the constructor and in both string tables; both new tests pass and REQ-UX-880bcda6 and REQ-UX-10020786 are active with their linked tests.
- 2026-08-17 build: dropped the localization-coverage test from REQ-UX-10020786's linked tests - it audits a hand-picked list of Romanian strings that does not include these two buttons, so linking it would have claimed coverage it does not give; the new page test checks both languages itself.
- 2026-08-17 build: command=`aegis test --impacted --base HEAD` (30 test refs); exit=0; 548 passed in 1748s.
- 2026-08-17 validate: reviewed the diff hunk by hunk - 3 source/doc files and 1 test file, no service, controller, payload, signal, or enable-rule change, no platform-specific code, no secrets; nothing outside the framed scope.
- 2026-08-17 validate: both user guides describe the page in prose ("Edit voice prompt and preview text before sample generation") and never quote these button labels, so no help text needed changing; the `dialog.character_voices_edit_title` string keeps the long wording because it titles the edit dialog, not a button.
- 2026-08-17 validate: updated the Character Voices knowledge page with both requirement IDs and the note that the two localization keys keep their names, and added the operator-facing CHANGELOG entry under Unreleased with no version assigned.
- 2026-08-17 validate: command=`ruff check src tests`; exit=0; "All checks passed!".
- 2026-08-17 validate: command=`aegis check --task TASK-1a3b964e --strict`; exit=0; errors=0 warnings=10 notes=0, strict ok - the warnings are the nine pre-existing ones on the base tree plus CHANGELOG.md flagged only for sitting outside the source and test globs.
- 2026-08-17 validate: the `--run` half of `check --strict --run` was not executed - the operator asked for targeted tests only and runs the application themselves, so the full-suite proof is owed and not claimed here.
- 2026-08-17 validate: refreshed the evolution report after the last candidate edit - 3 modified files, 0 added, 0 removed.
- 2026-08-17 deliver: presented the candidate unchanged since the recorded proof; the operator ran the application, confirmed the new order and the short labels, and approved delivery.
- 2026-08-17 deliver: the outcome is a repository-local commit the operator makes themselves - no push, no PR, no release - so the close-out is carried by that same commit under the second form of the deliver step.
- 2026-08-17 deliver: staged the two new requirement files, this journal with its anchor and evolution reports, the knowledge page, the two source files, the page test file and CHANGELOG.md; the untracked `0_Planning/Analysis_2026-08-10/` folder is left unstaged because it belongs to no task here.
- 2026-08-17 deliver: the report above was generated before the checklist was ticked, so its "checklist: 0/6 done" line is a stale snapshot of that moment and not the delivered state.
- 2026-08-17 deliver: the full suite remains owed and unclaimed - only the impacted set ran, at the operator's instruction.

## Delivery report (2026-08-17)

- stage: deliver; type: change; path: full; branch: master
- requirements:
  - REQ-UX-880bcda6 - The Character Voices action row shall order its five actions edit, save, import, generate, preview
  - REQ-UX-10020786 - The Character Voices prompt buttons shall carry short Edit and Save labels
- diff vs task base 9bd5cc2: 18 file(s) changed, 2684 line(s) added
- checks: errors=0 warnings=11 notes=0
- checklist: 0/6 done; open: validated candidate confirmed unchanged; otherwise returned to validate; validation evidence, diff, exclusions, and outcome presented; delivery confirmed by the human; journal and report included in the delivery commit; agreed outcome delivered, normally a PR; close-out committed after the outcome succeeded, or carried by the delivery commit where nothing could fail after it
