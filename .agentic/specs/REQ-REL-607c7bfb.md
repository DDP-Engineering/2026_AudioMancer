<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-REL-607c7bfb — Reject oversized classic WAV outputs before composition

## Behavior

Validate each pending output-plan item independently before Audio Assembly
persists a running report/state or starts Scene Mix materialization, frame copy,
or final-output temp-file creation. Completed resume records are not rewritten
and therefore are not revalidated as pending outputs.

The standard-library `wave` writer stores both the RIFF chunk length and the
data-chunk length as unsigned 32-bit integers. Because its RIFF chunk length is
`36 + data_bytes`, the binding PCM payload maximum is
`(2**32 - 1) - 36`, or `4,294,967,259` bytes. A planned payload equal to this
limit is legal when the output frame size divides it; the first whole frame
above it is rejected.

## Data / interface

Keep public functions and persisted payloads unchanged. Derive the output frame
size from the existing speech-preferred reference WAV parameters as
`nchannels * sampwidth` and sum planned output frames as follows:

- direct sources at the reference rate use their exact declared frame count;
- resampled sources use `ceil(source_frames * output_rate / source_rate)` as a
  conservative upper bound;
- explicit pauses and automatic gaps use exact integer floor division,
  `output_rate * milliseconds // 1000`, matching the silence writer;
- virtual Scene Mix blocks use the existing mix-target frame rule and then the
  same conservative rate-conversion bound into the final reference rate.

Multiply the summed planned frames by the output frame size. Reject only the
individual pending output whose bytes exceed the maximum; total bytes across
separate Per text chunk or Time limit files are not combined.

Raise `RuntimeError` naming the output and stating that it would exceed the
4 GB classic WAV limit, followed by the exact operator action: use Per text
chunk or Time limit output mode.

## Examples

- `4,294,967,258` planned mono 16-bit bytes are legal because they are frame
  aligned and below the maximum.
- The next mono 16-bit frame produces `4,294,967,260` bytes and is rejected.
- Two independent legal output files are accepted even when their combined PCM
  bytes exceed 4 GB.

## Acceptance

Tests exercise both sides of the derived byte boundary without allocating large
buffers, prove source conversion and silence are conservatively counted, prove
rejection precedes output work and persistence, and prove a legal boundary
continues to the existing writer seam.
