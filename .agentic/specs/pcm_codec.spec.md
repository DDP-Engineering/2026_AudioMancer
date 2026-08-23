<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: Internal PCM Codec

Companion specification for AudioMancer's internal PCM conversion requirements.

- Requirements: the `pcm_codec` functional set (sample-width conversion, channel
  conversion, stateful rate conversion, rejection and boundary behavior) and the
  testing requirement covering differential parity.
- Module: `05_Software/AudioMancer/src/audiomancer/services/pcm_codec.py`

## Behavior

The codec performs uncompressed linear PCM conversions that Audio Assembly and
Scene Mix need when a source WAV does not already match the target parameters.

The governing rule is **bit-exact deterministic behavior**: for every supported
input, each codec function returns the bytes specified below. The optional
`audioop` differential oracle verifies those semantics on interpreters where
that reference implementation is available.

Two consequences of that rule are deliberate and must not be "fixed" here:

- All sample widths are treated as **signed**, including width 1. WAV stores
  8-bit PCM as unsigned, but the codec contract interprets it as signed.
- Sample-width conversion is a pure arithmetic **bit shift**, not a rescale with
  rounding.

Samples are little-endian, matching the `wave` module's PCM payload.

### Supported inputs

- Sample widths: 1, 2, 3 and 4 bytes. Any other width is rejected.
- Channel conversion: mono to stereo and stereo to mono only.
- Trailing bytes: input whose length is not a whole number of frames is
  truncated to whole frames, matching `audioop`.

### Boundary and state effects

- Empty input returns empty output. `convert_frame_rate` still returns a valid
  state so a stream that starts with an empty chunk keeps working.
- `convert_frame_rate` is the only stateful function. The caller threads the
  returned state into the next call so resampling is continuous across chunk
  boundaries; a stream converted in chunks yields the same bytes as the same
  stream converted in one call.

## Data Structures

Rate-conversion state:

```text
state := None | (d, ((prev_0, cur_0), (prev_1, cur_1), ...))

d         int   fractional position counter; starts at -outrate after the
                inrate/outrate pair is reduced by their greatest common divisor
prev_n    int   previous input sample for channel n, scaled to 32-bit
cur_n     int   current input sample for channel n, scaled to 32-bit
```

Samples are scaled to a 32-bit domain internally, exactly as `audioop` does:

```text
width 1 -> value << 24
width 2 -> value << 16
width 3 -> value << 8
width 4 -> value
```

Per-width signed limits used for clipping:

```text
width 1 -> [-128, 127]
width 2 -> [-32768, 32767]
width 3 -> [-8388608, 8388607]
width 4 -> [-2147483648, 2147483647]
```

## Interface / Format

```text
SUPPORTED_SAMPLE_WIDTHS: tuple[int, ...] = (1, 2, 3, 4)

convert_sample_width(frame_data: bytes, sample_width: int,
                     target_sample_width: int) -> bytes
    Converts between supported sample widths by arithmetic shift.

mono_to_stereo(frame_data: bytes, sample_width: int,
               left_factor: float = 1.0, right_factor: float = 1.0) -> bytes
    Duplicates mono samples into clipped left and right channels.

stereo_to_mono(frame_data: bytes, sample_width: int,
               left_factor: float = 0.5, right_factor: float = 0.5) -> bytes
    Mixes stereo samples into a clipped mono channel.

convert_frame_rate(frame_data: bytes, sample_width: int, channels: int,
                   source_rate: int, target_rate: int,
                   state: object | None) -> tuple[bytes, object]
    Performs stateful linear-interpolation resampling.

Raises ValueError on an unsupported sample width, a non-positive channel count,
or a non-positive sample rate.
```

### Rate-conversion algorithm

The rate converter applies this algorithm:

1. Divide `source_rate` and `target_rate` by their greatest common divisor.
2. With no incoming state, set `d = -target_rate` and all channel samples to 0.
3. While `d < 0`, consume one input frame per channel into `cur`, moving the old
   `cur` into `prev`, and add `target_rate` to `d`. Stop and return when the
   input is exhausted.
4. While `d >= 0`, emit one output frame per channel computed as
   `(prev * d + cur * (target_rate - d)) / target_rate`, then subtract
   `source_rate` from `d`.

Integer division truncates **toward zero**, matching C, not Python's floor
division. This distinction is load-bearing for negative samples.

### Channel-mixing arithmetic

Both channel functions compute in floating point, then clip and floor:

```text
value = left * left_factor + right * right_factor
if value > maxval:        value = maxval
elif value < minval + 1:  value = minval
value = floor(value)
```

The `minval + 1.0` comparison is part of the byte-level boundary contract and
must not be simplified to `value < minval`.

## Examples

These golden examples define acceptance behavior and are generalized by the
differential test.

| Input | Expected result |
| --- | --- |
| `convert_sample_width(bytes([0x01, 0x80]), 1, 2)` | `00010080` — pure `<< 8`, so `1 -> 256` and `-128 -> -32768` |
| `convert_sample_width(bytes 0x01ff, 0x8000, 2, 1)` | `0180` — arithmetic `>> 8`, so `511 -> 1` and `-32768 -> -128` |
| `convert_sample_width(bytes 0x01ff, 2, 3)` | `00ff01` — pure `<< 8` into 24-bit |
| `mono_to_stereo(samples 1, -2, width 1, 1.0, 1.0)` | `0101fefe` — each sample duplicated |
| `stereo_to_mono(samples 100, 101, width 2, 0.5, 0.5)` | `6400` = `100` — `100.5` floors down, it does not round to `101` |
| `stereo_to_mono(samples 100, 100, width 1, 1.0, 1.0)` | `7f` = `127` — `200` clips to the width-1 maximum |
| `convert_frame_rate(b"", 2, 1, 44100, 22050, None)` | `(b"", (-1, ((0, 0),)))` — `d` is `-1` because `44100/22050` reduces to `2/1` |
| `convert_frame_rate(8 frames ending 2000, 3000, 2, 1, 44100, 22050, None)` | 8 bytes out and state `(-1, ((131072000, 196608000),))` — state holds 32-bit scaled samples, `2000 << 16` and `3000 << 16` |
| `convert_sample_width(b"", 2, 4)` | `b""` |
| `convert_sample_width(any, 2, 5)` | raises `ValueError` |

Rejection example at the call site: converting between channel counts other than
mono and stereo still raises `RuntimeError` from
`audio_assembly_service._convert_wav_channels` with the existing message
`Audio Assembly supports WAV channel conversion only between mono and stereo.`

## Acceptance

- [ ] Application source uses `pcm_codec` for PCM conversion.
- [ ] The codec exposes sample-width, channel and stateful rate conversion for
      widths 1, 2, 3 and 4.
- [ ] Sample-width conversion matches the golden and optional differential
      oracle for every ordered width pair drawn from `{1,2,3,4}`.
- [ ] Rate conversion matches the golden and optional differential oracle,
      including a chunked stream where state carries across calls.
- [ ] Mono-to-stereo and stereo-to-mono match the specified clipping and floor
      arithmetic.
- [ ] An unsupported sample width raises `ValueError`.
- [ ] Empty input returns empty output and a usable rate-conversion state.
- [ ] Unsupported channel conversion still raises `RuntimeError` with the
      existing Audio Assembly message.
- [ ] The optional differential parity test skips cleanly when its reference
      oracle is unavailable.
