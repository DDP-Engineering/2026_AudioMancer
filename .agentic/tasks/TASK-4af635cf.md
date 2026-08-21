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

# TASK-4af635cf — Treat the operator token cap as a soft target and split only at the model hard maximum

stage: done
type: change
path: full
requirements: REQ-FUNC-79fd5f3a, REQ-FUNC-46959c54
branch: master
base: 1df2c2564cd41b2609f73d45d5ffe538c4f66876
opened: 2026-08-20

## Done checklist (current stage)

- [x] requirements written and linked to tests
- [x] failing tests written first, then the implementation, until green
- [x] impacted regression set run and green
- [x] knowledge pages and changelog updated
- [x] strict check recorded truthfully
- [x] files staged, commit message handed to the operator

## Log

- 2026-08-20 frame: the operator token cap (Max Block Tokens, default 1024) currently
  forces every generated part under itself, so a long sentence is cut mid-sentence; it
  must become a packing target while only the model's reported `hard_maximum` (8192 for
  Qwen3-TTS-12Hz-1.7B-Base) may break a sentence.
- 2026-08-20 frame: sentence is the atomic unit; clause and word-group splitting stay,
  but only above the hard ceiling.
- 2026-08-20 frame: excluded - `plan_narrator_blocks` already keeps sentences whole and
  needs no change; no UI change; no new warning flag.
- 2026-08-20 frame: full path, because generation requests must also size `max_new_tokens`
  per part or a between-thresholds part is truncated by the runtime.
- 2026-08-20 frame: DEVIATION frame - working on master with no task branch, at the
  operator's standing instruction; they review the working tree in the running app and
  keep authorship of the commit.
- 2026-08-20 specify: REQ-FUNC-79fd5f3a governs the two-threshold splitting rule and
  REQ-FUNC-46959c54 the per-part generation ceiling that keeps a kept-whole sentence
  from being truncated by the runtime.
- 2026-08-20 design: the budget payload carries both numbers - `safe_word_count` from
  the operator-capped tokens as the packing target, and a new `hard_word_count` derived
  from the runtime's `hard_maximum`, falling back to the uncapped model budget when the
  runtime does not report one. Sentence stays the atomic unit; clause and word-group
  splitting survive but engage only above the hard ceiling. `plan_narrator_blocks`
  already behaves this way and is left alone.
- 2026-08-20 build: six tests written red first (2 budget, 2 normalization,
  2 generation-planner) plus 2 driving a recorded generation for the per-part
  ceiling; all green after the implementation.
- 2026-08-20 build: `hard_maximum` is the ceiling at the operator's decision, so a
  natural-prose sentence is effectively never cut - 8192 tokens is about 1365 words.
- 2026-08-20 validate: impacted set selected by following `affected_paths` back from
  every requirement naming a touched source file - 27 modules, 618 passed, 1 skipped,
  exit 0. `ruff check` clean on all six changed files.
- 2026-08-20 validate: `check --task TASK-4af635cf --strict` reports errors=0,
  warnings=20, notes=1, strict: ok.
- 2026-08-20 validate: DEVIATION validate - the full suite was not run, at the
  operator's standing instruction; they verify by running the application by hand.
  `check --strict` was therefore run without `--run`.
- 2026-08-20 validate: DEVIATION validate - the `uncovered-source` warnings name files
  this task never touched. They belong to TASK-928fbc46 and TASK-8be78471, still staged
  and uncommitted, so the diff from this task's base includes them; their own
  requirements cover them.
- 2026-08-20 deliver: staged, uncommitted; the operator commits.
