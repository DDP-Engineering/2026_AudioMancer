<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Release Requirements

| ID | Status | Priority | Requirement | Rationale | Related Components | Verification Method | Linked Tests | Created On | Last Updated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-REL-001 | Active | Must | Generated delivery archives shall not be committed and shall be published through the configured release flow instead. | Prevents large binary artifacts from polluting source history. | `AGENTS.md`; `07_Delivery/`; GitHub Releases | Manual verification: inspect `git status` and release assets before delivery commits. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-REL-002 | Active | Must | Release packages shall include the runtime, licenses, icon assets, prompts, and offline help needed to run from an extracted folder. | Operators should not need a separate installer or missing support files after extraction. | `02_Tools/package_windows_release.ps1`; `02_Tools/package_linux_release.sh`; `07_Delivery/README.md` | Manual verification: inspect package contents and launch the extracted app. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-REL-003 | Active | Should | Delivery notes shall identify package contents and validation status without mixing unrelated implementation changes into delivery-only updates. | Keeps release records auditable and focused. | `CHANGELOG.md`; `07_Delivery/README.md`; GitHub Releases | Manual verification: review release notes and staged files before publishing. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
