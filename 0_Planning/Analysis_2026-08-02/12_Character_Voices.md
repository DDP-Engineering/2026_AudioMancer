# Component Review — Character Voices

_Reviewed 2026-08-02. Files: `services/character_voices_service.py` (1305), `services/character_voices_state_service.py` (540), `services/voice_sample_import_service.py` (148), `ui/pages/character_voices_page.py` (673), `ui/controllers/character_voices_ui_controller.py` (1070). Total ~3736 lines._

## Summary

The component is in good shape overall: the character-ID -> target-ID mapping survives renames, sample-file naming cannot collide across characters, the Qt list index -> target-ID mapping is sound, and the batch "regenerate everything" behaviour is intentional and clearly disclosed in the confirmation dialog. One genuine **Critical** defect exists: simply opening the Character Voices page for the first time permanently promotes the project manifest to `character_voices_ready` and records the operation as `completed` with zero character samples generated (reproduced empirically). Beyond that: 1 Major (unhandled `OSError` on sample import terminates the app) and 2 Minor findings.

## Findings

### [CV-1] First entry to the page marks Character Voices complete and permanently promotes the project stage — **Critical**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py:886-925`, with `services/character_voices_service.py:750-774`
- **What:** `handle_page_activated` calls `_sync_manifest_stage` *before* `MainWindow.show_project_state` has ever built the page state, so `window._character_voices_page._targets` is still `[]`. The fallback that reloads targets from disk only fires when `characters_voice.json` already exists — but that file is created lazily by `build_character_voices_state(initialize_defaults=True)`, i.e. on this very first visit, *after* `handle_page_activated` has already run.

  `main_window.py:242-252` establishes the ordering:

  ```python
  if page_id == "character_voices":
      self._character_voices_missing_narrator_popup_shown = False
      character_voices_ui_controller.handle_page_activated(self)   # runs first, _targets == []
  if self._current_project_root is not None and self._current_manifest is not None:
      self.show_project_state(self._current_project_root, self._current_manifest)   # creates the file
  ```

  `_sync_manifest_stage` then computes readiness from an empty list:

  ```python
  voice_targets = list(window._character_voices_page._targets)  # noqa: SLF001
  if not voice_targets and (window._current_project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).is_file():
      voice_targets = character_voices_service.load_voice_plan(window._current_project_root)
  desired_stage = (
      "character_voices_ready"
      if character_voices_service.character_voices_is_ready(window._current_project_root, voice_targets)
      else "narrator_definition_ready"
  )
  ```

  and `character_voices_is_ready` is vacuously true for an empty list:

  ```python
  character_targets = [
      target for target in voice_targets if str(target.get("target_kind", "")).strip() == TARGET_KIND_CHARACTER
  ]
  return all(
      has_target_sample(project_root, str(target.get("target_id", "")).strip(), voice_targets)
      for target in character_targets
  )   # all([]) is True
  ```

- **Why it matters:** Reproduced with a scripted run (project with a selected+sampled narrator, 3 discovered characters, `current_stage = "narrator_definition_ready"`, `characters_voice.json` absent). A single `window.set_current_page("character_voices")` produces:

  ```
  current_stage      = character_voices_ready
  operation summary  = {'status': 'completed', 'progress_current': 0, 'progress_total': 0, 'mode': None, 'warning_count': 0}
  character count    = 3
  samples on disk    = 0
  ```

  This is written to `project.json`. It is **not** self-correcting: on a second visit the operation summary does repair itself to `in_progress 1/3`, but `project_workspace_service.sync_manifest_operation_summary` only ever *promotes* the stage (`if _stage_rank(normalized_stage) > _stage_rank(stored_stage)`, line 512, documented as deliberate), so `current_stage` stays `character_voices_ready` forever. Downstream stage gating, Home workflow display, completion evidence, export and snapshot all read a stage the project never actually reached.

- **Fix:** Two one-line changes, either of which removes the defect; both are worth having.
  1. In `_sync_manifest_stage`, bail out when the targets file does not exist yet — there is nothing to sync:
     ```python
     if not voice_targets:
         if not (window._current_project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).is_file():
             return
         voice_targets = character_voices_service.load_voice_plan(window._current_project_root)
     ```
  2. In `character_voices_is_ready`, require a non-empty target list: `return bool(voice_targets) and all(...)`.

---

### [CV-2] Unhandled `OSError` during voice-sample import terminates the application — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py:146-156`, with `services/character_voices_service.py:631`
- **What:** The import call site catches only `ValueError`:

  ```python
  try:
      character_voices_service.import_target_sample(
          window._current_project_root,
          target_payload,
          voice_language,
          normalized_sample_text,
          selected_file,
      )
  except ValueError as error:
      _show_voice_sample_import_error(window, error, current_language)
      return
  ```

  but `import_target_sample` performs two operations that raise `OSError`, not `ValueError`:

  ```python
  _write_bytes_atomic(audio_path, source_path.read_bytes())
  ```

  `source_path.read_bytes()` raises `PermissionError`/`FileNotFoundError` (both `OSError`), and `_write_bytes_atomic` documents `@exception OSError Raised when the temporary write or replacement fails.`

- **Why it matters:** This runs inside a Qt slot. The project pins `PySide6>=6.8,<7.0` (`pyproject.toml:12`) and installs no `sys.excepthook` (grep for `excepthook` across `src/audiomancer/` returns nothing), so an exception escaping a slot invoked from C++ terminates the process rather than showing a dialog. Triggers are lightly-abnormal but real on Windows: the operator picks a WAV from a USB stick or network share that disconnects between the file dialog and the copy; the source file is held exclusively by an audio editor; or the project drive is full or read-only. The operator loses the app, not just the import. Note there is a real window here — the file dialog, a validation pass, a multi-line transcript dialog and an invalidation confirmation all run between file selection and the copy.
- **Fix:** Widen the except clause and report the failure instead of escaping:
  ```python
  except ValueError as error:
      _show_voice_sample_import_error(window, error, current_language)
      return
  except OSError as error:
      QMessageBox.warning(
          window,
          ui_state_service.translate("dialog.project_error_title", current_language),
          str(error),
      )
      return
  ```

---

### [CV-3] Cancelling a batch sample run leaves the page and manifest showing the pre-batch state — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py:488-502`
- **What:** The cancel handler refreshes settings and shows a message, but — unlike the sibling failure handler at lines 466-485 — never refreshes the page state or the manifest summary:

  ```python
  def _handle_generate_sample_cancelled(window: "MainWindow", message: str, current_language: str) -> None:
      _ = message
      window._settings_payload = settings_service.load_settings()
      misc_ui_controller.show_message(
          window,
          ui_state_service.translate("status.operation_cancelled", current_language),
      )
  ```

  `_handle_generate_sample_failure` by contrast does call `window.show_project_state(...)`. `operation_runner_controller._handle_operation_cancelled` (line 387-400) only forwards to `cancel_handler(message)`, so nothing else compensates.

- **Why it matters:** `_generate_and_store_character_samples` persists each sample as it completes and only checks cancellation *between* targets (line 734). Cancel a 10-character batch after target 7 and 7 WAVs plus their metadata are on disk, but the target list still renders "sample missing" for all 10, the status pane still reports the old "targets with samples" count, and `operations.character_voices` in `project.json` is not updated. The operator reasonably concludes the cancel rolled everything back and re-runs the whole batch. State is correct on disk and self-heals on the next page visit, hence Minor.
- **Fix:** Mirror the failure handler — add the `show_project_state(...)` + `_sync_manifest_stage(window)` pair to `_handle_generate_sample_cancelled`.

---

### [CV-4] Prompt edit mode is a dead end when nothing is typed — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/pages/character_voices_page.py:416-466`
- **What:** There is no Cancel control, and `_apply_control_state` disables every remaining control while `_edit_mode` is true and `_dirty` is false:

  ```python
  list_enabled = self._project_active and not self._busy and not self._preview_active and not self._edit_mode
  ...
  self._save_prompt_button.setEnabled(
      self._project_active and not self._busy and not self._preview_active and self._edit_mode and self._dirty
  )
  ```

  Import / Edit / Generate / Generate-All all require `not self._edit_mode`; Preview requires `self._preview_available`, which is false because `begin_target_prompt_edit` (`character_voices_service.py:338`) has just deleted the target's sample.

- **Why it matters:** Operator clicks "Edit Voice Prompt", confirms both dialogs (losing the existing approved sample in the process), then decides not to change anything. Save is disabled (not dirty), the target list is disabled, every action button is disabled. The only escape is sidebar navigation to another page and back, which resets `_edit_mode` via `set_character_voices_state`. Not data loss beyond the already-confirmed sample deletion, but the page appears frozen.
- **Fix:** Enable Save whenever `_edit_mode` is true (saving the unchanged prompt is harmless and already re-clears the sample), or make the target list stay enabled and route a selection change through an "unsaved changes" prompt as `characters_ui_controller.handle_selection_change_requested` (line 332-359) already does for the Characters page.

## Duplication

- **Imported WAV is validated twice and read three times per import.** `handle_import_sample_requested:122` calls `voice_sample_import_service.validate_imported_wav_sample(selected_file)`, and `character_voices_service.import_target_sample:612` calls it again on the same path, before `source_path.read_bytes()` at line 631. `validate_imported_wav_sample` decodes every PCM sample in a pure-Python loop (`_audio_level_metrics:96-101`), so a 3-minute 48 kHz stereo 16-bit sample is fully scanned twice on the UI thread with no progress feedback. Collapsing this to a single validation — have `import_target_sample` accept the already-computed report, or drop the controller-side pre-check and rely on the service's `ValueError` — halves the work and removes the divergence risk between the two call sites.
- **Dead `model_parameters` branch, copy-pasted from the narrator controller.** `character_voices_ui_controller.py:661-663`:
  ```python
  model_parameters=dict(generation_request.get("model_parameters", {}))
  if isinstance(generation_request.get("model_parameters"), dict)
  else None,
  ```
  `character_voices_service._build_generation_request` (line 1234-1243) never emits a `model_parameters` key, so this always evaluates to `None`. The identical dead branch exists at `narator_voice_ui_controller.py:1050-1052`. Harmless today, but it reads as a supported feature that does not exist.

## Verified-clean notes

- **Assignments survive renames.** `character_discovery_service.update_character_profile` (line 758-786) preserves `character_id` across a rename, `character_target_id` derives `character_<id>`, and `sync_voice_plan` carries `sample_audio_path` / `sample_metadata` forward via `{**existing_target, ...}`. A renamed character keeps its sample; the file name is not re-derived because the stored `sample_audio_path` wins in `target_sample_paths`.
- **Sample file names cannot collide between characters.** The fallback name `audio_<normalized display_name>.wav` looked risky, but discovery groups candidates by `_normalize_identity` (`re.sub(r"[^a-z0-9]+", "", name.casefold())`), which is strictly coarser than `_normalized_audio_name` for ASCII names — two distinct accepted characters therefore cannot produce the same audio name. Manual additions are duplicate-checked against the same key in `validate_manual_character_name`.
- **Qt row index vs target ID.** The `QListWidget` is never sorted or filtered, `_refresh_target_list` rebuilds it in `self._targets` order under `blockSignals`, and `_handle_target_selection_changed` bounds-checks `row` before indexing. No mismatch path found.
- **Missing sample file at generation time.** `has_target_sample` requires both `audio_path.is_file()` and non-`None` metadata, so an externally deleted WAV correctly shows as missing and re-generation reuses the stored path. `audio_blocks_service.py:1322` independently re-checks `is_file()` before consuming a character sample.
- **Imported transcript is paired with the right audio.** `import_target_sample` stores the operator-typed transcript in `sample_metadata["preview_text"]`, and `audio_blocks_service.py:1326` reads exactly that field for clone prompts — the stale target-level `preview_text` shown in the editor is never used for cloning.
- **Batch regeneration scope is intentional.** `_current_character_target_payloads` returns *all* generatable character targets, not only those missing samples. Despite the `generate_missing_samples` identifiers, the confirmation text is explicit: `"AudioMancer will regenerate samples for all {sample_count} current character target(s). Existing character samples will be replaced."` (`ui_state_service.py:814`). Operator-approved samples are not clobbered without warning.
- **`sync_same_narrator_samples` overwriting approved samples is unreachable.** It does overwrite every character sample with the narrator WAV, but `voice_assignment_mode` is frozen by `project_options_locked` before any Character Voices work can happen (`home_ui_controller.py:230-234, 247-269`), so the "generate 20 samples then switch to same_narrator" path does not exist.
- **`_write_bytes_atomic`** is correct: same-directory `mkstemp`, `flush` + `fsync`, `os.replace`, and best-effort temp cleanup on `OSError`.
- **Latent, not currently reachable:** `_copied_narrator_sample_is_current` calls `voice_target_by_id("", target_id, voice_targets)` (`character_voices_service.py:1169`). This is safe only because `voice_targets` is always supplied by its single call site; if a future caller passed `None`, `load_voice_plan("")` would create `characters_voice.json` in the process working directory.
- **Dead code:** `CharacterVoicesPage.apply_selected_target` and `CharacterVoicesPage.is_dirty` have no callers in `src/` (the Characters page equivalents do). Harmless, but the missing `is_dirty` guard is why CV-4 has no clean exit.
