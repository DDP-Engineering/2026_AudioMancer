<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Deterministic Cleanup Service

## 1. Purpose

Provides the deterministic text-cleanup slice for `AudioMancer`.

It gives the `Text Cleanup` page one conservative cleanup workflow that
consumes extracted text, removes repeated header/footer and page-number noise,
preserves paragraph and chapter structure, and persists self-contained cleanup
artifacts inside `10_cleanup`.

## 2. Responsibilities

- read the canonical extracted text selected by `project.json`
- copy the cleanup input snapshot as `10_cleanup/input_<original_source_name>`
- remove repeated page headers and footers when the extracted text still
  exposes page boundaries
- remove simple page-number markers
- remove ornamental separator-only lines such as `***` or `* * *`
- keep dialogue markers such as `- Replica...` on separate display lines when
  the surrounding punctuation clearly marks spoken dialogue
- preserve meaningful paragraph, chapter, and scene separation for later
  chunking
- persist cleanup output as `10_cleanup/output_clean_text.txt`
- persist cleanup metadata as `10_cleanup/artifact_cleanup_report.json`
- persist resumable operation state as `10_cleanup/state_operation.json`
- allow the operator to manually edit and save the persisted cleaned text from
  the `Text Cleanup` page after cleanup output exists
- provide right-click `Find` search in both extracted-text and cleaned-text
  preview windows
- support cooperative cancellation and resume for interrupted cleanup runs

It does not own text extraction, AI cleanup, chunk generation, translation, or
character discovery.

## 3. Implementation Overview

The component is implemented in:

- `src/audiomancer/services/deterministic_cleanup_service.py`
- `src/audiomancer/services/operation_runtime_service.py`
- `src/audiomancer/ui/main_window.py`
- `src/audiomancer/ui/pages/text_cleanup_page.py`

Main public entrypoints:

- `clean_text(project_root, manifest, progress_callback=None, cancel_requested=None)`
- `load_operation_state(project_root)`
- `load_cleanup_report(project_root)`

High-level flow:

1. `TextCleanupPage` emits `clean_requested`.
2. `MainWindow._handle_deterministic_cleanup_requested()` validates the active
   project and extracted-text prerequisite.
3. If cleanup is already completed, `MainWindow` asks for confirmation before
   clearing cleanup plus downstream chunking, translation, and
   character-discovery data.
4. `MainWindow` starts the cleanup service through the reusable modal
   operation-progress dialog.
5. The cleanup service copies the extracted input into `10_cleanup` using the
   original source file name after the `input_` prefix.
6. The service splits pages when extraction preserved page separators, removes
   repeated headers and footers, removes page numbers and ornamental separator
   lines, heals false blank-line paragraph splits when one sentence clearly
   continues, rebuilds cleaned paragraphs, and updates `state_operation.json`
   after each processed page.
7. On success, `MainWindow` stores the completed cleanup operation state in
   `project.json` and advances the workflow stage to `text_chunking_ready`.
8. After cleanup output exists, the operator can press `Edit` under the cleaned
   text preview, change the text, and press `Save`; the page writes
   `10_cleanup/output_clean_text.txt`, resets downstream workflow data, and
   preserves the extracted-text preview scroll position.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`, `audiomancer.services.logging_service`,
  `audiomancer.services.operation_runtime_service`,
  `audiomancer.services.project_workspace_service`,
  `audiomancer.services.ui_state_service`,
  `audiomancer.ui.operation_progress_dialog`
- External dependencies:
  Python standard library for JSON, regex, counters, datetimes, and
  filesystem handling; `langdetect`; `PySide6`

## 5. Inputs And Outputs

Inputs:

- active project root folder
- current `project.json` manifest with populated `source_document`
- extracted text referenced by `extracted_text_relative_path`
- optional progress callback and cancellation callback

Outputs:

- `10_cleanup/input_<original_source_name>`
- `10_cleanup/output_clean_text.txt`
- `10_cleanup/artifact_cleanup_report.json`
- `10_cleanup/state_operation.json`
- updated `project.json` operation entry `operations.cleanup`
- updated `project.json` stage value `text_chunking_ready` after successful
  cleanup
- updated `project.json` stage value `text_cleanup_ready` after a manual
  cleaned-text edit
- cleaned-text preview and cleanup notes on the `Text Cleanup` page

## 6. Data Contracts

Current cleanup report fields:

- `input_relative_path`
- `cleaned_text_relative_path`
- `cleaned_at`
- `detected_language`
- `warnings`
- `paragraph_count`
- `removed_line_count`
- `removed_header_footer_line_count`
- `removed_page_number_line_count`
- `removed_separator_line_count`
- `detected_chapter_count`

Current cleanup operation-state fields:

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

Current deterministic cleanup invariants:

- the operation-local input snapshot always preserves the original imported
  source file name after the `input_` prefix
- cleanup folder and primary file names are defined centrally in
  `audiomancer.config`
- cleanup output is always UTF-8 text with a trailing newline
- page-header and footer removal is conservative and requires repeated
  candidates across at least two pages
- separator-only lines such as `***` and `* * *` are removed as non-semantic
  formatting noise
- blank lines inside one continuing sentence may be healed when the surrounding
  text strongly indicates a false paragraph break
- interrupted cleanup leaves resumable state instead of deleting partial
  output
- manual cleaned-text edits preserve the cleanup operation artifacts but reset
  chunking, translation, character discovery, voice, Speech Blocks, Audio
  Blocks, and Audio Assembly state

## 7. Workflow Integration

Upstream:

- `HomeProjectPage` source import
- `text_extraction_service.extract_text(...)`
- `TextCleanupPage` action buttons and preview panes

Downstream:

- future deterministic and AI chunking will consume
  `10_cleanup/output_clean_text.txt`
- confirmed cleanup reruns reset `20_chunking`, `30_translation`, and
  `40_character_discovery`
- manual cleaned-text edits reset all downstream workflow folders from
  `20_chunking` onward because the chunking source changed
- the modal progress dialog is shared with extraction and future long-running
  operations

## 8. Usage

Service usage:

```python
from audiomancer.services import deterministic_cleanup_service

report_payload = deterministic_cleanup_service.clean_text(project_root, manifest)
state_payload = deterministic_cleanup_service.load_operation_state(project_root)
```

UI usage:

- import one source and run `Extract Text`
- go to `Text Cleanup`
- press `Deterministic Cleanup`
- press `Edit` below the cleaned text preview when manual correction is needed
- press `Save` to persist the edited cleaned text and reset downstream state
- right-click either text preview and choose `Find` to search within that
  preview
- if cleanup is already completed, confirm the rerun reset before continuing

## 9. Validation And Tests

Automated tests:

- `tests/test_deterministic_cleanup_service.py`
- `tests/test_operation_runtime_service.py`
- `tests/test_text_cleanup_page.py`
- `tests/test_main_window.py`

Covered behaviors:

- runtime artifact naming and persistence in `10_cleanup`
- repeated header/footer removal
- page-number removal
- structure-preserving cleanup across page breaks
- resumable cancellation state
- page button enablement and cleanup preview updates
- manual cleaned-text edit and save enablement
- main-window cleanup trigger, modal progress dialog exposure, and cleanup UI
  refresh after success

Minimum validation after a change:

- `uv run python -m py_compile <changed_file.py>`
- focused `uv run pytest` for cleanup service, main window, cleanup page, and
  operation-runtime tests

## 10. Limitations And Future Work

- cleanup currently runs synchronously at the shell level; there is no
  multi-operation queue or scheduler
- page-boundary-aware cleanup depends on extraction preserving page separators
  in the extracted output
- interruption resume currently restores page progress conservatively but does
  not persist richer semantic cleanup checkpoints
- AI-assisted cleanup is still out of scope for this component
