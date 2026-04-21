<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 02_Tools

Project tooling, helper scripts, and development utilities.

## Packaging

Release packaging automation is implemented directly in this folder:

- `package_windows_release.ps1`
- `audiomancer_windows.spec`
- `package_linux_release.sh`

Each release script must be run on the target operating system because
`PyInstaller` bundles platform-specific runtime files.

Packaging scripts do not run application tests. Run the project validation
suite before using these scripts for a release candidate.

The Windows packaging flow is:

1. syncs the `uv` environment with dev dependencies
2. builds the Windows bundle with `PyInstaller`
3. stages the packaged app together with `settings.json`, the four license
   files, `Start-AudioMancer.cmd`, and `README_RELEASE.txt`
4. creates a versioned zip in `07_Delivery/`
5. removes temporary build and staging artifacts after success

Run it from PowerShell on Windows:

```powershell
.\02_Tools\package_windows_release.ps1
```

The Windows output archive is:

```text
07_Delivery/AudioMancer_Windows_x64_v<version>.zip
```

The Ubuntu packaging flow is:

1. syncs the `uv` environment with dev dependencies
2. builds the Ubuntu bundle with `PyInstaller`
3. stages the packaged app together with `settings.json`, the four license
   files, `start-audiomancer.sh`, and `README_RELEASE.txt`
4. creates a versioned zip in `07_Delivery/`
5. removes temporary build and staging artifacts after success

Run it from Bash on Ubuntu:

```bash
bash 02_Tools/package_linux_release.sh
```

The Ubuntu output archive is:

```text
07_Delivery/AudioMancer_Ubuntu_x64_v<version>.zip
```

For both archives, `<version>` is read from
`04_Software/AudioMancer/pyproject.toml`.

Release archives are portable application folders. Users should extract the
full archive before starting the executable and keep the extracted files
together.
