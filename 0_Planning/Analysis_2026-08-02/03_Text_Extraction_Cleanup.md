# Component Review — Text Extraction + Text Cleanup

_Reviewed 2026-08-02. Files: `text_extraction_service.py` (317), `text_extraction_adapters.py` (873), `text_cleanup_service.py` (1224), `cleanup_analysis_service.py` (807), `cleanup_ai_adjudication_service.py` (805), `cleanup_renderer_service.py` (532), `cleanup_text_analysis_service.py` (308), `cleanup_metadata_service.py` (220), `text_cleanup_state_service.py` (243), `ui/pages/text_cleanup_page.py` (243), `ui/controllers/text_cleanup_ui_controller.py` (262). Cross-checked against `source_ledger_service.py`, `operation_runtime_service.py`, `project_workspace_service.py`, `config.py`. Total ~5,800 lines._

## Implementation Update — 2026-08-03

Commit `0e8467f4a56e0fe725d1cc6dbab8a664e2e08ba6` resolves TC-2 under
`REQ-FUNC-2ab78634`. Automatic Cleanup finalization/rerendering and manual
cleaned-text save now call the same Cleanup-owned publication helper. That
helper uses `reset_operation_data(..., "chunking", include_current=True)` as
the sole downstream artifact owner, publishes `clean_text.txt` and
`cleanup.json` atomically, reloads `project.json`, applies
`project_workspace_service.build_manifest_after_operation_reset`, writes the
completed Cleanup summary into the same manifest value, and saves once at
`text_chunking_ready`.

The source document, completed Extraction state and artifacts, project options,
and new Cleanup artifact are preserved. Persistence errors propagate before a
service return or 100% progress report. Compatibility wrappers in
`text_cleanup_state_service` now delegate manifest-reset construction to
Project Lifecycle, avoiding a service dependency cycle and duplicated summary
reset logic.

Regression evidence covers both Cleanup publication paths from a manifest with
completed downstream summaries and real downstream artifacts. It asserts file
and summary reset, Cleanup completion, stage, preservation, coherent project
reopen, and injected manifest-write failures. The focused delivery set passed
121 tests with 1 skipped; the configured full suite completed successfully
across 1,210 selected tests with 1 skipped and 1 deselected.

| Finding | Status | Verification |
|---|---|---|
| TC-2 | Resolved | Automatic and manual publication remove all downstream artifacts, default their summaries, preserve upstream state and options, reopen without repair, and surface persistence failures. |

The original thirteen-finding inventory below remains review history. At that
point, the open Text Extraction + Cleanup findings were TC-1 and TC-3 through
TC-13: 0 Critical, 3 Major, and 9 Minor.

## Implementation Update — 2026-08-04

Commit `e7d67a52d4a82d3e658de69b4eed62f900c1d873` resolves TC-4 under `REQ-FUNC-c7960ee8` and TC-10 under `REQ-FUNC-379827ff`.

- **TC-4:** TXT and RTF decoding is now deterministic: BOMs and RTF `ansicpg` declarations take precedence, strict UTF-8 is tried next, and legacy candidates (`cp1250`, `cp1251`, and `cp1252`) are selected by decoded-text evidence instead of first successful decode. Latin-1 remains an explicit terminal fallback, and the source ledger records the encoding actually used.
- **TC-10:** Each EPUB spine member is decoded from its raw bytes using BOM, XML declaration, and HTML charset evidence. Unsupported declarations and declaration/decode mismatches fail strictly with the affected item or file named. Uniform encodings are recorded directly; heterogeneous books receive a deterministic `mixed(...)` ledger value.
- EPUB spine order, navigation filtering, progress reporting, cancellation checks, and visible-text extraction are preserved.
- Regression coverage uses genuine patched ZIP member bytes for UTF-16, Windows-1252, ISO-8859-1, mixed-encoding EPUBs, and invalid declarations, plus TXT/RTF legacy-code-page cases.
- Verification completed with 49 focused tests passing and the full suite at 1,256 passed, 1 skipped, and 1 deselected.

| Finding | Status | Evidence |
|---|---|---|
| TC-4 | Resolved | Exact-text and truthful-ledger tests for legacy TXT/RTF decoding, including Cyrillic and declared RTF code pages. |
| TC-10 | Resolved | Raw-member EPUB tests for uniform, mixed, and invalid declared encodings. |

After the source-import robustness update, the open Text Extraction + Cleanup
findings were TC-1, TC-3, TC-5 through TC-9, and TC-11 through TC-13:
0 Critical, 2 Major, and 8 Minor.

### Cleanup rerun and manual-edit safety — TC-3 and TC-12

Commit `362995d` resolves TC-3 under `REQ-FUNC-75d5b274` and
`REQ-REL-43c63d8c`, and TC-12 under `REQ-UX-6fb5efc7` and
`REQ-UX-e1bb52ba`.

- The controller now identifies a completed document as the sole destructive
  rerun case. After the existing localized confirmation, it calls
  `text_cleanup_state_service.reset_cleanup`, installs the returned manifest on
  the window, and only then launches `clean_text`. A declined confirmation and
  a reset failure leave the manifest and worker state untouched.
- Running, paused, finalizing, and failed Cleanup documents do not show the
  destructive rerun confirmation and do not reset their checkpoint. The
  service retains ownership of compatible resume and safe-rebuild decisions.
- During an active cleaned-text edit, the page preserves the draft and Cancel
  baseline across same-project refreshes and busy transitions. Extract,
  Cleanup, Reset Cleanup, and the optional AI-profile controls are disabled;
  Save and Cancel remain available when not busy.
- The page exposes modified-draft state to the Home controller. New Project
  and Open Project now require a localized No-by-default discard confirmation;
  accepting the warning does not clear a draft unless project activation later
  succeeds.

Focused controller, page, state, Home, and localization regressions passed 27
tests. The full suite passed 1,279 tests, with 1 skipped and 1 deselected.

### PDF reading order — TC-1

Commit `dafd8ed` resolves TC-1 under `REQ-FUNC-6dd114ad` and
`REQ-FUNC-6c977d3b`.

- Horizontal PDF line classification is now exclusive: a narrow centered line
  that satisfies both former column predicates is spanning instead of
  contributing to both column populations.
- Top, bottom, and ambiguous spanning classifications are also exclusive; a
  line satisfying both vertical thresholds is conservatively ambiguous and is
  emitted once.
- Clear two-column pages retain top-spanning, left-column, right-column, then
  bottom-spanning order and the existing reconstruction reason. Genuinely
  ambiguous layouts retain `uncertain_columns` and
  `multi_column_reading_order_uncertain`.
- Every single-column result assigns `column = 0` to every returned line,
  including pages with fewer than six lines and pages with unusable width, so a
  sparse page cannot create a false Cleanup `page_column_transition`.
- Focused helper tests prove identity-preserving permutations across all layout
  modes, centered and vertical-overlap lines emitted once, stable reason codes,
  and unchanged top-left ordering. A public PDF Extraction regression proves
  the centered source text appears once in `extracted_text.txt`.
- Verification passed 10 focused PDF cases, all 40 Extraction tests, Ruff,
  changed-file compilation, and the full suite at 1,264 passed, 1 skipped, and
  1 deselected.

| Finding | Status | Evidence |
|---|---|---|
| TC-1 | Resolved | Exclusive identity-preserving PDF ordering plus public extracted-text coverage for a centered line. |

After this update, the open Text Extraction + Cleanup findings are TC-5 through
TC-9 and TC-11 through TC-13: 0 Critical, 0 Major, and 7 Minor.

## Summary

The core of this component is in good shape: the ledger/renderer contract is genuinely airtight (interval partitioning, complete role and boundary coverage, strict AI answer validation, no reachable index or KeyError paths in the adjudication round-trip), and most of the "scary" areas I probed turned out correct by construction. The original review recorded **13 findings: 4 Major, 9 Minor**. With TC-1 through TC-4, TC-10, and TC-12 resolved, **7 remain open: 0 Major, 7 Minor**. No Critical: I found no path that corrupts `cleanup.json`/`source_ledger.json` beyond repair or crashes the UI thread on a normal run.

## Findings

### [TC-1] Two-column PDF ordering emits centered narrow lines twice — **Major, resolved 2026-08-04**

- **Resolution (2026-08-04):** `_order_pdf_lines` now partitions every input
  line exactly once. Lines satisfying both horizontal predicates become
  spanning, spanning lines satisfying both vertical thresholds become
  conservatively ambiguous, and all single-column returns assign column zero.
  Existing ordering modes, reconstruction and uncertainty reason codes, and
  stable top-left order are preserved.
- **Resolution evidence:** Focused tests compare input and output identities
  across `single_column`, `two_column`, and `uncertain_columns`, exercise both
  overlap classes and top/bottom positioning, and run a real PDF through public
  Extraction to confirm centered text is written once. Implemented in
  `dafd8ed` under `REQ-FUNC-6dd114ad` and `REQ-FUNC-6c977d3b`.

- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_extraction_adapters.py:794-826` (historical locations at review time)
- **What:** `left` and `right` are built with independent, non-exclusive predicates, so a line that fits entirely inside the ±4 % centre band satisfies both; `spanning` then excludes it, and `ordered` concatenates `left` and `right` unconditionally.

```python
    midpoint = page_width / 2.0
    margin = page_width * 0.04
    left = [line for line in lines if float(line["bbox"][2]) <= midpoint + margin]
    right = [line for line in lines if float(line["bbox"][0]) >= midpoint - margin]
    spanning = [line for line in lines if line not in left and line not in right]
    ...
    ordered = [
        *sorted(top_spanning, key=_pdf_line_sort_key),
        *sorted(left, key=_pdf_line_sort_key),
        *sorted(right, key=_pdf_line_sort_key),
        *sorted(bottom_spanning, key=_pdf_line_sort_key),
    ]
```

- **Why it matters:** On a US-Letter page (`page_width` 612) the band is 49 pt wide. A centered page number, a centered running footer, or a centered `* * *` ornament on a two-column page lands in both lists and is emitted as **two** `SourceEvent`s. The ledger stays valid (distinct unit ids, distinct offsets), so nothing rejects it — the duplicate simply appears in `extracted_text.txt` and then in `clean_text.txt`, once per affected page. A duplicated centered page number also inflates `left`/`right` counts, making `stable_two_column` *more* likely to trigger. The same shape exists for `top_spanning`/`bottom_spanning` overlap (a line satisfying both is likewise emitted twice while `ambiguous_spanning` stays empty).
- **Fix:** Make the classification exclusive — assign each line once, e.g. build `right` as `... if line not in left and float(line["bbox"][0]) >= midpoint - margin`, and derive `bottom_spanning` as `[line for line in spanning if line not in top_spanning and ...]`.

Related (same function, lower impact): the early return at line 790-791 leaves `line["column"]` as `None`, while the normal single-column return at 803-805 sets it to `0`. A page with fewer than six lines therefore reports a different column identity than its neighbours, and `_cross_page_prior` reads that as `page_column_transition` (`cleanup_analysis_service.py:542-548`). Set `line["column"] = 0` on the early return too.

### [TC-2] Cleanup deletes downstream artifacts without resetting their manifest summaries — **Major, resolved 2026-08-03**

- **Resolution (2026-08-03):** `_finalize_document` and
  `save_user_cleaned_text` now converge on `_publish_completed_cleanup`, which
  performs the centralized Chunking-and-downstream artifact reset, publishes
  the completed Cleanup files, reloads the manifest, resets downstream compact
  summaries through Project Lifecycle's shared builder, restores the completed
  Cleanup summary, and saves the one coherent manifest at
  `text_chunking_ready`.
- **Resolution evidence:**
  `test_automatic_cleanup_publication_invalidates_downstream_state_coherently`
  and `test_manual_cleanup_edit_invalidates_downstream_state_coherently` seed
  completed downstream summaries plus every current artifact class, verify all
  preservation and reset invariants, and reopen with `status="ok"`;
  `test_cleanup_publication_surfaces_manifest_persistence_failure` injects the
  final manifest-save failure into both paths. Implemented in `0e8467f` under
  `REQ-FUNC-2ab78634`.
- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_service.py:507` and `:670` (historical locations before `0e8467f`)
- **What:** Both `_finalize_document` and `save_user_cleaned_text` clear downstream **files** but only ever sync the `cleanup` summary back into `project.json`.

```python
    reset_operation_data(root, "chunking", include_current=True)
    write_text_atomic(root / config.CLEANED_TEXT_FILE_NAME, cleaned_text)
    ...
    project_workspace_service.sync_manifest_operation_summary(
        root, "cleanup", _manifest_summary(document),
        current_stage="text_chunking_ready", ...
    )
```

  `reset_operation_data(root, "chunking", include_current=True)` deletes `chunks_text.json`, `translated_text.json`, `characters.json`, `narrator_voice.json`, `characters_voice.json`, `speech_blocks.json`, `audio_blocks.json`, every generated `audio_blocks/*` file and the whole `audiobook/` folder. Nothing then resets `manifest["operations"]` for those kinds, and `sync_manifest_operation_summary` only ever *promotes* `current_stage` (`project_workspace_service.py:494-499,512-513`).
- **Why it matters:** Take a project that reached `speech_blocks_ready`. The operator fixes one typo via Edit → Save, or re-runs Cleanup. All downstream artifacts are deleted, but `project.json` still reports `operations.chunking/…/speech_blocks` as `completed` and `current_stage` stays `speech_blocks_ready`. On the next project open, `_build_project_manifest_healing_result` sees completed summaries with no artifacts and returns `status: "repair_required"` — the exact contradiction `sync_manifest_operation_summary`'s own docstring warns about ("Invalidating downstream work belongs to the explicit reset path, which clears artifacts and summaries together"). The Extraction handler does this correctly (`handle_extract_text_requested` calls `build_manifest_after_extraction_reset` and saves the manifest); the Cleanup handler has no equivalent.
- **Fix:** In `handle_cleanup_requested` (and in `handle_save_cleaned_text_requested`, or inside `save_user_cleaned_text`/`_finalize_document`), mirror the extraction path: after `reset_operation_data(..., "chunking", ...)`, apply `text_cleanup_state_service.build_manifest_after_operation_reset(manifest, "chunking")` and save it before syncing the cleanup summary. Note that `text_chunking_ui_controller.py:549-559` additionally passes `TEXT_REVISION_PRESERVED_OPERATION_KINDS` for the same "text was revised" case — decide once whether Cleanup should preserve character/narrator/voice work too, rather than having the two paths disagree.

### [TC-3] "Confirm Cleanup Rerun" is a silent no-op on a completed project — **Major, resolved 2026-08-04**

- **Resolution (2026-08-04):** The completed-document branch confirms, calls
  `text_cleanup_state_service.reset_cleanup`, replaces the window manifest with
  the returned reset manifest, and only then starts `clean_text`. Incomplete
  Cleanup statuses remain resumable without reset or confirmation; reset
  failures show the existing error warning and start no worker. Implemented in
  `362995d` under `REQ-FUNC-75d5b274` and `REQ-REL-43c63d8c`.
- **Resolution evidence:** Controller and state tests cover decline immutability,
  reset-before-start ordering, reset manifest handoff, downstream artifact and
  summary removal, a fresh analysis path instead of completed-result caching,
  resumable checkpoint retention, and reset failure. The focused set passed 27
  tests; the full suite passed 1,279 tests with 1 skipped and 1 deselected.

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/controllers/text_cleanup_ui_controller.py:68-90`, with `services/text_cleanup_service.py:155-176`
- **What:** The controller asks for confirmation but never resets anything; `clean_text` then short-circuits.

```python
    if existing is not None and not _confirm(
        window,
        ui_state_service.translate("dialog.confirm_cleanup_rerun_title", language),
        ui_state_service.translate("project.confirm_cleanup_rerun", language),
    ):
        return
    profile = _resolve_ai_profile(window._settings_payload, profile_id)
    start_operation(window, "cleanup", ...)
```

  and in the service:

```python
        if (
            document["status"] == "completed"
            and document["profile_fingerprint"] == profile_fingerprint
            and document["prompt_hash"] == prompt_hash
        ):
            ...
            _emit(progress_callback, 1, 1, 100, "Cleanup completed.")
            return document
```

- **Why it matters:** The dialog text is *"Continuing will delete the current cleanup data and every downstream result. Continue?"*. On a completed project with an unchanged AI profile, clicking Yes deletes nothing, re-analyses nothing, and returns the cached document with a 100 % progress flash. The operator believes a rerun happened. The only way to actually force one is Reset Cleanup, which the confirmation text does not mention. (The extraction equivalent at lines 40-44 *does* reset before starting, which is what makes the mismatch obvious.)
- **Fix:** Either call `text_cleanup_service.reset_cleanup_and_downstream(...)` after a Yes (matching the dialog and the extraction handler), or change the prompt to "Resume/verify Cleanup" and reserve the destructive wording for Reset.

### [TC-4] Text decoding has no Cyrillic codec, and the "cannot decode" error is unreachable — **Major, resolved 2026-08-04**

- **Resolution (2026-08-04):** Commit `e7d67a52d4a82d3e658de69b4eed62f900c1d873` replaces first-success legacy decoding with a deterministic standard-library selector. It honors BOM and RTF code-page declarations, supports `cp1251` alongside `cp1250` and `cp1252`, keeps Latin-1 as an explicit last resort, and records the chosen encoding truthfully.
- **Resolution evidence:** `test_extract_text_selects_supported_text_encoding_without_mojibake`, `test_extract_text_honors_rtf_code_page_declaration`, and `test_text_decoder_uses_explicit_latin1_terminal_fallback` cover exact decoded text and source-ledger behavior under `REQ-FUNC-c7960ee8`.

- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_extraction_adapters.py:39` and `:673-680`
- **What:**

```python
_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1250", "cp1252", "latin-1")
...
def _decode_bytes_with_fallback(source_bytes: bytes) -> tuple[str, str]:
    for encoding in _TEXT_ENCODINGS:
        try:
            return source_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("text", source_bytes, 0, 1, "Unable to decode text source.")
```

- **Why it matters:** Two things. (a) `latin-1` maps all 256 byte values, so it never raises — the `raise` on the last line is dead code and no input is ever reported as undecodable. (b) The knowledge doc (§7) and `config.CLEANUP_SUPPORTED_SOURCE_LANGUAGES` list Russian as a supported source language, but there is no `cp1251`/`koi8-r` in the chain. A cp1251-encoded `.txt` or `.rtf` decodes silently through `cp1250` (or `latin-1`) into Latin mojibake; `classify_text_script` then sees Latin characters, so the CJK/Hangul gate does not fire and Cleanup happily publishes a garbage book. There is no in-app recovery — the operator must re-encode the file externally.
- **Fix:** Add `"cp1251"` (and optionally `"koi8-r"`) to `_TEXT_ENCODINGS` ahead of `latin-1`, and drop the unreachable `raise` (or keep `latin-1` out of the loop and use it only as an explicit last resort so the error path is real).

### [TC-5] The "introduced alphanumeric fusion" guard can never fire — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/cleanup_renderer_service.py:342-366`
- **What:**

```python
        choice = str(decision["final"]["choice"])
        if choice not in {"dehyphenate", "join_preserving_hyphen"}:
            continue
        left_text = unit_text(canonical_text, units[str(left_id)])
        right_text = unit_text(canonical_text, units[str(right_id)])
        if choice == "dehyphenate":
            continue
        if left_text and right_text and left_text[-1].isalnum() and right_text[0].isalnum():
            count += 1
```

- **Why it matters:** After the two `continue`s the only surviving choice is `join_preserving_hyphen`, and `validate_operations` (line 331-337) already guarantees that its left unit ends in `-` or `­` — neither of which is `isalnum()`. So `_introduced_fusion_count` returns `0` for every possible input, `raise CleanupRenderError("Cleanup would introduce alphanumeric source adjacency.")` at line 153-156 is unreachable, and `quality_report["introduced_fusion_count"]` is a constant. Combined with the three hardcoded zeroes in `_quality_report` (`projection_violation_count`, `invalid_operation_count`, `unclassified_boundary_count`, lines 493-495), `_validate_blocking_quality_metrics` in `text_cleanup_service.py:612-625` can never fail — the whole "blocking quality gate" advertised in §6 of the knowledge doc is vacuous. I traced the render paths and no *actual* fusion is reachable today (every separator-`""` case is preceded by a hyphen-terminated unit), so this is a dead safety net rather than a live hole — but it will not catch a future regression either.
- **Fix:** Delete the dead `if choice == "dehyphenate": continue` and instead check the rendered adjacency the renderer actually produced (i.e. run the check over `parts` after `_render_boundary_group`), or remove the metric and its validation so the contract does not claim a guarantee that is not enforced.

### [TC-6] Resume progress baseline is counted in questions, not requests — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/cleanup_ai_adjudication_service.py:89-93` (with `:117-122`)
- **What:**

```python
    completed_requests = sum(
        int(item.get("primary_choice") is not None)
        + int(item.get("verifier_choice") is not None)
        for item in (resume_answers or {}).values()
    )
```

  `resume_answers` is keyed by **question_id** (built in `text_cleanup_service._resume_answers`, one entry per question), while `estimated_requests = len(batches) * 2` is counted in **requests**. A batch holds 4/8/16 questions.
- **Why it matters:** Resuming a paused run with, say, 200 answered questions sets `completed_requests = 200` against `estimated_requests` of maybe 60. `_emit_progress` then reports `min(200, 200)/max(200, 60)` → 100 %, which `_ai_progress_percent` clamps to the top of the AI band. The bar pegs at 88 % for the entire resumed run and only the message text changes. §3 of the knowledge doc explicitly promises that a resume "reconstructs its first displayed percentage from persisted completed and estimated AI request counts".
- **Fix:** Divide by the batch size, or better, count resumed *passes* while building `batches` (a batch contributes 1 when every one of its questions has a `primary_choice`, plus 1 when every disagreeing question has a `verifier_choice`).

### [TC-7] Two independent batch planners disagree, so the persisted batch plan does not describe the actual requests — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_service.py:1083-1096` vs `cleanup_ai_adjudication_service.py:648-661`
- **What:** `_batch_order` chunks the flat question list by size only:

```python
    return [
        [str(item["target_id"]) for item in questions[start : start + size]]
        for start in range(0, len(questions), size)
    ]
```

  while `_homogeneous_batches` groups by `question_type` **first** and then chunks:

```python
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in questions:
        grouped[str(item["question_type"])].append(item)
    return [ group[start : start + batch_size] for question_type in sorted(grouped) ... ]
```

- **Why it matters:** With 10 `line_boundary` + 3 `hyphenation` questions and size 4, the persisted plan is `[4,4,4,1]` while the real plan is `[3][4,4,2]` — different membership and, in general, a different count (`ceil(n/s)` vs `Σ ceil(n_t/s)`). The persisted `estimated_request_count` under-counts, `_next_batch_index` (`text_cleanup_service.py:1099-1111`) matches a real batch against the wrong persisted batch and can move backwards, and the resume banner ("Cleanup resumed from batch N/M") and `_manifest_summary["progress_current"]` are both derived from that index. Nothing crashes — `_next_batch_index` clamps with `min(index + 1, len(batch_order))` and `_validate_progress` only requires `next_batch_index <= len(batch_order)` — but every number shown to the operator during an AI run is approximate in a way the code does not admit.
- **Fix:** Have `text_cleanup_service` call the adjudication service's planner (expose `_homogeneous_batches`/`_batch_size_for_context` as the single source of truth) instead of maintaining a second, simplified copy.

### [TC-8] A whitespace-only edit stamps every paragraph with the union of all source unit ids — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_service.py:479-488`
- **What:**

```python
        source_ids = [
            str(unit_id)
            for item in document["paragraphs"]
            for unit_id in item.get("source_unit_ids", [])
        ]
        _realign_whitespace_roles(previous_records, runtime_records)
        for record in runtime_records:
            record["source_unit_ids"] = list(dict.fromkeys(source_ids))
            record["provenance_available"] = True
            record["reason_codes"] = ["user_whitespace_realign"]
```

  `source_ids` is flattened across **all** previous paragraphs, and then the same full list is assigned to **each** rebuilt paragraph.
- **Why it matters:** After one whitespace-only edit, every paragraph in `cleanup.json` claims provenance over every source unit in the book, and `provenance_available` is set to `True` while asserting it. Nothing reads `source_unit_ids` today (grep confirms the only writers are here and `cleanup_renderer_service._paragraph_record`), so blast radius is currently zero — but this is wrong persisted metadata that any future provenance feature would trust. `reason_codes` is also overwritten unconditionally, discarding the `deterministic_fallback` / `unknown_line_boundary` codes that `cleanup_metadata_service._runtime_record` turns into `warning_flags`.
- **Fix:** Either carry `source_unit_ids` across from the matched previous record inside `_realign_whitespace_roles` (which already does the unique-content match), or set `source_unit_ids: []` / `provenance_available: False` and stop claiming provenance the realignment did not establish.

### [TC-9] `clean_text` reads unvalidated checkpoint sub-fields, leaking `KeyError`/`TypeError` — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_service.py:136-215` (with `_can_reuse_analysis` at `:769-790`)
- **What:** `_read_checkpoint` returns the raw JSON dict with no validation. `_can_reuse_analysis` only checks the **top-level** key set and the three hashes; it never validates `progress` or the shape of `boundaries`. The resume branch then does:

```python
        _emit(
            progress_callback,
            int(document["progress"]["completed_request_count"]),
            max(1, int(document["progress"]["estimated_request_count"])),
            ...
            f"{int(document['progress']['next_batch_index']) + 1}/"
            f"{max(1, len(document['progress']['batch_order']))}."
        )
```

  and `questions_from_boundaries` dereferences `decision["adjudication"]["state"]` for every persisted boundary.
- **Why it matters:** §6 of the knowledge doc states that "persisted shape or value corruption does not leak `TypeError`, `KeyError`, or `AttributeError` to consumers" — every violation must surface as `CleanupDocumentError`. A `cleanup.json` with a truncated `progress` object or a boundary missing `adjudication` (hand edit, partial write from an older build) reaches the UI as a bare `KeyError: 'completed_request_count'` in a QMessageBox instead of the actionable "Reset Cleanup" message. `load_cleanup_document` does it correctly; the run path does not.
- **Fix:** Run the loaded checkpoint through `_validate_progress` (and a boundary-shape check) inside `_can_reuse_analysis`, returning `False` on any violation so the run falls through to a fresh analysis.

### [TC-10] EPUB XHTML is decoded as strict UTF-8 only — **Minor, resolved 2026-08-04**

- **Resolution (2026-08-04):** Commit `e7d67a52d4a82d3e658de69b4eed62f900c1d873` decodes each raw EPUB spine member using BOM and XML/HTML declaration evidence. Invalid or mismatched declarations identify the affected item, while the ledger records either the uniform encoding or a deterministic `mixed(...)` value.
- **Resolution evidence:** `test_extract_text_honors_uniform_epub_content_encoding`, `test_extract_text_preserves_mixed_encoding_epub_spine_order`, `test_extract_text_identifies_epub_item_with_invalid_declared_encoding`, and `test_extract_text_identifies_epub_item_when_declared_decoding_fails` cover the implementation under `REQ-FUNC-379827ff`.

- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_extraction_adapters.py:384`
- **What:**

```python
        parser.feed(item.get_content().decode("utf-8", errors="strict"))
```

  and the adapter unconditionally reports `encoding="utf-8"` at line 397.
- **Why it matters:** EPUB permits UTF-16 as well as UTF-8, and real-world EPUBs repackaged from HTML sometimes ship ISO-8859-1 content documents with a matching XML declaration. Any such spine item aborts the whole extraction with a raw `UnicodeDecodeError` surfaced verbatim in the failure QMessageBox (`text_cleanup_ui_controller.handle_operation_failure`) — with no indication which file or what to do. Every other adapter has a fallback chain.
- **Fix:** Route the bytes through `_decode_bytes_with_fallback` (which also returns the selected encoding for the ledger), or at minimum catch `UnicodeDecodeError` per item, skip it, and record a warning.

### [TC-11] The `hidden` attribute check never matches a bare boolean attribute — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/text_extraction_adapters.py:527-531`
- **What:**

```python
        attrs_map = {str(key).casefold(): str(value) for key, value in attrs if value is not None}
        if self._ignore_depth:
            self._ignore_depth += 1
            return
        if tag in {"script", "style", "nav"} or "hidden" in attrs_map or attrs_map.get("aria-hidden") == "true":
```

  `HTMLParser` reports a bare `hidden` attribute as `("hidden", None)`, and the comprehension filters exactly those out — so `"hidden" in attrs_map` is only ever true for `hidden=""` or `hidden="hidden"`.
- **Why it matters:** `<div hidden>` (the HTML5 spelling, common in EPUBs converted from HTML) is not skipped, so hidden footnote popovers, alternate covers and print-only blocks are extracted and narrated. Valid XHTML uses `hidden="hidden"` so it works there — this only bites HTML-flavoured EPUBs.
- **Fix:** Build `attrs_map` with `"" if value is None else str(value)` and keep the membership test.

  **Uncertain, same class:** `handle_starttag` increments `_ignore_depth` for *every* nested start tag while ignoring, and `handle_endtag` decrements on every end tag. In well-formed XHTML (`<br/>` → `handle_startendtag` → both callbacks) this balances. In an EPUB that uses HTML void syntax (`<br>`, `<img …>`) *inside* an ignored region, the depth never returns to zero and the **entire rest of that spine document is silently dropped**. I could not confirm a real EPUB that does this, so I am flagging rather than asserting it; tracking a tag stack instead of a counter would remove the class of bug.

### [TC-12] An in-progress operator edit is silently discarded by any page refresh — **Minor, resolved 2026-08-04**

- **Resolution (2026-08-04):** Active edits retain their exact buffer, Cancel
  baseline, writable state, and editing mode through ordinary refreshes and
  busy transitions. Workflow emitters and controls are gated while editing;
  New/Open project flows use localized No-by-default discard confirmation and
  clear the old edit state only after successful activation. Implemented in
  `362995d` under `REQ-UX-6fb5efc7` and `REQ-UX-e1bb52ba`.
- **Resolution evidence:** Qt page/controller/Home integration tests cover
  refresh preservation, disabled workflow actions, Cancel restoration, failed
  save retention, project-switch decline, picker cancellation, successful
  activation, and localization parity. The focused set passed 27 tests; the
  full suite passed 1,279 tests with 1 skipped and 1 deselected.

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/pages/text_cleanup_page.py:128-131` and `:233-242`
- **What:** `set_processing_state` unconditionally clears edit mode and overwrites the editor:

```python
        self._editing_cleaned_text = False
        self._saved_cleaned_text = cleaned_text or ""
        self._extracted_text_edit.setPlainText(extracted_text or "")
        self._cleaned_text_edit.setPlainText(cleaned_text or "")
        self._cleaned_text_edit.setReadOnly(True)
```

  while `_apply_button_state` leaves Extract / Cleanup / Reset Cleanup enabled during an edit:

```python
        self._extract_button.setEnabled(enabled and self._can_extract)
        self._cleanup_button.setEnabled(enabled and self._can_clean)
        self._reset_cleanup_button.setEnabled(enabled and self._can_reset_cleanup)
```

- **Why it matters:** Mid-edit, the operator clicks Cleanup (or Reset Cleanup, or switches project) → `MainWindow.show_project_state` → `set_processing_state` → the edited buffer is replaced by the on-disk text with no warning and no undo. For a long manual correction pass on a book-sized document that is real work lost. Cancel exists specifically to discard edits, which implies the other buttons should not do it implicitly.
- **Fix:** While `self._editing_cleaned_text` is true, disable Extract / Cleanup / Reset Cleanup (same pattern already used for Edit/Save/Cancel), or have `set_processing_state` keep the editor contents when an edit is in progress.

### [TC-13] `CLEANUP_SUPPORTED_SOURCE_LANGUAGES` is never used — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/config.py:471`
- **What:** The constant is referenced exactly twice in the repository — its definition, and `tests/test_cleanup_quality_contract.py:409`, which asserts its literal value. No production code reads it.
- **Why it matters:** §7 of `Text_Cleanup.md` states that "`config.CLEANUP_SUPPORTED_SOURCE_LANGUAGES` defines the supported source-content set". The only gate that actually exists is the script check in `text_cleanup_service.clean_text:124-131`, which rejects `cjk`/`hangul` and accepts everything else — including Greek, Hebrew, Arabic, Thai and Devanagari, none of which are in the list. `document_profile["language"]` is detected (`cleanup_analysis_service.py:167`) but never compared against the tuple. Either the doc or the code is wrong, and the test asserting the literal gives false confidence that the gate is enforced.
- **Fix:** Either drop the constant and correct the knowledge doc to describe the script-based gate, or compare `document_profile["language"]` against it and emit a warning (not a hard rejection — the operator can still review the result).

## Duplication

- **Paragraph segmentation, two copies.** `cleanup_renderer_service._paragraph_records` (lines 369-402) and `cleanup_metadata_service.build_paragraph_records_from_text` (lines 41-89) contain the same `find("\n\n")` scan with the same `\r\n` trimming and the same trailing-newline collapse, character for character. They already diverge in what they attach to each record (real spans/roles vs `user_edited` defaults), so a fix to the scanning half will land in one and not the other. Extract the offset scan into one helper and let the two callers supply the record builder.
- **Batch planning, two copies.** See [TC-7] — `text_cleanup_service._batch_order` and `cleanup_ai_adjudication_service._homogeneous_batches` are two implementations of the same policy that have already drifted apart.
- **`_page_index`, two copies.** Identical function bodies at `cleanup_renderer_service.py:523-528` and `cleanup_analysis_service.py:796-803`. Harmless today, but the renderer's version is used for the artifact-removal page check and the analyser's for page-transition detection, so a change to the locator schema has to be made twice.
- **AI log file name built by hand.** `text_cleanup_service.py:357-360` composes `f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}cleanup_{_timestamp_token()}.log"` instead of calling `config.ai_transaction_log_file_name("cleanup", token)`. The two currently produce the same string, which is exactly why a change to the helper would silently stop matching the glob `reset_operation_data` uses to delete the logs (`operation_runtime_service.py:613`).

## Verified-clean notes

Risky areas I specifically chased and found correct:

- **Renderer interleaving order.** `render_cleanup` merges units and boundaries into one list sorted only by `start`, which would be ambiguous on ties. `CanonicalDocumentBuilder._append_boundary` returns early on empty text, so no zero-length boundary exists and no tie is possible; the stable-sort hazard is unreachable.
- **`assert left is not None` in `_boundary_prior`.** Boundaries are only appended when `_last_unit_id is not None` (or as the terminal `document_end`), so `left_unit_id` is never `None` — the assert cannot fire, including under `python -O`.
- **AI answer round-trip.** `_validate_answers` enforces exact one-to-one coverage of the batch with allowed choices before returning, so `_checkpoint_request`'s `answer_by_id[question_id]` and `_apply_ai_result`'s `question_by_id[...]`/`boundary_by_id[...]` lookups cannot raise `KeyError`, and no index arithmetic is involved. Question ids are always minted by `_question_from_decision`, so `_normalized_questions`' `q-{index:06d}` fallback never actually fires and cannot desynchronise the maps.
- **Question-set stability across resume.** `analyze_cleanup` selects `state == "pending"`; `questions_from_boundaries` selects `state != "not_required"`. Both reduce to "prior confidence is not strong" on every path (`_classify_boundary:331`, `_reset_ai_adjudication:804-808`, `_apply_page_artifact_bridge_priors:664-669`), so `question_id` indices stay aligned between the fresh run, a paused resume and a profile-change reset.
- **`validate_operations`.** Genuinely covers unknown/duplicate targets, unsupported roles and choices, the 160-char / 3-line artifact cap, "not every unit on a page", terminal-boundary exclusivity of `document_end`, the hyphen precondition for both hyphen choices, and complete role/boundary coverage. I could not construct an accepted operation set that damages the source projection.
- **Whitespace realignment safety.** `_realign_whitespace_boundaries` skips decisions with `right_unit_id is None`, so it can never rewrite the terminal boundary into a non-`document_end` choice that the next `validate_operations` would reject; the `find(candidate, cursor)` scan is monotonic and the not-found path warns, records `user_whitespace_realign_incomplete` and still persists the edit, exactly as §7 specifies.
- **Dehyphenation trim in `_render_boundary_group`.** `parts[-1] = parts[-1][:-1]` only runs when `parts[-1]` actually ends in `-`/`­`, and the boundary-chain analysis shows the chain's first choice always belongs to a hyphen-terminated left unit, so no real character is ever trimmed and `spans[-1]["end"]` stays consistent with `output_length`.
- **File handles.** `_extract_pdf` uses `with fitz.open(...)`; `python-docx` and `odfpy` close their packages during load; EbookLib ≥ 0.18's `ZipFile` is released via `__del__` when the reader goes out of scope. No leaked handles that would keep the imported source locked on Windows.
- **`sentence_spans` termination.** Every non-emitting branch advances `index` to `cursor`, which is strictly greater than the entry `index` — no infinite loop on adjacent terminal runs.
- **Progress callback arity.** `_emit_status` (4 positional args) matches `emit_progress_update(..., include_token_usage=False)`; the 3-arg adapter callback matches `_record_progress`. No signature mismatch between extraction adapters and the operation runner.
- **Extraction metadata state machine.** `_persist_interrupted_metadata` re-validates before writing, `_validate_metadata` enforces `progress_current <= progress_total` and null statistics for non-completed runs, and `_validate_artifact_pair` refuses to call a run completed unless the ledger loads. Cancel and failure paths both leave a consistent, loadable `extraction_metadata.json`. (`_write_running_metadata` at lines 171-191 is dead code — never called — but harmless.)
