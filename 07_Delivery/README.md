<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 07_Delivery

Release packaging, delivery bundles, and distribution artifacts.

Delivery artifacts are produced by:

- `../02_Tools/package_windows_release.ps1`
- `../02_Tools/package_linux_release.sh`

The expected archive naming patterns are:

- `AudioMancer_Windows_x64_v<version>.zip`
- `AudioMancer_Ubuntu_x64_v<version>.zip`

Each delivery zip contains a portable application folder with:

- the platform-specific `AudioMancer` executable
- a platform start helper, either `Start-AudioMancer.cmd` or
  `start-audiomancer.sh`
- `README_RELEASE.txt`
- `help/en/` and `help/ro/` with the offline HTML user guides and screenshot assets
- `prompts/` with the external AI prompt templates required by AI-assisted
  cleanup, chunking, translation, character discovery, and Speech Blocks
- `settings.json`
- the four license files required by the app root

Build Windows archives on Windows and Ubuntu archives on Ubuntu. PyInstaller
does not create equivalent desktop bundles by cross-compiling from another
operating system.

Packaging scripts do not run application tests. Treat them as release assembly
tools and run the application validation suite before creating release
artifacts.
