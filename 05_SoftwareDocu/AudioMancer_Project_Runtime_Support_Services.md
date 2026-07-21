<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Project Runtime Support Services

## 1. Purpose

Documents project/runtime helper services that support source import,
operation-state persistence, and generated audio artifact handling:

- `src/audiomancer/services/import_service.py`
- `src/audiomancer/services/operation_runtime_service.py`
- `src/audiomancer/services/audio_blocks_artifact_service.py`

These services keep project-relative paths, workflow reset behavior, and audio
file naming/validation consistent across the application.

## 2. Responsibilities

- validate and register supported imported source documents
- copy source files into the project root while avoiding name collisions
- remove a previous imported source only when the stored relative path is safe
- build and resolve root-level operation artifact paths
- write and load operation JSON artifacts
- build shared operation-state payload envelopes
- treat malformed or unreadable operation-state files as no usable state while
  logging a warning
- calculate progress percentages and emit progress update payloads
- reset known downstream operation artifacts without deleting unrelated files
- build deterministic generated-audio paths and WAV filenames
- validate and stitch WAV byte streams produced by VoiceWeaver

They do not own source text extraction, UI dialogs, model generation, final
audiobook assembly, or arbitrary project cleanup.

## 3. Implementation Overview

Main public entrypoints:

- `import_service.import_source(...)`
- `operation_runtime_service.build_operation_output_path(...)`
- `operation_runtime_service.build_operation_state_payload(...)`
- `operation_runtime_service.ensure_default_operation_state(...)`
- `operation_runtime_service.load_operation_state_payload(...)`
- `operation_runtime_service.write_operation_json_artifact(...)`
- `operation_runtime_service.reset_operation_data(...)`
- `operation_runtime_service.raise_if_cancelled(...)`
- `audio_blocks_artifact_service.generated_audio_root(...)`
- `audio_blocks_artifact_service.audio_artifact_paths(...)`
- `audio_blocks_artifact_service.validate_wav_bytes(...)`
- `audio_blocks_artifact_service.stitch_wav_parts(...)`

`import_service` returns manifest-ready source metadata. The workspace layer
persists that metadata in `project.json`.

`operation_runtime_service` is the shared contract for root-level operation
folders, operation state, progress, cancellation, and selective artifact reset.
For `narrator_definition`, reset owns the strict `narrator_voice.json`
document, canonical `audio_narator_*.wav` profile samples, and diagnostic
`log_ai_narrator_profiles_*.log` files. Preservation of that operation keeps
all three current artifact classes. Removed Narrator Voice contract files are
never included in reset or preservation logic.

`audio_blocks_artifact_service` names generated audio from stable block data,
normalizes speaker names for filesystem safety, validates WAV content, and
stitches multi-part WAV responses into one approved block artifact.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `audiomancer.services.persistence_service`
- `audiomancer.services.logging_service`
- `audiomancer.services.time_service`
- `audiomancer.services.speech_blocks_service`

External dependencies:

- Python standard library: `pathlib`, `json`, `shutil`, `wave`, `io`, `re`,
  `unicodedata`, `math`

## 5. Inputs And Outputs

Inputs:

- selected source file paths
- active project root paths
- current manifest source metadata
- operation kind names and artifact file names
- speech/audio block dictionaries
- WAV bytes or WAV part paths

Outputs:

- copied source files in the project root
- manifest-ready source document dictionaries
- operation-state and report JSON files
- progress update dictionaries
- generated audio paths under the configured audio folder
- validated or stitched `.wav` files

## 6. Data Contracts

Imported source metadata includes original filename, project-relative path,
file type, byte size, and import timestamp.

Operation state payloads use a compact shared envelope with `status`,
`progress_current`, `progress_total`, `mode`, `warning_count`, `metadata`, and
`resume_checkpoint`. Generic input, output, artifact path arrays and operation
audit timestamps are intentionally not persisted. Fixed artifact names are
derived from configuration, while AI transaction logs remain explicit through
`metadata.log_relative_path`, `metadata.ai_log_relative_path`, or matching
resume-checkpoint fields.

Operation-state loading is crash tolerant: missing, malformed, truncated, or
non-dictionary JSON state files return `None` and log a warning, allowing the
owning workflow to restart cleanly or follow its existing reset policy.

Generated audio filenames combine chunk/block identity, sequence indexes, and a
normalized speaker name. WAV validation rejects empty, malformed, or non-WAV
payloads before paths are marked as usable.

## 7. Workflow Integration

Import runs from the Home page before extraction. Operation runtime helpers are
used by extraction, cleanup, chunking, translation, character discovery,
Speech Blocks, Audio Blocks, Audio Assembly, and page reset flows. Audio Blocks
uses the artifact helper during VoiceWeaver generation and approval.

## 8. Usage

```python
source_payload = import_service.import_source(source_path, project_root, manifest)
state = operation_runtime_service.build_operation_state_payload(
    operation_kind="speech_blocks",
    status="completed",
)
paths = audio_blocks_artifact_service.audio_artifact_paths(project_root, audio_block)
```

## 9. Validation And Tests

Focused tests:

- `tests/test_import_service.py`
- `tests/test_operation_runtime_service.py`
- `tests/test_audio_blocks_artifact_service.py`

Minimum validation after changes:

- `uv run python -m py_compile` for changed service files
- targeted `uv run pytest` for the matching runtime helper tests

## 10. Limitations And Future Work

- Import supports only the source formats recognized by the current extraction
  workflow.
- Operation reset behavior is intentionally limited to known runtime artifacts.
- WAV stitching assumes compatible input format parameters.

Reviewed for the single-document Chunking contract: page-open state creation
omits Chunking, while Reset deletes `chunks_text.json`, separate AI logs, and
obsolete sidecars without loading legacy data.
