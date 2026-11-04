<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Project Lifecycle

## Routing

For New Project, initial book import, Home language/narration changes, manifest
repair or exports, start at `home_ui_controller`, `project_options_service` and
`test_home_ui_controller.py` / `test_project_options_service.py`. Operation
Orchestration owns the artifact registry; individual workflows own generation.

## Purpose and boundaries

The Project Lifecycle component owns the operator-facing lifetime of an
AudioMancer project: creating or opening its flat workspace, validating and
repairing `project.json`, registering the source document, presenting Home-page
state, and producing external exports or whole-project snapshots. It also owns
the shared atomic writer used for critical project metadata.

### Responsibilities

- Create, validate, open, normalize, save, and metadata-repair project
  workspaces and manifests.
- Reject a create-project target that already exists as a file before directory
  inspection or mutation.
- Recover an otherwise valid project from an incompatible Chunking document by
  resetting Chunking and downstream derived state while preserving Source,
  Extraction, and Cleanup.
- Validate project names and project-relative artifact paths across supported
  platforms.
- Publish source-ready projects and import the first book into existing source-less
  projects, keeping registered source selection fixed in Home.
- Plan and apply confirmed language/narration changes with automatic persistence,
  exact artifact impacts and rollback after expected filesystem failures.
- Provide copy-first source replacement through the low-level importer API.
- Project detailed operation state into compact manifest summaries and derive
  Home-page workflow status and export readiness.
- Build coherent operation-and-downstream compact-summary resets for domain
  services that have already invalidated their centralized runtime artifacts.
- Coordinate Home-page create/open/repair, initial source import, automatically saved options,
  snapshot, and export actions.
- Render text/Markdown delivery projections and package ready voice or audio
  artifacts into external ZIP exports through temporary archives and atomic
  replacement, preserving an existing destination when creation fails.
- Create cancellable whole-project ZIP snapshots through a temporary archive
  and atomic replacement.
- Write critical text and JSON files through same-directory temporary files,
  `fsync`, and `os.replace`.

The component does not execute extraction, cleanup, chunking, translation,
character, voice, TTS, or audio-assembly operations. It reads those components'
artifacts only to present state, validate manifest evidence, and export current
results. Thread execution and cancellation primitives belong to
`operation-orchestration`.

### Implementation overview

The implementation boundary is:

- `05_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/import_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/project_options_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/persistence_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/project_export_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/project_snapshot_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/project_options_service.py` — creation and confirmed option publication.
- `05_Software/AudioMancer/tests/test_project_options_service.py` — impact, preservation, rollback and path containment.
- `05_Software/AudioMancer/src/audiomancer/services/home_presenter_service.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/home_page.py`

`project_workspace_service` builds and validates the manifest, resolves a
selected root or child path, rejects invalid project layouts, proposes
metadata-only repairs from artifact evidence, and saves compact operation
summaries. Ordinary manifest reads share one parse, identity, and project-path
validation boundary; repair keeps its identity-only read explicit before its
repair-specific normalization. Repaired manifests reuse the canonical
validator before applying narrator-field and downstream-operation resets, and
allowed operation summaries derive from the workflow-order prefix. Its public
`build_manifest_after_operation_reset` resets one
operation and every downstream compact summary, sets the matching readiness
stage, preserves explicit operation exceptions, and clears narrator shortcuts
when the reset makes them inapplicable. `import_service.import_source`
validates and copies the selected source through a same-project temporary file,
atomically promotes it to a collision-safe non-artifact name, removes only a
safely resolved previous project copy after the copy succeeds, and returns the
  manifest-ready source record. Reserved root-artifact names come from Operation
  Orchestration's central ownership registry. `persistence_service` provides
  public atomic replacement primitives for text, JSON, and complete byte
  payloads. Character Voices, Narrator, and Audio Blocks route generated-WAV
  byte publication through `write_bytes_atomic`, which creates parents, fsyncs
  the temporary payload, preserves an existing complete target on failure,
  removes its owned temporary file, and propagates the original `OSError`
  (`REQ-REL-ee8f9ed0`).

`project_export_service.create_archive_export` publishes each ready voice or
audio ZIP through the deterministic sibling `.<archive-name>.tmp`, closes the
complete archive before `os.replace`, and removes only that owned temporary file
when archive creation or replacement fails. The requested destination therefore
remains unchanged until a complete replacement is available
(`REQ-FUNC-efcaeeed`).

`project_options_service.create_project_with_source` stages a complete workspace
and copied source under a temporary sibling directory before publishing the
selected project folder. Cancelling a picker preserves the active project and
Cleanup draft. `import_initial_source` saves source registration and initial
options together, removing the new copy if manifest publication fails.

Home flushes the Translation page's existing debounced manual save before
planning, so both accepted and cancelled option changes retain the latest edit.
`plan_project_options_change` reads current project evidence and the centralized
operation-owned artifact registry without mutation. Home uses that exact plan
for localized confirmation and `apply_project_options_change`. A mode change
preserves text, translation, Book Analysis, character definitions, edited voice
prompts and preview text, and narrator profiles/selection/samples; it clears
character sample metadata and samples plus Speech Blocks through Audio Assembly.
Mode-only changes retain a legacy project's independently saved voice language.
A language change clears Translation and every later result plus Book Analysis,
keeping source and data through Chunking. The stage can move back to the last
retained boundary but cannot be promoted by an option edit. Same-value requests
leave project bytes unchanged, and programmatic combo refresh emits no change.

Application rechecks the manifest and replacement voice-plan bytes, stages
originals by rename, atomically publishes the new metadata, and restores originals
on expected failure. A restoration failure retains recovery originals under their
project-relative paths and reports the backup root. Project workers are blocked during changes. The source, target and
voice metadata remain project-local; external exports are preserved.

When strict Chunking loading reports incompatible persisted content,
`project_workspace_service.open_project` invokes the operation-runtime reset,
rewrites Chunking and downstream manifest summaries to `not_started`, retries
validation once, and returns `recovered_operations = ["chunking"]`. Filesystem
read failures fail the service-level open and do not trigger deletion;
`handle_open_project_requested` presents the resulting `OSError` through the
existing localized project-error warning without activating the project.
When the recovered result also requires a separate metadata repair, the Home
controller shows the localized Chunking recovery information before requesting
that repair decision. Declining the repair therefore leaves the project
unopened without hiding the completed reset; accepting it continues through
repair and activation without repeating the recovery information.

Project validation preflights the authoritative Speech Blocks and Audio Blocks
documents after upstream Chunking compatibility is established. A present
invalid block document returns `repair_required` with the stage-specific reset
instruction and preserves the damaged bytes until the operator confirms. The
confirmed repair resets that operation and its downstream artifacts through the
central runtime ownership boundary, rewrites the manifest to the preceding
ready stage, and then reopens normally. Direct activation also shows the same
project-error warning and keeps Home/export presentation non-crashing.

`REQ-UX-da3b47c4` contains expected workspace failures at the Home boundary.
Create, open, confirmed repair, and source-import service calls catch
`OSError` and `ValueError`, show `dialog.project_error_title` with the original
error text, and return before project activation, current window-state
replacement, or a success notification. Successful flows are unchanged.

`home_presenter_service` turns manifest summaries and the active operation into
read-only workflow rows. `HomeUiController` owns the UI orchestration and keeps
dialogs, project activation, automatic options, threaded snapshots, and external
save-path checks out of `HomeProjectPage`. The page owns Qt signals, controls,
translated labels, theme roles, busy state, and readiness display.

The create and open folder pickers start from the active project when one is
open — its parent folder for create, the project root itself for open — and from
`config.resolve_user_documents_root()` otherwise. They deliberately do not start
from `config.APP_ROOT`: that root owns read-only packaged resources, so for a
frozen build installed into a system location it would open the browser inside a
directory where any created project fails to write.

`project_export_service` reads ready downstream artifacts into format-neutral
export documents or curated audio ZIP files. `project_snapshot_service` walks
the active project, skips symlinks and AI transaction logs, archives files under
one top-level project folder, and replaces the requested destination only after
the temporary ZIP completes.

### Dependencies

Internal dependencies include `audiomancer.config`, time and logging services,
operation runtime/path-safety and reserved-artifact helpers, Extraction and
Cleanup reset-state helpers, UI state, token-usage normalization, and
the domain service loaders whose artifacts are exposed as exports. The Home
controller uses the shared operation runner for progress and cancellation.

External dependencies are Python standard-library filesystem, JSON, copying,
date/time, dataclass, regular-expression, and ZIP APIs. The UI boundary uses
PySide6 widgets, signals, dialogs, and models. Project data is stored in the
local filesystem; the component does not call a network service.

## Public interface

Inputs include operator-selected project and source paths, project names,
language and voice-mode selections, the active manifest, operation artifacts,
and export or snapshot destinations.

Outputs include the project root, root-level `project.json`, one copied source
file and its metadata, normalized or repaired manifest dictionaries, Home-page
status/readiness rows, external TXT/Markdown/ZIP exports, external project ZIP
snapshots, and operator-visible success, validation, or filesystem-error
messages. Export and snapshot deliverables are not registered as runtime project
artifacts.

## Invariants

Chunking completion evidence and text-chunk exports are projections of the one
strict `chunks_text.json` document. An incompatible document is regenerable
derived state: project open automatically removes Chunking-owned artifacts and
all downstream results, resets their manifest summaries at
`text_chunking_ready`, and retries validation exactly once. Source, Extraction,
`cleanup.json`, `clean_text.txt`, project identity, and options remain
unchanged. A wrapped `OSError` is re-raised without reset; the Home controller
catches that service error and shows `dialog.project_error_title` with the
original error text. Successful recovery is reported only after Home activates
the project.

Cleanup completion evidence is available only when
`text_cleanup_service.load_cleanup_document` accepts the strict persisted
document. `CleanupDocumentError` is a `ValueError`, so malformed progress or
completed blocking-quality data is treated as unavailable completion evidence.
Project opening then returns through its existing validation flow with `ok` or
`repair_required`, depending on whether the remaining evidence implies a
concrete manifest normalization, instead of propagating a document-shape
exception.

Speech Blocks and Audio Blocks completion evidence is projected only from their
strict authoritative documents. Missing documents remain ordinary not-started
evidence; existing unreadable or invalid documents produce an explicit
operator-approved stage-reset request and are never normalized into absence.

Narrator completion evidence and exports are projections of the strict
`narrator_voice.json` document. The selected profile's language, inline sample
metadata, and canonical `audio_narator_<profile_id>.wav` are resolved at read
time. The public export label is `Narrator Voice`, including its derived
default archive filename, without changing persisted narrator identifiers or
module and localization-key names (`REQ-FUNC-5e008e3b`). Narrator reset owns
only the current document, canonical profile WAVs,
and `log_ai_narrator_profiles_*.log`. Project snapshots include the document
and WAVs while excluding AI transaction logs.

The root manifest contains project identity and timestamps, `current_stage`,
`source_document`, compact `operations`, persisted language/voice options and a legacy options-lock flag,
audio-assembly settings, and notes. `source_document` contains
`original_name`, `stored_relative_path`, `file_type`, `imported_at`, and
`size_bytes`. Compact operation summaries contain `status`, progress values,
`mode`, and `warning_count`; detailed checkpoints and outputs remain in their
domain artifacts.

Audio Assembly owns the public settings defaults and normalization rules.
Project manifest creation, validation, saving/loading, and repair call those
exact functions through local imports, retaining one set of bounds and invalid
input behavior without introducing the existing reverse-service import cycle
(`REQ-FUNC-4cc6cf8c`).

`current_stage` is the highest workflow milestone the project has reached, not a
cursor for where the operator currently is. `sync_manifest_operation_summary`
therefore only promotes it: a lower `current_stage` argument is ignored. Lowering
it there would strand completed downstream summaries above the stage, and that
contradiction is what makes a finished project offer a metadata repair on every
later open. Invalidating downstream work is the job of the explicit reset path,
which clears domain artifacts and operation summaries together.

For `REQ-FUNC-ccc76f34` and `REQ-FUNC-e45d3577`, this service is the sole
operation-summary writer used by workflow controllers after persisted
transitions. It first reloads `project.json`, so it retains fields newer than a
window snapshot, updates only the requested compact summary, promotes but never
demotes the stage, saves, and returns the exact reloaded manifest for the
controller to display.

Project-relative paths must be relative, contain no parent traversal, and
resolve inside the active project even when symlinks are present. New projects
use a flat root, with generated audio permitted under `audio_blocks/` and final
assembly output under `audiobook/`; unsupported numbered workflow folders are not
accepted.
Low-level workspace creation accepts an absent target or an empty target directory. A non-empty
directory raises `FileExistsError`; an existing file raises `FileExistsError`
with `Project path already exists as a file: <path>` and remains unchanged.

Supported source suffixes are `.txt`, `.pdf`, `.rtf`, `.docx`, `.odt`, `.md`,
and `.epub`. Atomic JSON uses UTF-8, two-space indentation, unescaped Unicode,
and a trailing newline by default. Export/snapshot paths must be outside the
active project. Snapshot members share one top-level folder named after the
project root; AI transaction logs and symlinks are excluded.

`REQ-FUNC-b1f49831` defines the low-level importer copy-first replacement boundary.
The selected source and previous manifest path are validated before mutation;
the new file is copied and atomically promoted before the previous stored file
is deleted. A copy failure removes its incomplete temporary file and leaves the
previous source, manifest bytes, generated artifacts, and operation summaries
unchanged. Generated-artifact names are reserved case-insensitively, so a
supported source named `extracted_text.txt` or `clean_text.txt` receives the
normal numeric suffix instead of occupying a reset-owned path.

`REQ-FUNC-3278aae6` makes the low-level importer's stored-source selection an
exact identity no-op. Home rejects a new import once a book is registered,
independently of the legacy options-lock flag. A different same-named external
file remains a collision-safe replacement at the low-level importer API.

`REQ-UX-e4b0be69` keeps `_refresh_summary_labels()` as the source-status
projection. Changing UI language retains the absent or fixed-book state,
source name, styling and control availability.

`REQ-FUNC-cfd0a750` uses the shared append-only extension helper before export
and snapshot containment checks. It compares complete filenames
case-insensitively and appends the required extension only when absent, so
`Dune vol. 2` becomes `Dune vol. 2.zip` and `archive.ZIP` remains unchanged.

`REQ-FUNC-2ab78634` defines canonical Cleanup publication as a synchronized
transition. Cleanup first uses Operation Orchestration to delete Chunking and
all downstream artifacts, atomically publishes its text and metadata, then
reloads the manifest and uses `build_manifest_after_operation_reset` to default
the same downstream summaries. The completed Cleanup summary and
`text_chunking_ready` stage are saved in that single manifest write, preserving
the source, Extraction, project options, and unrelated manifest fields.

### Workflow integration

The application shell delegates project and Home actions to
`home_ui_controller`. A successful source-ready creation, open or repair activates
the project, updates the Home summary and enables workflow pages. The source book
is fixed after registration. Language and narration mode remain editable while
idle and persist automatically after any required actual-impact confirmation.
Existing projects display their saved options without an option-change reset.

Downstream workflow components persist detailed artifacts and compact manifest
summaries. Project open may use trustworthy artifacts to propose a metadata-only
summary/stage repair. Its sole automatic domain reset is the bounded incompatible
Chunking recovery described above. Home exports and snapshots read the current
local state without mutating the active project.

Successful automatic Cleanup publication and manual cleaned-text save therefore
reopen with `status="ok"`, not a repair request caused by stale downstream
summaries. A failed manifest write propagates to Cleanup and is never converted
into a successful transition.

### Usage

```python
from audiomancer.services import project_options_service, project_workspace_service

project_root, manifest = project_options_service.create_project_with_source(
    "Book5_CAL_CAL", "D:/Projects", "D:/Books/story.txt",
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

### Verification

Primary automated coverage:

- `05_Software/AudioMancer/tests/test_project_workspace_service.py`
- `05_Software/AudioMancer/tests/test_import_service.py`
- `05_Software/AudioMancer/tests/test_persistence_service.py`
- `05_Software/AudioMancer/tests/test_project_export_service.py`
- `05_Software/AudioMancer/tests/test_project_snapshot_service.py`
- `05_Software/AudioMancer/tests/test_home_presenter_service.py`
- `05_Software/AudioMancer/tests/test_home_ui_controller.py`
- `05_Software/AudioMancer/tests/test_home_page.py`
- `05_Software/AudioMancer/tests/test_main_window_project_flow.py`
- `05_Software/AudioMancer/tests/test_main_window_home_exports.py`
- `05_Software/AudioMancer/tests/test_atomic_io_contracts.py`

The Home controller suite verifies that expected create, open, confirmed-repair,
and source-import `OSError` failures use the localized project-error warning,
preserve the current project and manifest, and do not report success. Existing
open coverage also exercises `ValueError`. The main-window project-flow suite verifies that Chunking
recovery information precedes both accepted and declined follow-up repair
decisions and appears exactly once. The workspace-service suite separately
verifies that a Chunking `OSError` propagates without reset or deletion.
Source-import regressions inject a partial copy failure and compare the complete
project tree byte-for-byte, exercise current and case-variant reserved names,
and preserve the complete prior project after a failed low-level copy. Home
controller tests reject replacement of registered books while preserving all
root artifacts, generated audio, compact summaries and source registration.
They also verify resolved same-source no-ops, different same-named replacements,
and byte-for-byte preservation through the Home controller. Home-page tests
cover fixed-source availability and saved option selectors in English and Romanian. Export and snapshot tests
cover dotted, extensionless, lowercase, and uppercase destination names at both
controller and service boundaries.
`test_cleanup_service.py` covers the shared manifest-reset builder through both
Cleanup publication paths, including real downstream artifacts, completed
summaries, preservation checks, coherent reopen, and injected manifest-write
failures.
`test_workflow_controller_service.py` verifies that controller callers reach the
same disk-based writer, preserve newer manifest fields and completed downstream
summaries, ignore a lower requested stage, and display the final persisted
manifest.

After changes, run those focused tests with `uv run pytest`, plus
`uv run python -m py_compile` and `uv run ruff check` on changed files. Changes
to persistence or path containment require the atomic I/O and unsafe-path cases
as part of focused validation.

### Operational limits

- Atomic writes are last-replacement-wins and do not provide cross-process
  locking or backup rotation.
- Interactive project repair is metadata-only except for operator-confirmed
  Extraction, Speech Blocks, and Audio Blocks recovery. Incompatible Chunking
  remains the sole automatic domain reset.
- Export formats are TXT/Markdown for readable projections and ZIP for voice or
  assembly artifacts; PDF export is not implemented.
- Snapshots are filesystem snapshots taken at start time, not transactional
  captures; the UI prevents starting them while another operation is active.
- No last-used project parent folder is persisted. Once the operator closes the
  application, the create and open dialogs start again at the documents root
  rather than wherever their projects actually live.

### Supporting Book Analysis operation

`book_analysis` is included in project manifest operation summaries but not in
the workflow operation order or stage map. Manifest repair preserves supporting
summaries at every stage. Its start, failure, cancellation, completion, and
reset never promote or lower `current_stage`; explicit reset clears only its
summary and owned files. Upstream Chunking changes preserve its completed
report so freshness can be derived and shown as stale. Confirmed Home language
changes reset its document, AI logs and compact summary; narration-mode changes
preserve its report.

## Change map

| Change requested | Start with | Focused verification |
|---|---|---|
| Creation, automatic options and confirmed resets | project_options_service, home_ui_controller | test_project_options_service.py, test_home_ui_controller.py |
| Manifest validation and repair | project_workspace_service | test_project_workspace_service.py |
| Source copy safety | import_service | test_import_service.py |
| Exports and snapshots | project_export_service, project_snapshot_service | export/snapshot service and controller tests |

## Key behaviors

- `REQ-FUNC-b27e4e87`, `REQ-FUNC-ad79f7c7`, `REQ-FUNC-f0999e62`: source-ready creation and cancellation/failure preservation.
- `REQ-FUNC-1c28e0bf`, `REQ-FUNC-348f0aeb`, `REQ-FUNC-c3d29114`: autosaved options with exact mode/language reset boundaries.
- `REQ-FUNC-2083d3a1`: confirmed-reset failures restore originals; recovery failures retain their backup path.
- `REQ-FUNC-eb5d81aa`, `REQ-FUNC-c132a7bf`, `REQ-UX-e4b0be69`: source presence gates import while Home options remain editable when idle.
- `REQ-FUNC-3500196d`, `REQ-FUNC-3401b07e`, `REQ-FUNC-ec10fa36`: cancellation/no-op, refresh and busy guards.

## Files

From the adopted component map:

- `05_Software/AudioMancer/src/audiomancer/services/home_presenter_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/import_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py` - shared append-only destination-extension normalization.
- `05_Software/AudioMancer/src/audiomancer/services/persistence_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/project_export_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/project_snapshot_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py` - canonical disk-based operation-summary writer and promotion-only workflow-stage owner.
- `05_Software/AudioMancer/src/audiomancer/services/text_cleanup_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/home_page.py`
- `05_Software/AudioMancer/tests/test_atomic_io_contracts.py`
- `05_Software/AudioMancer/tests/test_home_page.py`
- `05_Software/AudioMancer/tests/test_home_presenter_service.py`
- `05_Software/AudioMancer/tests/test_home_ui_controller.py`
- `05_Software/AudioMancer/tests/test_import_service.py`
- `05_Software/AudioMancer/tests/test_main_window_home_exports.py`
- `05_Software/AudioMancer/tests/test_main_window_project_flow.py`
- `05_Software/AudioMancer/tests/test_persistence_service.py`
- `05_Software/AudioMancer/tests/test_project_export_service.py`
- `05_Software/AudioMancer/tests/test_project_snapshot_service.py`
- `05_Software/AudioMancer/tests/test_project_workspace_service.py`
- `05_Software/AudioMancer/tests/test_workflow_controller_service.py` - controller-to-Project-Lifecycle synchronization regressions.
- `05_Software/AudioMancer/tests/test_cleanup_service.py`
