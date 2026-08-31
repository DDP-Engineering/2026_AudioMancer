<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# AudioMancer

<p align="center">
  <img src="07_Delivery/AudioMancer_Hero_A4_Landscape.png" alt="AudioMancer: transform written words into a real audio experience" width="900">
</p>

<p align="center">
  <img src="05_Software/AudioMancer/src/audiomancer/assets/icons/audiomancer_icon.png" alt="AudioMancer app icon" width="96">
</p>

<p align="center">
  <strong>Transform written words into real audio experience!</strong>
</p>

AudioMancer is a cross-platform desktop application for Windows and Linux that
prepares translated books and audiobook production assets. It combines
operator-controlled text processing, optional AI-assisted workflow steps, voice
preparation, speech block review, audio block generation, and final WAV
assembly.

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

## Supported Platforms

AudioMancer runs from the same source tree on both platforms and ships as a
portable bundle that needs no installer.

- **Windows x64** - portable zip, built with `02_Tools/package_windows_release.ps1`
  from PowerShell on Windows.
- **Linux x64 (Ubuntu)** - portable zip and an AppImage, both built with
  `02_Tools/package_linux_release.sh` from Bash on Ubuntu.

Each platform is packaged on its own host; there is no cross-compilation step.
`02_Tools/README.md` documents both packaging flows, and
`02_Tools/validate_linux_delivery.sh` validates the Linux artifacts.

## Repository Layout

- `00_Planning/` - planning notes and design drafts.
- `01_Documentation/` - project-level documentation and media.
- `02_Tools/` - packaging, audit, and repository utility scripts.
- `03_Hardware/` - hardware design material.
- `04_HardwareDocu/` - hardware documentation.
- `05_Software/` - application source code.
- `06_SoftwareDocu/` - offline user help and model-selection guidance.
- `07_Delivery/` - delivery metadata and release packaging notes.
- `09_Others/` - runtime projects, samples, and local support material.
- `.agentic/` - engineering workflow contract, task journals, and the
  per-component knowledge base under `.agentic/knowledge/`.

## Where To Start

- `05_Software/AudioMancer/` contains the runnable desktop application.
- `05_Software/AudioMancer/README.MD` contains application development,
  runtime, and validation notes.
- `.agentic/knowledge/` contains focused per-component implementation
  documentation.
- `06_SoftwareDocu/UserGuide/` contains the English offline help bundle.
- `06_SoftwareDocu/UserGuide_ro/` contains the Romanian offline help bundle.
- `CHANGELOG.md` contains detailed version history.
- Current release metadata is maintained in the application package metadata
  and package `__version__`; README files intentionally avoid embedding the
  current application version.
- `HowToTest.md` summarizes the broader validation baseline.

## Release Notes

Use `CHANGELOG.md` for source-level version history. Generated delivery
archives are not committed to this repository; Windows and Linux release
packages are published through the configured GitHub Releases delivery flow.

## License

AudioMancer is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with an additional Non-Commercial restriction. See `LICENSE.txt` and
`LICENSE_NC.txt` for full license details.
