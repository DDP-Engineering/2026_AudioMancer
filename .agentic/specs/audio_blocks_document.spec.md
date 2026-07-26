<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: Audio Blocks Single Document

Companion specification for the Audio Blocks consolidation requirements that
replace the four-artifact Audio Blocks persistence layout with one authoritative
document, and replace the stored generated-audio path with a derived one.

- Requirements: the Audio Blocks single-document functional set (document
  contract, projections, derived artifact paths, resume checkpoint, reset) and
  the updated artifact-naming and artifact-deletion requirements.
- Modules:
  - `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py`
  - `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_artifact_service.py`
  - `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_state_service.py`

This mirrors the Speech Blocks consolidation
(`REQ-FUNC-c71fbab4`, `REQ-FUNC-74be10fd`, `REQ-FUNC-ac0451b0`,
`REQ-FUNC-ad1ab6dc`, `REQ-FUNC-a4d7fcde`) and follows the same shape so both
operations stay consistent.

## Behavior

Audio Blocks previously wrote four artifacts at the project root:
`audio_blocks.json`, `audio_blocks_report.json`, `audio_blocks_state.json` and
`voice_clone_profiles.json`. The report and the state carried no information
that could not be recomputed from the block list, and the block payload carried
fields that were either duplicated from `speech_blocks.json`, constant for the
whole run, or never read back.

After this change Audio Blocks persists **one** metadata document,
`audio_blocks.json`. `voice_clone_profiles.json` stays a separate artifact
because it is a large model-side cache (about 32 KB per voice target) that would
otherwise be rewritten on every per-block checkpoint.

`load_audio_blocks_report()` and `load_operation_state()` remain part of the
service API and return **projections** computed from the document, so existing
consumers keep working unchanged.

This is a **hard break**. A missing document, a legacy list-format
`audio_blocks.json`, or a document that violates the root contract all read as
not-started. No legacy report or state file is read, and no migration path
exists: generated audio in projects created before this change is orphaned and
must be regenerated.

### Derived artifact paths

The governing rule is that a generated-audio path is a **pure function of
`speech_block_id`**, which is the block's stable primary key:

```text
audio_blocks/<speech_block_id>.wav
audio_blocks/parts/<speech_block_id>_part<NNN>.wav      NNN = 1-based, 3 digits
```

The previous naming embedded `chunk_id`, `sequence_index` and the normalized
speaker name. Both of those inputs are unstable while the block itself survives:

- `_next_unused_speech_block_id` may allocate an identifier whose numeric suffix
  no longer equals `sequence_index`, because it refuses to reuse historical ids.
- Renaming a character changes the normalized speaker name, and Audio Blocks
  deliberately *keeps* the existing audio in that case rather than regenerating.

Because the old name could drift away from the block that owned it, the path had
to be stored in `audio_relative_path` and repaired by a rename pass. Keying the
name on `speech_block_id` removes both: the stored path field and the rename
pass. A block's audio file name cannot change while the block exists.

Consequences that are deliberate and must not be "fixed" here:

- The generated file name no longer contains the speaker name. Speaker identity
  lives in `speech_blocks.json` and in the UI, not in the file system.
- No code path renames or remaps a generated audio artifact any more. Deleting
  and regenerating is the only transition.

## Data Structures

### Document contract

The root object has a fixed field set. Any other key set is a contract
violation and reads as not-started.

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
split_part_count        int          number of generated WAV parts
split_plan_fingerprint  str | null   guards reuse of existing part files
```

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

## Removed State

Each removal below is a field or artifact that carried no recoverable
information. They are listed with the reason so the deletion is auditable.

| Removed | Reason |
| --- | --- |
| `audio_blocks_report.json` | every field recomputable from blocks plus Speech Blocks |
| `audio_blocks_state.json` | duplicated the report; only the checkpoint was unique |
| `audio_relative_path` | derived from `speech_block_id` |
| `metadata_relative_path` | always null; the per-block JSON sidecar was never written |
| `generated_part_relative_paths` | derived from `speech_block_id` and `split_part_count` |
| `chunk_id`, `speaker_id`, `content_kind` | duplicated from `speech_blocks.json` and overwritten on every load |
| `sound_prompt`, `negative_prompt`, `duration_seconds`, `ambience_position` | duplicated from `speech_blocks.json` and overwritten on every load |
| `model_token_budget`, `model_audio_seconds_budget` | constant per run and never read back; recomputed from settings |
| `voice_language`, `prompt_format` (per block) | belong to the clone profile, not the block |
| `runtime_result_summary` | reached the display model but no page ever rendered it |
| `split_strategy` | carried no decision that `split_part_count` does not |
| `warning_flags`, `warnings`, `warning_count` | every report rebuild passed an empty warning list |
| `generated` / `approved` timestamps | only their presence was ever consumed; now booleans |
| `reused_prompt_count`, `regenerated_prompt_count` | cosmetic run counters shown in one status line |
| `next_profile_index` | clone-prompt preparation is idempotent and re-checks cheaply |
| `prompt_count` | always equal to the persisted clone-profile count |

### Fingerprint change

`generation_fingerprint` keeps its role as the per-block invalidation hash, but
its payload drops `special_block_status`, `voice_source_kind`,
`model_token_budget` and `model_audio_seconds_budget`.

The first two are a correctness fix, not a simplification: they were included in
the hash but never persisted, so a reload recomputed a different fingerprint
than the one stored and invalidated blocks that had not changed.
`_AUDIO_BLOCK_FINGERPRINT_VERSION` moves to `2` so pre-change fingerprints do
not compare equal by accident.

## Verification

- Round-trip: writing and reading a document preserves the field set exactly.
- Contract rejection: a legacy list payload, a missing file, and a wrong root
  key set each read as not-started, and no report or state file is created.
- Projection compatibility: `load_audio_blocks_report()` and
  `load_operation_state()` return the shapes their existing consumers read.
- Path derivation: the resolved WAV path for a block equals
  `audio_blocks/<speech_block_id>.wav` for every block, including after a
  Speech Blocks re-split preserves a block.
- Reset removes the document and any residual legacy report and state files.
