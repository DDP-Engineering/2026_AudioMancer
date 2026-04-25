<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 2026_AudioMancer

Repository for the AudioMancer desktop application and its planning,
documentation, tooling, delivery, and support material.

## Top-Level Structure

- `0_Planning/`
- `01_Documentation/`
- `02_Tools/`
- `04_Software/`
- `05_SoftwareDocu/`
- `07_Delivery/`
- `09_Others/`

## Software Locations

The software subtrees currently live under:

- `04_Software/AudioMancer/`

## Current Implementation

`04_Software/AudioMancer/` contains the Python 3.12/PySide6 application. The
current app supports project creation, source import, extraction, deterministic
and AI cleanup, deterministic and AI chunking, AI translation, character
discovery, narrator and character voice preparation, Speech Blocks, Audio
Blocks, WAV Audio Assembly deliverables, Home-page TXT/Markdown exports for
completed text artifacts, and external full-project ZIP snapshots.

Focused implementation documentation is maintained in `05_SoftwareDocu/`.
The end-user help bundles are maintained in `05_SoftwareDocu/UserGuide/` and
`05_SoftwareDocu/UserGuide_ro/`, then packaged as offline HTML.
Validation commands and targeted test groups are listed in
`04_Software/AudioMancer/README.MD`.
