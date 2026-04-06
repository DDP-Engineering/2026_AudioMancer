<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Changelog

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
