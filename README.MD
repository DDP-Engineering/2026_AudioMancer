<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# AudioMancer

<p align="center">
  <img src="04_Software/AudioMancer/src/audiomancer/assets/icons/audiomancer_icon.png" alt="AudioMancer app icon" width="96">
</p>

<p align="center">
  <strong>Transform written words into real audio experience!</strong>
</p>

AudioMancer is a Windows desktop application for preparing translated books and
audiobook production assets. It combines operator-controlled text processing,
optional AI-assisted workflow steps, voice preparation, speech block review,
audio block generation, and final WAV assembly.

This repository contains the private source tree, planning material,
implementation documentation, tooling, delivery scripts, and support files for
AudioMancer.

## Product Overview

AudioMancer guides an operator from source text to audiobook production assets:
import a book, clean and structure the text, optionally use AI-assisted steps,
prepare voices, review generated speech, and assemble final WAV outputs.

The repository is organized so product planning, source code, implementation
documentation, tooling, delivery notes, and local support material stay in
separate folders.

## Repository Layout

- `0_Planning/` - planning notes and design drafts.
- `01_Documentation/` - project-level documentation and media.
- `02_Tools/` - packaging, audit, and repository utility scripts.
- `04_Software/` - application source code.
- `05_SoftwareDocu/` - implementation documentation and offline user help.
- `07_Delivery/` - delivery metadata and release packaging notes.
- `09_Others/` - runtime projects, samples, and local support material.

## Where To Start

- `04_Software/AudioMancer/` contains the runnable desktop application.
- `04_Software/AudioMancer/README.MD` contains application development,
  runtime, and validation notes.
- `05_SoftwareDocu/` contains focused implementation documentation.
- `05_SoftwareDocu/UserGuide/` contains the English offline help bundle.
- `05_SoftwareDocu/UserGuide_ro/` contains the Romanian offline help bundle.
- `CHANGELOG.md` contains detailed version history.
- Current release metadata is maintained in the application package metadata
  and package `__version__`; README files intentionally avoid embedding the
  current application version.
- `HowToTest.md` summarizes the broader validation baseline.

## Release Notes

Use `CHANGELOG.md` for source-level version history. Generated delivery
archives are not committed to this repository; Windows release packages are
published through the configured GitHub Releases delivery flow.

## License

AudioMancer is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with an additional Non-Commercial restriction. See `LICENSE.txt` and
`LICENSE_NC.txt` for full license details.
