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

  stage         frame | specify | design | build | deliver | done
                (adoption journals: survey | components | close | done)
  type          feature | fix | change | adopt
  path          full | quick
  requirements  comma-separated requirement IDs, empty until specify
  branch        the branch this task is delivered on
  opened        YYYY-MM-DD

Header lines are edited in place; log lines are only ever appended.
Keep each log line to one sentence.
-->

# TASK-6e7f4c7b - Safeguard and parallelize pytest runtime

stage: done
type: change
path: full
requirements: REQ-TEST-c40e9791, REQ-TEST-d5e21918
branch: AudioMancer_V2
opened: 2026-08-10

## Done checklist (current stage)

- [ ] check --strict --run green with full-suite evidence recorded
- [x] diff reviewed against scope, requirements, design, error paths, portability, security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report inside the delivery commit; agreed outcome delivered
- [x] close-out: stage done set and committed only after the outcome succeeded
- [x] code follows project style; this task is not a release

## Log

- 2026-08-10 frame: Scope is limited to adding a 120-second per-test pytest timeout dependency, configuration, lock data, and focused verification; parallel execution, modal-dialog interception, production behavior, and the full suite are excluded.
- 2026-08-10 frame: Full path selected because this task adds a development dependency; the user requested implementation without another checkpoint.
- 2026-08-10 specify: Created REQ-TEST-c40e9791 for the bounded individual-test runtime behavior; no separate specification is needed because the configuration and verification contract are self-contained.
- 2026-08-10 specify: AEGIS check reported zero errors and 195 pre-existing repository-wide warnings, including unrelated stage-zone findings from prior integrated work.
- 2026-08-10 design: A separate design note is unnecessary because the change is confined to one dependency, two pytest configuration values, generated lock data, and one configuration regression test.
- 2026-08-10 build: tests/test_pytest_runtime_configuration.py::test_individual_tests_have_a_windows_safe_timeout red as expected because the timeout plugin was not installed.
- 2026-08-10 build: AEGIS impacted selection expanded to 1199 branch-wide selectors and exited 127 before pytest because it emitted application-prefixed paths after changing into the application directory; direct focused verification is used instead.
- 2026-08-10 build: Direct focused verification passed 1 test, Ruff passed, Python compilation passed, pytest collection passed, and uv lock validation passed.
- 2026-08-10 build: AEGIS check reported zero errors and 41 repository-wide outside-layout or pre-existing ticket-reference warnings; no warning identifies a defect in the scoped implementation.
- 2026-08-10 deliver: Full-suite and commit steps remain deferred under the owner's instruction to run the full suite only after all planned implementation is complete and to require approval before committing.
- 2026-08-10 frame: The owner expanded scope to opt-in local pytest worker processes while retaining one Codex agent; UI parallelization, global automatic workers, production changes, the full suite, and commit remain excluded.
- 2026-08-10 specify: Created REQ-TEST-d5e21918 for explicitly requested parallel service-test execution with serial default behavior.
- 2026-08-10 specify: AEGIS check reported zero errors and 198 repository-wide warnings dominated by unrelated integrated stage-zone findings.
- 2026-08-10 design: A separate design note is unnecessary because xdist is an opt-in test dependency and the existing service and UI markers already provide the safe execution boundary.
- 2026-08-10 build: tests/test_pytest_runtime_configuration.py::test_parallel_execution_is_available_and_opt_in red as expected because xdist was not installed.
- 2026-08-10 build: Direct runtime configuration verification passed 2 tests, a two-worker smoke passed 5 tests, a four-worker file-grouped service smoke passed 40 tests, and an explicit serial UI smoke passed 1 test.
- 2026-08-10 build: One initially selected configuration-contract test failed identically in serial execution because the ignored settings.json from 2026-08-07 contains runtime discovery data, so it is pre-existing local state and was not modified.
- 2026-08-10 build: AEGIS impacted selection again expanded to 1199 branch-wide selectors and exited 127 before pytest because of its existing application-prefixed path construction.
- 2026-08-10 build: Ruff, Python compilation, uv lock validation, diff whitespace validation, and AEGIS check passed with zero errors; the 41 AEGIS warnings are repository-wide layout or pre-existing ticket-reference findings.
- 2026-08-10 deliver: The full suite and commit remain deferred under the owner's standing instructions; no production files or unrelated local artifacts were modified.
- 2026-08-16 close-out: the work this journal describes reached `master` as `7db71ae` ("Added timeout for test + parallel execution.", 2026-08-10) and the recorded `branch: AudioMancer_V2` no longer exists in this repository, so the outcome succeeded and `stage: done` is set on the operator's instruction to close the open tasks. The first checklist item stays deliberately unticked and is not retro-claimed: `check --strict --run` with full-suite evidence was never recorded for this task, because the owner's standing instruction deferred the full suite (see the 2026-08-10 deliver entry). Both requirements, REQ-TEST-c40e9791 and REQ-TEST-d5e21918, remain active and describe the delivered behaviour; nothing was changed at close-out.
