# Component Review — Operation Orchestration + App Shell

_Reviewed 2026-08-02. Files: `services/operation_runtime_service.py` (677), `services/workflow_impact_service.py` (626), `ui/operation_progress_dialog.py` (210), `ui/controllers/operation_runner_controller.py` (489), `ui/controllers/workflow_controller_service.py` (128), `app.py` (107), `__main__.py` (24), `ui/main_window.py` (1282), `ui/navigation_sidebar.py` (225), `ui/controllers/misc_ui_controller.py` (434). Total ~4200 lines._

## Summary

The core runtime is in good shape: path-traversal validation, progress clamping,
reset ordering against `WORKFLOW_OPERATION_ORDER`, and the QThread/worker/bridge
lifecycle all hold up under scrutiny. Five real defects were found: one that
writes a contradictory `current_stage` into `project.json` on a normal
cancel/failure path (Critical), two user-visible defects in the shared modal
progress dialog (Major), and two small reset-completeness gaps (Minor). Counts:
1 Critical, 2 Major, 2 Minor.

## Findings

> **OC-1 resolution update (2026-08-03):** Commit `36e3070` resolves this
> finding under `REQ-FUNC-ccc76f34` and `REQ-FUNC-e45d3577`. The controller no
> longer reconstructs a manifest from the stale window snapshot. It delegates
> to `project_workspace_service.sync_manifest_operation_summary`, which reloads
> the current disk manifest, updates the requested operation summary, and only
> promotes the requested stage. The controller then displays the exact final
> manifest loaded from disk. Newer manifest fields and completed downstream
> summaries are preserved, a lower requested stage is ignored, and a `None`
> loader without a stage request still refreshes the window without writing a
> replacement manifest. Focused regressions passed (10 tests); the delivery
> suite passed with 1,212 tests, 1 skipped, and 1 deselected. The original
> OC-1 evidence below is retained as historical review context.

### [OC-1] `sync_manifest_operation_from_disk` writes `current_stage` with no promotion guard, over a stale in-memory manifest — **Critical**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\controllers\workflow_controller_service.py:84-97`
- **What:** the helper rebuilds the manifest from the *pre-operation* in-memory
  snapshot and then assigns `current_stage` unconditionally:

```python
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations[operation_kind] = project_workspace_service.project_manifest_operation_summary(
            operation_kind,
            operation_state,
        )
    updated_manifest["operations"] = operations
    if current_stage is not None:
        updated_manifest["current_stage"] = current_stage
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
```

  Its sibling `project_workspace_service.sync_manifest_operation_summary`
  (`project_workspace_service.py:504-513`) does the opposite — it reloads the
  manifest from disk and only ever *promotes* the stage, with an explicit
  docstring note that demotion "would leave completed downstream summaries
  stranded above it, and that contradiction is what makes a finished project
  offer a repair on every later open."

- **Why it matters:** `characters_ui_controller.py:781-786` calls it with a
  hard-coded stage:

```python
    workflow_controller_service.sync_manifest_operation_from_disk(
        window,
        "character_discovery",
        _character_operation_summary,
        current_stage="translation_ready",
    )
```

  and that call is wired into `_handle_discovery_failure` (line 494) and
  `_handle_discovery_cancelled` (line 514). Concrete scenario: a project that has
  already reached `audio_blocks_ready`; the operator opens Characters, presses
  Start Discovery (no downstream reset happens at start —
  `handle_start_discovery_requested` only validates prerequisites), then cancels
  it or the provider call fails. `project.json` is rewritten with
  `current_stage = "translation_ready"` while `operations["speech_blocks"]`,
  `["audio_blocks"]`, `["audio_assembly"]` still say completed and their
  artifacts still exist on disk. On the next open,
  `project_workspace_service._…metadata_repair` computes
  `target_stage = max(base_stage, verified_stage)` (line 592), sees
  `verified_stage` above the stored stage, records a change, and returns
  `status: "repair_required"` — the spurious repair prompt the sibling helper
  documents. The stale-snapshot base additionally discards any manifest field
  the worker wrote to disk while the operation ran.

- **Fix:** delegate to the guarded helper instead of rebuilding from the stale
  snapshot:

```python
    operation_state = load_operation_state(window._current_project_root)
    if operation_state is not None or current_stage is not None:
        project_workspace_service.sync_manifest_operation_summary(
            window._current_project_root,
            operation_kind,
            operation_state,
            current_stage=current_stage,
        )
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
```

---

### [OC-2] The operation-progress dialog is never localized in production — **Major**

> **OC-2 resolution update (2026-08-03):** Commit `fd7edf7` resolves this
> finding under `REQ-FUNC-84c50360`. The shared
> `misc_ui_controller.create_progress_dialog` factory now resolves the current
> language from the optional window settings payload and calls
> `OperationProgressDialog.apply_language(...)` before `start(...)` renders the
> operation title. Every production caller therefore receives Romanian title,
> Cancel-control, and later token-usage rendering through the shared factory,
> while English behavior, caller-supplied operation/status text, runtime language
> changes, and incomplete test-double fallback remain intact. Focused factory and
> dialog tests passed, as did operation-runner, MainWindow progress-dialog, and
> localization coverage; the complete suite passed with 1,240 passed, 1 skipped,
> and 1 deselected.

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\controllers\misc_ui_controller.py:287-293`
- **What:** the dialog hard-codes English at construction
  (`operation_progress_dialog.py:42`: `self._current_language = "en"`), and the
  only production factory never applies the operator's language:

```python
    window._operation_progress_dialog = OperationProgressDialog(window)
    window._operation_progress_dialog.cancel_requested.connect(cancel_callback)
    window._operation_progress_dialog.start(
        operation_name,
        initial_message,
        cancellable=cancellable,
    )
```

  The single production caller of `apply_language` is
  `settings_ui_controller.py:143-144`, which only fires if the dialog already
  exists — impossible, because the dialog is `ApplicationModal` and blocks the
  Settings dialog.

- **Why it matters:** Romanian translations exist for all three dialog strings
  (`ui_state_service.py:1254-1257`), but a Romanian operator always sees the
  English window title (`"{operation_name} In Progress"`), the English cancel
  label (`"Cancel Operation"`), and the English token-usage line, on every
  long-running operation. `tests/test_operation_progress_dialog.py:12` passes
  only because it calls `dialog.apply_language("ro")` itself, which production
  code never does — so the knowledge-doc contract ("localized title/cancel
  label … localized token usage rendering") is not actually met at runtime.

- **Fix:** in `create_progress_dialog`, apply the current language before
  `start(...)`:

```python
    window._operation_progress_dialog = OperationProgressDialog(window)
    window._operation_progress_dialog.apply_language(
        ui_state_service.current_language_from_settings(window._settings_payload)
    )
    window._operation_progress_dialog.cancel_requested.connect(cancel_callback)
```

---

### [OC-3] Escape / title-bar close dismisses the modal progress dialog without cancelling the operation — **Major**

> **OC-3 resolution update (2026-08-03):** Commit `fd7edf7` resolves this
> finding under `REQ-UX-afd2c37d`. `OperationProgressDialog` now tracks its
> active lifecycle from `start()` until `finish()` or `fail()` begins hiding it.
> Its `reject()` and `closeEvent()` routes use one idempotent cancellation helper:
> Escape, title-bar/programmatic close, and the Cancel control emit at most one
> request, disable the control, and keep a cancellable active dialog visible and
> application-modal until the shared controller reaches its terminal lifecycle.
> Non-cancellable active dialogs ignore Escape and close requests, and normal
> finish, fail, and shared clearing behavior remains intact. Focused Qt coverage
> passed for every dismissal and lifecycle path, alongside the operation-runner,
> MainWindow, localization, and complete-suite verification recorded for OC-2.

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\operation_progress_dialog.py:61-62, 157-164`
- **What:** `OperationProgressDialog` inherits `QDialog`'s default
  `Esc -> reject()` and window-close `-> reject()` behaviour, and neither
  `reject()`, `closeEvent()`, nor `keyPressEvent()` is overridden. The only path
  that emits `cancel_requested` is the button:

```python
        self._cancel_button = QPushButton("", self)
        self._cancel_button.clicked.connect(self._emit_cancel_requested)
...
    def _emit_cancel_requested(self) -> None:
        self._cancel_button.setEnabled(False)
        self.cancel_requested.emit()
```

- **Why it matters:** during any long operation (a multi-hour TTS run), a stray
  Escape keypress hides the dialog. `window._operation_progress_dialog` stays
  non-`None`, so `update_progress_dialog` keeps writing into an invisible
  widget; `_active_operation_kind` stays set, so no new operation can start; the
  application-modal barrier is gone; and there is now **no** way to reach the
  Cancel button — `create_progress_dialog` is only invoked at operation start,
  and nothing ever re-`show()`s the dialog. The operator must wait out the run
  or kill the process.

- **Fix:** make `reject()` route through the cancel path instead of hiding:

```python
    def reject(self) -> None:  # noqa: N802 - Esc / close must not silently dismiss a running run
        if self._cancel_button.isVisible() and self._cancel_button.isEnabled():
            self._emit_cancel_requested()
```

  (deliberately not calling `super().reject()`, so the dialog stays up until the
  worker actually terminates and `clear_progress_dialog` removes it).

---

### [OC-4] Character Discovery AI transaction logs are never deleted by reset — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\operation_runtime_service.py:112-114, 611-615`
- **What:** the AI-log token override table covers only `narrator_definition`,
  so `character_discovery` falls back to its own kind name:

```python
_OPERATION_AI_LOG_TOKENS = {
    "narrator_definition": ("narrator_profiles",),
}
...
        log_tokens = _OPERATION_AI_LOG_TOKENS.get(selected_kind, (selected_kind,))
        for log_token in log_tokens:
            for log_path in root_path.glob(f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}{log_token}_*.log"):
```

  but the service actually writes the log under a different token
  (`character_discovery_service.py:1756`):

```python
        config.ai_transaction_log_file_name("characters", timestamp_token),
```

  so the glob is `log_ai_character_discovery_*.log` while the files on disk are
  `log_ai_characters_*.log`. It never matches. (The other five log-producing
  kinds — `cleanup`, `chunking`, `translation`, `narrator_profiles`,
  `speech_blocks` — all line up correctly.)

- **Why it matters:** the documented contract is that reset deletes
  "operation-owned root artifacts, AI logs, and safe targeted audio/assembly
  files". Every Character Discovery run leaves a permanent prompt/response
  transcript in the project root that no reset — not even the destructive
  project-open chunking recovery — ever removes. These accumulate in the project
  folder and are carried into every project snapshot/export.

- **Fix:**

```python
_OPERATION_AI_LOG_TOKENS = {
    "character_discovery": ("characters",),
    "narrator_definition": ("narrator_profiles",),
}
```

---

### [OC-5] `character_voices` reset leaves generated sample WAVs orphaned in the project root — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\operation_runtime_service.py:86, 107-109`
- **What:** the artifact table lists only the JSON document for
  `character_voices`, and the derived-name glob table covers narrator samples
  only:

```python
    "character_voices": (config.CHARACTER_VOICES_TARGETS_FILE_NAME,),
...
_OPERATION_ARTIFACT_GLOBS = {
    "narrator_definition": ("audio_narator_*.wav",),
}
```

  Character-voice samples are root-level WAVs named `audio_<name>.wav`
  (`character_voices_service.py:477`), symmetrical with the narrator's
  `audio_narator_<id>.wav` (`narrator_definition_service.py:1339`), but nothing
  deletes them in bulk — `character_voices_service` only unlinks one sample at a
  time (line 536).

- **Why it matters:** a reset that includes `character_voices` (e.g.
  `project_workspace_service._reset_incompatible_chunking_data`, which passes no
  `preserve_operation_kinds`) removes `characters_voice.json` but leaves every
  generated sample WAV behind. They are dead weight in the project folder and in
  every snapshot/export. Blast radius is limited: they cannot be silently reused
  as clone references, because `audio_blocks_service.py:1322` requires the
  sample metadata (which lives in the deleted `characters_voice.json`) in
  addition to the file.

- **Fix:** give the kind its own glob, mirroring the narrator entry:

```python
_OPERATION_ARTIFACT_GLOBS = {
    "narrator_definition": ("audio_narator_*.wav",),
    "character_voices": ("audio_*.wav",),
}
```

  (order is safe: `character_voices` is reset after `narrator_definition` in
  `WORKFLOW_OPERATION_ORDER`, and both are cleared together in every reset path
  that reaches either one — no current caller preserves `character_voices` while
  resetting `narrator_definition`.)

## Duplication

Two pairs of near-identical helpers have already drifted apart in ways that
matter:

1. **`downstream_operation_kinds`** exists in
   `operation_runtime_service.py:138-154` and
   `workflow_impact_service.py:143-154` with *different* error behaviour: the
   runtime version returns `()` for an unrecognized kind, the impact version
   raises `ValueError` via `operation_index`. A typo'd or renamed operation kind
   at a `reset_operation_data(...)` call site therefore becomes a silent no-op —
   no deletion, no error, no log — instead of an immediate failure. The same
   split exists between `_normalized_operation_kind_set`
   (`operation_runtime_service.py:630`) and `_normalize_operation_kinds`
   (`workflow_impact_service.py:458`), where only the latter validates its
   members. At minimum, `reset_operation_data` should log a warning when
   `downstream_operation_kinds` returns empty for a non-empty kind.

2. **Manifest operation sync** is implemented twice —
   `workflow_controller_service.sync_manifest_operation_from_disk` and
   `project_workspace_service.sync_manifest_operation_summary` — with different
   manifest bases (in-memory snapshot vs. reload from disk) and different stage
   policies (assign vs. promote-only). That divergence *is* OC-1; collapsing the
   controller helper onto the service helper removes both the duplication and
   the bug.

Minor, non-bug: `_collect_or_delete_artifact_path`
(`workflow_impact_service.py:564-573`) adds `path_text` to `seen_paths` and then
discards it two lines later on the success branch; the only lasting effect is
that rejected unsafe paths linger in a set keyed by project-relative labels,
which they can never collide with. Dead code, no behavioural impact.

## Verified-clean notes

- **Relative-path validation** (`validate_project_relative_path`,
  `resolve_project_relative_path`): correctly rejects POSIX-absolute,
  Windows-absolute, drive-relative (`C:foo`), UNC (`//server/share`) and any
  `..` component via both `Path` and `PureWindowsPath`, then re-checks
  containment after `resolve(strict=False)`. No escape found.
- **Deletion containment**: `_collect_or_delete_resolved_path` calls
  `is_path_inside_project` before every `unlink()`; `reset_audio_assembly_outputs`
  routes each `rglob` hit through it. `reset_operation_data`'s `rglob` sweeps
  stay under the project root and `rglob` does not descend directory symlinks.
- **Progress clamping**: `progress_percent` guards `progress_total <= 0`, floors,
  and clamps to `[0, 100]`; `OperationProgressDialog.update_progress` clamps
  again (`test_operation_progress_dialog` feeds it 135 and gets 100).
- **Reset ordering**: `_OPERATION_ARTIFACT_FILE_NAMES` has an entry for all ten
  kinds in `config.WORKFLOW_OPERATION_ORDER`, and `downstream_operation_kinds`
  slices that tuple, so `include_current` semantics match the knowledge doc
  (chunking reset owns `chunks_text.json` + `log_ai_chunking_*.log`, and does not
  touch Extraction/Cleanup).
- **Worker thread lifecycle**: worker is parentless and `moveToThread`'d before
  `start()`; all four terminal signals cross into `ThreadedOperationUiBridge`
  (parented to the window) via auto/queued connections, so no widget is touched
  from the worker thread; `worker.deleteLater` is flushed when the thread's event
  loop exits; `_clear_threaded_operation` is driven by `thread.finished` and
  clears every bookkeeping field including the bridge.
- **Shutdown wait loop** (`_wait_for_threaded_operation_shutdown`): the
  `deleteLater`-before-`handle_finished` connection order means
  `window._active_operation_thread` can only still be non-`None` when the
  thread object's deferred delete has not yet been posted, so
  `operation_thread.wait(...)` cannot run against a deleted C++ object.
- **Cancellation**: `threading.Event` is the only cross-thread channel;
  `raise_if_cancelled` / `OperationCancelledError` route to the cancel handler,
  which correctly does *not* beep, while success and failure do
  (`operation_runner_controller.py:368, 383, 398-400`).
- **Audio file locking**: every reset path that deletes generated WAVs
  (`_reset_audio_blocks_and_downstream`, `_reset_audio_assembly_after_audio_blocks_change`,
  the voice-invalidation path) calls `_stop_audio_blocks_and_assembly_playback`
  first, and `MainWindow.stop_all_audio_playback` clears every player's source —
  so `unlink()` will not hit a Windows sharing violation on a file still loaded
  in `QMediaPlayer`.
- **Split-part naming**: `workflow_impact_service._iter_audio_block_artifact_paths`
  produces `audio_blocks/parts/<stem>_partNNN.wav` with the same `1`-based
  `:03d` formatting as `audio_blocks_artifact_service` (line 62), so selective
  deletion does not orphan part files.
- **Startup**: `app.main` tolerates `initialize_logging()` returning `None`,
  applies the theme before `MainWindow` construction, and always calls
  `shutdown_logging()`; `int(settings_payload.get("ui_scroll_steps_per_wheel_notch", ...))`
  cannot raise because `settings_service` repairs that key to an in-range `int`
  (lines 453-462).
- **`NavigationSidebar.apply_language`** mutates `_page_labels` while iterating
  it, but only ever reassigns existing keys, so no `RuntimeError`.
- **`MainWindow._audio_assembly_playback_starting`** is set in
  `stop_all_audio_playback` but not in `__init__`; every read site uses
  `getattr(window, ..., False)`, so no `AttributeError`.
