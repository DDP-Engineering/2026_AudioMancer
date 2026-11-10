<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Character Voices

## Routing

For target prompts, character samples and readiness, start at
`character_voices_service` and its service/state tests. Home narration-mode and
language changes belong to Project Lifecycle's `project_options_service`.

## Purpose and boundaries

Character Voices derives narrator-first voice targets from the selected narrator
and reviewed character inventory, then manages prompt review, sample import or
generation, preview, readiness, and the compact project-manifest summary. It does
not assign Speech Blocks or generate final audiobook audio.

## Public interface

Project Lifecycle mode changes clear character sample metadata/WAVs and readiness
while preserving target prompts and preview text plus the selected narrator's
data. A language change resets the whole target plan and its dependent samples.


`character_voices_service.py` owns `characters_voice.json`, target/sample lookup,
prompt updates, import and generated-sample persistence, readiness, and operation
summary derivation. Export requests a strict read-only target-plan load so an
unreadable or malformed plan is distinct from an empty plan on Home.
`character_voices_state_service.py` builds the page payload.
`build_character_voices_state` and `set_character_voices_state` agree key for
key: the single call site in `MainWindow._refresh_character_voices_page_state`
splats the payload into the method, so a field added or removed on one side
must move on the other in the same change.
`character_voices_ui_controller.py` coordinates Qt actions, threaded generation,
manifest synchronization, downstream audio invalidation, and status presentation.
`tts_runtime_ui_support.py` owns the common unauthenticated simplified-VoiceWeaver
probe, model-load, `voice_design` generation, terminal validation, remote-aware
cancellation, and `/audio` WAV-download flow.
`CharacterVoicesPage` exposes target selection and import, edit/save, draft cancellation, generation,
batch generation, and preview signals.

## Key behaviors

Character sample generation resolves a design model for the project voice
language independently of clone availability.

- `REQ-FUNC-973449a5` — first activation cannot complete or promote Character
  Voices until a non-empty persisted plan and required sample evidence exist.
- `REQ-REL-f42cecc0` — filesystem failures during sample import remain inside the
  Qt slot, show a localized project-error warning, and trigger no success effects.
- An interrupted batch reconciles saved samples and invalidates only their target IDs.
- `REQ-UX-1e55ab3b` — valid edit mode keeps Save reachable and emits unchanged
  prompt and preview text through the established save path.
- `REQ-UX-aa109e16` — an edit request that reaches a read-only or
  missing target shows the localized specific or generic project warning and
  returns before manifest sync, invalidation, refresh, or edit-mode entry.
- `REQ-REL-ee8f9ed0` — generated, imported, and narrator-copied sample WAV
  bytes are staged through the shared atomic persistence contract.
- `REQ-DATA-52fee282` — selected-language writes validate an existing project
  manifest before initializing or mutating `characters_voice.json`; missing
  manifests retain the established fallback, while corrupt, unreadable, and
  unexpected failures propagate without reporting success.
- `REQ-UX-f80d35c2` — expected manifest failures become read-only recovery
  state or the existing project-error warning, without target synchronization
  or partial normal page application.
- `REQ-UX-7a0a2d7a` — the page header carries the title and the batch-generation
  action alone; the four read-only boxes for original language, translated
  language, voice assignment, and voice language are gone, because the Home
  page already owns those choices and they were not editable here.
- `REQ-NFR-9792c51a` — the page-state payload carries no original-language,
  translated-language, assignment-mode-label, or language-entries field. The
  selected voice language stays, because sample generation and preview text
  read it. `language_entries` still lives inside the state service, where it
  validates the saved voice language against the selectable codes.
- `REQ-UX-880bcda6` — the action row under the preview text box runs edit,
  save, import sample, generate sample, preview, in the order the operator
  works it.
- `REQ-UX-10020786` — the two prompt actions are labelled with the single
  word for edit and for save in the interface language, so the five buttons
  fit one row. The `character_voices.edit_prompt` and
  `character_voices.save_prompt` keys keep their names; they name the action,
  not the label, and no other page reads them.
- `REQ-NFR-b3fb9944` — the page applies selection through its controller-owned
  full-state payload and exposes `current_target_id()` without a stale direct
  selection-application method.
- `REQ-FUNC-7a68a78e` â€” shared runtime orchestration returns generated data to
  the character controller, which retains target-owned persistence, batch
  sequencing, refresh, manifest sync, and downstream invalidation.
- Narrator targets are preview-only; character targets retain stable IDs across
  character renames and store sample metadata with their project-local WAVs.
- Readiness requires the selected narrator WAV and metadata plus every character
  target WAV and metadata; the manifest stage remains a promotion-only high-water
  mark.

## Invariants

Narrator targets reuse the selected narrator sample and remain read-only. Target
IDs remain stable during prompt edits and mode changes. A mode reset retains
operator prompt/preview edits and narrator data; downstream block/audio results
are governed by Project Lifecycle's confirmed impact plan.

## Persistence and workflow

The target plan is created lazily on the first Character Voices page-state build.
Controller synchronization therefore returns without writing the manifest when
the page has no targets and `characters_voice.json` does not yet exist. Once the
file exists, the controller may reload it when the page snapshot is empty and
derive truthful not-started, in-progress, or completed progress from disk.

Language persistence loads and validates `project.json` before target-file
initialization. A valid locked manifest continues to force the project target
language, an unlocked manifest saves normally, and a genuinely missing manifest
keeps the compatible target-initialization fallback. Validation, filesystem,
and unexpected manifest failures cannot act as an implicit unlock; expected
errors are logged at the write boundary and surfaced by state/controller UI.

Edit captures a prompt and preview draft in the page. Cancel restores those fields.
Saving changes confirms any destructive impact, clears the old sample pair and
invalidates generated audio for the edited target. An unchanged Save preserves
the sample and downstream audio.

New generated, imported and narrator-copied WAVs use the target ID under
`character_voice_samples/`. The stored path and spoken transcript remain in
`characters_voice.json`. Existing paths are read as stored. Sample publication
uses `replace_project_files` to restore the previous pair if replacement fails.

The batch worker records each target ID after publishing its sample. Success,
cancellation and generation errors reconcile the durable progress and use those
IDs for selective Audio Blocks invalidation. If rollback cannot finish, skip
reloading the voice plan while still invalidating audio for the saved IDs.

## Validation

Primary coverage:

- `05_Software/AudioMancer/tests/test_character_voices_service.py`
- `05_Software/AudioMancer/tests/test_character_voices_state_service.py`
- `05_Software/AudioMancer/tests/test_character_voices_page.py`
- `05_Software/AudioMancer/tests/test_character_voices_ui_controller.py`

The controller suite includes the real `MainWindow.set_current_page` first-entry
ordering, injected import failure, partial cancellation refresh, and persisted
ready-promotion regressions.

## Files

- `05_Software/AudioMancer/src/audiomancer/services/character_voices_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/character_voices_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/voice_sample_import_service.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/tts_runtime_ui_support.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/character_voices_page.py`
- `05_Software/AudioMancer/tests/test_character_voices_service.py`
- `05_Software/AudioMancer/tests/test_character_voices_state_service.py`
- `05_Software/AudioMancer/tests/test_character_voices_page.py`
- `05_Software/AudioMancer/tests/test_character_voices_ui_controller.py`
- `05_Software/AudioMancer/tests/test_tts_runtime_ui_support.py`
