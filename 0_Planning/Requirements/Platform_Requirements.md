<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Platform Requirements

| ID | Status | Priority | Requirement | Rationale | Related Components | Verification Method | Linked Tests | Created On | Last Updated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-AUDIO-PLAT-001 | Active | Must | The application shall target Python 3.12 with the repository-managed `uv` environment and PySide6 desktop runtime. | Keeps development, tests, and packaged runtime aligned. | `04_Software/AudioMancer/pyproject.toml` | Manual verification: inspect `pyproject.toml` and run `uv sync --extra dev` on a supported workstation. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-AUDIO-PLAT-002 | Active | Must | Packaged delivery shall remain intended for Windows 11 and Ubuntu 22.04 LTS or newer without an installer dependency. | Matches the documented operator deployment model. | `0_Planning/Overview.md`; `02_Tools/`; `07_Delivery/` | Manual verification: build and smoke-test platform packages on the target operating systems. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-AUDIO-PLAT-003 | Active | Should | The application shall remain offline-first except for explicitly configured AI and TTS provider calls. | Operators should decide when provider access is used. | `04_Software/AudioMancer/src/audiomancer/services/`; `04_Software/AudioMancer/settings.example.json` | Manual verification: review provider defaults and run non-provider workflows without network access. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
