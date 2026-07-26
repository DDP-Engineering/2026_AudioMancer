<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# How To Test AudioMancer

This file lists the focused validation used for the selective downstream
preservation release work.

Run Python commands from `04_Software/AudioMancer/`.

## Automated Validation

Changed-file checks:

```powershell
uv run python -m py_compile src/audiomancer/services/ui_state_service.py tests/test_ui_state_service.py
uv run ruff check tests/test_ui_state_service.py --fix
uv run ruff format tests/test_ui_state_service.py
uv run pytest tests/test_ui_state_service.py
```

Selective workflow regression set:

```powershell
uv run pytest tests/test_workflow_impact_service.py
uv run pytest tests/test_text_chunking_state_service.py tests/test_text_chunking_page.py tests/test_text_chunking_ui_controller.py
uv run pytest tests/test_characters_ui_controller.py tests/test_character_discovery_service.py
uv run pytest tests/test_voice_sample_import_service.py tests/test_character_voices_ui_controller.py tests/test_narator_voice_ui_controller.py
uv run pytest tests/test_speech_blocks_service.py tests/test_speech_blocks_ui_controller.py
uv run pytest tests/test_audio_blocks_service.py tests/test_audio_blocks_page.py tests/test_audio_blocks_ui_controller.py
uv run pytest tests/test_audio_assembly_service.py tests/test_audio_assembly_page.py tests/test_audio_assembly_ui_controller.py
```

Full regression baseline:

```powershell
uv run pytest -q
```

Current expected result is `1096 passed, 62 skipped, 1 deselected`, in roughly
21 minutes. The previously documented `586 passed, 1 skipped` had been stale for
some time; the count above was measured directly.

## Regression Matrix

Expected covered behavior:

- chunk insert preserves unrelated Translation, Speech Blocks, and Audio
  Blocks while adding one untranslated chunk record
- chunk delete removes only affected Translation, Speech Blocks, Audio Blocks,
  and generated audio
- chunk edit resets only affected chunk downstream records and Audio Assembly
- character add preserves existing Speech Blocks, Audio Blocks, and Assembly
- character edit unapproves only assigned Speech Blocks and resets only their
  Audio Blocks
- character delete moves affected Speech Blocks to Narrator, unapproves them,
  and resets only their Audio Blocks
- character voice edit, sample import, and sample regeneration reset only Audio
  Blocks using the affected `voice_target_id`
- narrator voice edit resets narrator-driven Audio Blocks only
- Speech Block edit/reset/delete resets only that block's Audio Block
- Speech Block insert and approval preserve generated Audio Blocks and reset
  Assembly only
- Speech Blocks generation with Scene Ambience disabled preserves the existing
  narration/dialogue workflow
- Speech Blocks generation with Scene Ambience enabled creates opener, closer,
  and scene-change metadata blocks according to the selected policy and resumes
  from the next unfinished chunk after cancellation
- Audio Block selected reset/regeneration preserves unrelated Audio Blocks and
  resets Assembly
- Audio Blocks generation skips Scene Ambience when ambience audio is disabled
  and generates approved Scene Ambience WAV files through a sound-capable
  VoiceWeaver model when enabled
- Audio Block approval/unapproval preserves generated audio and resets Assembly
  only
- Audio Assembly settings changes preserve approved Audio Blocks and reset only
  assembly outputs/state/report
- Audio Assembly groups generated Scene Ambience prompt WAVs into on-demand
  Scene Mix previews and uses the same mixed segments in final assembly

Known broad reset that remains documented:

- AI Translation approval loss after a manual translation edit still broad
  resets downstream operation data through the current AI Translation
  controller. This is intentionally documented as a remaining broad reset for
  the v2 release rather than claimed as selective behavior.

## Manual QA

Use a small sample book and an offline or local AI/TTS setup when available.

1. Create a project, import a source file, extract text, clean text, chunk text,
   translate when needed, discover characters, prepare voices, generate Speech
   Blocks, generate Audio Blocks, approve them, and assemble audio.
2. Edit one Text Chunking chunk. Confirm that unrelated Translation, Speech
   Blocks, generated Audio Blocks, and audio files remain.
3. Insert one Text Chunking chunk. Confirm existing `chunk_id` values and
   existing audio survive, and only the new chunk needs translation/review.
4. Delete one character assigned to some Speech Blocks. Confirm those Speech
   Blocks become Narrator, become unapproved, and only their Audio Blocks are
   reset.
5. Import a WAV sample for one narrator profile. Enter the exact spoken sample
   text, select the profile, and confirm the sample previews and can be used by
   later Audio Blocks.
6. Import a WAV sample for one character voice. Confirm samples shorter than
   three seconds, silent files, and non-WAV files are rejected. Confirm imported
   samples reset only Audio Blocks using that character `voice_target_id`.
7. Change one character voice prompt or regenerate one character sample.
   Confirm unrelated character audio remains.
8. Edit one Speech Block. Confirm only that block's Audio Block is reset.
9. Enable Scene Ambience in Speech Blocks, accept the confirmation, generate a
   small chunk set, and confirm Scene Ambience opener/closer/scene-change
   blocks can be reviewed and approved.
10. Enable Scene Ambience Audio in Audio Blocks, accept the confirmation, and
   confirm spoken audio is generated before Scene Ambience audio for the same
   chunk when a sound-capable VoiceWeaver model is available.
11. Unapprove one Audio Block. Confirm generated audio remains and only Audio
   Assembly resets.
12. Change one Audio Assembly setting. Confirm approved Audio Blocks remain and
   only assembly outputs/state/report are reset.
13. On Audio Assembly, select a Scene Mix Preview, generate it, play it, then
    assemble audio and confirm the final audiobook uses one mixed ambience
    segment for that scene.
