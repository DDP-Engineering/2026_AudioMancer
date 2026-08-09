<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Character Voices

## Purpose

Character Voices derives narrator-first voice targets from the selected narrator
and reviewed character inventory, then manages prompt review, sample import or
generation, preview, readiness, and the compact project-manifest summary. It does
not assign Speech Blocks or generate final audiobook audio.

## Public interface

`character_voices_service.py` owns `characters_voice.json`, target/sample lookup,
prompt updates, import and generated-sample persistence, readiness, and operation
summary derivation. `character_voices_state_service.py` builds the page payload.
`character_voices_ui_controller.py` coordinates Qt actions, threaded generation,
manifest synchronization, downstream audio invalidation, and status presentation.
`CharacterVoicesPage` exposes target selection and import, edit/save, generation,
batch generation, and preview signals.

## Key behaviors

- `REQ-FUNC-973449a5` — first activation cannot complete or promote Character
  Voices until a non-empty persisted plan and required sample evidence exist.
- `REQ-REL-f42cecc0` — filesystem failures during sample import remain inside the
  Qt slot, show a localized project-error warning, and trigger no success effects.
- `REQ-FUNC-efab6267` — cancellation reloads durable partial batch progress into
  the page and manifest before presenting cancellation status.
- `REQ-UX-1e55ab3b` — valid edit mode keeps Save reachable and emits unchanged
  prompt and preview text through the established save path.
- Narrator targets are preview-only; character targets retain stable IDs across
  character renames and store sample metadata with their project-local WAVs.
- Readiness requires the selected narrator WAV and metadata plus every character
  target WAV and metadata; the manifest stage remains a promotion-only high-water
  mark.

## Persistence and workflow

The target plan is created lazily on the first Character Voices page-state build.
Controller synchronization therefore returns without writing the manifest when
the page has no targets and `characters_voice.json` does not yet exist. Once the
file exists, the controller may reload it when the page snapshot is empty and
derive truthful not-started, in-progress, or completed progress from disk.

Batch generation persists each completed character sample immediately. A later
cancellation does not roll back those samples; it refreshes the UI and manifest
to expose the durable partial result. Successful voice changes continue to use
the existing downstream Audio Blocks invalidation paths.

## Validation

Primary coverage:

- `04_Software/AudioMancer/tests/test_character_voices_service.py`
- `04_Software/AudioMancer/tests/test_character_voices_state_service.py`
- `04_Software/AudioMancer/tests/test_character_voices_page.py`
- `04_Software/AudioMancer/tests/test_character_voices_ui_controller.py`

The controller suite includes the real `MainWindow.set_current_page` first-entry
ordering, injected import failure, partial cancellation refresh, and persisted
ready-promotion regressions.

## Files

- `04_Software/AudioMancer/src/audiomancer/services/character_voices_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/character_voices_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/voice_sample_import_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/character_voices_page.py`
- `04_Software/AudioMancer/tests/test_character_voices_service.py`
- `04_Software/AudioMancer/tests/test_character_voices_state_service.py`
- `04_Software/AudioMancer/tests/test_character_voices_page.py`
- `04_Software/AudioMancer/tests/test_character_voices_ui_controller.py`
