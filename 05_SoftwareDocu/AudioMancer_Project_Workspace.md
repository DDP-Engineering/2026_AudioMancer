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
that project root, import or replace one pre-start source document, lock
immutable audiobook options with that selected source, persist compact workflow-operation
summaries, and validate the current `project.json` contract used by the
application shell.

## 2. Responsibilities

- validate exact project names against the current Windows and Linux folder
  safety rules
- create the project root without numbered workflow folders
- create and save the minimal `project.json` manifest
- keep new project creation limited to `project.json`; page-level state files
  are initialized only when the operator first opens the related workflow page
- lock the selected source, project target language, and narration mode when
  the operator starts the project
- resolve and validate the selected project root
- validate and copy one supported source file into the active project root
- persist structured source metadata and allow replacement until project start
- reject manifest and replacement-source paths that are absolute, contain parent
  traversal, or resolve through symlinks outside the active project root
- reject unsupported legacy numbered workflow-folder layouts during open
- validate required manifest fields during open
- detect recoverable stage metadata corruption during open
- detect recoverable stale `project.json` workflow summaries during open by
  comparing manifest metadata with trusted local operation artifacts
- return a metadata-only repair report with proposed changes, warnings, and a
  normalized manifest candidate before writing any repair
- persist compact extraction, cleanup, chunking, translation, and
  character-discovery summaries in the root manifest
- persist locked project-local narrator workflow settings such as
  `target_language`, `selected_voice_language`, and `voice_assignment_mode` in
  the root manifest
- keep detailed per-step state, reports, outputs, checkpoints, and AI logs as
  root-level project artifacts, except generated Audio Blocks files under
  `audio_blocks/` and final Audio Assembly deliverables under `audiobook/`
- create `<step>_state.json` defaults on first page open, while creating
  `<step>_report.json` files and output artifacts only after real workflow
  results exist
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
- `lock_project_options(project_root, target_language, voice_assignment_mode)`
- `import_source(project_root, source_path)`

High-level flow:

1. `MainWindow` opens a parent-folder picker and then a project-name input popup from the toolbar.
2. `MainWindow` calls `audiomancer.services.project_workspace_service`
   directly.
3. The workspace service validates the project name, creates or resolves the
   project root, rejects unsupported legacy numbered layouts, and loads or
   writes `project.json`.
4. If recoverable metadata corruption or stale workflow-summary metadata is
   detected, the service returns a `repair_required` result payload with
   proposed `project.json` changes, non-destructive warnings, and a normalized
   manifest candidate. `MainWindow` asks the operator for confirmation before
   anything is written.
5. After confirmation, the workspace service writes only the normalized
   `project.json` metadata and reloads the project. It does not delete
   artifacts, rewrite operation-state files, regenerate content, or repair
   unsupported numbered workflow folders.
6. `MainWindow` lets the operator choose one supported source file, calls
   `audiomancer.services.import_service`, stores the copied file in the
   project root, saves `source_document` in `project.json`, and advances the
   project to `source_selected`.
7. After source selection, `MainWindow` lets the operator choose the project
   target language and narration mode on the Home page. The workspace service
   persists `project_options_locked = true`, stores `target_language`, mirrors
   it into `selected_voice_language`, and stores `voice_assignment_mode`.
8. When the operator first opens a workflow page with operation-state
   metadata, `MainWindow` creates the missing `<step>_state.json` file with a
   `not_started` payload. It does not create reports or output artifacts.
9. After one workflow step writes its full local state into root-level
   operation artifacts, `MainWindow` stores only the compact operation summary
   back into `project.json`.
10. After deterministic cleanup completes, `MainWindow` advances the project to
   `text_chunking_ready` while keeping cleanup detail files at the project
   root.
11. After a selected chunk is manually edited and saved from `Text Chunking`,
   `MainWindow` keeps `chunks_text.json`, resets dependent runtime artifacts
   from translation onward, preserves existing Narator Voice profiles and
   selected narrator samples, and returns the project to `translation_ready`
   without changing the cleaned-text reference or chunk list scroll positions.
12. `MainWindow` stores the active project root and manifest, updates the home
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
- one `audiobook/` runtime subfolder for generated Audio Assembly deliverables
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
- `project_options_locked`
- `target_language`
- `selected_voice_language`
- `narrator_profile_name`
- `narrator_language`
- `voice_assignment_mode`
- `audio_assembly_settings`
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

AI-assisted chunking checkpoints store the completed paragraph-unit count plus
the last completed unit id, so an interrupted run can continue with a different
currently selected AI profile without reprocessing completed text. The chunking
state and report persist the selected profile id, model name, context window,
max output tokens, temperature, current budget metadata, and ordered profile
settings history when resumed segments use different model settings.

Default operation-state files are lazy page metadata. Opening a workflow page
may create a `not_started` state file with empty `input_paths`, `output_paths`,
`artifact_paths`, operation-specific default `metadata`, and
`resume_checkpoint = null`. For example, opening the Characters page creates
`characters_state.json` with zero-valued character-discovery metadata counters.
This initialization does not imply that the workflow step has run and does not
create reports or canonical outputs.

Voice workflow metadata is also lazy. Project activation and Home-page refreshes
do not create `audio_profiles.json`, `narator.json`, or `characters_voice.json`.
Opening the Narator Voice page initializes only narrator metadata; opening the
Character Voices page initializes the character-voice target metadata.

Upstream text and character reruns preserve narrator-definition data. Cleanup
reruns, selected cleaned-text edits, chunking reruns, selected chunk edits,
translation resets or approval-loss resets, and character-discovery resets keep
`audio_profiles.json`, `narator.json`, `narator.wav`, and `narator_sample.json`
when those files already exist. Character voice targets, Speech Blocks, Audio
Blocks, and assembled audiobook outputs are still invalidated because they
depend on the regenerated text or character set.

Required folder contract:

- no workflow folders are required for new projects
- `audio_blocks/` may be created by the Audio Blocks workflow for generated
  audio artifacts
- `audiobook/` may be created by the Audio Assembly workflow for generated
  audiobook deliverables

Current validation invariants:

- project names are stored exactly as entered
- invalid names are rejected rather than rewritten
- `project.json` must exist at the project root
- new projects start with `project_options_locked = false`
- source import is available before `project_options_locked = true`
- source import is disabled after the project is started
- locked project options cannot be changed through the normal workflow
- once locked, `selected_voice_language` is kept equal to `target_language`
- `current_stage` must match one of the configured workflow stage tokens
- `source_document`, when present, must contain one valid structured payload
- project-relative manifest paths must remain inside the active project root;
  absolute paths, `..` traversal, and symlink escapes fail validation before
  source or artifact evidence is trusted
- opening a project expects a selected project root with `project.json`
- legacy numbered workflow folders cause validation to fail with an unsupported
  legacy layout error
- repair is metadata-only and does not recreate numbered workflow folders
- repaired metadata keeps the last consistent workflow stage
- project-open manifest healing can promote operation summaries only when
  local artifacts prove the step completed; `current_stage` alone never marks
  an operation completed
- stale operation-state files are reported as warnings and are not rewritten by
  the project-open repair path
- the repaired `current_stage` is derived from the highest contiguous
  artifact-backed workflow milestone, but the first implementation does not
  downgrade a manifest that already claims a later stage
- a project with one imported source remains replaceable until
  `project_options_locked = true`

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
- use the Home page `Select Source File` button to import or replace one source
  document before starting the project

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
- copied source metadata persistence, collision-safe file naming, and pre-start
  source replacement cleanup
- manifest defaults for extraction fields and operation-state entries
- rejection of tampered manifest paths and traversal artifact references during
  project-open completion healing
- main-window activation and workflow progress updates after create/open
- main-window source import, replacement, and project-start lock behavior
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
