<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# 02_Tools

Project tooling, helper scripts, and development utilities.

## Audits

Repeatable repository audits live in `02_Tools/audits/`.

Run them from the repository root with Python:

```powershell
# Check changed implementation files for stale documentation.
python 02_Tools/audits/audit_documentation.py --changed-only

# Check changed Python files for repository Doxygen/style requirements.
python 02_Tools/audits/audit_codestyle.py --changed-only

# Check changed service files for likely missing logging coverage.
python 02_Tools/audits/audit_logging_coverage.py --changed-only
```

Omit `--changed-only` for a full scan.

The logging audit is intentionally conservative: it reports candidates for
engineering review instead of editing code automatically.

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
3. stages the packaged app together with a clean `settings.json`, the four
   license files, `Start-AudioMancer.cmd`, and `README_RELEASE.txt`
4. creates the stable Windows zip in `07_Delivery/`
5. removes temporary build and staging artifacts after success

Run it from PowerShell on Windows:

```powershell
# Build the Windows portable release archive in 07_Delivery/.
.\02_Tools\package_windows_release.ps1
```

The Windows output archive is:

```text
07_Delivery/AudioMancer_Windows_x64.zip
```

The Ubuntu packaging flow is:

1. syncs the `uv` environment with dev dependencies
2. builds the Ubuntu bundle with `PyInstaller`
3. stages the packaged app together with a clean `settings.json`, the four
   license files, `start-audiomancer.sh`, and `README_RELEASE.txt`
4. creates the stable Linux zip in `07_Delivery/`
5. removes temporary build and staging artifacts after success

Run it from Bash on Ubuntu:

```bash
# Build the Ubuntu portable release archive in 07_Delivery/.
bash 02_Tools/package_linux_release.sh
```

The Linux output archive is:

```text
07_Delivery/AudioMancer_Linux_x64.zip
```

Both archive filenames are intentionally stable so Git stores one delivery
artifact per platform instead of one new filename per application version. The
application version is still read from `04_Software/AudioMancer/pyproject.toml`
and written inside the packaged release notes and application metadata.
Both packaging scripts write a cleaned staging copy of `settings.json`:
operator API keys, local LM Studio host addresses, VoiceWeaver API key, runtime
probe status, discovered-model cache, active-model cache, and device
diagnostics are removed from the archive without modifying the source app-root
settings file.

Release archives are portable application folders. Users should extract the
full archive before starting the executable and keep the extracted files
together.
