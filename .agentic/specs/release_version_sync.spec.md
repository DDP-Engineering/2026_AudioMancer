<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: AudioMancer Release Version Synchronization

- Requirement ID: `REQ-REL-6347c5a6-71bf-4d9b-8197-cddae2ccfcd2`
- Requirement: AudioMancer release surfaces shall declare one identical semantic version.

## Behavior

Publishing a release replaces the active `Unreleased` changelog body with a
dated release heading, restores an empty `Unreleased` heading above it, and
sets every authoritative project and help version surface to the same semantic
version. Historical changelog headings remain unchanged.

## Interface / Format

For release `2.0.0`, the authoritative surfaces are:

```text
CHANGELOG.md
  ## [Unreleased]
  ## [2.0.0] - 2026-07-30

04_Software/AudioMancer/pyproject.toml
  [project].version = "2.0.0"

04_Software/AudioMancer/uv.lock
  [[package]] name = "audiomancer", version = "2.0.0"

04_Software/AudioMancer/src/audiomancer/__init__.py
  __version__ = "2.0.0"

04_Software/AudioMancer/tests/test_package_import.py
  EXPECTED_VERSION = "2.0.0"

05_SoftwareDocu/UserGuide/index.html
  title, Help version, and Application version = 2.0.0

05_SoftwareDocu/UserGuide_ro/index.html
  title, Versiune ajutor, and Versiune aplicatie = 2.0.0
```

## Examples

| Input | Expected result |
| --- | --- |
| All authoritative surfaces declare `2.0.0` | Release-version check passes. |
| Any authoritative surface declares another version | Release-version check fails and identifies the inconsistent surface. |
| Historical `## [1.7.0]` changelog heading | Remains unchanged as release history. |

## Acceptance

- [ ] A fresh `Unreleased` heading precedes `## [2.0.0] - 2026-07-30`.
- [ ] Package metadata, runtime API, lockfile, smoke test, and offline help bundles declare `2.0.0`.
- [ ] Historical changelog headings remain unchanged.
- [ ] Focused and full validation pass.
