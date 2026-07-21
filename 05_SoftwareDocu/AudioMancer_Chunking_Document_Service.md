<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Chunking Document Service

## 1. Purpose

Provides the sole authoritative persistence boundary for Text Chunking through
one strict root-object `chunks_text.json` document.

## 2. Responsibilities

- validate the exact document and chunk field sets
- atomically write the complete document
- load defensive document and chunk copies
- reject malformed, legacy, or extended payloads with Reset Chunking guidance
- derive transient report and operation-state projections
- calculate the cleaned-text source fingerprint and chapter count

## 3. Implementation Overview

`chunking_document_service.py` resolves the root-level document path, parses and
validates JSON, and delegates atomic replacement to `persistence_service`.
Deterministic generation, AI generation, manual mutation, lifecycle validation,
exports, and downstream readers share this boundary.

## 4. Dependencies

The service depends on `audiomancer.config`, Python JSON/hash/path utilities,
and the shared atomic JSON writer. It does not call AI providers or own UI state.

## 5. Inputs And Outputs

Input is an active project root plus either canonical cleaned text or a candidate
document. Output is `chunks_text.json` or an in-memory defensive projection.
AI transaction logs are separate resettable artifacts and their paths are not
stored in the document.

## 6. Data Contracts

The exact root fields are lifecycle status, mode, manual-adjustment flag, source
fingerprint, semantic strategy, additional instructions, cumulative token use,
warnings, next paragraph, fallback count, and chunks. Each chunk contains only
its stable ID, sequence, text, cleanup boundary confidence, page-break join flag,
and cleanup warning flags.

Progress totals, AI profile/model/request settings, budget metadata, history,
derived counts, generic metadata, and log paths are runtime-only. Legacy arrays
and obsolete report/state sidecars are never loaded or migrated.

## 7. Workflow Integration

Text Cleanup supplies the fingerprinted source. Text Chunking writers commit
only complete units or AI windows. Translation, Character Discovery, narrator
generation, Speech Blocks, Audio Blocks readiness, Project Lifecycle, and
exports consume the shared chunk reader.

## 8. Usage

Use `load_chunking_document`, `write_chunking_document`, or `load_chunks`.
Callers must not parse `chunks_text.json` independently. An incompatible value
must be recovered by the operator through Reset Chunking.

## 9. Validation And Tests

`test_chunking_single_document_contract.py` verifies exact schemas, lifecycle,
resume, manual mutation, sidecar rejection, UI projection, and downstream
routing. Focused deterministic, AI, lifecycle, and export suites cover existing
integration behavior.

## 10. Limitations And Future Work

The persistence format intentionally has no compatibility dispatcher or schema
migration layer. Adding fields requires a new approved contract change.
