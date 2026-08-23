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

`05_Software/AudioMancer/pyproject.toml` carries the reference version, because
it is what builds the package. For a release `X.Y.Z` dated `YYYY-MM-DD`, the
authoritative surfaces are:

```text
05_Software/AudioMancer/pyproject.toml        (reference)
  [project].version = "X.Y.Z"

CHANGELOG.md
  ## [Unreleased]
  ## [X.Y.Z] - YYYY-MM-DD

05_Software/AudioMancer/uv.lock
  [[package]] name = "audiomancer", version = "X.Y.Z"

05_Software/AudioMancer/src/audiomancer/__init__.py
  __version__ = "X.Y.Z"

06_SoftwareDocu/UserGuide/index.html
  title, Help version, and Application version = X.Y.Z

06_SoftwareDocu/UserGuide_ro/index.html
  title, Versiune ajutor, and Versiune aplicatie = X.Y.Z
```

The release-version check is not itself a version surface: it reads the
reference version and compares the others against it, so a release bump never
edits the check.

## Examples

| Input | Expected result |
| --- | --- |
| All authoritative surfaces declare the same version | Release-version check passes. |
| Any authoritative surface declares another version | Release-version check fails and identifies the inconsistent surface. |
| Reference version is not a semantic `X.Y.Z` version | Release-version check fails. |
| Changelog carries no dated release section for the reference version | Release-version check fails. |
| Historical `## [1.7.0]` changelog heading | Remains unchanged as release history. |

## Acceptance

- [ ] A fresh `Unreleased` heading precedes the dated release heading.
- [ ] Package metadata, runtime API, lockfile, and both offline help bundles declare the reference version.
- [ ] Historical changelog headings remain unchanged.
- [ ] Focused and full validation pass.
