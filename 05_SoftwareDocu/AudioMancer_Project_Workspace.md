<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Project Workspace

## 1. Purpose

Provides the project-persistence and source-import layer for `AudioMancer`.

It gives the desktop shell a stable way to create a new flat project root, open
that project root, import one locked source document, persist compact
workflow-operation summaries, and validate the current `project.json` contract
used by the application shell.

## 2. Responsibilities

- validate exact project names against the current Windows and Linux folder
  safety rules
- create the project root without numbered workflow folders
- create and save the minimal `project.json` manifest
- resolve and validate the selected project root
- validate and copy one supported source file into the active project root
- persist structured source metadata and lock the project to that source
- reject unsupported legacy numbered workflow-folder layouts during open
- validate required manifest fields during open
- detect recoverable stage metadata corruption during open
- persist compact extraction, cleanup, chunking, translation, and
  character-discovery summaries in the root manifest
- persist project-local narrator workflow settings such as
  `voice_assignment_mode` in the root manifest
- keep detailed per-step state, reports, outputs, checkpoints, and AI logs as
  root-level project artifacts, except generated Audio Blocks files under
  `audio_blocks/`
- feed the main window with loaded project root and manifest state

It does not extract text by itself, own narrator content storage, or implement
the downstream cleanup, chunking, translation, or character-discovery logic.

## 3. Implementation Overview

The component is implemented in:

- `src/audiomancer/services/project_workspace_service.py`
- `src/audiomancer/services/import_service.py`
- `src/audiomancer/ui/main_window.py`

Main public entrypoints:

- `build_project_manifest(display_name, timestamp_iso=None)`
- `validate_project_manifest(payload)`
- `validate_project_name(name)`
- `create_project(name, parent_path)`
- `resolve_project_root(selected_path)`
- `validate_project(project_root)`
- `open_project(selected_path)`
- `import_source(project_root, source_path)`

High-level flow:

1. `MainWindow` opens a parent-folder picker and then a project-name input popup from the toolbar.
2. `MainWindow` calls `audiomancer.services.project_workspace_service`
   directly.
3. The workspace service validates the project name, creates or resolves the
   project root, rejects unsupported legacy numbered layouts, and loads or
   writes `project.json`.
4. If recoverable metadata corruption is detected, the service returns a
   `repair_required` result payload and `MainWindow` asks the operator for
   confirmation.
5. After confirmation, the workspace service repairs the manifest stage and
   reloads the project. Missing numbered workflow folders are not repaired
   because numbered runtime layouts are no longer supported.
6. `MainWindow` lets the operator choose one supported source file, calls
   `audiomancer.services.import_service`, stores the copied file in the
   project root, saves `source_document` in `project.json`, and advances the
   project to `source_selected`.
7. After one workflow step writes its full local state into root-level
   operation artifacts, `MainWindow` stores only the compact operation summary
   back into `project.json`.
8. After deterministic cleanup completes, `MainWindow` advances the project to
   `text_chunking_ready` while keeping cleanup detail files at the project
   root.
9. After a selected chunk is manually edited and saved from `Text Chunking`,
   `MainWindow` keeps `chunks_text.json`, resets downstream
   downstream runtime artifacts from translation onward, and returns the project to
   `translation_ready` without changing the cleaned-text reference or chunk
   list scroll positions.
10. `MainWindow` stores the active project root and manifest, updates the home
   summary, updates workflow progress, and enables the workflow pages.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`, `audiomancer.services.logging_service`,
  `audiomancer.services.ui_state_service`, `audiomancer.ui.main_window`
- External dependencies:
  Python standard library for JSON, UUID, datetime, and filesystem handling;
  `PySide6` for the folder picker and text-input popup

## 5. Inputs And Outputs

Inputs:

- operator-selected parent folder for project creation
- operator-entered exact project name
- operator-selected folder for project opening
- operator-selected source document path
- project layout and validation rules from `src/audiomancer/config.py`

Outputs:

- one new project root folder under the selected parent
- one root-level `project.json`
- one copied source file stored directly in the project root
- root-level workflow artifacts written by each operation
- one `audio_blocks/` runtime subfolder for generated Audio Blocks files
- one loaded validated manifest dictionary for the UI shell
- persisted compact operation summaries in `project.json`
- persisted detailed operation state in operation-specific root state files and
  related artifacts
- operator-visible status and validation feedback through the main window

## 6. Data Contracts

Current root manifest contract in `project.json`:

- `project_id`
- `display_name`
- `created_at`
- `updated_at`
- `current_stage`
- `source_document`
- `extracted_text_relative_path`
- `extraction_report_relative_path`
- `extraction_warning_count`
- `operations`
- `original_language`
- `narrator_profile_name`
- `narrator_language`
- `voice_assignment_mode`
- `notes`

`source_document` payload contract:

- `original_name`
- `stored_relative_path`
- `file_type`
- `imported_at`
- `size_bytes`

Current `operations` map keys:

- `extraction`
- `cleanup`
- `chunking`
- `translation`
- `character_discovery`

Each compact operation entry stores:

- `folder_relative_path`
- `status`
- `progress_current`
- `progress_total`
- `mode`
- `started_at`
- `completed_at`
- `updated_at`
- `warning_count`

Detailed operation payloads such as input or output paths, metadata,
checkpoints, translated chunks, warning details, and similar workflow
internals are stored only in root-level state files, reports, and canonical
output artifacts.

Required folder contract:

- no workflow folders are required for new projects
- `audio_blocks/` may be created by the Audio Blocks workflow for generated
  audio artifacts

Current validation invariants:

- project names are stored exactly as entered
- invalid names are rejected rather than rewritten
- `project.json` must exist at the project root
- `current_stage` must match one of the configured workflow stage tokens
- `source_document`, when present, must contain one valid structured payload
- opening a project expects a selected project root with `project.json`
- legacy numbered workflow folders cause validation to fail with an unsupported
  legacy layout error
- repair is metadata-only and does not recreate numbered workflow folders
- repaired metadata keeps the last consistent workflow stage
- a project with one imported source is considered source-locked

Supported import formats:

- `.txt`
- `.pdf`
- `.rtf`
- `.docx`
- `.odt`
- `.md`
- `.epub`

## 7. Workflow Integration

This component now sits between the static shell and future workflow modules.

Upstream:

- `MainWindow` toolbar actions `New Project` and `Open Project`
- `HomeProjectPage` source-import request signal

Downstream:

- `HomeProjectPage` summary and workflow-progress display
- page enablement across the current sidebar shell
- future extraction and narrator-definition workflows that will consume the
  imported source metadata

## 8. Usage

Service usage:

```python
from audiomancer.services.project_workspace_service import create_project, open_project

project_root, manifest = create_project("Book5_CAL_CAL", "D:/Projects")
open_result = open_project(project_root)
```

UI integration:

- use the toolbar `New Project` action to choose a parent folder and enter the
  exact project name
- use the toolbar `Open Project` action to select the project root
- use the Home page `Select Source File` button to import exactly one source
  document into the active project

## 9. Validation And Tests

Automated tests:

- `tests/test_project_workspace_service.py`
- `tests/test_import_service.py`
- `tests/test_main_window.py`
- `tests/test_config_contract.py`

Covered behaviors:

- project creation layout
- exact-name validation for unsupported Windows characters
- rejection of Linux-reserved names
- rejection of reserved Windows device names
- open-project validation from the project root
- missing manifest handling
- rejection of unsupported legacy numbered workflow folders
- missing required manifest-field handling
- repair handling for invalid `current_stage` metadata
- source import acceptance for supported file types
- source import rejection for `.doc`
- copied source metadata persistence and collision-safe file naming
- manifest defaults for extraction fields and operation-state entries
- main-window activation and workflow progress updates after create/open
- main-window source import and lock behavior
- main-window metadata repair confirmation flow during open

Minimum validation after a change:

- `uv run python -m py_compile <changed_file.py>`
- focused `uv run pytest` for project workspace and main-window tests

## 10. Limitations And Future Work

- the manifest remains intentionally smaller than the older `DDP_Audiomancer`
  schema by storing only compact operation summaries at the project root
- project open repair currently handles missing step folders and invalid
  `current_stage` metadata only
- extraction artifacts are produced by a separate component documented in
  `05_SoftwareDocu/AudioMancer_Text_Extraction_Service.md`
- deterministic cleanup artifacts are produced by a separate component
  documented in `05_SoftwareDocu/AudioMancer_Deterministic_Cleanup_Service.md`
- existing projects with older detailed operation payloads remain readable, but
  there is no automatic manifest migration layer yet for future schema
  revisions
