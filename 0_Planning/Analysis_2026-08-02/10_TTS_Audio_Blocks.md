# Component Review — TTS Audio Blocks

_Reviewed 2026-08-02. Files: `services/audio_blocks_service.py`, `services/audio_blocks_state_service.py`, `services/audio_blocks_artifact_service.py`, `ui/pages/audio_blocks_page.py`, `ui/controllers/audio_blocks_ui_controller.py`. Total ~6340 lines._

## Summary

The core identity contract is sound: the WAV name is a pure function of `speech_block_id`, ids are `NNNN-NNNNNN` so the filename sanitizer cannot collide, deletion is confined to the project root, and WAV bytes are validated before they are written, so a cancelled run cannot leave a half-written file that later passes as valid. Six real defects were found: four Major and two Minor. The two that will actually bite an operator are the Scene Ambience metadata-only block that exposes a WAV path it does not own (which makes Audio Assembly abort), and the fact that "Re-Generate Audio" runs full TTS on a pause/indication block's marker text. The documented split-part resume checkpoint is also effectively dead code.

## Findings

### [AB-1] Metadata-only Scene Ambience blocks expose a WAV path that does not exist — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py:3169`

- **What:** `_attach_derived_audio_path` excludes only pause and indication blocks from owning a WAV, but an approved Scene Ambience block is also metadata-only whenever the operator runs generation with the Audio Blocks "Scene Ambience Audio" selector set to Off:

```python
    speech_block_id = str(audio_block.get("speech_block_id", "")).strip()
    owns_audio = is_generated(audio_block) and str(audio_block.get("content_kind", "")).strip() not in {
        speech_blocks_service.CONTENT_KIND_PAUSE,
        speech_blocks_service.CONTENT_KIND_INDICATION,
    }
    if not speech_block_id or not owns_audio:
        return {**audio_block, "audio_relative_path": None}
    audio_path = _audio_artifact_path(project_root, speech_block_id)
    return {**audio_block, "audio_relative_path": relative_to_project(project_root, audio_path)}
```

  Such a block *is* flagged generated: `_initialize_audio_blocks` sets `metadata_only_completed = metadata_only and (speech_block_approved or content_kind == CONTENT_KIND_PAUSE)` (line 2359) and `_apply_scene_ambience_audio_policy` (line 2509) only re-marks it `metadata_only` — it never clears `generated`. So the persisted entry is `generated=True`, `audio_can_play=True`, and on load it gains `audio_relative_path = audio_blocks/<id>.wav` for a file that was never written. This directly contradicts the knowledge doc: "A set path therefore still means *generated audio exists on disk*".

- **Why it matters:** Scene Ambience placement enabled in TTS Settings + the Audio Blocks selector switched Off + approved ambience Speech Blocks. Audio Assembly loads these blocks through `load_audio_blocks`; `audio_assembly_service._is_assembly_block` (line 1539) includes an ambience block purely on a non-empty `audio_relative_path`, so it is grouped into a scene mix and `_mix_scene_group` raises `RuntimeError("Scene Ambience mix requires generated source WAV files.")`. The assembly stage fails outright and the only workarounds are turning off `include_scene_ambience` in Audio Assembly or generating ambience audio after all. The pre-composition guard at `audio_assembly_service.py:457` does not catch it, because that guard filters `metadata_only` blocks out first.

- **Fix:** Make `owns_audio` depend on the block actually owning audio rather than on a content-kind denylist, e.g. `owns_audio = is_generated(audio_block) and not bool(audio_block.get("metadata_only", False))`. Note that `_attach_current_speech_block_fields` (line 3133) currently re-derives `metadata_only=True` for *every* Scene Ambience block, including genuinely generated ones, so that recomputation has to be corrected at the same time (e.g. keep `metadata_only` False for an ambience block whose WAV exists) — otherwise real ambience audio would lose its path.

### [AB-2] "Re-Generate Audio" runs speech synthesis on pause / indication blocks — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py:1090`

- **What:** `regenerate_audio_block` special-cases only Scene Ambience; there is no `metadata_only` guard, so a pause or indication block falls through to the full clone-and-generate path:

```python
    if (
        str(audio_blocks[target_index].get("content_kind", "")).strip()
        == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    ):
        ...
        return _persist_report_update(...)

    loaded_model_budget = _ensure_clone_model_loaded(
```

  ...ending in `audio_blocks[target_index] = _generate_audio_block(..., force_restart=True)` (line 1205). The page enables the button for any selected row — `self._regenerate_button.setEnabled(self._project_active and not self._busy and selected_block is not None)` (`audio_blocks_page.py:568`) — and `audio_blocks_state_service` sets `"can_regenerate_selected": current_block is not None`, so pause rows are freely selectable and regenerable.

- **Why it matters:** The operator selects a pause row (the list shows every block), clicks Re-Generate, confirms, and the runtime synthesizes speech for the pause marker text (`pause_duration_ms` just scrapes the first integer out of free-form text, so the text is human-readable prose). Results: a runtime call and GPU time wasted; an orphan `audio_blocks/<pause id>.wav` that Audio Assembly will never use because pause blocks are composed as silence; and `_generate_audio_block` returns `"approved": None`, so a previously auto-approved pause block becomes unapproved and Audio Assembly then refuses to run with "Approve every generated Audio Block…" until the operator re-approves it.

- **Fix:** At the top of `regenerate_audio_block`, after `target_index` is resolved, return the unchanged report (or raise a clear `ValueError`) when the target block is `metadata_only` and its content kind is not Scene Ambience.

### [AB-3] Split-part resume never resumes; a cancelled multi-part block restarts from part 1 — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py:2156`

- **What:** `_existing_part_paths` treats the persisted `split_part_count` as "parts already on disk" and bails out unless *all* of them exist:

```python
    persisted_part_count = _optional_int(audio_block.get("split_part_count"), 0) or 0
    if persisted_part_count <= 1 or persisted_part_count > len(split_plan["parts"]):
        return []
    speech_block_id = str(audio_block.get("speech_block_id", "")).strip()
    existing_paths: list[Path] = []
    for part_index in range(persisted_part_count):
        expected_path = _audio_part_artifact_path(project_root, speech_block_id, part_index)
        if not expected_path.is_file() or not _is_valid_wav_path(expected_path):
            return []
```

  But the per-part checkpoint persists the *planned total*, not the completed count (line 1902):

```python
        if len(split_plan["parts"]) > 1 and callable(checkpoint_callback):
            checkpoint_callback(
                {
                    **dict(audio_block),
                    "split_part_count": len(split_plan["parts"]),
```

  The checkpoint's `next_split_part_index` is written by `_persist_split_checkpoint` / `_persist_cancelled_state` and read back only to be re-written (line 752); nothing ever consumes it to skip completed parts.

- **Why it matters:** Cancel (or lose the runtime) during a long block split into e.g. 8 parts after 6 are on disk. On resume, `persisted_part_count == 8`, parts 7-8 are missing, `_existing_part_paths` returns `[]`, and generation restarts at part 1 — minutes of already-completed synthesis are thrown away. The contract in `TTS_Audio_Blocks.md` ("`next_split_part_index` … for truthful resume") is not honoured. The two existing tests around this only assert the negative cases and still set the removed `generated_part_relative_paths` field, so they pass vacuously.

- **Fix:** Persist the number of completed parts in the checkpoint (or read `next_split_part_index` from the checkpoint) and let `_existing_part_paths` reuse the first `k` valid contiguous parts instead of demanding the full planned count.

### [AB-4] Cancelling mid-generation persists wrong `voice_target_id` values (dropped `voice_assignment_mode`) — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py:739`

- **What:** Every other `_merge_existing_audio_blocks` call site passes the project's voice assignment mode; the cancellation handler for a speech block does not, so the default `"narrator_and_characters"` is silently used:

```python
        except operation_runtime_service.OperationCancelledError:
            latest_state = load_operation_state(resolved_project_root) or {}
            latest_blocks = _merge_existing_audio_blocks(
                generation_context["speech_blocks"],
                load_audio_blocks(resolved_project_root) or existing_blocks,
            )
```

  `_merge_existing_audio_blocks` rebuilds each entry through `_initialize_audio_blocks(speech_blocks, voice_assignment_mode)`, and `_voice_target_id_for_block` (line 2936) returns the narrator target only when the mode is `same_narrator` or the speaker kind is narrator. These rebuilt blocks are then persisted by `_persist_cancelled_state`, and `_compact_audio_block_payload` writes `voice_target_id` into the document.

- **Why it matters:** In a `same_narrator` project, cancelling a run rewrites every dialogue block's persisted `voice_target_id` from `narrator` to `character-<speaker_id>`. Those values are the matching key for invalidation: `narator_voice_ui_controller` invalidates with `(character_voices_service.TARGET_ID_NARRATOR,)` only, and `remove_audio_blocks_for_speech_blocks` / `workflow_impact_service._audio_block_matches` compare against the persisted id. So after a cancel, changing the narrator voice silently leaves those WAVs in place and the final audiobook mixes the old and the new narrator voice with no operator-visible signal. The wrong value survives approvals (`_persist_report_update` re-persists whatever `load_audio_blocks` returned) until the next full generation run.

- **Fix:** Pass the mode, exactly as the other five call sites do: `_merge_existing_audio_blocks(generation_context["speech_blocks"], load_audio_blocks(resolved_project_root) or existing_blocks, str(generation_context.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)))`.

### [AB-5] `update_audio_block_item` desyncs `_speech_blocks` indexes from QListWidget rows — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/pages/audio_blocks_page.py:328`

- **What:** When the incoming block is not already in the page model, the model list is appended to and re-sorted, but the list widget is not rebuilt; the freshly computed row is then used to index the *old* widget rows:

```python
        else:
            self._speech_blocks.append(dict(audio_block))
            self._speech_blocks = speech_blocks_service.sort_speech_blocks(self._speech_blocks)
            row = self._visible_block_row(normalized_id)
        if row >= 0:
            item = self._speech_block_list.item(row)
            if item is not None:
                item.setText(_format_audio_block_list_item(audio_block, self._current_language))
```

  After this, `len(self._speech_blocks) == count + 1` while the widget still has `count` items, and every row at or after the insertion point maps to the wrong block for `_show_selected_block`, `select_block_id` and `advance_to_next_block`.

- **Why it matters:** Reachability caveat: the only caller (`_refresh_audio_blocks_incremental_state`) passes the block the operator just acted on, which is by construction already in the model, so the `else` branch is not reachable on today's paths. The defect is real but latent — any future incremental push of a newly added block would relabel a neighbouring row and mis-target subsequent approve/regenerate actions.

- **Fix:** In the `else` branch, do a full refresh (rebuild the list widget from `self._speech_blocks`) instead of patching a single row.

### [AB-6] "Play" is enabled on pause / metadata-only rows but always reports missing audio — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/audio_blocks_ui_controller.py:249`

- **What:** `_merge_audio_block_state` publishes `"can_play": audio_blocks_service.audio_can_play(persisted_audio_block)` (`audio_blocks_state_service.py:416`), and `_persisted_audio_can_play` returns `True` for any generated metadata-only entry, so pause rows (and metadata-only ambience rows) are persisted with `audio_can_play=True`. The page enables the button on that flag (`audio_blocks_page.py:569`), but the handler resolves a file:

```python
    audio_block = _audio_block_by_id(window, speech_block_id)
    audio_path = _audio_path_for_block(window, audio_block)
    if audio_path is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("audio_blocks.error_missing_audio", current_language),
        )
        return
```

- **Why it matters:** Selecting any pause row and pressing Play always yields an error dialog, even though the same block is correctly previewed as timed silence in audiobook mode (`_play_audio_block_at_index` handles `_is_preview_pause_block` with a `QTimer`). It reads as a broken/missing artifact to the operator.

- **Fix:** Reuse the existing pause handling in the selected-playback path (schedule `_preview_pause_duration_ms` silence when `_is_preview_pause_block(audio_block)` is true), or exclude metadata-only entries from `can_play` in the state builder.

## Duplication

- **Six copies of the cancel-and-persist block** in `start_or_continue_generation` (lines 472-483, 542-553, 563-574, 613-624, 651-662, 737-754). They differ only in phase, block id and index — and the sixth copy is precisely the one that drifted and lost the `voice_assignment_mode` argument (AB-4). Collapsing them into one local helper (`_cancel_and_persist(phase, block_id, order_index, split_part_index=0)`) removes the class of defect, not just the instance.
- **`_audio_block_has_reusable_audio` (line 2518) and `_filesystem_audio_can_play` (line 3231)** are the same predicate written twice: not-generated → False, metadata-only → True, otherwise validate `_audio_artifact_path`. One of them should call the other.
- **The `input_fingerprint` recomputation after model load** is duplicated verbatim in `start_or_continue_generation` (lines 485-499) and `regenerate_audio_block` (lines 1146-1160), including the ambience keys.
- **The part-artifact layout is written twice**: `audio_blocks_artifact_service.audio_part_artifact_path` builds `parts/<stem>_partNNN.wav`, and `workflow_impact_service._iter_audio_block_artifact_paths` re-derives the identical layout as a hand-written f-string (with literal backslashes). The deletion path should call the artifact helper so the two can never diverge.

## Verified-clean notes

- **Block id → WAV mapping.** `audio_artifact_path` is a pure function of `speech_block_id`; ids are allocated as `NNNN-NNNNNN` by `speech_blocks_service._next_unused_speech_block_id`, so `audio_artifact_file_stem`'s `[^A-Za-z0-9_-]` strip cannot fold two distinct ids onto one filename. No path for one block to play or assemble another block's audio was found.
- **Re-split / chunk changes.** `reconcile_after_speech_blocks_resplit` deletes artifacts for the changed chunk *and* for blocks that no longer exist in Speech Blocks, so re-split id reuse does not inherit stale audio. Speech-block text edits go through `remove_audio_blocks_for_speech_blocks`, which deletes the WAV.
- **Deletion safety.** All artifact deletion resolves through `operation_runtime_service.try_resolve_project_relative_path`/`resolve_project_relative_path`, which rejects traversal, absolute and UNC-style paths; `_delete_audio_block_artifacts` derives its paths from the block id only. Nothing outside the project root can be unlinked.
- **Cancellation and partial WAVs.** `_validate_wav_bytes` runs before `write_bytes`, and the stitched output is only written after every part completes, so a cancel cannot leave a truncated file that later reads as valid. The one residue is `stitch_wav_parts` raising on incompatible part parameters after `wave.open(output_path, "wb")` has created the file — harmless in practice, because the block is never flagged `generated` on that path and every reuse check (`_audio_block_has_reusable_audio`, `_first_incomplete_generation_order_index`) tests `is_generated` first, so the stub is overwritten on the next run.
- **File handles.** Every `wave.open` in the artifact service is context-managed, and `_stop_audio_blocks_playback` clears the Qt player with `setSource(QUrl())` before any regenerate/reset operation starts, so Windows file locks do not block deletion of a WAV that was just auditioned.
- **Generation ordering and skip logic.** `_audio_generation_order_indices` returns indexes into the same list it was built from, and the loop skips unapproved, metadata-only and already-generated blocks by explicit `continue`; `_first_incomplete_generation_order_index` returns an order position (not a list index) and is consumed as such — no off-by-one between the two index spaces.
- **Approval paths.** `approve_audio_block`, `unapprove_audio_block` and `approve_all_audio_blocks` only toggle flags and re-persist; no WAV is deleted, matching the documented "approval changes preserve WAVs" rule.
- **Manifest stage.** `_persist_report_update` passing `current_stage="speech_blocks_ready"` cannot regress a finished project: `project_workspace_service.sync_manifest_operation_summary` only ever promotes the stage.
