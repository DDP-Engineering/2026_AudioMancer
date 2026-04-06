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

## [0.7.0] - 2026-04-06

### Added

- added deterministic text cleanup with project-local `10_cleanup` artifacts, resumable state, and cleanup output/report generation
- added focused cleanup, page-controller, presenter-service, and runtime-reset test coverage plus matching software documentation updates

### Changed

- simplified and reused the modal progress flow for extraction and cleanup operations
- improved extraction progress granularity for `pdf`, `rtf`, and `epub` processing so long-running work advances in visible steps
- refactored the application shell toward page-oriented UI controllers and related presenter/state services
- improved cleanup heuristics to better remove separator noise, preserve dialogue structure, and keep paragraph/newline structure more faithfully
- package version updated to `0.7.0`

### Fixed

- fixed workflow progress so `text_chunking_ready` no longer marks `Text Chunking` as already completed

## 0.6.0 - 2026-04-06

- added deterministic text extraction from the `Text Cleanup` page with project-local `00_extraction` artifacts and resumable `state_operation.json`
- added support for `.txt`, `.pdf`, `.rtf`, `.docx`, `.odt`, `.md`, and `.epub` text extraction using copied operation-local inputs
- changed extraction manifest persistence to store extracted-text/report paths, warning counts, and per-step `operations` state in `project.json`
- added destructive extraction rerun confirmation, downstream-folder reset behavior, and workflow-progress updates that mark `Text Cleanup` as in progress after extraction starts
- fixed RTF validation to reject misnamed legacy `.doc` containers instead of generating corrupted output
- added extraction-service, cleanup-page, main-window, and config/workspace test coverage plus component documentation for the extraction workflow

## 0.5.0 - 2026-04-06

- added source-file import from the Home page and locked the project to one imported source
- changed `project.json` to persist structured `source_document` metadata
- added support for `.txt`, `.pdf`, `.rtf`, `.docx`, `.odt`, `.md`, and `.epub` source import
- added import-service coverage and main-window/workspace tests for source locking and manifest persistence
- updated project workspace documentation and README to reflect the new import workflow

## [0.4.1] - 2026-04-06

### Added

### Changed

- refactored `audiomancer.services.ai_backend_service` to use fully functional dictionary payloads instead of dataclass-based result objects
- updated the AI settings page, main-window connect popup flow, and focused AI tests to consume the new functional probe-result contract
- package version updated to `0.4.1`

### Fixed

## [0.4.0] - 2026-04-06

### Added

- added the first persisted project-workspace flow for `AudioMancer` with `New Project` and `Open Project` support
- added cross-platform exact project-name validation for Windows and Linux folder rules
- added a minimal root-level `project.json` contract and a dedicated functional `project_workspace_service`
- added focused tests for project creation, project open, repair handling, and the project-aware main-window shell
- added `05_SoftwareDocu/AudioMancer_Project_Workspace.md` for the new project-workspace component

### Changed

- the main window now enables workflow pages only after one project is created or opened
- the Home / Project workflow-progress list is now driven from `config.PROJECT_WORKFLOW_STAGES` and displays rows as `Step | Progress`
- replaced the earlier custom new-project dialog with a simpler 2-popup flow using one folder picker and one name-input popup
- removed the thin project controller layer and kept the project workflow direct and functional from `main_window.py` to `project_workspace_service.py`
- refactored project manifest handling to validated dictionary payloads instead of a manifest class
- package version updated to `0.4.0`

### Fixed

- fixed project open so recoverable corruption now offers a repair confirmation instead of failing generically
- fixed project repair so the corrupted step and all downstream step folders are recreated/reset and the manifest stage is repaired consistently
- fixed repaired-project workflow progress so empty downstream steps do not appear completed after repair

## [0.3.3] - 2026-04-05

### Added

- added Windows and Linux release packaging scripts (`package_windows_release.ps1`, `package_linux_release.sh`) and entrypoint/spec helpers under `02_Tools/`
- added VS Code workspace configuration (`2026_Audiomancer.code-workspace`)

### Changed

- removed legacy build scripts (`build_linux.sh`, `build_windows.ps1`, and `02_Tools/AudioMancer/README.MD`) in favor of the new packaging flow
- updated tool, software, documentation, and delivery READMEs to reflect the new packaging structure
- refreshed `settings.json` and `uv.lock` to stay in sync with the current dependency set
- updated `05_SoftwareDocu/AudioMancer_App_Shell.md` to match the current application state
- package version updated to `0.3.3`

### Fixed

## [0.3.2] - 2026-04-05

### Added

### Changed

- added the missing callable-level Doxygen-style docstrings across the recent AI settings, localization, startup, logging, and main-window test changes so the codebase matches the repository documentation rules
- updated the affected Python module `@version` tags for the documentation-compliance pass
- package version updated to `0.3.2`

### Fixed

- fixed the remaining `AGENTS.md` and `Code_Style.md` compliance gaps for file and function documentation in the recently changed Python files

## [0.3.1] - 2026-04-05

### Added

- added `audiomancer.services.ai_backend_service` with normalized backend probing and model-discovery support for `lmstudio`, `ollama`, and `openai_compatible` AI profiles
- added focused automated coverage for backend probing, discovered-model normalization, AI Settings profile discovery updates, and translated connect popup feedback

### Changed

- the `AI Settings` dialog now supports real `Connect` probing, discovered-model refresh, popup feedback with discovered-model counts, and persisted discovery state for saved profiles
- AI backend probing now uses a dedicated short connect timeout from `config.py` instead of the longer workflow request timeout
- refined the `AI Settings` layout by removing the inline connect-status message, aligning the default-profile selectors with the main form rows, and moving `Structured output supported` under `Temperature`
- completed the connect-result translation path so localized popup messages no longer mix English success text into Romanian UI sessions
- updated application and shell documentation to describe the functional AI Settings connect flow
- package version updated to `0.3.1`

### Fixed

- fixed the AI Settings connect popup so operator-facing success feedback is fully translated for the active UI language

## [0.3.0] - 2026-04-05

### Added

- added `ui_state_service` as a dedicated runtime UI-state component for applying persisted UI language and text-size changes
- added focused test coverage for runtime UI translation lookup, text-scale application, and translated About-dialog license loading
- added Romanian app-root companion license files for the About dialog: `LICENSE_ro.txt` and `LICENSE_NC_ro.txt`
- added a repository rule requiring every operator-facing UI text change to update the translation mechanism in the same change

### Changed

- `Settings` save now applies the selected UI language and text-size immediately across the running shell instead of waiting for restart
- extended runtime English/Romanian translation coverage across the main toolbar, sidebar, status bar, settings dialogs, and current page shell labels
- updated the Home / Project page layout so the source-selection button sits in the project summary block and the workflow-progress area regains vertical space at large UI text sizes
- the About dialog now loads localized license text based on the current UI language, with fallback to the English license files when no localized pair exists
- `ui_state_service` now emits backend-service logging for translation and runtime UI-apply actions
- updated software and shell documentation to describe runtime UI apply behavior and localized license assets
- package version updated to `0.3.0`

### Fixed

- fixed the Home / Project page so the workflow-progress panel fits better at the maximum interface text size

## [0.2.0] - 2026-04-05

### Added

- added real save/load integration for the `Settings` and `AI Settings` dialogs through the shared settings service
- added focused page tests for `Settings` and `AI Settings` load/build behavior plus dialog-integration coverage in the main window

### Changed

- `Settings` and `AI Settings` now reload persisted values when opened, discard unsaved edits on cancel, and save merged settings back into the shared `settings.json` payload
- expanded the persisted settings schema to include AI default cleanup, chunking, and character-extraction profile selections alongside the simplified operator-facing settings
- updated startup so the main window receives the validated settings payload at bootstrap and keeps one in-memory source of truth for dialog coordination
- updated shell documentation to describe the now-wired settings persistence flow
- package version updated to `0.2.0`

### Fixed

## [0.1.13] - 2026-04-05

### Added

- added a static `Settings` dialog with language, interface text size, completion-beep, and save/cancel controls
- extended focused UI and settings-service coverage for the simplified settings dialog and reduced persisted settings schema

### Changed

- replaced the `Settings` placeholder dialog with the new presentational settings dialog and wired `Cancel` to close the dialog shell
- simplified the `Settings` dialog by removing unused provider, project-root, notification, and recent-project controls and aligning the remaining selectors on one row
- reduced the persisted settings schema and implementation to keep only the active operator-facing fields still used by the project
- updated shell documentation to describe the simplified settings dialog and settings payload
- package version updated to `0.1.13`

### Fixed

## [0.1.12] - 2026-04-05

### Added

- added a static `AI Settings` dialog with AI profile listing, provider configuration fields, default-profile selectors, and save/cancel actions
- extended the focused UI test to verify the cloned AI Settings controls are present in the main shell

### Changed

- replaced the `AI Settings` placeholder dialog with the new presentational cloned dialog
- refined the AI Settings layout by moving `Connect` beside `Backend Kind`, moving profile add/remove controls below the profile list, aligning the default-profile selectors with the main form rows, and centering the bottom actions
- updated the AI Settings form labels and control widths for closer visual fit, and wired the `Cancel` button to close the dialog shell
- updated shell documentation to describe the cloned AI Settings dialog
- package version updated to `0.1.12`

### Fixed

## [0.1.11] - 2026-04-05

### Added

- added a static `Narrator` page with a profile list, narrator-language selector, prompt-based profile editor, preview text area, and profile-management actions
- extended the focused UI test to verify the narrator profile-management controls are present in the main shell

### Changed

- replaced the earlier simple narrator placeholder with a fuller operator-facing narrator profile manager
- simplified the narrator page by removing delivery-direction, linked-role, model-source, and technical voice-source selectors so the UI stays focused on profile management only
- updated shell documentation to describe the narrator profile manager layout
- package version updated to `0.1.11`

### Fixed

## [0.1.10] - 2026-04-05

### Added

- added a static `Characters` page with discovery controls, character list, editable profile form, and evidence panels
- extended the focused UI test to verify the cloned characters controls are present in the main shell

### Changed

- replaced the `Characters` placeholder page in the application shell with the new presentational page
- reduced the static `Character Profile` panel height so the page fits the window better
- package version updated to `0.1.10`

### Fixed

## [0.1.9] - 2026-04-05

### Added

- added a static `AI Translation` page with target-language selection, translation-profile selection, chunk list, progress display, source/translation editors, and review action layout
- extended the focused UI test to verify the cloned translation controls are present in the main shell

### Changed

- replaced the `AI Translation` placeholder page in the application shell with the new presentational page
- reduced the static `Chunk List` section height on the AI Translation page by about 20 percent for closer visual fit
- repository validation guidance now prefers `uv run ...` for Python validation and tests in `04_Software/AudioMancer/`
- package version updated to `0.1.9`

### Fixed

## [0.1.8] - 2026-04-05

### Added

- added a static `Text Chunking` page with deterministic chunking, AI chunking, cleaned-text reference, chunk list, selected-chunk preview, and notes layout
- extended the focused UI test to verify the cloned chunking controls are present in the main shell

### Changed

- replaced the `Text Chunking` placeholder page in the application shell with the new presentational page
- package version updated to `0.1.8`

### Fixed

## [0.1.7] - 2026-04-05

### Added

- added a static `Text Cleanup` page with extraction, deterministic cleanup, AI cleanup, preview, and notes layout
- added focused UI-test coverage to verify the cloned cleanup controls are present in the main shell

### Changed

- replaced the `Text Cleanup` placeholder page in the application shell with the new presentational page
- package version updated to `0.1.7`

### Fixed

## [0.1.6] - 2026-04-05

### Added

- added a real About dialog with a scrollable read-only license text area
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

- added the main-window shell structure for `AudioMancer` with a toolbar, navigation sidebar, stacked pages, status bar, and placeholder dialogs
- added presentational UI support modules for navigation, status display, the home/project page, generic placeholder pages, and a new static narrator page
- inserted a `Narrator` workflow page between `Characters` and `Narration Plan` with profile selection, description entry, preview controls, and a reserved blank workspace area

### Changed

- replaced the earlier custom placeholder main window with the current `AudioMancer` application shell
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
- adapted the `settings.json` baseline for the local application scaffold

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
