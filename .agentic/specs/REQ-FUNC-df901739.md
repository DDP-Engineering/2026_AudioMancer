<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-df901739 - Synthesis resume follows the candidate checkpoint boundary

## Behavior

Character Discovery keeps four runtime concepts separate: the root
`characters` array is the durable operator-visible inventory; checkpoint
`candidates` are discovery output waiting for synthesis; the completed
candidate prefix is prior synthesis progress; and `next_candidate_index` is
the exclusive cursor that divides completed from pending candidates.

A discovery checkpoint has no completed synthesis prefix even when durable
characters exist. A synthesis checkpoint recovers currently present AI records
whose stable character IDs correspond to candidates before the cursor. Manual
records do not participate in this relationship. A missing completed AI record
is treated as an intentional durable deletion and is not reconstructed.

## Data / interface

The strict `characters.json` root and checkpoint schemas do not change. Resume
logic uses `checkpoint.phase`, `checkpoint.candidates`, and the phase-specific
index. It preserves current nested inventory records directly and adds each new
AI profile after a successful synthesis response. Checkpoint persistence writes
the cursor from completed candidate work, never from inventory length.

At completion the current preserved inventory and newly synthesized profiles
are sorted by the established deterministic profile ordering. Ordering is a
presentation property only and never feeds progress restoration.

## Acceptance

- Discovery resume begins with zero synthesis progress regardless of inventory.
- Synthesis resumes at `next_candidate_index` with manual records in any order.
- Candidates before the cursor are not submitted and candidates at or after it
  are submitted once.
- Edited completed AI records remain byte-for-byte intact and deleted completed
  AI records remain absent.
- Cancellation, failure, and completion persist the same truthful inventory and
  cursor without duplicates or new schema fields.
