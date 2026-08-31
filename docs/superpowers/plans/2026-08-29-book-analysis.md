# Book Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Subagent execution is not authorized for this task.

**Goal:** Add an optional, model-agnostic, resumable Book Analysis page after Text Chunking that produces a layered report in the project target language without affecting the canonical workflow.

**Architecture:** A strict atomic `book_analysis.json` keeps the last completed report separate from a resumable candidate. A domain service packs whole canonical chunks into conservative model windows, checkpoints validated leaf/consolidation summaries, and synthesizes the final report through the existing JSON chat provider. A state/page/controller boundary integrates the supporting operation into the existing status and progress UI without adding a workflow stage.

**Tech Stack:** Python 3.12, PySide6, standard-library JSON/hash/path/threading utilities, existing AudioMancer services, pytest, pytest-qt, Ruff.

**Spec:** `.agentic/specs/REQ-FUNC-e73cba08.md`

## Global Constraints

- Work on the existing `master` checkout; do not create a branch, commit, push, or open a pull request.
- Book Analysis is optional and consumes only a completed valid `chunks_text.json`.
- The report language is the project `target_language`; no report-language selector or free-form instruction box is added.
- Accept every compatible LM Studio, Ollama, or generic OpenAI-compatible model by capability, never by model-name allowlist.
- Reject profile context below 16,384 tokens; source text is capped at 50 percent of local context or 30 percent of online context and also at capacity remaining after prompt, output/reasoning, and safety reserves.
- Never split a canonical chunk; reject an oversized single chunk with Text Chunking guidance.
- Preserve stale completed reports; exact candidate resume requires matching chunks, target language, profile ID, and safe request-configuration fingerprint.
- A fresh completed report remains current regardless of the profile selector and keeps Analyze disabled until Reset.
- The page has one AI-profile selector and exactly two `QPushButton` actions: Analyze and Reset. Context and reasoning mode remain visible only in AI Settings.
- Use the existing Operation Status button and standard operation progress dialog/bar.
- Automated tests must use deterministic doubles only: no API keys, network connections, LM Studio/Ollama launch, or live generation.
- Preserve existing user changes in `00_Planning/README.md` and `00_Planning/Book_Analysis_Agentic_Implementation_Plan.md`; retain every existing runtime profile value while adding only the new settings-schema fields to `settings.json`.

---

### Task 1: Book Analysis context budgeting

**Requirement:** `REQ-NFR-057ca9b2`

**Files:**
- Modify: `05_Software/AudioMancer/src/audiomancer/config.py`
- Create: `05_Software/AudioMancer/src/audiomancer/services/book_analysis_budget_service.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_budget_service.py`

**Interfaces:**
- Consumes: normalized profile dictionaries and `ai_budget_service.estimate_text_tokens(text)`.
- Produces: `build_request_budget(profile_payload, prompt_text) -> dict[str, int | str]`, `reduced_source_budget(budget) -> int`, and `source_text_fits(text, source_budget_tokens) -> bool`.

- [ ] **Step 1: Write the failing boundary and fraction tests**

```python
def test_build_request_budget_accepts_exact_16k_local_context() -> None:
    budget = book_analysis_budget_service.build_request_budget(
        _profile("lmstudio", context_window=16_384, reasoning_mode="disabled"),
        "system and user shell",
    )
    assert budget["context_window"] == 16_384
    assert 512 <= budget["source_budget_tokens"] <= 8_192


@pytest.mark.parametrize(
    ("backend_kind", "maximum"),
    (("lmstudio", 8_192), ("ollama", 8_192), ("openai_compatible", 4_915)),
)
def test_build_request_budget_applies_backend_fraction(backend_kind: str, maximum: int) -> None:
    budget = book_analysis_budget_service.build_request_budget(
        _profile(backend_kind, context_window=16_384),
        "prompt",
    )
    assert budget["source_budget_tokens"] <= maximum
```

- [ ] **Step 2: Run the tests and record the expected red**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_budget_service.py`

Expected: exit 1 because `book_analysis_budget_service` does not exist. Record this exact command, exit code, and reason in `TASK-022bb563`, then run `python .agentic/aegis.py anchor --task TASK-022bb563` before implementation.

- [ ] **Step 3: Add constants and the minimal budget implementation**

```python
BOOK_ANALYSIS_MIN_CONTEXT_TOKENS = 16_384
BOOK_ANALYSIS_LOCAL_SOURCE_CONTEXT_FRACTION = 0.50
BOOK_ANALYSIS_ONLINE_SOURCE_CONTEXT_FRACTION = 0.30
BOOK_ANALYSIS_OUTPUT_CONTEXT_FRACTION = 0.20
BOOK_ANALYSIS_REASONING_CONTEXT_FRACTION = 0.10
BOOK_ANALYSIS_SAFETY_CONTEXT_FRACTION = 0.05
BOOK_ANALYSIS_MIN_SAFETY_TOKENS = 512
BOOK_ANALYSIS_MIN_SOURCE_TOKENS = 512
BOOK_ANALYSIS_OVERFLOW_RETRY_FRACTION = 0.75
```

```python
def build_request_budget(profile_payload: dict[str, object], prompt_text: str) -> dict[str, int | str]:
    context_window = int(profile_payload.get("context_window", 0))
    if context_window < config.BOOK_ANALYSIS_MIN_CONTEXT_TOKENS:
        raise ValueError("Book Analysis requires an AI profile context window of at least 16,384 tokens.")
    reasoning_mode = str(profile_payload.get("reasoning_mode", "provider_default"))
    output_reserve = min(
        int(profile_payload.get("max_output_tokens", config.DEFAULT_LLM_MAX_OUTPUT_TOKENS)),
        max(1_024, int(context_window * config.BOOK_ANALYSIS_OUTPUT_CONTEXT_FRACTION)),
    )
    reasoning_reserve = 0 if reasoning_mode == "disabled" else int(
        context_window * config.BOOK_ANALYSIS_REASONING_CONTEXT_FRACTION
    )
    prompt_reserve = ai_budget_service.estimate_text_tokens(prompt_text)
    safety_reserve = max(
        config.BOOK_ANALYSIS_MIN_SAFETY_TOKENS,
        int(context_window * config.BOOK_ANALYSIS_SAFETY_CONTEXT_FRACTION),
    )
    fraction = (
        config.BOOK_ANALYSIS_ONLINE_SOURCE_CONTEXT_FRACTION
        if ai_budget_service.uses_online_text_budget(profile_payload)
        else config.BOOK_ANALYSIS_LOCAL_SOURCE_CONTEXT_FRACTION
    )
    post_reserve = context_window - output_reserve - reasoning_reserve - prompt_reserve - safety_reserve
    source_budget = min(int(context_window * fraction), post_reserve)
    if source_budget < config.BOOK_ANALYSIS_MIN_SOURCE_TOKENS:
        raise ValueError("Book Analysis profile reserves leave too little context for source text.")
    return {
        "context_window": context_window,
        "source_budget_tokens": source_budget,
        "output_reserve_tokens": output_reserve,
        "reasoning_reserve_tokens": reasoning_reserve,
        "prompt_reserve_tokens": prompt_reserve,
        "safety_reserve_tokens": safety_reserve,
        "reasoning_mode": reasoning_mode,
    }
```

- [ ] **Step 4: Add below-minimum, reserve, exact-fit, reduction, and oversized-text tests**

Test names: `test_build_request_budget_rejects_context_below_16k`, `test_reserves_reduce_fraction_capacity`, `test_source_text_fits_exact_budget`, and `test_reduced_source_budget_uses_one_75_percent_retry`.

- [ ] **Step 5: Run focused tests and record the no-commit checkpoint**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_budget_service.py tests/test_ai_budget_service.py`

Expected: all pass. Update the requirement links/status and run `python .agentic/aegis.py test --impacted --base HEAD`. Do not commit.

---

### Task 2: Strict atomic report and candidate document

**Requirement:** `REQ-DATA-8e648624`

**Files:**
- Modify: `05_Software/AudioMancer/src/audiomancer/config.py`
- Create: `05_Software/AudioMancer/src/audiomancer/services/book_analysis_document_service.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_document_service.py`

**Interfaces:**
- Consumes: completed canonical chunk dictionaries and `persistence_service.write_json_atomic`.
- Produces: `document_path`, `empty_document`, `load_document`, `write_document`, `canonical_source_descriptor`, `safe_profile_fingerprint`, `candidate_resume_matches`, `completed_report_is_stale`, and `derive_operation_state`.

- [ ] **Step 1: Write failing strict-document and preservation tests**

```python
def test_write_document_preserves_completed_report_while_candidate_changes(tmp_path) -> None:
    completed = _completed_report(source_fingerprint="source-a")
    document = book_analysis_document_service.empty_document()
    document["completed_report"] = completed
    document["candidate_run"] = _candidate(status="running")
    book_analysis_document_service.write_document(tmp_path, document)
    loaded = book_analysis_document_service.load_document(tmp_path)
    assert loaded["completed_report"] == completed
    assert loaded["candidate_run"]["status"] == "running"


def test_completed_report_staleness_ignores_profile_selection() -> None:
    report = _completed_report(source_fingerprint="same", target_language="ro", profile_id="profile-a")
    source = {"fingerprint": "same", "chunk_count": 2}
    assert not book_analysis_document_service.completed_report_is_stale(report, source, "ro")
```

- [ ] **Step 2: Run and record the expected red**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_document_service.py`

Expected: exit 1 because the document service does not exist. Record the red before implementation.

- [ ] **Step 3: Implement the strict schema and safe fingerprints**

```python
def canonical_source_descriptor(chunks: list[dict[str, object]]) -> dict[str, object]:
    canonical = [
        {
            "chunk_id": str(chunk["chunk_id"]),
            "sequence_index": int(chunk["sequence_index"]),
            "text": str(chunk["text"]),
        }
        for chunk in chunks
    ]
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "fingerprint": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "chunk_count": len(canonical),
    }


def safe_profile_fingerprint(profile_payload: dict[str, object]) -> str:
    safe_request_fields = {
        key: profile_payload.get(key)
        for key in (
            "backend_kind", "base_url", "model_name", "context_window",
            "max_output_tokens", "request_timeout_seconds", "temperature",
            "supports_structured_output", "reasoning_mode",
        )
    }
    encoded = json.dumps(safe_request_fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
```

Validation must require exactly `schema_version`, `completed_report`, and `candidate_run` at the root; reject unknown lifecycle status, malformed report layers, non-consecutive checkpoint indices, and any persisted key whose normalized name contains `api_key`, `authorization`, `token`, or `secret` except the allowed aggregate `token_usage` key.

- [ ] **Step 4: Add resume, stale, interruption, invalid-shape, and atomic-replacement tests**

Test names: `test_candidate_resume_requires_source_language_profile_and_config_match`, `test_running_candidate_loads_as_interrupted_state`, `test_source_change_marks_completed_report_stale_without_deleting_it`, `test_invalid_document_is_rejected`, and `test_atomic_write_preserves_previous_document_on_replace_failure`.

- [ ] **Step 5: Run the document regression set and impacted gate**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_document_service.py tests/test_atomic_io_contracts.py`

Expected: all pass. Link tests and activate the requirement; run the impacted AEGIS test. Do not commit.

---

### Task 3: Model-agnostic reasoning preference

**Requirement:** `REQ-PLAT-4b56b5de`

**Files:**
- Modify: `05_Software/AudioMancer/src/audiomancer/config.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/settings_service.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/ui/pages/ai_settings_page.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
- Modify: `05_Software/AudioMancer/settings.example.json`
- Modify: `05_Software/AudioMancer/settings.json` (schema fields only; preserve profile values)
- Test: `05_Software/AudioMancer/tests/test_settings_service.py`
- Test: `05_Software/AudioMancer/tests/test_llm_provider_service.py`
- Test: `05_Software/AudioMancer/tests/test_ai_settings_page.py`
- Test: `05_Software/AudioMancer/tests/test_ai_settings_ui_controller.py`

**Interfaces:**
- Produces profile field `reasoning_mode` in `{"provider_default", "enabled", "disabled"}` and setting `default_book_analysis_profile_id`.
- Extends `chat_json` results with `request_metadata.reasoning_mode_effective` while preserving existing `payload` and `usage` keys.

- [ ] **Step 1: Write failing settings normalization and unknown-model request tests**

```python
@pytest.mark.parametrize("mode", ("provider_default", "enabled", "disabled"))
def test_validate_settings_preserves_reasoning_mode(mode: str) -> None:
    payload = settings_service.build_default_settings()
    payload["llm_profiles"] = [_profile(reasoning_mode=mode)]
    assert settings_service.validate_settings(payload)["llm_profiles"][0]["reasoning_mode"] == mode


def test_chat_json_disables_reasoning_for_unknown_lmstudio_model(monkeypatch) -> None:
    requests = _capture_successful_requests(monkeypatch)
    result = llm_provider_service.chat_json(
        _profile(model_name="vendor/model-never-seen", reasoning_mode="disabled"),
        "system",
        "user",
    )
    assert requests[0]["reasoning_effort"] == "none"
    assert result["request_metadata"]["reasoning_mode_effective"] == "disabled"
```

- [ ] **Step 2: Run and record the expected red**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_settings_service.py tests/test_llm_provider_service.py -k reasoning`

Expected: exit 1 because reasoning mode is neither normalized nor sent. Record the red.

- [ ] **Step 3: Normalize and display reasoning mode only in AI Settings**

Add `LLM_REASONING_MODE_OPTIONS`, `DEFAULT_LLM_REASONING_MODE`, the profile field, and the Book Analysis default-profile key. Add one localized `QComboBox` to the profile editor and one default Book Analysis profile combo to the workflow defaults. `build_current_profile_payload`, editor sync/load, `build_settings`, and default-combo reload must round-trip both values. Add only `reasoning_mode` and `default_book_analysis_profile_id` to runtime `settings.json`, preserving all existing profile values.

- [ ] **Step 4: Add capability fallback in the provider**

```python
def _reasoning_effort_for_profile(profile_payload: dict[str, object]) -> str | None:
    mode = str(profile_payload.get("reasoning_mode", config.DEFAULT_LLM_REASONING_MODE))
    return {"enabled": "medium", "disabled": "none"}.get(mode)
```

When `_request_chat_completion` receives HTTP 400 explicitly naming unsupported `reasoning_effort`, raise `_UnsupportedReasoningModeError`. `chat_json` retries the same call once after removing only that field, retains the fallback for outer retries/JSON repair, logs `reasoning_mode_unsupported_retry_provider_default`, and reports `provider_default` in `request_metadata`. The decision checks fields and error markers only; it never checks `model_name`.

- [ ] **Step 5: Add provider-default, enabled, disabled, backend, fallback, and UI tests**

Cover LM Studio, Ollama, and `openai_compatible`; assert provider default omits the field, enabled sends `medium`, disabled sends `none`, an explicit rejection retries without it, unrelated HTTP 400 does not retry, and the mode control appears on AI Settings but no context/reasoning widget exists on Book Analysis later.

- [ ] **Step 6: Run focused settings/provider/UI tests and impacted gate**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_settings_service.py tests/test_llm_provider_service.py tests/test_ai_settings_page.py tests/test_ai_settings_ui_controller.py`

Expected: all pass. Link tests, activate the requirement, and run the impacted AEGIS test. Do not commit.

---

### Task 4: Resumable hierarchical analysis engine

**Requirement:** `REQ-FUNC-e73cba08`

**Files:**
- Create: `05_Software/AudioMancer/prompts/book_analysis_leaf.txt`
- Create: `05_Software/AudioMancer/prompts/book_analysis_consolidate.txt`
- Create: `05_Software/AudioMancer/prompts/book_analysis_report.txt`
- Create: `05_Software/AudioMancer/src/audiomancer/services/book_analysis_service.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_service.py`

**Interfaces:**
- Consumes: `chunking_document_service.load_chunks`, document/budget services, prompt templates, `llm_provider_service.chat_json`, cancellation/progress callbacks, and project target language.
- Produces: `analyze_book(project_root, ai_profile_payload, target_language, progress_callback=None, cancel_requested=None) -> dict[str, object]` and `reset_book_analysis(project_root) -> None`.

- [ ] **Step 1: Write the failing whole-chunk resume test**

```python
def test_analyze_book_resumes_after_validated_leaf_without_repeating_it(monkeypatch, tmp_path) -> None:
    _write_completed_chunks(tmp_path, ["one", "two", "three", "four"])
    calls = _script_provider(monkeypatch, cancel_after_first_leaf=True)
    with pytest.raises(OperationCancelledError):
        book_analysis_service.analyze_book(tmp_path, _profile(), "ro", cancel_requested=calls.cancelled)
    first_document = book_analysis_document_service.load_document(tmp_path)
    assert len(first_document["candidate_run"]["leaf_summaries"]) == 1
    calls.resume_with_valid_results()
    report = book_analysis_service.analyze_book(tmp_path, _profile(), "ro")
    assert calls.leaf_chunk_ids.count(first_document["candidate_run"]["leaf_summaries"][0]["chunk_ids"]) == 1
    assert report["status"] == "completed"
```

- [ ] **Step 2: Run and record the expected red**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_service.py::test_analyze_book_resumes_after_validated_leaf_without_repeating_it`

Expected: exit 1 because the analysis service does not exist. Record the red.

- [ ] **Step 3: Define exact provider schemas and prompts**

Leaf/consolidation payload:

```json
{"summary":"Ana discovers the hidden archive.","characters":[{"name":"Ana","role":"protagonist"}],"subjects":["memory"],"themes":["identity"],"settings":["Bucharest, present day"],"narrative_notes":["third-person limited"],"audiobook_notes":["restrained suspense"],"uncertainties":["The visitor's identity is not yet resolved."]}
```

Final payload:

```json
{"concise":{"book_type":"novel","genres":["mystery"],"subjects":["memory"],"setting_time":["Bucharest, present day"],"summary":"Ana investigates a hidden archive.","main_characters":[{"name":"Ana","role":"protagonist"}],"themes":["identity"]},"details":{"detailed_summary":"Ana follows the archive's history and confronts its keeper.","supporting_characters":[{"name":"Mihai","role":"archivist","relationships":["Ana's reluctant guide"]}],"narrative_perspective":"third-person limited","narrative_structure":"linear with brief recollections","tone":["intimate","suspenseful"],"pacing":"measured","diction":"literary and direct","emotional_range":["curiosity","grief","resolve"],"audiobook_guidance":{"narration_style":"restrained suspense","character_voice_notes":["Keep Mihai measured and reserved."]},"uncertainties":["The visitor's identity remains ambiguous."],"source_evidence":[{"chunk_ids":["chunk-0001"],"note":"Introduces Ana and the archive."}]}}
```

All three prompts explicitly require the project target language, preserve uncertainty, forbid invented evidence, and request only the corresponding JSON object.

- [ ] **Step 4: Implement deterministic windowing and checkpoint transitions**

Use ordered whole chunks. Each leaf checkpoint stores its `window_index`, first/last sequence, `chunk_ids`, validated summary, and usage. Consolidation levels store the same ordered node shape and can be partially resumed. Checkpoint after every accepted response with atomic document replacement. Persist `running`, then `cancelled`, `failed`, or `completed`; a persisted `running` candidate is treated as resumable after restart.

- [ ] **Step 5: Implement structured-output fallback and one overflow retry**

Pass the exact JSON Schema whenever the profile supports it. Otherwise call strict JSON with `allow_model_json_repair=True` and `retry_count_override=0`, allowing the provider service's one bounded correction. On a provider-confirmed context-overflow error, reduce the source budget once to 75 percent and repack from the first unprocessed canonical chunk/node. Never split a chunk; if one item exceeds the reduced budget, raise the localized-ready guidance text mentioning Text Chunking.

- [ ] **Step 6: Add algorithm, validation, usage, cancellation, mismatch, and overflow tests**

Test names: `test_analyze_book_covers_every_chunk_once_in_order`, `test_analyze_book_builds_recursive_consolidation_levels`, `test_invalid_leaf_response_is_checkpointed_as_failure_not_success`, `test_different_profile_replaces_candidate_but_preserves_completed_report`, `test_context_overflow_repacks_once_with_smaller_budget`, `test_oversized_single_chunk_sends_no_provider_request`, `test_completed_report_uses_project_target_language`, and `test_final_report_has_every_concise_and_detail_field`.

- [ ] **Step 7: Run focused engine tests and impacted gate**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_service.py tests/test_book_analysis_document_service.py tests/test_book_analysis_budget_service.py`

Expected: all pass with provider calls monkeypatched. Link tests, activate the requirement, and run the impacted AEGIS test. Do not commit.

---

### Task 5: Supporting-operation manifest and reset integration

**Requirement:** `REQ-FUNC-4fad33e4`

**Files:**
- Modify: `05_Software/AudioMancer/src/audiomancer/config.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
- Test: `05_Software/AudioMancer/tests/test_operation_runtime_service.py`
- Test: `05_Software/AudioMancer/tests/test_project_workspace_service.py`

**Interfaces:**
- Produces `SUPPORTING_OPERATION_KINDS = ("book_analysis",)` and `PROJECT_OPERATION_KINDS = WORKFLOW_OPERATION_ORDER + SUPPORTING_OPERATION_KINDS`.
- Extends exact-current reset support for Book Analysis without including it in downstream ordering or `OPERATION_STAGE_BY_KIND`.

- [ ] **Step 1: Write failing workflow-independence tests**

```python
def test_book_analysis_is_manifest_operation_but_not_workflow_stage() -> None:
    assert "book_analysis" in config.PROJECT_OPERATION_KINDS
    assert "book_analysis" not in config.WORKFLOW_OPERATION_ORDER
    assert "book_analysis" not in config.OPERATION_STAGE_BY_KIND


def test_chunking_downstream_reset_preserves_book_analysis_artifact_as_stale(tmp_path) -> None:
    analysis_path = tmp_path / config.BOOK_ANALYSIS_DOCUMENT_FILE_NAME
    analysis_path.write_text('{"preserved":true}', encoding="utf-8")
    operation_runtime_service.reset_operation_data(tmp_path, "chunking", include_current=False)
    assert analysis_path.is_file()
```

- [ ] **Step 2: Run and record the expected red**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_operation_runtime_service.py tests/test_project_workspace_service.py -k book_analysis`

Expected: exit 1 because the supporting operation is not registered. Record the red.

- [ ] **Step 3: Register the supporting operation without stage promotion**

Use `PROJECT_OPERATION_KINDS` when building/normalizing manifest summaries. `_allowed_operations_for_stage` returns the canonical prefix union all supporting operations so repair never erases their summary. `sync_manifest_operation_summary(project_root, "book_analysis", state, current_stage=None)` updates status without stage movement. `downstream_operation_kinds("book_analysis", include_current=True)` returns only `("book_analysis",)` and returns `()` when `include_current=False`.

- [ ] **Step 4: Add Book Analysis artifact/log reset ownership**

Map `book_analysis` to `BOOK_ANALYSIS_DOCUMENT_FILE_NAME` and the `book_analysis` AI-log token. Explicit reset removes only those paths. Chunking reset does not delete or reset them; staleness is derived from the preserved report against current chunks.

- [ ] **Step 5: Add stage-continuity and downstream-artifact tests**

For absent, running, failed, stale, and completed Book Analysis summaries, assert Translation and later stage availability are unchanged and `characters.json`, narrator/voice files, and downstream summaries are byte-for-byte unchanged after Book Analysis start/reset.

- [ ] **Step 6: Run focused workflow tests and impacted gate**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_operation_runtime_service.py tests/test_project_workspace_service.py tests/test_workflow_controller_service.py`

Expected: all pass. Link tests, activate the requirement, and run the impacted AEGIS test. Do not commit.

---

### Task 6: Book Analysis state projection and page

**Requirement:** `REQ-UX-7a9404e3`

**Files:**
- Create: `05_Software/AudioMancer/src/audiomancer/services/book_analysis_state_service.py`
- Create: `05_Software/AudioMancer/src/audiomancer/ui/pages/book_analysis_page.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_state_service.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_page.py`

**Interfaces:**
- Produces `build_book_analysis_profile_state(settings, selected_profile_id=None)` and `build_book_analysis_state(project_root, manifest, language, settings, selected_profile_id, operation_is_active=False)`.
- Produces `BookAnalysisPage` signals `analyze_requested(str)` and `reset_requested()` plus `set_ai_profiles`, `set_analysis_state`, `set_busy`, `current_profile_id`, and `operation_status_text`.

- [ ] **Step 1: Write failing state-table tests**

```python
@pytest.mark.parametrize(
    ("state_name", "can_analyze", "can_reset"),
    (
        ("ready", True, False),
        ("running", False, True),
        ("interrupted", True, True),
        ("fresh_completed", False, True),
        ("stale_completed", True, True),
    ),
)
def test_book_analysis_control_state(state_name: str, can_analyze: bool, can_reset: bool, scenario) -> None:
    state = book_analysis_state_service.build_book_analysis_state(**scenario(state_name))
    assert state["can_analyze"] is can_analyze
    assert state["can_reset"] is can_reset
```

- [ ] **Step 2: Run and record the expected red**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_state_service.py tests/test_book_analysis_page.py`

Expected: exit 1 because the state service/page do not exist. Record the red.

- [ ] **Step 3: Implement state derivation**

No chunks means unavailable. Missing document plus completed chunks means ready. Exact-match cancelled/failed/interrupted candidate means resumable. A fresh completed report disables Analyze regardless of selected profile. A stale source/language enables Analyze while leaving the old report visible. `can_reset` is true whenever either document slot contains started work. `operation_is_active` disables Analyze but does not clear `can_reset`.

- [ ] **Step 4: Implement the page with exactly two action buttons**

Use a profile `QComboBox`, `QPushButton("Analyze")`, `QPushButton("Reset")`, a note/stale label, concise field labels, and a checkable `QGroupBox` that shows/hides detailed report content. Do not add context-size, reasoning-mode, language, or extra-instructions controls. Render strings from the structured report without HTML supplied by the model.

- [ ] **Step 5: Add Qt signal, rendering, localization, and exact-control tests**

Assert there are exactly two `QPushButton` descendants, Analyze emits the selected profile ID, Reset emits once, stale reports remain visible, details are collapsed initially and expandable, all concise/detail sections render, and English/Romanian labels switch through `apply_language`.

- [ ] **Step 6: Run focused state/page tests and impacted gate**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_state_service.py tests/test_book_analysis_page.py tests/test_localization_parity.py tests/test_ui_localization_coverage.py`

Expected: all pass. Link tests, activate the UX requirement, and run the impacted AEGIS test. Do not commit.

---

### Task 7: Controller, shell, status, progress, and safe running reset

**Requirements:** `REQ-UX-7a9404e3`, `REQ-FUNC-4fad33e4`, `REQ-DATA-8e648624`

**Files:**
- Create: `05_Software/AudioMancer/src/audiomancer/ui/controllers/book_analysis_ui_controller.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_ui_controller.py`
- Modify: `05_Software/AudioMancer/tests/test_main_window_project_flow.py`
- Modify: `05_Software/AudioMancer/tests/test_main_window_ai_profiles.py`
- Modify: `05_Software/AudioMancer/tests/test_controller_cancellation_wiring.py`

**Interfaces:**
- Produces handlers `handle_analyze_requested(window, profile_id)`, `handle_reset_requested(window)`, and internal success/failure/cancel/manifest-sync callbacks.
- Adds page ID `book_analysis` immediately after `text_chunking`, mapped to manifest operation `book_analysis` and standard operation kind `book_analysis`.

- [ ] **Step 1: Write failing shell order and controller-dispatch tests**

```python
def test_book_analysis_page_follows_text_chunking() -> None:
    page_ids = [page_id for page_id, _label in MainWindow.PAGE_ORDER]
    assert page_ids.index("book_analysis") == page_ids.index("text_chunking") + 1


def test_analyze_dispatches_standard_threaded_operation(window, monkeypatch) -> None:
    started = _capture_workflow_start(monkeypatch)
    book_analysis_ui_controller.handle_analyze_requested(window, "profile-a")
    assert started["operation_kind"] == "book_analysis"
    assert started["set_busy"] is not None
```

- [ ] **Step 2: Run and record the expected red**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_ui_controller.py tests/test_main_window_project_flow.py -k book_analysis`

Expected: exit 1 because the page/controller are not integrated. Record the red.

- [ ] **Step 3: Wire page creation, refresh, profile state, and operation status**

Import the new state/controller/page. Add it to `PAGE_ORDER`, `PAGE_OPERATION_KIND`, `_PAGE_OPERATION_STATE_KINDS`, page construction/signals, registry, and `_refresh_current_page_state`. Read the target language from the active manifest. Use the page's selected profile when refreshing so incomplete candidate resume/mismatch notes react to the selector without changing completed-report freshness.

- [ ] **Step 4: Dispatch Analyze through the existing operation runner**

Resolve one enabled profile with `workflow_controller_service.resolve_enabled_ai_profile`; reject missing profile/chunks before starting. Call `workflow_controller_service.start_operation` with the existing progress dialog, cancellation callback, completion beep, and page busy setter. On every terminal path, derive the document operation state and call `project_workspace_service.sync_manifest_operation_summary` with `current_stage=None`, then reload project/page state.

- [ ] **Step 5: Implement safe Reset while running**

If Book Analysis is active, set `window._book_analysis_reset_pending = True` and request cooperative cancellation. The cancel/finished path performs the reset only after the worker is no longer able to checkpoint. Otherwise reset immediately. Reset calls `book_analysis_service.reset_book_analysis`, clears only the manifest `book_analysis` summary, and refreshes the page. Reset remains enabled after any started run, including while running; Analyze is disabled while running.

- [ ] **Step 6: Add status/progress/stale/completed/reset tests**

Assert the left Operation Status button is enabled for started Book Analysis and uses `page.operation_status_text`; the standard progress dialog receives leaf/consolidation/final progress; Analyze disables during running/fresh completion; stale completion enables Analyze; a second Analyze resumes; different profile replaces only an incomplete candidate; and running Reset cancels before deleting.

- [ ] **Step 7: Run focused integration tests and impacted gate**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_ui_controller.py tests/test_main_window_project_flow.py tests/test_main_window_ai_profiles.py tests/test_controller_cancellation_wiring.py tests/test_operation_status_button.py tests/test_operation_status_dialog.py tests/test_operation_runner_controller.py`

Expected: all pass. Update all linked requirements and run the impacted AEGIS test. Do not commit.

---

### Task 8: Hermetic coverage, user help, knowledge, and changelog

**Requirement:** `REQ-TEST-5a3dcf8d`

**Files:**
- Modify: all new Book Analysis tests from Tasks 1-7
- Create: `.agentic/knowledge/Book_Analysis.md`
- Modify: `.agentic/knowledge/AI_Runtime.md`
- Modify: `.agentic/knowledge/Project_Lifecycle.md`
- Modify: `.agentic/knowledge/Text_Chunking.md`
- Modify: `.agentic/knowledge/Platform_Settings_UI.md`
- Modify: `06_SoftwareDocu/UserGuide/index.html`
- Modify: `06_SoftwareDocu/UserGuide_ro/index.html`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Documents the final public behavior and test seams; no runtime API is added.

- [ ] **Step 1: Add a failing hermetic guard test before any broader execution**

```python
def test_book_analysis_tests_use_no_live_provider(monkeypatch) -> None:
    def fail_network(*_args, **_kwargs):
        raise AssertionError("Book Analysis tests must not open network connections")
    monkeypatch.setattr(llm_provider_service.request, "urlopen", fail_network)
    state = book_analysis_state_service.build_book_analysis_profile_state(
        {"llm_profiles": [_profile()], "default_book_analysis_profile_id": "profile-a"}
    )
    assert state["selected_profile_id"] == "profile-a"
```

- [ ] **Step 2: Run and record the expected red if the guard is not yet satisfied**

Run: `cd 05_Software/AudioMancer; uv run pytest -q tests/test_book_analysis_service.py tests/test_book_analysis_document_service.py tests/test_book_analysis_budget_service.py tests/test_book_analysis_state_service.py tests/test_book_analysis_page.py tests/test_book_analysis_ui_controller.py`

Expected before the final fixture cleanup: any unpatched provider path fails with the guard assertion; otherwise record the red from the first missing hermetic fixture. Do not contact a live service.

- [ ] **Step 3: Centralize deterministic provider fixtures and remove environment dependencies**

All generated replies come from in-process scripted dictionaries. Tests must not read `OPENAI_API_KEY`, other credential variables, runtime `settings.json`, or local server state. Patch `urlopen` to fail in the Book Analysis test fixture unless a provider-request-shape test installs its own fake response.

- [ ] **Step 4: Update knowledge and help in both languages**

Document optional placement, Analyze/Reset behavior, stale preservation, exact resume matching, 16K/fraction rules, profile reasoning modes, status/progress, report layers, and live-validation ownership. Add the intended/final component diagram to `Book_Analysis.md`; update existing knowledge pages to name the new supporting boundary. Add matching English and Romanian user-guide navigation/section text without claiming a screenshot or live model test.

- [ ] **Step 5: Update the changelog without assigning a version**

Under `## [Unreleased]`, describe the optional resumable layered Book Analysis page, model-agnostic profile reasoning controls, conservative context budgeting, stale-report preservation, and hermetic automated validation. Do not change project version fields.

- [ ] **Step 6: Run the complete focused set, static checks, and AEGIS build gates**

Run from `05_Software/AudioMancer`:

```powershell
uv run pytest -q tests/test_book_analysis_budget_service.py tests/test_book_analysis_document_service.py tests/test_book_analysis_service.py tests/test_book_analysis_state_service.py tests/test_book_analysis_page.py tests/test_book_analysis_ui_controller.py tests/test_settings_service.py tests/test_llm_provider_service.py tests/test_ai_settings_page.py tests/test_ai_settings_ui_controller.py tests/test_operation_runtime_service.py tests/test_project_workspace_service.py tests/test_main_window_project_flow.py tests/test_main_window_ai_profiles.py
uv run ruff check src/audiomancer tests
uv run python -m compileall -q src/audiomancer
```

Expected: all pass. Link the hermetic tests, activate `REQ-TEST-5a3dcf8d`, run `python .agentic/aegis.py test --impacted --base HEAD`, then `python .agentic/aegis.py evolution --task TASK-022bb563` and `python .agentic/aegis.py check`. Review every path and record any accepted warning as a deviation. Do not commit.

---

### Task 9: Validation and handoff without live AI

**Files:**
- Modify: `.agentic/tasks/TASK-022bb563.md`
- Modify: requirement links/status only if validation reveals omissions

**Interfaces:**
- Produces validation evidence and a user handoff; no product interface changes.

- [ ] **Step 1: Run the task-scoped static AEGIS validation**

Use the validate-stage command from `.agentic/steps/5_validate.md`. Record exact command, exit code, warnings, and whether they are task-owned.

- [ ] **Step 2: Run the full pytest suite once with a 60-minute bound**

Run: `cd 05_Software/AudioMancer; uv run pytest`

Allow at least 60 minutes. If a launcher returns early, check whether the original pytest process is still active before considering another run. Do not start a duplicate suite. Expected: all tests pass; no API keys or live AI services are used.

- [ ] **Step 3: Re-run changed-file Ruff/compile checks after any validation repair**

Run: `cd 05_Software/AudioMancer; uv run ruff check <changed Python files>; uv run python -m compileall -q src/audiomancer`

Expected: exit 0.

- [ ] **Step 4: Inspect the final diff and preserve user-owned changes**

Confirm only task files plus the pre-existing planning changes are present. Verify `settings.json` changed only by the two new schema fields, no credential value changed or was introduced, no version changed, and no branch/commit/push occurred.

- [ ] **Step 5: Report the validation boundary honestly**

State automated results separately from live acceptance. Explicitly say that no online API, LM Studio/Ollama model, API key, or live generation was used and that the user will validate live behavior by starting AudioMancer.
