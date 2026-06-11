<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 04_Software

Implementation sources and runnable software artifacts.

## Current Application Subtree

- `AudioMancer/` contains the Python 3.12/PySide6 desktop application,
  project-local runtime services, Qt pages/controllers, prompt templates,
  focused tests, packaging metadata, and the current end-to-end workflow from
  source selection and locked project options through WAV Audio Assembly. The
  application Help action opens the offline user guide for the selected UI
  language, maintained under
  `../05_SoftwareDocu/UserGuide/` and `../05_SoftwareDocu/UserGuide_ro/`, and
  bundled into release archives as `help/en/` plus `help/ro/`.
  Current validation guidance and the full regression baseline are documented
  in `../HowToTest.md` and `AudioMancer/README.MD`.
  Speech Blocks, Audio Blocks, and Audio Assembly currently include the Scene
  Ambience path, where ambience prompts are stored as ordered individual Speech
  Blocks, generated through the sound-prompt runtime path when enabled, and
  optionally included in final WAV assembly.
  Runtime generation diagnostics are logged through the shared application
  logging service and workflow artifacts remain project-local. Text chunking
  keeps deterministic and AI-assisted checkpoint artifacts resumable and uses
  atomic JSON persistence for chunking state, reports, and chunk output.
  AI Translation likewise uses atomic translated-artifact persistence,
  read-only steady-state synchronization, and terminal cancel/failure state
  records for interrupted runs.
  Narrator voice preparation uses atomic profile/sample persistence,
  cooperative VoiceWeaver cancellation, non-destructive sample replacement, and
  terminal cancel/failure checkpoints for interrupted narrator AI analysis.
