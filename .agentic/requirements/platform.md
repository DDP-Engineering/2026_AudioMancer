<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Platform Requirements

| ID | Status | Priority | Requirement | Rationale | Related Components | Verification Method | Linked Tests | Created On | Last Updated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-PLAT-001 | Active | Must | The application shall target Python 3.12 with the repository-managed `uv` environment and PySide6 desktop runtime. | Keeps development, tests, and packaged runtime aligned. | `04_Software/AudioMancer/pyproject.toml` | Manual verification: inspect `pyproject.toml` and run `uv sync --extra dev` on a supported workstation. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-PLAT-002 | Active | Must | Packaged delivery shall remain intended for Windows 11 and Ubuntu 22.04 LTS or newer without an installer dependency. | Matches the documented operator deployment model. | `0_Planning/Overview.md`; `02_Tools/`; `07_Delivery/` | Manual verification: build and smoke-test platform packages on the target operating systems. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-PLAT-003 | Active | Should | The application shall remain offline-first except for explicitly configured AI and TTS provider calls. | Operators should decide when provider access is used. | `04_Software/AudioMancer/src/audiomancer/services/`; `04_Software/AudioMancer/settings.example.json` | Manual verification: review provider defaults and run non-provider workflows without network access. | N/A | 2026-06-09 09:50 | 2026-06-09 09:50 |
| REQ-PLAT-004 | Active | Should | AudioMancer local-model guidance shall state that AI Settings sends only request-level model, context, max-output, temperature, timeout, and structured-output hints to LM Studio, while sampler controls such as top-p, top-k, repeat penalty, seed, and reasoning mode remain LM Studio preset settings unless provider payload support is intentionally added. | Keeps operator guidance honest about what the app controls and prevents unsupported sampler settings from appearing in AudioMancer AI Settings. | `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_settings_page.py`; `04_Software/AudioMancer/src/audiomancer/services/settings_service.py`; `05_SoftwareDocu/AudioMancer_LMStudio_Local_Model_Recommendations.md`; `05_SoftwareDocu/UserGuide/index.html`; `05_SoftwareDocu/UserGuide_ro/index.html` | Automated pytest verifies docs describe AudioMancer request settings versus LM Studio-only sampler and reasoning presets. | `04_Software/AudioMancer/tests/test_speech_blocks_service.py::test_local_model_guidance_is_honest_about_ai_settings_and_lmstudio_presets` | 2026-07-01 18:55 | 2026-07-01 16:09 |
