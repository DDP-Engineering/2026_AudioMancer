<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Project Snapshot Service

## 1. Purpose

`project_snapshot_service.py` creates complete ZIP snapshots of an active
AudioMancer project folder from the Home / Project page. The snapshot is an
external operator deliverable and is not registered in `project.json`.

## 2. Responsibilities

- Build a timestamped default ZIP file name for the active project.
- Add the `.zip` suffix when the selected save path omits it.
- Reject destinations that are equal to or below the active project root.
- Archive all regular files under the active project root, including
  `project.json`, imported sources, runtime artifacts, generated audio,
  reports, state files, logs, and final outputs.
- Place every archive member under one top-level folder named after the project
  folder so extraction does not scatter files directly into the destination
  directory.
- Avoid following symlink directories.
- Write through a temporary ZIP beside the requested destination and replace the
  final archive only after successful completion.

## 3. Workflow Integration

The Home page shows `Export Project ZIP` in the Project Summary area beside the
source-selection action. The button is disabled until a project is active and is
disabled while the shared long-running operation runner marks an operation as
busy. The Home controller also performs an active-operation check before opening
the save-file dialog, so direct signal calls cannot create a snapshot during an
operation.

The controller owns the UI flow:

- open `QFileDialog.getSaveFileName`
- apply the `.zip` extension
- reject inside-project destinations
- call `project_snapshot_service.create_project_snapshot`
- show localized success or failure messages

## 4. Data Contract

The service does not read or change the manifest content. It treats the active
project root as the source of truth and archives the filesystem snapshot that
exists when the user starts the export.

Archive paths use this structure:

```text
Project Folder Name/
  project.json
  clean_text.txt
  speech_blocks.json
  audio_blocks/
  audiobook/
  ...
```

## 5. Validation And Tests

Automated coverage:

- `tests/test_project_snapshot_service.py` checks top-level folder creation,
  runtime file inclusion, UTF-8 filename/content preservation, path rejection,
  extension/default-name helpers, failure cleanup, and symlink-directory
  skipping when the platform permits symlinks.
- `tests/test_home_page.py` checks the Home button presence, translated label,
  and enablement from project/busy state.
- `tests/test_home_ui_controller.py` checks active-operation blocking,
  inside-project rejection, extension selection, and readable ZIP creation.

Minimum focused validation after changes:

```powershell
uv run python -m py_compile src/audiomancer/services/project_snapshot_service.py src/audiomancer/ui/pages/home_page.py src/audiomancer/ui/controllers/home_ui_controller.py src/audiomancer/ui/main_window.py src/audiomancer/ui/controllers/operation_runner_controller.py
uv run pytest tests/test_project_snapshot_service.py tests/test_home_page.py tests/test_home_ui_controller.py
```

## 6. Limitations

- The snapshot is a full project folder archive, not a curated delivery package.
- It is not generated while long-running operations are active.
- The archive is not added to project metadata and is not treated as a runtime
  artifact.
