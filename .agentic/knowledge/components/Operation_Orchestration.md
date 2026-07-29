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
- Run worker callables on a dedicated `QThread`, marshal progress/success/
  failure/cancellation back to the UI thread, and safely handle shutdown.
- Present the modal operation-progress dialog, including localized messages,
  token usage, cancellation, and final success/failure state.
- Request the operator completion beep when an operation ends on its own, so an
  operator who left the machine is told the run is over.
- Synchronize persisted operation state into the project manifest and resolve
  enabled AI profiles for page controllers.

It does not define individual workflow algorithms, domain artifact schemas,
or the project workspace/manifest persistence implementation.

## 3. Implementation Overview

`operation_runtime_service` is the low-level runtime boundary. It validates
relative paths against traversal and absolute-path forms (including Windows
forms), owns standard `{status, progress_current, progress_total, mode,
warning_count, metadata, resume_checkpoint}` state payloads, and resets only
the configured root-level artifacts for affected operation kinds.

`workflow_impact_service` converts workflow order and stable-ID policies into
full and selective reset summaries. It can preserve selected operations,
resequence records without changing stable IDs, and only collects/deletes audio
paths that resolve inside the active project. It refreshes manifest operation
summaries from completed artifacts.

`operation_runner_controller` owns `ThreadedOperationWorker` and its UI bridge.
It disables conflicting project switches, creates the shared dialog, routes
signals to UI-thread handlers, clears all bookkeeping after thread completion,
and cooperatively waits during close. Its success and failure handlers also call
`misc_ui_controller.play_completion_beep(...)`; the cancellation handler
deliberately does not, because the operator requested the cancellation and is
already present. `OperationProgressDialog` is the visible
progress/token/cancel surface. `workflow_controller_service` is the small
controller-facing facade for starting operations, syncing a manifest from
disk, and choosing an enabled AI profile.

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

Chunking reset owns `chunks_text.json`, the obsolete
`chunking_checkpoint.json`, `chunking_report.json`, `chunking_state.json`, and
matching `log_ai_chunking_*.log` files. When reset begins at Chunking with
`include_current=True`, the same allowlisted deletion proceeds through every
configured downstream operation; Extraction and Cleanup artifacts are outside
that scope.

## 7. Workflow Integration

Text extraction/cleanup, chunking, translation, character, voice, speech, TTS,
and assembly controllers use this component to start/cancel work and invalidate
downstream outputs. The App Shell invokes its shutdown path. Project Lifecycle
owns the manifest itself, invokes the scoped reset when project-open detects an
incompatible Chunking document, and projects individual operation state into
the manifest after an operation writes its artifacts.

## 8. Usage

Domain controllers call `workflow_controller_service.start_operation(...)` with
a worker callable and success/failure/cancel handlers. Workers call
`emit_progress_update(...)` and `raise_if_cancelled(...)`, then persist their
domain artifacts through their own services or the operation-runtime helpers.
Use `build_selective_invalidation_summary(...)` before invalidating edited
speech data, and `sync_manifest_operation_from_disk(...)` after a persisted
state transition.

## 9. Validation And Tests

Primary automated coverage:

- `test_operation_runtime_service.py` covers progress, common state/artifact
  IO, malformed/missing data handling, path containment, default state, and
  reset preservation, including obsolete Chunking checkpoint deletion.
- `test_workflow_impact_service.py` and `test_workflow_order_consistency.py`
  cover ordering, stable identity, full/selective reset, safe artifact deletion,
  assembly reset, and manifest refresh.
- `test_operation_runner_controller.py`,
  `test_workflow_controller_service.py`, and
  `test_main_window_operation_shutdown.py` cover success/failure/cancellation,
  active-operation suppression, profile resolution, manifest synchronization,
  and close-time shutdown, including that a completion beep is emitted on
  success and failure but never on cancellation or when the preference is off.
- `test_operation_progress_dialog.py` directly verifies the visible localized
  title/cancel label, clamped progress, status replacement, and localized token
  usage rendering.

After changes, run the focused modules above with `uv run pytest`, plus
`uv run python -m py_compile` and `uv run ruff check` on changed files.

## 10. Limitations And Future Work

The component intentionally relies on window private attributes as its current
Qt integration contract; a future UI architecture may replace that with a
typed operation-session object. It cannot forcibly terminate a noncooperative
worker: shutdown waits only for the configured timeout after setting the
cancellation event. Domain services remain responsible for checkpoints and
for translating their own failure state into operator-facing outcomes.
