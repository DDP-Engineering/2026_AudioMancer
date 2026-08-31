<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Standalone Book Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Repository AEGIS checkpoints and Git
> authority remain binding; a request to continue does not authorize a commit.

**Goal:** Add a standalone, resumable Book Analysis page immediately after Text
Chunking that uses local or online AI to create a user-facing book overview from
canonical chunks while remaining independent of Translation, Character
Discovery, Narrator Voice, and every downstream operation.

**Architecture:** The operation reads only the strict `chunks_text.json`
document, fingerprints the exact ordered chunk content, analyzes dynamically
budgeted windows, recursively consolidates summaries when necessary, and
atomically completes one strict `book_analysis.json` document. A dedicated
PySide6 page, state service, and controller expose analysis, refresh, reset,
progress, cancellation, recovery, and the completed report through the existing
AudioMancer patterns.

**Tech Stack:** Python 3.12, PySide6, JSON project artifacts, existing
OpenAI-compatible/LM Studio/Ollama AI provider layer, `uv`, `pytest`,
`pytest-qt`, repository-installed AEGIS.

**Spec:** `00_Planning/Book_Analysis_Agentic_Implementation_Plan.md` — the
Design Contract below is the approved feature specification implemented by the
task plan in this same document.

## Global Constraints

- Book Analysis appears after Text Chunking and before AI Translation.
- Book Analysis is a supporting operation, not a canonical stage milestone:
  `PROJECT_WORKFLOW_STAGES`, `WORKFLOW_OPERATION_ORDER`, and
  `OPERATION_STAGE_BY_KIND` retain their current pipeline meaning.
- The only product-data input is the completed canonical `chunks_text.json`.
- Book Analysis does not read translated text, character data, narrator data,
  voice assignments, Speech Blocks, Audio Blocks, or Audio Assembly artifacts.
- No downstream operation reads `book_analysis.json`; the artifact informs the
  operator only.
- Translation, character edits, narrator changes, voice changes, and downstream
  resets do not invalidate Book Analysis.
- Source replacement, Cleanup reset, Chunking reset, or exact chunk-content
  changes invalidate Book Analysis through existing upstream reset semantics or
  the stored chunk-content fingerprint.
- Minimum supported AI context window: exactly `16384` tokens.
- Recommended AI context window: `32768` tokens or more.
- Profiles below `16384` tokens are rejected before an AI request is sent.
- Request sizing is derived from the selected profile; model names are never
  used as compatibility gates.
- A request never splits a canonical chunk. A single chunk that exceeds the
  safe text budget fails with an operator-readable instruction to split that
  chunk in Text Chunking.
- Completed chunk windows and consolidation rounds are checkpointed so cancel,
  shutdown, transport failure, or malformed model output can resume safely.
- Refresh never destroys the last completed report before its replacement has
  passed strict validation and been written atomically.
- Window analysis and consolidation use compact strict JSON with chunk-ID
  provenance; final synthesis never receives the complete source book.
- English and Romanian UI/localization/help coverage are required.
- Follow `01_Documentation/Code_Style.md`; use small functional services and no
  speculative framework or compatibility layer.
- Record every user-visible delivery change under `## [Unreleased]` in
  `CHANGELOG.md`; do not assign a release version unless separately requested.
- Do not commit, push, create a branch, or create a PR without explicit user
  authority. AEGIS `deliver` still requires its normal approval checkpoint.

---

## Design Contract

### User workflow

The visible page order becomes:

`Home / Project -> Text Cleanup -> Text Chunking -> Book Analysis -> AI Translation -> Characters -> Narrator Voice -> Character Voices -> Speech Blocks -> Audio Blocks -> Audio Assembly`

Book Analysis is a first-class supporting operation with status, progress,
cancellation, resume, refresh, and reset. It is not a hard prerequisite for
later operations: the operator may proceed without running it because no
downstream service consumes its output. Its absence or failure never makes an
otherwise valid Translation-or-later project non-contiguous.

### User-facing report

The completed report contains these exact sections:

1. Book at a Glance: book type, genres, subjects, settings, and time periods.
2. Overview: spoiler-light summary and an explicitly labelled detailed summary.
3. Narrative and Style: perspective, structure, tone, pacing, diction, and
   emotional range.
4. Characters: narratively important main and supporting characters, roles,
   relationships, evidence chunk IDs, and confidence.
5. Themes: recurring themes and supported uncertainties.
6. Audiobook Guidance: narrator qualities, voice-differentiation priorities,
   dialogue density, pronunciation candidates, and performance risks.

Book Analysis characters represent narrative importance. They are not the
speaking-character inventory later produced by Character Discovery and must not
be copied into `characters.json`.

### Persistence contract

`book_analysis.json` is the sole authoritative artifact. Its exact root fields
are:

```json
{
  "status": "not_started|running|cancelled|failed|completed",
  "source": {
    "kind": "canonical_chunks",
    "fingerprint": "sha256:<64 lowercase hex characters>",
    "chunk_count": 0
  },
  "report_language": "en|ro",
  "additional_instructions": "",
  "ai_profile_id_last_used": "",
  "token_usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "usage_available": false
  },
  "budget_metadata": {},
  "checkpoint": null,
  "failure": null,
  "analysis": null
}
```

The completed `analysis` object has exact fields:

```json
{
  "book_type": "",
  "genres": [],
  "subjects": [],
  "spoiler_light_summary": "",
  "detailed_summary": "",
  "settings": [],
  "time_periods": [],
  "themes": [],
  "tone": [],
  "pacing": [],
  "diction": [],
  "emotional_range": [],
  "narrative_perspective": [],
  "narrative_structure": [],
  "main_characters": [],
  "supporting_characters": [],
  "audiobook_guidance": {
    "narrator_qualities": [],
    "voice_differentiation_priorities": [],
    "dialogue_density": "",
    "pronunciation_candidates": [],
    "performance_risks": []
  },
  "uncertainties": []
}
```

Each character object contains exactly `name`, `aliases`, `role`,
`relationships`, `importance`, `evidence_chunk_ids`, and `confidence`.
Confidence is one of `high`, `medium`, or `low`. Every reported character must
have at least one valid source chunk ID.

### Context-budget contract

The operation uses phase-specific output caps and a dynamic text budget:

| Phase | Maximum output tokens | Maximum context fraction for supplied text |
|---|---:|---:|
| Window analysis | 1536 | 0.50 |
| Consolidation | 2048 | 0.50 |
| Final synthesis | 4096 | 0.40 |

Every phase reserves the larger of `1024` tokens or 10% of the configured
context as a safety margin. Prompt-shell tokens are estimated through the
existing `ai_budget_service`. At a `16384` context, ordinary source windows
therefore target at most approximately 8192 estimated text tokens and can be
smaller when the prompt or configured output reservation requires it.

Window grouping preserves whole chunks. Adjacent windows share at most one
complete overlap chunk when it fits safely. Consolidation deduplicates facts by
normalized value and evidence chunk ID.

When all window summaries do not fit the consolidation budget, merge them in
ordered batches. Repeat consolidation until the remaining summaries fit one
final synthesis request. This makes analysis length-bound by request count, not
by model context.

### Failure and refresh contract

- Validate every AI response before checkpointing it.
- Use the existing provider retry behavior, then allow one operation-level
  contract-correction request containing the validation error and the invalid
  response, both bounded inside the same phase budget.
- If correction also fails, persist `failed` with `failure.phase` and
  `failure.message` and keep the resumable checkpoint.
- Cancel persists `cancelled` without losing accepted summaries.
- Resume requires the same exact source fingerprint, report language,
  additional instructions, AI profile, and budget-driving model settings.
- Changed resume inputs start a fresh candidate run only after user
  confirmation; a previously completed document remains available until the
  new candidate completes.
- A non-completed refresh document may retain the previous validated `analysis`
  object for display while `status`, `checkpoint`, and `failure` describe the
  new candidate attempt.
- A completed replacement is written atomically. No partially synthesized
  report is displayed as completed.

---

## Execution Protocol

Before Task 1, the implementing agent must:

1. Read `AGENTS.md`, `.agentic/AGENTS.md`, `.agentic/PROJECT.md`,
   `01_Documentation/Code_Style.md`, and this complete plan.
2. Run `git status --short --branch` and preserve all pre-existing work.
3. Run `python .agentic/aegis.py status`; do not resume either unrelated
   VoiceWeaver task currently recorded at `deliver`.
4. Create a new AEGIS task named `Add standalone Book Analysis workflow` and
   follow the full path: frame, specify, design, build, validate, deliver.
5. At the frame checkpoint, present the scope and generated requirements to the
   user. Do not begin implementation until the user approves that checkpoint.
6. Create requirements covering the functional operation, 16K local-model
   budget, strict persistence/recovery, page UX, localization, and independence
   from downstream operations. Cite their generated IDs in the AEGIS design.
7. Treat this plan as design input, not as permission to commit or push.

The plan below begins after the AEGIS frame checkpoint has been approved.

---

### Task 1: Register the supporting operation and reset boundary

**Files:**

- Modify: `05_Software/AudioMancer/src/audiomancer/config.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
- Modify: `05_Software/AudioMancer/tests/test_workflow_order_consistency.py`
- Modify: `05_Software/AudioMancer/tests/test_operation_runtime_service.py`
- Modify: `05_Software/AudioMancer/tests/test_project_workspace_service.py`

**Interfaces:**

- Consumes: Existing canonical stage/order/reset mappings.
- Produces: `config.BOOK_ANALYSIS_DOCUMENT_FILE_NAME`, supporting operation kind
  `book_analysis`, manifest summary support without a workflow stage, and reset
  ownership of `book_analysis.json` plus its AI logs.

- [ ] **Step 1: Write failing workflow-order tests**

```python
def test_book_analysis_is_supporting_not_a_stage_milestone() -> None:
    assert "book_analysis" in config.SUPPORTING_OPERATION_KINDS
    assert "book_analysis" in config.SUPPORTED_OPERATION_KINDS
    assert "book_analysis" not in config.WORKFLOW_OPERATION_ORDER
    assert "book_analysis" not in config.OPERATION_STAGE_BY_KIND
    assert "book_analysis_ready" not in config.PROJECT_WORKFLOW_STAGES
```

- [ ] **Step 2: Write failing reset-isolation tests**

```python
def test_translation_reset_preserves_book_analysis(project_root: Path) -> None:
    analysis_path = project_root / config.BOOK_ANALYSIS_DOCUMENT_FILE_NAME
    analysis_path.write_text('{"sentinel": true}', encoding="utf-8")

    operation_runtime_service.reset_operation_data(project_root, "translation")

    assert analysis_path.is_file()


def test_chunking_reset_removes_book_analysis(project_root: Path) -> None:
    analysis_path = project_root / config.BOOK_ANALYSIS_DOCUMENT_FILE_NAME
    analysis_path.write_text('{"sentinel": true}', encoding="utf-8")

    operation_runtime_service.reset_operation_data(project_root, "chunking")

    assert not analysis_path.exists()
```

- [ ] **Step 3: Run the focused tests and confirm the intended failures**

Run from `05_Software/AudioMancer`:

```powershell
uv run pytest tests/test_workflow_order_consistency.py tests/test_operation_runtime_service.py tests/test_project_workspace_service.py -q
```

Expected: new assertions fail because `book_analysis` is not registered.

- [ ] **Step 4: Add the minimum configuration and reset mappings**

Add these configuration values in the matching existing sections without
altering the canonical pipeline order or stage list:

```python
BOOK_ANALYSIS_DOCUMENT_FILE_NAME = "book_analysis.json"
SUPPORTING_OPERATION_KINDS = ("book_analysis",)
SUPPORTED_OPERATION_KINDS = frozenset((*WORKFLOW_OPERATION_ORDER, *SUPPORTING_OPERATION_KINDS))
```

Give `book_analysis` a default manifest summary and add its document and AI-log
ownership to `operation_runtime_service`. A direct Book Analysis reset clears
only Book Analysis. Any reset whose resolved canonical operation set includes
Chunking also clears Book Analysis. Translation and later resets preserve it.

Update `_allowed_operations_for_stage` so the supporting summary is permitted
at `text_chunking_ready` and every later stage but reset at earlier stages. Add
`reset_supporting_operation_summary(project_root, "book_analysis")` to clear its
manifest summary without changing `current_stage`.

- [ ] **Step 5: Run the focused tests**

```powershell
uv run pytest tests/test_workflow_order_consistency.py tests/test_operation_runtime_service.py tests/test_project_workspace_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Review without committing**

Run `git diff --check` and record the focused test result in the AEGIS journal.
Do not commit unless the user has separately granted Git authority.

---

### Task 2: Implement the strict Book Analysis document contract

**Files:**

- Create: `05_Software/AudioMancer/src/audiomancer/services/book_analysis_document_service.py`
- Create: `05_Software/AudioMancer/tests/book_analysis_test_support.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_document_service.py`

**Interfaces:**

- Consumes: `chunking_document_service.load_chunks`,
  `persistence_service.write_json_atomic`, and
  `config.BOOK_ANALYSIS_DOCUMENT_FILE_NAME`.
- Produces:
  `chunk_content_fingerprint(chunks: list[dict[str, object]]) -> str`,
  `load_book_analysis_document(project_root: str | Path) -> dict[str, object] | None`,
  `write_book_analysis_document(project_root: str | Path, document: object) -> Path`,
  `build_initial_document(...) -> dict[str, object]`, and
  `operation_summary(document: dict[str, object]) -> dict[str, object]`.
- Test support produces the exact shared helpers used by later tasks:
  `ai_profile`, `completed_book_analysis_document`, `completed_manifest`,
  `make_chunks`, `write_completed_chunks`, `long_chunk_fixture`,
  `very_long_chunk_fixture`, `run_analysis`, `install_window_response_stub`,
  `install_cancel_after_first_window_stub`, `install_success_stub`,
  `install_hierarchical_success_stub`, `install_final_synthesis_failure`, and
  `write_completed_book_analysis` plus
  `write_completed_translation_and_downstream_fixture`.

- [ ] **Step 1: Write failing fingerprint and round-trip tests**

```python
def test_chunk_content_fingerprint_changes_for_manual_text_edit() -> None:
    chunks = [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Alpha"}]
    original = book_analysis_document_service.chunk_content_fingerprint(chunks)

    chunks[0]["text"] = "Alpha changed"

    assert book_analysis_document_service.chunk_content_fingerprint(chunks) != original


def test_completed_document_round_trips_exact_contract(tmp_path: Path) -> None:
    document = completed_book_analysis_document()

    path = book_analysis_document_service.write_book_analysis_document(tmp_path, document)

    assert path.name == "book_analysis.json"
    assert book_analysis_document_service.load_book_analysis_document(tmp_path) == document
```

- [ ] **Step 2: Write failing rejection tests**

Cover an unknown root field, an invalid fingerprint, `completed` with null
analysis, a character without evidence chunk IDs, an unsupported confidence,
an invalid report language, negative token counts, and checkpoint/phase mismatch.

```python
def test_completed_character_requires_valid_evidence_chunk_id(tmp_path: Path) -> None:
    document = completed_book_analysis_document()
    document["analysis"]["main_characters"][0]["evidence_chunk_ids"] = []

    with pytest.raises(BookAnalysisDocumentError, match="evidence"):
        book_analysis_document_service.write_book_analysis_document(tmp_path, document)
```

- [ ] **Step 3: Run the document tests and confirm failure**

```powershell
uv run pytest tests/test_book_analysis_document_service.py -q
```

Expected: collection fails because the new service does not exist.

- [ ] **Step 4: Implement the exact validator and atomic persistence boundary**

Use exact field sets from the Design Contract. Hash a canonical UTF-8 JSON
encoding of ordered `chunk_id`, `sequence_index`, and `text` values:

```python
def chunk_content_fingerprint(chunks: list[dict[str, object]]) -> str:
    canonical_chunks = [
        {
            "chunk_id": str(chunk.get("chunk_id", "")),
            "sequence_index": int(chunk.get("sequence_index", 0)),
            "text": str(chunk.get("text", "")),
        }
        for chunk in chunks
    ]
    encoded = json.dumps(
        canonical_chunks,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"
```

Return defensive copies from all public loaders/builders. Do not silently
repair malformed current-format documents.

Implement `book_analysis_test_support.py` with valid complete payload builders,
project/chunk writers, deterministic local AI-profile builders, and the named
provider stubs. Every stub records phase, window/level identity, rendered
prompts, and calls so later tests can assert request count and resume behavior
without contacting a real model.

- [ ] **Step 5: Run the document tests**

```powershell
uv run pytest tests/test_book_analysis_document_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Review without committing**

Run `git diff --check`; record evidence in the AEGIS journal and retain the
uncommitted candidate.

---

### Task 3: Build 16K-safe window and consolidation budgeting

**Files:**

- Create: `05_Software/AudioMancer/src/audiomancer/services/book_analysis_budget_service.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_budget_service.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/config.py`

**Interfaces:**

- Consumes: `ai_budget_service.context_budget_metadata` and exact canonical
  chunk payloads.
- Produces:
  `validate_context_window(ai_profile_payload: dict[str, object]) -> int`,
  `build_phase_budget(ai_profile_payload, phase, prompt_text) -> dict[str, int]`,
  `build_chunk_windows(chunks, text_budget_tokens) -> list[list[dict[str, object]]]`,
  and `build_summary_batches(summaries, text_budget_tokens) -> list[list[dict[str, object]]]`.

- [ ] **Step 1: Write failing minimum-context tests**

```python
def test_book_analysis_accepts_exactly_16k_context(ai_profile: dict[str, object]) -> None:
    ai_profile["context_window"] = 16384
    assert book_analysis_budget_service.validate_context_window(ai_profile) == 16384


def test_book_analysis_rejects_context_below_16k(ai_profile: dict[str, object]) -> None:
    ai_profile["context_window"] = 16383
    with pytest.raises(ValueError, match="at least 16,384"):
        book_analysis_budget_service.validate_context_window(ai_profile)
```

- [ ] **Step 2: Write failing whole-chunk and recursive-batch tests**

```python
def test_window_builder_never_splits_a_chunk() -> None:
    chunks = make_chunks(token_estimates=[3000, 3000, 3000])
    windows = book_analysis_budget_service.build_chunk_windows(chunks, 6500)
    assert [[item["chunk_id"] for item in window] for window in windows] == [
        ["chunk-0001", "chunk-0002"],
        ["chunk-0002", "chunk-0003"],
    ]


def test_oversized_single_chunk_is_rejected() -> None:
    chunks = make_chunks(token_estimates=[9000])
    with pytest.raises(ValueError, match="split chunk-0001"):
        book_analysis_budget_service.build_chunk_windows(chunks, 8192)
```

- [ ] **Step 3: Run the budget tests and confirm failure**

```powershell
uv run pytest tests/test_book_analysis_budget_service.py -q
```

- [ ] **Step 4: Implement phase budgets and ordered grouping**

Add exact constants:

```python
BOOK_ANALYSIS_MIN_CONTEXT_WINDOW = 16384
BOOK_ANALYSIS_RECOMMENDED_CONTEXT_WINDOW = 32768
BOOK_ANALYSIS_MIN_TEXT_BUDGET_TOKENS = 2048
BOOK_ANALYSIS_MIN_SAFETY_MARGIN_TOKENS = 1024
BOOK_ANALYSIS_SAFETY_MARGIN_CONTEXT_FRACTION = 0.10
```

Use phase maps for the output caps and text fractions in the Design Contract.
Estimate the complete rendered block—including IDs and delimiters—not only raw
chunk text. Include one previous complete chunk as overlap only when both chunks
remain under budget; otherwise begin the new window without overlap.

- [ ] **Step 5: Run the budget and shared-budget tests**

```powershell
uv run pytest tests/test_book_analysis_budget_service.py tests/test_ai_budget_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Review without committing**

Run `git diff --check` and record the observed tests in the journal.

---

### Task 4: Implement resumable window analysis

**Files:**

- Create: `05_Software/AudioMancer/src/audiomancer/services/book_analysis_service.py`
- Create: `05_Software/AudioMancer/prompts/book_analysis_system.txt`
- Create: `05_Software/AudioMancer/prompts/book_analysis_window_user.txt`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_service.py`
- Modify: `05_Software/AudioMancer/tests/test_prompt_template_service.py`

**Interfaces:**

- Consumes: Book Analysis document/budget services, `llm_provider_service.chat_json`,
  `prompt_template_service`, `token_usage_service`, and operation cancellation/progress helpers.
- Produces:
  `analyze_book(project_root, manifest, ai_profile_payload, report_language,
  progress_callback=None, cancel_requested=None, additional_instructions="") -> dict[str, object]`.
  Task 4 implements the window-analysis portion and leaves the checkpoint at
  `phase="consolidation"`; Task 5 completes consolidation and synthesis.

- [ ] **Step 1: Write failing source and independence tests**

```python
def test_analysis_reads_only_canonical_chunks(project_root: Path, monkeypatch) -> None:
    write_completed_chunks(project_root, ["Original book text."])
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        '{"sentinel": "must not be read"}', encoding="utf-8"
    )
    observed_prompts = install_window_response_stub(monkeypatch)

    book_analysis_service.analyze_book(
        project_root,
        project_workspace_service.load_manifest(project_root),
        ai_profile(context_window=16384),
        "en",
    )

    assert "Original book text." in observed_prompts[0]
    assert "must not be read" not in observed_prompts[0]
```

- [ ] **Step 2: Write failing checkpoint/cancel/resume tests**

```python
def test_cancel_after_first_window_resumes_without_repeating_it(project_root: Path, monkeypatch) -> None:
    write_completed_chunks(project_root, long_chunk_fixture())
    calls = install_cancel_after_first_window_stub(monkeypatch)

    with pytest.raises(OperationCancelledError):
        run_analysis(project_root)

    cancelled = book_analysis_document_service.load_book_analysis_document(project_root)
    assert cancelled["status"] == "cancelled"
    assert cancelled["checkpoint"]["next_window_index"] == 1

    install_success_stub(monkeypatch, calls)
    run_analysis(project_root)
    assert calls.count("window-1") == 1
```

- [ ] **Step 3: Write failing malformed-response correction test**

Assert one invalid response triggers exactly one correction request and that a
second invalid result persists `failed` with the window checkpoint intact.

- [ ] **Step 4: Run the focused tests and confirm failure**

```powershell
uv run pytest tests/test_book_analysis_service.py tests/test_prompt_template_service.py -q
```

- [ ] **Step 5: Implement window prompting, validation, and checkpointing**

The window response schema must be compact and exact:

```json
{
  "range_start_chunk_id": "",
  "range_end_chunk_id": "",
  "summary": "",
  "events": [],
  "characters": [],
  "settings": [],
  "time_periods": [],
  "themes": [],
  "style": {
    "tone": [],
    "pacing": [],
    "diction": [],
    "emotional_range": []
  },
  "narrative_perspective": [],
  "narrative_structure": [],
  "audiobook_observations": [],
  "uncertainties": [],
  "evidence_chunk_ids": []
}
```

Use short phrases and compact factual summaries. Validate that every evidence
ID belongs to the supplied window. Persist a validated observation before
emitting progress. The prompt must explicitly distinguish narratively important
characters from speaking-character discovery and prohibit invented evidence.

For every provider call, copy the selected profile and cap its
`max_output_tokens` to the phase value from the Design Contract; do not mutate
the saved settings profile. Bound a contract-correction prompt by truncating the
invalid response to the remaining phase text budget before calling the model,
so malformed local output cannot push the correction request past context.

- [ ] **Step 6: Run the focused tests**

```powershell
uv run pytest tests/test_book_analysis_service.py tests/test_prompt_template_service.py -q
```

Expected: window, correction, cancellation, resume, token usage, and independence tests PASS.

- [ ] **Step 7: Review without committing**

Run `git diff --check` and record the evidence in the AEGIS journal.

---

### Task 5: Implement recursive consolidation and final synthesis

**Files:**

- Modify: `05_Software/AudioMancer/src/audiomancer/services/book_analysis_service.py`
- Create: `05_Software/AudioMancer/prompts/book_analysis_consolidation_user.txt`
- Create: `05_Software/AudioMancer/prompts/book_analysis_synthesis_user.txt`
- Modify: `05_Software/AudioMancer/tests/test_book_analysis_service.py`

**Interfaces:**

- Consumes: Validated window summaries and phase budgets from Tasks 3–4.
- Produces: A completed strict `book_analysis.json`, a compact operation summary,
  and hierarchical consolidation that supports books of unbounded window count.

- [ ] **Step 1: Write a failing multi-level-consolidation test**

```python
def test_long_book_uses_multiple_consolidation_levels(project_root: Path, monkeypatch) -> None:
    write_completed_chunks(project_root, very_long_chunk_fixture())
    calls = install_hierarchical_success_stub(monkeypatch)

    result = run_analysis(project_root, context_window=16384)

    consolidation_levels = [call["level"] for call in calls if call["phase"] == "consolidation"]
    assert consolidation_levels == [1, 1, 1, 2]
    assert result["status"] == "completed"
    assert result["analysis"]["book_type"] == "fiction"
```

- [ ] **Step 2: Write failing final-contract and atomic-refresh tests**

```python
def test_failed_refresh_preserves_previous_completed_report(project_root: Path, monkeypatch) -> None:
    previous = write_completed_book_analysis(project_root, summary="Previous valid report")
    install_final_synthesis_failure(monkeypatch)

    with pytest.raises(ValueError):
        run_analysis(project_root, force_refresh=True)

    failed = book_analysis_document_service.load_book_analysis_document(project_root)
    assert failed["status"] == "failed"
    assert failed["analysis"] == previous["analysis"]
```

- [ ] **Step 3: Run the service test and confirm failure**

```powershell
uv run pytest tests/test_book_analysis_service.py -q
```

- [ ] **Step 4: Implement recursive ordered consolidation**

Consolidation outputs the same compact summary schema as window analysis plus a
`source_summary_ids` array. Assign stable IDs such as `summary-L01-0001`.
Checkpoint after each accepted batch and after each completed level. Deduplicate
strings by normalized casefolded whitespace while unioning ordered evidence IDs.
Never deduplicate character identities solely by matching a name; preserve
ambiguous identities and carry uncertainty to final synthesis.

- [ ] **Step 5: Implement strict final synthesis**

Render only the fully consolidated summaries into the final prompt. Require the
exact completed analysis schema in the Design Contract. Validate every reported
character evidence ID against the original chunk-ID set. Write the completed
document atomically, then synchronize the supporting manifest operation summary
with `current_stage=None`; Book Analysis completion never promotes or regresses
the canonical workflow stage.

- [ ] **Step 6: Run Book Analysis service tests**

```powershell
uv run pytest tests/test_book_analysis_service.py tests/test_book_analysis_document_service.py tests/test_book_analysis_budget_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Review without committing**

Run `git diff --check`; record consolidation levels, 16K coverage, and atomic
refresh evidence in the journal.

---

### Task 6: Add Book Analysis settings and page-state presentation

**Files:**

- Create: `05_Software/AudioMancer/src/audiomancer/services/book_analysis_state_service.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_state_service.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/settings_service.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/ui/pages/ai_settings_page.py`
- Modify: `05_Software/AudioMancer/tests/test_settings_service.py`
- Modify: `05_Software/AudioMancer/tests/test_ai_settings_page.py`
- Modify: `05_Software/AudioMancer/tests/test_ai_state_note_service.py`

**Interfaces:**

- Consumes: Enabled AI profiles, `default_book_analysis_profile_id`, current
  chunks, and the strict Book Analysis document.
- Produces:
  `build_book_analysis_profile_state(settings_payload, selected_profile_id=None)`,
  `build_book_analysis_state(project_root, manifest, language, settings_payload,
  selected_profile_id=None)`, and the default-profile selector in AI Settings.

- [ ] **Step 1: Write failing profile/default tests**

```python
def test_book_analysis_profile_state_uses_configured_default(settings_payload) -> None:
    settings_payload["default_book_analysis_profile_id"] = "profile_b"
    state = book_analysis_state_service.build_book_analysis_profile_state(settings_payload)
    assert state["selected_profile_id"] == "profile_b"
```

- [ ] **Step 2: Write failing state/staleness tests**

Cover no project, missing chunks, valid completion, cancelled resume, failed
resume, invalid document recovery message, context below 16K, and changed exact
chunk fingerprint. Later Translation/Character/Narrator artifacts must not alter
the resulting Book Analysis state.

- [ ] **Step 3: Run state and settings tests and confirm failure**

```powershell
uv run pytest tests/test_book_analysis_state_service.py tests/test_settings_service.py tests/test_ai_settings_page.py tests/test_ai_state_note_service.py -q
```

- [ ] **Step 4: Implement state projection and setting validation**

Add `default_book_analysis_profile_id` beside the existing per-operation default
AI-profile settings. Use the common profile-state note service. State projection
must never mutate project files; it reports `not_started`, `running`, `cancelled`,
`failed`, `completed`, `stale`, or `invalid` as presentation state and returns
the last completed analysis when one exists.

- [ ] **Step 5: Run state and settings tests**

```powershell
uv run pytest tests/test_book_analysis_state_service.py tests/test_settings_service.py tests/test_ai_settings_page.py tests/test_ai_state_note_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Review without committing**

Run `git diff --check`; update journal evidence.

---

### Task 7: Build the Book Analysis page

**Files:**

- Create: `05_Software/AudioMancer/src/audiomancer/ui/pages/book_analysis_page.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_page.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/ui/pages/__init__.py`

**Interfaces:**

- Consumes: Profile state and analysis presentation dictionaries from Task 6.
- Produces: `BookAnalysisPage`, signal
  `analyze_requested(str, str, str)`, signal `reset_requested()`,
  `set_ai_profiles(...)`, `set_book_analysis_state(...)`, and
  `operation_status_text() -> str`.

- [ ] **Step 1: Write failing page-contract tests**

```python
def test_book_analysis_page_emits_selected_request(qtbot) -> None:
    page = BookAnalysisPage()
    qtbot.addWidget(page)
    page.set_ai_profiles(
        profiles=[{"id": "local_qwen", "display_name": "Local Qwen"}],
        selected_profile_id="local_qwen",
        enabled=True,
        note="",
    )
    page.set_report_language("ro")
    page.set_additional_instructions("Emphasize audiobook performance.")

    with qtbot.waitSignal(page.analyze_requested) as emitted:
        page.analyze_button().click()

    assert emitted.args == ["local_qwen", "ro", "Emphasize audiobook performance."]
```

- [ ] **Step 2: Write failing rendering and accessibility tests**

Verify every Design Contract section renders, detailed summary is explicitly
labelled for spoilers, main/supporting characters remain separate, evidence IDs
are visible, long text is selectable/read-only, Tab order reaches controls, and
large UI/text font settings do not clip the action bar.

- [ ] **Step 3: Run page tests and confirm failure**

```powershell
uv run pytest tests/test_book_analysis_page.py -q
```

- [ ] **Step 4: Implement the page with existing Qt patterns**

Use a compact top action row and read-only section widgets. Do not put the full
report in a modal popup. Include:

```text
AI Profile | Report Language | Additional Instructions | Analyze/Resume/Refresh | Reset
```

Render analysis from structured fields, not preformatted HTML supplied by the
model. Escape all model text through normal Qt text widgets. Preserve report
selection and scrolling when state refreshes without a source change.

- [ ] **Step 5: Run page tests**

```powershell
uv run pytest tests/test_book_analysis_page.py tests/test_ui_page_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Review without committing**

Run `git diff --check`; record UI-test evidence.

---

### Task 8: Wire the controller, operation runner, and main window

**Files:**

- Create: `05_Software/AudioMancer/src/audiomancer/ui/controllers/book_analysis_ui_controller.py`
- Create: `05_Software/AudioMancer/tests/test_book_analysis_ui_controller.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/ui/controllers/__init__.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- Modify: `05_Software/AudioMancer/tests/test_main_window_ai_profiles.py`
- Modify: `05_Software/AudioMancer/tests/test_main_window_project_flow.py`
- Modify: `05_Software/AudioMancer/tests/test_navigation_sidebar.py`
- Modify: `05_Software/AudioMancer/tests/test_operation_status_button.py`
- Modify: `05_Software/AudioMancer/tests/test_controller_cancellation_wiring.py`

**Interfaces:**

- Consumes: `BookAnalysisPage`, Task 4–5 analysis callable, Task 6 state
  builder, existing operation runner, confirmations, manifest synchronization,
  and workflow impact/reset services.
- Produces: Start/resume/refresh/reset handlers and page placement between
  `text_chunking` and `ai_translation`.

- [ ] **Step 1: Write failing navigation and operation-map tests**

```python
def test_book_analysis_page_follows_text_chunking(main_window) -> None:
    page_ids = [page_id for page_id, _label in main_window.PAGE_ORDER]
    assert page_ids.index("book_analysis") == page_ids.index("text_chunking") + 1
    assert main_window.PAGE_OPERATION_KIND["book_analysis"] == "book_analysis"
```

- [ ] **Step 2: Write failing controller tests**

Cover missing project, missing/incomplete chunks, invalid or disabled profile,
profile context `16383`, exact `16384` acceptance, paid-token confirmation,
start, resume, refresh confirmation, cancellation, failure, completion, manifest
sync, reset confirmation, and preservation of Translation/downstream data when
only Book Analysis is reset.

- [ ] **Step 3: Run controller/window tests and confirm failure**

```powershell
uv run pytest tests/test_book_analysis_ui_controller.py tests/test_main_window_ai_profiles.py tests/test_main_window_project_flow.py tests/test_navigation_sidebar.py tests/test_operation_status_button.py tests/test_controller_cancellation_wiring.py -q
```

- [ ] **Step 4: Implement controller handlers**

Follow existing controller boundaries. The worker callable returns the completed
document; completion synchronizes its derived supporting-operation summary and
refreshes Home plus the current page. Reset calls the supporting-operation reset
path, clears only Book Analysis artifacts/logs and its manifest summary, and
leaves `current_stage`, Translation, Characters, voices, speech, audio, and
assembly untouched.

The confirmation text must state that local analysis can take a long time,
report the configured model/context, and warn about paid usage only when the
selected provider is online.

- [ ] **Step 5: Wire the main window**

Insert the page, state refresh branch, operation status mapping, operation-state
initialization, signals, and sidebar label. Do not add a Home popup in this
delivery; the dedicated page is the only report surface.

- [ ] **Step 6: Run controller/window tests**

```powershell
uv run pytest tests/test_book_analysis_ui_controller.py tests/test_main_window_ai_profiles.py tests/test_main_window_project_flow.py tests/test_navigation_sidebar.py tests/test_operation_status_button.py tests/test_controller_cancellation_wiring.py -q
```

Expected: PASS.

- [ ] **Step 7: Review without committing**

Run `git diff --check`; record evidence in the AEGIS journal.

---

### Task 9: Complete localization and project recovery

**Files:**

- Modify: `05_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
- Modify: `05_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
- Modify: `05_Software/AudioMancer/tests/test_localization_parity.py`
- Modify: `05_Software/AudioMancer/tests/test_ui_localization_coverage.py`
- Modify: `05_Software/AudioMancer/tests/test_project_workspace_service.py`
- Modify: `05_Software/AudioMancer/tests/test_project_stage_consistency.py`

**Interfaces:**

- Consumes: Completed/invalid Book Analysis documents and manifest operation summaries.
- Produces: English/Romanian strings, supporting-operation validation/healing
  evidence, and corruption recovery guidance without changing canonical stage
  contiguity.

- [ ] **Step 1: Write failing localization and supporting-operation tests**

```python
def test_missing_book_analysis_does_not_break_later_stage_contiguity(project_root: Path) -> None:
    write_completed_translation_and_downstream_fixture(project_root)

    result = project_workspace_service.validate_project(project_root)

    assert result["status"] == "ok"
    assert result["manifest"]["current_stage"] == "audio_assembly_ready"
```

Require parity for all `book_analysis.*`, dialog, status, operation, and stage
keys. Romanian text must be meaningful translation rather than copied English.

- [ ] **Step 2: Write failing project validation/healing tests**

Cover completed artifact healing, corrupted artifact recovery instruction,
missing artifact with completed manifest summary, stale fingerprint, and a
completed later stage that remains the high-water mark when Book Analysis
completes afterward.

- [ ] **Step 3: Run localization/Home/recovery tests and confirm failure**

```powershell
uv run pytest tests/test_localization_parity.py tests/test_ui_localization_coverage.py tests/test_project_workspace_service.py tests/test_project_stage_consistency.py -q
```

- [ ] **Step 4: Implement strings and independent supporting-operation healing**

Do not add Book Analysis to the Home canonical workflow stepper or export rows
in this delivery. Project validation handles its completion evidence in a
separate supporting-operation pass using `operation_summary(document)`; the
result never participates in canonical contiguous-stage calculation. Malformed
documents name Book Analysis as the recovery step. Healing never promotes a
workflow stage or completion from an invalid or stale document.

- [ ] **Step 5: Run localization/Home/recovery tests**

```powershell
uv run pytest tests/test_localization_parity.py tests/test_ui_localization_coverage.py tests/test_project_workspace_service.py tests/test_project_stage_consistency.py -q
```

Expected: PASS.

- [ ] **Step 6: Review without committing**

Run `git diff --check`; record evidence.

---

### Task 10: Document, visually verify, and validate the complete feature

**Files:**

- Modify: `00_Planning/Overview.md`
- Modify: `CHANGELOG.md`
- Modify: `06_SoftwareDocu/UserGuide/index.html`
- Modify: `06_SoftwareDocu/UserGuide_ro/index.html`
- Create: `06_SoftwareDocu/UserGuide/assets/screenshots/book-analysis.png`
- Create: `06_SoftwareDocu/UserGuide_ro/assets/screenshots/book-analysis.png`
- Modify: `02_Tools/regenerate_help_screenshots.py`
- Modify: applicable `.agentic/requirements/`, `.agentic/specs/`,
  `.agentic/tasks/`, and `.agentic/knowledge/` files created by the executing task

**Interfaces:**

- Consumes: Fully implemented and focused-test-green feature.
- Produces: User documentation, current screenshots, changelog entry, AEGIS
  traceability, focused verification, full-suite evidence, and delivery checkpoint.

- [ ] **Step 1: Update the product overview and changelog**

Insert Book Analysis after Text Chunking in the documented workflow. Under
`## [Unreleased]`, describe the feature in user language without assigning a
version:

```markdown
- Added a standalone Book Analysis step that creates a resumable overview of a
  chunked book, including its subject, main characters, narrative style, themes,
  and audiobook guidance, with support for local AI profiles using 16K contexts.
```

- [ ] **Step 2: Update both user guides**

Document prerequisites, Analyze/Resume/Refresh/Reset behavior, 16K minimum and
32K recommendation, report sections, spoiler labelling, local/online usage,
independence from Translation and voices, invalidation after chunk changes, and
the oversized-single-chunk recovery instruction. Keep English and Romanian
content semantically aligned.

- [ ] **Step 3: Generate and visually inspect current screenshots**

Extend `regenerate_help_screenshots.py`, generate both language screenshots,
and inspect them at normal and large text scales. Verify no clipped action row,
readable report sections, visible scrollbar, correct spoiler label, and correct
sidebar order. A screenshot file existing is not sufficient evidence; record
the observed visual result in the AEGIS journal.

- [ ] **Step 4: Run the complete focused feature set**

From `05_Software/AudioMancer`:

```powershell
uv run pytest tests/test_book_analysis_document_service.py tests/test_book_analysis_budget_service.py tests/test_book_analysis_service.py tests/test_book_analysis_state_service.py tests/test_book_analysis_page.py tests/test_book_analysis_ui_controller.py tests/test_workflow_order_consistency.py tests/test_operation_runtime_service.py tests/test_project_workspace_service.py tests/test_main_window_project_flow.py tests/test_navigation_sidebar.py tests/test_localization_parity.py tests/test_ui_localization_coverage.py -q
```

Expected: PASS with no deselected Book Analysis test.

- [ ] **Step 5: Run task-scoped static AEGIS validation**

Run the repository-configured task-scoped `aegis check` command for the active
task. Read every finding and correct it. If any warning is accepted, record it
and immediately say the required `DEVIATION validate:` line.

- [ ] **Step 6: Run the full suite directly with a 60-minute bound**

From `05_Software/AudioMancer`:

```powershell
uv run pytest
```

Allow at least 60 minutes. If the command launcher returns early, first verify
whether the original pytest process is still running; never launch a duplicate
suite. If `uv` reports the known trampoline/canonicalization failure, use the
owning environment instead and record the deviation:

```powershell
.venv\Scripts\python.exe -m pytest
```

- [ ] **Step 7: Perform final contract review**

Confirm from the final diff and tests that:

- no request can exceed the configured context budget;
- exact 16K works and below 16K fails before network access;
- hierarchical consolidation covers arbitrarily many windows;
- source windows never split chunks;
- cancellation and resume do not repeat accepted work;
- failed refresh preserves the previous completed report;
- only chunk/source changes invalidate the report;
- no downstream service imports or reads Book Analysis;
- English/Romanian localization and help remain aligned;
- `CHANGELOG.md` is updated under Unreleased;
- no version was changed;
- no unrelated work entered the candidate.

- [ ] **Step 8: Present the AEGIS validation report and stop for delivery approval**

Update the journal stage report, run `python .agentic/aegis.py status`, copy the
exact Book Analysis task ID printed there, and run
`python .agentic/aegis.py summary` with that exact ID. Present the compact
summary plus focused/full-suite/GUI evidence and stop at the delivery approval
checkpoint. Do not copy one of the unrelated existing task IDs.

- [ ] **Step 9: Commit or publish only with explicit authority**

If and only if the user grants Git authority after reviewing the validated
candidate, stage only the intended Book Analysis, test, documentation, AEGIS,
and changelog files and follow the deliver-stage instructions. Do not infer push
authority from commit authority.

---

## Expected File Map After Implementation

New product files:

```text
05_Software/AudioMancer/prompts/book_analysis_system.txt
05_Software/AudioMancer/prompts/book_analysis_window_user.txt
05_Software/AudioMancer/prompts/book_analysis_consolidation_user.txt
05_Software/AudioMancer/prompts/book_analysis_synthesis_user.txt
05_Software/AudioMancer/src/audiomancer/services/book_analysis_budget_service.py
05_Software/AudioMancer/src/audiomancer/services/book_analysis_document_service.py
05_Software/AudioMancer/src/audiomancer/services/book_analysis_service.py
05_Software/AudioMancer/src/audiomancer/services/book_analysis_state_service.py
05_Software/AudioMancer/src/audiomancer/ui/controllers/book_analysis_ui_controller.py
05_Software/AudioMancer/src/audiomancer/ui/pages/book_analysis_page.py
```

New primary tests:

```text
05_Software/AudioMancer/tests/test_book_analysis_budget_service.py
05_Software/AudioMancer/tests/book_analysis_test_support.py
05_Software/AudioMancer/tests/test_book_analysis_document_service.py
05_Software/AudioMancer/tests/test_book_analysis_service.py
05_Software/AudioMancer/tests/test_book_analysis_state_service.py
05_Software/AudioMancer/tests/test_book_analysis_ui_controller.py
05_Software/AudioMancer/tests/test_book_analysis_page.py
```

Project-local runtime outputs:

```text
book_analysis.json
log_ai_book_analysis_YYYYMMDDTHHMMSS.log
```

No new third-party dependency is expected.
