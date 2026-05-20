# Implementation Review Report

> Generated from a deep, evidence-based implementation review of the AudioMancer
> codebase. No code was changed. References use `path:line` form against
> `04_Software/AudioMancer/`.

## Executive Summary

AudioMancer is a mature, carefully engineered offline-first PySide6 application.
The codebase is unusually disciplined for its size (~67K LOC source, ~38K LOC
tests): consistent module prologues and Doxygen-style docstrings, atomic
persistence everywhere, strong path-traversal defenses, secret redaction in AI
logs, clean `ruff` pass, and complete en/ro localization parity (868 keys each,
zero gaps). Security posture is good — no `subprocess`/`shell`/`eval`/
`extractall`/`pickle`, snapshots exclude symlinks and AI transaction logs,
`settings.json` is correctly gitignored and untracked.

The most important risks are **not** crashes or data loss in the happy path —
that path is solid. They are **maintainability hazards from parallel
implementations that have already drifted**: at least three cancellation code
paths exist, and the two non-canonical ones are dead code that encodes a
now-incorrect cancellation contract (and are still asserted by a test). The
canonical workflow order is duplicated in 4+ modules. Several public service
functions accept parameters they silently ignore. These don't fail today but
are landmines for the next contributor.

Highest-value fixes: (1) delete the dead/incorrect cancellation helpers and
re-point their test at the real path; (2) collapse the duplicated workflow-order
constants to a single source; (3) decide and document whether AI provider base
URLs (which contain operator LAN hosts) belong in user-shareable exports.

---

## High Priority Findings

### H1. Dead, drifted cancellation helpers encode an incorrect contract; a test asserts the broken behavior
- **Severity:** High (latent correctness + dead code + misleading test)
- **Files:**
  - `src/audiomancer/ui/controllers/workflow_controller_service.py:75-99`
  - `src/audiomancer/ui/controllers/operation_runner_controller.py:282-348`
  - `_cancel_active_operation`/`_is_cancel_requested` in
    `ai_translation_ui_controller.py:566-589`,
    `audio_blocks_ui_controller.py:1006-1029`,
    `characters_ui_controller.py:1203-1226`,
    `speech_blocks_ui_controller.py:838-861`
  - `cancel_active_operation`/`is_cancel_requested` in
    `text_cleanup_ui_controller.py:364-388`,
    `text_chunking_ui_controller.py:382-406`
  - `tests/test_workflow_controller_service.py:36-43`
- **What is wrong:** The live cancellation model: `start_threaded_operation`
  creates a `threading.Event` (`cancel_event`), passes
  `cancel_requested=cancel_event.is_set` to the worker callable, and the modal
  dialog's Cancel button is wired to `request_operation_cancel`, which sets
  **both** `window._operation_cancel_requested` **and** `cancel_event`. That
  path is correct. However, `workflow_controller_service.cancel_active_operation`
  and the per-controller `_cancel_active_operation`/`cancel_active_operation`
  wrappers set **only** `window._operation_cancel_requested`, and
  `is_cancel_requested` reads only that flag — which the worker never consults.
  Verified by grep: every `_cancel_active_operation`/`_is_cancel_requested` and
  the two text-controller `cancel_active_operation`/`is_cancel_requested`
  functions are defined but **never called** anywhere in `src/`;
  `workflow_controller_service.cancel_active_operation`/`is_cancel_requested`
  are reached only by that dead code and by `test_workflow_controller_service.py`.
- **Why it matters:** This is dead code that silently misrepresents the
  cancellation contract. The next person who wires a secondary "Cancel"
  affordance to one of these helpers will ship a long AI/TTS operation that
  ignores cancellation, with no compile/lint signal (ruff cannot flag unused
  module-level functions — it passes clean). `test_workflow_controller_service.py`
  actively asserts the broken flag-only behavior, lending it false legitimacy.
- **Recommended fix:** Delete the six dead `_cancel_active_operation`/
  `_is_cancel_requested` controller helpers and the `text_cleanup`/
  `text_chunking` `cancel_active_operation`/`is_cancel_requested` functions.
  Either remove `workflow_controller_service.cancel_active_operation`/
  `is_cancel_requested` or reimplement them to delegate to
  `operation_runner_controller.request_operation_cancel` (which sets the event).
  Re-point the test at the real cancel path.
- **Suggested test coverage:** End-to-end test: starting a threaded operation,
  invoking the dialog cancel callback, and asserting the worker-visible
  `cancel_event.is_set()` becomes `True` (not just the bookkeeping flag).

---

## Medium Priority Findings

### M1. Canonical workflow order duplicated across 4+ modules
- **Severity:** Medium
- **Files:** `config.py:211-223` (`PROJECT_WORKFLOW_STAGES`),
  `operation_runtime_service.py:33-44` (`_OPERATION_ORDER`),
  `workflow_impact_service.py:37-61` (`WORKFLOW_OPERATION_ORDER` +
  `OPERATION_STAGE_BY_KIND`), `project_workspace_service.py:72-95`
  (`_OPERATION_STAGE_BY_KIND` + `_HEALABLE_OPERATION_ORDER`) and the long
  `_allowed_operations_for_stage` if-ladder at
  `project_workspace_service.py:1874-1955`.
- **What is wrong:** `_OPERATION_ORDER` and `WORKFLOW_OPERATION_ORDER` are
  byte-identical 10-tuples in two files; `OPERATION_STAGE_BY_KIND`/
  `_OPERATION_STAGE_BY_KIND` is the same 9-entry map in two files;
  `_allowed_operations_for_stage` hand-rolls the same prefix relationship that
  `PROJECT_WORKFLOW_STAGES` ordering already encodes.
- **Why it matters:** Adding or reordering a workflow stage requires
  synchronized edits in 4–5 places with no enforcement; divergence would corrupt
  reset/invalidation and manifest healing.
- **Recommended fix:** Define the operation order and operation→stage map once
  (in `config`) and import everywhere; derive `_allowed_operations_for_stage`
  from the ordered list.
- **Suggested test coverage:** A consistency test asserting the orders and stage
  maps across modules are equal.

### M2. `build_operation_state_payload` accepts seven parameters it silently ignores; `build_operation_input_snapshot_path` always raises
- **Severity:** Medium
- **File:** `operation_runtime_service.py:178-198`, `operation_runtime_service.py:284-337`
- **What is wrong:** `build_operation_state_payload` documents and accepts
  `input_paths`, `output_paths`, `artifact_paths`, `started_at`, `completed_at`,
  `folder_relative_path`, `updated_at` then discards them all
  (`_ = input_paths` …). `build_operation_input_snapshot_path` exists only to
  raise `RuntimeError`.
- **Why it matters:** Callers still construct and pass these arguments, implying
  contracts that no longer hold. Leftover scaffolding from the v2 flat-layout
  migration that misleads readers and wastes caller work.
- **Recommended fix:** Trim the signature to the fields actually persisted;
  remove `build_operation_input_snapshot_path` and its call sites (or convert to
  an explicit no-op only if a caller truly depends on the exception).

### M3. AI provider base URL (operator LAN host) is embedded in user-shareable TXT/MD exports
- **Severity:** Medium — Needs confirmation (intent)
- **File:** `project_export_service.py:1192-1232` (`_ai_parameter_fields` emits
  `("AI Base URL", …)`)
- **What is wrong:** Cleaned-text/chunks/translation/characters/speech-blocks
  exports include "AI Base URL" and "AI Backend" pulled from the AI transaction
  log/report. With realistic settings (`settings.json` shows
  `http://192.168.1.28:1234/v1`, `http://192.168.1.17:1234/v1`), exports a user
  shares will contain internal network hostnames/IPs and model names. API keys
  are correctly *not* exposed (they only ever travel in the `Authorization`
  header and are redacted by key-name in logs).
- **Why it matters:** The review brief explicitly flags operator-local runtime
  settings as high-risk in export paths. Base URLs are operator-local
  infrastructure even though they aren't secrets.
- **Recommended fix:** Confirm whether base URL belongs in operator-shareable
  documents. If diagnostic value is wanted, consider emitting only the backend
  kind and model, or a host-stripped URL, or gate behind an explicit "include
  technical details" option.
- **Suggested test coverage:** Assert export rendering omits/contains base URL
  per the chosen policy.

### M4. Markdown export reconstructs structured tables by re-parsing plain text it just generated
- **Severity:** Medium — Needs confirmation
- **File:** `project_export_service.py:701-745`
  (`_render_character_dossiers_markdown` → `_parse_character_dossier_fields`)
- **What is wrong:** `_render_character_dossiers` builds `"Label: value"` lines
  joined by `\n\n----\n\n`; the Markdown path then splits on `"\n\n----\n\n"`
  and on the first `":"` to rebuild a table. Any dossier value containing
  `": "`, a line that is just `----`, or a newline will mis-split into wrong
  label/value pairs.
- **Why it matters:** Character `voice_definition_prompt` text is free-form AI
  output and can plausibly contain colons/separators, silently corrupting the
  Markdown character table.
- **Recommended fix:** Build the `ExportDocument` from structured character
  records and render TXT and Markdown from that structure directly, rather than
  parsing the TXT projection back into fields.

### M5. `default_operation_state("character_discovery")` returns a different schema than every other operation
- **Severity:** Medium
- **File:** `operation_runtime_service.py:240-282`
- **What is wrong:** All operations return
  `{status, progress_current, progress_total, mode, warning_count, metadata,
  resume_checkpoint}`, but `character_discovery` returns a divergent shape
  (`phase`, `input_fingerprint`, `checkpoint`, nested `token_usage`, no
  `metadata`/`resume_checkpoint`).
- **Why it matters:** Generic state consumers (manifest summary projection,
  healing) must special-case this one operation; future code that assumes the
  common schema will silently misbehave for character discovery.
- **Recommended fix:** Either normalize character discovery onto the common
  envelope (with its extras under `metadata`) or document the divergence as a
  deliberate, tested contract.

---

## Low Priority Findings / Cleanup

- **L1. Orphaned HTTP worker + redundant wait loop.**
  `llm_provider_service.py:284-301`: on cancel, a daemon request thread keeps
  running (holding a socket) until the provider timeout; the wait loop does both
  `thread.join(timeout=0.05)` and `time.sleep(0.01)` (double wait). Acceptable
  for a desktop app but worth a comment and dropping the redundant sleep.
- **L2. `assert` used for control flow/invariants.** e.g.
  `llm_provider_service.py:238` (`assert last_error is not None`),
  `project_workspace_service.py:403`,
  `operation_runner_controller.py:279-280`. Stripped under `python -O`; prefer
  explicit raises.
- **L3. Two different "safe file stem" rules.**
  `project_export_service._safe_file_stem` allows Unicode (regex strips only
  reserved chars) while `project_snapshot_service._safe_file_stem` collapses
  anything non-`[A-Za-z0-9._-]`. Same concept, divergent output for the same
  project name.
- **L4. Cancelled operation rendered as failure.**
  `operation_runner_controller.py:439-453`: `_handle_operation_cancelled` calls
  `fail_progress_dialog`; operator-initiated cancel shows as a failure visually.
  Minor UX.
- **L5. Atomic write fsyncs file but not directory.**
  `persistence_service.py:59-63`: `os.replace` gives atomicity; durability of
  the rename across power loss on some filesystems would also need a parent-dir
  fsync. Low for a desktop app.
- **L6. README imprecision.** `README.MD` "Layout" says `settings.json … API-key
  fields must remain blank in committed files`, implying it is committed; it is
  gitignored/untracked — the committed scaffold is `settings.example.json`.

---

## Duplicate Code and Duplicate Implementations

1. **Cancellation logic — three parallel implementations** (see H1): the correct
   event-setting path in `operation_runner_controller`, and two flag-only
   variants (`workflow_controller_service` + per-controller wrappers;
   `text_cleanup`/`text_chunking`). Consolidate to one.
2. **Workflow order/stage maps** duplicated across `config`,
   `operation_runtime_service`, `workflow_impact_service`,
   `project_workspace_service` (see M1).
3. **`is_path_inside_project`** is re-exported/wrapped in
   `project_export_service` and `project_snapshot_service` delegating to
   `operation_runtime_service`. Acceptable thin delegation, but the two
   `_safe_file_stem` variants (L3) are genuine drift.
4. **Per-controller boilerplate.** The workflow page controllers
   (`ai_translation`, `audio_blocks`, `characters`, `speech_blocks`,
   `text_cleanup`, `text_chunking`) repeat near-identical operation start /
   cancel / sync scaffolding. `workflow_controller_service` partially
   centralizes this; finishing that consolidation would remove the duplicated
   cancel helpers entirely.

---

## Dead Code / Unused Code

Confirmed unused (grep across `src/` and `tests/`):

- `_cancel_active_operation` / `_is_cancel_requested` in
  `ai_translation_ui_controller`, `audio_blocks_ui_controller`,
  `characters_ui_controller`, `speech_blocks_ui_controller` — defined, never
  referenced.
- `text_cleanup_ui_controller.cancel_active_operation` / `is_cancel_requested`,
  `text_chunking_ui_controller.cancel_active_operation` / `is_cancel_requested`
  — defined, never referenced.
- `workflow_controller_service.cancel_active_operation` / `is_cancel_requested`
  — reached only by the dead helpers above and
  `test_workflow_controller_service.py`.
- `operation_runtime_service.build_operation_input_snapshot_path` —
  unconditional `RuntimeError` stub (obsolete v1 flat-layout compat).
- Ignored parameters in `operation_runtime_service.build_operation_state_payload`
  (`input_paths`, `output_paths`, `artifact_paths`, `started_at`,
  `completed_at`, `folder_relative_path`, `updated_at`).
- `keep_input_snapshots` parameter of `reset_operation_data`
  (`operation_runtime_service.py:737-757`) is ignored.

All of the above are safe to remove except where a test currently depends on
them — **remove the dead code and the test together** (the test asserts
incorrect behavior). No prompts, assets, or dependencies appear unused
(`pyproject.toml` deps all map to extraction backends; ruff finds no unused
imports).

---

## Missing or Weak Tests

Ordered by risk reduction:

1. **Cancellation end-to-end** (replaces the misleading
   `test_workflow_controller_service.py`): assert the dialog cancel callback
   flips the worker-visible predicate (`cancel_event.is_set`), not just
   `_operation_cancel_requested`.
2. **Workflow-order consistency**: assert the operation orders and
   operation→stage maps in `config`, `operation_runtime_service`,
   `workflow_impact_service`, `project_workspace_service` are equal.
3. **Localization parity guard**: assert `en`/`ro` key sets are identical
   (currently true at 868/868, but nothing prevents future drift).
4. **Selective invalidation path safety**: tests that
   `delete_audio_block_artifacts` / `_collect_or_delete_resolved_path` never
   delete outside the project root and correctly classify skipped/preserved.
5. **Manifest healing of stale state**: a project with completed
   report+artifacts but `status != completed` in state files heals to the right
   stage and emits expected warnings (`_completed_or_report_healed_operation`).
6. **Snapshot/export secret-surface**: snapshot excludes `log_ai_*.log`; AI log
   redaction covers `*_api_key`/`authorization`; export base-URL behavior
   matches the decided M3 policy.
7. **Export Markdown robustness** (M4): dossier values containing `:` / `----` /
   newlines render correctly.

---

## Architecture and Maintainability Notes

- Overall layering (services / state services / controllers / pages / shared
  runtime) is clean and consistently applied; UI controllers correctly marshal
  work to a `QThread` worker with UI-thread signal bridges, and persistence is
  uniformly atomic.
- The dominant maintainability theme is **incomplete migration cleanup (v1 → v2
  flat layout, "v2 workflow impact")**: dead compat stubs, ignored parameters,
  divergent state schema, and parallel cancellation helpers are all symptoms.
  None break the happy path; collectively they raise the cost and risk of
  future change.
- Several files are very large (`audio_blocks_service.py` 3356,
  `character_discovery_service.py` 2792, `speech_blocks_service.py` 2582,
  `ui_state_service.py` 2490). They are well-sectioned and documented, so size
  alone is not alarming, but `ui_state_service.py` mixes the translation catalog
  with font/theme/scaling logic — splitting the string catalog into its own
  module would reduce churn-driven merge risk.
- The manifest "self-healing" subsystem (`project_workspace_service`) is the
  most intricate area and is **defensively excellent** — it reconstructs
  stage/operation metadata from on-disk evidence, never deletes user artifacts
  to "fix" metadata, and filters stale warnings. This is the right bias for the
  stated "deletion wastes operator time" risk.

---

## Documentation Consistency Notes

- `05_SoftwareDocu/` is comprehensive (one component doc per service, plus user
  guides in en/ro) and aligns with the implemented service set; README defers
  versioning to changelog/help per `AGENTS.md`. This is in good shape.
- README "Layout" line about `settings.json` being a "committed file"
  contradicts the gitignore reality (L6).
- Documentation describes WAV-only audio output, matching
  `AUDIO_ASSEMBLY_OUTPUT_FORMAT_OPTIONS = ("wav",)` — consistent
  (MP3/normalization/cover art remain unimplemented as expected).
- If H1/M1/M2 cleanups are made, `AudioMancer_Operation_Runner_Controller.md`,
  `AudioMancer_Workflow_Impact_Service.md`, and
  `AudioMancer_Project_Runtime_Support_Services.md` will need synchronized
  updates (per repo same-change doc rule).

---

## Quick Wins

- Delete the dead cancellation helpers + obsolete
  `build_operation_input_snapshot_path`; re-point/repair
  `test_workflow_controller_service.py` (H1).
- Add the en/ro key-parity test (one assertion, prevents localization
  regressions).
- Add the workflow-order consistency test (locks M1 before refactor).
- Fix the README `settings.json` "committed" wording (L6).
- Remove the redundant `time.sleep(0.01)` in the LLM cancel-wait loop (L1).

---

## Suggested Refactor Plan

1. **Safe cleanup:** delete dead cancellation helpers,
   `build_operation_input_snapshot_path`, and ignored-parameter scaffolding; fix
   README wording. Update affected `05_SoftwareDocu` pages in the same change.
   Bump touched file/function `@version` tags per `AGENTS.md`.
2. **Bug fixes:** restructure Markdown export to render from structured records
   (M4); decide & enforce export base-URL policy (M3).
3. **Consolidation:** single source for workflow order/stage maps (M1); unify
   `_safe_file_stem` (L3); normalize or document the character-discovery state
   schema (M5); finish centralizing controller operation/cancel scaffolding into
   `workflow_controller_service`.
4. **Test hardening:** add tests #1–#7 from "Missing or Weak Tests,"
   prioritizing cancellation E2E, order-consistency, localization parity, and
   deletion-path safety.
5. **Documentation synchronization:** reconcile every doc page touched by steps
   1–4; verify HowToTest/README validation instructions still match.

---

## Open Questions

1. **Export of AI base URL (M3):** is surfacing operator-local provider
   hostnames/IPs in user-shareable TXT/MD exports intentional, or should it be
   host-stripped / opt-in?
2. **Cancellation API intent:** is `workflow_controller_service`'s flag-only
   cancellation meant to be removed, or rewired to set the `cancel_event`?
   (Decides delete-vs-fix for H1.)
3. **Character-discovery state schema (M5):** deliberate divergence or migration
   leftover?
4. **Ignored operation-state parameters (M2):** are external/plugin callers
   expected to keep passing `input_paths`/`output_paths`/etc., or can the
   signature be trimmed?
5. **Snapshot vs. export of AI logs:** snapshots deliberately exclude
   `log_ai_*.log` (which contain full prompts and raw model responses, i.e. book
   text), but `project_export_service` reads them for AI parameter fields —
   confirm this asymmetry is the intended privacy boundary.

---

## Resolutions to Open Questions (Owner Decisions)

These decisions are authoritative and supersede the "Needs confirmation" labels
on the related findings.

1. **AI config / base-URL in exports (M3):** **Keep as-is — intentional.** The
   AI configuration and provider base URL in exported documents are a desired
   feature. M3 is **closed / won't-fix**; no host-stripping or opt-in gate
   required. Remove the M3 export-policy work from the refactor plan.
2. **`workflow_controller_service` cancellation API (H1):** **Delete it if it
   has no impact.** The dead `cancel_active_operation`/`is_cancel_requested`
   helpers (per-controller `_cancel_active_operation`/`_is_cancel_requested`,
   the `text_cleanup`/`text_chunking` variants, and the
   `workflow_controller_service` functions) are to be **removed** along with
   `tests/test_workflow_controller_service.py`'s assertions of the dead
   behavior — provided removal does not change runtime behavior (it does not;
   the live modal path via `request_operation_cancel` is unaffected). No
   re-implementation/delegation needed.
3. **Character-discovery state schema (M5):** **Normalize the schema while
   preserving functionality.** Converge `default_operation_state(
   "character_discovery")` onto the common state envelope (extras under
   `metadata`), keeping all existing discovery behavior, resume/checkpoint
   semantics, and token-usage reporting intact. Update affected consumers and
   docs in the same change.
4. **Ignored operation-state parameters (M2):** **Trim the signature to the
   fields actually persisted.** Reduce `build_operation_state_payload` to the
   fields it really writes, update all call sites to stop constructing/passing
   the discarded arguments, and remove the obsolete
   `build_operation_input_snapshot_path` stub and the ignored
   `keep_input_snapshots` parameter.
5. **AI logs in exports/snapshots:** **No export may include `log_ai_*` files.**
   Apply the snapshot exclusion rule consistently to **all** export paths
   (`project_export_service` archive and document exports, and any other
   artifact-collection path). `project_export_service` may still *read*
   `log_ai_*.log` to derive AI parameter fields (allowed per decision 1), but
   the log files themselves must never be packaged into any exported archive or
   document. Add regression tests asserting `log_ai_*` is absent from every
   export/snapshot output.

### Clarification: downstream reset is selective, not blanket (authoritative)

Changing or editing one operation does **not** unconditionally reset all
downstream operations. The implemented behavior is **selective invalidation**:
e.g. editing a single chunk preserves stable IDs and only invalidates the
exact affected downstream records/artifacts, while unrelated downstream work
(and explicitly preserved operations such as character discovery / narrator
definition / character voices via `preserve_operation_kinds`) is kept. This
selective-reset design in `workflow_impact_service` and the
`preserve_operation_kinds` path of `reset_operation_data` is intentional and
correct, and must be preserved by any cleanup. The H1/M1/M2 changes do **not**
touch this logic — they remove dead cancellation helpers, consolidate
order/stage constants, and trim an already-ignored signature; the selective
preservation semantics are unchanged.

### Net effect on the refactor plan

- **M3:** dropped (won't-fix).
- **H1, M2:** become straightforward deletions / signature trims.
- **M5:** schema normalization with behavior preservation.
- **New scope from decision 5:** audit and enforce `log_ai_*` exclusion across
  every export path (treat as an added Bug-fix / Test-hardening item).
- **Selective downstream reset is intentional** and must be preserved by all
  cleanup work (see clarification above).

### Implementation status (2026-05-19)

All approved items are **implemented and validated** (ruff clean; targeted
suites green; zero new regressions vs. the documented pre-existing stale-test
baseline):

- **H1** — dead cancellation helpers removed across 6 controllers +
  `workflow_controller_service`; test re-pointed at the real `cancel_event`
  path.
- **M1** — canonical `WORKFLOW_OPERATION_ORDER` / `OPERATION_STAGE_BY_KIND`
  single-sourced in `config.py`; runtime/impact/workspace reference it.
- **M2** — `build_operation_state_payload` trimmed to the 7 persisted fields;
  obsolete `build_operation_input_snapshot_path` and ignored
  `keep_input_snapshots` removed; all 11 service + 4 controller call sites and
  tests updated.
- **M5** — `default_operation_state("character_discovery")` normalized onto the
  shared envelope (discovery fields under `metadata`, `resume_checkpoint`).
  Verified the running service already persisted the common envelope; only the
  default seed diverged. Behavior preserved (service still reads
  `metadata`/`resume_checkpoint` first, legacy flat fallback retained).
- **Decision 5** — confirmed structurally satisfied (snapshot already excludes
  `log_ai_*`; archive exports only add explicit WAV/TXT/manifest entries).
  Added regression test
  `test_project_export_archives_never_include_ai_transaction_logs`; existing
  snapshot exclusion test retained.
- **L1/L3/L6** — redundant sleep removed; `_safe_file_stem` unified into one
  shared helper; README `settings.json` wording corrected.
- **M4** — owner chose option A. Character export now renders TXT and Markdown
  from one structured `(label, value)` record set (`_character_dossier_records`);
  the fragile parse-your-own-output path (`_parse_character_dossier_fields`)
  was removed and `ExportDocument` gained a `character_dossiers` field. Voice
  prompts containing `:`, newlines, or `----` no longer corrupt the Markdown
  table. Regression test added
  (`test_project_export_markdown_character_dossiers_survive_separator_and_colon_prompts`);
  all existing export tests still pass.
- **Guard tests added** — en/ro key parity; single-source workflow-order
  consistency.
- **M3** — not actioned (won't-fix, per decision 1).
- Pre-existing stale tests (~7) remain failing on a clean baseline; out of
  scope for these decisions and flagged separately.

---

## Recommended Implementation Model & Reasoning Effort

Most of this work is mechanical-to-moderate. Suggested mapping for Claude Code:

| Work item | Model | Reasoning effort | Rationale |
|---|---|---|---|
| Quick Wins: delete dead cancel helpers (H1, decision 2), README wording (L6), drop redundant `sleep` (L1), add en/ro parity + workflow-order consistency tests | Sonnet 4.6 | Low | Deterministic deletions / small additive tests; dead code already proven unreferenced. |
| H1 cancellation cleanup + remove/repair `test_workflow_controller_service.py` | Sonnet 4.6 | Medium | Touches ~8 files plus a test asserting wrong behavior; must not disturb the Qt threading model. |
| M1 workflow-order consolidation, M2 signature trim (decision 4), L3 `_safe_file_stem` unify | Sonnet 4.6 | Medium | Cross-module refactor with drift risk; bounded once the single source is chosen. Run full `uv run pytest` after. |
| Decision 5: enforce `log_ai_*` exclusion across all export paths + regression tests | Sonnet 4.6 | Medium | Localized rule applied consistently; needs careful path auditing and tests. |
| M4 export restructure, M5 state-schema normalization (decision 3) | Opus 4.7 | High | Change data/behavior contracts with cross-service + doc impact; behavior-preservation reasoning warrants the strongest model. |

Guidance:

- **Single-model option (lowest risk, less supervision):** Opus 4.7 with high
  reasoning effort for the whole plan.
- **Cost-optimized split:** Sonnet 4.6 for Quick Wins + H1 + M1/M2/L-items +
  decision 5; escalate to Opus 4.7 only for M4 and M5.
- Keep high reasoning effort **on** for anything touching manifest healing,
  threading, workflow-order, or the character-discovery schema (subtle
  invariants, easy to break silently); low effort is fine for README/`sleep`/
  test-addition edits.
- Haiku is not recommended even for deletions — cross-file reasoning plus the
  `@version`/doc-sync rules in `AGENTS.md` reward a stronger model.
- Tackle findings as separate sessions/PRs in the staged order; each is small
  enough that context window is not the constraint — model capability and
  validation/doc-sync discipline matter more.
