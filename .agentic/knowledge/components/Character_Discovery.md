<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Character Discovery

## 1. Purpose

Derives a reviewable character inventory from the canonical project text so later voice and speech workflows have explicit character context.

## 2. Responsibilities

- Render discovery and synthesis prompts, budget source chunks, call the configured AI profile, merge candidates, and persist resumable discovery artifacts.
- Maintain operator-created or edited character records, evidence, demographic confidence, and character voice-definition prompts.
- Project persisted state into the Characters page and coordinate start, resume, cancellation, selection, edit, add, save, and delete actions.
- It does not select final narrator/character voices or generate speech/audio.

## 3. Implementation Overview

`character_discovery_service.py` loads compatible source chunks, builds bounded discovery windows, collects structured candidates, groups and synthesizes them, and writes profiles, report, checkpoint, and operation state. It preserves completed work on cancellation/failure and supports offline manual maintenance. `character_discovery_state_service.py` derives page-ready state and validates that an enabled AI profile is available before a run. The controller delegates long work through the shared operation runner; the page keeps review fields read-only until an operator deliberately enters edit/add mode.

## 4. Dependencies

- Internal: project/operation runtime artifacts, AI Runtime provider, budget and prompt-template services, canonical chunks or compatible translation artifacts, shared operation runner, and Qt page widgets.
- External: the selected AI provider is required only for discovery/synthesis or regeneration; persisted JSON project artifacts are used for recovery and review.

## 5. Inputs And Outputs

- Inputs: project root, canonical source chunks, selected enabled AI profile, optional operator rules, persisted checkpoint/state, and page edit/add/delete requests.
- Outputs: `characters_profile.json`, `characters_report.json`,
  `characters_state.json`, a per-run AI transaction log, character profiles
  with evidence and demographic confidence, page view state, and downstream
  invalidation when a saved character affects voice or speech work.

## 6. Data Contracts

- Character records retain stable identifiers, name validation, evidence, dialogue previews, demographic fields/confidence, and a compact voice-definition prompt.
- Discovery progress uses the shared operation-state envelope. Candidate payloads are normalized and trimmed to context-budget metadata before synthesis.
- Translation chunks are usable only when they are compatible with the selected target; otherwise source chunks remain authoritative.
- Malformed profile/report JSON is treated as absent with a logged warning for
  page recovery; the next successful atomic write replaces it. A generated
  preview must be grounded in that character's direct dialogue evidence before
  it can be retained for downstream voice work.

## 7. Workflow Integration

Character Discovery follows text chunking and is the review gate before Voice Profiles and Speech Blocks. Operators may resume a saved synthesis checkpoint, manually correct a record, or reset downstream work when a material character change invalidates it.

## 8. Usage

Open the Characters page after chunking, select an enabled character-discovery profile, optionally provide rules, and start or resume discovery. Review evidence and demographics, then use Edit or Add for intentional manual changes. Save before proceeding to voice-definition or speech-block work; cancel leaves resumable completed work intact.

## 9. Validation And Tests

Focused suite E-0013 passed 55 tests across discovery service, state service, page, and controller. It covers prompts, source selection, budgets, normalization/merge/synthesis, checkpoints, cancellation/failure recovery, manual mutation validation, profile state, and review UI flows. After changes, run all four mapped test modules with temporary/cache paths redirected outside `.agentic`. Manual review remains necessary for the truthfulness and completeness of AI-derived identities, evidence, and demographics.

## 10. Limitations And Future Work

Automated tests prove structural contracts and recovery behavior, not that a provider correctly identifies fictional characters or assigns accurate demographics. Candidate quality depends on the source, selected model, prompt response, and operator review; ambiguous entities, aliases, or weak dialogue evidence require human judgment before downstream voice or speech decisions.
