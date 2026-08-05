# Component Review — Text Chunking

_Reviewed 2026-08-02. Files: `services/deterministic_chunking_service.py` (445), `services/ai_chunking_service.py` (1058), `services/chunking_document_service.py` (398), `services/text_chunking_state_service.py` (694), `ui/pages/text_chunking_page.py` (642), `ui/controllers/text_chunking_ui_controller.py` (620). Total ~3.9k lines._

## Implementation update - 2026-08-03

**Resolved: CH-2 in commit `e829071` under `REQ-FUNC-18dd9ec2`.**
`_persist_manual_chunk_change` now loads the authoritative Chunking document
before `_write_chunk_artifact` or any downstream invalidation. It rejects
`running`, `cancelled`, and `failed` documents with `ValueError` telling the
operator to finish, resume, or reset the current Chunking run before editing
chunks. The rejection leaves the document checkpoint and metadata,
`project.json`, manifest summaries/current stage, and downstream artifacts
unchanged.

`test_manual_chunk_mutations_reject_resumable_documents_without_side_effects`
parameterizes every resumable status and every public manual mutation, snapshots
the relevant files as bytes, and verifies exact preservation after rejection.
Existing completed-document mutations and first manual insertion remain covered
and unchanged. UI control gating, CH-1, CH-3, and downstream algorithms were
outside this fix. The full delivery suite passed with 1,221 tests, 1 skipped,
and 1 deselected.

**Resolved: CH-1 and CH-3 in commit `d8a08bd`.** The work is covered by
`REQ-FUNC-bb809764`, `REQ-UX-9501c338`, `REQ-FUNC-56dfec40`, and
`REQ-FUNC-16c16214`. Every AI no-prefix window, including a single or final
window, now uses the one structural-fallback path. That path increments and
persists the one fallback count, emits the absolute paragraph range, and feeds
the terminal warning and manifest summary. The production page-state path now
selects lifecycle notes before its report summary: running documents show a
checkpoint-based in-progress note; failed and cancelled documents retain the
resume note, warnings, and AI token usage; completed and not-started behavior
remains unchanged.

Focused descriptor, state, authoritative-document, and localization coverage
passed (68 tests), including one-window, two-window, structural-fallback,
resume-count, and persisted running deterministic/AI-assisted documents.

## Summary

**Resolution update:** The three historical findings below (CH-1, CH-2, and
CH-3) are resolved. The original analysis remains as review evidence; it does
not describe the current implementation. No open Critical, Major, or Minor
finding remains for Text Chunking in this review inventory.

The component is in good shape on the parts that are easiest to get wrong: window/offset arithmetic, descriptor validation, checkpoint/resume bookkeeping and cancellation all check out, and chunk coverage of the source paragraphs is exact in both modes (no gaps, no overlaps, no duplication). Three real defects were found: two **Major** — an AI-chunking fallback on the last window that is applied completely silently (no warning, no fallback counter, no progress message), and manual chunk edit/insert/delete on an unfinished run that force-marks a truncated document as `completed` and destroys the resume checkpoint — plus one **Minor** unreachable branch in the page-note builder. No Critical (crash / hard corruption) defect was found.

## Findings

**Current status:** CH-1 is resolved by removing the duplicate final-window
branch and using the shared counted/disclosed fallback path. CH-2 is resolved
by rejecting manual mutations against resumable documents. CH-3 is resolved by
ordering authoritative lifecycle handling before report-derived completed
notes and using localized checkpoint wording instead of unavailable numeric
totals.

### [CH-1] AI fallback on the final window is silent — no warning, no counter, no message — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/ai_chunking_service.py:280-292`
- **What:** When the model returns no valid descriptor prefix, the code takes one of two branches. The non-final branch records the fallback; the final-window branch is a near-verbatim copy that drops the bookkeeping:

```python
            elif is_final_window:
                fallback_ranges = _deterministic_structural_fallback_ranges(
                    paragraph_records,
                    window_start_index,
                    len(paragraph_records) - 1,
                )
                _append_chunks_from_ranges(
                    committed_chunks,
                    paragraph_records,
                    fallback_ranges,
                    semantic_strategy,
                )
                next_paragraph = len(paragraph_records) + 1
            else:
                fallback_ranges = _deterministic_structural_fallback_ranges(
                    paragraph_records,
                    window_start_index,
                    window_end_index,
                )
                ...
                context_window_fallback_count += 1     # line 305
                next_paragraph = window_end_index + 2
                ...                                    # sets progress_message
```

  Because `is_final_window` is `window_end_index == len(paragraph_records) - 1` (line 210), the two branches compute *identical* ranges and an identical `next_paragraph` (`len - 1 == window_end_index`, `len + 1 == window_end_index + 2`). The only behavioural difference is that the `elif` branch never increments `context_window_fallback_count` and never sets `progress_message`, so the completion warning built at lines 361-370 (`"N text windows were saved as a fallback chunk…"`) is never emitted for the last window.
- **Why it matters:** For a book small enough to fit one window (or for any run whose last window fails), a total AI failure is reported to the operator as a clean success. Concretely: cleaned text with no headings, one budget window, model returns `{"chunks": []}` → the whole book is committed as **one** chunk, `context_window_fallback_count == 0`, `warnings` contains no fallback notice, the final progress message is "AI-assisted chunking completed." The operator has no signal that the AI contributed nothing. This is already visible in `tests/test_ai_chunking_descriptor_contract.py:339-371`, where *two* windows fall back but the test asserts `report["context_window_fallback_count"] == 1`.
- **Fix:** Delete the `elif is_final_window:` branch entirely; the `else:` branch already handles the final window correctly (same ranges, same cursor advance) and additionally counts and reports the fallback.

### [CH-2] Manual chunk edit/insert/delete on an unfinished run marks the truncated document `completed` — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_chunking_state_service.py:337-357`
- **What:** Every manual mutation funnels through `_write_chunk_artifact`, which unconditionally promotes whatever document it finds to a terminal state and throws away the resume checkpoint:

```python
    document = chunking_document_service.load_chunking_document(project_root)
    if document is None:
        ...
    else:
        document["status"] = "completed"
        document["manual_adjusted"] = True
        document["next_paragraph"] = None
        document["chunks"] = chunks
    chunking_document_service.write_chunking_document(project_root, document)
```

  Nothing upstream restricts this to finished runs. `build_text_chunking_state` publishes `chunking_document["chunks"]` for *any* status (line 81), and `TextChunkingPage._apply_button_state` enables Edit/Insert/Delete purely on selection and busy state (lines 359-366) — a `running`, `cancelled` or `failed` document keeps them enabled. `_build_manifest_after_selective_chunk_change` then writes `operations["chunking"]` from that document and sets `current_stage = "translation_ready"`.
- **Why it matters:** Operator cancels a deterministic run over a 5,000-paragraph book at paragraph 120 (page shows the resume note and 120 chunks), notices a typo in chunk-0007 and fixes it. The saved document now has `status="completed"`, `next_paragraph=None`, 120 chunks. The resume checkpoint is gone: pressing Deterministic Chunking again is treated as a destructive *rerun* (`handle_deterministic_chunking_requested:81-84`), which resets and re-chunks from scratch, discarding the manual edit. If the operator does not notice, the manifest reports chunking complete and the remaining 4,880 paragraphs are silently dropped from the whole downstream pipeline. The same applies to a crashed AI run.
- **Fix:** Reject manual mutations while the document is unfinished. Smallest change: at the top of `_write_chunk_artifact` (or in the three public entry points), raise `ValueError` when `document["status"] in chunking_document_service.RESUMABLE_STATUSES` with a message such as "Finish or reset the current chunking run before editing chunks." — the controller already shows `ValueError` text in a warning box. (Optionally also gate Edit/Insert/Delete in the page.)

### [CH-3] The in-progress / resume note branches are unreachable — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_chunking_state_service.py:572-630`
- **What:** `build_text_chunking_notes` returns from the report branch before ever reaching the status branches:

```python
    if chunking_report_payload is not None:
        ...
        if chunking_status in {"failed", "cancelled"}:
            ...
            notes.append(
                ui_state_service.translate(resume_key, language).format(
                    progress_current=0,
                    progress_total=0,
                    ...
        return notes                     # line 570 — always taken when a document exists

    if chunking_status == "running":      # line 572 — dead
```

  Its only production caller, `build_text_chunking_state` (lines 74-80), derives `chunking_report_payload` and `chunking_operation_state` from the same document, so they are non-`None` together. Whenever a status exists, the function has already returned; when no document exists, `chunking_status` is `None` and all three status branches are skipped. Lines 572-630 are only exercised by tests that call the helper directly with `chunking_report_payload=None` (`tests/test_text_chunking_state_service.py:25-97`).
- **Why it matters:** Low blast radius — `text_chunking.note_resume` / `note_ai_resume` do not contain `{progress_current}`/`{progress_total}` placeholders, so the hardcoded zeros at lines 557-558 are swallowed by `str.format`. The visible effect is that a `running` document never shows the "chunking is in progress at X/Y" note (the app shows the summary + rerun note instead), and the dead code plus its passing tests give a false impression that the progress notes work.
- **Fix:** Either delete lines 572-630, or move the `running`/`failed`/`cancelled` handling above the `chunking_report_payload is not None` block and feed it real values. Note that `derive_operation_state` does not emit `progress_current`/`progress_total` at all, so any revived branch must read `metadata["next_paragraph"]` / chunk count instead.

## Duplication

**Resolution update:** The CH-1 fallback duplication has been removed. The
remaining duplication observations below are historical or separate cleanup
opportunities.

- **Fallback branches** (`ai_chunking_service.py:280-319`) — the `elif is_final_window` block is a copy of the `else` block that computes the same values; see CH-1. Collapsing them removes the defect.
- **Chapter-heading detection exists three times**: `deterministic_chunking_service._CHAPTER_PATTERNS` + `_detect_chapter_label` (lines 45-52, 430-442), `deterministic_chunking_service._chapter_count_from_chunks` / `_chapter_count_state_from_chunks` (lines 370-414), and an inline re-implementation in `chunking_document_service._chapter_count` (lines 56-58, 378-395) with its own copy of `_ROMAN_NUMERAL_PATTERN`. The three agree today (I checked the regexes and the consecutive-label dedupe are equivalent), but the warning count and the reported `detected_chapter_count` are computed by two independent code paths that can drift. Worth collapsing onto one helper.
- `_is_narratable_record` / `_starts_after_scene_separator` are defined identically in both chunking services (`deterministic_chunking_service.py:247-262`, `ai_chunking_service.py:909-922`); the AI module already reaches into `deterministic_chunking_service` for `_build_paragraph_records`, `_build_chunking_warnings` and `_chapter_count_from_chunks`, so these two could come from the same place.

## Verified-clean notes

- **Fallback reporting and lifecycle notes (resolved 2026-08-03).** Every
  no-prefix AI window contributes once to the persisted fallback count and its
  terminal/manifest warning. `build_text_chunking_state` now reaches truthful
  localized running, resume, completed, and not-started notes without a
  fabricated durable progress total.

- **Chunk coverage / no text loss or duplication.** `_validate_chunk_descriptor_prefix` forces `start_paragraph == expected_start_paragraph` starting at `window_start_index + 1` and re-seeds `expected` to `break_after_paragraph + 1`, so accepted ranges are contiguous, non-overlapping and monotonic by construction; the cursor then advances to `validated_ranges[-1]["end_index"] + 2` and the next window is rebuilt from there. Deterministic mode emits exactly one chunk per narratable paragraph in order. Scene separators are the only intentionally dropped text (contract §6).
- **Boundary indexing.** `paragraph_records[window_start:window_end + 1]`, `break_after_paragraph <= window_end_index + 1`, and `_narratable_subranges` bounds were checked for off-by-one; the range check at lines 755-758 happens *before* the `paragraph_records[start_paragraph - 1]` access, so an out-of-range descriptor cannot IndexError.
- **No stalled/infinite loops.** Every path through the AI `while` advances `next_paragraph` by at least one (`validated_ranges` non-empty ⇒ `end_index >= window_start_index`; both fallback paths jump past the window). `_build_windows` always consumes at least one paragraph per window because the token check is skipped while `current_paragraph_count == 0`.
- **Cancellation state.** Deterministic: `document["chunks"]`/`next_paragraph` are updated together at the end of every iteration and `raise_if_cancelled` fires at the top of the next one, so the persisted `cancelled` checkpoint is always resume-consistent (`next_paragraph` = first unprocessed paragraph, including for separator paragraphs that produce no chunk). AI: same, at window granularity. Both write terminal `cancelled`/`failed` state before re-raising.
- **Resume guards.** Both modes reject a mode mismatch and a changed `source_fingerprint`; deterministic additionally re-derives the expected chunk count from the processed prefix and refuses to resume on mismatch (lines 123-130).
- **Token usage.** `merge_token_usage` keeps `usage_available` if either side has it, and `_document_token_usage` re-derives `total_tokens = input + output`, so a response without usage data cannot zero the cumulative counters and the strict document balance check cannot fail.
- **Roles.** `cleanup_analysis_service.UNIT_ROLES` is exactly the set accepted by `_validate_chunk`, so a propagated Cleanup role cannot fail document validation. `_narratable_subranges` runs before `_build_chunk_from_range`, so `_effective_cleanup_role` can never emit `scene_separator` on a generated chunk.
- **Manual-edit metadata.** Delete transfers `starts_after_scene_separator` to the next survivor before removing the record and refuses to empty the list; insert sets the flag to `False`; text edit preserves it; `resequence_records` renumbers `sequence_index` without touching `chunk_id`; `_next_chunk_id` takes `max + 1` so it cannot collide with a surviving id.
- **Final-remainder closure** (`ai_chunking_service.py:263-274`): committing the untouched tail of the last window as one chunk when the model returned a fully valid but partial response is intentional (`test_valid_non_final_split_advances_from_the_last_break_and_closes_final_remainder`), not a defect — though it shares CH-1's lack of any operator-facing signal.
- **Roman-numeral grammar.** `(?=[MDCLXVI]+$)…` under `fullmatch` correctly rejects `""`, `IIII`, `IC` and any lowercase form while accepting valid uppercase numerals.
- **Page/controller plumbing.** `build_text_chunking_state` returns exactly the keyword set `set_processing_state` accepts (both branches); `progress_percent` guards `progress_total <= 0`; the deterministic 4-arg vs AI 5-arg progress callbacks both match the worker's `_emit_progress` signature.
