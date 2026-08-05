# Component Review — Speech Blocks (core service + state)
_Reviewed 2026-08-02. Files: `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py` (3683), `speech_blocks_state_service.py` (493), `speech_blocks_report_state_service.py` (227). Total ~4400 lines. Cross-checked against `.agentic/knowledge/Speech_Blocks.md`, `0_Planning/Speech_Blocks_Metadata_Simplification.md`, `config.py`, `operation_runtime_service.py`, `persistence_service.py`, `speech_blocks_normalization_service.py` (constants only)._

## Summary

The single-document consolidation is structurally sound: the write path is genuinely atomic, strict validation is applied on write, a corrupt/legacy document reads as `None`, and reset covers the legacy sidecars. The defects are concentrated in one place — the *derived* counters that replaced the previously persisted ones. Because `processed_chunk_count` is now recomputed as "number of distinct chunk ids that own blocks" and then used as a *chunk index*, the resume path mis-positions itself whenever a chunk in the middle of the book has no blocks — an operator action the knowledge doc explicitly allows. Findings: 1 Critical, 2 Major, 4 Minor.

## Findings

### [SB-1] Resume uses a block *count* as a chunk *index*, duplicating one chunk and skipping another — **Critical**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:328`, `:359`, `:3533-3543`, `:748`, `:871-872`

- **What:** Both read projections derive the processed-chunk figure from the block list:

```python
# _project_speech_blocks_report / _project_operation_state
processed_chunk_count = len({str(block.get("chunk_id", "")).strip() for block in blocks} - {""})
total_chunk_count = max(int(source_chunk_count), processed_chunk_count)
```

and the resume restore then consumes that figure as the *index of the next source chunk*:

```python
def _restore_next_speech_blocks_chunk_index(...):
    if str(existing_state.get("status", "")).strip() in {"running", "failed"}:
        raw_checkpoint_index = resume_checkpoint.get("next_chunk_index")
        if raw_checkpoint_index not in (None, ""):
            return max(0, min(int(raw_checkpoint_index), total_chunk_count))
    if isinstance(existing_report, dict):
        raw_report_count = existing_report.get("processed_chunk_count")
        if raw_report_count not in (None, ""):
            return max(0, min(int(raw_report_count), total_chunk_count))
```

  That equivalence (count == index) only holds if the blocks cover a contiguous prefix of the source chunks. The generation loop then appends to whatever was loaded:

```python
    all_blocks.extend(chunk_blocks)
    all_blocks = _renumber_speech_blocks(source_chunks, all_blocks)
```

- **Why it matters:** Knowledge doc §6: *"deletion can remove the final row for a chunk without removing that source chunk"*. Take a 10-chunk project, generated and persisted (`status: review_pending`). The operator deletes the last remaining row of chunk 3. `_persist_report_update` recomputes `processed_chunk_count = 9`, `total = 10`, stage `in_progress`, status `review_pending`. Source text is untouched, so the fingerprint, language and instruction fingerprint all still match and `_restore_resume_state` accepts the resume. `_restore_next_speech_blocks_chunk_index` returns **9**, so the loop runs `range(9, 10)` and regenerates **chunk 10**, whose blocks are already in `existing_blocks`. The document is then written with chunk 10's text duplicated (old approved rows plus new unapproved rows, ids re-allocated by `_renumber_speech_blocks`), while chunk 3 stays empty. The audiobook plan now contains a repeated passage and a missing one. The same happens for any non-final chunk left without blocks. (When the emptied chunk happens to be the *last* one, the arithmetic accidentally works — which is why `test_start_or_continue_generation_resumes_after_partial_review_approval` passes.)

- **Fix:** Resolve the resume position from chunk identity instead of a count: pass the ordered `source_chunks` into `_restore_next_speech_blocks_chunk_index` and, on the non-`running`/`failed` path, return the index of the first source chunk that has no persisted block (`next(i for i, c in enumerate(source_chunks) if c["chunk_id"] not in covered_chunk_ids)`, or `len(source_chunks)` when all are covered). As a belt-and-braces guard, drop existing blocks whose chunk index is `>= start_chunk_index` before entering the loop, so a re-run can never append onto an already-generated chunk.

### [SB-2] Multi-segment chunks are persisted (and resumed) with interleaved block order — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:775`, `:2004-2058`, `:3260-3266`

- **What:** Each AI segment of a chunk is normalized with chunk-local sequence indices that restart at 1 (`build_speech_block_payload(chunk_id, local_sequence_index, ...)` inside `_normalize_chunk_blocks`), and `combined_blocks` simply concatenates them:

```python
        combined_blocks.extend(segment_blocks)
        combined_warnings.extend(segment_warnings)
        if segment_progress_callback is not None:
            segment_progress_callback(list(combined_blocks), ...)
```

  The intermediate persist then re-sorts by that index:

```python
    persisted_blocks = _renumber_speech_blocks(source_chunks, [*base_blocks, *segment_blocks])
```
```python
    ordered_blocks = sorted(
        speech_blocks,
        key=lambda block: (
            chunk_order.get(str(block.get("chunk_id", "")).strip(), 10**9),
            int(block.get("sequence_index", 0)),
        ),
    )
```

  Python's sort is stable, so segment 1's blocks (1,2,3…) and segment 2's blocks (1,2,3…) end up as `s1b1, s2b1, s1b2, s2b2, …`. The end-of-chunk return path is correct (`_renumber_single_chunk_blocks` renumbers by list order), so a run that finishes the chunk repairs itself — but every checkpoint written *during* the chunk is scrambled.

- **Why it matters:** Two concrete failures for any chunk large enough to need ≥2 request segments (scene-strategy chunks easily exceed the `_SPEECH_BLOCKS_DIRECT_SOURCE_TOKEN_CAP = 2000` token cap). (a) If the run is cancelled or crashes mid-chunk, the persisted plan the operator sees has that chunk's sentences out of order. (b) On resume, `existing_blocks` contains those partial rows with sequence 1..k while the freshly generated remainder comes back renumbered 1..m from `_renumber_single_chunk_blocks`, so `all_blocks.extend(chunk_blocks)` + `_renumber_speech_blocks` interleaves old and new — the chunk reads "First. Third. Second. Fourth.". The existing regression test only covers k=1, m=1, where interleaving is invisible.

- **Fix:** Make the segment blocks continue the chunk's numbering instead of restarting: in `_generate_budgeted_chunk_blocks`, apply `_renumber_single_chunk_blocks(chunk_id, combined_blocks)` before handing the list to `segment_progress_callback`, and in `_persist_segment_progress` offset the new blocks by the number of rows already persisted for `current_chunk_id` (or drop that chunk's persisted rows and regenerate it whole on resume).

### [SB-3] A `same_narrator` document has its `response_contract` rewritten to `direct_blocks` by any operator edit — **Major**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:1854-1859`, used at `:3186`

- **What:** The restore helper's accept-set is missing the deterministic contract:

```python
    if response_contract in {
        _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT,
        _SPEECH_BLOCKS_NARRATOR_BOUNDARY_CONTRACT,
    }:
        return response_contract
    return _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT
```

  `_SPEECH_BLOCKS_DETERMINISTIC_NARRATOR_CONTRACT` ("deterministic_narrator_blocks") is not listed, so it is silently downgraded. The return value is written straight back into the authoritative document via `_persist_report_update` → `_build_operation_state_with_prompt_rules(speech_blocks_response_contract=...)` → `metadata["speech_blocks_response_contract"]` → `_compose_speech_blocks_document` → `document["response_contract"]`.

- **Why it matters:** In a `same_narrator` project the generated document correctly records `deterministic_narrator_blocks`. The first insert, delete, edit, approve-all, character rename, or character-deletion fallback flips the persisted contract to `direct_blocks` — a value that never described this document. This is exactly the marker the knowledge doc relies on (§6: *"A response contract incompatible with deterministic same-narrator segmentation is not resumable; generation restarts to avoid mixing two segmentations in one document"*), and `_is_resumable_speech_blocks_response_contract` / `_restore_next_speech_blocks_segment_index` both branch on it. After the rewrite, a deterministically segmented document claims to be a model-segmented one, and the segment-cursor path (`checkpoint_contract != _SPEECH_BLOCKS_DIRECT_BLOCK_CONTRACT → return 0`) no longer short-circuits for it.

- **Fix:** Add `_SPEECH_BLOCKS_DETERMINISTIC_NARRATOR_CONTRACT` to the accept-set in `_restore_persisted_speech_blocks_response_contract` (the same set `_is_resumable_speech_blocks_response_contract` already uses).

### [SB-4] `chunk_order_from_id` truncates to 4 digits, colliding past 9999 chunks — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_normalization_service.py:194-202` (consumed at `speech_blocks_service.py:999`, `:3342`)

- **What:**

```python
def chunk_order_from_id(chunk_id: str) -> int:
    digits = "".join(character for character in str(chunk_id) if character.isdigit())
    return int(digits[-4:] or "0")
```

  Chunk ids are `f"chunk-{sequence_index:04d}"` (`deterministic_chunking_service.py:303`, `ai_chunking_service.py:886`) and `_CHUNK_ID_PATTERN = r"^chunk-[0-9]{4,}$"` explicitly allows more than four digits.

- **Why it matters:** With ≥10000 chunks, `chunk-10001` and `chunk-0001` both yield order `1`, and `chunk-10000` yields `0`. That value is both the block-id prefix (`speech_block_id` → `f"{chunk_number:04d}-…"`) and the primary key of `speech_block_book_sort_key`, so `load_speech_blocks` would order chunk 10000's blocks before the whole book, and `_next_unused_speech_block_id` would allocate two chunks out of one id range. Paragraph-level chunking of a very long book can cross 10000.

- **Fix:** Drop the `[-4:]` truncation (`int(digits or "0")`) and widen the id format to the full chunk number; note that this changes existing ids, so it belongs with a document-version bump or a project re-run.

### [SB-5] Speech Block ids are recycled after deletion, contrary to the helper's own contract — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:3334-3353`, `:1174`

- **What:**

```python
def _next_unused_speech_block_id(chunk_id: str, used_ids: set[str]) -> str:
    """@brief Allocate the next chunk-local Speech Block id without reusing historical ids."""
    ...
    for speech_block_id in used_ids:
        match = suffix_pattern.match(speech_block_id)
        if match is not None:
            next_index = max(next_index, int(match.group(1)) + 1)
```

  `used_ids` is only `_used_speech_block_ids(<currently persisted blocks>)`; deleted ids are not tracked anywhere. With chunk rows `0001-000001..0001-000003`, deleting `0001-000003` and then inserting a new row re-issues `0001-000003`.

- **Why it matters:** The id is the join key to Audio Blocks (`audio_blocks_service._merge_existing_audio_blocks` matches by `speech_block_id`, and `_audio_block_has_reusable_audio` will adopt an existing WAV for a mismatched fingerprint). Today the damage is contained because `speech_blocks_ui_controller._reset_audio_block_after_speech_block_change` deletes the audio row and its artifact right after `delete_speech_block`, so nothing is left to inherit — but the service-level guarantee the docstring states is not met, and any future caller of `delete_speech_block` that skips the controller cleanup gets a new block wearing a dead block's audio.

- **Fix:** Either make the promise true (seed the allocator from a persisted per-chunk high-water mark) or correct the docstring to say ids are unique among *current* blocks only, so callers know the artifact cleanup is load-bearing.

### [SB-6] Scene-ambience insertion invalidates the `after_speech_block_id` it just matched on — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:2542-2557`

- **What:** `_insert_scene_ambience_blocks` matches scene-change rows against the *pre-insert* ids and then renumbers everything:

```python
        matching_changes = [
            block for block in pending_scene_changes
            if str(block.get("after_speech_block_id", "")).strip() == speech_block_id
        ]
    ...
    return _renumber_single_chunk_blocks(chunk_id, ordered_blocks)
```

  An opener ambience row is first in `ordered_blocks`, so it takes `CCCC-000001` and every narration/dialogue row shifts by one, while the persisted `after_speech_block_id` values still point at the old numbering.

- **Why it matters:** The persisted field now names a different block than the one it was computed from. It is not used for placement (ordering is by `sequence_index`), only for Scene Ambience grouping and labelling in `audio_assembly_service._scene_mix_group_key/_scene_mix_label`, so the visible effect is a wrong label such as "chunk-0001 scene mix after 0001-000002". Grouping stays self-consistent.

- **Fix:** Re-map `after_speech_block_id` after `_renumber_single_chunk_blocks` using the old-id → new-id mapping produced by the renumbering, or clear the field once the row's position has been materialized.

### [SB-7] Every read projection re-resolves the whole source corpus, several times per operator click — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:305-317`, `:415-432`, `:2947-2948`, `:3123-3125`, `:3619`

- **What:** `load_operation_state` and `load_speech_blocks_report` each call `_projection_source_chunk_count`, which does a full upstream re-resolution:

```python
    try:
        manifest = project_workspace_service.load_manifest(Path(project_root))
        source_resolution = resolve_source_chunks(Path(project_root), manifest)
    except (FileNotFoundError, OSError, ValueError, KeyError):
        return processed
```

  `resolve_source_chunks` parses the whole chunking document and, when a translation exists, the whole `translated_text.json` as well. `_persist_compact_review_update` calls it 3× per approval (report + state + `_resolve_log_path`'s own `load_operation_state`); `_persist_report_update` reaches ~6× (it additionally calls `_load_or_resolve_source_context`, which loads report + state + resolves again).

- **Why it matters:** Approve/unapprove is the most repeated operator action on this page and runs synchronously on the UI thread (`handle_approve_block_requested`). On a large book this turns a click into several full-corpus JSON parses. The pre-consolidation code read a persisted `total_chunk_count` instead, so this is a regression introduced by the projection design, not an inherent cost.

- **Fix:** Resolve the source chunk count once per public entry point and pass it down (`_persist_report_update` / `_persist_compact_review_update` already have `source_chunks` or can obtain them once), instead of letting every projection helper re-resolve.

## Duplication

- `processed_chunk_count` is computed in three places with two different rules: `_project_speech_blocks_report:328` and `_project_operation_state:359` strip the empty id (`- {""}`), while `speech_blocks_report_state_service.build_operation_state:173` does not — a block with no `chunk_id` counts as a chunk there. Since the document is now the single source, this should be one helper.
- `_persist_report_update:3112-3201` and `_persist_compact_review_update:2936-3002` are ~80% the same sequence (load report, load state, restore language/kind/profile/usage/budget/instructions/ambience, rebuild report, build state, compose, write, sync manifest); they differ only in whether blocks are renumbered and how the status is mapped.
- `_restore_persisted_additional_speech_block_instructions`, `_restore_persisted_scene_ambience_settings`, `_restore_persisted_budget_metadata` and `_restore_persisted_speech_blocks_response_contract` all reconcile "report vs. operation state" for fields that now come from the *same* document — the report/state disagreement they defend against can no longer exist.
- `_compose_speech_blocks_document` reassembles the document out of a report and an operation state that were themselves projected from a document; the round trip is what lets SB-3 corrupt a field in passing.

## Verified-clean notes

- **Write atomicity.** `write_speech_blocks_document` → `write_operation_json_artifact` → `write_json_atomic` → `write_text_atomic` uses `mkstemp` in the target directory, `flush` + `fsync`, then `os.replace`, with temp cleanup on `OSError`. A failed or interrupted write cannot leave a truncated `speech_blocks.json`; the previous document survives.
- **Strict-on-write / lenient-on-read.** `_validate_speech_blocks_document` enforces the exact top-level field set on write; `load_speech_blocks_document` swallows `OSError`/`JSONDecodeError`/validation errors and returns `None`, so a legacy list-shaped artifact reads as not-started — matching the plan's "reset & regenerate" decision.
- **Legacy reset.** `_OPERATION_ARTIFACT_FILE_NAMES["speech_blocks"]` still lists `speech_blocks_report.json` / `speech_blocks_state.json`, so `reset_speech_blocks` cleans pre-consolidation projects. The AI-log glob (`log_ai_speech_blocks_*.log`) matches `config.ai_transaction_log_file_name`'s `.log` extension.
- **Id uniqueness inside one document.** `_stable_speech_block_id` + `_renumber_speech_blocks`/`_renumber_single_chunk_blocks` keep a per-pass `used_ids` set, so no two blocks in a written document can share an id even when generation hands over colliding ids (e.g. after scene-ambience insertion).
- **Insert/delete resequencing.** `insert_speech_block` shifts `sequence_index` for the tail of the chunk before appending, `delete_speech_block` relies on `_renumber_speech_blocks` to close the gap; both keep chunk-local indices contiguous from 1 and neither touches other chunks.
- **Approval survival.** Approvals and `approved_at` ride on the block dicts through `load_speech_blocks` → mutate → `_persist_*`; a resume keeps previously approved rows (`test_start_or_continue_generation_resumes_after_partial_review_approval`), a per-chunk resplit only replaces that chunk's rows, and `update_character_speech_block_display_name` deliberately preserves approval while `fallback_character_speech_blocks_to_narrator` deliberately clears it.
- **Narrator/character/operation distinction.** `_normalize_persisted_speech_block` and `build_speech_block_payload` both force operation content kinds (`scene_ambience`/`pause`/`indication`) onto the operation speaker entry regardless of what was persisted or returned by the model, so an operation row can never end up owning a character voice.
- **LLM parse failure.** `_generate_direct_block_response` catches `ValueError` from `llm_provider_service.chat_json` and returns a narrator fallback block flagged `speech_blocks_ai_parse_failed` + `needs_review` with empty usage — the failure is surfaced to the operator rather than swallowed, and the source text is preserved verbatim.
- **Cancellation.** `raise_if_cancelled` is checked before each chunk, before and after each provider call, and after each segment persist; the last `status: "running"` document plus its checkpoint is what a later run resumes from, so a cancel loses at most the in-flight segment. A stale `running` status does not lock the page — `handle_generate_requested` guards on the in-process `_active_operation_kind`, not on the persisted status.
- **`same_narrator` path.** `_deterministic_narrator_chunk_blocks` calls no model, carries `cleanup_boundary_confidence` through as `weak_source_boundary` + `needs_review` (`_cleanup_review_warning_flags`), and flags rather than cuts over-budget sentences — matching knowledge doc §6.
- **State service.** `_speaker_catalog_entries`'s narrator filter compares `speaker_id` against `SPEAKER_KIND_NARRATOR`; both constants are the literal `"narrator"`, so the filter is correct today (fragile naming, not a defect). `_source_chunks_are_resolvable` correctly refuses to resolve when the selected voice language is neither the original nor a completed translation.
