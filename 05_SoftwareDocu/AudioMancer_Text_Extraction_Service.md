<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Text Extraction Service

## 1. Purpose

Provides the deterministic raw-text extraction slice for `AudioMancer`.

It gives the `Text Cleanup` page one self-contained extraction workflow that
copies the selected source into `00_extraction`, produces `output_raw_text.txt`,
persists extraction metadata, stores resumable operation state, and reports
progress through the shared modal operation runner.

## 2. Responsibilities

- copy the imported source into `00_extraction/input_<original_name>`
- extract raw text from the currently supported source formats
- normalize extracted text and persist it as `00_extraction/output_raw_text.txt`
- persist extraction metadata as
  `00_extraction/extraction_report.json`
- persist resumable operation state as
  `00_extraction/state_operation.json`
- support resume for interrupted extraction when the saved checkpoint is safe
- clear extraction outputs and downstream operation folders for a confirmed
  rerun of a completed extraction
- emit unit-based progress and support cooperative cancellation for long runs
- emit one immediate preparation-status update before the heavier format-specific
  extraction steps begin

It does not own deterministic cleanup, AI cleanup, chunking, translation, or
OCR.

## 3. Implementation Overview

The component is implemented in:

- `src/audiomancer/services/text_extraction_service.py`
- `src/audiomancer/ui/pages/text_cleanup_page.py`
- `src/audiomancer/ui/main_window.py`
- `src/audiomancer/services/operation_runtime_service.py`

Main public entrypoints:

- `extract_text(project_root, manifest)`
- `load_operation_state(project_root)`
- `load_extraction_report(project_root)`
- `reset_extraction_and_downstream(project_root)`

High-level flow:

1. `TextCleanupPage` emits `extract_requested`.
2. `MainWindow._handle_extract_text_requested()` validates the active project
   and imported source.
3. If extraction is already completed, `MainWindow` asks for confirmation
   before clearing extraction outputs and downstream folders.
4. If extraction is unfinished, `MainWindow` starts the extraction again
   without the destructive confirmation and resumes from saved progress when
   possible.
5. `text_extraction_service.extract_text(...)` ensures one copied input
   snapshot exists inside `00_extraction`.
6. The service extracts text units, updates `state_operation.json` while the
   work is in progress, emits unit-based progress callbacks, then writes
   `output_raw_text.txt` and `extraction_report.json`.
7. `MainWindow` drives the extraction run through the reusable modal progress
   dialog, including cooperative cancellation.
8. `MainWindow` stores the resulting artifact paths and operation state in
   `project.json` and refreshes the cleanup page preview.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`, `audiomancer.services.logging_service`,
  `audiomancer.services.operation_runtime_service`,
  `audiomancer.services.project_workspace_service`,
  `audiomancer.services.ui_state_service`, `audiomancer.ui.main_window`,
  `audiomancer.ui.operation_progress_dialog`,
  `audiomancer.ui.pages.text_cleanup_page`
- External dependencies:
  Python standard library for JSON, filesystem handling, datetimes, and HTML
  parsing; `PyMuPDF`, `python-docx`, `striprtf`, `odfpy`, `EbookLib`, and
  `PySide6`

## 5. Inputs And Outputs

Inputs:

- active project root folder
- current `project.json` manifest with a populated `source_document`
- the copied source snapshot or root-level imported source file
- extraction format implied by `source_document.file_type`

Outputs:

- `00_extraction/input_<original_name>`
- `00_extraction/output_raw_text.txt`
- `00_extraction/extraction_report.json`
- `00_extraction/state_operation.json`
- updated `project.json` fields:
  `extracted_text_relative_path`,
  `extraction_report_relative_path`,
  `extraction_warning_count`, and `operations.extraction`
- progress updates delivered to the modal operation-progress dialog
- cleanup-page preview text and operator-facing notes

## 6. Data Contracts

Current extraction report fields:

- `source_relative_path`
- `source_type`
- `extracted_text_relative_path`
- `extracted_at`
- `page_count`
- `warnings`
- `character_count`
- `word_count`
- `line_count`

Current extraction operation-state fields:

- `folder_relative_path`
- `status`
- `input_paths`
- `output_paths`
- `artifact_paths`
- `progress_current`
- `progress_total`
- `mode`
- `started_at`
- `completed_at`
- `updated_at`
- `warning_count`
- `metadata`
- `resume_checkpoint`

Supported extraction formats in the current implementation:

- `.txt`
- `.pdf`
- `.rtf`
- `.docx`
- `.odt`
- `.md`
- `.epub`

Current deterministic behavior:

- extracted output is always written as `00_extraction/output_raw_text.txt`
- line endings are normalized to `\n`
- leading and trailing unusable whitespace is trimmed
- one final trailing newline is written to the completed output file
- PDF page units are separated with a stable page-break marker so cleanup can
  still detect repeated headers and footers later
- PDF extraction progress now advances page-by-page during the real page-text
  extraction pass
- RTF extraction progress now advances paragraph-by-paragraph after the RTF
  payload is converted to plain text
- EPUB extraction progress now advances across paragraph-sized units derived
  from extracted XHTML content
- a completed rerun keeps the copied input snapshot but clears generated
  extraction data and all downstream operation folders

## 7. Workflow Integration

Upstream:

- `HomeProjectPage` source import must complete first
- `TextCleanupPage` exposes the operator action and preview state

Downstream:

- deterministic cleanup now consumes `output_raw_text.txt`
- future chunking, translation, and character-discovery steps are reset when
  the operator confirms a destructive extraction rerun
- the shared modal progress dialog now blocks the main shell while extraction is
  active

## 8. Usage

Service usage:

```python
from audiomancer.services import text_extraction_service

report_payload = text_extraction_service.extract_text(project_root, manifest)
state_payload = text_extraction_service.load_operation_state(project_root)
```

UI usage:

- open one project with an imported source
- go to `Text Cleanup`
- press `Extract Text`
- if extraction was already completed, confirm the rerun reset before
  continuing

## 9. Validation And Tests

Automated tests:

- `tests/test_text_extraction_service.py`
- `tests/test_text_cleanup_page.py`
- `tests/test_main_window.py`
- `tests/test_project_workspace_service.py`

Covered behaviors:

- TXT extraction artifact creation
- extraction support for Markdown, RTF, DOCX, ODT, and EPUB
- PDF page-count and warning reporting
- rejection of empty-text PDFs without OCR
- resume of unfinished incremental extraction
- destructive reset behavior for extraction and downstream folders
- cleanup-page button enablement and preview updates
- main-window extraction, completed-rerun confirmation, and unfinished-resume flow

Minimum validation after a change:

- `uv run python -m py_compile <changed_file.py>`
- focused `uv run pytest` for extraction service, cleanup page, main window,
  and workspace tests

## 10. Limitations And Future Work

- OCR is not implemented, so image-only PDFs fail extraction
- extraction runs synchronously in the main shell and still processes one unit
  at a time without parallel format handling
- cleanup, chunking, translation, and character-discovery artifact generation
  are still out of scope for this service
- format handlers currently extract plain text only and do not preserve richer
  semantic structure
