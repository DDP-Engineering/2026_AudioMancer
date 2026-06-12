<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Text Pipeline Support Services

## 1. Purpose

Documents supporting services used by text cleanup, chunking, and Speech
Blocks:

- `src/audiomancer/services/cleanup_metadata_service.py`
- `src/audiomancer/services/cleanup_text_analysis_service.py`
- `src/audiomancer/services/deterministic_chunking_service.py`
- `src/audiomancer/services/ai_chunking_service.py`
- `src/audiomancer/services/speech_blocks_report_state_service.py`
- `src/audiomancer/services/speech_blocks_text_split_service.py`

These services preserve stable text identity, split source text into safe AI
or TTS-sized units, and shape chunking/Speech Blocks operation reports.

## 2. Responsibilities

- build and atomically persist cleaned-text paragraph structure/provenance with
  stable paragraph IDs and no duplicated paragraph text
- classify text lines, scripts, language hints, chapter labels, sentence
  endings, and dialogue line breaks
- produce deterministic one-paragraph chunk artifacts for local chunking
- produce AI-assisted chunk artifacts from model-selected paragraph breaks
- rebuild Speech Blocks operation reports and warning summaries
- split long Speech Blocks text into budget-safe AI/TTS spans

They do not own text extraction, deterministic cleanup, AI provider transport,
voice generation, or Qt widget state.

## 3. Implementation Overview

Main public entrypoints:

- `cleanup_metadata_service.write_cleanup_metadata(...)`
- `cleanup_metadata_service.load_or_build_paragraph_records(...)`
- `cleanup_text_analysis_service.detect_language(...)`
- `cleanup_text_analysis_service.detect_chapter_label(...)`
- `cleanup_text_analysis_service.format_dialogue_lines(...)`
- `deterministic_chunking_service.chunk_text(...)`
- `deterministic_chunking_service.load_chunks(...)`
- `ai_chunking_service.chunk_text(...)`
- `speech_blocks_report_state_service.rebuild_report(...)`
- `speech_blocks_report_state_service.build_operation_state(...)`
- `speech_blocks_text_split_service.split_text_for_ai_context_budget(...)`
- `speech_blocks_text_split_service.tts_budget_unit_count(...)`

The deterministic path consumes cleaned text and compact paragraph metadata,
reconstructs paragraph text from `clean_text.txt`, writes ordered chunk JSON,
and persists operation state/report files. Deterministic chunking keeps chunks
in memory during the run, checkpoints the artifact and running state at bounded
paragraph/time intervals, updates chapter counts incrementally, and writes the
same completed artifacts as an uninterrupted per-paragraph run. The AI path
uses the same paragraph metadata but asks the configured model for safe break
positions, appends optional operator-supplied chunking rules to each prompt,
then commits only valid break IDs, reuses the already-built chunk list for each
window checkpoint, and writes AI transaction logs.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `audiomancer.services.operation_runtime_service`
- `audiomancer.services.llm_provider_service`
- `audiomancer.services.prompt_template_service`
- `audiomancer.services.persistence_service`
- `audiomancer.services.token_usage_service`
- `audiomancer.services.time_service`
- `audiomancer.services.speech_blocks_normalization_service`

External dependencies:

- Python standard library: `json`, `pathlib`, `re`, `hashlib`
- `langdetect` for best-effort language detection

## 5. Inputs And Outputs

Inputs:

- cleaned text from the project root
- cleanup metadata JSON when available
- selected AI profile, optional operator prompt rules, and prompt templates for
  AI chunking
- Speech Blocks payloads and source chunk paths
- context-budget values for AI/TTS segmentation

Outputs:

- cleanup metadata files
- chunk payload JSON files
- chunking report and operation-state files
- AI chunking log files
- Speech Blocks report and operation-state dictionaries
- ordered text segment lists for AI/TTS calls

## 6. Data Contracts

Cleanup metadata records are written through the shared atomic JSON helper and
preserve paragraph ordering, paragraph IDs,
`source_start_line`/`source_end_line` spans in canonical `clean_text.txt`,
source page numbers where available, warnings, and timestamps. They do not
persist paragraph `text`; `cleanup_metadata_service.load_or_build_paragraph_records(...)`
adds text back at runtime by slicing `clean_text.txt` with the stored line
spans.

Chunk payloads keep stable `chunk_id` values, source paragraph references,
chapter labels, sequence indexes, and text content. AI chunking persists token
usage, optional operator prompt rules, their fingerprint, and profile runtime
metadata in operation state so an interrupted run can resume with the same
committed break IDs and original prompt rules. Chunking state, report, and
chunk-artifact JSON writes use the shared atomic persistence helper; malformed
state JSON restarts chunking from a clean checkpoint, and malformed chunk
artifact JSON loads as an empty list with a warning instead of raising into the
workflow page.

Speech Blocks reports include stage status, approved counts, warning records,
source metadata, and token-usage payloads.

## 7. Workflow Integration

The text pipeline begins after cleanup has produced canonical cleaned text.
Chunking artifacts feed AI Translation, Character Discovery, Speech Blocks, and
later audio generation workflows. Speech Blocks report helpers are used by the
Speech Blocks service and state page to keep persisted operation metadata and
UI summaries aligned.

## 8. Usage

```python
records = cleanup_metadata_service.load_or_build_paragraph_records(project_root, cleaned_text)
chunks = deterministic_chunking_service.chunk_text(project_root, cleaned_text)
parts = speech_blocks_text_split_service.split_text_for_ai_context_budget(text, budget)
```

## 9. Validation And Tests

Focused tests:

- `tests/test_cleanup_metadata_service.py`
- `tests/test_cleanup_text_analysis_service.py`
- `tests/test_deterministic_chunking_service.py`
- `tests/test_ai_chunking_service.py`
- `tests/test_text_chunking_state_service.py`
- `tests/test_speech_blocks_report_state_service.py`
- `tests/test_speech_blocks_text_split_service.py`

Minimum validation after changes:

- `uv run python -m py_compile` for changed service files
- targeted `uv run pytest` for the matching text-pipeline tests

## 10. Limitations And Future Work

- Language detection is heuristic and can be unavailable for short text.
- AI chunking depends on model compliance and therefore validates break IDs
  before committing them.
- Text splitting uses conservative budget units rather than provider-specific
  tokenizers.
