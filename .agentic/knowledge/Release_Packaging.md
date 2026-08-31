<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Release Packaging

## Purpose

Release packaging produces the stable Windows ZIP, Linux ZIP, and Linux
AppImage delivery artifacts from the application source and sanitized default
settings. It validates package structure and runtime dependencies, but does not
publish artifacts or change the release version.

## Public interface

Run `02_tools/package_windows_release.ps1` on Windows for the portable Windows
ZIP. Under WSL, run `02_tools/package_linux_release.sh`, followed by
`02_tools/validate_linux_delivery.sh`, for the Linux ZIP and AppImage. Outputs
use the stable names recorded in `07_Delivery/SHA256SUMS.txt`.

## Key behaviors

- `REQ-PLAT-03c3187a` - Packages contain version-matched release notes and sanitized settings with no API keys or runtime discovery cache.
- `REQ-PLAT-03c3187a` - Linux validation checks archive contents, AppImage shared libraries, offscreen startup, and SHA-256 checksums.
- `REQ-PLAT-03c3187a` - The Linux build omits PySide6's optional TIFF image plugin because its retired `libtiff.so.5` ABI is unavailable on the supported Ubuntu 24.04 packaging host and AudioMancer does not use TIFF assets.
- `REQ-PLAT-e9388a76` - The active release section in `CHANGELOG.md` is the release note source embedded in both portable archives.
- `REQ-PLAT-c9c8f2b1` - The Windows packager removes Codex host-runtime
  directories from `PATH` while PyInstaller collects binaries, preventing
  foreign Poppler ICU DLLs from shadowing the bundled Qt runtime.

## Files

- `02_tools/package_windows_release.ps1` - builds the portable Windows ZIP.
- `02_tools/package_linux_release.sh` - builds the Linux portable bundle, ZIP, and AppImage.
- `02_tools/validate_linux_delivery.sh` - validates Linux artifacts and refreshes their checksums.
- `07_Delivery/AudioMancer_Windows_x64.zip` - stable Windows delivery archive.
- `07_Delivery/AudioMancer_Linux_x64.zip` - stable Linux delivery archive.
- `07_Delivery/AudioMancer_Linux_x64.AppImage` - stable Linux AppImage.
- `07_Delivery/SHA256SUMS.txt` - release artifact integrity hashes.
- `CHANGELOG.md` - release notes embedded into delivery archives.
