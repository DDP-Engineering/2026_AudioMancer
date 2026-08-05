# Component Review — Project Lifecycle

_Reviewed 2026-08-02. Files: `services/project_workspace_service.py` (1822), `services/project_export_service.py` (1333), `services/project_snapshot_service.py` (217), `services/persistence_service.py` (101), `services/import_service.py` (136), `services/source_ledger_service.py` (370), `services/home_presenter_service.py` (218), `ui/pages/home_page.py` (977), `ui/controllers/home_ui_controller.py` (617). Total ~5790 lines._

## Implementation Update — 2026-08-03

Commit `2db1297660d200b7101b8b3c59dbba8dbda9439d` resolves PL-1, PL-3, and PL-5 under durable requirement `REQ-FUNC-b1f49831`. The implementation copies and atomically promotes a safely named new source before deleting the previous source, then uses the centralized Extraction-and-downstream artifact reset and manifest-summary reset helpers. It preserves the registered new source plus the unlocked target-language, selected-voice-language, and voice-assignment options.

Regression evidence covers processed-project replacement, complete prior-state preservation after an injected partial-copy failure, and current/case-variant reserved source names. Delivery verification completed with 1,205 tests passed, 1 skipped, and 1 deselected; the focused post-suite reserved-name replacement check also passed.

| Finding | Status | Verification |
|---|---|---|
| PL-1 | Resolved | Processed replacement removes stale Extraction and downstream artifacts, resets all compact summaries, sets `source_selected`, preserves options, and retains the new source. |
| PL-3 | Resolved | A partial `copy2` failure leaves the complete previous project tree byte-for-byte unchanged. |
| PL-5 | Resolved | `extracted_text.txt`, `clean_text.txt`, and case variants receive safe numbered names derived from the centralized artifact registry. |

The original seven-finding inventory below is retained as review history. At that point, the open Project Lifecycle findings were PL-2, PL-4, PL-6, and PL-7: 0 Critical, 1 Major, and 3 Minor.

## Implementation Update — 2026-08-04

Commit `e7d67a52d4a82d3e658de69b4eed62f900c1d873` resolves PL-2 under `REQ-UX-da3b47c4`.

- Project creation and source import now catch both `OSError` and `ValueError`, and the confirmed-repair path has the same protection. This includes `PermissionError`, `FileExistsError`, and `FileNotFoundError` through the `OSError` hierarchy.
- Failures are shown in a localized project warning that includes the original error text.
- A failed operation returns before project activation, success notification, or mutation of the window's project and manifest state. Successful creation, import, and repair flows are unchanged, and no global exception hook was added.
- Regression coverage exercises project-creation `PermissionError`, source-import `PermissionError`, and confirmed-repair `OSError`, verifying the warning and the absence of activation or success side effects.
- Verification completed with 49 focused tests passing and the full suite at 1,256 passed, 1 skipped, and 1 deselected.

| Finding | Status | Evidence |
|---|---|---|
| PL-2 | Resolved | Local containment in the Home UI controller plus regression tests for creation, import, and repair failures. |

After this update, the open Project Lifecycle findings are PL-4, PL-6, and PL-7: 0 Critical, 0 Major, and 3 Minor.

## Summary

The manifest/validation core is in good shape: atomic writes, project-relative path containment, symlink exclusion in snapshots and the "promote-only" stage rule are all implemented correctly and consistently with the knowledge doc. Seven findings were originally recorded: 1 Critical, 1 Major, and 5 Minor. The source-replacement cluster and Home Qt-slot error-handling defect are resolved as recorded above; the remaining open defects are same-source re-selection, language-switch status text, and dotted export names.

## Findings

### [PL-1] Replacing the source document lowers `current_stage` but leaves the previous book's artifacts and completed operation summaries in place - **Critical, resolved 2026-08-03**

- **Resolution (2026-08-03):** `home_ui_controller.handle_import_source_requested` now registers the successfully copied source in the pending manifest, calls `text_extraction_service.reset_extraction_and_downstream`, applies `text_cleanup_state_service.build_manifest_after_extraction_reset`, and saves the resulting manifest. The centralized helpers remove Extraction and every downstream generated artifact, reset every compact operation summary, and set `current_stage = "source_selected"`; the replacement branch does not rewrite `target_language`, `selected_voice_language`, or `voice_assignment_mode`.
- **Resolution evidence:** `test_home_ui_controller_replaces_processed_source_as_one_consistent_reset` exercises a project at `audio_assembly_ready`, verifies the root and generated-audio artifacts are gone, compares summaries with new-project defaults, checks all three options, and proves a reserved-name new source remains registered after reset. Implemented in `2db1297` under `REQ-FUNC-b1f49831`.
- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py:227-238` (historical location before `2db1297`)
- **What:** The import handler rewrites the manifest by hand instead of going through the reset path:

```python
    updated_manifest = dict(window._current_manifest)
    updated_manifest["source_document"] = source_document
    updated_manifest["current_stage"] = "source_selected"
    if not bool(updated_manifest.get("project_options_locked", False)):
        ...
    project_workspace_service.save_manifest(
        updated_manifest,
        window._current_project_root,
    )
```

  `operations` is carried over untouched, and no domain artifact is deleted. This is exactly the contradiction the workspace service documents as forbidden (`project_workspace_service.py:494-499`: *"a lower `current_stage` argument is ignored … Lowering it there would strand completed downstream summaries above the stage … Invalidating downstream work belongs to the explicit reset path, which clears artifacts and summaries together."*). `sync_manifest_operation_summary` refuses to lower the stage for that reason; this call site bypasses it by writing the manifest directly. The sibling flow does it correctly — `text_cleanup_ui_controller.py:40-44` calls `reset_extraction_and_downstream()` **and** `build_manifest_after_extraction_reset()` before re-running extraction.
- **Why it matters:** Nothing forces the operator to lock project options before processing: every workflow page is enabled as soon as a project is active (`main_window.py:261-269`), no page checks `project_options_locked`, and `_import_button.setEnabled(self._project_active and not self._project_options_locked)` (`home_page.py:566`) therefore keeps "Select Source File" live after extraction/cleanup/chunking have run. Concrete sequence: create project → import `BookA.pdf` → run Extraction and Cleanup (options still unlocked) → notice it was the wrong book → import `BookB.epub`. Result on disk: `BookA`'s `extracted_text.txt`, `source_ledger.json`, `extraction_metadata.json`, `clean_text.txt`, `cleanup.json` remain, `project.json` says `current_stage = "source_selected"` while `operations.cleanup.status == "completed"`, and `source_document` points at `BookB.epub`. Home still shows Cleanup finished, the Cleaned Text export is still "available" and exports `BookA`'s text, and the user can continue straight into Chunking on `BookA`'s content. On the next open, `_build_project_manifest_healing_result` finds the stale (self-consistent) `BookA` artifacts, computes a higher `verified_stage`, and offers a "metadata can be normalized" repair that promotes the stage back — laundering the corruption into a state that looks legitimate.
- **Fix:** In `handle_import_source_requested`, when the manifest already had a `source_document`, reuse the existing reset helpers instead of setting the stage by hand:

```python
    if isinstance(previous_source_document, dict):
        text_extraction_service.reset_extraction_and_downstream(window._current_project_root)
        updated_manifest = text_cleanup_state_service.build_manifest_after_extraction_reset(updated_manifest)
    updated_manifest["source_document"] = source_document
```

  (`build_manifest_after_extraction_reset` / `build_manifest_after_operation_reset(manifest, "extraction")` already set `current_stage = "source_selected"` and reset every operation summary — `text_cleanup_state_service.py:188-218`.)

### [PL-2] Filesystem errors during project creation and source import escape the Qt slot — **Major, resolved 2026-08-04**

- **Resolution (2026-08-04):** Commit `e7d67a52d4a82d3e658de69b4eed62f900c1d873` adds local `(OSError, ValueError)` containment to project creation, source import, and confirmed repair. Each failure produces a localized warning with the original exception and returns before activation, success notification, or project/manifest mutation.
- **Resolution evidence:** `test_home_ui_controller_contains_project_creation_filesystem_error`, `test_home_ui_controller_contains_source_import_filesystem_error`, and `test_home_ui_controller_contains_confirmed_repair_filesystem_error` cover the newly contained filesystem failures under `REQ-UX-da3b47c4`; the existing open-project warning regression remains green.

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py:87` and `:219`
- **What:** Both handlers catch only a subset of `OSError`:

```python
    except (FileExistsError, FileNotFoundError, ValueError) as error:   # line 87, create_project
```
```python
    except (FileNotFoundError, ValueError) as error:                     # line 219, import_source
```

  `create_project` reaches `project_root.mkdir(parents=True, exist_ok=True)` and `save_manifest(...)` (`project_workspace_service.py:130-134`); `import_source` reaches `previous_path.unlink()` and `shutil.copy2(...)` (`import_service.py:71,110`). `PermissionError`, `OSError(ENOSPC)` and Windows `ENAMETOOLONG` are none of the three caught types. No `sys.excepthook` is installed anywhere in `src/`, so an exception raised inside a slot invoked from Qt terminates the application rather than showing the existing localized `dialog.project_error_title` warning.
- **Why it matters:** Plausible triggers: the operator picks a non-writable parent folder in the create dialog (`C:\`, `C:\Program Files`, a read-only network share) → `PermissionError` from `mkdir` → app dies with a console traceback and the half-typed project is lost. Or the previously imported source is open in another Windows application when a replacement is imported → `PermissionError` from `unlink()` → app dies. `validate_project_name` also has no length limit, so a long name under a deep parent path raises a bare `OSError` from `mkdir` on Windows instead of a clean validation message.
- **Fix:** Widen both excepts to `except (OSError, ValueError) as error:` (`FileExistsError`/`FileNotFoundError` are `OSError` subclasses, so the existing messages still work). The same one-word change applies to the unguarded `repair_project(open_result)` call at `home_ui_controller.py:136`, which writes the manifest with no handler at all.

### [PL-3] Source import deletes the previous stored source before the new copy succeeds - **Minor, resolved 2026-08-03**

- **Resolution (2026-08-03):** `import_service.import_source` validates the previous manifest path before mutation, copies through a same-project temporary file, atomically promotes the completed copy, builds its manifest metadata, and only then deletes the previous stored source. A failed copy removes its incomplete temporary file before propagating the error.
- **Resolution evidence:** `test_import_source_copy_failure_preserves_complete_previous_project_state` injects a failure after writing partial data and verifies that the previous source, `project.json`, Extraction, Cleanup, and Chunking files remain byte-for-byte identical with no new project file. Implemented in `2db1297` under `REQ-FUNC-b1f49831`.
- **File:** `04_Software/AudioMancer/src/audiomancer/services/import_service.py:62-71` (historical location before `2db1297`)
- **What:**

```python
    _delete_previous_source_file(
        resolved_project_root,
        previous_source_document,
        resolved_source,
    )
    destination_path = _build_unique_destination(
        resolved_project_root,
        resolved_source.name,
    )
    shutil.copy2(resolved_source, destination_path)
```

  The unlink happens first and there is no rollback if `copy2` raises.
- **Why it matters:** If the copy fails (disk full, unreadable network/cloud-placeholder source, read-only project folder) the project is left with no source file at all while `project.json` still records the old `source_document.stored_relative_path`; combined with PL-2 the app also terminates before the user is told. The destination is unique by construction (`_build_unique_destination`), so the delete can safely be deferred.
- **Fix:** Move `_delete_previous_source_file(...)` to after `shutil.copy2(...)` succeeds.

### [PL-4] Re-selecting the project's own stored source duplicates the file and orphans the old copy — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/import_service.py:104-110`, `113-132`
- **What:** The "same file" guard only suppresses the delete; it does not stop the copy:

```python
    try:
        if previous_path == selected_source.resolve():
            return
    except FileNotFoundError:
        pass
    if previous_path.is_file():
        previous_path.unlink()
```

  Control then falls through to `_build_unique_destination`, which sees `book.pdf` already present and returns `book_1.pdf`.
- **Why it matters:** The import dialog opens **inside the project root** (`home_ui_controller.py:206`: `str(window._current_project_root)`), so the stored source is the most visible candidate file. Re-selecting it leaves `book.pdf` orphaned in the project while the manifest points at `book_1.pdf`; repeating adds `book_2.pdf`, and every orphan is also included in project ZIP snapshots. For a large PDF/EPUB this silently multiplies project size.
- **Fix:** When `previous_path == selected_source.resolve()`, return the existing manifest record unchanged instead of copying (or have `import_source` short-circuit before `_build_unique_destination`).

### [PL-5] An imported source may be stored under a reserved artifact name and later deleted by its own workflow - **Minor, resolved 2026-08-03**

- **Resolution (2026-08-03):** `operation_runtime_service.reserved_project_artifact_file_names` exposes the existing centralized root-artifact ownership registry. `_build_unique_destination` treats those names as collisions using case-insensitive comparison, so it never duplicates the downstream deletion list and stores a source such as `extracted_text.txt` as `extracted_text_1.txt`.
- **Resolution evidence:** `test_import_source_avoids_reserved_generated_artifact_names` covers `extracted_text.txt`, `clean_text.txt`, and an uppercase variant; the processed-project controller regression additionally proves `extracted_text_1.txt` survives the Extraction-and-downstream reset and remains the manifest source. Implemented in `2db1297` under `REQ-FUNC-b1f49831`.
- **File:** `04_Software/AudioMancer/src/audiomancer/services/import_service.py:113-132` (historical location before `2db1297`)
- **What:** `_build_unique_destination` only avoids *existing* files; it does not avoid the project's reserved root-level artifact names:

```python
    candidate = destination_dir / file_name
    if not candidate.exists():
        return candidate
```

  `.txt` is a supported source suffix, so importing `extracted_text.txt` (or `clean_text.txt`) into a fresh project stores the source at exactly the path a downstream operation owns.
- **Why it matters:** `text_extraction_service.extract_text` unconditionally removes its own outputs before running: `for artifact_name in (config.EXTRACTED_TEXT_FILE_NAME, config.SOURCE_LEDGER_FILE_NAME): (root / artifact_name).unlink(missing_ok=True)` (`text_extraction_service.py:66-67`). The imported source is deleted before it is read, the extraction run then fails on a missing file, and the project's only copy of the source is gone. The same shape applies to `clean_text.txt` via the cleanup reset (`operation_runtime_service.py:59-66`).
- **Fix:** In `_build_unique_destination`, treat a collision with any reserved artifact name the same as a collision with an existing file — e.g. seed the loop when `file_name` is in the known root-level artifact name set (`config.EXTRACTED_TEXT_FILE_NAME`, `config.CLEANED_TEXT_FILE_NAME`, `config.PROJECT_MANIFEST_FILE_NAME`, …) so the copy lands on `extracted_text_1.txt`.

### [PL-6] Switching UI language relabels an unlocked source as locked — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/pages/home_page.py:611-615`
- **What:** `apply_language` re-implements the source-status text with an older two-state rule and overwrites the correct three-state text that `_refresh_summary_labels()` had just written one line earlier:

```python
        self._refresh_summary_labels()
        if self._source_locked:
            self._source_lock_label.setText(_build_locked_source_text(language, self._current_locked_source_name))
        else:
            self._source_lock_label.setText(ui_state_service.translate("home.no_source", language))
```

  `_refresh_summary_labels` uses `_build_source_status_text(language, self._source_locked, self._project_options_locked, ...)` (`home_page.py:744-751`), which distinguishes "selected" from "locked"; this block ignores `_project_options_locked` entirely.
- **Why it matters:** With a source imported but project options not yet locked, changing the UI language flips the summary line to the "source is locked / frozen" wording even though the operator can still replace the source. The wrong text persists until the next project-state refresh.
- **Fix:** Delete the `if/else` block — `_refresh_summary_labels()` already sets the label correctly for all three states.

### [PL-7] `with_suffix` truncates export/snapshot file names that contain a dot — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py:362-363`, `project_snapshot_service.py:70-73`, `project_export_service.py:280-281`
- **What:** All three normalize the extension with `Path.with_suffix`, which replaces everything after the **last** dot in the file name:

```python
    export_path = Path(selected_path)
    if export_path.suffix.lower() != required_extension:
        export_path = export_path.with_suffix(required_extension)
```

- **Why it matters:** A typed save name such as `Dune vol. 2` has `suffix == ". 2"`, so the file is written to `Dune vol.txt` / `Dune vol.zip` — silently not where the operator asked, and silently overwriting any earlier `Dune vol.zip`.
- **Fix:** Append instead of replace: `if not export_path.name.lower().endswith(required_extension): export_path = export_path.with_name(export_path.name + required_extension)` (same edit in `ensure_snapshot_extension` and `create_archive_export`).

## Duplication

- **Extension normalization** is implemented three times with the identical `with_suffix` flaw (PL-7): `home_ui_controller.py:362`, `project_snapshot_service.ensure_snapshot_extension`, `project_export_service.create_archive_export:280`. One shared `ensure_extension(path, ext)` helper would fix all three at once.
- **Source-status text** is derived in two places (`home_page._build_source_status_text` vs. the inline branch in `apply_language`), and the copies have already diverged — that divergence *is* PL-6.
- **`current_stage` semantics are defined twice and disagree.** `config.OPERATION_STAGE_BY_KIND` (used by `project_workspace_service._build_project_manifest_healing_result` and `_allowed_operations_for_stage`) treats `text_cleanup_ready` as "cleanup is done", while every runtime writer treats it as "ready to do cleanup" — e.g. `text_cleanup_service.py:510-515` writes `current_stage="text_chunking_ready"` on cleanup completion, and `home_presenter_service.stage_reached_index` (`index - 3`) also encodes the "ready to do X" reading. Today this is harmless because `target_stage = max(base_stage, verified_stage, key=_stage_rank)` always keeps the higher runtime value and `_apply_legacy_stage_fallbacks` is unreachable for normalized manifests, but the two conventions are one refactor away from producing a repair prompt on every open of a finished project.

## Verified-clean notes

- `persistence_service.write_text_atomic` / `write_json_atomic`: `mkstemp` in the target directory, `flush` + `fsync`, `os.replace`, and temp cleanup on `OSError`. `newline=""` keeps the exact bytes, so `source_ledger_service`'s SHA-256 round-trip through `read_text` is stable.
- Path containment: `validate_project_relative_path` rejects POSIX *and* Windows absolute forms and `..`; `resolve_project_relative_path` re-checks containment after `resolve()`, so manifest-driven symlink escapes are blocked. `_validate_project_scoped_manifest_paths` is applied on load, save, and repair.
- `create_project` file/non-empty-directory handling matches the documented contract exactly, including the `Project path already exists as a file:` message and leaving the target untouched.
- `validate_project_name` covers `.`/`..`, the invalid-character set, control characters, trailing space/dot, and `CON.txt`-style reserved bases via `split(".", 1)[0]`. Only the missing length bound is a gap (folded into PL-2).
- `open_project` chunking recovery: `OSError` is correctly re-raised from `error.__cause__` without any reset or deletion, `IncompatibleChunkingDocumentError` subclasses `ValueError` so a second failure is still caught by the Home slot, and validation is retried exactly once.
- `project_snapshot_service`: writes to a same-directory temp `.zip.tmp`, `os.replace`s only after the archive closes, deletes the temp on cancel/failure, refuses destinations inside the project, and `_iter_project_files` skips both symlinked directories and symlinked files.
- Archive entry names go through `safe_file_stem` / `Path(...).name`, so no zip-slip or absolute member paths are reachable in `create_archive_export`.
- No manifest read-modify-write race in practice: the operation progress dialog is `ApplicationModal` (`operation_progress_dialog.py:44-45`), so Home actions cannot run concurrently with a worker thread's `sync_manifest_operation_summary`. (`home_page._refresh_import_button` not honouring `_operation_busy` is therefore only a latent defence gap, not a live bug.)
- Manifest-healing evidence matches what the runtime persists (e.g. `chunking_document_service.derive_operation_state` is used by both the writer and the healer, `text_cleanup_service._manifest_summary` and `_cleanup_completion_evidence` agree on `mode="hybrid"` and `warning_count`), so a completed project does not get a spurious repair prompt on every open.
