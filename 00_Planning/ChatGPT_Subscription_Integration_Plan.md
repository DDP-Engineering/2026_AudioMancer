<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# ChatGPT subscription support: analysis and agentic implementation plan

Date: 2026-09-16

Status: proposed implementation, based on source inspection; no live authentication or inference performed.

## 1. Objective and recommendation

Add **ChatGPT subscription** as another AudioMancer LLM backend, alongside LM Studio, Ollama, and OpenAI-compatible API-key endpoints. A user signs in through OpenAI, selects a supported model, and uses that profile in existing text workflows. Existing local and API-key profiles retain their behavior.

Recommended architecture: a native Python OAuth service and a dedicated ChatGPT/Codex Responses transport, behind the existing `llm_provider_service.chat_json()` interface. Keep renewable credentials outside settings and project files. Use browser login with PKCE, device-code login as a fallback, and HTTP server-sent events (SSE) for the first version.

Pi and OpenCode demonstrate the mechanism: **ChatGPT OAuth credentials authenticate requests to the Codex backend, not ordinary Platform API requests.** Replacing an API key with an OAuth access token in AudioMancer's current Chat Completions connector is insufficient. Subscription use also does not imply access to every ChatGPT model, unlimited requests, or access to audio/TTS APIs.

This document is the only requested repository addition. The research used no AEGIS lifecycle, journal, requirement creation, implementation changes, changelog changes, version changes, or commits. The implementation tasks below are future work, not authorization to execute them now.

## 2. Evidence baseline and limits

The following revisions were inspected directly on 2026-09-16:

| Project | Revision | Inspection scope |
| --- | --- | --- |
| AudioMancer | `c3566dd92a2a85a50654ebad2ae5ce3d59c60305` | Settings, backend probing, request execution, UI, usage, budgeting, workflow call sites, tests, packaging entry points |
| [Pi](https://github.com/earendil-works/pi/tree/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759) | `60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759` | OAuth, credential resolution/storage, Codex transport, provider catalog, relevant tests |
| [OpenCode](https://github.com/anomalyco/opencode/tree/e03db9bc6908f75c9334d8aa997deeaac81c0298) | `e03db9bc6908f75c9334d8aa997deeaac81c0298` | Built-in OpenAI Codex auth plugin, Responses provider selection, request transformation, credential storage, relevant tests |

The AudioMancer worktree was clean at the start. External repositories were downloaded into a temporary directory outside this repository; neither was executed. No local API keys, browser sessions, or existing Codex/Pi/OpenCode credential stores were read.

**Evidence classification:** Sections 3–5 describe observed source behavior. Sections 6–10 propose AudioMancer behavior. The compatibility questions in section 7 are unresolved until tested; upstream code establishes precedent, not a stable public service contract.

Official OpenAI documentation distinguishes ChatGPT subscription sign-in from Platform API-key billing and describes browser login and automatic credential refresh in Codex clients. It does not, by itself, establish a general public OAuth registration contract for arbitrary applications calling the private Codex HTTP endpoint. Revalidate the supported integration route and account eligibility before shipping. [OpenAI authentication documentation](https://learn.chatgpt.com/docs/auth)

## 3. Pi implementation analysis

### 3.1 Authentication and credential ownership

Pi registers a distinct `openai-codex` provider with subscription OAuth, separate from its ordinary OpenAI provider. Its authentication module offers browser and device-code login. [Provider registration](https://github.com/earendil-works/pi/blob/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759/packages/ai/src/providers/openai-codex.ts), [OAuth implementation](https://github.com/earendil-works/pi/blob/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759/packages/ai/src/auth/oauth/openai-codex.ts)

Observed protocol details:

- Authorization: `https://auth.openai.com/oauth/authorize`, authorization-code flow with PKCE S256 and a random state value.
- Scope: `openid profile email offline_access`.
- Public client identifier: `app_EMoamEEZ73f0CkXaXp7hrann`; this is an identifier, not a client secret or an API key. Its presence upstream does not establish AudioMancer's right or long-term ability to use that registration.
- Browser redirect: `http://localhost:1455/auth/callback`. Pi binds its callback server to `127.0.0.1` by default; an environment override exists.
- Browser login can also accept pasted authorization input. State is checked when supplied in that manual input; AudioMancer should require the full matching redirect URL if it ever implements this fallback.
- Token exchange and refresh: `POST https://auth.openai.com/oauth/token`, form-encoded. Credentials contain access token, refresh token, absolute expiry in milliseconds, and account ID.
- Account ID is extracted from the access token's `https://api.openai.com/auth.chatgpt_account_id` claim. Decoding claims supplies routing metadata; it is not JWT signature verification.
- Device flow requests a code from `/api/accounts/deviceauth/usercode`, shows `/codex/device`, polls `/api/accounts/deviceauth/token`, and exchanges the returned authorization code plus verifier using `/deviceauth/callback` as the redirect URI. Pi bounds this flow at 15 minutes and handles pending/slow-down responses.

Pi's generic auth resolver refreshes tokens with less than five minutes remaining, re-reads credentials under the store lock, and persists rotated credentials before releasing it. It does not silently fall back to environment API keys when a stored OAuth credential fails. Its file-backed credential store uses `auth.json`, restrictive creation modes and interprocess locking. These are useful lifecycle patterns; the POSIX modes alone are not a Windows secret-storage design. [Auth resolution](https://github.com/earendil-works/pi/blob/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759/packages/ai/src/auth/resolve.ts), [Credential storage](https://github.com/earendil-works/pi/blob/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759/packages/coding-agent/src/core/auth-storage.ts)

### 3.2 Request and response handling

Pi implements a dedicated `openai-codex-responses` transport. It sends requests to the Codex Responses route under `https://chatgpt.com/backend-api`, with bearer access token, ChatGPT account ID, client identification and streaming headers. The body includes `model`, `instructions`, Responses-format `input`, `store: false`, and `stream: true`. Reasoning controls use a nested `reasoning` object. Temperature is optional in this implementation, so a blanket claim that the backend always rejects temperature would be unsupported. [Transport implementation](https://github.com/earendil-works/pi/blob/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759/packages/ai/src/api/openai-codex-responses.ts)

The transport handles SSE and WebSockets, maps terminal/error events, accounts for usage, supports cancellation, and distinguishes some terminal quota failures from retryable transport/rate-limit failures. It uses a provider-specific model catalog. AudioMancer does not need Pi's tool execution, multi-turn reasoning history, WebSocket reuse, compression, or cache-affinity machinery for this feature.

Pi's request builder does not demonstrate AudioMancer's exact JSON-schema output contract. Function-tool schema support in a coding agent is not evidence that a text response schema is enforced by the subscription endpoint. That must be tested separately.

Useful test precedents: [OAuth tests](https://github.com/earendil-works/pi/blob/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759/packages/ai/test/openai-codex-oauth.test.ts), [stream tests](https://github.com/earendil-works/pi/blob/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759/packages/ai/test/openai-codex-stream.test.ts), [auth resolution tests](https://github.com/earendil-works/pi/blob/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759/packages/ai/test/oauth-auth.test.ts).

## 4. OpenCode implementation analysis

### 4.1 Authentication and provider integration

OpenCode implements ChatGPT login inside its built-in OpenAI Codex auth plugin. It offers browser OAuth, headless device login, and manual API-key entry under the `openai` provider. It uses the same public client identifier, issuer, scope and browser redirect port as Pi. [Codex plugin](https://github.com/anomalyco/opencode/blob/e03db9bc6908f75c9334d8aa997deeaac81c0298/packages/opencode/src/plugin/openai/codex.ts)

Its browser flow generates PKCE and state, accepts the callback and exchanges the code. It has a five-minute browser callback timeout. The inspected listener calls `listen(port)` without an explicit loopback host; AudioMancer should bind explicitly to loopback. The inspected headless polling loop has no explicit overall deadline; use a deadline and cancellation in AudioMancer.

OpenCode's OAuth credential variant stores `refresh`, `access`, `expires`, and optional `accountId` in its application-data `auth.json`; API credentials are a separate variant. Its plugin deduplicates concurrent refreshes with a shared promise within the loader. Pi's interprocess recheck is a stronger model when multiple desktop processes can share one credential. [Credential variants and persistence](https://github.com/anomalyco/opencode/blob/e03db9bc6908f75c9334d8aa997deeaac81c0298/packages/opencode/src/auth/index.ts)

Account extraction checks ID-token claims, then access-token claims, and supports root/namespaced account IDs and an organization fallback. It also extracts compute residency and sends `x-openai-internal-codex-residency` to the Codex route. These are observed compatibility details to investigate, not a reason to guess an organization or region in AudioMancer.

### 4.2 Why its URL rewrite works

OpenCode's OpenAI provider uses the SDK's **Responses** model implementation. Its OAuth fetch wrapper replaces authorization, adds `ChatGPT-Account-Id`, and rewrites applicable requests to `https://chatgpt.com/backend-api/codex/responses`. It supplies a dummy API key only to satisfy SDK configuration; the actual request carries the OAuth access token. The wrapper does not itself convert a Chat Completions payload into a Responses payload. Copying only this rewrite into AudioMancer would therefore be incorrect. [Provider selection](https://github.com/anomalyco/opencode/blob/e03db9bc6908f75c9334d8aa997deeaac81c0298/packages/opencode/src/provider/provider.ts), [Request options](https://github.com/anomalyco/opencode/blob/e03db9bc6908f75c9334d8aa997deeaac81c0298/packages/opencode/src/provider/transform.ts)

The request transformation defaults storage off. The Codex plugin removes the output-token setting, filters its model catalog for OAuth use, adjusts some context limits and sets catalog API costs to zero. AudioMancer should not interpret zero catalog cost as unlimited/free usage or treat the filter as an authoritative account-entitlement list. OpenCode also has optional WebSocket transport; SSE is sufficient for AudioMancer's initial integration.

Its tests cover account extraction, compute residency, model filtering and concurrent refresh. [Codex plugin tests](https://github.com/anomalyco/opencode/blob/e03db9bc6908f75c9334d8aa997deeaac81c0298/packages/opencode/test/plugin/codex.test.ts)

### 4.3 Lessons to carry into AudioMancer

| Concern | Pi | OpenCode | Proposed AudioMancer choice |
| --- | --- | --- | --- |
| Backend identity | Separate `openai-codex` | Auth variant under `openai` | Separate `chatgpt_subscription` backend, easiest to keep distinct from arbitrary compatible endpoints |
| Authentication | PKCE browser and device flow | PKCE browser and device flow | Both, with bounded lifecycle and explicit account status |
| Refresh concurrency | Store lock and expiry recheck | Promise deduplication in loader | Account-scoped thread and interprocess coordination |
| Inference protocol | Dedicated Responses implementation | Responses SDK plus fetch interception | Small Python Responses/SSE module |
| Model metadata | Bundled Codex catalog | Filtered provider catalog | Versioned, verified subscription catalog; honest availability labels |
| Storage | App-owned file | App-owned file | OS-protected store; session-only mode if unavailable |
| Reuse scope | Full agent infrastructure | Full plugin/SDK infrastructure | Protocol patterns only; no Node/Bun sidecar dependency |

Both inspected repositories use MIT licenses. If implementation copies or translates substantial code, retain the relevant copyright and permission notice in third-party notices and reconcile attribution with the repository style rules. A Python reimplementation of the protocol is not a reason to vendor either entire agent. [Pi license](https://github.com/earendil-works/pi/blob/60e7e76bd7ea25cad1dd6f3f1ce0d18814a42759/LICENSE), [OpenCode license](https://github.com/anomalyco/opencode/blob/e03db9bc6908f75c9334d8aa997deeaac81c0298/LICENSE)

## 5. Current AudioMancer architecture and change points

Paths in this section are relative to `05_Software/AudioMancer/src/audiomancer/`, unless specified otherwise. Line numbers refer to the inspected revision.

| Existing area | Observed behavior | Integration consequence |
| --- | --- | --- |
| `config.py:622` | Backend options are `lmstudio`, `ollama`, `openai_compatible`; one `ONLINE_AI_BACKEND_KIND` constant | Add the backend and a shared online-backend predicate/set; keep existing identifiers stable |
| `services/settings_service.py:198`, `_validate_llm_profile()` | Profiles are dictionaries. API key lives in profile/settings JSON. Unknown backend values are repaired to the default. Unknown extra profile fields are currently retained | Add explicit validation for the new backend/reference; never insert tokens into a profile or rely on normalization to remove them |
| `ui/pages/ai_settings_page.py` | Duplicated profile defaults, editable base URL/API key, model discovery cache, context overrides, operation-default selectors | Update both defaults, backend-sensitive editor, account controls, cached model semantics and async result ownership |
| `ui/controllers/ai_settings_ui_controller.py:82` | Connect calls `probe_profile()` synchronously and then applies results to the selected profile | OAuth and subscription probes must run outside the GUI thread; results must target the initiating profile |
| `services/ai_backend_service.py:88` | Requires a base URL, probes `/v1/models` except Ollama, optionally reads native context metadata | Subscription dispatch must occur before generic URL/model probing; API-key model discovery is not valid here |
| `services/llm_provider_service.py:95` | `chat_json()` handles prompts, retries, format/reasoning compatibility, JSON parsing/repair, usage and logging | Preserve the public call/return contract and dispatch transport beneath it |
| Same module, `_request_chat_completion()` | Uses standard-library `urllib`, bearer API key, `/v1/chat/completions`, JSON response with `choices` | Add dedicated Responses body, SSE parser and normalization; a URL-only change cannot work |
| Same module, cancellation wrapper | A daemon request thread runs while the caller polls every 50 ms; cancelling returns before the underlying HTTP call necessarily finishes | New transport must own a closable stream and bounded worker lifecycle; do not reproduce abandoned long-lived streams |
| Same module, `_repair_json_response_with_model()` | Calls the Chat Completions request helper directly for repair | Route repair through the chosen transport too, preserving the operation's repair policy and usage merge |
| `services/token_usage_service.py:37` | Reads Chat Completions `prompt_tokens`/`completion_tokens` | Normalize Responses `input_tokens`/`output_tokens` without breaking existing counters |
| `services/ai_budget_service.py:59` | Only `openai_compatible` uses online text budgeting | Subscription must count as online without removing context safeguards |
| `services/text_cleanup_service.py:1317` | Own online-provider predicate controls reporting of submitted fragments | Update reporting as well as budgeting so remote book text is accounted for correctly |
| `services/cleanup_ai_adjudication_service.py:542` | Requires a response schema; disables unconstrained fallback and model JSON repair; sets provider retry override to zero | Preserve this strict contract; successful generic JSON generation is insufficient |
| `services/character_discovery_service.py:276`, `narrator_profile_generation_service.py:160`, `speech_blocks_service.py` | Some workflows require profile ID, model name and nonempty base URL | Keep a canonical, non-editable subscription base URL in normalized profiles, or deliberately adapt those validators |
| `services/ui_state_service.py` | English and Romanian UI strings | Add both languages and retain localization parity |
| App `pyproject.toml` | Python 3.12–3.13, PySide6, no OpenAI SDK or credential-store dependency | Decide minimal dependencies explicitly; check frozen Windows and Linux packages |

Current request result contract:

```python
{
    "payload": {...},
    "usage": {
        "input_tokens": int_or_none,
        "output_tokens": int_or_none,
        "total_tokens": int_or_none,
        "usage_available": bool,
    },
    "request_metadata": {"reasoning_mode_effective": "provider_default"},
}
```

Consumers include AI chunking, translation, book analysis, character discovery, narrator-profile generation, speech blocks and cleanup adjudication. Their prompt formats, local validation, artifacts, resume logic and usage totals should continue through this interface. Audio generation and VoiceWeaver/TTS are a separate integration and outside this feature.

Additional constraints to preserve:

- Output reservation is a local budgeting concept. Existing connector tests explicitly check that provider output limits are omitted; do not convert `output_reserve_tokens` into a wire-level maximum.
- Reasoning preference is currently `provider_default`, `enabled`, or `disabled`. Preserve that saved contract; translate only in the backend adapter.
- Transaction logs redact selected dictionary keys but can also contain raw bodies/error strings. New auth paths must never log token bodies, authorization URLs/codes, or token-bearing exception strings.
- Cleanup resume fingerprints intentionally contain non-secret profile policy. Credential rotation must not invalidate workflow progress; account/profile changes must not silently move an in-flight request to a different identity.

## 6. Proposed design

### 6.1 Backend and profile contract

Add `backend_kind = "chatgpt_subscription"`, displayed as **ChatGPT subscription**. Keep existing backend values unchanged. The new backend determines OAuth authentication and Responses transport; a second independently editable `auth_type` is unnecessary in the first version.

Add one non-secret nullable `credential_ref` to profiles. It identifies an AudioMancer-owned account connection, not an access token, email address or provider account ID. Existing profiles normalize with `credential_ref = None`. Subscription profiles normalize to an empty `api_key` and the canonical base URL `https://chatgpt.com/backend-api`; transport code uses its own fixed trusted endpoints, not the profile string.

Retain model, timeout, context/reservation, reasoning, label and enabled fields. Keep subscription capability metadata separate from the editable API-key settings. The existing `supports_structured_output` flag alone must not let a user assert an unverified subscription capability.

Scope for version one: one connected ChatGPT account/workspace per OS user, reusable across multiple model profiles. Keep `credential_ref` so future multi-account support does not require another profile migration. Do not implement account rotation or automatic account switching. Profiles on a machine without their credential resolve to **Sign in required**, without being replaced by LM Studio or an API profile.

### 6.2 Credential lifecycle

Create `services/chatgpt_credential_service.py` for secret storage, identity metadata, expiry and synchronized refresh. Proposed internal credential envelope:

```text
version, access_token, refresh_token, expires_at_utc,
chatgpt_account_id, optional compute_residency,
credential_generation
```

Use one atomic serialized envelope in an OS-protected store. Prefer a maintained keyring integration with a verified secure native backend; verify Windows token-size handling and frozen packaging in the spike. If that is unsuitable on Windows, use a DPAPI-protected blob in an ACL-restricted per-user directory. Choose and document one production path before implementation; never silently fall back to plaintext. On systems without secure persistence, offer an explicitly labeled session-only sign-in.

Credentials must remain outside the repository, portable settings directory, project directories, snapshots, exported reports and release payloads. Do not share or import `~/.codex/auth.json`, Pi auth files or OpenCode auth files. A copied portable installation should require sign-in on the destination machine.

Refresh rules:

1. Resolve by credential reference immediately before a request, including repair requests. Refresh proactively within a five-minute expiry margin.
2. Serialize refresh per reference across threads and processes. Re-read expiry and credential generation after acquiring the lock; another process may have refreshed or signed out.
3. Validate the token response and persist the complete rotated envelope before returning a usable credential. Test refresh-token omission behavior against the actual service; preserve a previous refresh token only when the verified contract allows omission.
4. Distinguish temporary network failures from revoked/invalid refresh credentials. Temporary errors preserve stored credentials; permanent auth errors require sign-in and stop request retries.
5. Increment/invalidate generation on disconnect or account replacement. A late login/refresh result cannot recreate a disconnected credential. Use the same lock for these mutations.
6. If token rotation succeeds remotely but persistence fails, do not silently return to a now-stale disk credential or repeat refresh indefinitely. Report the storage failure, retain only a controlled in-memory state if safe, and require reconnection when durability cannot be restored.

Sign-out removes AudioMancer's local credentials and invalidates pending auth work; it is not described as revoking every OpenAI session. An in-flight request may already have consumed quota. Never switch that request to a different account or API key.

### 6.3 Login service and UI

Create `services/chatgpt_auth_service.py` for protocol operations with no Qt dependency. Use a separate thin UI controller or worker for browser opening, progress, cancel, completion and shutdown. Reuse the existing QThread/queued-signal patterns; the workflow runner is modal and project-oriented, so do not force sign-in into project operation state.

Browser login should bind the verified callback port on loopback before opening the system browser, generate cryptographically random verifier/state, and retain a single pending attempt in memory. Validate callback path and state before either success or error processing, enforce one-time completion, suppress callback access logs, escape HTML output and close the listener on every exit. Support a bounded timeout and cancel. Do not choose an arbitrary port or redirect URI unless the registration is verified to allow it.

If the port is busy, the browser cannot launch, or loopback is blocked, offer device-code sign-in. OpenCode and Pi use provider-specific device endpoints; do not assume a standard RFC device response shape. Honor polling intervals and slow-down, impose an overall deadline, and cancel promptly. A manual pasted redirect fallback is deferred; if added later, require the full expected redirect with matching state.

AI Settings behavior:

- Existing backends keep their current fields and Connect behavior.
- Subscription backend replaces editable API key/base URL controls with **Sign in**, **Sign in with device code**, **Cancel**, **Disconnect**, and account status. Show only safe account/workspace metadata returned from the credential service.
- Show **Not signed in**, **Signing in**, **Signed in**, **Sign in again**, or **Temporarily unavailable** from runtime state. A saved `discovery_succeeded` flag is not evidence of current authentication.
- Clearly separate **Signed in** from **Model connection verified**. A catalog entry does not prove entitlement.
- Run auth/model verification outside the GUI thread. Capture profile ID and attempt ID; discard stale results after selection changes, profile removal, backend changes, cancellation or dialog destruction.
- Sign-in/disconnect are immediate account actions; Apply/Save governs profile edits. If a newly created profile is discarded, the account can remain connected for other profiles; explain this in the UI/help. Removing a profile does not silently disconnect shared credentials.
- Opening AI Settings or loading profiles never automatically launches the browser. Background workflows report that sign-in is required instead.

### 6.4 Provider boundary and Responses transport

Add `services/chatgpt_provider_service.py`. Keep `chat_json()` as the application facade. Refactor only the minimum necessary common logic: prompt/request intent, normalized provider result, JSON parsing/repair, logging and retry policy. Existing Chat Completions construction remains on the legacy branch and must pass the existing tests unchanged in behavior.

Introduce a small internal result record containing text, normalized usage, terminal status, safe diagnostic data and effective request metadata. Each transport produces this record. Avoid fabricating Chat Completions `choices` merely to disguise Responses as the old wire format. Both the original request and optional repair request must use the same dispatch and credential resolver.

The subscription request maps:

| AudioMancer input | Proposed Codex request mapping |
| --- | --- |
| `model_name` | `model`, from a verified subscription model entry |
| System prompt | `instructions`, preserving the workflow prompt |
| User prompt | `input` with a user message and `input_text` content |
| Storage/streaming | `store: false`, `stream: true` |
| Authentication | Runtime bearer access token plus `ChatGPT-Account-Id` |
| Client identification | Truthful AudioMancer originator/user agent, subject to compatibility verification |
| Reasoning | Nested `reasoning.effort`, mapped through the selected model's verified supported values |
| Response schema | `text.format` JSON-schema configuration only after endpoint/model verification |
| Temperature | Omit by default for this backend; enable only where verified supported, with UI explaining applicability |
| Output reservation | Local budgeting only; do not send `max_tokens`, `max_completion_tokens` or `max_output_tokens` by default |

Do not copy tool-related request fields, coding-agent instructions or encrypted reasoning history into AudioMancer's one-shot text requests. Inspect necessary beta/client headers in the spike. Preserve compute-residency routing when the service contract requires it; do not infer residency from locale or IP.

SSE parser requirements: incremental UTF-8 decoding, frames split across arbitrary reads, LF/CRLF separators, multi-line `data:`, comments/keepalives, bounded frame/output size, unknown nonterminal events, and malformed event errors. Accumulate only assistant output text, not reasoning summaries or tool arguments. Reconcile deltas and terminal output without duplication. Require an explicit successful terminal response; an EOF, `[DONE]`, parseable partial JSON or `response.incomplete` alone is not success. Normalize supported `response.done`/`response.completed` variants, and surface refusals, failed responses and truncation before JSON repair.

Use a network handle that can be closed on cancellation, short bounded I/O waits and an overall request deadline. Cancellation must stop reads/refresh waits/backoff, release handles and prevent late artifact writes. Start by assessing the existing standard-library transport; add a dependency only if it materially simplifies a tested shutdown requirement. Remote computation may continue after disconnection; never promise quota is refunded.

### 6.5 Structured output and repair

The public Responses API represents structured text output using `text.format`; strict schemas have restrictions, including closed objects. That is useful format guidance, not proof the subscription route supports the same feature. [OpenAI structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs)

Track separate capabilities for plain JSON generation, JSON-object mode and provider-enforced JSON schema. Test the actual cleanup schema, including `const`, bounded arrays, enums, required fields and `additionalProperties: false`. If a keyword requires translation, allow only a semantics-preserving conversion, such as a constant to a single-value enum, backed by tests.

For `require_response_schema=True`, verify capability before sending book content and enforce the exact operation contract. If unsupported, leave that operation unavailable for the subscription profile with an actionable explanation. Do not silently drop schema constraints, enable repair or substitute prompt-only JSON. Supporting the other workflows remains useful, but any release claiming complete workflow coverage must first satisfy cleanup's contract.

For workflows that already allow unconstrained fallback/model repair, retain those options. Fallback is call-local, only follows an explicit parameter rejection, and never downgrades future calls or other profiles. JSON repair consumes subscription quota and must use the same backend/account and accumulate its usage. Refusal, empty output, incomplete stream and truncation are not repairable JSON failures.

### 6.6 Model discovery, context and accounting

Do not call Platform `/v1/models` with OAuth tokens or claim a static catalog was discovered from the account. Neither inspected implementation establishes a stable account-specific discovery contract suitable to copy directly.

For version one, use a small versioned subscription catalog with source date, model ID, context/input limits, reasoning support and verified output capabilities. Populate it during the compatibility spike rather than embedding this document's upstream model names as permanent truth. Label entries as supported candidates; an explicit **Test model** performs a minimal request and reports model availability, consuming a small amount of subscription allowance. If an account-specific discovery route is verified, it can replace the catalog behind the same model descriptor contract.

Preserve manual context overrides and existing selected-model ownership rules, while applying verified backend input ceilings. Do not infer limits solely from the public Platform model catalog or model-name patterns. Add the subscription backend to online budgeting and cleanup remote-submission reporting, with tests for the exact existing online fraction behavior.

Normalize Responses usage to the existing counters, keeping unknown usage as unavailable rather than zero. Input includes any cached-input subset; output includes any reasoning-token subset, so do not add those subsets a second time. Keep token totals distinct from subscription limits: no conversion to dollars, remaining messages, unlimited usage or guaranteed remaining tokens. A quota dashboard is deferred.

### 6.7 Errors, retries and diagnostics

Use typed internal failures, surfaced as sanitized user messages. All retries must be bounded under one overall request budget; avoid multiplying adapter retries, facade retries and workflow retries.

| Condition | Required handling |
| --- | --- |
| Expired access token | Proactive synchronized refresh before inference |
| HTTP 401 before output | At most one forced refresh/replay, then require sign-in; record it as auth recovery, not unbounded transient retry |
| Forbidden workspace/model or model unavailable | Explain access/model issue; no silent model/account/API-key fallback |
| HTTP 429 with recoverable rate limit | Honor bounded `Retry-After` and cancellation within the caller's retry allowance |
| Subscription allowance exhausted | Stop; show reset time only if explicitly returned and valid |
| 5xx/network error before accepted output | Apply bounded transient retry only where caller permits it |
| Midstream disconnect or missing terminal event | Fail as incomplete; no automatic replay after output has started in version one |
| Invalid refresh credential | Mark sign-in required; preserve unrelated profiles |
| Unsupported schema/reasoning parameter | Apply only the capability/fallback policy described above |
| Cancellation | Propagate `OperationCancelledError`; no repair or retry |

Cleanup sets `retry_count_override=0`: it must not acquire hidden transient retries from the new adapter. One pre-output auth recovery may remain distinct, but must be documented and tested with cleanup's submission accounting; if it cannot be accounted for safely, surface the auth error instead.

Logs may contain the existing operator-enabled book prompts/results, with current behavior preserved. Authentication diagnostics must use an allowlist of safe fields: event, backend, profile/reference ID, status, sanitized provider error code, duration and request correlation ID. Never log complete OAuth URLs, device credentials, verifier/state, access/refresh/ID tokens, authorization headers, or raw token-response exceptions. Add sentinel-secret tests across application logs, transaction logs, GUI errors, settings, project snapshots, exports and packaged artifacts.

## 7. Compatibility spike and explicit unresolved decisions

Implement the smallest isolated experiment first, using a consenting test account and synthetic book fragments. Do not infer these answers from upstream code:

| Question | Evidence required | Consequence if unresolved/negative |
| --- | --- | --- |
| Is direct ChatGPT/Codex OAuth an appropriate supported distribution route for AudioMancer's text-processing use? | Current official integration guidance or provider confirmation, including client registration/originator expectations | Keep direct mode experimental; evaluate App Server instead of presenting a copied client ID as guaranteed integration |
| Which model IDs and account/workspace entitlements work? | One verified inference per initial advertised model and recorded account type, with no credentials in evidence | Catalog remains conservative; no generic promise that every subscription/model works |
| Does the route enforce AudioMancer's cleanup schema? | Exact request/response protocol, schema acceptance and local contract validation, plus rejection tests | Cleanup stays unavailable on that backend; retain existing API-key/local options |
| Which optional fields/headers and residency rules are needed? | Minimal successful request with honest AudioMancer identity; checked omission/rejection cases | Isolate verified compatibility constants; do not spoof another application's identity |
| Can secure credentials persist in packaged Windows/Linux builds? | Save/load/rotate/logout with realistic token sizes; lock/unavailable-store tests | Use documented session-only mode where persistence is unavailable |
| Can requests cancel and shut down promptly? | Synthetic stalled stream and live small-request cancellation | Choose a transport that provides bounded cancellation before UI rollout |

Alternative: official **Codex App Server** exposes a documented integration protocol with ChatGPT browser/device login, login cancellation, logout and account/rate-limit methods. It can own token lifecycle. It is an alternative to implementing the private HTTP protocol, not evidence that the latter is public. [Codex App Server documentation](https://learn.chatgpt.com/docs/app-server)

App Server would add a managed executable, subprocess/JSON-RPC lifecycle, version compatibility, model-turn translation and packaging work. A spike must verify structured output, no unintended tools/filesystem access, isolated application credentials/configuration and prompt behavior for book processing. Do not use the user's installed Codex profile by default, scrape its tokens, or silently switch architecture. Recommendation remains the smaller native adapter if the direct-route questions are satisfactorily resolved; otherwise make the App Server decision explicit before broad integration.

## 8. Ordered agent implementation tasks

Execute in dependency order. Each task should leave passing focused tests and a short evidence note. This is an implementation checklist, not an AEGIS workflow or a request for parallel agents. Read `01_Documentation/Code_Style.md` before writing Python and preserve its module/documentation conventions.

### Task 1 — Establish the integration contract

- Re-read the pinned upstream modules and check relevant changes since these revisions.
- Run the compatibility spike from section 7 under the future implementation request's authorization; record synthetic fixtures without secrets.
- Decide direct native protocol versus App Server, secure-store implementation, initial models and verified schema support.
- Record endpoint/body/event fixtures, timeout/retry decisions and the exact supported workflow matrix.

**Done when:** the implementer can demonstrate sign-in, one successful complete text response and a defensible capability matrix; unresolved capabilities are explicitly unavailable rather than assumed. Do not run large book jobs as the spike.

### Task 2 — Add profile and capability contracts

- Edit `config.py`, `services/settings_service.py` and the AI Settings default template.
- Add backend identity, credential reference, trusted canonical base URL, non-secret capability metadata and shared online-provider classification.
- Add tests for old-settings round trips, unknown fields, copied profiles without credentials, invalid backend/reference combinations, and unchanged API-key/local settings.

**Done when:** all existing profiles retain their effective behavior, new profiles survive save/load, and settings never persist OAuth secrets.

### Task 3 — Implement protected storage and refresh

- Add `chatgpt_credential_service.py`, secure-store dependency/packaging adjustments if selected, and focused tests with fake stores/clocks/HTTP responses.
- Implement atomic envelope writes, per-reference process/thread locks, expiry recheck, refresh, generation invalidation, storage failure and session-only behavior.
- Test two processes refreshing one credential, cancellation while waiting for a lock, disconnect during refresh and refresh-token rotation failure scenarios.

**Done when:** concurrent requests use one valid rotation and late work cannot restore disconnected credentials. No test uses a real user credential.

### Task 4 — Implement browser/device authentication

- Add `chatgpt_auth_service.py` with injected browser/HTTP/clock boundaries and bounded operations.
- Implement PKCE, state validation, loopback callback lifecycle, provider-specific device polling and token-response validation.
- Cover wrong/missing/replayed state, wrong route, cancellation, timeout, port collision, malformed/denied auth responses, polling slow-down and cleanup of resources.

**Done when:** login success/failure/cancel paths are deterministic in tests and work with the selected secure store. No background API request opens a browser.

### Task 5 — Implement Responses/SSE and facade dispatch

- Add `chatgpt_provider_service.py` and any small shared result/error types justified by the two transports.
- Adapt `llm_provider_service.py` at the request/response boundary, including the repair path; keep existing `chat_json()` arguments and result shape.
- Add robust SSE parsing, model-specific request mapping, terminal-state validation, usage normalization, cancellation and bounded retries.
- Implement verified schema enforcement and preserve operation-specific fallback restrictions.

**Done when:** subscription fixtures traverse `chat_json()` end to end; existing Chat Completions tests remain green; truncated valid-looking JSON never becomes a successful result.

### Task 6 — Integrate model verification, UI and shutdown

- Update `ai_backend_service.py` with subscription-specific probe dispatch before generic validation/discovery.
- Add the verified catalog and distinguish catalog contents, authentication status and successful model verification.
- Update `ai_settings_page.py`, `ai_settings_ui_controller.py`, optional `chatgpt_auth_ui_controller.py`, and `ui/main_window.py` wiring/shutdown ownership.
- Update both language dictionaries in `ui_state_service.py`.
- Test result delivery after profile switching/removal, dialog closure, account replacement and app shutdown; verify the event loop remains responsive.

**Done when:** users can sign in, choose/test a model, save a profile, restart and disconnect without putting tokens into settings or freezing the UI.

### Task 7 — Verify all workflow and persistence integrations

- Update `ai_budget_service.py` and `text_cleanup_service.py` online classification/reporting.
- Exercise existing profile validators in character discovery, narrator generation and speech blocks using the canonical URL approach.
- Verify cleanup strict schema, book analysis/translation/chunking JSON handling, narrator/character/speech-block workflows, JSON repair usage and operation cancellation.
- Inspect resume fingerprints, account replacement behavior, `project_export_service.py`, `project_snapshot_service.py` and transaction logs for credential leakage or changed artifact semantics.

**Done when:** each supported workflow uses the selected backend without special prompt rewrites; unsupported strict operations report a capability error before sending source text; API-key/local regressions pass.

### Task 8 — Package, document and deliver the implementation

- Add user help in both `06_SoftwareDocu/UserGuide/index.html` and `06_SoftwareDocu/UserGuide_ro/index.html`: subscription versus API billing, sign-in, model verification, quotas, schema limitations, session-only storage, sign-out and portable installs.
- Update `settings.example.json` only with non-secret examples; include dependency lock updates and required third-party notices.
- Inspect `02_Tools/audiomancer_windows.spec`, `02_Tools/package_windows_release.ps1` and `02_Tools/package_linux_release.sh` for credential-store/runtime packaging needs.
- Run focused tests while implementing, then the normal full suite, lint/style checks and packaged smoke checks on the final candidate. Report platform checks not performed explicitly.
- For the future delivery, record the user-visible change under `CHANGELOG.md` → `Unreleased`. Do not assign a release version unless requested; a release follows the repository's version workflow.

**Done when:** supported-platform evidence, workflow matrix, remaining limitations and clean credential-exclusion checks accompany the implementation. No commit, publication or release is implied by this planning document.

## 9. Acceptance and test matrix

| Area | Minimum required scenarios |
| --- | --- |
| Compatibility | Existing LM Studio, Ollama and OpenAI-compatible profiles retain URL/header/body behavior and default selections |
| Settings | Missing new fields, round trip, invalid reference, portable copy, backend switching, profile removal, no secret serialization |
| Login | Browser and device success; denied login; malformed response; wrong/missing state; port busy; cancel; timeout; device pending/slow-down |
| Storage | Restart, native store locked/unavailable, oversized credential, rotation, failed durable write, disconnect, session-only exit, concurrent processes |
| Refresh | Proactive expiry margin, one refresh for concurrent callers, one 401 recovery, revoked credential, temporary outage, logout/refresh race |
| Routing | OAuth tokens reach only fixed trusted auth/inference hosts; reject unexpected redirects; API-key headers never mix with OAuth |
| Requests | Responses input/instructions, reasoning mapping, optional fields, no output-token limit, canonical model identity and residency handling |
| SSE | Fragmented UTF-8/JSON, multiple frames per read, CRLF, multiline data, keepalive, unknown event, malformed event, bounded memory |
| Completion | Terminal event while socket stays open; refusal; failed/incomplete response; EOF without completion; duplicate delta/terminal text |
| JSON contracts | Cleanup schema and disabled fallback/repair; allowed fallback elsewhere; repair dispatch/account/usage; empty/truncated output rejected |
| Accounting | Normal, absent, cached and reasoning usage; repair merge; usage is not subscription quota or API price |
| Retries | 401 once, entitlement 403, quota exhausted, recoverable 429 with Retry-After, bounded 5xx retry, no post-output automatic replay |
| Cancellation | During login, refresh lock, token exchange, stream read and retry delay; app/dialog shutdown releases workers/listener/stream |
| UI | Backend-dependent controls, account status, model test, stale completion ignored, default-profile selection, English/Romanian parity |
| Workflows | Cleanup, chunking, translation, book analysis, character discovery, narrator profiles and speech blocks through the facade |
| Privacy | Sentinel credentials absent from logs/errors/settings/artifacts/snapshots/exports/packages; no third-party credential-store imports |
| Packaging | Windows frozen build and Linux supported build; browser callback and secure-store/session-only paths |

Relevant existing regression suites live in `05_Software/AudioMancer/tests/`: `test_llm_provider_service.py`, `test_ai_backend_service.py`, `test_settings_service.py`, `test_ai_settings_page.py`, `test_ai_settings_ui_controller.py`, `test_main_window_ai_profiles.py`, `test_token_usage_service.py`, `test_ai_budget_service.py`, cleanup contract suites, workflow service suites, cancellation/shutdown suites and localization suites. Add dedicated auth, credential, provider and UI-controller tests beside them; use synthetic provider fixtures and disable live network by default.

Run commands from `05_Software/AudioMancer/` during implementation:

```powershell
uv run pytest -q tests/test_llm_provider_service.py tests/test_ai_backend_service.py tests/test_settings_service.py tests/test_token_usage_service.py tests/test_ai_budget_service.py
uv run pytest -q tests/test_ai_settings_page.py tests/test_ai_settings_ui_controller.py tests/test_main_window_ai_profiles.py tests/test_localization_parity.py tests/test_main_window_operation_shutdown.py
# Also run the new auth/provider tests and affected workflow contracts.
uv run pytest -q
# Scope lint/format checks to changed Python files, following the project guide.
uv run ruff check <changed_python_files>
uv run ruff format --check <changed_python_files>
```

The default suite excludes opt-in performance tests according to `pyproject.toml`; do not claim those ran. No application or upstream test suite was executed for this research-only delivery.

## 10. Scope boundaries and implementation handoff

Version one includes account login/refresh/disconnect, secure persistence, subscription profile selection, verified models, text generation through the shared facade, structured output where verified, cancellation and actionable quota/auth failures. It excludes ChatGPT web scraping, browser-cookie reuse, arbitrary OAuth endpoints, importing another app's credentials, account rotation, TTS/audio access, WebSocket optimization, conversational tools and a subscription-usage dashboard.

Implementation agent starting prompt:

> Implement the ChatGPT subscription backend described in `00_Planning/ChatGPT_Subscription_Integration_Plan.md`, starting with Task 1 and recording which compatibility assumptions are actually verified. Preserve API-key/local profiles and the `chat_json()` contract. Never weaken cleanup's required schema enforcement. Keep credentials outside settings/projects and route repair requests through the same backend. Follow the ordered tasks and acceptance matrix, report unsupported capabilities explicitly, and do not release or publish without the applicable authorization. This plan does not override the workflow instructions in the future implementation request.

The highest-risk work is establishing the direct integration contract, matching strict output semantics, protecting rotating credentials under concurrency, and guaranteeing bounded cancellation. Resolve those before polishing the account UI or claiming support for every workflow.
