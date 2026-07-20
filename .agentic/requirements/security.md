<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Security Requirements

| ID | Status | Priority | Requirement | Rationale | Related Components | Verification Method | Linked Tests | Created On | Last Updated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-SEC-001 | Active | Must | Project-relative source and artifact paths shall reject absolute paths, parent traversal, and symlink escapes, and project export or snapshot destinations shall be outside the active project root. | Containment prevents untrusted project metadata or operator destinations from reading, deleting, overwriting, or recursively archiving files beyond the intended workspace. | `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`; `04_Software/AudioMancer/src/audiomancer/services/import_service.py`; `04_Software/AudioMancer/src/audiomancer/services/project_export_service.py`; `04_Software/AudioMancer/src/audiomancer/services/project_snapshot_service.py`; `04_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py` | Automated focused pytest coverage passed for traversal, symlink escape, and external export or snapshot destinations. | `04_Software/AudioMancer/tests/test_project_workspace_service.py::test_validate_project_manifest_rejects_unsafe_source_document_paths`; `04_Software/AudioMancer/tests/test_project_workspace_service.py::test_open_project_rejects_source_document_symlink_escape`; `04_Software/AudioMancer/tests/test_import_service.py::test_import_source_rejects_previous_source_traversal_path`; `04_Software/AudioMancer/tests/test_project_export_service.py::test_project_export_service_detects_paths_inside_project`; `04_Software/AudioMancer/tests/test_project_snapshot_service.py::test_project_snapshot_service_rejects_destination_inside_project`; `04_Software/AudioMancer/tests/test_home_ui_controller.py::test_home_ui_controller_rejects_snapshot_inside_project` | 2026-07-18 15:49 | 2026-07-18 15:54 |
