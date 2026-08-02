<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage 5 — deliver

**Purpose:** Prove the whole repo is still good — not just the part you
touched — refresh the component knowledge, write the report, and publish.

**Read first:**

- `.agentic/PROJECT.md` — this repository's binding code style and its
  four-place version workflow (changelog, project, both help files).
  Its "Delivery checklist additions" are part of this stage's Done list.
- The task journal `.agentic/tasks/TASK-<id>.md`, whole file.
- Every requirement on its `requirements:` line.
- The knowledge page of each component you touched, and
  `.agentic/templates/component.md`.

**Steps:**

1. Prove the repo: `python .agentic/aegis.py check --task TASK-<id>
   --strict --run` — name the task, so the diff checks are scoped to it
   and a branch mismatch is reported. One
   pass runs every configured command — including the **full** test suite
   (the impacted set was the inner loop; it is not enough here) — plus
   all fifteen checks. Errors are objectively broken files: fix them.
   For each remaining warning, either fix it or accept it with a one-line
   reason in the log:
   `- <date> deliver: accepted <check> on <path> because <reason>`.
   Distinguish failures: one **your diff introduced** must be fixed here;
   one that already fails on the base branch is logged as a future task
   (`- <date> deliver: pre-existing failure <test> - out of scope`), not
   silently absorbed into this one. Then record the **actual** result in
   one log line — this is what the report's counts point back to:
   `- <date> deliver: check --strict --run exit 0 (<N> tests passed)` or
   `... exit 1 - only pre-existing failures, listed above as out of scope`.
   Never write "green" over a non-zero exit. Note: CI running the same
   command will fail on that debt too — flag it in the PR description so
   the team decides (fix it, or waive it at team level) with open eyes.
   Note: `check --run` executes only verification commands — it skips
   side-effect-looking names unless `[check] run` lists them; deployment
   commands do not belong in `[commands]` at all. It also proves only
   what your config covers: "the full suite ran" is true because
   `[commands] test` *is* your suite and `[check] run` does not exclude
   it. If you see `run: test skipped`, the suite did not run — say so in
   the log instead of claiming it did.
2. Review the diff — semantically, hunk by hunk, against: the scope and
   exclusions in the frame log, each requirement's prose and
   `verification`, the design note, **`01_Documentation/Code_Style.md`**,
   error paths, Windows/Linux portability, secrets and security, and
   anything changed that nothing asked for. A wrong assumption sends you **back**: set `stage:` to
   `specify` or `design`, **replace the checklist with that stage's "Done
   when" list**, log why, and stop — do not patch over it here. An
   implementation flaw goes back to `build`, same protocol.
3. Update the component knowledge. For every component whose behavior,
   interface, or file set materially changed, update or create
   `.agentic/knowledge/<component>.md` from the template — keep
   **Purpose**, **Public interface**, **Key behaviors** (with requirement
   IDs) and **Files** true. A new component gets a new page. This is the
   page a future session loads instead of re-reading the source.
4. Re-read each requirement: `status = "active"` (or `"retired"` where
   this task deliberately removed the behavior, with the reason in the
   prose), the prose still describes what you built, `verification`
   still matches how the test checks it, and every `linked_tests` entry
   points at a test that exists.
5. The log is **append-only** — never rewrite or delete log lines. If
   the journal has grown very long, add one summary line pointing at the
   span it summarizes; the history stays.
6. **Stop and present** — in both interaction modes: the suite and check
   results, the diff summary, what you are about to commit, and the
   intended outcome (see step 8). Wait for a yes.
7. Prepare the delivery commit: tick every checklist item **except the
   close-out item**, keep `stage: deliver`, log the delivery decision,
   then generate the summary —
   `python .agentic/aegis.py report TASK-<id>` — and read it; correct
   anything wrong. Journal and report ride inside the delivery commit.
8. If this task is a **release**, apply the four-place version workflow
   from `.agentic/PROJECT.md` now — changelog, project (two files), both
   help files — and run its two `git grep` verifications before
   committing. A release commit that bumps only some of the four is the
   failure this step exists to prevent.
9. Deliver the agreed outcome:
   - **Commit** on the task branch, message naming the requirement IDs —
     always.
   - **PR** (the default outcome). If CI runs `check --strict --run`,
     that is the gate that decides the merge.
   - **Release or deployment** beyond the PR happens only via the repo's
     own release process, with its own explicit approval and its own
     post-release verification, logged in the journal. This workflow
     ends at the PR unless the owner asked for more.
   - Degraded environments, stated honestly: no remote → stop after the
     commit and say there is no PR to open; no git at all → stop after
     the presentation and say the outcome cannot be delivered here.
10. **Close out only after the outcome succeeded**: set `stage: done`,
   tick the close-out item, log one line, and make a small close-out
   commit on the same branch — then push it, so the PR carries it. If
   anything failed (commit rejected, PR impossible, release broke), log
   the failure and leave `stage: deliver` — the journal then tells the
   truth, and `status` still shows the task as open work. A `done`
   journal must never claim a delivery that did not happen.

**Outputs:**

- The recorded suite and strict-check result in the journal log.
- Updated or created `.agentic/knowledge/<component>.md` pages.
- **Delivery commit:** the work, the delivery report, and the journal
  with `stage: deliver` and the close-out item still unticked.
- The agreed outcome (PR by default).
- **Close-out commit** (pushed after the outcome succeeded): the journal
  with `stage: done` and every item ticked.

**Done when:**

- [ ] `check --strict --run` green — where "green" means: no errors, no
      failures the diff introduced, warnings fixed or explained, and any
      pre-existing base-branch failures logged as out-of-scope future
      tasks; the evidence line is in the log
- [ ] diff reviewed against scope, requirements, design, error paths,
      portability, security — no unrequested changes
- [ ] knowledge pages updated for every materially changed component
- [ ] requirements re-read: status, prose, verification, links all true
- [ ] delivery confirmed by the human before the commit
- [ ] journal and report inside the delivery commit; agreed outcome
      delivered (PR by default)
- [ ] close-out: `stage: done` set and committed only after the outcome
      succeeded
- [ ] the project items from `.agentic/PROJECT.md` ("Delivery checklist
      additions") — code style, and for a release the four-place version
      workflow

**Skip when:** Never, on either path. The quick path only means there was
no design note to summarize; the suite, the strict check, the diff
review, the knowledge update, and the report all still happen.
