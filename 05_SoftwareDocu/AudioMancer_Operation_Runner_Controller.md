<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Operation Runner Controller

## 1. Purpose

Provides the shared threaded modal-operation runner for `AudioMancer` desktop
workflows that can take long enough to make the Qt window appear stuck.

It lets page controllers keep all widget updates on the Qt UI thread while
service calls execute on a dedicated `QThread`.

## 2. Responsibilities

- start one long-running modal workflow on a `QThread`
- move a `QObject` worker to that thread
- expose progress, success, failure, cancellation, and finish signals
- create and update the shared modal progress dialog from the UI thread
- set and clear page busy state through controller-supplied callbacks
- disable project-switching toolbar actions while a worker is active
- preserve the existing single-active-operation guard
- expose cooperative cancellation through a `threading.Event`
- support bounded shutdown cancellation when the main window is closed
- clear `MainWindow` operation bookkeeping after the thread finishes and
  schedule the UI bridge for deferred Qt deletion

It does not own service-level artifacts, retry policy, provider polling,
VoiceWeaver request behavior, or operation-specific manifest synchronization.
Those remain in the existing services and page controllers.

## 3. Implementation Overview

The component is implemented in:

- `04_Software/AudioMancer/src/audiomancer/ui/controllers/operation_runner_controller.py`

Main public API:

- `ThreadedOperationWorker`
- `start_threaded_operation(...)`
- `request_operation_cancel(window)`
- `cancel_active_operation_for_shutdown(window, wait_timeout_ms=3000)`

Runtime flow:

1. A page controller validates prerequisites and gathers UI-only inputs.
2. The controller calls `start_threaded_operation(...)` with operation labels,
   a service worker callable, page busy callbacks, and operation-specific
   success, failure, and cancellation handlers.
3. The runner creates a `threading.Event`, `QThread`, and
   `ThreadedOperationWorker`.
4. The worker receives `project_root`, a manifest snapshot, a progress callback,
   and `cancel_requested=cancel_event.is_set`.
5. Worker progress is emitted as Qt signal payloads.
6. The UI thread updates the modal progress dialog and invokes the supplied
   terminal handler.
7. When the worker finishes, the thread quits and the runner clears
   `_active_operation_*`, `_operation_cancel_event`, and progress-dialog state,
   then calls `deleteLater()` on the operation UI bridge.
8. `MainWindow.closeEvent(...)` calls
   `cancel_active_operation_for_shutdown(...)` before accepting application
   shutdown. The helper requests cooperative cancellation and processes Qt
   events until the runner clears active-operation state or the bounded timeout
   expires. If the worker remains active, the close event is ignored.

## 4. Dependencies

Internal dependencies:

- `audiomancer.services.operation_runtime_service`
- `audiomancer.ui.controllers.misc_ui_controller`
- `audiomancer.ui.main_window.MainWindow` operation fields

External dependencies:

- `PySide6.QtCore.QObject`
- `PySide6.QtCore.QEventLoop`
- `PySide6.QtCore.QThread`
- `PySide6.QtCore.Signal`
- `PySide6.QtCore.Slot`
- `PySide6.QtWidgets.QApplication`
- Python standard library `threading.Event`, `pathlib.Path`, and `time`

## 5. Inputs And Outputs

Inputs:

- active `MainWindow`
- `operation_kind`
- `operation_name`
- `initial_message`
- worker callable accepting `project_root`, `manifest`, `progress_callback`,
  and `cancel_requested`
- controller-supplied `set_busy`, `success_handler`, `failure_handler`, and
  `cancel_handler`
- `cancellable` flag for the modal progress dialog

Outputs and state changes:

- progress dialog creation and updates
- `_active_operation_kind`
- `_active_operation_name`
- `_operation_cancel_requested`
- `_operation_cancel_event`
- `_active_operation_thread`
- `_active_operation_worker`
- `MainWindow` New Project and Open Project action enabled state
- controller-specific success, failure, or cancellation side effects
- deferred deletion of the operation UI bridge after finish cleanup

## 6. Data Contracts

Worker progress is emitted as a dictionary with these fields:

- `progress_current`
- `progress_total`
- `percent`
- `message`
- `token_usage`

Cancellation remains cooperative. `request_operation_cancel(window)` sets both
`window._operation_cancel_requested` and the thread-safe cancel event. Services
must still check their existing `cancel_requested` callback before they stop.

Shutdown cancellation uses the same cancel event. The runner does not terminate
threads forcibly; it waits only for the configured bounded timeout while Qt
events are processed so queued worker, thread, and UI-bridge cleanup slots can
run.

The runner catches
`audiomancer.services.operation_runtime_service.OperationCancelledError` as the
canonical cancellation exception.

## 7. Workflow Integration

The runner is used by the modal long workflows in:

- `text_cleanup_ui_controller.py`
- `text_chunking_ui_controller.py`
- `ai_translation_ui_controller.py`
- `characters_ui_controller.py`
- `speech_blocks_ui_controller.py`
- `audio_blocks_ui_controller.py`
- `narator_voice_ui_controller.py`
- `character_voices_ui_controller.py`
- `main_window.py` for application-close cancellation and close rejection while
  a worker is still active

Operation-specific controllers still own:

- prerequisite validation
- confirmation dialogs
- profile or editor payload collection
- manifest synchronization
- page refreshes
- final status messages
- warning dialogs
- downstream invalidation

## 8. Usage

Typical controller integration:

```python
operation_runner_controller.start_threaded_operation(
    window,
    "character_discovery",
    operation_name,
    initial_message,
    worker_callable,
    set_busy=lambda is_busy: window._characters_page.set_busy(is_busy),
    success_handler=lambda result: _handle_discovery_success(window, result),
    failure_handler=lambda error: _handle_discovery_failure(window, error),
    cancel_handler=lambda message: _handle_discovery_cancelled(window, message),
)
```

Worker callables keep the existing service contract:

```python
def worker_callable(project_root, manifest, progress_callback=None, cancel_requested=None):
    return service.run(
        project_root,
        manifest,
        progress_callback=progress_callback,
        cancel_requested=cancel_requested,
    )
```

## 9. Validation And Tests

Focused tests:

- `04_Software/AudioMancer/tests/test_operation_runner_controller.py`
- `04_Software/AudioMancer/tests/test_main_window_operation_shutdown.py`
- migrated controller tests for cleanup, chunking, translation, character
  discovery, speech blocks, audio blocks, narrator samples, and character
  voice samples

Minimum validation after runner changes:

```powershell
uv run python -m py_compile src/audiomancer/ui/controllers/operation_runner_controller.py
uv run python -m py_compile src/audiomancer/ui/main_window.py
uv run ruff check src/audiomancer/ui/controllers/operation_runner_controller.py --fix
uv run ruff check src/audiomancer/ui/main_window.py --fix
uv run ruff format src/audiomancer/ui/controllers/operation_runner_controller.py
uv run ruff format src/audiomancer/ui/main_window.py
uv run pytest tests/test_operation_runner_controller.py
uv run pytest tests/test_main_window_operation_shutdown.py
```

## 10. Limitations And Future Work

- Cancellation is cooperative. Blocking HTTP calls may finish their current
  request before a service observes `cancel_requested`.
- Closing the main window during a non-cooperative operation requests
  cancellation and rejects the close after the bounded wait; the operator must
  wait for the worker to finish cleanup or request close again after it stops.
- The runner uses one dedicated `QThread` per operation rather than a
  `QThreadPool`.
- The runner intentionally supports only one active long operation at a time
  because the rest of the UI state model assumes that invariant.
