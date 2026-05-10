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
  bundled into release archives as `help/en/` plus `help/ro/`. Current package
  version `1.0.1` includes protected minimum splitter widths on the dense review
  pages, the Character Voices batch sample action, and the selective
  downstream-preservation model for manual chunk, character, voice, speech,
  audio-block, and assembly operations. Speech Blocks review can also trigger
  selected-block audio regeneration and Play/Stop preview through the existing
  Audio Blocks workflow, using the compact `Generate Audio` label on that page.
  Current validation guidance and the full regression baseline are documented
  in `../HowToTest.md` and `AudioMancer/README.MD`.
