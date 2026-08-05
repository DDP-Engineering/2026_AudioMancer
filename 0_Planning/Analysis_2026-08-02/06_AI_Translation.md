# Component Review — AI Translation

_Reviewed 2026-08-02. Files: `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py` (987), `.../services/ai_translation_state_service.py` (251), `.../ui/pages/ai_translation_page.py` (636), `.../ui/controllers/ai_translation_ui_controller.py` (488). Total ~2362 lines. Cross-checked `config.py`, `chunking_document_service.py`, `operation_runtime_service.py`, `operation_runner_controller.py`, `main_window.py` (call sites only)._

## Summary

The service layer is in good shape: chunk-ID alignment, resume-skips-non-empty, per-chunk checkpointing and cancellation semantics all match the knowledge doc, and the strict document validator is genuinely strict. The defects are concentrated in the review surface — the debounced auto-save round-trip resets the editor the operator is typing into, one action bypasses the flush and lets the UI thread write the document underneath a running worker, and a failed/cancelled single-chunk retranslation drops the whole translation out of "completed". Six findings: 4 Major, 2 Minor. No Critical.

## Implementation update - 2026-08-05

Commit `488973a` resolves TR-1, TR-2, TR-3, and TR-6 under
`REQ-FUNC-9a7e98c9`, `REQ-UX-7e8fb80a`, `REQ-UX-31620904`,
`REQ-UX-1373b3b5`, `REQ-UX-eb55be5b`, `REQ-UX-3dae2eb0`, and
`REQ-FUNC-ee95beb7`.

- **TR-1 resolved:** translation-state list rebuilds suppress the transient
  empty selection, restore the selected chunk by stable ID, and compare source
  and translated text independently before changing either Qt editor document.
  Same-content refreshes therefore preserve cursor/anchor, selection,
  undo/redo history, and both scroll positions, while genuinely different
  authoritative content still replaces stale text under the loading guard.
- **TR-2 resolved:** Start/Resume synchronously flushes the latest pending edit
  before emitting worker intent, and entering busy state defensively stops the
  debounce timer. An idempotent no-pending flush emits no duplicate update.
- **TR-3 resolved:** the main window captures the page's live profile ID before
  every AI Translation refresh and passes it through both state builders. An
  enabled selection survives; removed or disabled selections fall back to the
  configured enabled default and then the first enabled profile without adding
  a persisted setting.
- **TR-6 resolved:** Re-Translate Selected now requires a started, idle
  translation state in addition to the existing project/chunk/profile checks.
  Both the page emitter and controller reject an unavailable request before a
  prompt, worker, error, translation write, or manifest-stage change.

Focused AI Translation page, state, service, controller, and main-window
verification passed 39 tests. The configured full suite passed in 1497.4
seconds, and the task-scoped strict AEGIS check reported zero errors. TR-4 and
TR-5 remain open. The original evidence and pre-fix excerpts below are retained
as the 2026-08-02 review record and are superseded only for the four resolved
findings.

## Findings

| Finding | Original severity | Current status |
|---|---|---|
| TR-1 | Major | Resolved in `488973a` on 2026-08-05 |
| TR-2 | Major | Resolved in `488973a` on 2026-08-05 |
| TR-3 | Major | Resolved in `488973a` on 2026-08-05 |
| TR-4 | Major | Open |
| TR-5 | Minor | Open |
| TR-6 | Minor | Resolved in `488973a` on 2026-08-05 |

### [TR-1] Debounced save round-trip resets the translated-text editor while the operator is typing — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_translation_page.py:443`

- **What:** every persisted edit re-enters the page through `show_project_state` and unconditionally calls `setPlainText` on the editor the operator is typing in:

```python
        selected_chunk = self._display_chunks[row]
        self._current_chunk_id = str(selected_chunk.get("chunk_id", ""))
        self._source_text_edit.setPlainText(str(selected_chunk.get("source_text", "")))
        self._loading_translation_text = True
        self._translated_text_edit.setPlainText(str(selected_chunk.get("translated_text", "")))
        self._loading_translation_text = False
```

  The full loop is synchronous and always closes: `_edit_timer` (750 ms) -> `flush_pending_translation_edit` (`:508-515`) -> `translated_text_changed` -> `ai_translation_ui_controller.handle_translated_text_changed` (`:264-280`) -> `update_translated_text` -> `_sync_manifest_after_translation` -> `window.show_project_state(...)` (`:406-409`) -> `main_window._refresh_ai_translation_page_state` -> `set_translation_state` -> `self._chunk_list.clear()` + `setCurrentRow(row_to_select)` (`:276`, `:295`) -> `currentRowChanged` -> `_show_selected_chunk(row)` -> the `setPlainText` above. `_loading_translation_text` suppresses the `textChanged` re-entry but does nothing about the caret: `QPlainTextEdit.setPlainText` rebuilds the document, so the caret snaps to offset 0 and the undo stack is cleared.

  Two sibling pages already guard exactly this: `audio_blocks_page.py:281` and `speech_blocks_page.py:1045` both wrap the call in `if self._source_text_edit.toPlainText() != <text>:`. This page does not, and it is the only page whose operator types directly into the affected editor.

- **Why it matters:** operator edits a translated chunk, pauses ~0.75 s mid-sentence, keeps typing — the new characters land at the very beginning of the chunk. The garbled text is then auto-persisted by the next debounce tick. The source pane scroll position is lost on the same tick. This fires on every editing pause, i.e. on a completely normal run.

- **Fix:** guard both `setPlainText` calls in `_show_selected_chunk` with a content comparison, matching `audio_blocks_page.py:281`:
  ```python
  if self._translated_text_edit.toPlainText() != translated_text:
      self._loading_translation_text = True
      self._translated_text_edit.setPlainText(translated_text)
      self._loading_translation_text = False
  ```

### [TR-2] Start Translation does not flush the pending edit, letting the UI thread write `translated_text.json` under a running worker — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_translation_page.py:447-455`, `:300-308`

- **What:** every other action flushes the debounced edit before emitting — `_emit_retranslate_selected` (`:463`), `_emit_approve_selected` (`:475`), `_emit_approve_all` (`:519`), `_show_selected_chunk` (`:430`), `closeEvent` (`:524`). Start does not, and `set_busy` does not stop the timer either:

```python
    def _emit_start_translation(self) -> None:
        profile_id = self.current_profile_id()
        if profile_id is not None:
            self.start_translation_requested.emit(profile_id)
```
```python
    def set_busy(self, is_busy: bool) -> None:
        self._busy = is_busy
        self._apply_control_state()
```

  The progress dialog is non-modal-blocking (`operation_runner_controller.start_threaded_operation` uses `create_progress_dialog(...)` + `thread.start()`, never `exec()`), so the Qt event loop keeps spinning and `_edit_timer` fires *during* the run. On the resume path the controller skips the instructions prompt entirely (`ai_translation_ui_controller.py:93-99`), so nothing else drains the timer first.

- **Why it matters:** operator types into chunk A, clicks **Start/Resume** within 750 ms (a normal gesture — the run is what they were heading for). At t≈0.3 s the worker loads the document from disk and starts translating. At t≈0.75 s the UI thread's timer fires and `update_translated_text` load-modify-writes the same `translated_text.json`, also overwriting the worker's `status: running` with `_review_status(...)`. The worker's next per-chunk `write_translation_document` (`ai_translation_service.py:361`) then writes back its own in-memory copy, which never saw the edit — the operator's edit is silently gone. `_sync_manifest_after_translation` also runs mid-operation from that flush, re-saving the manifest and possibly invoking `reset_operation_data` for downstream kinds.

- **Fix:** call `self.flush_pending_translation_edit()` at the top of `_emit_start_translation` (and, for belt and braces, `self._edit_timer.stop()` when `set_busy(True)`), matching `_emit_retranslate_selected`.

### [TR-3] AI profile selection silently reverts to the default on every page refresh — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/ai_translation_state_service.py:82`

- **What:** `build_ai_translation_state` resolves the profile with no knowledge of what the operator selected:

```python
    profile_state = build_ai_translation_profile_state(settings_payload)
```

  `build_ai_translation_profile_state` with `selected_profile_id=None` falls through to `resolved_default` / `enabled_ids[0]` (`:59-64`). `main_window.py:430-435` then feeds that already-defaulted value back in as if it were the live selection:

```python
        self._ai_translation_page.set_ai_profiles(
            **ai_translation_state_service.build_ai_translation_profile_state(
                self._settings_payload,
                translation_state.get("selected_profile_id"),
            )
        )
```

  The page's real selection (`AiTranslationPage.current_profile_id()`) is never read, so the `selected_profile_id` parameter is decorative on this path and `set_translation_state` (`ai_translation_page.py:271-274`) forces the combo back to the default.

- **Why it matters:** with more than one enabled profile, the operator picks profile B, runs the translation, and the success handler refreshes the page — combo silently back to profile A. Every subsequent **Approve Selected** / **Approve All** / text edit refreshes again, so during review every **Re-Translate Selected** runs on the default profile unless the operator re-picks B immediately before each click.

- **Fix:** pass the page's current selection into the refresh, e.g. in `main_window._refresh_ai_translation_page_state` resolve `selected = self._ai_translation_page.current_profile_id()` first and hand it to `build_ai_translation_profile_state`, and thread the same value into `build_ai_translation_state` (add the optional parameter it already lacks) so `stage`/`profile` state agree.

### [TR-4] A failed or cancelled single-chunk retranslation stamps `failed`/`cancelled` on a fully approved document — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py:452-461`

- **What:**

```python
    except OperationCancelledError:
        document["status"] = TRANSLATION_STATUS_CANCELLED
        document["token_usage"] = token_usage
        write_translation_document(resolved_project_root, document)
        raise
    except Exception:
        document["status"] = TRANSLATION_STATUS_FAILED
        document["token_usage"] = token_usage
        write_translation_document(resolved_project_root, document)
        raise
```

  `cancelled` and `failed` are sticky in `build_translation_summary` (`:206-212`) — they override the derived state — so a document whose chunks are all non-empty and all approved stops reporting `completed`.

- **Why it matters:** translation is finished and fully approved. The operator clicks **Re-Translate Selected** on one chunk to try a better wording and hits **Cancel** (or the provider times out). Nothing about the chunk records changed, but `translation_is_completed()` (`:230-236`) now returns False, so `character_voices_state_service.py:497` and `audio_blocks_state_service.py:475` stop offering the translated language downstream. On the page there is no control left to fix it: Start is disabled (`has_untranslated_chunks` is False, `ai_translation_page.py:371-383`), Approve All is disabled (nothing unapproved, `:387-394`), Approve Selected is disabled (already approved, `:398-403`). The only ways back are a *successful* retranslation (which clears that chunk's approval, forcing a re-approval) or an obscure no-op text edit that happens to re-run `_review_status`.

- **Fix:** in `retranslate_chunk`, leave the document's review state alone — the chunk records were not touched. Persist only the accrued usage and re-derive the status, e.g. `document["status"] = _review_status(document["chunks"])` in both handlers instead of `CANCELLED` / `FAILED`. (Note `tests/test_ai_translation_service.py:211` currently pins `status == FAILED`; that assertion needs to move with the fix.)

### [TR-5] Identical `if`/`else` branches make operator-supplied instructions unreachable whenever a document exists — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py:312-315`

- **What:**

```python
        if str(document["status"]) in _RESUMABLE_STATUSES:
            instructions = str(document["additional_translation_instructions"])
        else:
            instructions = str(document["additional_translation_instructions"])
```

  Both arms are byte-identical, so the `additional_translation_instructions` argument is discarded on every path where a document already exists. The controller nonetheless prompts for it precisely in the non-resumable case (`ai_translation_ui_controller.py:92-101` — the prompt is skipped for `running/in_progress/cancelled/failed` and taken otherwise).

- **Why it matters:** the operator is shown the "extra translation instructions" dialog, types rules, and they are silently dropped. Reachability is narrow: the persisted status must be `review_pending`/`completed` while the page's effective status is `in_progress` (i.e. the canonical chunk set drifted from the document without `sync_translation_after_chunk_change` having run). It is a genuine copy-paste defect either way — the `else` arm can never do anything different from the `if`.

- **Fix:** make the branches actually differ — keep the stored instructions when resuming, and use the caller's value otherwise:
  ```python
  if str(document["status"]) in _RESUMABLE_STATUSES or additional_translation_instructions is None:
      instructions = str(document["additional_translation_instructions"])
  else:
      instructions = _normalized_additional_translation_instructions(additional_translation_instructions)
  ```

### [TR-6] Re-Translate Selected is enabled before any translation exists, and the resulting failure regresses the manifest stage — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_translation_page.py:395-397`

- **What:** the button ignores `has_started_translation` (which is computed on line `355` and then explicitly discarded on line `368`, `_ = has_started_translation`):

```python
        self._retranslate_button.setEnabled(
            self._project_active and not self._busy and selected_chunk is not None and selected_profile_id is not None
        )
```

  On a chunked project with no translation yet, a chunk is auto-selected (`:294-295`) so the button is live. Clicking it prompts for instructions, spins up a worker, and `retranslate_chunk` fails at `ai_translation_service.py:415-416` with `"Start AI translation before re-translating a chunk."`.

- **Why it matters:** beyond the pointless error dialog, the failure handler runs `_sync_manifest_from_disk` -> `load_translation_summary` (returns the `not_started` summary) -> `_sync_manifest_after_translation`, which writes `updated_manifest["current_stage"] = _translation_manifest_stage(report)` = `"translation_ready"` (`ai_translation_ui_controller.py:404`, `:231-233`). The project stage advances to "translation_ready" even though translation never started, purely from clicking a button that should have been disabled.

- **Fix:** add `and has_started_translation` to the Re-Translate enable condition (and drop the `_ = has_started_translation` discard on line `368`).

## Duplication

- **Target-language resolution is implemented twice, identically:** `ai_translation_ui_controller._manifest_target_language` (`:474-487`) and `ai_translation_state_service._persisted_target_language` (`:216-225`) both read `manifest["target_language"]`, strip it, validate against `dict(config.TRANSLATION_LANGUAGE_OPTIONS)`, and fall back to `config.DEFAULT_TRANSLATION_TARGET_LANGUAGE`. One shared helper would remove the risk of the controller and the page disagreeing about which language is "the" target.
- **Status derivation is implemented twice over different inputs:** `_review_status` (`ai_translation_service.py:655-666`) derives completed/review_pending/in_progress from the *document's* chunk list, while `build_translation_summary` (`:206-218`) derives it from the *canonical source* chunk list. They disagree whenever the two lists drift (which is exactly the state TR-5 needs). Deriving `_review_status` from the same canonical projection — or having it call into the summary logic — would collapse the two.
- `_translated_count` (`:711-713`) re-counts what `build_translation_summary` already computes as `translated_count`; minor, but it is a third place the "non-empty means translated" rule is spelled out.

## Verified-clean notes

- **Chunk-ID alignment is sound.** Canonical IDs match `^chunk-[0-9]{4,}$`, are unique, and `text_chunking_state_service` never renumbers them (only `sequence_index` is resequenced via `resequence_records`, and insert uses `_next_chunk_id` = max+1). `_synchronize_document_chunks` rebuilds the document list strictly from `_canonical_source_chunks`, so `zip(source_chunks, document["chunks"], strict=True)` at `:338` can never mismatch, and a translation cannot land on the wrong chunk.
- **Batching preserves order / model over- or under-returns.** There is no multi-chunk batching: exactly one chunk is translated per request path, and an oversized chunk is split locally (`_split_translation_source_text`) and rejoined in order. A malformed or empty `translated_text` raises rather than being stored (`:803-807`), and the accrued token usage is merged *before* that validation so it is not lost.
- **Resume does not overwrite operator work.** `if str(translated_chunk["translated_text"]).strip(): continue` (`:340`) skips every chunk that already has text, so a resumed run never re-translates an edited or approved chunk and never clears an `approved` flag. `_synchronize_document_chunks` clears only IDs in `invalidated_chunk_ids`.
- **Cancellation mid-chunk never checkpoints a partial chunk.** `raise_if_cancelled` runs per chunk (`:339`) and per segment (`:774`); the chunk record is only assigned after all segments return (`:358`). Token usage accrued inside the aborted chunk survives because `_translate_text_in_budgeted_segments` mutates the caller's usage dict in place (`:801-802`) rather than rebinding it.
- **Approval invariants hold.** `update_translated_text` preserves approval when the text is byte-identical (`:487-489`); `approve_chunk` rejects empty text (`:506-507`); the validator rejects `approved && !translated_text.strip()` (`:587-588`). The transient UI-only "unapproved" flicker in `_handle_translated_text_changed` (`:498-502`) self-heals on the refresh that immediately follows the flush.
- **No same-language pass-through exists, by design.** `tests/test_ai_translation_service.py:220 test_same_language_translation_uses_llm` pins it; downstream (`character_discovery_service._resolve_discovery_input_chunks`) falls back to the original chunks when translation is absent or unapproved, so skipping the stage entirely is the intended pass-through.
- **Reset scope is correct.** `reset_translation` passes `preserve_operation_kinds=downstream_operation_kinds("translation", include_current=False)`, so `reset_operation_data` clears only the `translation` artifacts (`translated_text.json` plus the legacy sidecars and AI logs) and leaves narrator/character work alone.
- **State/page contract matches.** All three return paths of `build_ai_translation_state` (`_empty_state`, the `TranslationDocumentError` branch, the normal branch) emit exactly the ten keys `set_translation_state(**...)` expects, so `**` expansion cannot `TypeError`.
- **Not reported:** `build_ai_translation_state:89` calls `chunking_document_service.load_chunks` outside the `try` that catches `TranslationDocumentError`, so an `IncompatibleChunkingDocumentError` would escape the page refresh. No other `*_state_service` catches it either, and `write_json_atomic` makes a truncated chunk document implausible — this is a shared pattern, not a translation-specific defect.
- **Not reported:** the target-language mismatch guards (`:261-262`, `:309-310`, `:417-418`) are effectively unreachable in normal use because `project_options_locked` freezes `manifest["target_language"]` once the project starts (`home_ui_controller.py:195-201`, `:230-234`).
