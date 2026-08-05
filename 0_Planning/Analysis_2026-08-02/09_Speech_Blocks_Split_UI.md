# Component Review — Speech Blocks (splitting, normalization, UI)
_Reviewed 2026-08-02. Files: `services/speech_blocks_normalization_service.py` (1596), `services/speech_blocks_text_split_service.py` (925), `services/speech_blocks_narrator_split_service.py` (274), `ui/pages/speech_blocks_page.py` (1560), `ui/controllers/speech_blocks_ui_controller.py` (1194). Total ~5550 lines._

## Summary

The component is in good shape structurally: the deterministic narrator splitter really is total (it verifies coverage at runtime and raises rather than persisting a lossy plan), the span/unit coverage validators are strict, no splitter can loop forever, and the page consistently resolves Qt rows through `_blocks_for_current_chunk()` rather than trusting raw row indices. Seven findings: one Critical (a 4-digit truncation in `chunk_order_from_id` that silently corrupts book order and block-id uniqueness once a project exceeds 9 999 chunks), two Major (dash-dialogue span building drops leading text and forces a whole-chunk narrator fallback; the narrator splitter's quote stack never closes German `„…“` quotations), and four Minor. All findings below were reproduced by running the real code.

## Findings

### [SBU-1] `chunk_order_from_id` truncates to 4 digits, corrupting book order and block ids past chunk 9999 — **Critical**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\speech_blocks_normalization_service.py:194-202` (and its use at `:182-191`)
- **What:**

```python
def chunk_order_from_id(chunk_id: str) -> int:
    digits = "".join(character for character in str(chunk_id) if character.isdigit())
    return int(digits[-4:] or "0")
```

  `digits[-4:]` throws away every digit above the fourth. Chunks are one paragraph each and are named `f"chunk-{sequence_index:04d}"` (`deterministic_chunking_service.py:303`, `ai_chunking_service.py:886`), which is *not* capped at four digits. Reproduced:

```
chunk-0001  -> 1
chunk-10001 -> 1
speech_block_id("chunk-10001", 1) -> "0001-000001"
speech_block_id("chunk-0001",  1) -> "0001-000001"
```

- **Why it matters:** this helper is the canonical book-order key. `speech_blocks_service.speech_block_book_sort_key()` calls it (`speech_blocks_service.py:90, 999`), and `sort_speech_blocks()` drives the Speech Blocks list, the Audio Blocks list and — critically — audio assembly ordering (`audio_assembly_service.py:219, 245, 448, 552`). For any book with more than 9 999 paragraphs (a long or dialogue-heavy novel; every line of dialogue is its own chunk), paragraph 10 001 sorts immediately after paragraph 1 instead of at the end. The assembled audiobook is silently produced in the wrong order, with no warning anywhere. Secondly, `speech_block_id()` mints colliding ids for those chunks; `_stable_speech_block_id` then resolves the collision by allocating chunk 10 001's blocks inside chunk 1's `0001-*` id namespace, so the persisted ids no longer identify their chunk.
- **Fix:** drop the truncation — `return int(digits or "0")` — and widen the id format in `speech_block_id` from `{chunk_number:04d}` to a width that cannot overflow (e.g. `:05d`, or keep `:04d` as a minimum width since `format` does not truncate). Existing four-digit ids are unaffected because `f"{1:04d}"` is still `0001`.

### [SBU-2] Dash-dialogue span building drops the text before the first dash marker — **Major**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\speech_blocks_text_split_service.py:713-727` (`_dash_dialogue_ranges`) and `:391-405` (`_dash_atomic_ranges`)
- **What:** a dash only counts as a turn marker when it is *followed by whitespace* (`_dash_marker_is_dialogue_boundary`, `:730-745`). A paragraph opening with `—Text` (no space) therefore has no marker at offset 0, and the special case that would pull the first range back to 0 only fires when everything before the marker is blank:

```python
        boundary_start = marker_offset
        while boundary_start > 0 and paragraph_text[boundary_start - 1].isspace():
            boundary_start -= 1
        if not boundary_starts and not paragraph_text[:marker_offset].strip():
            boundary_start = 0
        boundary_starts.append(boundary_start)
```

  `_dash_atomic_ranges` has the same walk-back loop and no special case at all. Reproduced end-to-end:

```
'—Buna. — Ce faci? — Bine.'
  spans: [(6, 17, ' — Ce faci?'), (17, 25, ' — Bine.')]     # offsets 0..6 missing
  parse_source_spans  -> "source_spans do not cover the source chunk contiguously."
  parse_atomic_units  -> "atomic_units do not cover the source chunk contiguously."

'—Buna ziua. — Ce faci?'                                     # spans OK, units still broken
  units: [(11, 22, ' — Ce faci?')]
  parse_atomic_units  -> "atomic_units do not cover the source chunk contiguously."
```

- **Why it matters:** `normalize_source_span_selection_chunk_blocks` calls `parse_source_spans` first and, on error, returns `source_span_selection_fallback(...)` — the entire chunk collapses into a single unapproved narrator block flagged `source_span_selection_invalid` / `atomic_unit_selection_invalid`. Mixed dash typography (`—Text` for the opening turn, `— Text` for replies) is common in Romanian, Spanish and French EPUBs, and the project explicitly targets those languages (`_ATTRIBUTION_VERBS`). Every affected paragraph loses all AI speaker attribution and has to be re-split by hand. No text is lost (the fallback uses the full chunk text), which is why this is Major and not Critical.
- **Fix:** in both functions, force the first segment to start at offset 0 unconditionally — the caller has already established the span/paragraph is dash-led — e.g. `boundary_starts[0] = 0` after the loop in `_dash_dialogue_ranges`, and `segment_start = 0 if index == 0 else segment_start` in `_dash_atomic_ranges`.

### [SBU-3] `open_quote_stack` never closes German `„…“` quotations, collapsing the chunk into one over-budget block — **Major**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\speech_blocks_narrator_split_service.py:35-44` and `:79-83`
- **What:** `“` (U+201C) appears as a *key* in the opener table, and the opener branch is tested before the closer branch, so `“` can only ever push:

```python
_OPENING_TO_CLOSING_QUOTE = {
    "“": "”",
    "„": "”",
    ...
}
...
        if character in _OPENING_TO_CLOSING_QUOTE:
            stack.append(_OPENING_TO_CLOSING_QUOTE[character])
            continue
        if stack and character == stack[-1]:
            stack.pop()
```

  German typography is `„Text.“` — the closer is `“`, and `„` is mapped to `”`, so neither character can ever pop. Reproduced:

```
'„Guten Tag.“ Er ging weiter. Die Sonne schien hell. …'
  open_quote_stack -> ['”', '”']        # never empties
  plan_narrator_blocks(text, 8) -> 1 block, warning_flags=['tts_budget_exceeded']

'„Buna ziua.” El a plecat. Soarele stralucea. …'   (Romanian „…”)
  open_quote_stack -> []
  plan_narrator_blocks(text, 8) -> 4 evenly sized blocks, no warnings
```

  The sibling module already has the correct table: `speech_blocks_text_split_service._DIALOGUE_QUOTE_PAIRS` maps `„` → `“`, and `_ATOMIC_DIALOGUE_QUOTE_CLOSERS` maps `„` → `("”", "“")`. The narrator splitter is the only place that gets it wrong.
- **Why it matters:** `_atomic_sentence_spans` merges forward for as long as `open_quote_stack(prefix)` is non-empty, so from the first `„` to the end of the chunk no boundary is ever offered. Every quoted German (also Hungarian, Czech, Polish `„…“`) paragraph becomes one block, always flagged `tts_budget_exceeded`, defeating the documented "evenly sized blocks" contract for `same_narrator`. The same collapse is triggered in any language by an unbalanced quote — e.g. an unmatched `"` (inch mark) or the standard novel convention of opening a quote on each paragraph of a multi-paragraph quotation but closing only the last.
- **Fix:** give `„` both plausible closers, as the split service already does, and test the closer branch before the opener branch so `“` can close a pending `„`. Minimal version: keep a `set` of acceptable closers per stack entry and pop when the character matches any of them.

### [SBU-4] TTS-budget splitting rewrites `source_text` with whitespace-normalized, re-joined text — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\speech_blocks_normalization_service.py:1344-1372` (`split_over_budget_ai_blocks`), `:1391-1417` and `:1446-1470`
- **What:** `split_paragraph_spans` / `split_sentence_spans` strip every part, and `pack_tts_split_parts` rejoins with a single space, so the parts no longer reproduce the input. They are then written straight back over the block's provenance field:

```python
        for text_part in split_text_parts:
            split_block = dict(ai_block)
            split_block["source_text"] = text_part
            split_block["text"] = normalize_block_text(text_part, content_kind)
```

  Reproduced with `safe_word_count=5` on `"First para line one.\n\nSecond para line two here.\n\nThird para is longer than the budget for sure."` — the four resulting `source_text` values rejoin to a different string (blank lines gone, run-together spacing). Additionally, when the model's audio text differs from the source, `split_basis_text = audio_text` (`:1346`) and the original source text is overwritten by model text for every part.
- **Why it matters:** the knowledge doc states that normalization and splits "preserve usable text". `source_text` is provenance only (nothing in Audio Blocks / Assembly consumes it), so the audiobook is unaffected — but the persisted document silently stops matching the chunk it claims to cover, which defeats any later re-alignment or diagnosis. Same class of loss in `normalize_direct_block_chunk_blocks:1026,1032` where whitespace-only gaps between aligned model spans are dropped rather than attached to a block.
- **Fix:** make `split_text_for_tts_budget` return spans sliced from the input (offset-based, like `ai_sentence_spans`, which already preserves trailing whitespace) instead of `.strip()`-ed copies, and keep `source_text` as the exact slice while only `text` is normalized.

### [SBU-5] Edit mode is enforced only on the block list; every other control silently discards the in-progress edit — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\pages\speech_blocks_page.py:897-907` (and `:826-828`)
- **What:** the block list is deliberately locked while editing, but the chunk list, the re-split button and the header buttons are not:

```python
        self._resplit_button.setEnabled(
            self._project_active
            and not self._busy
            and self._can_resplit_selected
            ...
        )
        self._chunk_list.setEnabled(self._project_active and not self._busy)
        ...
        self._speech_block_list.setEnabled(self._project_active and not self._busy and not self._editing)
```

  Selecting another chunk runs `_show_selected_chunk`, which starts with `self._editing = False` and clears the list; `apply_language` ends with `self._show_selected_block(current_row)`, which does the same and reloads the persisted text.
- **Why it matters:** the operator types a correction, clicks another chunk (or `Split Chunk`, `Approve All`, or changes the UI language), and the typed text is gone with no prompt and no message. The block list being disabled shows the intent was to block exactly this.
- **Fix:** add `and not self._editing` to the `_chunk_list`, `_resplit_button`, `_generate_button`, `_approve_all_button` and `_reset_generation_button` enablement expressions, matching the block list.

### [SBU-6] Pressing Edit permanently clears the block's warning flags before anything is changed — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\ui\controllers\speech_blocks_ui_controller.py:296-304`
- **What:**

```python
    source_text_position = _source_text_position(window)
    if selected_block.get("warning_flags"):
        speech_blocks_service.clear_speech_block_warning_flags(window._current_project_root, speech_block_id)
        ...
    window._speech_blocks_page.begin_editing_selected_block()
```

  `clear_speech_block_warning_flags` persists `warning_flags = []` immediately, before the operator has looked at or changed anything, and there is no cancel path — clicking another row just sets `_editing = False`.
- **Why it matters:** opening a block for inspection destroys the very markers (`needs_review`, `source_gap`, `weak_source_boundary`, `tts_budget_exceeded`, `unknown_speaker`) the operator uses to find the blocks that still need attention, and they can only be restored by regenerating the whole plan. Warning counts in the report and the `!` markers in the list disappear for blocks that were never actually reviewed.
- **Fix:** move the `clear_speech_block_warning_flags` call into `handle_save_block_requested`'s success path (where `update_speech_block` already resets `warning_flags`), so warnings are cleared when an edit is committed rather than when the editor is opened.

### [SBU-7] Dialogue quote-unwrapping omits the `„…”` / `„…“` / `‚…'` pairs the splitter recognizes — **Minor**

- **File:** `F:\2026_AudioMancer\04_Software\AudioMancer\src\audiomancer\services\speech_blocks_normalization_service.py:112-123`
- **What:**

```python
    for opening_quote, closing_quote in (('"', '"'), ("“", "”"), ("‘", "’"), ("«", "»")):
```

  `speech_blocks_text_split_service._DIALOGUE_QUOTE_PAIRS` recognizes `„`→`“`, `‚`→`‘`, `»`→`«`, `‹`→`›` and the CJK brackets as dialogue delimiters, but none of those pairs is stripped here.
- **Why it matters:** a Romanian/German/Polish dialogue block keeps its `„ … ”` glyphs in the spoken `text` while an English or French block of the same shape has them removed, so the TTS input is inconsistent between languages within the same feature. Cosmetic and operator-correctable, but it is a straightforward omission relative to the table that already exists two modules away.
- **Fix:** reuse (or mirror) `_DIALOGUE_QUOTE_PAIRS` in `normalize_block_text` instead of the hard-coded four-pair tuple.

## Duplication

- `speech_blocks_normalization_service.normalize_source_span_selection_chunk_blocks:371-394` and `:411-434` are the same nine statements twice (build `ai_blocks`, warning entries, `split_over_budget_ai_blocks`, narrator budget check, then the identical `build_speech_block_payload` loop), differing only in which validator produced the result. `normalized_blocks` is even declared twice in the same scope. Collapsing this into one tail after the atomic/span branch selection removes ~40 lines and the risk of the two copies drifting.
- `speech_blocks_text_split_service._dash_dialogue_ranges:697-727` and `_dash_atomic_ranges:375-405` are two near-copies of the same "find markers, walk back over whitespace, slice between markers" algorithm — and SBU-2 is precisely a bug that exists in both because the fix in one (`if not boundary_starts and not paragraph_text[:marker_offset].strip()`) was never copied to the other, and is itself incomplete. Worth collapsing into one helper returning boundary offsets that both callers slice.
- `_ATTRIBUTION_VERBS` (`speech_blocks_text_split_service.py:87-129`) contains `"sopti"` twice (lines 107 and 109 — the second was presumably meant to be another diacritic variant).

## Verified-clean notes

- **Deterministic narrator splitting is genuinely total.** `cleanup_text_analysis_service.sentence_spans` preserves the input character for character, and `_atomic_sentence_spans` → `_pack_spans` → `_absorb_orphan_tail` → `_build_block` only ever concatenate slices; `_verify_source_coverage` raises rather than persisting a lossy plan. Confirmed by running the splitter on Romanian, English and no-punctuation samples.
- **No splitter can loop forever or emit a zero-length part.** `_quote_dialogue_ranges` and `_atomic_quote_dialogue_ranges` always advance the cursor past the closer; `split_text_for_tts_budget` recursion is bounded by `boundary_index <= 2` and falls through to `hard_split_text_for_tts_budget`; `hard_split_text_by_characters` uses `max(1, safe_word_count * 6)` so a zero budget cannot produce an empty step; `split_text_for_tts_budget("   ", ...)` returns `([], False)` and the caller keeps the original block. An over-budget single sentence is emitted as its own flagged block instead of looping, matching the documented contract.
- **Coverage validation is correct for normal prose.** Spot-checked eight realistic samples (plain narration, `"…," she said.` dialogue, quote-then-attribution, spaced dash dialogue, in-word apostrophes, German curly quotes, a bare heading, a sentence with no terminal punctuation) — `parse_source_spans` and `parse_atomic_units` accepted all of them. Only the SBU-2 shape fails.
- **`resolve_speaker_entry` cannot `KeyError`.** `speech_blocks_service._speaker_catalog` always seeds the `narrator` entry before adding characters, so the three unguarded `speaker_catalog[NARRATOR_SPEAKER_ID]` lookups are safe on every production path.
- **Qt row-index vs block-id handling is sound.** The page never indexes `_speech_blocks` by list row: `_visible_block_row`, `_visible_insertion_row`, `_select_block_by_id` and `_show_selected_block` all go through `_blocks_for_current_chunk()`. `remove_speech_block_item` computes the visible row *before* mutating the model. Ids are stable across insert/delete (`_stable_speech_block_id` preserves an existing id whenever it is unique), so the controller's targeted `remove_audio_blocks_for_speech_blocks((speech_block_id,))` after a delete/save always hits the right Audio Block.
- **No re-entrancy hazard while the model is rebuilt.** `set_speech_blocks_state` blocks `_chunk_list` signals around `clear()`/`setCurrentRow()` and drives `_show_selected_chunk` explicitly; `_populate_selectors` blocks both combo boxes around `clear()`. `_apply_control_state` short-circuits (`can_edit_selected and ... selected_block.get(...)`) so it cannot dereference `None`.
- **Deferred widget access is guarded.** Every `QTimer.singleShot` restore path re-checks `shiboken6.isValid(self)` / `isValid(scroll_bar)` and a monotonic `_source_text_restore_generation` token, and the temporary `rangeChanged`/`valueChanged` connections are disconnected under `suppress(RuntimeError, TypeError)`, so a page teardown or project close during a restore cannot raise.
