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

`04_Software/AudioMancer/` contains the Python 3.12/PySide6 desktop
application. The current package version is `1.1.0`.

AudioMancer supports a reviewed audiobook-preparation workflow:

- project creation and source import
- text cleanup and text chunking
- AI translation
- character discovery
- narrator and character voice preparation
- speech block editing and approval
- audio block generation
- WAV audio assembly
- text, project, voice-sample, and audio-output exports

The application is designed so operators can combine AI-assisted steps with
manual review and manual editing. The workflow pages preserve completed work
where possible and reset only affected downstream artifacts when source text,
chunks, voices, speech blocks, audio blocks, or assembly settings change.

## Documentation

- `04_Software/AudioMancer/README.MD` contains application development,
  runtime, and validation notes.
- `05_SoftwareDocu/` contains focused implementation documentation.
- `05_SoftwareDocu/UserGuide/` contains the English offline help bundle.
- `05_SoftwareDocu/UserGuide_ro/` contains the Romanian offline help bundle.
- `CHANGELOG.md` contains detailed version history.
- `HowToTest.md` summarizes the broader validation baseline.
