<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Senior Code Review Report

Date: `2026-04-22`

Reviewed scope:

- `04_Software/AudioMancer/src/audiomancer/`
- focused validation with `uv run pytest -q`

## Executive Summary

The codebase has a solid automated-test baseline and the main workflow layering
is understandable, but several central helpers are creating cross-cutting risk.

Most important findings:

1. AI request retries currently treat permanent provider failures as transient.
2. The translation workflow is marked as ready before the approval contract is complete.
3. AI transaction logging and read-path helpers both introduce avoidable filesystem behavior that will scale badly in long jobs.
4. There is already meaningful duplicate logic across cleanup pipelines and VoiceWeaver UI controllers.

I did not find strong evidence of large unreachable production code blocks.
The clearest dead or redundant code candidate is a zero-value wrapper in the
operation-path helper layer.

## Findings

### 1. High - Permanent AI provider failures are retried as if they were transient

Files:

- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:178`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:286`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:287`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:633`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:647`

Why this is a problem:

- `_request_chat_completion()` raises `"AI provider request failed with HTTP ..."` for non-transient HTTP failures such as `400`, `401`, `403`, and `404`.
- `_is_retryable_error()` classifies any error containing `"request failed"` as retryable.
- That means invalid credentials, malformed payloads, or wrong endpoints get retried for the full retry budget instead of failing fast.

Impact:

- unnecessary repeated remote calls
- longer operator wait time for obviously permanent failures
- extra rate-limit pressure
- duplicate noise in AI transaction logs

Recommendation:

- classify retryability from structured error categories or explicit HTTP status ranges
- remove the generic `"request failed"` substring rule

### 2. High - Translation is marked as workflow-ready before approval is complete

Files:

- `04_Software/AudioMancer/src/audiomancer/ui/controllers/ai_translation_ui_controller.py:358`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py:714`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py:720`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py:722`
- `04_Software/AudioMancer/src/audiomancer/services/character_voices_state_service.py:450`

Why this is a problem:

- `_sync_manifest_after_translation()` unconditionally sets `current_stage` to `translation_ready`.
- The translation report itself distinguishes `translated_chunk_count` from `approved_chunk_count`.
- Downstream translated-language availability in `character_voices_state_service` requires `approved_chunk_count == total_chunk_count`.

Impact:

- the project manifest can advertise a more advanced workflow stage than the translated data actually satisfies
- Home-page progress and downstream workflow semantics are inconsistent
- repair and reset behavior become harder to reason about because "translation ready" does not mean one stable thing

Recommendation:

- either derive manifest stage from approval completion
- or introduce a separate stage for "translated but not fully approved"

### 3. Medium - AI transaction logging rewrites the full log file on every entry

Files:

- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:651`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:669`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:671`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:672`

Why this is a problem:

- `_append_ai_log()` reads the entire existing log into memory, concatenates one new line, then rewrites the whole file.
- This happens per request and per response, inside workflows that iterate over many chunks or segments.

Impact:

- O(n^2) write behavior as the log grows
- avoidable UI slowdown on long AI runs
- larger corruption window if the process is interrupted during rewrite

Recommendation:

- switch to append-mode file writes
- keep one JSON-lines format, but write one line at a time atomically

### 4. Medium - Read helpers mutate project folders and can hide missing-directory corruption

Files:

- `04_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py:119`
- `04_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py:140`
- `04_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py:156`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py:81`
- `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py:123`
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:85`
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:102`
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:139`

Why this is a problem:

- `build_operation_output_path()` creates the operation folder as a side effect.
- multiple `load_*` functions call that helper before checking whether the file exists.
- the alias `build_operation_artifact_path()` adds no behavior and hides the same side effect behind a second name.

Impact:

- read-only state inspection mutates the project on disk
- a missing step folder can be silently recreated before higher-level repair logic sees the corruption
- path semantics are harder to trust because "load" operations are not actually read-only

Recommendation:

- split "ensure directory exists" helpers from pure path-resolution helpers
- remove or consolidate the zero-value `build_operation_artifact_path()` wrapper

### 5. Medium - Duplicate logic is already spread across parallel workflow implementations

Files:

- `04_Software/AudioMancer/src/audiomancer/services/ai_cleanup_service.py:570`
- `04_Software/AudioMancer/src/audiomancer/services/ai_cleanup_service.py:980`
- `04_Software/AudioMancer/src/audiomancer/services/ai_cleanup_service.py:999`
- `04_Software/AudioMancer/src/audiomancer/services/ai_cleanup_service.py:1017`
- `04_Software/AudioMancer/src/audiomancer/services/deterministic_cleanup_service.py:637`
- `04_Software/AudioMancer/src/audiomancer/services/deterministic_cleanup_service.py:656`
- `04_Software/AudioMancer/src/audiomancer/services/deterministic_cleanup_service.py:674`
- `04_Software/AudioMancer/src/audiomancer/services/deterministic_cleanup_service.py:734`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py:573`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py:597`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py:615`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/character_voices_ui_controller.py:632`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py:632`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py:656`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py:674`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/narator_voice_ui_controller.py:691`

Why this is a problem:

- cleanup heuristics such as chapter counting, chapter-label detection, language detection, and dialogue formatting exist twice
- VoiceWeaver runtime cache persistence and active-model handling also exist twice in near-identical controller helpers

Impact:

- bug fixes require multi-file manual synchronization
- behavior drift becomes likely over time
- the duplicated code is already large enough that drift will be hard to spot in review

Recommendation:

- extract shared cleanup-analysis helpers into one internal module
- extract shared VoiceWeaver runtime-cache helpers into one controller/service utility layer

### 6. Low - Endpoint normalization is too permissive and under-validated

Files:

- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:296`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:309`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py:311`
- `04_Software/AudioMancer/src/audiomancer/services/ai_backend_service.py:41`
- `04_Software/AudioMancer/src/audiomancer/services/ai_backend_service.py:56`
- `04_Software/AudioMancer/src/audiomancer/services/voiceweaver_runtime_service.py:56`
- `04_Software/AudioMancer/src/audiomancer/services/settings_service.py:171`
- `04_Software/AudioMancer/src/audiomancer/services/settings_service.py:465`

Why this is a problem:

- provider and runtime URLs are mostly normalized by string concatenation
- settings validation checks type, but not URL shape
- a user-entered full endpoint URL, a missing scheme, or an already suffixed path can be transformed into a malformed request target

Likely corner cases:

- base URL pasted as a full `/v1/chat/completions` endpoint
- host entered without `http://` or `https://`
- runtime base URL already containing an API suffix

Impact:

- hard-to-diagnose connection failures
- error handling will report transport failure, but the real problem is bad normalization

Recommendation:

- validate URLs at settings-save time
- normalize against one explicit allowed contract per backend kind

### 7. Low - Validation is currently failing because the version contract is split between runtime code and stale tests

Files:

- `04_Software/AudioMancer/pyproject.toml:7`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py:181`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py:196`
- `04_Software/AudioMancer/tests/test_main_window_lifecycle.py:156`
- `04_Software/AudioMancer/tests/test_main_window_lifecycle.py:190`

Why this matters:

- runtime code resolves the About-dialog version from `pyproject.toml`
- the tests still hardcode `0.17.2`
- current project metadata is `0.18.0`

Impact:

- the full test suite is not green even though the runtime version lookup is internally consistent
- release validation signal is weaker than it should be

Recommendation:

- derive the expected version from the same source in tests
- or centralize the version string behind one importable constant

## Dead Code / Redundant Code Notes

- No high-confidence unreachable production code blocks were identified in this pass.
- The clearest redundant abstraction is `build_operation_artifact_path()` in
  `operation_runtime_service.py:140-156`; it is a pure alias for
  `build_operation_output_path()` and currently adds no contract value.

## Validation Notes

Command executed:

```powershell
uv run pytest -q
```

Result:

- `260` tests passed
- `2` tests failed
- failing tests:
  - `tests/test_main_window_lifecycle.py::test_about_dialog_includes_license_text`
  - `tests/test_main_window_lifecycle.py::test_about_dialog_loads_translated_license_text_for_romanian`

Failure cause:

- both failures are caused by stale hardcoded version expectations (`0.17.2`)
  while the current package version is `0.18.0`

## Recommended Next Actions

1. Fix retry classification in `llm_provider_service.py` first.
2. Align translation stage semantics with approval semantics.
3. Replace rewrite-based AI log appends with true append-mode writes.
4. Separate pure path resolution from directory-creation helpers.
5. Consolidate the duplicated cleanup and VoiceWeaver helper code.

