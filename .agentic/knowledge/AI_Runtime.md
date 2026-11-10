<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# AI Runtime

## Routing

For provider profiles, ChatGPT sign-in, model verification, JSON requests, retries or token usage, start at `llm_provider_service.chat_json`, `chatgpt_provider_service.complete` and `tests/test_chatgpt_provider.py`. Domain response semantics belong to the corresponding workflow component.

## Purpose and boundaries

AI Runtime is the cross-cutting provider boundary for AI-assisted workflows. It
probes configured OpenAI-compatible and Ollama backends, verifies ChatGPT subscription models, sends cancellable
structured chat requests, budgets context, renders prompts, tracks token use,
and lets operators manage AI profiles and defaults.

- Normalize backend discovery responses and connection failures without
  exposing provider-specific payloads to the UI.
- Derive OpenAI-compatible chat and model-probe endpoints through one shared
  version-aware URL policy (`REQ-FUNC-9273a9ed`).
- Associate optional context metadata with its exact effective model and
  preserve successful profile-local discovery across failed probes
  (`REQ-FUNC-20817a63`, `REQ-FUNC-e9d13e10`, `REQ-FUNC-6c33e242`).
- Build conservative context budgets and reject requests whose usable text
  budget is too small.
- Send JSON-oriented chat completions with structured-output fallbacks,
  retained call-local compatibility adaptations, bounded cancellation-aware
  retries, null/refusal handling, hard output-length failure detection,
  response repair, transaction logging, and redaction
  (`REQ-FUNC-23c51ea4`, `REQ-FUNC-18168ed4`, `REQ-FUNC-388c7b18`).
- Load, render, and validate prompt templates with exact placeholders.
- Normalize, merge, restore, and localize provider token usage, deriving a
  missing total from valid input/output counts without changing the durable
  schema (`REQ-FUNC-a0ea278d`).
- Present editable, localized AI profiles/default selectors and persist their
  merged settings through the shared settings controller.

It does not own domain prompts, project-local workflow artifacts, or the
semantic validation of a domain's provider response.

### Dependencies

Internal dependencies include configuration, URL/logging/UI-state/settings
services, and the App Shell dialog host. AI workflow components provide their
own prompts and operation state. External dependencies are httpx for subscription I/O, native DPAPI/keyring credential protection, standard-library
HTTP/JSON/threading primitives and PySide6 for profile UI; the runtime has no
hard SDK dependency on a particular AI vendor.

## Public interface

Inputs include normalized profile dictionaries, model/provider HTTP responses,
prompt template files and replacement values, chat messages/schema, optional
cancellation callbacks, and settings-page edits. Outputs include normalized
model descriptors/probe results, JSON objects, redacted transaction logs,
budget metadata, token-usage payloads/localized notes, and validated merged
settings payloads.

Domain services call `context_budget_metadata`, `render_prompt`, and
`chat_json`, passing their own request schema/cancellation/log destination.
Controllers resolve enabled profiles rather than reading settings directly.
The App Shell invokes `show_ai_settings_dialog`; users can add/remove profiles,
switch among profiles without losing dialog-session edits
(`REQ-FUNC-8eba808c`), probe connectivity, select defaults, and save the
resulting settings payload. The middle action is labeled Apply because it
persists without closing; OK persists and closes (`REQ-UX-aa109e16`). Reopening
after Cancel reloads persisted settings, so Cancel continues to discard the
dialog session. Both Apply and OK save the payload, reload it, and refresh only
the current workflow page through `MainWindow.refresh_current_page_state()`;
they do not reapply the application-wide theme, font, or language or rescan
project export readiness, because AI Settings changes none of those
(`REQ-FUNC-d335d502`, `REQ-NFR-dfe9ab8a`).

## Invariants

A profile carries enabled state, backend kind, base URL, model identifier,
context/output/time-out/temperature values, structured-output support, and
optional API key. Probe results keep model context and loaded server context
as separate optional positive values owned by the exact selected model.
A failed probe retains discovery metadata for the same connection. Changing
the model clears the loaded-context observation, and changing endpoint or
backend clears both local limits. The context field and request budget use the
loaded context when reported or fall back to the model maximum. Local profiles
auto-fill from a loaded instance until the operator sets a value. AI Settings
exposes context and temperature, plus the model’s reasoning options when
available. The output reserve and timeout are internal profile values. Workflow
resolution caps the reserve at half of effective context. Subscription catalogs
contribute model defaults and retain explicit overrides.
Token
usage maps the provider's `prompt_tokens`, `completion_tokens`, and
`total_tokens` to input/output/total values plus `usage_available`. Finite
non-negative integral floats normalize to integers, and an absent/null total is
derived only when both input and output exist; a valid reported total remains
authoritative. Persisted usage notes restore only report and operation-metadata
usage; a noncanonical top-level operation-state field is ignored
(`REQ-NFR-6634ea30`). Repair usage is merged with the original response usage.
Prompt rendering requires exact named placeholders. Chat responses must parse
to JSON objects. Null scalar or multipart text is empty; a refusal explanation
becomes a clear safe ValueError, while reasoning-only output remains empty and
never triggers model repair. Explicit provider rejection of response_format
or max_tokens can trigger one applicable request-shape adaptation. Every
Chat Completions payload carries the planned output limit, using max_tokens
or the accepted max_completion_tokens field. Retries and JSON repair retain
that limit. The subscription Responses adapter uses the configured output
reserve for local budgeting. Transient outer retries wait 0.5, 1.0, 2.0, then
at most 4.0 seconds, polling cancellation every 0.05 seconds.
Logging redacts sensitive field names before persistence.

OpenAI-compatible generation and Test Connection append
`/v1/chat/completions` and `/v1/models` through `join_endpoint_url` with
duplicate-version collapse enabled. Root and proxy-prefixed bases therefore
gain one version segment, existing `/v1` bases do not duplicate it, and the
shared helper preserves query and fragment data identically for both paths
(`REQ-FUNC-9273a9ed`).

Callers may opt into a strict schema path. Strict calls require a profile that
advertises structured output plus a supplied JSON Schema, may disable the
unconstrained `response_format` fallback and model-based JSON repair, and may
override retry limits. Cleanup uses this path; existing AI
operations retain the default compatibility behavior.

For the first OpenAI-compatible chat-completion choice, an explicit
`finish_reason` of `"length"` is a hard provider failure: `chat_json` raises a
`RuntimeError` that identifies provider-side output truncation before it
reads message content, parses JSON, performs local repair, or issues a
model-repair request. Providers that omit the field remain compatible, and
other finish reasons keep their existing behavior. The diagnostic identifies provider-side truncation regardless of the
exact backend token accounting.

`REQ-NFR-8d83d955` makes a failure record keep the response it failed on. When
the provider answered and the exchange failed afterwards, the transaction log
record carries that response's raw body and normalized token usage under the
field names a successful record already uses; a transport failure produced no
response and records neither. Without this, a run could fill its log with
identical error lines that never show the token counts explaining them.

### Operational limits

Token counts are conservative estimates rather than provider tokenizers.
Provider networking remains synchronous inside the request worker, so timely
cancellation of an in-flight HTTP operation depends on polling/timeout behavior;
retry backoff itself is cancellation-aware. The settings-page suite
covers the current UI contract, but not live remote backend integration; that
requires controlled manual/provider testing. Domain services must still
validate output schemas beyond JSON-object parsing.

Explicit output-length termination is a hard provider failure and is never
repairable JSON.

## Change map

| Change requested | Start with | Focused verification |
| --- | --- | --- |
| Subscription protocol/account | chatgpt_*_service.py | test_chatgpt_auth.py, test_chatgpt_credentials.py, test_chatgpt_provider.py |
| JSON compatibility and usage | llm_provider_service.chat_json, token_usage_service | test_llm_provider_service.py, test_chatgpt_facade.py |
| Profiles and account controls | AiSettingsPage, ChatGPTAuthUiController | test_ai_settings_page.py, test_chatgpt_ui.py |

## Key behaviors

- `REQ-FUNC-bb149fc8`, `REQ-FUNC-85b20482`: subscription profiles dispatch through chat_json without changing its JSON/usage contract; repair pins the original account generation.
- `REQ-FUNC-c27e4b20`, `REQ-FUNC-92d7fe25`: cancellable browser PKCE and device-code login use fixed OpenAI destinations.
- `REQ-SEC-5317d6ae`, `REQ-REL-90e02839`: protected per-user credentials, durable tombstones and cross-process rotation locks own account state.
- `REQ-FUNC-be219dba`: bounded SSE requires terminal success and rejects refusals, tool output and incomplete streams before parsing or repair.
- `REQ-FUNC-cdc31a8f`: model candidates remain unverified until synthetic text/schema tests write account-bound evidence. Cleanup requires protected schema evidence.
- `REQ-FUNC-92819b45`: native account model discovery filters primary text models and caches only normalized metadata for one hour; failed refresh uses labelled stale cache or built-in candidates. Login/disconnect delimit cache ownership.
- `REQ-FUNC-cfd856fa`: subscription profiles store an exact reasoning effort, with model-specific choices and explicit rejection of unsupported saved preferences before inference. Provider default omits effort; API-key/local reasoning keeps its existing semantics.
- `REQ-FUNC-0cbc8cba`, `REQ-SEC-6bf98d63`: hosted budgeting and Responses usage share existing contracts; sensitive credentials and raw OAuth failures stay out of artifacts.
- `REQ-UX-3d0aeaec`: account jobs run independently of project modal workers and discard cancelled/stale profile results.

- Subscription default context (`REQ-FUNC-dbf2ccce`) uses the catalog context_window, not max_context_window. Metadata normalization validates positive bounded integers; missing defaults remain unknown and older cache entries trigger metadata refresh. The settings UI applies defaults on model selection and preserves later manual edits.

### Implementation behavior

`ai_backend_service.probe_profile` validates a profile URL/backend kind then
normalizes `/v1/models` or Ollama tags results. Generic OpenAI-compatible entries
may carry inline context metadata. LM Studio reads native model and
loaded-instance metadata. Ollama uses /api/show for the model maximum and
/api/ps for the confirmed loaded model. Operating-system and HTTP protocol failures during response
reading remain inside the normal failed-result boundary.
`llm_provider_service.chat_json`
dispatches subscription profiles to a native Responses adapter. For API-key/local profiles it
builds a `/v1/chat/completions` endpoint and request payload, supports response-format and reasoning
parameter compatibility retries retained across the current invocation,
cooperatively cancels both waiting requests and short-sliced exponential retry
backoff, rejects explicit output-length termination before content parsing or
repair, treats null/refused assistant content as non-repairable, parses/repairs
bounded non-truncated JSON responses, and redacts sensitive transaction logs.

`ai_budget_service` calculates the effective context and reserves prompt,
output and safety capacity for all workflows. Per-workflow input fractions
are ceilings on the remaining source budget.
`prompt_template_service` resolves template files and rejects missing or extra
placeholders. `token_usage_service` normalizes provider usage into a common
payload, while `ai_state_note_service` builds the shared enabled-profile
selector contract for Text Chunking, AI Translation, Character Discovery,
Speech Blocks, and narrator generation and produces localized persisted-usage
notes (`REQ-NFR-d559facc`). Cleanup retains its distinct whitespace-label
projection rather than being forced through that shared normalizer. The AI
Settings page owns in-memory profile editing/default selectors.
It tracks the stable profile ID represented by the editor, synchronizes that
owner before selection changes, treats successful probes as authoritative for
discovery, and lets failed probes update status without erasing prior metadata.
Its controller opens, probes, applies, or saves the dialog.

### Workflow integration

Text Cleanup, Text Chunking, AI Translation, Character Discovery, narrator
generation, and Speech Blocks obtain their selected profile, budgets, prompts,
provider request behavior, and usage notes here. The five behavior-equivalent
strip-normalizing selector wrappers delegate to the shared builder while
keeping their public workflow-specific names and configured-default keys.
Their source coverage and artifact semantics remain domain-owned.

### Book Analysis Integration

Book Analysis adds a profile-level `reasoning_mode` preference with
`provider_default`, `enabled`, and `disabled` values. The shared provider maps
explicit API-key preferences to a request field without inspecting model names and
retries once at provider default only when the backend explicitly rejects that
field. AI Settings is the sole UI location for context and reasoning controls
and also owns `default_book_analysis_profile_id`.

The domain applies its own minimum 16K context and conservative local/online
source fractions on top of shared token estimation. It uses the normal
structured-output compatibility boundary and validates domain payloads before
checkpointing. Automated Book Analysis tests replace provider calls in process
and install a failing network transport guard.

Subscription account workers have their own cancellation lifecycle and
credential manager. The Responses adapter and API-key Chat Completions
transport share the JSON/usage facade used by project workflows.

## Files

- `05_Software/AudioMancer/src/audiomancer/services/ai_backend_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/ai_budget_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/ai_state_note_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/settings_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/cleanup_ai_adjudication_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/ai_chunking_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/prompt_template_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/token_usage_service.py`
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/ai_settings_ui_controller.py`
- `05_Software/AudioMancer/src/audiomancer/ui/pages/ai_settings_page.py`
- `05_Software/AudioMancer/tests/test_ai_backend_service.py`
- `05_Software/AudioMancer/tests/test_ai_budget_service.py`
- `05_Software/AudioMancer/tests/test_ai_settings_ui_controller.py`
- `05_Software/AudioMancer/tests/test_ai_settings_page.py`
- `05_Software/AudioMancer/tests/test_ai_state_note_service.py`
- `05_Software/AudioMancer/tests/test_llm_provider_service.py`
- `05_Software/AudioMancer/tests/test_settings_service.py`
- `05_Software/AudioMancer/tests/test_cleanup_adjudication_contract.py`
- `05_Software/AudioMancer/tests/test_ai_chunking_service.py`
- `05_Software/AudioMancer/tests/test_ai_translation_service.py`
- `05_Software/AudioMancer/tests/test_main_window_ai_profiles.py`
- `05_Software/AudioMancer/tests/test_prompt_template_service.py`
- `05_Software/AudioMancer/tests/test_token_usage_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/chatgpt_auth_service.py` - subscription auth boundary.
- `05_Software/AudioMancer/src/audiomancer/services/chatgpt_credential_service.py` - subscription credential boundary.
- `05_Software/AudioMancer/src/audiomancer/services/chatgpt_http_service.py` - subscription http boundary.
- `05_Software/AudioMancer/src/audiomancer/services/chatgpt_model_service.py` - subscription model boundary.
- `05_Software/AudioMancer/src/audiomancer/services/chatgpt_catalog_service.py` - native model/default-context metadata, account-scoped cache and effort validation.
- `05_Software/AudioMancer/tests/test_chatgpt_catalog.py` - discovery bounds, primary-model filtering, cache ownership, renewal and cancellation.
- `05_Software/AudioMancer/src/audiomancer/services/chatgpt_provider_service.py` - subscription provider boundary.
- `05_Software/AudioMancer/src/audiomancer/services/chatgpt_storage_service.py` - subscription storage boundary.
- `05_Software/AudioMancer/src/audiomancer/ui/controllers/chatgpt_auth_ui_controller.py` - account worker/UI lifecycle.
- `05_Software/AudioMancer/tests/test_chatgpt_auth.py` - subscription auth regressions.
- `05_Software/AudioMancer/tests/test_chatgpt_credentials.py` - subscription credentials regressions.
- `05_Software/AudioMancer/tests/test_chatgpt_facade.py` - subscription facade regressions.
- `05_Software/AudioMancer/tests/test_chatgpt_models.py` - subscription models regressions.
- `05_Software/AudioMancer/tests/test_chatgpt_provider.py` - subscription provider regressions.
- `05_Software/AudioMancer/tests/test_chatgpt_settings.py` - subscription settings regressions.
- `05_Software/AudioMancer/tests/test_chatgpt_ui.py` - subscription ui regressions.

### Focused verification

Primary automated coverage:

- `tests/test_ai_backend_service.py`
- `tests/test_ai_budget_service.py`
- `tests/test_ai_state_note_service.py`
- `tests/test_prompt_template_service.py`
- `tests/test_token_usage_service.py`
- `tests/test_llm_provider_service.py`
- `tests/test_url_service.py`
- `tests/test_ai_settings_page.py`
- `tests/test_ai_settings_ui_controller.py`

These cover backend models/failures including response-read containment,
provider-specific exact-model context discovery, profile switching/mutation
ownership, failed-probe retention/settings reload, manual context overrides,
context budgets, token
normalization including derived totals and integral floats, merge/ordered
restore and localized notes, prompt placeholder rules, null/refusal and
multipart chat content, exact retained compatibility request sequences,
bounded retry timing/backoff cancellation, response-wait cancellation,
redaction, and profile dialog editing/probing/persistence. Minimum validation after a change:
run the focused modules above with `uv run pytest`, plus
`uv run python -m py_compile` and `uv run ruff check` on changed files.

`test_llm_provider_service.py` additionally verifies that both malformed and
otherwise valid output-length-limited responses fail after one provider
request, log `parsed_failure` rather than repaired success, preserve normal
`stop` and omitted-finish-reason parsing, and leave non-truncated
malformed-response model repair available. It also verifies that the length
error names the request's own limit, that a failure record following a provider
response carries that response's body and usage, and that a transport failure
records neither.
