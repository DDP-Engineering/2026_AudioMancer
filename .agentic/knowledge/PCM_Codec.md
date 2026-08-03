<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# PCM Codec

## 1. Purpose

Provides the linear PCM conversions Audio Assembly needs when a source WAV
does not already match the target parameters.

## 2. Responsibilities

- Convert linear PCM sample data between 1, 2, 3 and 4 byte sample widths.
- Convert between mono and stereo channel layouts.
- Resample between sample rates while carrying resampler state across chunks.
- It does not read or write WAV containers, choose target parameters, or mix
  audio blocks; callers own those decisions.

## 3. Implementation Overview

`pcm_codec` exposes four pure functions—`convert_sample_width`,
`mono_to_stereo`, `stereo_to_mono` and `convert_frame_rate`—over
little-endian signed samples. Width conversion is an arithmetic shift between
per-width 32-bit scale factors. Channel conversion mixes in floating point,
then clips and floors. Rate conversion reduces the rate pair by its greatest
common divisor and runs the linear-interpolation resampler, returning
`(position, per-channel (previous, current))` state for the next chunk.

The byte-level contract treats samples as **signed at every width including one
byte** (WAV itself stores 8-bit PCM unsigned), and width conversion **shifts
rather than rounds**. Integer division in the resampler truncates toward zero
rather than using Python's floor division.

## 4. Dependencies

- Internal: none. The module is self-contained.
- External: Python standard library only (`math.floor`, `math.gcd`).

## 5. Inputs And Outputs

- Inputs: little-endian signed PCM bytes, sample width, channel count, source
  and target sample rates, and prior resampler state.
- Outputs: converted PCM bytes, plus updated state from
  `convert_frame_rate`.

## 6. Data Contracts

- Supported sample widths are 1, 2, 3 and 4 bytes; anything else raises
  `ValueError`, as do non-positive channel counts and sample rates.
- Resampler state is `(position, ((previous, current), ...))` with one tuple
  per channel and samples scaled to 32 bits.
- Empty input yields empty output, and rate conversion still returns usable
  state so a stream may begin with an empty chunk.
- Bytes that do not form a whole sample or frame are ignored rather than
  raising.
- Conversion is deterministic: converting a stream in chunks yields the same
  bytes as converting it in one call.

## 7. Workflow Integration

The codec sits below Audio Assembly and is called only from its WAV frame-chunk
conversion path during final assembly and Scene Mix. It has no upstream
dependency and no UI surface.

## 8. Usage

Call directly with PCM bytes; thread the returned state through successive
`convert_frame_rate` calls when converting a stream:

```python
converted, rate_state = pcm_codec.convert_frame_rate(
    chunk, 2, 2, 44100, 48000, rate_state
)
```

## 9. Validation And Tests

Primary automated coverage: `tests/test_pcm_codec.py`.

Golden cases pin the specified semantics on every interpreter. Differential
cases use `audioop` as an optional reference oracle across width pairs, channel
counts, rate pairs, and a chunked stream. Streaming equivalence and
rejection/boundary cases require no external reference implementation.

Minimum validation after a change: run `tests/test_pcm_codec.py` and
`tests/test_audio_assembly_service.py`, plus `uv run ruff check` on changed
files. Manual listening remains required for audible judgments.

## 10. Limitations And Future Work

Handles uncompressed linear PCM only; compressed formats, sample widths outside
1-4 bytes and channel layouts beyond mono/stereo are out of scope. Conversion
is a per-sample Python loop; if assembly throughput becomes a concern, those
loops are the place to optimize. Resampling is linear interpolation;
higher-quality resampling would be an audible behavior change and belongs in
its own decision.

## Files

From the adopted component map:

- `04_Software/AudioMancer/src/audiomancer/services/pcm_codec.py`
- `04_Software/AudioMancer/tests/test_pcm_codec.py`
