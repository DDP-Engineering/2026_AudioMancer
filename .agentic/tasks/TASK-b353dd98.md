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

# TASK-b353dd98 — Scope the scene ambience negative prompt to a short core plus scene-specific exclusions

stage: done
type: change
path: full
requirements: REQ-FUNC-a80dacf7, REQ-UX-c52f02c1
branch: master
base: 1df2c2564cd41b2609f73d45d5ffe538c4f66876
opened: 2026-08-20

## Done checklist (current stage)

- [x] scope agreed, requirements written
- [x] failing tests first, then implementation, until green
- [x] impacted regression set green
- [x] knowledge and changelog updated
- [x] strict check recorded truthfully
- [x] files staged, commit message handed to the operator

## Log

- 2026-08-20 frame: the shipped ambience prompts tell the model to paste one 13-term
  negative list on every block. Six of those terms - continuous beep, pure sine wave,
  single tone, alarm, loud bass drone, harsh buzzing - suppress periodicity, so a
  ticking clock, dripping tap or idling engine is fought on every block whether or not
  the scene wanted it. Scene-specific exclusions were written into a universal default.
- 2026-08-20 frame: a second, shorter 7-term default is hardcoded in
  `_normalize_scene_ambience_response` and disagrees with the prompts. No shared
  constant, no setting, no requirement covers any of it.
- 2026-08-20 frame: scope - one configurable core carried through settings into both
  the rendered prompt and the fallback, plus an instruction to add scene-specific
  exclusions only where they contradict the sound just described.
- 2026-08-20 frame: excluded - the per-block Negative Prompt editor on Speech Blocks
  already exists and is unchanged.
- 2026-08-20 frame: the operator accepted that existing generated ambience is
  invalidated; `negative_prompt` sits in both fingerprints, so every ambience clip is
  regenerated. Compatibility is explicitly not required.
- 2026-08-20 frame: DEVIATION frame - working on master with no task branch, at the
  operator's standing instruction.
- 2026-08-20 specify: REQ-FUNC-a80dacf7 governs the one configured core reaching both
  the prompt and the fallback, and the absence of periodicity terms from every shipped
  default; REQ-UX-c52f02c1 governs the operator-editable field.
- 2026-08-20 design: `_scene_ambience_negative_prompt_core()` is the single reader.
  The core rides on the normalized scene-ambience settings payload, so it reaches the
  user prompt as `{negative_prompt_core}` and the omitted-field fallback by the same
  route. The system prompt states the policy and names no list, so the list exists in
  exactly one place. `DEFAULT_SCENE_AMBIENCE_NEGATIVE_PROMPT` drops the six periodicity
  terms and adds `melody`, which the old fallback lacked.
- 2026-08-20 build: six tests written red first - three on the core reaching prompt,
  fallback and model-chosen exclusions, one asserting no shipped default names a
  periodicity term, two on the settings page round trip and its empty-field fallback.
- 2026-08-20 build: one existing test pinned the retired thirteen-term string in the
  system prompt; repointed at the new policy line and the rendered core.
- 2026-08-20 build: DEVIATION build - the untracked local `settings.json` needed the
  new key, because a source checkout resolves `APP_DEFAULT_SETTINGS_PATH` there and the
  scaffold tests read it. Patched through the application's own atomic writer.
- 2026-08-20 build: also sharpened the collapse-avoidance rule in both prompts, which
  named "low beep" and "alarm" and reinforced the same bias from the positive side.
- 2026-08-20 validate: impacted set selected by following `affected_paths` back from
  every requirement naming a touched file - 55 modules, 1115 passed, 1 skipped, pytest
  exit 0 in 23m40s. `ruff check` clean on all seven changed files.
- 2026-08-20 validate: `check --task TASK-b353dd98 --strict` reports errors=0,
  warnings=21, notes=1, strict: ok.
- 2026-08-20 validate: DEVIATION validate - the full suite was not run, at the
  operator's standing instruction; `check --strict` ran without `--run`.
- 2026-08-20 validate: DEVIATION validate - the `uncovered-source` warnings name files
  from the three earlier staged-but-uncommitted tasks, which the diff from this task's
  base includes; their own requirements cover them.
- 2026-08-20 deliver: staged, uncommitted; the operator commits.
