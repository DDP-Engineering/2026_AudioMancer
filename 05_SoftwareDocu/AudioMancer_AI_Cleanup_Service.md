<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer AI Cleanup Service

## 1. Purpose

Provides the AI-assisted cleanup slice for `AudioMancer`.

It gives the `Text Cleanup` page one second cleanup mode that consumes the
canonical extracted text, calls one configured AI provider through the profile
selected in `AI Settings`, writes the cleaned result back into the shared
root-level cleanup artifact set, and keeps one resumable checkpoint plus one
per-run AI transaction log.

## 2. Responsibilities

- populate the `Text Cleanup` AI profile selector from enabled AI settings
- start AI-assisted cleanup from the selected profile
- confirm that AI cleanup can take longer before the run starts
- confirm destructive reruns when cleanup is already completed
- resume interrupted AI cleanup with the currently selected model settings,
  without the destructive rerun confirmation
- load prompts from the application-root `prompts/` folder
- call OpenAI-compatible `/v1/chat/completions` endpoints with the configured
  model, timeout, temperature, and max-token settings, while retrying with
  `max_completion_tokens` when one remote API explicitly rejects `max_tokens`
- keep cancel requests responsive while one provider call is still waiting for
  the model response
- retry transient provider failures conservatively
- normalize model JSON output before parsing and attempt one conservative
  malformed-JSON repair pass when the assistant content is not valid JSON
- persist `clean_text.txt`, `cleanup_report.json`, and `cleanup_state.json`
- append project-local AI transaction records to
  `log_ai_cleanup_<timestamp>.log`
- allow the operator to manually edit and save the shared cleaned-text output
  from the `Text Cleanup` page after AI cleanup completes
- provide right-click `Find` search in both extracted-text and cleaned-text
  preview windows

It does not own AI profile editing, model discovery, text extraction,
chunking, translation, or character discovery.

## 3. Implementation Overview

The component is implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/ai_cleanup_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/prompt_template_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/text_cleanup_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/text_cleanup_page.py`
- `04_Software/AudioMancer/prompts/text_cleanup_system.txt`
- `04_Software/AudioMancer/prompts/text_cleanup_user.txt`

Main public entrypoints:

- `text_cleanup_ui_controller.handle_ai_cleanup_requested(window, profile_id)`
- `ai_cleanup_service.clean_text(project_root, manifest, ai_profile_payload, ...)`
- `llm_provider_service.chat_json(profile_payload, system_prompt, user_prompt, ...)`
- `prompt_template_service.load_prompt(...)`
- `prompt_template_service.render_prompt(...)`

High-level flow:

1. `TextCleanupPage` emits `ai_clean_requested(profile_id)`.
2. `text_cleanup_ui_controller` validates the active project, extracted-text
   prerequisite, and currently selected AI profile.
3. The controller shows the AI-length warning popup and, when needed, the
   destructive cleanup-rerun confirmation.
4. The shared modal progress dialog starts through the existing blocking
   operation flow.
5. `ai_cleanup_service` loads prompt files, splits extracted text into
   paragraph-like units, windows them to fit the selected profile budget,
   computes source-language and dominant-script hints, adds previous and next
   unit context for each classified unit, and resumes from stored unit
   classifications when the extracted-text fingerprint still matches.
6. `llm_provider_service` sends one chat-completion request per window,
   retries one compatibility-adjusted request when a provider rejects
   `max_tokens`, attempts one follow-up JSON-repair request when the returned
   assistant content is malformed, appends request or response or failure
   records to the operation-local AI log, and keeps polling for cancellation
   while the provider request runs in a small helper thread.
7. The AI cleanup service accepts the current artifact/action/confidence
   schema and legacy `label` output, preserves `keep` decisions and
   low-confidence removals conservatively, removes only high-confidence or
   medium-confidence removable artifacts, rebuilds the cleaned text, writes
   the shared cleanup artifacts, and stores `mode="ai_assisted"` in the cleanup
   operation state.
8. On success, the shell advances the workflow stage to `text_chunking_ready`.
9. Manual edits to the cleaned text save back to `clean_text.txt` and reset
   downstream workflow state from chunking onward while preserving the
   extracted-text preview scroll position.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`, `audiomancer.services.settings_service`,
  `audiomancer.services.operation_runtime_service`,
  `audiomancer.services.project_workspace_service`,
  `audiomancer.services.ui_state_service`,
  `audiomancer.ui.controllers.misc_ui_controller`
- External dependencies:
  Python standard library for JSON, hashing, regex, datetimes, filesystem
  access, and `urllib`; `langdetect`; `PySide6`

## 5. Inputs And Outputs

Inputs:

- active project root folder
- current `project.json` manifest with `source_document` and
  `extracted_text_relative_path`
- selected enabled AI profile from `settings.json`
- prompt files in `04_Software/AudioMancer/prompts/`
- optional progress callback and cancellation callback

Outputs:

- `clean_text.txt`
- `cleanup_report.json`
- `cleanup_state.json`
- `log_ai_cleanup_<timestamp>.log`
- updated `project.json` cleanup operation entry with `mode="ai_assisted"`
- updated `project.json` stage `text_chunking_ready` after successful cleanup
- updated `project.json` stage `text_cleanup_ready` after a manual
  cleaned-text edit

## 6. Data Contracts

Current prompt contract:

- `text_cleanup_system.txt` owns the allowed cleanup artifact types, actions,
  confidence values, and required JSON response shape
- `text_cleanup_user.txt` must expose the `{units_block}` placeholder and may
  also use `{source_language_hint}`, `{dominant_script_hint}`, and
  `{unit_count}`
- each current-schema result item contains `unit_id`, `artifact_type`,
  `action`, `confidence`, and a short `reason`
- legacy result items containing only `unit_id` and `label` remain accepted for
  compatibility with older prompts and tests
- ambiguous units should use `artifact_type="unknown"` and `action="keep"` so
  the cleaned text preserves content unless removal is high-confidence

Current AI cleanup report fields extend the shared cleanup report with:

- `cleanup_mode`
- `ai_profile_id`
- `model_settings`
- `model_settings_history`
- `ai_log_relative_path`

Current AI cleanup operation-state invariants:

- the operation kind remains `cleanup`; AI cleanup does not create a separate
  workflow folder
- `mode` is `ai_assisted`
- `resume_checkpoint` stores `completed_window_count`,
  `total_window_count`, `input_fingerprint`, concrete `model_settings`, and
  accumulated unit classifications
- resume identity is based on the extracted-text fingerprint and stored unit
  classifications, not the earlier profile id; if the operator selects another
  enabled model/profile before resuming, the remaining units use that selected
  model's name, temperature, context window, and output-token budget
- `metadata.ai_log_relative_path` points to the per-run AI transaction log

Current AI transaction log behavior:

- one `.log` file is created per AI cleanup run
- each line is one JSON object with timestamped request, response, or failure
  metadata
- parse-failure and repair records now retain the raw assistant message
  content to support postmortem diagnosis of malformed JSON outputs

## 7. Workflow Integration

Upstream:

- `AI Settings` provides the enabled profile list and
  `default_ai_cleanup_profile_id`
- `text_extraction_service.extract_text(...)` provides the canonical extracted
  text input

Downstream:

- the shared cleanup preview and notes on the `Text Cleanup` page
- chunking consumes the same `clean_text.txt`
- confirmed AI cleanup reruns reset chunking, translation, and
  character-discovery data
- manual cleaned-text edits reset chunking and all later workflow artifacts

## 8. Usage

Operator flow:

- configure and save at least one enabled AI profile in `AI Settings`
- open `Text Cleanup`
- select the desired AI profile
- press `AI-Assisted Cleanup`
- confirm the AI-length warning
- use `Edit` and `Save` under the cleaned text preview for manual corrections
- right-click either text preview and choose `Find` to search within that
  preview
- confirm the destructive rerun warning when cleanup was already completed

Service call pattern:

```python
from audiomancer.services import ai_cleanup_service

report_payload = ai_cleanup_service.clean_text(
    project_root,
    manifest,
    ai_profile_payload,
)
```

## 9. Validation And Tests

Automated tests:

- `04_Software/AudioMancer/tests/test_ai_cleanup_service.py`
- `04_Software/AudioMancer/tests/test_llm_provider_service.py`
- `04_Software/AudioMancer/tests/test_prompt_template_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_page.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_state_service.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_ui_controller.py`

Minimum validation after a change:

- `uv run python -m py_compile <changed_file.py>`
- focused `uv run pytest` for AI cleanup service, provider service, prompt
  service, cleanup page, and cleanup controller tests

## 10. Limitations And Future Work

- the provider flow currently assumes an OpenAI-compatible
  `/v1/chat/completions` interface for requests, even though it now tolerates
  providers that require `max_completion_tokens` instead of `max_tokens`
- AI cleanup runs through the shared threaded modal-operation runner; provider
  requests still complete sequentially within the worker and honor cancellation
  only at cooperative checkpoints
- transaction logs are newline-delimited JSON records inside a `.log` file, not
  a richer indexed audit store
- canceling during an in-flight provider call is cooperative; the shell stops
  waiting immediately, but the abandoned background HTTP call may still finish
  on its own shortly after
- malformed JSON repair still depends on best-effort normalization and one
  follow-up repair prompt; it is not yet equivalent to strict schema-enforced
  structured output
- AI cleanup currently classifies paragraph-like units only; it does not yet
  reuse deterministic page-aware heuristics during the AI phase
