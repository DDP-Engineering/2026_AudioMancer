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

# TASK-b4e61cf1 — Purge the retired tts_runtime_api_key from stored and packaged settings

stage: done
type: fix
path: full
requirements: REQ-SEC-ddb1f692
branch: master
base: 610c317a4099a99a8b91acd9375b447e605bb5a2
opened: 2026-08-22

## Done checklist (current stage)

- [x] validated candidate confirmed unchanged; otherwise returned to validate
- [x] validation evidence, diff, exclusions, and outcome presented
- [x] delivery confirmed by the human - closed on request with no commit
- [ ] journal and report included in the delivery commit - no commit was made
- [x] agreed outcome delivered - an uncommitted working tree, by constraint
- [ ] close-out committed after the outcome succeeded - not committed

## Design

- Interface: `_validate_settings_internal` gains no parameter and no new
  public function; the prune runs inside it, right after the loop that fills
  missing defaults, so every key the schema defines is present before any key
  is judged unknown (REQ-SEC-ddb1f692).
- Data: the factory defaults returned by `build_default_settings` become the
  single allow-list for persisted keys, replacing the two hand-maintained
  tuples of deprecated and retired names, which the prune subsumes exactly
  (REQ-SEC-ddb1f692).
- Data: the `ui_text_scale` migration keeps running before the prune, because
  it converts a legacy key into two current keys rather than discarding it
  (REQ-SEC-ddb1f692).
- Rejected alternative: adding the one missing name to the retired tuple was
  rejected because it leaves the same trap armed for the next removed field,
  and because it reintroduces the per-key legacy recognition the VoiceWeaver
  hard break deliberately removed (REQ-SEC-ddb1f692).
- Packaging: both release packagers filter the copied `settings.json` against
  the same factory default key set, read once from the app environment, which
  retires the named `tts_runtime_device_diagnostics` exclusion in each script.
  This is a delivery operation outside AEGIS scope and carries no requirement.
- Test seam: `settings_service.validate_settings` is called directly with a
  defaults payload carrying one undefined key, and the returned payload is
  inspected (REQ-SEC-ddb1f692).

## Log

- 2026-08-22 frame: Scope is to make persisted settings carry no key outside the current schema, so a value retired from the schema cannot survive on disk or be copied into a delivery archive.
- 2026-08-22 frame: In scope are `settings_service._validate_settings_internal` and the settings-copy step of both release packagers; out of scope are the settings UI, the schema itself, any per-key migration of a removed value, and the release-notes wording.
- 2026-08-22 frame: Path is full because this changes data-handling behavior for stored operator secrets, which `1_frame.md` puts outside the quick path.
- 2026-08-22 frame: The defect is that `_validate_settings_internal` copies the incoming payload wholesale and only pops names listed in two hand-maintained tuples, so `tts_runtime_api_key` - dropped from the schema and the UI without being added to either tuple - round-trips untouched.
- 2026-08-22 frame: The user chose the generic remedy over naming the key, so validation will drop every key absent from the factory defaults and both packagers will filter the copied settings against that same default key set.
- 2026-08-22 frame: The defect is latent on this machine - the operator `settings.json` key set matches the factory defaults exactly and holds no `tts_runtime_api_key`.
- 2026-08-22 frame: The release-notes line "cleaned of operator API keys" was checked and is not false, because both packagers still blank every `llm_profiles[].api_key`; no wording change is owed.
- 2026-08-22 frame: Expected requirement is one new REQ-SEC stating that validated settings retain only current schema keys; the packager change is a delivery operation outside AEGIS scope and carries no requirement.
- 2026-08-22 frame: Scope, path and the single proposed requirement were confirmed by the user at the frame checkpoint.
- 2026-08-22 specify: Created REQ-SEC-ddb1f692 for schema-only persistence; `check` reported zero errors and only the pre-existing warnings inherited from the previous commit.
- 2026-08-22 design: Design note written; no knowledge page owns an `## Architecture` diagram for the settings service and the component graph is unchanged, so no diagram revision is owed.
- 2026-08-22 build red: command=`uv run --no-sync pytest -q tests/test_settings_service.py::test_settings_drop_every_key_the_factory_defaults_do_not_define`; exit=1; expected missing behavior=a settings file carrying a key the schema does not define loaded unchanged and logged "without requiring repairs", so the value was never rewritten away.
- 2026-08-22 build: Repository anchor recorded at 610c317 over 324 files after the red test and before implementation edits.
- 2026-08-22 build: Replaced the two hand-maintained deprecated and retired name tuples with one prune of every key the factory defaults do not define, and pointed both release packagers at that same default key set instead of their named `tts_runtime_device_diagnostics` exclusion.
- 2026-08-22 build: DEVIATION `test_validate_settings_preserves_unknown_extra_keys` asserted the opposite behavior and was deleted, and its entry removed from REQ-PLAT-046b2de7 - the forward-compatibility affordance it protected is exactly what let a retired secret survive, and the cost is that an older build now discards keys a newer build wrote.
- 2026-08-22 build: `test_load_settings_repair_write_oserror_returns_validated_settings` used an unknown key as its do-not-log content marker; the marker moved to a schema field that is repaired the same way, preserving the test's intent.
- 2026-08-22 build: Both packagers were exercised against a settings file seeded with `tts_runtime_api_key`, and each produced a packaged payload without that key that then validated with `repairs_made = False`, satisfying the delivery clean-load assertion.
- 2026-08-22 build: DEVIATION the user forbade running the whole suite, so `test --impacted` was replaced by the 241 tests of the settings, settings-UI, config, atomic-IO and theme files; the cost is that regressions outside those files would not be seen here.
- 2026-08-22 build: `uv run ruff check` passed on both changed Python files; `ruff format --check` reports drift on both, but the same drift is present at HEAD and was not introduced by this task.
- 2026-08-22 build: Evolution review found the five expected changed files with no additions or removals.
- 2026-08-22 build: `check --task` reported zero errors and four accepted warnings - one unrelated pre-existing ticket reference and three delivery files outside the configured layout.
- 2026-08-22 validate: Semantic diff review found the candidate matches the frame scope and the design note, touches no UI or schema surface, keeps the `ui_text_scale` migration ahead of the prune, and adds no unrequested work.
- 2026-08-22 validate: Reviewed the log surface deliberately - the repair message names the removed key but never its value, so a stored secret is not written to the log when it is discarded.
- 2026-08-22 validate: Portability reviewed - the Linux cleaner runs its heredoc through `uv run` in a `cd` subshell under `set -euo pipefail`, and the Windows cleaner reads the key list once from the same environment without redirecting native stderr.
- 2026-08-22 validate: Updated `.agentic/knowledge/Platform_Settings_UI.md`, which still claimed unknown future keys are preserved unless an explicit migration removes them.
- 2026-08-22 validate: REQ-SEC-ddb1f692 re-read; status, prose, verification, affected paths and linked tests describe the built behavior, and no other requirement asserted the preservation this task removed.
- 2026-08-22 validate: DEVIATION `check --task --strict --run` was run without `--run` because the user forbade the full suite; the repository-wide proof this stage owes was not performed, and only the settings-related set backs this candidate.
- 2026-08-22 validate: command=`python .agentic/aegis.py check --task TASK-b4e61cf1 --strict`; exit=0; result=WARN with zero errors, `strict: ok`, and four accepted warnings - one unrelated pre-existing ticket reference and three delivery files outside the configured layout.

## Delivery report (2026-08-22)

- stage: deliver; type: fix; path: full; branch: master
- requirements:
  - REQ-SEC-ddb1f692 - Validated settings shall retain only current schema keys
- deviations: none recorded
- diff vs task base 610c317: 12 file(s) changed, 2045 line(s) added
- checks: errors=0 warnings=5 notes=0
- checklist: 2/6 done; open: delivery confirmed by the human; journal and report included in the delivery commit; agreed outcome delivered, normally a PR; close-out committed after the outcome succeeded, or carried by the delivery commit where nothing could fail after it

## Close-out

- 2026-08-22 deliver: The user asked to close the task and the standing repository constraint forbids committing, so the agreed outcome is an uncommitted working tree on `master`; no delivery commit, PR, tag, or publication was made.
- 2026-08-22 deliver: The candidate handed over is exactly the tree the strict check described - `settings_service.py`, `test_settings_service.py`, both packagers, `CHANGELOG.md`, `Platform_Settings_UI.md`, `REQ-SEC-ddb1f692`, and the unlinked test entry in `REQ-PLAT-046b2de7`.
- 2026-08-22 deliver: The delivery report printed "deviations: none recorded" because the four deviation notices live as `DEVIATION` log lines rather than in a form the report counts; they stand and are listed below.
- 2026-08-22 deliver: Open deviations at close - the deleted forward-compatibility test, the focused suite in place of `test --impacted`, the strict check run without `--run`, and TASK-be95a1a6 closed with its own build checklist unticked.
- 2026-08-22 deliver: Nothing outward-facing succeeded or failed after this line, because nothing outward-facing was attempted; the change reaches users only when someone commits and releases it.
