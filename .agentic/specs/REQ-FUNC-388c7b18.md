<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-388c7b18 - Back off between retryable outer attempts

## Behavior

After outer attempt `n` fails transiently and attempt `n + 1` exists,
`chat_json` waits `min(4.0, 0.5 * 2 ** (n - 1))` seconds. Compatibility
adaptation stays inside the current attempt and has no wait. Permanent errors
and a transient error on the last configured attempt have no wait.

The wait checks `cancel_requested` before sleeping and after every short sleep
slice. Cancellation raises `OperationCancelledError` and exits before the next
provider dispatch. No single sleep spans the complete backoff duration.

## Data / interface

The public retry configuration is unchanged. A private wait helper accepts the
computed delay and optional cancellation callback, uses a monotonic clock, and
sleeps for at most 0.05 seconds per polling slice. Constants define the 0.5
second initial delay, 4.0 second cap, and 0.05 second polling interval.

## Examples

- Five remaining retries wait `0.5`, `1.0`, `2.0`, `4.0`, and `4.0` seconds.
- A 429 followed by success waits once; a final 429 does not wait.
- Cancellation observed during any slice stops the wait and no new HTTP
  request is started.

## Acceptance

Tests replace the wait or clock seam so they consume no wall-clock seconds,
assert exact delays and request counts, and demonstrate cancellation before
and during the wait plus unchanged cancellation while awaiting a response.
