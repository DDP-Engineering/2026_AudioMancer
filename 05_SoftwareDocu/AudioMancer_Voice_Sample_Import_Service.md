<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Voice Sample Import Service

## 1. Purpose

Documents `src/audiomancer/services/voice_sample_import_service.py`, the shared
validator for operator-provided WAV reference samples used by Narator Voice and
Character Voices.

The service confirms that a selected file is a usable non-silent WAV before
the caller copies it into project voice-sample storage.

## 2. Responsibilities

- accept only `.wav` files
- verify that the selected path exists and can be opened as WAV
- read WAV channel, sample-width, sample-rate, and frame-count metadata
- reject empty, malformed, too-short, or effectively silent samples
- return normalized audio metadata for downstream sample records
- expose imported-sample marker constants used by narrator and character voice
  services

It does not copy files, write metadata, transcode formats, trim silence, or
call VoiceWeaver.

## 3. Implementation Overview

Implementation file:

- `04_Software/AudioMancer/src/audiomancer/services/voice_sample_import_service.py`

Public constants:

- `IMPORTED_SAMPLE_SOURCE`
- `IMPORTED_SAMPLE_GENERATION_MODE`

Public function:

- `validate_imported_wav_sample(sample_path)`

Validation flow:

1. Normalize the input as a `Path`.
2. Require a `.wav` suffix and existing file.
3. Open the file with Python `wave`.
4. Read channel count, sample width, sample rate, frame count, and PCM bytes.
5. Require valid positive WAV metadata.
6. Compare duration with `config.DEFAULT_IMPORTED_VOICE_SAMPLE_MIN_SECONDS`.
7. Compute peak and RMS amplitudes from PCM data.
8. Reject samples below silence thresholds.
9. Return a metadata report for the accepted sample.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config` for `DEFAULT_IMPORTED_VOICE_SAMPLE_MIN_SECONDS`

External dependencies:

- Python standard library: `pathlib` and `wave`

## 5. Inputs And Outputs

Input:

- `sample_path`: string or `Path` pointing to a candidate WAV file

Output fields for accepted samples:

- `duration_seconds`
- `frame_count`
- `sample_rate`
- `channel_count`
- `sample_width_bytes`
- `peak_amplitude`
- `rms_amplitude`
- `silence_peak_threshold`
- `silence_rms_threshold`

Rejected samples raise `ValueError` with one of the current reason tokens:

- `unsupported_file_type`
- `missing_file`
- `invalid_wav`
- `sample_too_short`
- `sample_silent`

## 6. Data Contracts

The returned metadata is consumed by:

- `narrator_definition_service.import_narrator_sample(...)`
- `character_voices_service.import_character_sample(...)`

Imported voice sample records use:

- `sample_source`: `IMPORTED_SAMPLE_SOURCE`
- `generation_mode`: `IMPORTED_SAMPLE_GENERATION_MODE`

The service assumes uncompressed PCM-style sample data readable through
Python's `wave` module. One-byte samples are decoded as unsigned PCM; wider
sample widths are decoded as little-endian signed PCM.

## 7. Workflow Integration

Upstream UI callers:

- `narator_voice_ui_controller.py`
- `character_voices_ui_controller.py`

Downstream persistence owners:

- `narrator_definition_service.py`
- `character_voices_service.py`

The UI controllers request an operator-selected WAV file, then the owning
service validates and imports it. Validation metadata is stored with the
project-local narrator or character sample record.

## 8. Usage

Validate before import:

```python
from audiomancer.services import voice_sample_import_service

validation_report = voice_sample_import_service.validate_imported_wav_sample(source_path)
```

Callers should catch `ValueError` and translate the reason token into
operator-facing UI text.

## 9. Validation And Tests

Focused tests:

- `04_Software/AudioMancer/tests/test_voice_sample_import_service.py`

Covered behavior:

- accepts a valid WAV sample
- rejects too-short samples
- rejects effectively silent samples
- rejects non-WAV files
- rejects unreadable WAV payloads

Minimum validation after service changes:

```powershell
uv run python -m py_compile src\audiomancer\services\voice_sample_import_service.py tests\test_voice_sample_import_service.py
uv run ruff check src\audiomancer\services\voice_sample_import_service.py tests\test_voice_sample_import_service.py --fix
uv run ruff format src\audiomancer\services\voice_sample_import_service.py tests\test_voice_sample_import_service.py
uv run pytest tests\test_voice_sample_import_service.py
```

## 10. Limitations And Future Work

- the service does not normalize sample rate, channel layout, bit depth, or
  loudness
- non-WAV imports are rejected rather than transcoded
- silence detection uses simple peak/RMS thresholds, not speech detection
- operator-facing error messages are owned by UI/controller translation code
