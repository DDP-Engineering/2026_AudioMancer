<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Changelog

## 0.9.0 - 2026-04-07

- added a complete deterministic Text Chunking workflow with dedicated runtime state, resumable progress, output artifacts, and one-chunk-per-paragraph processing
- added a dedicated Text Chunking UI controller plus main-window wiring for start, resume, rerun confirmation, downstream reset handling, and manifest synchronization
- upgraded the Text Chunking page to render cleaned-text preview, chunk list, selected chunk preview, localized notes, and deterministic action state
- added focused tests for deterministic chunking service behavior, chunking page behavior, chunking controller behavior, and main-window integration
- updated the chunking header layout so the `Deterministic Chunking` button appears before the AI-related controls
