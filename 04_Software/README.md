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
  current package version is `1.1.5`. The
  application Help action opens the offline user guide for the selected UI
  language, maintained under
  `../05_SoftwareDocu/UserGuide/` and `../05_SoftwareDocu/UserGuide_ro/`, and
  bundled into release archives as `help/en/` plus `help/ro/`.
  Current validation guidance and the full regression baseline are documented
  in `../HowToTest.md` and `AudioMancer/README.MD`.
