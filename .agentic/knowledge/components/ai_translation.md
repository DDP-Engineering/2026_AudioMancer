<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AI Translation Component Knowledge

## 1. Purpose

AI Translation consumes canonical Text Chunking output and uses an explicitly
selected OpenAI-compatible provider to translate each chunk into the
project-locked target language. Generated text remains review-gated before
translated-language downstream workflows may consume it.

## 2. Responsibilities

- Own translation prompt construction, context budgeting, oversized-chunk
  segmentation, provider JSON handling, token accounting, chunk-level resume,
  atomic translation persistence, and operator edit, approval, retranslation,
  and reset behavior.
- Own the translated-text readiness boundary used by narrator, voice, Speech
  Blocks, export, and project-stage consumers.
- Do not own source import, cleanup, canonical chunk construction, AI profile
  editing, target-language selection, or downstream character/audio output.

## 3. Current Implementation Overview

`ai_translation_service.py` persists per-chunk output plus separate report and
operation-state JSON files. `ai_translation_state_service.py` projects these
artifacts into page state. `ai_translation_ui_controller.py` owns threaded UI
orchestration and manifest synchronization, while `ai_translation_page.py`
owns selection, direct text editing, approval actions, and progress display.

Requests are sequential by canonical chunk order. Oversized chunks are split
deterministically by paragraph, sentence, then words. The durable checkpoint is
the completed chunk: partial translated segments are not persisted.

## 4. Dependencies

Internal dependencies include canonical chunk loading, AI budgeting, prompt
templates, provider JSON transport, token usage, atomic persistence, operation
runtime reset helpers, project manifest services, logging, UI state, and
downstream translated-text consumers. The external dependency is an
operator-configured OpenAI-compatible endpoint.

## 5. Inputs And Outputs

Inputs are `chunks_text.json`, locked `project.json.target_language`, the
currently selected enabled AI profile, translation prompt templates, and
optional operator rules. Current outputs are `translated_text.json`,
`translation_report.json`, `translation_state.json`, an AI transaction log,
and a compact translation summary in `project.json`.

## 6. Data Contracts

Relevant durable requirements are `REQ-FUNC-004`, `REQ-FUNC-005`,
`REQ-NFR-016`, `REQ-UX-002`, `REQ-UX-003`, and `REQ-FUNC-049`.

Current translated-chunk records duplicate canonical sequence and source text,
persist the profile identifier and per-chunk status, and keep review approval.
The report persists counts and review stage; the operation state persists
technical status, progress, log metadata, token usage, budget metadata,
operator rules, and resume metadata. Fully approved translated text is the
downstream consumption gate.

## 7. Workflow Integration

Text Chunking supplies canonical input. The controller starts provider work on
the shared threaded operation runner and keeps incomplete translation at
`translation_ready`. Full approval advances to `character_discovery_ready`.
Translation reset and approval loss retain the existing broad downstream reset
policy while preserving the configured narrator exceptions.

## 8. Validation And Tests

Focused coverage includes `test_ai_translation_service.py`,
`test_ai_translation_state_service.py`,
`test_ai_translation_ui_controller.py`, `test_ai_translation_page.py`, and
`test_atomic_io_contracts.py`. Direct consumers are covered by project export,
narrator definition/generation, Speech Blocks, and translated-language state
tests.

## 9. Risks And Boundaries

Translation is paid, resumable provider work and translated text can affect all
later audiobook stages. Persistence replacement is intentionally incompatible
with existing translation artifacts and therefore must fail safely rather than
reinterpret legacy data. Human approval remains the quality control; the
service validates response shape and non-empty text, not semantic quality.

