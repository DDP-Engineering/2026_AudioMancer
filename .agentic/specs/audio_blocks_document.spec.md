<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: Audio Blocks Single Document

Companion specification for the current authoritative Audio Blocks document,
derived audio paths, projections, resume checkpoint, and reset behavior.

- Requirements: the Audio Blocks single-document functional set (document
  contract, projections, derived artifact paths, resume checkpoint, reset) and
  the updated artifact-naming and artifact-deletion requirements.
- Modules:
  - `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py`
  - `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_artifact_service.py`
  - `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_state_service.py`

## Behavior

Audio Blocks persists one metadata document, `audio_blocks.json`.
`voice_clone_profiles.json` is a separate model-side cache so per-block
checkpoints do not rewrite the full voice-target inventory.

`load_audio_blocks_report()` and `load_operation_state()` remain part of the
service API and return projections computed from the document.

A missing document reads as not-started. A non-object payload or document with
an invalid root field set is rejected.

### Derived artifact paths

The governing rule is that a generated-audio path is a **pure function of
`speech_block_id`**, which is the block's stable primary key:

```text
audio_blocks/<speech_block_id>.wav
audio_blocks/parts/<speech_block_id>_part<NNN>.wav      NNN = 1-based, 3 digits
```

Speaker identity remains in `speech_blocks.json` and the UI. A block's audio
file name stays stable for the lifetime of its `speech_block_id`.

## Data Structures

### Document contract

The root object has a fixed field set. Any other key set is a contract
violation raises `AudioBlocksDocumentError` with reset recovery guidance.

```text
status              str    not_started | running | in_progress
                           | cancelled | failed | completed
voice_language      str    selected Character Voices language, "" when unset
input_fingerprint   str    stable hash of the generation inputs, "" when unset
checkpoint          null | object
blocks              array  ordered Audio Block entries
```

`checkpoint` is `null` when no resumable run exists, otherwise:

```text
run_token                str        operation start timestamp
current_phase            str        prepare_prompts | generate_blocks
current_block_id         str | null speech_block_id being generated
next_speech_block_index  int        >= 0, resume position in generation order
next_split_part_index    int        >= 0, resume position inside a split block
```

### Block contract

Every entry carries exactly these seven fields:

```text
speech_block_id         str          primary key, also derives the audio path
voice_target_id         str          voice used for this block
generated               bool         audio (or metadata-only handling) exists
approved                bool         operator approved this block
audio_can_play          bool         cached playability, avoids per-WAV probing
audio_duration_seconds  float | null measured duration, null when unmeasured
generation_fingerprint  str | null   invalidation hash for this block
```

Two further fields are emitted **only** when the block was actually split, that
is when `split_part_count > 1`:

```text
split_part_count        int          planned total number of WAV parts
split_plan_fingerprint  str | null   guards reuse of existing part files
```

For a cancelled split block, `next_split_part_index` is the completed-prefix
length for the current split plan. Resume validates part files from index zero
up to that value and reuses only the valid contiguous prefix. An invalid index,
planned-count mismatch, fingerprint mismatch, missing file, corrupt WAV, or
unsafe derived path makes that part the resume position; no later part is
skipped or merged. `split_part_count` retains its planned-total meaning.

### Worked example

```json
{
  "status": "completed",
  "voice_language": "en",
  "input_fingerprint": "14817f4098d75a98ee2a1c0b3f544929616244b6",
  "checkpoint": {
    "run_token": "2026-07-24T21:44:20+00:00",
    "current_phase": "generate_blocks",
    "current_block_id": null,
    "next_speech_block_index": 436,
    "next_split_part_index": 0
  },
  "blocks": [
    {
      "speech_block_id": "0001-000004",
      "voice_target_id": "narrator",
      "generated": true,
      "approved": true,
      "audio_can_play": true,
      "audio_duration_seconds": 10.32,
      "generation_fingerprint": "3e97a4fe8af657eddc944afb5a4ced2619d7f8e3"
    }
  ]
}
```

The block above owns `audio_blocks/0001-000004.wav`. Nothing in the document
states that; it follows from `speech_block_id`.

## Verification

- Round-trip: writing and reading a document preserves the field set exactly.
- Contract rejection: a missing file reads as not-started; a non-object payload
  and a wrong root key set raise the typed reset-recovery error.
- Projection compatibility: `load_audio_blocks_report()` and
  `load_operation_state()` return their contracted shapes.
- Path derivation: the resolved WAV path for a block equals
  `audio_blocks/<speech_block_id>.wav` for every block, including after a
  Speech Blocks re-split preserves a block.
- Reset removes the authoritative document.
