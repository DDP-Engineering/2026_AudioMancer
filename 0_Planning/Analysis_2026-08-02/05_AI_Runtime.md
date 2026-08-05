# Component Review — AI Runtime

_Reviewed 2026-08-02. Files: `services/llm_provider_service.py` (827), `services/ai_backend_service.py` (272), `services/ai_budget_service.py` (127), `services/token_usage_service.py` (176), `services/prompt_template_service.py` (125), `services/ai_state_note_service.py` (63), `ui/pages/ai_settings_page.py` (860), `ui/controllers/ai_settings_ui_controller.py` (127); plus `prompts/` (17 templates) and cross-checks in `config.py`, `settings_service.py`, `url_service.py`. Total ~2580 lines._

## Summary

The component is in good shape overall: HTTP timeouts are set everywhere, cancellation is cooperative and correctly typed, budget comparisons run the right direction, and API-key redaction in the transaction log is genuinely airtight (keys live only in headers, never in the logged request payload, and the recursive redactor covers nested `api_key`/`authorization` fields). At review time, two defects required attention: the AI Settings page silently discarded editor changes when the operator switched profiles, and the provider client did not inspect `finish_reason`, so a response truncated at `max_tokens` could be model-repaired into a smaller-but-valid JSON object and returned as success. Seven further small defects follow — a dead probe branch, a persisted list wiped by a failed probe, and several minor transport/accounting gaps. The original inventory was 0 Critical, 2 Major, and 7 Minor; AI-2 is resolved as recorded below.

## Implementation update — 2026-08-03

AI-2 was resolved in commit `6a866da` under `REQ-FUNC-3875ac3b`:

- `llm_provider_service._extract_message_content` now validates the first
  choice's `finish_reason` before extracting message content;
- an explicit string token `length` raises the fixed `RuntimeError` `AI provider
  response reached the provider output-token limit.` before JSON parsing, local
  repair, or a model-based repair request;
- the failure text contains no prompt, response content, credential, or raw
  provider-payload data, and the normal failure transaction-log path records
  `parsed_failure` rather than `parsed_success_after_repair`;
- `stop` and omitted finish reasons retain their existing parsing behavior, and
  non-truncated malformed-response repair remains available; and
- focused provider tests (20), direct Cleanup/Chunking/Translation caller tests
  (77), and the complete suite (1,224 passed, 1 skipped, 1 deselected) passed.

Explicit output-length termination is now a hard provider failure and is never
repairable JSON. The original finding below is retained as historical review
evidence.

## Implementation update — 2026-08-05

AI-1, AI-3, AI-4, and AI-8 were resolved in commit `6f75eaa` under
`REQ-FUNC-8eba808c`, `REQ-FUNC-e9d13e10`, `REQ-FUNC-20817a63`,
`REQ-FUNC-6f8e52c8`, and `REQ-FUNC-6c33e242`:

- the settings editor now records the stable ID of the profile whose values it
  displays and synchronizes those values to that owner before profile/list,
  default-selector, Connect, or save transitions;
- failed probes preserve the profile's last successful model list, selector
  options, discovered model/context pair, typed model, and configured context;
- successful probes report both `discovered_context_window` and the exact
  `discovered_context_model_name` that owns it. Generic OpenAI-compatible
  discovery reads model context metadata, LM Studio augments `/v1/models` with
  optional native `/api/v1/models` metadata, and Ollama queries `/api/show`
  only for the exact effective model confirmed by `/api/tags`;
- discovered context values must be positive integers no greater than
  1,000,000. Auto-fill occurs only when the result belongs to the effective
  model and the operator has not manually overridden the context window; and
- probe transport handling preserves dedicated HTTP-status messages while
  converting timeout, socket/read, `HTTPException`, decode, and JSON failures
  into normal, non-sensitive failed results through one failure builder.

Focused verification passed 69 tests. The full suite passed 1,301 tests with
1 skipped and 1 deselected; the only warning was the existing `audioop`
deprecation warning. A post-suite set of 21 backend tests and 2 profile tests,
plus Ruff and compile checks, also passed. The attempted impacted-test command
could not launch because 361 selectors exceeded the Windows command-length
limit; the successful full suite superseded it.

The original finding inventory remains below as historical review evidence.
After the recorded updates, AI-1, AI-2, AI-3, AI-4, and AI-8 are resolved,
leaving 0 Critical, 0 Major, and 4 Minor findings open. Original file/line
references describe the 2026-08-02 snapshot and are superseded where a
resolution is recorded.

## Findings

### [AI-1] Editing a profile then clicking another profile silently discards the edits — **Major, resolved 2026-08-05**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_settings_page.py:111`, `:567-578`, `:602-610`

- **What:** The list-selection signal loads the newly selected profile into the editor but nothing writes the *outgoing* profile's editor state back first.

```python
self._profile_list.currentRowChanged.connect(self._load_selected_profile_into_editor)
```

```python
def _load_selected_profile_into_editor(self, row: int) -> None:
    if self._loading_profile:
        return
    if row < 0 or row >= len(self._profiles):
        return
    self._load_profile_into_editor(self._profiles[row])
```

  `_sync_editor_to_current_profile()` is the only thing that copies the widgets back into `self._profiles`, and it is called from exactly three places — `build_settings` (:366), `build_current_profile_payload` (:397, i.e. the Connect button) and `_add_profile` (:729). No call site is reached on a plain row change. The editor widgets have no per-field change handlers either; the only two connected signals (`_on_model_name_edited`, `_on_context_window_edited`) just set override flags, they do not persist values.

- **Why it matters:** Operator opens AI Settings with two profiles. On "Profile A" they paste a new base URL and API key, then click "Profile B" in the list to check something, then click OK. `build_settings` → `_sync_editor_to_current_profile` writes the editor (which now holds B's values) into **B**, and A is saved with its old URL and old key. No warning, no visual cue at the moment of loss — the operator only finds out when the next AI run hits the stale endpoint. `_add_profile` has the same shape but happens to be safe because it syncs first.

- **Fix:** Track the row the editor currently represents and flush it before loading the new one. Keep an `self._editor_row` attribute set in `_load_profile_into_editor`, and in `_load_selected_profile_into_editor` sync `self._profiles[self._editor_row]` from the widgets (guarded by `self._loading_profile`) before calling `_load_profile_into_editor(self._profiles[row])`. `_sync_editor_to_current_profile` cannot be reused as-is because by the time `currentRowChanged` fires, `currentRow()` already points at the *new* row.

- **Resolution (2026-08-05):** Implemented with a stable
  `_editor_profile_id` rather than a row index, so list mutations cannot
  retarget pending edits. The outgoing editor owner is synchronized before
  switching, adding/removing profiles, Connect, Save/Apply/OK, and
  list/default-selector refreshes. Cancel retains its established behavior of
  discarding the dialog session by reloading persisted settings.

### [AI-2] Truncated responses (`finish_reason == "length"`) are silently repaired into a smaller valid payload — **Major, resolved 2026-08-03**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:517-539`, `:180-220`

- **What:** `_extract_message_content` reads `choices[0].message.content` and never looks at `choices[0].finish_reason`. `finish_reason` does not appear anywhere in `src/` (verified by grep).

```python
first_choice = choices[0]
if not isinstance(first_choice, dict):
    raise ValueError("AI provider response contains an invalid choice payload.")
message = first_choice.get("message", {})
```

  When the model hits `max_tokens`, `content` is a truncated JSON fragment. `_parse_json_content` fails, `_trim_json_like_payload` cuts back to the last `}`/`]` (still unbalanced), `_repair_json_like_content` does not add closing brackets, so the flow lands in the model-repair branch:

```python
except ValueError as parse_error:
    if not raw_content.strip() or not allow_model_json_repair:
        raise
    (
        parsed_payload,
        repair_body,
        repaired_content,
        repair_usage,
    ) = _repair_json_response_with_model(...)
```

  The repair model is told to "Return one valid JSON object only", so it closes the brackets and returns a well-formed object with the truncated tail dropped. `chat_json` then logs `parsed_status: "parsed_success_after_repair"` and returns it as a normal success.

- **Why it matters:** A chunking or speech-blocks request over a long chapter with `max_output_tokens` set too low returns, say, chunks 1–17 of 24. Nothing in the return value, the operation state, or the report distinguishes that from a model that genuinely produced 17 chunks — the tail of the chapter is silently missing from the persisted artifact. The condition is fully detectable: the provider said `finish_reason: "length"` in the same response.

- **Fix:** In `_extract_message_content` (or right after it in `chat_json`), read `first_choice.get("finish_reason")` and raise a `RuntimeError` naming truncation when it equals `"length"`, before the repair branch is entered. That surfaces it to the operator as a failed step instead of a silently short result.

- **Resolution:** Implemented in `llm_provider_service._extract_message_content`.
  The first choice now recognizes a normalized string token `length` and raises
  the fixed output-token-limit `RuntimeError` before content extraction. The
  regression suite covers malformed and syntactically valid JSON, exactly one
  provider request, transaction-log failure status, `stop`, an omitted finish
  reason, and the retained non-truncated model-repair path.

### [AI-3] A failed Connect erases the profile's persisted discovered-model list — **Minor, resolved 2026-08-05**

- **File:** `04_Software/AudioMancer/src/audiomancer/ui/pages/ai_settings_page.py:418-440`

- **What:** `apply_probe_result` overwrites `discovered_model_names` unconditionally, including on a failed probe where `discovered_models` is empty.

```python
model_options = [
    (str(model.get("id", "")), str(model.get("label", "")))
    for model in probe_result.get("discovered_models", [])
    if isinstance(model, dict) and str(model.get("id", "")).strip()
]
self._discovered_model_options[str(current_profile["id"])] = model_options
current_profile["discovered_model_names"] = [model_id for model_id, _label in model_options]
```

  Every failure path in `probe_profile` returns `discovered_models=[]`, so any transport hiccup clears the list.

- **Why it matters:** The persisted list exists specifically so the model selector still offers real model ids after a relaunch (see `test_model_selector_keeps_discovered_models_across_a_settings_round_trip`). One Connect attempt while LM Studio is restarting, followed by Save, throws that away and drops the selector back to the three hard-coded placeholder names the endpoint may not serve.

- **Fix:** Only replace `discovered_model_names` and `self._discovered_model_options[...]` when `probe_result.get("success")` is true (or when `model_options` is non-empty); leave the previous list untouched otherwise.

- **Resolution (2026-08-05):** Failed results now update only
  `discovery_succeeded` and `discovery_message`. The last successful model
  list/options and discovered model/context metadata remain intact, as do the
  typed model and configured context window. A successful empty discovery
  remains authoritative and may clear the prior discovered list.

### [AI-4] The probe never reports a context window, so the auto-fill branch and its override flag are dead code — **Minor, resolved 2026-08-05**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/ai_backend_service.py:150-156`; `ui/pages/ai_settings_page.py:442-445`, `:638-649`

- **What:** `probe_profile` hard-codes `discovered_context_window=None` on every one of its six returns, including the success path:

```python
return _build_probe_result(
    success=True,
    message=message,
    discovered_models=discovered_models,
    discovered_context_window=None,
    selected_model_valid=selected_model_valid,
)
```

  So the consumer branch can never run:

```python
if probe_result.get("discovered_context_window") is not None and not bool(
    current_profile.get("user_overrode_context_window", False)
):
    current_profile["context_window"] = int(probe_result["discovered_context_window"])
```

  `user_overrode_context_window` has no other reader, so `_on_context_window_edited` and the persisted flag are dead too.

- **Why it matters:** `AI_Runtime.md` §6 lists "optional context window" as part of the probe contract and the profile carries `discovered_context_window`, but a successful Connect never fills the context window — the operator must always set it by hand, and a wrong value silently mis-sizes every budget in `ai_budget_service`. The dead branch also reads as working code to the next maintainer.

- **Fix:** Either populate `discovered_context_window` in `_probe_openai_compatible_models` / `_probe_ollama_models` for the selected model (LM Studio's `/v1/models` and Ollama's `/api/show` both expose it), or delete the dead branch, the `discovered_context_window` field and the `user_overrode_context_window` flag so the UI stops advertising a behaviour it does not have.

- **Resolution (2026-08-05):** The probe contract now includes the discovered
  context and its exact owning model. Generic OpenAI-compatible discovery reads
  positive `context_length` with `max_context_length` fallback; LM Studio
  optionally augments the standard list with exact native model/instance
  metadata; and Ollama reads the selected model's `*.context_length` from
  `/api/show`. Invalid, boolean, non-positive, and implausibly large values are
  ignored. The UI auto-fills only a matching effective model and preserves a
  manual context override while refreshing informational discovery metadata.

### [AI-5] `content: null` becomes the literal string `"None"` — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:532-539`, `:185`

- **What:**

```python
content = message.get("content", "")
if isinstance(content, list):
    ...
return str(content)
```

  OpenAI-compatible providers send `"content": null` when a response is refused or when the payload carries only `refusal`/`reasoning_content`. `str(None)` yields `"None"`, so the caller's empty-response short-circuit never fires:

```python
if not raw_content.strip() or not allow_model_json_repair:
    raise
```

  `"None".strip()` is truthy, so the code sends a full repair round-trip with the body `MALFORMED_JSON_BEGIN\nNone\nMALFORMED_JSON_END`, and the eventual error message is `AI provider did not return JSON content.` rather than something that names the refusal.

- **Why it matters:** A wasted provider call (billed, and up to `request_timeout_seconds` of wall time) plus a misleading error on every refusal, and `message["refusal"]` — which contains the actual reason — is never shown to the operator.

- **Fix:** `content = message.get("content") or ""` and, when the result is empty, surface `message.get("refusal")` in the raised `ValueError`.

### [AI-6] Token usage is discarded whole when the provider omits any one usage field — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/token_usage_service.py:48-52`

- **What:**

```python
input_tokens = _optional_non_negative_int(raw_usage.get("prompt_tokens"))
output_tokens = _optional_non_negative_int(raw_usage.get("completion_tokens"))
total_tokens = _optional_non_negative_int(raw_usage.get("total_tokens"))
if None in {input_tokens, output_tokens, total_tokens}:
    return empty_token_usage()
```

  A provider or proxy that reports `prompt_tokens` and `completion_tokens` but omits `total_tokens` (common with OpenAI-compatible gateways) causes all three known counters to be thrown away and `usage_available` to be `False`. `_optional_non_negative_int` also rejects floats, so `"prompt_tokens": 1234.0` has the same effect.

- **Why it matters:** Every AI operation for that backend reports "token usage unavailable" (`ai_state_note_service` line 58) even though two of the three numbers were present. Once a single request in a multi-window run returns unavailable usage, `merge_token_usage` keeps the rest, so the totals are silently under-reported.

- **Fix:** Derive the missing `total_tokens` as `input + output` when both are present, and accept integral floats in `_optional_non_negative_int`.

### [AI-7] The `response_format` fallback is forgotten on the next retry attempt — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:150-179`

- **What:** `active_request_payload` is reset to the original payload at the top of every attempt:

```python
for attempt_index in range(1, attempts + 1):
    raw_content: str | None = None
    try:
        active_request_payload = request_payload
        try:
            raw_payload, raw_body = _request_chat_completion_with_cancellation(
                profile_payload,
                active_request_payload,
                ...
```

  If attempt 1 discovers the provider rejects `response_format`, retries without it, and that second call fails transiently (HTTP 429/5xx), attempt 2 starts again from `request_payload` — which still carries `response_format` — and re-earns the same 400 before falling back again. The same applies to the `max_completion_tokens` compatibility payload built inside `_request_chat_completion`: it is local to that call and never propagates back.

- **Why it matters:** Every retry against an incompatible provider costs an extra guaranteed-failing round trip, and with `retry_count_override=0` (the cleanup path) the discovery is thrown away entirely.

- **Fix:** Assign the fallback payload back to `request_payload` after a successful fallback (`request_payload = active_request_payload`) so later attempts start from the compatible shape.

### [AI-8] `probe_profile` does not catch read-phase transport errors despite documenting `@exception None` — **Minor, resolved 2026-08-05**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/ai_backend_service.py:113-145`, `:237-238`

- **What:** The probe catches `HTTPError`, `URLError`, `TimeoutError` and `ValueError`, but `urllib` only wraps failures that happen while opening the connection. Errors raised during the body read are not wrapped:

```python
with request.urlopen(http_request, timeout=timeout_seconds) as response:
    payload = json.loads(response.read().decode("utf-8"))
```

  `ConnectionResetError` or `http.client.IncompleteRead` from `response.read()` propagate straight out. The only caller is a Qt slot with no handler (`ai_settings_ui_controller.connect_ai_profile_from_dialog`, wired at `main_window.py:1124-1126`), and the app installs no `sys.excepthook`.

- **Why it matters:** Clicking Connect while the local backend is being restarted can take down the settings dialog (PySide6 does not swallow exceptions raised inside slots). The function's docstring promises it cannot raise, so no caller guards it.

- **Fix:** Widen the transport handler in `probe_profile` from `error.URLError` to `OSError` (which covers `URLError`, `TimeoutError` and `ConnectionResetError`) and add `http.client.HTTPException`.

- **Resolution (2026-08-05):** `probe_profile` retains its dedicated
  `HTTPError` status message and safely normalizes `TimeoutError`, `OSError`,
  `http.client.HTTPException` (including `IncompleteRead`), response decoding,
  and JSON parsing failures. Failure messages expose no API key,
  authorization header, or raw body, and the controller receives an ordinary
  failed payload rather than an exception escaping the Qt slot.

### [AI-9] Retries fire back-to-back with no delay — **Minor**

- **File:** `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:252-253`

- **What:** The retry loop has no sleep between attempts:

```python
if attempt_index >= attempts or not _is_retryable_error(error_object):
    break
```

  `_is_retryable_error` classifies HTTP 408/409/429 and 5xx as transient (via the `"Transient AI provider failure"` prefix), so all three attempts for a rate-limited request are consumed within a few hundred milliseconds.

- **Why it matters:** Against an online provider, a 429 that would clear in one second instead exhausts the retry budget instantly and fails the whole operation, and the burst makes the rate limit worse.

- **Fix:** Add a short bounded backoff before the next attempt (e.g. `time.sleep(min(4.0, 0.5 * 2 ** (attempt_index - 1)))`), interrupted by `cancel_requested` so cancellation stays responsive.

## Duplication

- `llm_provider_service._build_chat_endpoint` (`:380-407`) reimplements `url_service.join_endpoint_url`, which `ai_backend_service` already uses for the same base URLs. Besides the duplication, the two disagree: `join_endpoint_url` preserves the base URL's query/fragment via `parsed_url._replace(path=...)`, while `_build_chat_endpoint` drops them — `parse.urlunparse((parsed_url.scheme, parsed_url.netloc, full_path, "", "", ""))`. A base URL carrying a query string works for the model probe and silently loses it for the chat request.
- `token_usage_service.normalize_provider_usage` (`:38-58`) and `coerce_token_usage` (`:61-83`) are the same three-field extract → `None in {...}` guard → build-dict body with different source keys. One shared private helper taking the key triple would collapse them and keep the two paths from drifting.
- `ai_backend_service._probe_openai_compatible_models` (`:159-190`) and `_probe_ollama_models` (`:193-220`) are the same fetch → list-check → per-entry id extraction → descriptor append, differing only in the container key (`data` vs `models`) and the id field.
- **Resolved with AI-8:** the repeated `probe_profile` failure-result blocks
  are centralized in `_build_probe_failure`, which also keeps the expanded
  transport/decode failure behavior consistent.

## Verified-clean notes

- **API keys never reach any artifact.** The key is read into `headers["Authorization"]` in `_request_chat_completion` and in `_build_request_headers`, and is never part of `request_payload`, so the transaction log written to the project folder cannot contain it. `_redact_ai_log_value` recurses through dicts and lists, and `_is_sensitive_log_field` normalizes case and hyphens and also matches any `*_api_key` suffix, so a caller that passed a whole profile in `log_context` would still be redacted. The debug logger only prints the endpoint and timeout.
- **Prompt placeholders.** `render_prompt` uses `str.replace`, not `str.format`, so literal `{`/`}` in book text or in a template's JSON examples cannot blow up; the `\{([a-zA-Z_][a-zA-Z0-9_]*)\}` matcher correctly ignores `{"type": "object"}`-style braces. I enumerated the placeholders in all 17 files under `prompts/` and each is an identifier the strict missing/extra check will catch at render time, with a clear message.
- **Timeouts are set on both HTTP paths** (`urlopen(..., timeout=timeout_seconds)` in `_request_chat_completion` and in `_read_json`), and both use context managers.
- **`_build_max_completion_tokens_payload` recursion is bounded**: the retried payload has no `max_tokens`, so the guard `if compatibility_payload != request_payload` is false on a second pass and there is no third call.
- **Cancellation typing is right.** `OperationCancelledError` subclasses `RuntimeError`, not `ValueError`, so it cannot be swallowed by the JSON-repair `except ValueError` branch, and `chat_json` re-raises it ahead of the generic retry handler.
- **Budget comparison direction** in `context_budget_metadata` (`text_budget_tokens < min_text_budget` → raise) is correct, and `available_text_budget` lets the value go negative rather than clamping, so an over-committed profile is rejected instead of quietly running with a zero budget. `settings_service._validate_llm_profile` coerces `context_window`/`max_output_tokens`/`request_timeout_seconds` to positive ints, so the `int(...)` conversions in the budget service cannot see `None`.
- **`merge_token_usage`** correctly returns the available side when only one of the two payloads has usage (`_sum_usage_field` skips unavailable payloads and reports `None` only when neither contributed).
- **`_is_valid_json_escape_sequence`** bounds check for `\uXXXX` (`escape_index + 4 < len(content)`) is correct — it requires all four hex digits to exist.
- **`probe_profile` validates scheme and netloc** before issuing any request, so a typo'd base URL yields a message rather than a `ValueError: unknown url type`.
