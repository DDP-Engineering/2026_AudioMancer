<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-20817a63 - Model-associated context discovery

## Behavior

The normalized probe result carries `discovered_context_window` and
`discovered_context_model_name`. Both are populated only when the context is a
positive integer no greater than the AI Settings context control maximum and
the owner name equals the effective selected model. Missing, boolean,
non-numeric, non-positive, or larger values are ignored without failing the
otherwise successful model-list probe.

Generic OpenAI-compatible discovery may read `context_length` or
`max_context_length` from the exact selected `/models` entry. LM Studio also
performs optional `GET /api/v1/models`: it matches the configured model against
the model `key` or a loaded-instance `id`, preferring the matching instance's
`config.context_length`; without a matching loaded instance it may use the
matched model's `max_context_length`. Failure of this optional lookup leaves the
successful OpenAI-compatible model list authoritative and returns no context.

Ollama performs `POST /api/show` with `{"model": "<exact-selected-name>"}`
only after that name is confirmed in `/api/tags`. It accepts a value from
`model_info` only when the key's final dot-separated component is
`context_length`.

## Data / interface

`probe_profile(profile_payload)` continues returning the existing normalized
dictionary and adds `discovered_context_model_name: str | None`. The context
integer and owner name are either both populated or both `None`.

HTTP remains standard-library based. The shared JSON reader supports GET and
POST with an optional JSON object body so tests can inspect URL, method, and
body without a provider SDK.

## Examples

- Selected `google/gemma`, LM Studio model key `google/gemma`, loaded instance
  id `google/gemma` with context `8192`: return context `8192` owned by
  `google/gemma`.
- Selected `gemma4:latest`, Ollama `model_info` containing
  `gemma4.context_length = 131072`: return `131072` owned by `gemma4:latest`.
- Selected `model-a`, metadata only for `model-b`: return no discovered
  context and no owner.
- Context values `True`, `"large"`, `0`, `-1`, or `1000001`: ignore them.

## Acceptance

Mocked provider tests cover generic inline metadata, LM Studio loaded-instance
preference and model-limit fallback, Ollama request shape and qualified-key
extraction, no metadata, malformed bounds, and exact-model ownership.
