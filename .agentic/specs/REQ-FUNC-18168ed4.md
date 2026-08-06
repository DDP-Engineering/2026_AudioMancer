<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-18168ed4 - Retain provider compatibility adaptations across retries

## Behavior

`chat_json` owns one mutable request shape for one invocation. Each outer
attempt begins with the most recently compatible shape. A 400 response that
explicitly rejects `response_format` removes that field only when
`allow_unconstrained_fallback` permits it. A 400 response that explicitly
rejects `max_tokens` replaces it with `max_completion_tokens`. Either
adaptation is retried immediately inside the same outer attempt.

Once applied, an adaptation remains in force through later transient outer
retries. It is never persisted to the profile or shared across calls. A
compatibility rejection is still a permanent error when policy disallows its
fallback or no applicable field remains to adapt.

## Data / interface

The public `chat_json` signature and retry-count meaning do not change.
Private marker exceptions carry provider rejections from the HTTP layer to the
call-level adaptation loop. Request payloads remain dictionaries and no
provider capability state is stored outside the invocation.

The existing `request_fallback` transaction record is emitted exactly when
`response_format` is first removed. Immediate token-parameter adaptation keeps
its component log message. Neither adaptation invokes outer backoff.

## Examples

- `response_format` request -> explicit 400 -> request without field -> 429 ->
  outer retry without field -> success.
- `max_tokens` request -> explicit 400 -> `max_completion_tokens` request ->
  503 -> outer retry with `max_completion_tokens` -> success.
- A new `chat_json` call starts again from the profile-supported original
  request shape.

## Acceptance

Captured payload sequences match the examples exactly; the configured outer
attempt count is unchanged; permanent and policy-disabled errors stop; only
one response-format fallback record is written; and no adaptation escapes its
invocation.
