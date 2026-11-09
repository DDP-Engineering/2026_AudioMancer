<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# Project profile

## Purpose and users

AudioMancer is a desktop audiobook-production application for operators working
with book text, AI-assisted text workflows, voice profiles and generated audio.

## Product responsibilities

Project Lifecycle publishes a new project with its selected book, keeps the book
fixed in Home, and saves language/narration options automatically with confirmed
resets of affected results. Mode changes preserve text, characters and narrator
data; language changes preserve source and text through Chunking.

Cleanup processes canonical text in an isolated pure package. Completed reruns
retain the published text and downstream work until recoverable replacement
succeeds; interrupted replacement AI work uses a separate pending checkpoint.

Chunking uses an isolated pure source-range core, cursor-based budget planning,
verified resumable prefixes and separate AI/persistence/edit adapters. Replacements
and selective manual edits publish recoverably; pending replacements retain the
previously published result and downstream work until success.

AI Translation binds approvals to current source chunks and uses one eligibility
rule across downstream text consumers. Review mutations, reset and finalization
stage the translation and workflow effects together.

Character Discovery consumes that same effective source, resumes overlapping
windows from the saved next start, and keeps operator evidence edits in the
character inventory.

AI Runtime owns provider profiles, backend probing, JSON-oriented LLM requests,
context budgeting and token-usage normalization. Workflow services own their
prompts, semantic response validation and project-local artifacts.

Narrator Voice keeps edits in a draft, publishes the WAV with its transcript,
and retains usable AI profile suggestions.

VoiceWeaver receives the Italian synthesis hint for Romanian voice design and
cloning. Project languages, speech text, and reference transcripts retain their
Romanian values.

## Supported operation

The LLM backend options are LM Studio, Ollama, OpenAI-compatible endpoints and
experimental ChatGPT subscription profiles. Subscription text/model capabilities
are verified separately from sign-in. Account-scoped model discovery supplies primary
text models and per-model reasoning choices, with cached fallback and explicit effort
persisted per subscription profile. Subscription model selection applies its reported
default context while allowing manual edits until a different model is selected.
The operator interface supports English and Romanian. Normal text fields and
previews share localized context menus and local Find navigation, including
dynamically created dialogs; edit commands follow the control's current state.

## Established constraints

The shared `chat_json()` facade returns parsed JSON plus normalized usage and
request metadata. Cleanup requires provider-enforced response schemas and
disables unconstrained fallback and model repair. API credentials currently
belong to API-key settings profiles. Subscription credentials belong to a
separate protected OS-user store or explicitly selected memory-only session;
project artifacts belong to workflow services.

## Implementation orientation

Source is under `05_Software/AudioMancer/src/audiomancer/`; tests are under
`05_Software/AudioMancer/tests/`. AI settings use a PySide6 page/controller;
provider operations live in service modules.

## Authoritative references

- `.agentic/PROJECT.md` and `01_Documentation/Code_Style.md`
- `.agentic/knowledge/AI_Runtime.md`
- `.agentic/knowledge/Platform_Settings_UI.md`
- `.agentic/knowledge/Operation_Orchestration.md`
- `05_Software/AudioMancer/src/audiomancer/config.py`
- `05_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/cleanup_ai_adjudication_service.py`
