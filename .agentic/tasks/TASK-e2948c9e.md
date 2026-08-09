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

# TASK-e2948c9e — Validate and remove DEAD-10 through DEAD-16

stage: done
type: change
path: quick
requirements: REQ-FUNC-32f94a76, REQ-FUNC-57acf8bd, REQ-FUNC-b1613487, REQ-FUNC-f878c579, REQ-FUNC-a18bd73e, REQ-FUNC-c1ab4b69, REQ-FUNC-f9a4bf62, REQ-FUNC-b8a50984, REQ-FUNC-c75ae58f, REQ-FUNC-46ec3365, REQ-UX-1e55ab3b, REQ-FUNC-170ed96e, REQ-FUNC-a85c1f52
branch: ddp/dead-10-16
opened: 2026-08-09

## Done checklist (current stage)

- [x] requested focused suite is green; the explicitly excluded full suite was not run
- [x] strict task-scoped AEGIS static check has no errors and its merge-base warnings are explained
- [x] exact diff reviewed against scope, requirements, error paths, portability, security, and code style
- [x] knowledge pages and requirements re-read and updated only where the contract materially changed
- [x] delivery confirmed by the standing user approval before the commit
- [x] journal and report are inside the delivery commit
- [x] close-out: `stage: done` set and committed only after delivery succeeds
- [x] CHANGELOG Unreleased contains a maintainability note; no release/version/help changes were made

## Log

- 2026-08-09 frame: Validate DEAD-10 through DEAD-16 against current source, tests, tools, requirements, history, and public contracts, removing only confirmed dead implementation and unnecessary caller work.
- 2026-08-09 frame: Excluded the parent checkout, 0_Planning edits, DEAD items outside 10 through 16, full-suite execution, release/version/help changes, push, merge, and compatibility-breaking public signature removal without independent contract proof.
- 2026-08-09 frame: Chose the quick path because accepted work removes unused implementation, fields, aliases, and caller costs while preserving behavior, persisted formats, dependencies, and existing public call compatibility.
- 2026-08-09 frame: Existing requirements REQ-FUNC-32f94a76, REQ-FUNC-57acf8bd, REQ-FUNC-b1613487, REQ-FUNC-f878c579, REQ-FUNC-a18bd73e, REQ-FUNC-c1ab4b69, REQ-FUNC-f9a4bf62, REQ-FUNC-b8a50984, REQ-FUNC-c75ae58f, REQ-FUNC-46ec3365, REQ-UX-1e55ab3b, REQ-FUNC-170ed96e, and REQ-FUNC-a85c1f52 remain the behavior constraints; no requirement rewrite is expected.
- 2026-08-09 frame: Standing user approval authorizes uninterrupted validation, focused verification, delivery commit, and AEGIS close-out without the normal checkpoints.
- 2026-08-09 build: Five focused regression selectors were red as expected because summary refresh reloaded chunks, character state exposed discarded fields, capability aliases remained, sample generation loaded an unused TTS plan, and AI profile append required discarded metadata.
- 2026-08-09 build: Accepted DEAD-10 because source_chunk_count had no read and three summary-only callers loaded Character Discovery chunks solely to compute it, including the manifest-sync controller path covered by the new regression.
- 2026-08-09 build: Accepted DEAD-11 because all nine private writer calls supplied progress_current, progress_total, run_token, and input_fingerprint while the writer only assigned them to a discard tuple.
- 2026-08-09 build: Accepted DEAD-12 because the current tree has three writer calls, not the report's four, and all ten named arguments plus state_path and the newly exposed source_path local had no persisted or behavioral use.
- 2026-08-09 build: Accepted DEAD-13 because the resume tuple slot, constant, merge wrapper, narrator metadata helper, page language methods, prompt-update flag/helper, and capability alias keys had no source, tool, requirement, or knowledge consumer; current merge and prompt behavior remain covered directly.
- 2026-08-09 build: Partially accepted DEAD-14 by removing the production selected_language argument, generation_metadata construction, and sample-generation TTS-plan load while retaining documented public parameters as optional legacy call surfaces.
- 2026-08-09 build: Deferred DEAD-14 runtime_result_summary and discovered_models signature/plumbing removal because store_profile_sample and the TTS-plan APIs are documented, widely called public services and no compatibility-safe caller simplification offsets the break.
- 2026-08-09 build: Accepted DEAD-15 because character_count and the three always-false flags were discarded by every Characters page state application and MainWindow already forwards the state mapping dynamically.
- 2026-08-09 build: Accepted DEAD-16 because both counters were initialized and incremented without any read or persistence, _metadata_int had no other caller, and current contract tests require the fields absent; the same obsolete fields were also removed from the current synthetic-project tool missed by the report.
- 2026-08-09 build: The five red selectors passed after implementation in 0.29 seconds.
- 2026-08-09 build: One combined focused run exceeded its 180-second launcher bound while pytest continued; no duplicate ran, and pytest cache identified only the removed private resume-tuple slot assertion, which was updated to the current tuple contract.
- 2026-08-09 build: Split focused verification passed with 143 Character and VoiceWeaver tests, 89 narrator tests, and 139 Audio Blocks, workspace, and chunking tests plus 1 skip.
- 2026-08-09 build: Scoped Ruff and compileall passed for every changed Python source, test, and tool file before the final diff review.
- 2026-08-09 build: python .agentic/aegis.py check --task TASK-e2948c9e --strict exited 0 with no errors and 86 warnings caused by the configured merge-base including unrelated historical source, documentation, tools, and planning files.
- 2026-08-09 deliver: The exact working diff was reviewed hunk by hunk and contains only accepted DEAD-10 through DEAD-16 cleanup, compatibility-safe DEAD-14 caller savings, focused tests, one requirement link, the AEGIS journal, and the required Unreleased note.
- 2026-08-09 deliver: Character Discovery, Character Voices, Voice Profiles, AI Runtime, and TTS Audio Blocks knowledge pages remain accurate because active behavior, persisted formats, component ownership, and file sets did not change.
- 2026-08-09 deliver: REQ-FUNC-32f94a76 now links the new no-chunk-reload regression; all other linked requirements remain active and accurate without prose changes.
- 2026-08-09 deliver: Final focused smoke verification passed 7 selectors in 0.33 seconds, and final scoped Ruff, compileall, symbol-absence, whitespace, branch, and status checks passed.
- 2026-08-09 deliver: No full suite ran by explicit task scope, no settings file was created, and no parent checkout, planning report, remote, merge, or release/version/help surface was touched.
- 2026-08-09 deliver: Delivery commit a1a8034 succeeded on ddp/dead-10-16 without push or merge.
- 2026-08-09 close-out: Marked TASK-e2948c9e done after the requested delivery commit succeeded.

## Delivery report (2026-08-09)

- stage: deliver; type: change; path: quick; branch: ddp/dead-10-16
- requirements:
  - REQ-FUNC-32f94a76 - Character Discovery shall persist completed-window progress
  - REQ-FUNC-57acf8bd - Discovery resume shall preserve durable character inventory
  - REQ-FUNC-b1613487 - Character discovery shall merge and group candidates, keeping role
  - REQ-FUNC-f878c579 - Characters page shall recover from invalid discovery documents
  - REQ-FUNC-a18bd73e - Narrator profile generation shall complete in the authoritative
  - REQ-FUNC-c1ab4b69 - Narrator AI profile generation shall atomically persist attempt status
  - REQ-FUNC-f9a4bf62 - Narrator profile generation shall append odd allocations without
  - REQ-FUNC-b8a50984 - The narrator definition service shall require minimum Qwen capabilities
  - REQ-FUNC-c75ae58f - The narrator definition service shall store or import a single profile
  - REQ-FUNC-46ec3365 - The VoiceWeaver capability matrix shall ignore unhealthy models
  - REQ-UX-1e55ab3b - Valid Character Voices edit mode can save unchanged text
  - REQ-FUNC-170ed96e - Audio Blocks shall persist all operation metadata and blocks in one
  - REQ-FUNC-a85c1f52 - Audio-block generation shall produce ordered clone-prompt WAVs, use the
- diff vs merge base: 427 file(s) changed, 39481 line(s) added
- checks: errors=0 warnings=87 notes=0
- checklist: 7/8 done; open: close-out: `stage: done` set and committed only after delivery succeeds

## Delivery report clarification

- The generated 427-file merge-base diff is an AEGIS base-selection artifact that includes unrelated repository history and is not the task delivery diff.
- The authoritative delivery candidate is the exact staged patch reviewed immediately before commit; the strict static result recorded above is 0 errors and 86 warnings before the expected unticked close-out warning.
