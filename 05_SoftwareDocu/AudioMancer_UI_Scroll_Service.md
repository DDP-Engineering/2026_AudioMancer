<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer UI Scroll Service

## 1. Purpose

Provides the shared mouse-wheel scroll-step behavior for the AudioMancer Qt
interface.

The service lets the Settings dialog control how many scrollbar single-steps
common scroll panes move for each physical mouse-wheel notch.

## 2. Responsibilities

- install one application-wide Qt event filter
- apply `ui_scroll_steps_per_wheel_notch` to `QAbstractScrollArea` viewports
- support common text editors, list widgets, and scroll areas without changing
  each page class
- preserve normal Ctrl+wheel behavior for controls that use it for zoom or
  platform-specific shortcuts
- clamp in-memory filter values to the supported `1..5` range

It does not own settings persistence, Settings dialog widgets, theme styling,
or page-specific selection state.

## 3. Implementation Overview

The component is implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/ui_scroll_service.py`

Main public API:

- `ScrollStepEventFilter`
- `install_global_scroll_step_filter(application, scroll_steps_per_notch)`

Runtime flow:

1. Application startup loads validated settings.
2. `audiomancer.app.main()` installs the global scroll-step filter before the
   main window is built.
3. Settings Apply/OK calls the settings controller, which reconfigures the
   already-installed filter with the current settings payload.
4. Wheel events on scroll-area viewports move the vertical scrollbar by the
   configured number of single-steps per complete wheel notch.

## 4. Dependencies

Internal dependencies:

- `04_Software/AudioMancer/src/audiomancer/config.py`

External dependencies:

- `PySide6.QtCore`
- `PySide6.QtWidgets`

## 5. Inputs And Outputs

Inputs:

- a running `QApplication`
- validated or in-memory scroll-step value from settings
- Qt wheel events delivered to scroll-area viewports

Outputs:

- an installed `ScrollStepEventFilter` retained on the application object
- adjusted scroll-bar values for handled wheel events

The service does not write files or emit operator-facing text.

## 6. Data Contracts

Supported setting:

- `ui_scroll_steps_per_wheel_notch`

Supported range:

- minimum: `1`
- maximum: `5`
- default: `1`

The settings service repairs invalid persisted values to the default. The scroll
service also clamps runtime values defensively before applying them.

## 7. Workflow Integration

The service is runtime UI infrastructure. It is used by:

- `audiomancer.app.main()` during startup
- `settings_ui_controller.apply_current_ui_settings()` after Settings Apply/OK

The Settings page exposes the operator-facing numeric control, while
`settings_service` owns persisted validation.

## 8. Validation And Tests

Documentation audit status:

- reviewed against the current implementation on 2026-06-08

Automated tests:

- `04_Software/AudioMancer/tests/test_ui_scroll_service.py`
- `04_Software/AudioMancer/tests/test_app_entrypoint.py`
- `04_Software/AudioMancer/tests/test_settings_service.py`
- `04_Software/AudioMancer/tests/test_settings_page.py`

Covered behaviors:

- one wheel notch moves by the configured number of single-steps
- ordinary non-scroll-area widgets are ignored
- app startup installs the filter from settings
- settings validation preserves `1..5` and repairs invalid values to default
- Settings page loads and saves the scroll-step value

Minimum validation after changing this component:

```powershell
uv run python -m py_compile src/audiomancer/services/ui_scroll_service.py
uv run pytest tests/test_ui_scroll_service.py tests/test_app_entrypoint.py tests/test_settings_service.py tests/test_settings_page.py
```

## 9. Limitations And Future Work

- The current implementation handles vertical wheel scrolling only.
- Horizontal wheel and touchpad pixel-delta customization can be added later if
  operator testing shows a need.

