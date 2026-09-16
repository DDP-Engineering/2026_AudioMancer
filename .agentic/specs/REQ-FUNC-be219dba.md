# REQ-FUNC-be219dba — Subscription backend protocol and lifecycle

Status: active.

## Purpose and scope

AudioMancer supports ChatGPT subscription authentication and text inference
alongside LM Studio, Ollama and OpenAI-compatible API-key profiles. The operator
signs in, selects and tests a model, saves a profile, and uses that profile in
existing JSON-based text workflows. Existing providers retain their settings,
request and workflow behavior.

One AudioMancer-owned account connection per OS user can serve multiple model
profiles. This feature covers text workflows only: TTS, tool execution, account
rotation, website scraping, cookie reuse and importing another application's
credentials are outside its scope.

This specification defines the shared contract for REQ-FUNC-bb149fc8,
REQ-FUNC-c27e4b20, REQ-FUNC-92d7fe25, REQ-SEC-5317d6ae, REQ-REL-90e02839,
REQ-FUNC-be219dba, REQ-FUNC-85b20482, REQ-UX-3d0aeaec, REQ-FUNC-cdc31a8f,
REQ-FUNC-0cbc8cba, REQ-SEC-6bf98d63, REQ-FUNC-92819b45, REQ-FUNC-cfd856fa
and REQ-FUNC-dbf2ccce.

## Behavior and interface

The backend is `chatgpt_subscription`; the first account reference is
`chatgpt-default`. Normalize the informational base URL to
`https://chatgpt.com/backend-api`; network destinations are constants, with
redirects rejected. Existing backends keep their Chat Completions behavior.

Subscription profiles normalize to an empty `api_key`, the canonical URL and
`credential_ref = "chatgpt-default"`; injected credential fields are discarded.
Retain profile identity, label, enabled state, model, timeout, context window,
output reservation and reasoning preference. A profile copied without its
account connection remains a subscription profile and requires sign-in when
used. Removing a profile does not disconnect the shared account.

Browser login uses PKCE S256, random state, localhost:1455/auth/callback,
explicit loopback binding, one-time matching callbacks and a five-minute
deadline. Device login uses the protocol defined below and a
fifteen-minute deadline, including pending and slow-down. Every exit closes
resources. Credential validation precedes saving and checks connection generation.

The store envelope has version, generation, credential (or null) and verified
model metadata. Tokens never enter profiles. Windows uses atomic DPAPI-protected
per-user storage outside portable settings; other platforms use a supported
native keyring. Session-only storage is explicitly selected, never a silent
downgrade. Lock state mutations across processes and threads; refresh within
five minutes of expiry with an authoritative recheck and 15-second network
deadline. Disconnect writes a fresh tombstone generation. Storage/refresh
errors expose safe fixed diagnostics rather than raw token-response errors.
Temporary refresh failures preserve stored state; revoked/invalid credentials
require sign-in. A rotated credential is persisted before use; failed persistence
cannot report a successful refresh. Account identity must remain unchanged by
refresh. Disconnect affects AudioMancer's local connection, not all OpenAI sessions.

Use httpx AsyncClient in the calling worker's asyncio loop. A 50-ms monitor
cancels and awaits the request on cancellation/deadline so contexts close;
there are no detached request threads. Restrict auth to fixed auth.openai.com
routes, inference to chatgpt.com/backend-api/codex/responses and model metadata
to chatgpt.com/backend-api/codex/models. Bound response
buffers and sanitize failures.

Responses requests contain model, instructions, user input_text, store=false,
stream=true. No tools, temperature or wire output-token maximum. Reasoning
`reasoning_effort=provider_default` omits an explicit effort; an explicit effort
is sent exactly as `reasoning.effort`. Supported values come from the selected
model's account catalog, with labelled built-in metadata as fallback. Unknown
models support Provider default until their effort metadata is discovered.
Unsupported explicit choices fail before inference and are never retried with a
different effort. Legacy subscription `enabled` migrates to `medium`, `disabled`
to `none`, and provider default remains provider default. A saved unsupported
choice remains visible as unavailable until the operator changes it. Keep the
legacy `reasoning_mode` as a budget summary: none is disabled, other explicit
efforts are enabled. Report both effective mode and explicit effort; provider
default means the server chooses and its exact internal effort remains unknown.
API-key/local mode semantics remain unchanged.
Optional text.format uses verified strict json_schema; other JSON
requests use the facade's existing prompt and JSON parser contract. Required
schemas need a successful model/generation capability test and cannot downgrade.
Translate const to a single-value enum only if needed without relaxing semantics.
Capabilities live with the account connection, not editable profile assertions.

SSE supports incremental UTF-8, CRLF, multiline data and comments. Reconcile
text deltas with terminal output, stopping at the complete event even while the
socket remains open. Refusal, failed/incomplete terminal, unexpected tool output,
malformed or oversized events and EOF without completion are failures.
Normalize terminal Responses usage into existing counters without adding cached
or reasoning subsets twice. Missing usage stays unknown.

An internal completion result carries text, usage and effective reasoning.
chat_json preserves its public signature/result; initial and repair requests
use the same dispatch/account. Caller-controlled retries remain bounded:
at most one pre-output 401 recovery, quota errors fail, transient Retry-After
is bounded, and emitted output is never automatically replayed. Cleanup's zero
retry and strict schema/no-model-repair behavior remains intact. Cancellation
propagates OperationCancelledError and never triggers repair.

Optional formatting fallback may remove schema formatting only after an explicit
HTTP 400 unsupported formatting-parameter/value rejection, when the caller allows
fallback and a retry remains. It is local to that request and does not downgrade
stored capabilities or future requests. Required schemas never downgrade.
Zero retries also forbids formatting retries and 401 replay. JSON repair is
limited to one repair of completed nonempty text and merges both calls' usage.

Account UI workers are independent of project workflow operations. Capture
profile identity and the owned worker attempt; changing the profile/backend/model,
closing or cancelling the editor invalidates late results. Opening settings never
launches login. Signed-in, catalog candidate,
model verified and schema verified are distinct states. Login/disconnect apply
immediately; profile Apply/OK retain existing semantics. Both languages explain
session-only mode, experimental compatibility and subscription allowance.

Subscription controls hide the API-key editor, make the canonical URL read-only,
disable temperature and editable schema assertions, and provide browser sign-in,
device sign-in, cancellation, disconnect, Refresh models and Test model. Refresh
models performs metadata discovery without inference. Account status on opening
settings refreshes stale metadata; successful sign-in forces a refresh. Profile
identity, selected model and unsaved edits survive catalog replacement. Disconnect during a job
cancels that job before writing the tombstone. Application shutdown cancels and
waits within its close budget; a still-running worker keeps the application alive
rather than being destroyed. Cancelling profile edits does not undo an immediate
account action.

The settings page has a scrollable two-column body with Cancel, Apply and OK in
a fixed footer. A compact profile list with its own vertical scrollbar occupies
the upper left; workflow defaults follow beneath it in the same column. The
selected profile editor occupies the right column with one numeric field
per row. The compact left column keeps default labels on one line and uses
equal font-derived selector widths. Columns stack when their natural widths
exceed the viewport. Rebuilding profiles preserves the list offset and ensures
the selected item stays visible. Font/style
changes recalculate list and compact action sizes; content scrolls when space is
insufficient. The initial dialog is 800x600 logical pixels, bounded by the available screen.
Idle sign-in and catalog status text use no form rows. Catalog source is available
in the Refresh models tooltip; active progress, device codes, errors and storage
warnings remain visible. Experimental
subscription guidance remains in help rather than a text block above the account
controls.

## Exact data and protocol

### Credential state

The protected envelope is an object with `version: 1`, opaque string `generation`,
`credential` (object or null) and `verified` (map from exact model identifier to
`text`/`schema` booleans). A credential contains `access_token`, `refresh_token`,
`expires_at` in Unix seconds, `account_id`, safe display `label` and optional
`residency` metadata. Validate nonempty token/account strings and finite positive
expiry before persistence or use. Decoded JWT claims supply metadata, not local
proof of token authenticity. An optional catalog contains normalized model IDs,
effort lists/defaults, optional default context_window and fetched_at. Login replacement and disconnect clear
verification and catalog metadata. Generation-checked catalog writes reject late
results and preserve newer metadata if concurrent refreshes finish out of order.

Credentials remain outside the repository, portable settings, projects, snapshots,
exports and release packages. Native storage rejects plaintext and chained keyring
fallbacks. Bound protected envelopes and OAuth response bodies to 256 KiB.
Serialize read/refresh/write and disconnect under the same thread/process lock;
recheck expiry and generation after acquiring it. Login commits only to the
generation captured before authentication. Inference and repair pin the same
generation, and reject completion if the connection changed during the request.

### OAuth destinations and messages

The public client identifier is `app_EMoamEEZ73f0CkXaXp7hrann`.
Use these fixed destinations; reject redirects:

| Operation | Destination |
| --- | --- |
| Browser authorization | `https://auth.openai.com/oauth/authorize` |
| Code exchange and refresh | `https://auth.openai.com/oauth/token` |
| Device-code creation | `https://auth.openai.com/api/accounts/deviceauth/usercode` |
| Device authorization polling | `https://auth.openai.com/api/accounts/deviceauth/token` |
| Operator device verification | `https://auth.openai.com/codex/device` |

Browser authorization sends `response_type=code`, client identifier, scopes
`openid profile email offline_access`, state, PKCE S256 challenge and
`redirect_uri=http://localhost:1455/auth/callback`. It also sends
`id_token_add_organizations=true`, `codex_cli_simplified_flow=true` and
`originator=audiomancer`. Bind `127.0.0.1:1455` before presenting the URL.
Accept only GET `/auth/callback` with exactly one matching state and a single
nonempty code. A matching denial terminates the attempt; an invalid state does
not complete it. Exchange the code using `grant_type=authorization_code`, the
original verifier, client identifier and identical redirect URI. Occupied port
or browser-launch failure offers device sign-in, not a different redirect URI.

Device-code creation posts the client identifier and receives `device_auth_id`,
`user_code` and polling interval. Display the code transiently. Poll with the
device identifier and user code at an interval bounded to one through thirty
seconds. Pending authorization continues polling; `slow_down` adds five seconds
up to thirty. Explicit denial or expiry stops polling. Exchange the authorized
code and verifier using `https://auth.openai.com/deviceauth/callback` as redirect.
Refresh posts `grant_type=refresh_token`, the current refresh token and client
identifier; retain the previous refresh token if a valid response omits its
replacement. Cancellation closes pending HTTP and loopback resources.

### Inference messages and limits

Send runtime bearer authorization and `ChatGPT-Account-Id` only to the fixed
Responses and catalog destinations. Responses uses
`https://chatgpt.com/backend-api/codex/responses`, together with
`originator=audiomancer`, `User-Agent: AudioMancer`, `Accept: text/event-stream`
and `OpenAI-Beta: responses=experimental`. Valid credential residency metadata
supplies `x-openai-internal-codex-residency`; do not infer it from locale or IP.

| Application input | JSON request field |
| --- | --- |
| Selected model identifier | `model` |
| System prompt | `instructions` |
| User prompt | `input: [{"role":"user","content":[{"type":"input_text","text":...}]}]` |
| Persistence and streaming | `store: false`, `stream: true` |
| Verified structured schema | `text.format` with type `json_schema`, schema name, `strict: true` and schema |

Bound an SSE event to 4 Mi characters and the stream to 32 MiB. Require
`response.completed` or `response.done` with status `completed`, no error and
no incomplete details. When terminal output is absent, collected assistant text
deltas may supply text; an explicit successful terminal event remains mandatory.
An incompatible supplied Content-Type is rejected. Empty text and `[DONE]` alone
are failures. Numeric Retry-After is capped at thirty seconds. HTTP 5xx, network
failure and recoverable rate limits may retry only before output and within the
caller allowance; exhausted quota and unavailable models fail without switching
accounts, models or transports. The profile timeout bounds each inference attempt.

### Shared JSON result and capability checks

`chat_json` returns an object with `payload` (parsed JSON object), `usage`
(`input_tokens`, `output_tokens`, `total_tokens`, `usage_available`) and
`request_metadata.reasoning_mode_effective` and subscription-only
`request_metadata.reasoning_effort_effective`. `structured_output` defaults to
true; `response_schema` defaults to absent and `response_schema_name` to
`audiomancer_json_response`. Required schema defaults to false; unconstrained
fallback and model repair default to true. An absent retry override uses the
configured request retry count. Disallowing unconstrained fallback with a
supplied structured schema makes that schema mandatory.

Test model sends tiny synthetic text and strict-schema probes. The latter uses
Cleanup's closed-object, required-field, constant/enum and bounded-answer-array
constraints, with a contrary plain-text prompt, and validates the exact batch and
answer structure returned. Successful text with a failed schema check permits
ordinary JSON text use but leaves strict Cleanup unavailable. Catalog names remain
candidates; manual model entry is supported and editable flags cannot grant access.
### Model discovery and cache

GET `https://chatgpt.com/backend-api/codex/models?client_version=<AudioMancer version>`
uses the connection's bearer/account headers, truthful AudioMancer originator and
User-Agent, optional credential residency, and Accept application/json. Reject
redirects, limit each metadata request to fifteen seconds and its body to 4 MiB,
and allow at most one 401 credential rotation/replay. Cancellation closes I/O.

Read the native `models` array, bounded to 200 entries. Keep visibility=list
entries whose input_modalities contain text; order by finite bounded priority.
Normalize slug to an ID of at most 200 ASCII identifier characters. Copy at most
16 supported_reasoning_levels effort identifiers (at most 32 lowercase identifier
characters each) and a default_reasoning_level only when included in that list.
Ignore provider instructions, tools and unrelated metadata. New valid model and
effort identifiers require no application update. Discovery grants no tested
text/schema capability. Copy context_window only when it is an integer from 1
through 2,147,483,647; other values remain unknown. max_context_window is not
the model default and must not substitute for it.

Store normalized metadata with its fetch timestamp in the current protected
connection envelope (or memory in explicit session-only mode). A one-hour cache
avoids repeated requests on settings opening. Older cached entries without the
context metadata field trigger a refresh even inside that hour. Refresh models bypasses the TTL.
Failed refresh retains the last valid same-connection cache as stale in the Refresh models tooltip;
missing/corrupt metadata uses labelled built-in candidates. Signed-out state uses
built-in candidates and never launches login automatically. Model discovery
does not switch the selected model, including manual or withdrawn model names.

Built-in suggestions include gpt-5.5, gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna
and gpt-6-astra. Candidate effort defaults follow the inspected catalog and are
not claims of successful inference for the operator's account.

Book Analysis's credential-free request fingerprint includes subscription effort,
so changing effort starts a new candidate instead of mixing checkpoint settings.

Selecting a subscription model applies its catalog context_window default and
clears the previous model's manual override. A subsequent manual context edit
survives catalog refresh, profile switching and settings reload until another
model is selected. Catalog arrival fills the selected model's default when no
manual override exists. Built-in candidates include the inspected 272,000-token
default; unknown model defaults retain the existing value. Selecting local/custom
endpoint models leaves their context manual; explicit Connect probe behavior
remains unchanged. Advertised defaults are metadata, not a full-capacity inference
test or a guarantee of the account's remaining quota.
Subscription profiles use the hosted-provider text allocation of thirty percent
of the configured context window and count as remote for Cleanup submission
accounting. Output reservation is local budgeting only. Derive missing total
usage from known input/output counts; cached-input and reasoning-output counts
are subsets. Token totals do not establish remaining subscription allowance or
an API price.

Existing operator-enabled prompt/result logging remains available. Authentication
diagnostics exclude complete OAuth URLs, verifier/state, device codes,
access/refresh/ID tokens, authorization headers and raw token-response exceptions.
Only safe account labels, profile identity, backend/model, status and normalized
usage may cross the protected credential boundary.

## Examples and acceptance

- Legacy LM Studio save/load and request-sequence tests remain unchanged.
- Cancel a stalled stream: contexts close and no late project result is applied.
- Cleanup without schema verification fails before book content is submitted.
- Concurrent refresh uses one durable rotation; disconnect rejects late login.
- Token sentinels never appear in settings, logs, errors or project/export data.
- Wrong-state callbacks do not complete sign-in; matching denial, cancellation
  and timeout release the listener without saving credentials.
- Corrupt protected storage fails safely; explicit disconnect permits recovery.
  Failed rotation persistence never returns a supposedly durable new credential.
- Optional schema rejection permits only the caller-authorized bounded fallback;
  required-schema and zero-retry calls fail without downgrading.
- Profile/backend/model changes discard late model-test results; shutdown retains
  ownership of a worker that has not stopped within the close budget.
- Native persistence claims require OS-specific save/load/rotation/disconnect
  evidence. Packaged support requires startup and secure-storage evidence;
  synthetic tests alone do not establish live entitlement or keyring availability.

## Compatibility boundaries

The native Codex protocol is experimental. Model and exact schema capabilities
are verified separately for the current account generation. Upstream public client IDs do not
prove a universal third-party registration contract. Use truthful AudioMancer
identification. Candidate models come from inspected Codex catalogs, not an
assumed entitlement. Linux packaging requires explicit evidence; no App Server
runtime is silently substituted.

A successful terminal response may omit Content-Type and carry an empty output
list when completed output_item events already supply the assistant text. These
items are validated before assembly; terminal success is still mandatory. A total
deadline is conservatively non-retryable because output may already have arrived.

Explicit session-only recovery can proceed when the protected store is unavailable.
The UI reports when an older saved connection could not be removed. That connection
is not used by the memory manager; switching back clears the protected connection
before enabling it. This does not claim deletion while the OS store is unavailable.
