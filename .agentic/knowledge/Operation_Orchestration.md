<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Operation Orchestration

## 1. Purpose

Operation Orchestration supplies the shared runtime contract for cancellable
workflow work. It owns safe project-local operation artifacts and state
envelopes, progress reporting, selective downstream invalidation, and the Qt
worker lifecycle used by all long-running workflow pages.

## 2. Responsibilities

- Resolve and validate project-relative artifact paths, read optional JSON,
  persist operation state/artifacts atomically, and construct default compact
  state envelopes. Speech Blocks and Audio Blocks own single authoritative
  documents instead of separate state artifacts, so no default state file is
  initialized for them and a missing document reads as not-started.
- Calculate bounded progress payloads and provide cooperative cancellation.
- Define ordered full-reset and selective-invalidation impacts, preserve stable
  identities, and delete only operation-owned root artifacts, AI logs, and safe
  targeted audio/assembly files.
- Publish the exact root-level artifact file names owned by the reset registry
  so source storage cannot claim a generated-artifact path.
- Run worker callables on a dedicated `QThread`, marshal progress/success/
  failure/cancellation back to the UI thread, and safely handle shutdown.
- Present the modal operation-progress dialog, including factory-applied current
  language, localized messages and token usage, cooperative cancellation, and
  final success/failure state.
- Request the operator completion beep when an operation ends on its own, so an
  operator who left the machine is told the run is over.
- Synchronize persisted operation state into the project manifest and resolve
  enabled AI profiles for page controllers.
- Keep operation artifact ownership centralized while Project Lifecycle owns
  the corresponding compact-summary reset construction.

It does not define individual workflow algorithms, domain artifact schemas,
or the project workspace/manifest persistence implementation.

## 3. Implementation Overview

`operation_runtime_service` is the low-level runtime boundary. It validates
relative paths against traversal and absolute-path forms (including Windows
forms), owns standard `{status, progress_current, progress_total, mode,
warning_count, metadata, resume_checkpoint}` state payloads, and resets only
the configured root-level artifacts for affected operation kinds.
`reserved_project_artifact_file_names()` exposes the same current and
reset-only legacy file-name registry as an immutable set; consumers therefore
do not duplicate the downstream deletion lists.

`workflow_impact_service` converts workflow order and stable-ID policies into
full and selective reset summaries. It can preserve selected operations,
resequence records without changing stable IDs, and only collects/deletes audio
paths that resolve inside the active project. It refreshes manifest operation
summaries from completed artifacts.

`operation_runtime_service.reset_operation_data` remains the sole artifact-list
owner for full Cleanup publication invalidation. It does not edit
`project.json`; after the file reset and Cleanup publication succeed, Text
Cleanup asks Project Lifecycle's shared manifest-reset builder to reset the
matching compact summaries in one manifest value.

`operation_runner_controller` owns `ThreadedOperationWorker` and its UI bridge.
It disables conflicting project switches, creates the shared dialog, routes
signals to UI-thread handlers, clears all bookkeeping after thread completion,
and cooperatively waits during close. Its success and failure handlers also call
`misc_ui_controller.play_completion_beep(...)`; the cancellation handler
deliberately does not, because the operator requested the cancellation and is
already present. `misc_ui_controller.create_progress_dialog` resolves the
optional window settings payload and applies the current language before
`OperationProgressDialog.start()` renders an operation title, so every
production caller receives the same localized title, Cancel label, and later
token-usage text. `OperationProgressDialog` is the visible progress/token/cancel
surface: while active, its Cancel control, Escape rejection, and title-bar close
request share one idempotent cooperative-cancellation path that leaves the
application-modal dialog visible; terminal finish/fail paths deactivate and hide
it, and shared clearing deletes its reference. `workflow_controller_service` is the small
controller-facing facade for starting operations, syncing a manifest from
disk, and choosing an enabled AI profile. For `REQ-FUNC-ccc76f34` and
`REQ-FUNC-e45d3577`, it loads the persisted operation state but delegates the
summary and stage update to Project Lifecycle's canonical manifest writer; it
then displays the exact manifest reloaded from disk. A missing state with no
stage request causes no manifest write but still refreshes the window.

The dialog stays active from `start()` until `finish()` or `fail()` begins its
terminal hide path. A dismissal gesture is a cooperative request only: it never
means the worker has stopped, so the shared controller remains responsible for
hide/clear after the worker reaches a terminal signal. Non-cancellable active
dialogs ignore Escape and title-bar close requests. MainWindow retains ownership
of application-close protection and the operation runner retains ownership of
worker cancellation and shutdown waiting.

## 4. Dependencies

Internal dependencies include `audiomancer.config`, atomic JSON persistence,
logging, project-workspace manifest helpers, Text Cleanup's normalized manifest
operations, Home presentation, UI state, and common dialog helpers. All domain
controllers depend on this component for operations but remain owners of their
worker callables and post-operation effects.

External dependencies are PySide6 `QThread`, signals/slots, dialogs, and the
Python filesystem/JSON/runtime primitives. No provider SDK is used directly.

## 5. Inputs And Outputs

Inputs are an active project root and manifest, stable operation kind, optional
state/artifact paths, cancellation event, worker callable, and UI callbacks.
Outputs include root-level JSON artifacts, compact state payloads, impact
summaries, safe deletion summaries, signal payloads with bounded percent and
optional token usage, and refreshed manifest/page state.

## 6. Data Contracts

Operation kinds must be present in `config.WORKFLOW_OPERATION_ORDER`. Relative
artifact paths must be nonempty, nonabsolute, and traversal-free; conversion
to a manifest-relative string rejects paths outside the project. Operation
state uses the shared compact envelope; workflow-specific state belongs in
`metadata` and resumable work in `resume_checkpoint`.

Progress payloads contain a clamped `percent`, a message, and optional token
usage. Selective invalidation identifies blocks by stable identity fields, not
display sequence numbers. Artifact collection/deletion rejects paths outside
the active project and requires exact affected identities where appropriate.

Chunking reset owns `chunks_text.json` and matching
`log_ai_chunking_*.log` files. When reset begins at Chunking with
`include_current=True`, the same allowlisted deletion proceeds through every
configured downstream operation; Extraction and Cleanup artifacts are outside
that scope. `REQ-FUNC-2ab78634` requires automatic and manual Cleanup
publication to pair this exact artifact reset with the Project Lifecycle
compact-summary reset before reporting success.

Root-level operation artifact names are reserved independently of whether a
file currently exists. Project Lifecycle compares them case-insensitively when
choosing a stored source name, which is conservative on case-sensitive hosts
and consistent with Windows behavior.

The shared `append_required_extension` helper preserves a complete requested
filename, compares extensions case-insensitively, and appends only a missing
required extension. Project Lifecycle uses it for export and snapshot paths
before containment checks, avoiding dotted-name truncation.

## 7. Workflow Integration

Text extraction/cleanup, chunking, translation, character, voice, speech, TTS,
and assembly controllers use this component to start/cancel work and invalidate
downstream outputs. The App Shell invokes its shutdown path. Project Lifecycle
owns the manifest itself, invokes the scoped reset when project-open detects an
incompatible Chunking document, uses the root-artifact registry to choose safe
source names, and projects individual operation state into the manifest after
an operation writes its artifacts. Text Cleanup uses the same scoped Chunking
reset for both automatic and manual canonical-text publication, then delegates
summary reset construction to Project Lifecycle before success is returned.

## 8. Usage

Domain controllers call `workflow_controller_service.start_operation(...)` with
a worker callable and success/failure/cancel handlers. Workers call
`emit_progress_update(...)` and `raise_if_cancelled(...)`, then persist their
domain artifacts through their own services or the operation-runtime helpers.
Use `build_selective_invalidation_summary(...)` before invalidating edited
speech data, and `sync_manifest_operation_from_disk(...)` after a persisted
state transition. That helper does not reconstruct a manifest from the window
snapshot: Project Lifecycle reloads the current file, refreshes the requested
summary, and only promotes a requested workflow stage.

## 9. Validation And Tests

Primary automated coverage:

- `test_operation_runtime_service.py` covers progress, common state/artifact
  IO, malformed/missing data handling, path containment, default state, and
  reset preservation.
- `test_workflow_impact_service.py` and `test_workflow_order_consistency.py`
  cover ordering, stable identity, full/selective reset, safe artifact deletion,
  assembly reset, and manifest refresh.
- `test_operation_runner_controller.py`,
  `test_workflow_controller_service.py`, and
  `test_main_window_operation_shutdown.py` cover success/failure/cancellation,
  active-operation suppression, profile resolution, manifest synchronization
  from the freshest disk payload, monotonic stage preservation, the missing
  operation-state path, and final window payload delivery,
  and close-time shutdown, including that a completion beep is emitted on
  success and failure but never on cancellation or when the preference is off.
- `test_operation_progress_dialog.py` directly verifies runtime localized
  title/cancel-label/token-usage rendering, active Escape and close requests,
  cancellation idempotence, non-cancellable dismissal handling, and terminal
  hide behavior; `test_misc_ui_controller.py` verifies the production factory
  applies Romanian before start, retains English fallback behavior, and clears
  the shared dialog reference.
- `test_cleanup_service.py` verifies the centralized Chunking-and-downstream
  reset removes every current artifact class in both Cleanup publication paths
  while the paired manifest summaries are reset coherently.

After changes, run the focused modules above with `uv run pytest`, plus
`uv run python -m py_compile` and `uv run ruff check` on changed files.

## 10. Limitations And Future Work

The component intentionally relies on window private attributes as its current
Qt integration contract; a future UI architecture may replace that with a
typed operation-session object. It cannot forcibly terminate a noncooperative
worker: shutdown waits only for the configured timeout after setting the
cancellation event. Domain services remain responsible for checkpoints and
for translating their own failure state into operator-facing outcomes.

## Files

From the adopted component map:

- `04_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py` - shared runtime artifact, path-containment, and append-only extension helpers.
- `04_Software/AudioMancer/src/audiomancer/services/workflow_impact_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/operation_progress_dialog.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/operation_runner_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/workflow_controller_service.py` - controller facade that delegates manifest summary and stage persistence to Project Lifecycle.
- `04_Software/AudioMancer/tests/test_main_window_operation_shutdown.py`
- `04_Software/AudioMancer/tests/test_operation_progress_dialog.py`
- `04_Software/AudioMancer/tests/test_misc_ui_controller.py`
- `04_Software/AudioMancer/tests/test_operation_runner_controller.py`
- `04_Software/AudioMancer/tests/test_operation_runtime_service.py`
- `04_Software/AudioMancer/tests/test_cleanup_service.py`
- `04_Software/AudioMancer/tests/test_workflow_controller_service.py` - controller synchronization and final-window-manifest regressions.
- `04_Software/AudioMancer/tests/test_workflow_impact_service.py`
- `04_Software/AudioMancer/tests/test_workflow_order_consistency.py`
