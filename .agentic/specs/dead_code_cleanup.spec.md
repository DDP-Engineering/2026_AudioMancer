<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: issue #37 dead-code cleanup

Companion specification for the issue #37 deletion-only maintenance contract.

- Requirement ID: `REQ-NFR-8967d3a9-c376-4ed1-b551-8581db800946`
- Requirement: `AudioMancer production modules shall not define the confirmed-dead internal callables listed in this specification.`

## Behavior

Delete only callables that have no caller in the current `src` tree after exact
symbol-reference verification. Delete stale tests and localization entries that
exist only for those callables. Do not add aliases, compatibility wrappers,
deprecated stubs, migrations, or replacement placeholders.

Narrator manifest healing continues to derive `narrator_profile_name` and
`narrator_language` from the selected profile returned by
`_narrator_definition_completion_evidence`; the nonexistent `selection`
evidence branch is removed.

## Interface / Format

The following production callables are retired:

```text
services/project_workspace_service.py
  _payload_has_text
  _selected_narrator_profile

services/operation_runtime_service.py
  operation_folder_name

services/text_chunking_state_service.py
  build_manifest_after_chunk_edit

services/cleanup_metadata_service.py
  finalize_paragraph_records

services/cleanup_text_analysis_service.py
  count_detected_chapters
  format_dialogue_lines

services/audio_blocks_service.py
  invalidate_audio_for_speech_block
  _speech_blocks_snapshot_path
  _first_incomplete_block_index
  _status_timestamp

services/character_discovery_service.py
  _review_status_summary
  _persistable_character_profile
  _sentence_fragment

services/narrator_definition_service.py
  clear_all_profile_samples

services/project_export_service.py
  _removed_line_count

services/speech_blocks_service.py
  mark_speech_blocks_for_character_review

services/speech_blocks_normalization_service.py
  validate_source_span_response_payload
  validate_ai_block_source_spans

services/speech_blocks_text_split_service.py
  _dash_dialogue_has_attribution

services/text_extraction_service.py
  build_extraction_summary

ui/controllers/audio_blocks_ui_controller.py
  confirm_audio_blocks_invalidation
  invalidate_audio_blocks_after_upstream_change
  _sync_manifest_after_audio_blocks_update

ui/controllers/characters_ui_controller.py
  handle_character_profile_changed

ui/controllers/character_voices_ui_controller.py
  _preview_timeout_seconds
  _persist_runtime_status

ui/controllers/narator_voice_ui_controller.py
  _preview_timeout_seconds
  _persist_runtime_status
```

The following current production surface is explicitly outside the deletion:

```text
cleanup_text_analysis_service.normalized_compare_key

voiceweaver_runtime_service:
  read_server_info, read_model_catalog, unload_model, rescan_models,
  delete_model, start_model_download, read_model_download_status,
  cancel_model_download, generate_voice_clone

ui_theme_service:
  duplicate/export/import helpers

ui_state_service:
  get_ui_strings, apply_text_scale

workflow_impact_service:
  stable_identity_fields, is_stable_identity_field,
  apply_full_operation_reset, build_impact_metadata

operation_runtime_service:
  project_text_artifact_has_content

speech_blocks_report_state_service:
  source_chunks_input_path

speech_blocks_service:
  load_input_source_chunks

text_extraction_service:
  _write_running_metadata
```

Remove these localization keys from both English and Romanian catalogs:

```text
project.confirm_audio_blocks_invalidation
dialog.confirm_audio_blocks_invalidation_title
```

## Examples

| Input | Expected result |
| --- | --- |
| Exact current-tree reference scan for a retired callable | No production or test reference resolves. |
| Exact scan for `normalized_compare_key` | Its definition and both `text_cleanup_service` callers remain. |
| Narrator completion evidence containing only `profile` | Manifest narrator name and language heal from that profile. |
| English and Romanian translation key sets | Key sets remain identical after both obsolete keys are removed. |

## Acceptance

- [ ] All 29 retired callables are absent from production modules.
- [ ] All explicitly preserved APIs remain present.
- [ ] Narrator manifest healing reads only the selected profile evidence.
- [ ] Three stale controller monkeypatches are absent.
- [ ] Both obsolete localization keys are absent from both language catalogs.
- [ ] Focused tests, Ruff, traceability, coverage, and impact checks pass.
