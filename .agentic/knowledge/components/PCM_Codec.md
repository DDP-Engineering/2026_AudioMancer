<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# PCM Codec

## 1. Purpose

Provides the linear PCM conversions Audio Assembly needs when a source WAV does not already match the target parameters, without depending on the `audioop` standard-library module removed in Python 3.13.

## 2. Responsibilities

- Convert linear PCM sample data between 1, 2, 3 and 4 byte sample widths.
- Convert between mono and stereo channel layouts.
- Resample between sample rates while carrying resampler state across successive chunks.
- It does not read or write WAV containers, choose target parameters, or mix audio blocks; callers own those decisions.

## 3. Implementation Overview

`pcm_codec` exposes four pure functions — `convert_sample_width`, `mono_to_stereo`, `stereo_to_mono` and `convert_frame_rate` — over little-endian signed samples. Width conversion is an arithmetic shift between per-width 32-bit scale factors. Channel conversion mixes in floating point, then clips and floors. Rate conversion reduces the rate pair by its greatest common divisor and runs the linear-interpolation resampler, returning `(position, per-channel (previous, current))` state for the next chunk.

Each function reproduces its former `audioop` counterpart bit for bit, so the move off the removed module changed no produced audio. Two `audioop` quirks are reproduced deliberately rather than corrected: samples are read as **signed at every width including one byte** (WAV itself stores 8-bit PCM unsigned), and width conversion **shifts rather than rounds**. Integer division in the resampler truncates toward zero to match C, not Python's floor division.

## 4. Dependencies

- Internal: none. The module is self-contained so it can be tested and reasoned about in isolation.
- External: Python standard library only (`math.floor`, `math.gcd`).

## 5. Inputs And Outputs

- Inputs: little-endian signed PCM bytes, sample width, channel count, source and target sample rates, and prior resampler state.
- Outputs: converted PCM bytes, plus updated resampler state from `convert_frame_rate`.

## 6. Data Contracts

- Supported sample widths are 1, 2, 3 and 4 bytes; anything else raises `ValueError`, as do non-positive channel counts and sample rates.
- Resampler state is `(position, ((previous, current), ...))` with one tuple per channel and samples scaled to 32 bits; it is interchangeable with the former `audioop.ratecv` state shape.
- Empty input yields empty output, and rate conversion still returns usable state so a stream may begin with an empty chunk.
- Bytes that do not form a whole sample or frame are ignored rather than raising.
- Conversion is deterministic: converting a stream in chunks yields the same bytes as converting it in one call.

## 7. Workflow Integration

The codec sits below Audio Assembly and is called only from its WAV frame-chunk conversion path during final assembly and Scene Mix. It has no upstream dependency and no UI surface.

## 8. Usage

Call directly with PCM bytes; thread the returned state through successive `convert_frame_rate` calls when converting a stream:

```python
converted, rate_state = pcm_codec.convert_frame_rate(chunk, 2, 2, 44100, 48000, rate_state)
```

## 9. Validation And Tests

Primary automated coverage: `tests/test_pcm_codec.py`.

Coverage has three layers. Golden cases pin the measured semantics and run on every interpreter. Differential cases compare byte-for-byte against real `audioop` across all ordered width pairs, both channel counts and several rate pairs including a chunked stream; they skip automatically where `audioop` no longer exists. Streaming equivalence and rejection/boundary cases need no reference implementation.

Minimum validation after a change: run `tests/test_pcm_codec.py` and `tests/test_audio_assembly_service.py`, plus `uv run ruff check` on changed files. Run at least once on Python 3.12 so the differential layer actually executes rather than skipping. Manual listening remains required for audible judgements.

## 10. Limitations And Future Work

Handles uncompressed linear PCM only; compressed formats, sample widths outside 1-4 bytes and channel layouts beyond mono/stereo are out of scope. Conversion is a per-sample Python loop, so it is slower than the former C implementation; if assembly throughput becomes a concern, the per-sample loops are the place to optimise. Resampling is linear interpolation, matching the previous behaviour rather than improving on it — higher-quality resampling would be an audible change and belongs in its own decision.
