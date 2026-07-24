<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Text Extraction Service

## 1. Purpose

Provides the deterministic raw-text extraction slice for `AudioMancer`.

It gives the `Text Cleanup` page one extraction workflow that reads the
imported source from the project root, produces `extracted_text.txt`, persists
one authoritative `extraction_metadata.json` document, and reports progress
through the shared modal operation runner.

## 2. Responsibilities

- extract raw text from the currently supported source formats
- normalize extracted text and persist it as `extracted_text.txt` atomically
- persist status, progress, warnings, page count, and final statistics together
  in `extraction_metadata.json` atomically
- support resume for interrupted extraction from `progress_current` when the
  saved checkpoint is safe
- clear known extraction and downstream runtime artifacts for a confirmed rerun
  of a completed extraction
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
- `load_extraction_metadata(project_root)`
- `write_extraction_metadata(project_root, metadata)`
- `build_extraction_summary(metadata)`
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
5. `text_extraction_service.extract_text(...)` resolves the imported source
   from `project.json`.
6. The service appends extracted text units to `extracted_text.txt`, updates
   `extraction_metadata.json` atomically after every processed unit, and emits
   unit-based progress callbacks.
7. `MainWindow` drives the extraction run through the reusable modal progress
   dialog, including cooperative cancellation.
8. `MainWindow` refreshes the cleanup page directly from the authoritative
   extraction metadata; no extraction summary is stored in `project.json`.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`, `audiomancer.services.logging_service`,
  `audiomancer.services.operation_runtime_service`,
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
- root-level imported source file
- extraction format implied by `source_document.file_type`

Outputs:

- `extracted_text.txt`
- `extraction_metadata.json`
- progress updates delivered to the modal operation-progress dialog
- cleanup-page preview text and operator-facing notes

## 6. Data Contracts

`extraction_metadata.json` has an exact root schema:

- `status`
- `progress_current`
- `progress_total`
- `warnings`
- `character_count`
- `word_count`
- `line_count`
- `page_count`

Persisted statuses are `running`, `cancelled`, `failed`, and `completed`;
absence of the metadata file means `not_started`. `progress_current` is the
resume checkpoint. Text statistics are `null` while incomplete and
non-negative integers when completed. `page_count` is the PDF page total or
`null` for other formats. Warning count is derived from `len(warnings)`.
Completed metadata requires `progress_current == progress_total` and valid,
non-empty `extracted_text.txt`.

The source path and type come only from `project.source_document`. The
extracted text and metadata paths are derived from configuration; no path,
mode, warning count, or extraction operation summary is duplicated in
`project.json`. Unknown fields, invalid status/progress/statistics, malformed
JSON, legacy sidecars, and mixed legacy/current artifacts fail strict loading
and require Extraction reset. There is no migration or permanent fallback.

Supported extraction formats in the current implementation:

- `.txt`
- `.pdf`
- `.rtf`
- `.docx`
- `.odt`
- `.md`
- `.epub`

Current deterministic behavior:

- extracted output is always written as `extracted_text.txt`
- `project.json` does not store extracted-text, extraction-metadata, warning,
  progress, or status shortcuts; downstream services resolve the root-level
  artifact names from `config.py`
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
- a completed rerun keeps the imported source file but clears known generated
  extraction and downstream runtime artifacts
- cancellation and failure persist their explicit status, progress, and
  warnings for resume; TXT and Markdown restart cleanly because they do not
  support granular resume

## 7. Workflow Integration

Upstream:

- `HomeProjectPage` source import must complete first
- `TextCleanupPage` exposes the operator action and preview state

Downstream:

- deterministic cleanup now consumes `extracted_text.txt`
- cleanup, chunking, translation, character discovery, narrator, character
  voice, Speech Blocks, Audio Blocks, and Audio Assembly runtime artifacts are
  reset when the operator confirms a destructive extraction rerun
- the shared threaded modal progress dialog runs extraction off the Qt UI
  thread while the dialog owns progress, cancellation, and final refresh

## 8. Usage

Service usage:

```python
from audiomancer.services import text_extraction_service

metadata = text_extraction_service.extract_text(project_root, manifest)
summary = text_extraction_service.build_extraction_summary(metadata)
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
- strict metadata-schema rejection and explicit cancellation/failure state
- legacy and mixed-project reset-required behavior
- destructive reset behavior for extraction and downstream runtime artifacts
- cleanup-page button enablement and preview updates
- main-window extraction, completed-rerun confirmation, and unfinished-resume flow

Minimum validation after a change:

- `uv run python -m py_compile <changed_file.py>`
- focused `uv run pytest` for extraction service, cleanup page, main window,
  and workspace tests

## 10. Limitations And Future Work

- OCR is not implemented, so image-only PDFs fail extraction
- extraction processes one unit at a time without parallel format handling
- cleanup, chunking, translation, and character-discovery artifact generation
  are still out of scope for this service
- format handlers currently extract plain text only and do not preserve richer
  semantic structure

Documentation audit status: reviewed against the current implementation on
2026-07-23. Shared operation-runtime behavior is documented separately in
`AudioMancer_Project_Runtime_Support_Services.md`.
