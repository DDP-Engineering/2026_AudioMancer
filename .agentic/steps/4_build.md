<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage 4 — build

**Purpose:** Implement the linked requirements test-first, one at a time,
using the impacted-test set as the fast inner loop, and keep the
requirement links current so that set stays correct.

**Read first:**

- The task journal `.agentic/tasks/TASK-<id>.md`, including `## Design`.
- Every requirement on its `requirements:` line, and their specs.
- The existing tests for the files you are about to touch.

**Steps:**

1. Pick one requirement. Work it to green before starting the next — do
   not open several at once.
2. Write or extend a test that expresses that requirement's
   `verification` and fails for the right reason. Write the test
   **before** you touch any implementation file.
3. Run the test and watch it fail. Confirm the failure is the one you
   expect (missing behavior), not a typo, an import error, or a bad
   fixture.
4. Note the observed failure in `## Log` before implementing, one line:
   `- <date> build: tests/x.py::test_y red as expected (<reason>)`.
   This line is the evidence that the test came first; if it is missing,
   the test did not.
5. Implement the smallest change that makes the test pass. Resist adding
   behavior no requirement asks for.
6. Maintain the links **now, before running the focused set**:
   - add each source path you changed to that requirement's
     `affected_paths` (forward slashes, repo-relative);
   - add each new or changed test to `linked_tests` as
     `tests/path.py::test_name`;
   - set `status = "active"` and refresh `updated`.
   These two lists are what select the impacted set. Link first: an
   unlinked new test would not be in the set, and a changed source file
   no requirement covers makes `--impacted` refuse and fall back to the
   full suite (by design).
7. Run `python .agentic/aegis.py test --impacted` as the inner loop. It
   runs only the tests linked to requirements whose `affected_paths` you
   touched, so it is fast enough to run after every edit. Repeat steps
   2–7 until the requirement is done.
8. Move to the next requirement and repeat from step 1.
9. When all requirements are green, run `python .agentic/aegis.py check`.
   Fix what it flags, or record in one log line which warning you accept
   and why.
10. Tick the checklist, set `stage: deliver`, and **replace
    `## Done checklist`** with the deliver stage's "Done when" list from
    `5_deliver.md` — the checklist always shows the current stage's items.

**Outputs:**

- New and changed tests, and the implementation that satisfies them.
- Updated `affected_paths`, `linked_tests`, `status` on each requirement.
- Journal log lines: one red-test line per requirement, plus any accepted
  warning.

**Done when:**

- [ ] a failing test was written and observed red for each requirement,
      and noted in the log before implementation
- [ ] implementation makes those tests pass
- [ ] `test --impacted` green
- [ ] `affected_paths` and `linked_tests` updated on every requirement
- [ ] `status = "active"` on every requirement this task delivers — or
      `"retired"`, with the reason in its prose, where this task
      deliberately removed the behavior
- [ ] `check` clean, or each remaining warning explained in the log
- [ ] `stage: deliver`

**Skip when:** Never — the quick path goes through `build` too. If a task
genuinely changes no behavior (documentation only), say so in the log and
record which requirements you re-read to confirm it; do not invent a test.
