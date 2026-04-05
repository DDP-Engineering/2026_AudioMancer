<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 02_Tools

Project tooling, helper scripts, and development utilities.

## Packaging

Windows delivery automation is implemented directly in this folder:

- `package_windows_release.ps1`
- `audiomancer_windows.spec`

The Windows packaging flow:

1. syncs the `uv` environment with dev dependencies
2. runs focused validation for the app bootstrap and UI shell
3. builds the Windows bundle with `PyInstaller`
4. stages the packaged app together with `settings.json` and the four license files
5. creates a versioned zip in `07_Delivery/`
6. removes temporary build and staging artifacts after success

Linux packaging is not implemented yet. The reserved entrypoint is:

- `package_linux_release.sh`

