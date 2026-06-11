<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Page State Support Services

## 1. Purpose

Documents page-state and presenter helpers that shape persisted project data
into view-ready dictionaries for the Qt UI:

- `src/audiomancer/services/home_presenter_service.py`
- `src/audiomancer/services/text_cleanup_state_service.py`
- `src/audiomancer/services/ai_translation_state_service.py`
- `src/audiomancer/services/character_discovery_state_service.py`
- `src/audiomancer/services/character_voices_state_service.py`
- `src/audiomancer/services/audio_assembly_state_service.py`

These services keep UI controllers thin by centralizing status rows, enabled
flags, notes, preview text, selected targets, and reset-state calculations.

## 2. Responsibilities

- build Home workflow stage statuses from manifest operations and active
  operation state
- build Text Cleanup extraction/cleanup previews and reset manifests
- select AI profile state for cleanup, translation, and character discovery
- derive AI Translation page state from chunking and translation artifacts
- derive Characters and Character Voices page state from persisted reports,
  narrator profiles, selected language, and VoiceWeaver readiness
- build the Characters page `source_chunk_map` from the already-loaded chunk
  artifact without invoking Character Discovery input enrichment or
  dialogue-span detection during page refresh
- derive Audio Assembly page state from audio-block approval and assembly
  report artifacts, including whether generated Scene Ambience blocks count
  toward readiness and final output

They do not own widget construction, signal wiring, long-running operation
execution, or low-level project persistence.

## 3. Implementation Overview

Main public entrypoints:

- `home_presenter_service.build_stage_statuses(...)`
- `home_presenter_service.apply_active_operation_status(...)`
- `home_presenter_service.stage_reached_index(...)`
- `text_cleanup_state_service.build_text_cleanup_state(...)`
- `text_cleanup_state_service.save_cleaned_text_edit(...)`
- `text_cleanup_state_service.build_manifest_after_operation_reset(...)`
- `ai_translation_state_service.build_ai_translation_state(...)`
- `ai_translation_state_service.build_ai_translation_notes(...)`
- `character_discovery_state_service.build_character_discovery_state(...)`
- `character_discovery_state_service.build_character_discovery_notes(...)`
- `character_voices_state_service.build_character_voices_state(...)`
- `character_voices_state_service.build_status_lines(...)`
- `audio_assembly_state_service.build_audio_assembly_state(...)`

The helpers read project manifests and operation reports, normalize missing
runtime values, then return plain dictionaries that page classes and
controllers can apply without duplicating workflow rules.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- workflow services such as `deterministic_cleanup_service`,
  `deterministic_chunking_service`, `ai_translation_service`,
  `character_discovery_service`, `character_voices_service`,
  `narrator_definition_service`, `audio_blocks_service`, and
  `audio_assembly_service`
- shared helpers such as `operation_runtime_service`, `ai_state_note_service`,
  and `ui_state_service`

External dependencies:

- Python standard library only

## 5. Inputs And Outputs

Inputs:

- active project root paths
- current `project.json` manifest dictionaries
- selected UI language
- configured AI/TTS profile payloads
- operation reports and operation-state files

Outputs:

- view-state dictionaries for page `apply_*_state(...)` methods
- localized notes and status lines
- updated manifest dictionaries after manual cleanup edits or operation resets
- preview text snippets loaded from project artifacts

## 6. Data Contracts

Returned dictionaries intentionally use primitive JSON-like values so UI tests
can assert behavior without constructing service objects. Important fields
include:

- Home stage tokens and statuses
- selected AI profile IDs and readiness messages
- `can_start`, `can_reset`, `can_generate`, and similar enablement flags
- preview text and warning/note lines
- selected character, narrator, language, and audio assembly summary values
- Audio Assembly Scene Ambience inclusion state and readiness counts after the
  current inclusion filter is applied

Manual cleanup edits persist the edited text and reset downstream operations
through the shared operation-runtime reset policy.

## 7. Workflow Integration

These helpers sit between controllers/pages and workflow services. Controllers
load the active manifest, call the state helper, then pass the result to the
page. When an operator edits cleaned text or resets a workflow step, the helper
returns the manifest changes needed by the workspace layer.

## 8. Usage

```python
state = text_cleanup_state_service.build_text_cleanup_state(project_root, manifest)
page.apply_state(state)

statuses = home_presenter_service.build_stage_statuses(manifest, language="en")
```

## 9. Validation And Tests

Focused tests:

- `tests/test_home_presenter_service.py`
- `tests/test_text_cleanup_state_service.py`
- `tests/test_ai_translation_state_service.py`
- `tests/test_character_discovery_state_service.py`
- `tests/test_character_voices_state_service.py`
- `tests/test_audio_assembly_state_service.py`

Minimum validation after changes:

- `uv run python -m py_compile` for changed state helper files
- targeted `uv run pytest` for the matching state-service tests

## 10. Limitations And Future Work

- The helpers return dictionaries rather than typed view models.
- Some fields are intentionally shaped around current Qt page contracts.
- Localization is limited to strings already present in the UI state service.
