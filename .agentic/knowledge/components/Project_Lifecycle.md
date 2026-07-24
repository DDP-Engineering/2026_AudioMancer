<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Project Lifecycle

## 1. Purpose

The Project Lifecycle component owns the operator-facing lifetime of an
AudioMancer project: creating or opening its flat workspace, validating and
repairing `project.json`, registering the source document, presenting Home-page
state, and producing external exports or whole-project snapshots. It also owns
the shared atomic writer used for critical project metadata.

## 2. Responsibilities

- Create, validate, open, normalize, save, and metadata-repair project
  workspaces and manifests.
- Validate project names and project-relative artifact paths across supported
  platforms.
- Import or replace one supported source document before project options are
  locked, preserving normalized source metadata in the manifest.
- Project detailed operation state into compact manifest summaries and derive
  Home-page workflow status and export readiness.
- Coordinate Home-page create/open/repair, source import, option locking,
  snapshot, and export actions.
- Render text/Markdown delivery projections and package ready voice or audio
  artifacts into external ZIP exports.
- Create cancellable whole-project ZIP snapshots through a temporary archive
  and atomic replacement.
- Write critical text and JSON files through same-directory temporary files,
  `fsync`, and `os.replace`.

The component does not execute extraction, cleanup, chunking, translation,
character, voice, TTS, or audio-assembly operations. It reads those components'
artifacts only to present state, validate manifest evidence, and export current
results. Thread execution and cancellation primitives belong to
`operation-orchestration`.

## 3. Implementation Overview

The implementation boundary is:

- `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/import_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/persistence_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/project_export_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/project_snapshot_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/home_presenter_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/home_page.py`

`project_workspace_service` builds and validates the manifest, resolves a
selected root or child path, rejects unsupported legacy layouts, proposes
metadata-only repairs from artifact evidence, and saves compact operation
summaries. `import_service.import_source` validates and copies the selected
source, removes only a safely resolved previous project copy, and returns the
manifest-ready source record. `persistence_service` provides the atomic write
primitive used by manifest persistence.

`home_presenter_service` turns manifest summaries and the active operation into
read-only workflow rows. `HomeUiController` owns the UI orchestration and keeps
dialogs, project activation, option locking, threaded snapshots, and external
save-path checks out of `HomeProjectPage`. The page owns Qt signals, controls,
translated labels, theme roles, busy state, and readiness display.

`project_export_service` reads ready downstream artifacts into format-neutral
export documents or curated audio ZIP files. `project_snapshot_service` walks
the active project, skips symlinks and AI transaction logs, archives files under
one top-level project folder, and replaces the requested destination only after
the temporary ZIP completes.

## 4. Dependencies

Internal dependencies include `audiomancer.config`, time and logging services,
operation runtime/path-safety helpers, UI state, token-usage normalization, and
the domain service loaders whose artifacts are exposed as exports. The Home
controller uses the shared operation runner for progress and cancellation.

External dependencies are Python standard-library filesystem, JSON, copying,
date/time, dataclass, regular-expression, and ZIP APIs. The UI boundary uses
PySide6 widgets, signals, dialogs, and models. Project data is stored in the
local filesystem; the component does not call a network service.

## 5. Inputs And Outputs

Inputs include operator-selected project and source paths, project names,
language and voice-mode selections, the active manifest, operation artifacts,
and export or snapshot destinations.

Outputs include the project root, root-level `project.json`, one copied source
file and its metadata, normalized or repaired manifest dictionaries, Home-page
status/readiness rows, external TXT/Markdown/ZIP exports, external project ZIP
snapshots, and operator-visible success or validation messages. Export and
snapshot deliverables are not registered as runtime project artifacts.

## 6. Data Contracts

Chunking completion evidence and text-chunk exports are projections of the one
strict `chunks_text.json` document. Project open does not create a default
Chunking state file, and obsolete report/state sidecars are ignored except when
Reset Chunking deletes them.

Narrator completion evidence and exports are projections of the strict
`narrator_voice.json` document. The selected profile's language, inline sample
metadata, and canonical `audio_narator_<profile_id>.wav` are resolved at read
time. Narrator reset owns only the current document, canonical profile WAVs,
and `log_ai_narrator_profiles_*.log`; project repair never imports or rewrites
removed narrator persistence artifacts. Project snapshots include the document
and WAVs while excluding AI transaction logs.

The root manifest contains project identity and timestamps, `current_stage`,
`source_document`, compact `operations`, locked language/voice options,
audio-assembly settings, and notes. `source_document` contains
`original_name`, `stored_relative_path`, `file_type`, `imported_at`, and
`size_bytes`. Compact operation summaries contain `status`, progress values,
`mode`, and `warning_count`; detailed checkpoints and outputs remain in their
domain artifacts.

Project-relative paths must be relative, contain no parent traversal, and
resolve inside the active project even when symlinks are present. New projects
use a flat root, with generated audio permitted under `audio_blocks/` and final
assembly output under `audiobook/`; numbered legacy workflow folders are not
accepted.

Supported source suffixes are `.txt`, `.pdf`, `.rtf`, `.docx`, `.odt`, `.md`,
and `.epub`. Atomic JSON uses UTF-8, two-space indentation, unescaped Unicode,
and a trailing newline by default. Export/snapshot paths must be outside the
active project. Snapshot members share one top-level folder named after the
project root; AI transaction logs and symlinks are excluded.

## 7. Workflow Integration

The application shell delegates project and Home actions to
`HomeUiController`. A successful create/open/repair activates the project,
updates the Home presenter and export readiness, and enables the appropriate
workflow pages. Source import precedes downstream processing; locking project
options freezes source replacement and establishes target language and voice
assignment mode.

Downstream workflow components persist detailed artifacts and compact manifest
summaries. Project open may use trustworthy artifacts to propose a metadata-only
summary/stage repair, but it does not rewrite domain artifacts. Home exports and
snapshots read the current local state without mutating the active project.

## 8. Usage

```python
from audiomancer.services import project_workspace_service

project_root, manifest = project_workspace_service.create_project(
    "Book5_CAL_CAL",
    "D:/Projects",
)
open_result = project_workspace_service.open_project(project_root)
```

```python
from audiomancer.services import project_export_service

markdown = project_export_service.render_export(
    project_root,
    manifest,
    project_export_service.EXPORT_KIND_TEXT_CHUNKS,
    project_export_service.EXPORT_FORMAT_MARKDOWN,
)
```

The desktop UI normally reaches these services through
`HomeUiController`; callers must preserve the external-destination checks for
exports and snapshots.

## 9. Validation And Tests

Primary automated coverage:

- `04_Software/AudioMancer/tests/test_project_workspace_service.py`
- `04_Software/AudioMancer/tests/test_import_service.py`
- `04_Software/AudioMancer/tests/test_persistence_service.py`
- `04_Software/AudioMancer/tests/test_project_export_service.py`
- `04_Software/AudioMancer/tests/test_project_snapshot_service.py`
- `04_Software/AudioMancer/tests/test_home_presenter_service.py`
- `04_Software/AudioMancer/tests/test_home_ui_controller.py`
- `04_Software/AudioMancer/tests/test_home_page.py`
- `04_Software/AudioMancer/tests/test_main_window_project_flow.py`
- `04_Software/AudioMancer/tests/test_main_window_home_exports.py`
- `04_Software/AudioMancer/tests/test_atomic_io_contracts.py`

After changes, run those focused tests with `uv run pytest`, plus
`uv run python -m py_compile` and `uv run ruff check` on changed files. Changes
to persistence or path containment require the atomic I/O and unsafe-path cases
as part of focused validation.

## 10. Limitations And Future Work

- Atomic writes are last-replacement-wins and do not provide cross-process
  locking or backup rotation.
- Project repair is metadata-only and intentionally leaves corrupt or stale
  domain artifacts untouched.
- Export formats are TXT/Markdown for readable projections and ZIP for voice or
  assembly artifacts; PDF export is not implemented.
- Snapshots are filesystem snapshots taken at start time, not transactional
  captures; the UI prevents starting them while another operation is active.
