<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

### Changed

### Fixed

## [0.1.8] - 2026-04-05

### Added

- added a static `Text Chunking` page cloned from `DDP_Audiomancer` with matching deterministic chunking, AI chunking, cleaned-text reference, chunk list, selected-chunk preview, and notes layout
- extended the focused UI test to verify the cloned chunking controls are present in the main shell

### Changed

- replaced the `Text Chunking` placeholder page in the copied shell with the new presentational cloned page
- package version updated to `0.1.8`

### Fixed

## [0.1.7] - 2026-04-05

### Added

- added a static `Text Cleanup` page cloned from `DDP_Audiomancer` with matching extraction, deterministic cleanup, AI cleanup, preview, and notes layout
- added focused UI-test coverage to verify the cloned cleanup controls are present in the main shell

### Changed

- replaced the `Text Cleanup` placeholder page in the copied shell with the new presentational cloned page
- package version updated to `0.1.7`

### Fixed

## [0.1.6] - 2026-04-05

### Added

- added a real About dialog based on the `DDP_Audiomancer` version with a scrollable read-only license text area
- added app-root `LICENSE.txt` and `LICENSE_NC.txt` files for About dialog display and delivery packaging
- added focused test coverage for the About dialog license content and updated subtitle/layout expectations

### Changed

- narrowed the About dialog, increased the `@2026` mark size, centered the `Ok` button, and updated the subtitle to `Transform written words into real audio experience!`
- changed the About dialog license source to the `04_Software/AudioMancer/` app root so delivered builds can keep the license files beside the application
- updated application and shell documentation to describe the About dialog and app-root license-file placement
- package version updated to `0.1.6`

### Fixed

## [0.1.5] - 2026-04-05

### Added

- copied the `DDP_Audiomancer` main-window shell structure into `AudioMancer` with a toolbar, navigation sidebar, stacked pages, status bar, and placeholder dialogs
- added presentational UI support modules for navigation, status display, the home/project page, generic placeholder pages, and a new static narrator page
- inserted a `Narrator` workflow page between `Characters` and `Narration Plan` with profile selection, description entry, preview controls, and a reserved blank workspace area

### Changed

- replaced the earlier custom placeholder main window with a source-matched `DDP_Audiomancer`-style shell adapted to the `AudioMancer` package
- adjusted the Home / Project workflow-progress panel sizing and default empty project-stage text to better match the intended initial state and layout
- removed UI logging from the main window in line with the rule that logging is reserved for backend implementation only
- updated package, test, and shell documentation to describe the copied UI structure
- package version updated to `0.1.5`

### Fixed

## [0.1.4] - 2026-04-04

### Added

- shared `settings_service` for `settings.json` creation, loading, validation, self-healing, saving, and startup integration
- focused tests for settings lifecycle behavior and a dedicated `05_SoftwareDocu/AudioMancer_Settings_Service.md` component document

### Changed

- settings defaults now start with no seeded LLM profiles and no selected LLM profile-id fields
- settings validation now emits more detailed repair/load/save lifecycle logs and uses decorator-based trace logging on the public settings-service API
- package version updated to `0.1.4`

### Fixed

## [0.1.3] - 2026-04-04

### Added

- dedicated `05_SoftwareDocu/AudioMancer_Logging_Service.md` component documentation for the runtime logging service
- repo-local Codex skill under `.codex/skills/write-component-documentation/` for creating and updating `05_SoftwareDocu/` component documents using the repository template and established style

### Changed

- `05_SoftwareDocu/README.md` now lists the logging service document
- package version updated to `0.1.3`

### Fixed

## [0.1.2] - 2026-04-04

### Added

- shared runtime logging service for the AudioMancer desktop app with per-run log files, component loggers, and optional decorator tracing
- focused tests for logging initialization, cleanup, structured output, and trace logging

### Changed

- app bootstrap now initializes logging at startup and shuts it down on exit or bootstrap failure
- main window initialization now emits a component log message
- software and application documentation now describe the logging service behavior and configuration ownership
- package version updated to `0.1.2`

### Fixed

- repository ignore rules now exclude generated runtime logs under `04_Software/AudioMancer/Logs/`

## [0.1.1] - 2026-04-04

### Added

- adapted `config.py` baseline and configuration/settings component documentation
- focused configuration contract test for the config and settings scaffold
- adapted `settings.json` baseline preserved from `04_Software/DDP_Audiomancer/settings.json`

### Changed

- application scaffold documentation and tests to reflect the preserved config/settings contract
- main window setup to use the shared configuration values for title and dimensions
- callable Doxygen docstrings to match the stricter repository documentation format

### Fixed

- `pyproject.toml` encoding so `uv sync --extra dev` parses and resolves correctly

## [0.1.0] - 2026-04-04

### Added

- initial repository scaffold with planning, documentation, tools, software, delivery, and support folders
- repository rules in `AGENTS.md` and code/documentation style guidance in `01_Documentation/Code_Style.md`
- initial planning overview for the `AudioMancer` desktop application
- Python 3.12 application scaffold under `04_Software/AudioMancer/`
- `uv`-based environment and dependency setup
- minimal `PySide6` desktop app shell with package entrypoints and focused tests
- packaging placeholders for future `PyInstaller`-based build flow
- setup documentation for repository bootstrap and dependency installation

### Changed

### Fixed
