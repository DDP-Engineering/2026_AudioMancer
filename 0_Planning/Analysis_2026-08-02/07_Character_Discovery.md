# Component Review — Character Discovery
_Reviewed 2026-08-02. Files: `04_Software/AudioMancer/src/audiomancer/services/character_discovery_service.py` (2861), `04_Software/AudioMancer/src/audiomancer/services/character_discovery_state_service.py` (303), `04_Software/AudioMancer/src/audiomancer/ui/pages/characters_page.py` (1204), `04_Software/AudioMancer/src/audiomancer/ui/controllers/characters_ui_controller.py` (1081). Total ~5450 lines._

## Summary

The component is structurally sound: the strict document contract, the atomic
checkpoint writes, the chunk-id-anchored evidence, and the Qt page's row/id
handling all hold up under inspection. Two defect clusters are real and
reachable: (1) mixing operator CRUD with a *resumable* (cancelled/failed) run
destroys operator data and silently skips discovered characters, and (2) the
identity normalizer is ASCII-only, which breaks character merging and blocks all
manual add/edit for any non-Latin-script book. Findings: 1 Critical, 4 Major,
5 Minor.

## Findings

### [CD-1] Manually added characters are erased when a cancelled/failed run is resumed — **Critical**

- **File:** `services/character_discovery_service.py:453-474`, `:1808-1813`

- **What:** Every discovery-phase checkpoint write derives the persisted
  `characters` array from the checkpoint's `synthesized_profiles` key, and the
  in-loop checkpoint hard-codes that key to an empty list:

  ```python
  discovery_checkpoint = {
      "completed_window_count": discovery_progress_current,
      "next_discovery_start_chunk_index": next_discovery_start_chunk_index,
      "raw_candidates": list(raw_candidates),
      "merged_candidates": [],
      "rejected_candidates": [],
      "synthesized_profiles": [],          # <-- always empty during discovery
  }
  _write_operation_state(..., phase="discovery", checkpoint=discovery_checkpoint)
  ```

  and in `_write_operation_state`:

  ```python
  elif legacy_checkpoint is not None:
      flat_characters = _restore_mapping_list(legacy_checkpoint.get("synthesized_profiles"))
  ...
  "characters": [ _nested_character_profile(profile, ...) for profile in flat_characters ],
  ```

- **Why it matters:** `build_character_discovery_state` enables Add whenever the
  document exists (`can_add = has_discovery_result`, `state_service.py:135`), so
  after cancelling a long run the operator can add characters they already know
  about. `add_character_profile` -> `_write_character_profiles` keeps
  `status: "cancelled"` and the discovery checkpoint, so the document now holds
  `characters: [Ghost]` plus a resumable checkpoint. Pressing Start again:
  the first completed window writes `characters: []`, permanently deleting
  `Ghost` from `characters.json`. If the operator cancels that resumed run
  (the cancel handler writes the same `discovery_checkpoint`, `:482-497`), the
  manual character is gone for good — it is never re-committed. No warning, no
  confirmation.

- **Fix:** In `_write_operation_state`, when the caller passes no explicit
  `characters` list, fall back to the characters already in
  `existing_document` instead of to the checkpoint's `synthesized_profiles`
  during the discovery phase (the discovery phase produces no characters, so it
  should never rewrite that array).

### [CD-2] Resume counts persisted characters as already-synthesized, so merged candidates are silently skipped — **Major**

- **File:** `services/character_discovery_service.py:1647-1667`, `:549`

- **What:** `_restore_resume_state` returns the persisted `characters` as
  `synthesized_profiles` for **both** phases, including `discovery`:

  ```python
  synthesized_profiles = [
      _normalize_character_profile(_flat_character_profile(item))
      for item in existing_state.get("characters", [])
      if isinstance(item, dict)
  ]
  if phase == "discovery":
      ...
      return (next_chunk_index, next_chunk_index, candidates, [], [], synthesized_profiles, None)
  ```

  and the synthesis loop uses that length as its start index:

  ```python
  for profile_index in range(len(synthesized_profiles), len(merged_candidates)):
  ```

- **Why it matters:** Same entry state as CD-1 (one manual character added to a
  cancelled discovery-phase document). On resume `synthesized_profiles` has
  length 1, so synthesis starts at index 1 and `merged_candidates[0]` — sorted
  first, i.e. the character with the earliest evidence, typically the
  protagonist — is never synthesized and never appears in the result. N manual
  characters => N discovered characters dropped.
  The synthesis-phase branch has the mirror-image bug: the manual profile is
  sorted into `characters` by `_profile_sort_key` (its synthetic evidence has
  `sequence_index: 0`, so it lands near the front), then
  `synthesized_profiles = synthesized_profiles[:next_candidate_index]`
  (`:1676`) truncates the list and discards one genuinely synthesized character.

- **Fix:** Return `[]` for `synthesized_profiles` in the discovery branch, and
  drive the synthesis resume index from the checkpoint's
  `next_candidate_index` rather than from `len(synthesized_profiles)`.

### [CD-3] `validate_manual_character_name` rejects every non-Latin name, blocking add *and* edit — **Major**

- **File:** `services/character_discovery_service.py:726-731`, `:2722-2728`

- **What:**

  ```python
  normalized_identity = _normalize_identity(normalized_name)
  if not normalized_identity:
      raise ValueError("invalid_name")
  ```

  ```python
  def _normalize_identity(value: str) -> str:
      return re.sub(r"[^a-z0-9]+", "", value.casefold())
  ```

  Verified: `"Иван"` -> `""`, `"李明"` -> `""`, `"Ελένη"` -> `""`.

- **Why it matters:** `update_character_profile` calls the same validator
  (`:763-767`), and the controller calls it again before saving
  (`characters_ui_controller.py:209`). So for a Russian, Greek, Chinese,
  Japanese, Korean, Hebrew or Arabic source — or any project translated into
  one — the operator cannot add a character, and cannot save *any* edit
  (gender, age, voice prompt) to an AI-discovered character whose canonical
  name is in the source script: the save fails with "invalid character name".
  Since the whole component is premised on operator correction, this removes
  the correction path entirely for those books. The only workaround is
  renaming every character to ASCII.

- **Fix:** Make `_normalize_identity` Unicode-aware, e.g.
  `re.sub(r"[^\w]+", "", value.casefold(), flags=re.UNICODE)` (optionally after
  `unicodedata.normalize("NFKD", ...)`), which keeps the existing ASCII
  behaviour and stops collapsing non-Latin scripts to the empty string.

### [CD-4] ASCII-only identity normalization splits and merges the wrong characters — **Major**

- **File:** `services/character_discovery_service.py:2722-2728`, used at `:2078-2080`

- **What:** `_group_character_candidates_by_identity` keys on
  `_normalize_identity` and then drops empty keys:

  ```python
  alias_keys = {_normalize_identity(str(candidate.get("canonical_name", "")))}
  alias_keys.update(_normalize_identity(alias) for alias in list(candidate.get("aliases", [])))
  alias_keys.discard("")
  ```

  Measured normalizations: `"René"` -> `"ren"`, `"Rene"` -> `"rene"`,
  `"Renée"` -> `"rene"`, `"José"` -> `"jos"`, `"Jos"` -> `"jos"`,
  `"Иван"` -> `""`.

- **Why it matters:** Two distinct failure modes on ordinary input.
  *Split:* for a non-Latin-script book every candidate has an empty key set, so
  `matching_group_indexes` is always empty and each window's mention becomes its
  own group. A character named in 12 windows becomes 12 identical characters,
  each burning one synthesis AI call, each getting id `character_0001`…`0012`
  (`_slugify_character_id` also yields `""` and falls back to the positional
  slug, `:2738`). The same happens for `"René"` vs `"Rene"` (accented vs
  unaccented spellings of one name).
  *False merge:* `"Rene"` and `"Renée"` — two different people — normalize to
  the same key and are merged into one character with a single voice.

- **Fix:** Same one-line change as CD-3; both symptoms come from the same
  regex.

### [CD-5] A corrupt or legacy `characters.json` makes the Characters page throw instead of offering Reset — **Major**

- **File:** `services/character_discovery_state_service.py:99`

- **What:** The page-state builder calls the strict reader unguarded:

  ```python
  document = character_discovery_service.load_character_document(project_root)
  profiles = character_discovery_service.load_character_profiles(project_root)
  ```

  `load_character_document` raises `CharacterDocumentError` for invalid JSON,
  an unexpected root key set, a bad status, a non-bool `usage_available`, or any
  incompatible nested character record (`:845-935`). The knowledge doc states
  those rejections are intended.

- **Why it matters:** `build_character_discovery_state` runs from
  `main_window._refresh_characters_page_state`, i.e. on every project-state
  refresh while the Characters page is visible. A document written by an earlier
  build (the contract is explicitly "hard-break"), or a hand-edited file, makes
  the exception escape into the Qt slot: the page never renders, so the operator
  cannot reach the Reset button that would fix it. Notably
  `project_workspace_service._character_discovery_completion_evidence:832-834`
  guards exactly this call with `except CharacterDocumentError: return None`,
  so the need for the guard is already recognised elsewhere.

- **Fix:** Wrap the two loads in
  `except character_discovery_service.CharacterDocumentError`, treat the result
  as "document present but unreadable" (no profiles, `can_reset = True`), and
  put the error text in the notes list.

### [CD-6] Completed-run summary note always reports "0 analysis windows" — **Minor**

- **File:** `services/character_discovery_state_service.py:110-115`, `:194`

- **What:** The synthesized `report` contains only two keys, but the note reads
  a third:

  ```python
  report = ( None if ... else {"token_usage": dict(document["token_usage"]), "warnings": []} )
  ...
  ui_state_service.translate("characters.note_summary", language).format(
      character_count=len(profiles),
      analyzed_window_count=int(report.get("analyzed_window_count", 0)),
  )
  ```

  `analyzed_window_count` is never written into `report` anywhere in the
  codebase (grep-confirmed: the only occurrences are this read and the two
  translation strings).

- **Why it matters:** After every successful run the operator sees "Discovered
  N speaking characters across **0** analysis windows", which reads like a
  failure.

- **Fix:** Either drop the placeholder from the `characters.note_summary`
  string, or populate it from the document (the completed document no longer
  stores a window count, so dropping it is the smaller change).

### [CD-7] Discovery AI logs use a token that Reset does not match, and the log-reuse branch is dead — **Minor**

- **File:** `services/character_discovery_service.py:1752-1760`, `:1747-1751`

- **What:** The log file is named with the token `"characters"`:

  ```python
  config.ai_transaction_log_file_name("characters", timestamp_token)
  ```

  producing `log_ai_characters_<ts>.log`, while
  `operation_runtime_service.reset_operation_data` deletes
  `f"{AI_TRANSACTION_LOG_FILE_PREFIX}{log_token}_*.log"` with
  `log_token = "character_discovery"` (there is no remap entry for this kind in
  `_OPERATION_AI_LOG_TOKENS`). The knowledge doc also names the files
  `log_ai_character_discovery_*.log`.
  Separately, the reuse branch

  ```python
  if log_relative_path not in (None, ""):
      resolved_log_path = project_root / Path(str(log_relative_path)).name
  ```

  is unreachable: `_restore_resume_state` returns `None` for the log path on
  every code path (`:1638`, `:1641`, `:1644`, `:1654`, `:1666`, `:1669`,
  `:1671`, `:1684`).

- **Why it matters:** Reset Discovery leaves every previous AI transaction log
  behind, and each resume of a long run starts yet another log file, so a
  repeatedly-resumed project accumulates logs that no in-app action ever
  removes.

- **Fix:** Use `"character_discovery"` as the log token (or add a
  `"character_discovery": ("characters",)` entry to `_OPERATION_AI_LOG_TOKENS`),
  and delete the unreachable reuse branch.

### [CD-8] Rejected-candidate diagnostics are computed, threaded through the whole run, then discarded — **Minor**

- **File:** `services/character_discovery_service.py:2049-2065`, `:380`, `:535`, `:1823-1830`

- **What:** `_merge_character_candidates_with_rejections` builds a
  `rejected` list (`missing_evidence`, `missing_spoken_dialogue_evidence`),
  which is carried in `rejected_candidates` through eight `_write_operation_state`
  call sites — but the persisted synthesis checkpoint only keeps
  `phase`/`next_candidate_index`/`candidates`, and `_restore_resume_state`
  always returns `[]` for it. Nothing reads it, and `character_operation_summary`
  hard-codes `"warning_count": 0` (`:198`).

- **Why it matters:** Characters the model found but that failed the
  spoken-dialogue gate disappear with no operator-visible trace; the operator
  sees a shorter list than the book warrants and has no way to know why. The
  diagnostic data needed to explain it is produced and thrown away.

- **Fix:** Either surface the rejection count in the notes
  (`build_character_discovery_notes`) or delete the `rejected_candidates`
  plumbing.

### [CD-9] Resume reports a chunk index as the completed-window count, corrupting progress totals — **Minor**

- **File:** `services/character_discovery_service.py:1659-1667`, `:346`

- **What:** The discovery branch returns the chunk index as both the first
  (`completed_window_count`) and second (`next_discovery_start_chunk_index`)
  tuple element:

  ```python
  return (next_chunk_index, next_chunk_index, candidates, [], [], synthesized_profiles, None)
  ```

  and the caller then does `discovery_progress_total = completed_window_count + len(windows)`.

- **Why it matters:** Windows hold up to 8 chunks
  (`DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE`), so resuming a 100-chunk book at
  chunk 40 shows "40 / 48" in the modal instead of "5 / 13", and the final
  synthesis total is inflated by the same amount. Purely a display defect, but
  it makes a resumed run look almost finished when it is a third done.

- **Fix:** Return `next_chunk_index // window_size` (or persist the completed
  window count in the checkpoint) for the first element.

### [CD-10] The AI profile used by a resumed run is not recorded and the selector always snaps back to the default — **Minor**

- **File:** `services/character_discovery_state_service.py:121-124`, `services/character_discovery_service.py:1795-1802`

- **What:** The page state always resolves the selector with `None` as the
  preferred id:

  ```python
  profile_state = build_character_discovery_profile_state(
      settings_payload,
      None,
  )
  ```

  and `_write_operation_state` explicitly discards the profile id instead of
  persisting it:

  ```python
  _ = (progress_current, progress_total, run_token, profile_id, input_fingerprint, log_relative_path)
  ```

  `_persisted_profile_id` (`state_service.py:276-300`), whose entire purpose is
  to recover the last-used profile, is dead code — nothing calls it.

- **Why it matters:** `main_window._refresh_characters_page_state` feeds this
  value into both `set_ai_profiles` and `set_character_state`, and the page
  applies it (`characters_page.py:399-402`). Any refresh (saving a character,
  cancelling a run) resets the combo to
  `default_character_extraction_profile_id`, so an operator who selected a
  different profile and then resumes a cancelled run silently continues it with
  a different model. Nothing in the document records which profile produced the
  existing candidates.

- **Fix:** Persist the profile id in the document (or at least seed the
  selector from the page's current selection instead of `None`).

## Duplication

- `_profile_sort_key` exists twice with identical bodies —
  `character_discovery_service.py:2757-2769` and
  `characters_page.py:1130-1143` — and `_candidate_sort_key`
  (`:2742-2754`) is a third copy differing only in the dict key it reads. The
  page and the service must agree on ordering or the list rows and the persisted
  order drift; sharing one helper would make that structural.
- `_merge_character_candidates` (`:2027-2036`) is a wrapper used only by tests;
  production code calls `_merge_character_candidates_with_rejections` directly.
- `_persisted_profile_id` in `character_discovery_state_service.py:276-300` is a
  verbatim copy of `speech_blocks_state_service._persisted_profile_id`; only the
  Speech Blocks copy is wired up.
- The six `_write_operation_state` calls in `start_or_continue_discovery`
  repeat an 11-argument keyword block that differs only in
  `status`/`phase`/progress; the checkpoint dict literal is built five times
  with the same six keys (`:375`, `:402`, `:453`, `:530`, `:540`, `:594`). This
  is what let CD-1's `"synthesized_profiles": []` slip in unnoticed.

## Verified-clean notes

- **Evidence vs. shifted chunk indices.** `_normalize_evidence` drops any
  evidence whose `chunk_id` is not in the current `chunk_map` and re-derives
  `sequence_index` from the live chunk, so a model-invented or stale chunk
  reference cannot poison the record (`:1951-1972`). Combined with
  `invalidate_if_source_changed` / the source-fingerprint check at `:293`, a
  re-chunk invalidates the whole document rather than leaving dangling indices.
- **Qt row index vs. character id.** `_row_for_character_id`,
  `_refresh_character_list`, `_handle_character_selection_changed` and
  `_handle_editor_changed` all index the same `self._profiles` list, which is
  sorted exactly once in `set_character_state`; `begin_add_mode` appends the
  draft to that same list before rebuilding the widget, so rows and ids stay
  aligned. Renaming during edit updates the item text in place without
  re-sorting. No "edited the wrong row" path found.
- **Selection guards.** `_selection_guard` / `_loading_profile` correctly
  suppress the re-entrant `currentRowChanged` produced by
  `clear()`/`setCurrentRow()`, and the dirty-draft guard
  (`handle_selection_change_requested` -> `restore_current_selection`) restores
  the row without re-emitting.
- **LLM response parsing.** `_normalize_window_candidates` and
  `_normalize_evidence` return `[]` for non-list payloads, skip non-dict
  entries, and require a non-empty `canonical_name`; `_normalize_string_list`
  accepts both a comma string and a list. A response missing `characters`
  entirely yields zero candidates for that window and the run continues.
- **Cancellation.** Both loops call `raise_if_cancelled` at the top and wrap the
  provider call, and both `except OperationCancelledError` handlers persist the
  last committed checkpoint before re-raising; the synthesis checkpoint is
  rebuilt after every appended profile, so at most one in-flight AI call is
  lost.
- **Provenance across edits.** `update_character_profile` drops
  `_provenance_origin` when it normalizes, but `_write_character_profiles`
  re-reads `origin` from the persisted record via `existing_by_id`, so a manual
  character stays `origin: "manual"` after an edit and
  `_flat_character_profile` still projects `review_status: "manual"`.
- **Character ids across a re-run.** Ids are slugs of the canonical name
  (`_slugify_character_id`), not positional, so a re-run over unchanged text
  reproduces the same ids for Latin-script names. (Non-Latin names fall back to
  the positional `character_%04d` slug — see CD-4.)
- **Identity grouping order-dependence.** `_group_character_candidates_by_identity`
  attaches a multi-match candidate to `min(matching_group_indexes)` without
  unioning the other matched groups, so "Beth" and "Beatrice" can end up in
  different groups even though both claim alias "B". This is deliberate:
  `test_group_character_candidates_preserves_first_match_order` pins exactly
  this output against a reference implementation. Noted, not filed.
