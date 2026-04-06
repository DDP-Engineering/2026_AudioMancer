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
persists extraction metadata, and stores resumable operation state.

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

It does not own deterministic cleanup, AI cleanup, chunking, translation, or
OCR.

## 3. Implementation Overview

The component is implemented in:

- `src/audiomancer/services/text_extraction_service.py`
- `src/audiomancer/ui/pages/text_cleanup_page.py`
- `src/audiomancer/ui/main_window.py`

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
4. If extraction is unfinished, `MainWindow` calls the extraction service
   directly without the destructive confirmation.
5. `text_extraction_service.extract_text(...)` ensures one copied input
   snapshot exists inside `00_extraction`.
6. The service extracts text units, updates `state_operation.json` while the
   work is in progress, then writes `output_raw_text.txt` and
   `extraction_report.json`.
7. `MainWindow` stores the resulting artifact paths and operation state in
   `project.json` and refreshes the cleanup page preview.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`, `audiomancer.services.logging_service`,
  `audiomancer.services.project_workspace_service`,
  `audiomancer.services.ui_state_service`, `audiomancer.ui.main_window`,
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
- a completed rerun keeps the copied input snapshot but clears generated
  extraction data and all downstream operation folders

## 7. Workflow Integration

Upstream:

- `HomeProjectPage` source import must complete first
- `TextCleanupPage` exposes the operator action and preview state

Downstream:

- future deterministic cleanup will consume `output_raw_text.txt`
- future chunking, translation, and character-discovery steps are reset when
  the operator confirms a destructive extraction rerun
- home-page workflow progress remains at `source_selected` until later
  cleanup work is implemented

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
- extraction runs synchronously in the main window; there is no background
  worker yet
- cleanup, chunking, translation, and character-discovery artifact generation
  are still out of scope for this service
- format handlers currently extract plain text only and do not preserve richer
  semantic structure
