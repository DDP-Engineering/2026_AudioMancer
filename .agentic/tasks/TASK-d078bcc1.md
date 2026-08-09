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

# TASK-d078bcc1 — Persist assembly run timestamps and cache Scene Mix digests

stage: deliver
type: fix
path: full
requirements: REQ-DATA-94132a27, REQ-REL-3ccdf599, REQ-NFR-b6ffe4e8, REQ-REL-45ec2fa5
branch: ddp/as5-as6-report-hash-cache
opened: 2026-08-09

## Done checklist (current stage)

- [x] user-directed scoped suite and task-scoped strict static check recorded truthfully
- [x] diff reviewed against scope, requirements, design, error paths, portability, security and code style
- [x] Audio Assembly knowledge and `CHANGELOG.md` Unreleased updated
- [x] requirements re-read: status, prose, verification and links remain true
- [x] exact staged diff and fingerprint presented; human confirms delivery before commit
- [x] journal and report included in the delivery commit
- [x] non-release delivery leaves project/help versions unchanged
- [ ] close-out journal committed only after the approved delivery outcome succeeds

## Log

- 2026-08-09 frame: Scope is truthful Audio Assembly lifecycle timestamps and resumable run tokens plus bounded in-memory Scene Ambience source-digest reuse with safe invalidation, while public APIs, completed-output records, settings, containment, reset ownership, and legacy loaders remain compatible.
- 2026-08-09 frame: Exclusions are planning edits, persistent cache or schema replacement, whole-audio caching, duration-header optimization, unrelated refactors, settings bootstrap, full-suite execution, version release work, commits, pushes, and main-worktree changes before approval.
- 2026-08-09 frame: The full path is required because this extends a durable report/state contract and adds synchronized runtime caching; the source delegation already confirms the exact scope and directs the next human stop at the staged pre-commit checkpoint.
- 2026-08-09 frame: Proposed requirements are durable report lifecycle timestamps, one logical-run resume token with legacy fallback, bounded reuse for unchanged shared Scene Ambience sources, and safe digest invalidation without cached failures.
- 2026-08-09 specify: Created REQ-DATA-94132a27, REQ-REL-3ccdf599, REQ-NFR-b6ffe4e8, and REQ-REL-45ec2fa5 with the Audio Assembly service and focused service regressions as their affected implementation and verification surfaces.
- 2026-08-09 specify: Task-scoped AEGIS check reported zero errors and 88 existing repository-wide warnings unrelated to these new artifacts.

## Design

- Component: change only `audio_assembly_service.py`, its focused service tests, and Audio Assembly knowledge; state/controller/page public interfaces and shared operation-state schema remain unchanged (all requirements).
- Report contract: add `started_at` and nullable `completed_at` to every newly built report while raw loading keeps old reports without either key valid (REQ-DATA-94132a27).
- Resume contract: build each run-owned compact state with `resume_checkpoint.run_token` copied from the report start; `_resolve_started_at` retains the current missing/invalid checkpoint UTC fallback (REQ-REL-3ccdf599).
- Cache data: wrap the existing file-byte SHA-1 work in a 256-entry `functools.lru_cache` keyed by resolved path, `st_mtime_ns`, and `st_size`; cache only digest strings and keep cache state process-local (REQ-NFR-b6ffe4e8).
- Cache failure behavior: perform containment-aware path resolution and stat before cache lookup; exceptions from the byte-hash worker propagate and therefore never populate the cache (REQ-REL-45ec2fa5).
- Public interface: no callable signatures change; the only persisted extension is two report keys and a previously defined state checkpoint value (REQ-DATA-94132a27, REQ-REL-3ccdf599).
- Rejected alternative: removing content SHA-1 from preview names would weaken deterministic content identity, while a persisted cache would add invalidation schema and cleanup obligations outside scope (REQ-NFR-b6ffe4e8, REQ-REL-45ec2fa5).
- Test seams: controlled `_utc_now_iso` and cancellation callbacks cover fresh, cancelled, resumed, legacy, state/report consistency, and completed-output reuse paths (REQ-DATA-94132a27, REQ-REL-3ccdf599).
- Test seams: instrumented `Path.open`, explicit nanosecond `utime`, one injected hash failure, and cache-info/clear hooks cover unchanged/shared reads, invalidation, retry, bounds, deterministic naming, and reuse (REQ-NFR-b6ffe4e8, REQ-REL-45ec2fa5).
- Expected files: the Audio Assembly service and service test, four requirements, this journal, Audio Assembly knowledge, and `CHANGELOG.md` only.
- 2026-08-09 design: The full-path design preserves existing loading, containment, reset, resume-record, warning, metadata, progress, and input-fingerprint flows while making the two previously unreachable runtime values durable.
- 2026-08-09 build: `test_audio_assembly_service_persists_truthful_run_timestamps` was red as expected for REQ-DATA-94132a27 because the durable report omitted `started_at`.
- 2026-08-09 build: `test_audio_assembly_service_cancel_resume_preserves_run_token_and_outputs` was red as expected for REQ-REL-3ccdf599 after one output persisted because the cancelled report omitted its logical-run start and state token.
- 2026-08-09 build: `test_audio_assembly_scene_mix_refresh_reuses_unchanged_source_digests` was red as expected for REQ-NFR-b6ffe4e8 because no bounded digest cache or clear seam existed.
- 2026-08-09 build: `test_audio_assembly_scene_mix_digest_cache_invalidates_on_stat_change` was red as expected for REQ-REL-45ec2fa5 because no stat-keyed digest cache or invalidation seam existed.
- 2026-08-09 build: The strengthened completed-output reuse regression was red for REQ-DATA-94132a27 because a no-work re-entry replaced the original truthful completion timestamp.
- 2026-08-09 build: All 12 new or strengthened lifecycle, legacy, reuse, cache, invalidation, retry, naming, and reset selectors passed after the minimal service changes.
- 2026-08-09 build: The user-directed direct linked-selector run replaces the configured impacted wrapper for this task; no `uv`, settings bootstrap, or duplicate wrapper run was attempted.
- 2026-08-09 build: Complete Audio Assembly service/state/controller/page/sample-width and operation-runtime modules passed 95 tests once in one non-duplicated scoped run under normal Windows Qt.
- 2026-08-09 build: Changed source and test files passed Ruff and `py_compile`, while task-scoped AEGIS check reported zero errors and the same 88 repository-wide advisory warnings.
- 2026-08-09 deliver: The full pytest suite is explicitly deferred by user direction; delivery evidence is the linked and complete scoped module coverage rather than a full-suite claim.
- 2026-08-09 deliver: Task-scoped AEGIS strict static check exited 0 with zero errors and 89 warnings, consisting of the 88 existing repository-wide advisories plus the expected unticked delivery-checklist warning.
- 2026-08-09 deliver: Semantic diff review confirmed legacy raw loading, missing-token fallback, reset emptiness, project containment and symlink resolution, completed output/progress/warning/metadata/fingerprint reuse, deterministic preview naming, uncached failures, and public call signatures remain intact.
- 2026-08-09 deliver: All four active requirements were re-read against their linked selectors; Audio Assembly knowledge and the Unreleased changelog are current, and this non-release intentionally changes no project or help version.
- 2026-08-09 deliver: Human approval covers the independently reviewed nine-file patch and 46-test service run at `git diff --cached --binary | git hash-object --stdin` fingerprint `7b7672b109549d529dff8073d92d09792a3b6fea`; the earlier checkpoint's `895e1c70f2f732e25697e29a592c9e06c724fbe5` used the different `--full-index --binary` command and is recorded only as that command's result.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/as5-as6-report-hash-cache
- requirements:
  - REQ-DATA-94132a27 - Persist Audio Assembly report lifecycle timestamps
  - REQ-REL-3ccdf599 - Preserve Audio Assembly logical-run resume token
  - REQ-NFR-b6ffe4e8 - Reuse unchanged Scene Ambience source digests in memory
  - REQ-REL-45ec2fa5 - Invalidate Scene Ambience digests safely
- task diff vs `3551cab243e00a85716d968115658ab35aaf6d54`: 9 file(s) changed, 816 line(s) added, 6 line(s) removed
- checks: errors=0 warnings=89 notes=0
- checklist: 7/8 done; open: close-out journal committed only after the approved delivery outcome succeeds
