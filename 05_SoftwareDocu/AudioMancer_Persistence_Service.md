<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Persistence Service

## 1. Purpose

Provides shared atomic write helpers for AudioMancer files that must not be
left partially written after a crash, interrupted process, or failed final
replacement.

## 2. Responsibilities

- write complete text payloads to temporary files in the target directory
- flush and fsync temporary files before replacement
- replace the destination with `os.replace`
- serialize JSON payloads with the repository-standard UTF-8 formatting
- clean up temporary files when the replacement fails

It does not own schema validation, backup rotation, concurrent edit conflict
resolution, or recovery from already-corrupted files.

## 3. Implementation Overview

The component is implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/persistence_service.py`

Public functions:

- `write_text_atomic(target_path, text, encoding="utf-8")`
- `write_json_atomic(target_path, payload, indent=2, ensure_ascii=False, sort_keys=False, encoding="utf-8")`

High-level flow:

1. The target parent directory is created if it does not already exist.
2. A hidden temporary file is created in the same directory as the target file.
3. The full payload is written, flushed, and fsynced.
4. `os.replace` swaps the temporary file into the final path.
5. If replacement fails, the previous target remains in place and the temporary
   file is removed on a best-effort basis.

## 4. Dependencies

- Internal dependencies:
  services that persist project manifests, application settings, or operation
  state files
- External dependencies:
  Python standard library only: `contextlib`, `json`, `os`, `pathlib`,
  `tempfile`, and `typing`

## 5. Inputs And Outputs

Inputs:

- target paths supplied as `str` or `pathlib.Path`
- complete text payloads
- JSON-serializable Python objects

Outputs:

- replaced UTF-8 text or JSON files at the requested target path
- temporary files named near the target as `.<target-name>.*.tmp` during the
  write window

## 6. Data Contracts

JSON writes currently use these defaults unless the caller overrides them:

- indentation: `2`
- `ensure_ascii`: `False`
- `sort_keys`: `False`
- trailing newline: always present
- encoding: UTF-8

Atomicity depends on writing the temporary file in the same directory as the
target and using `os.replace` for the final replacement.

## 7. Workflow Integration

Current in-repo callers:

- `project_workspace_service.save_manifest(...)` for `project.json`
- `settings_service._write_settings_file(...)` for `settings.json`
- `operation_runtime_service.ensure_default_operation_state(...)` for first-use
  operation state files

Downstream readers continue to use normal JSON loading and do not need to know
whether the previous write was atomic.

## 8. Usage

```python
from audiomancer.services.persistence_service import write_json_atomic

write_json_atomic(project_root / "project.json", manifest_payload)
```

```python
from audiomancer.services.persistence_service import write_text_atomic

write_text_atomic(project_root / "notes.txt", operator_notes)
```

## 9. Validation And Tests

Automated coverage:

- `04_Software/AudioMancer/tests/test_persistence_service.py`

Minimum validation after changes:

- `uv run python -m py_compile 04_Software/AudioMancer/src/audiomancer/services/persistence_service.py`
- `uv run pytest tests/test_persistence_service.py`

## 10. Limitations And Future Work

- The helper does not lock files across processes; simultaneous writers remain
  last-replacement-wins.
- The helper currently covers critical manifest, settings, and default operation
  state writes. Additional operation report and artifact writers can be migrated
  incrementally.
