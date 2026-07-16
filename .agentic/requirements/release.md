<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Release Requirements

| ID | Status | Priority | Requirement | Rationale | Related Components | Verification Method | Linked Tests | Created On | Last Updated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-REL-001 | Active | Must | Generated delivery archives shall not be committed and shall be published through the configured release flow instead. | Prevents large binary artifacts from polluting source history. | `AGENTS.md`; `07_Delivery/`; GitHub Releases | Manual verification: inspect `git status` and release assets before delivery commits. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-REL-002 | Active | Must | Release packages shall include the runtime, licenses, icon assets, prompts, and offline help needed to run from an extracted folder. | Operators should not need a separate installer or missing support files after extraction. | `02_Tools/package_windows_release.ps1`; `02_Tools/package_linux_release.sh`; `07_Delivery/README.md` | Manual verification: inspect package contents and launch the extracted app. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-REL-003 | Active | Should | Delivery notes shall identify package contents and validation status without mixing unrelated implementation changes into delivery-only updates. | Keeps release records auditable and focused. | `CHANGELOG.md`; `07_Delivery/README.md`; GitHub Releases | Manual verification: review release notes and staged files before publishing. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-REL-004 | Active | Must | Each AudioMancer release shall synchronize its version across `pyproject.toml`, `audiomancer.__version__`, `uv.lock`, the release smoke test, `CHANGELOG.md`, and the English and Romanian offline help bundle title and version displays. | Ensures operators, package tooling, and offline documentation identify the same release. | `CHANGELOG.md`; `04_Software/AudioMancer/pyproject.toml`; `04_Software/AudioMancer/uv.lock`; `04_Software/AudioMancer/src/audiomancer/__init__.py`; `04_Software/AudioMancer/tests/test_package_import.py`; `05_SoftwareDocu/UserGuide/index.html`; `05_SoftwareDocu/UserGuide_ro/index.html` | Release-version smoke test passed for 1.6.7. | `04_Software/AudioMancer/tests/test_package_import.py::test_package_exposes_main_and_release_version_metadata` | 2026-07-16 20:53 | 2026-07-16 18:18 |
