<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# REQ-FUNC-32f94a76 - Character Discovery shall persist completed-window progress

## Behavior

The strict discovery checkpoint carries `completed_window_count` and
`planned_window_count` separately from `next_chunk_index`; completed work is
incremented only after a successfully completed planned discovery window.  The
strict synthesis checkpoint carries the same completed/planned baseline while
`next_candidate_index` advances candidate synthesis.  Cancellation, failure,
transition, and resume preserve these values.

## Data / interface

Discovery checkpoints contain exactly `phase`, `completed_window_count`,
`planned_window_count`, `next_chunk_index`, and `candidates`.  Synthesis
checkpoints contain exactly `phase`, `completed_window_count`,
`planned_window_count`, `next_candidate_index`, and `candidates`.  Both counts
are non-negative integers and completed cannot exceed planned.  The old
three-field checkpoints are a hard-break invalid document, not a repair or
compatibility path.

Discovery progress is completed/planned windows.  Synthesis progress retains
the combined work model: completed windows plus completed/planned candidates.
Public operation summaries expose the corresponding units truthfully.

## Examples

If the real twelve-window plan reaches chunk cursor 40 after five
variable-sized windows, the checkpoint is `completed_window_count = 5`,
`planned_window_count = 12`, and `next_chunk_index = 40`; it never reports 40
completed windows.  After discovery completes, a following synthesis checkpoint
retains the 12/12 baseline even when the source has 100 chunks.

## Acceptance

- Strict validation rejects missing, extra, non-integer, or negative fields.
- Resume reads the stored count and never derives it from a chunk cursor or a
  fixed window size.
- State, callbacks, manifest summary, and page notes retain unit-consistent
  completed/planned progress after cancellation, failure, transition, and a
  repeated resume.
