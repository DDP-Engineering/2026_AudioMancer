<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Project Workspace

## 1. Purpose

Provides the first project-persistence layer for `AudioMancer`.

It gives the desktop shell a stable way to create a new project root, open an
existing project from its root or one child folder, and validate the minimal
`project.json` contract used by the current application state.

## 2. Responsibilities

- validate exact project names against the current Windows and Linux folder
  safety rules
- create the numbered project workflow folders plus `temp`
- create and save the minimal `project.json` manifest
- resolve the project root from a selected root folder or child workflow folder
- validate required folders and required manifest fields during open
- detect recoverable corruption in workflow folders or stage metadata during open
- repair the corrupted step and all downstream step folders after operator confirmation
- feed the main window with loaded project root and manifest state

It does not yet own source import, extraction artifacts, narrator content
storage, or full workflow-state persistence beyond the current minimal
manifest.

## 3. Implementation Overview

The component is implemented in:

- `src/audiomancer/services/project_workspace_service.py`
- `src/audiomancer/ui/main_window.py`

Main public entrypoints:

- `build_project_manifest(display_name, timestamp_iso=None)`
- `validate_project_manifest(payload)`
- `validate_project_name(name)`
- `create_project(name, parent_path)`
- `resolve_project_root(selected_path)`
- `validate_project(project_root)`
- `open_project(selected_path)`

High-level flow:

1. `MainWindow` opens a parent-folder picker and then a project-name input popup from the toolbar.
2. `MainWindow` calls `audiomancer.services.project_workspace_service`
   directly.
3. The workspace service validates the project name, creates or resolves the
   project root, validates the structure, and loads or writes `project.json`.
4. If one recoverable corruption is detected, the service returns a
   `repair_required` result payload and `MainWindow` asks the operator for
   confirmation.
5. After confirmation, the workspace service recreates or resets the corrupted
   step folder and all downstream step folders, repairs the manifest stage,
   and reloads the project.
6. `MainWindow` stores the active project root and manifest, updates the home
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
- project layout and validation rules from `src/audiomancer/config.py`

Outputs:

- one new project root folder under the selected parent
- required workflow subfolders:
  `00_extraction`, `10_cleanup`, `20_chunking`, `30_translation`,
  `40_character_discovery`, `50_narrator_definition`, and `temp`
- one root-level `project.json`
- one loaded validated manifest dictionary for the UI shell
- operator-visible status and validation feedback through the main window

## 6. Data Contracts

Current root manifest contract in `project.json`:

- `project_id`
- `display_name`
- `created_at`
- `updated_at`
- `current_stage`
- `source_document_name`
- `narrator_profile_name`
- `narrator_language`
- `notes`

Required folder contract:

- `00_extraction`
- `10_cleanup`
- `20_chunking`
- `30_translation`
- `40_character_discovery`
- `50_narrator_definition`
- `temp`

Current validation invariants:

- project names are stored exactly as entered
- invalid names are rejected rather than rewritten
- `project.json` must exist at the project root
- `current_stage` must match one of the configured workflow stage tokens
- opening a project walks upward from the selected folder until `project.json`
  is found
- a missing workflow step folder is treated as recoverable corruption
- repair resets the corrupted step folder and every later workflow step folder
- repaired metadata keeps the last consistent workflow stage

## 7. Workflow Integration

This component now sits between the static shell and future workflow modules.

Upstream:

- `MainWindow` toolbar actions `New Project` and `Open Project`

Downstream:

- `HomeProjectPage` summary and workflow-progress display
- page enablement across the current sidebar shell
- future source-import and narrator-definition workflows that will persist
  additional manifest metadata

## 8. Usage

Service usage:

```python
from audiomancer.services.project_workspace_service import create_project, open_project

project_root, manifest = create_project("Book5_CAL_CAL", "D:/Projects")
resolved_root, loaded_manifest = open_project(project_root / "20_chunking")
```

UI integration:

- use the toolbar `New Project` action to choose a parent folder and enter the
  exact project name
- use the toolbar `Open Project` action to select either the project root or a
  child workflow folder

## 9. Validation And Tests

Automated tests:

- `tests/test_project_workspace_service.py`
- `tests/test_main_window.py`
- `tests/test_config_contract.py`

Covered behaviors:

- project creation layout
- exact-name validation for unsupported Windows characters
- rejection of Linux-reserved names
- rejection of reserved Windows device names
- open-project root resolution from child workflow folders
- missing manifest handling
- repair handling for missing required folders
- missing required manifest-field handling
- repair handling for invalid `current_stage` metadata
- main-window activation and workflow progress updates after create/open
- main-window repair confirmation flow during open

Minimum validation after a change:

- `uv run python -m py_compile <changed_file.py>`
- focused `uv run pytest` for project workspace and main-window tests

## 10. Limitations And Future Work

- the manifest is intentionally minimal and does not yet mirror the older
  `DDP_Audiomancer` schema
- project open repair currently handles missing step folders and invalid
  `current_stage` metadata only
- source import, extraction state, and narrator assets are not yet persisted
  into project-local artifacts
- there is no migration layer yet for future manifest schema revisions
