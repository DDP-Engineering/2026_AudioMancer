<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# Character Discovery

## 1. Purpose

Character Discovery derives a reviewable inventory of speaking characters from
the effective project text. Voice Profiles and Speech Blocks consume that
inventory through the stable profile projection.

## 2. Responsibilities

- Resolve original versus fully approved translated text.
- Discover candidates in bounded chunk windows and synthesize one character per
  AI request.
- Persist operation status, resume progress, token usage, characters, and
  manual edits in one authoritative document.
- Maintain evidence, demographic confidence, voice prompts, and provenance.
- Invalidate its own and downstream output when the effective source changes.
- It does not select voices or generate speech/audio.

## 3. Implementation Overview

`04_Software/AudioMancer/src/audiomancer/services/character_discovery_service.py`
owns source resolution, strict persistence, discovery, synthesis, resume, and
manual CRUD. `load_character_document()` validates the authoritative document;
`load_character_profiles()` exposes the flat projection expected by existing
consumers.

`character_discovery_state_service.py` derives Characters-page state.
`characters_ui_controller.py` coordinates start, resume, cancellation, reset,
and manual maintenance.

Manual validation and candidate grouping share one Unicode-aware identity key.
The key uses NFKD decomposition, case folding, and Unicode alphanumeric
characters, discarding combining marks and punctuation. It compares accented
Latin spelling variants without transliterating other scripts; canonical names
and aliases retain their original display spelling in `characters.json`.

Discovery checkpoints after every successful window. Synthesis remains
sequential: each candidate is compacted to the current profile budget and sent
in one AI request, then the resulting character and next index are committed
atomically.

Resume keeps four concepts separate. The root character array is the current
durable inventory, checkpoint candidates are discovery output, the completed
candidate prefix identifies prior synthesis results still present by stable
AI-character ID, and `next_candidate_index` is the only synthesis cursor.
Manual records and root ordering never advance that cursor. Discovery writes
preserve current nested records directly, so operator additions and edits
survive later checkpoints without normalization, while a deleted completed AI
record is not reconstructed from stale checkpoint data.

## 4. Dependencies

- Internal: strict Chunking and AI Translation documents, project manifest,
  prompt templates, AI provider, budget/token-usage helpers, atomic JSON
  persistence, operation reset helpers, and the Qt Characters page.
- External: the currently selected AI provider is required only for discovery
  and synthesis.

## 5. Inputs And Outputs

- Inputs: canonical chunks, optional fully approved translations, the current
  enabled AI profile, optional operator instructions, and manual CRUD requests.
- Output: `characters.json` in the project artifact root.
- Diagnostics: per-run `log_ai_character_discovery_*.log` files are separate and
  are not referenced by the authoritative document.
- Side effects: the manifest character-discovery entry is refreshed as a
  reconstructible cache; source changes reset dependent runtime artifacts while
  preserving Narrator Definition.

## 6. Data Contracts

The root of `characters.json` contains exactly:

```text
status, source, instructions, token_usage, character_profile_id_last_used,
checkpoint, failure, characters
```

`source` contains exactly `kind`, `language`, and `fingerprint`. `kind` is
`translated` only when every canonical chunk has a non-empty approved
translation; otherwise it is `original`. The fingerprint covers source kind,
language, and ordered chunk ID, sequence index, and selected text.

`character_profile_id_last_used` is the stable ID selected for the most recent
start or resume invocation. It is a selection preference, not attribution for
every accumulated candidate, and never contains credentials or copied provider
configuration.

`checkpoint` is null or one of:

- discovery: `phase`, `completed_window_count`, `planned_window_count`,
  `next_chunk_index`, `candidates`
- synthesis: `phase`, `completed_window_count`, `planned_window_count`,
  `next_candidate_index`, `candidates`

Discovery progress is completed/planned windows; neither value is derived from
the source-chunk cursor. Synthesis checkpoints retain a completed/planned
window baseline with all discovery windows complete, then add candidate work to
the combined progress model. For synthesis checkpoints, candidates before
`next_candidate_index` are complete and are never resubmitted; candidates at or
after it remain pending. Inventory count and order are presentation state, not
progress state.

Characters contain exactly `character_id`, `canonical_name`, `aliases`,
`traits`, `voice`, `discovery_confidence`, `provenance`, and `evidence`.
`provenance` separates `origin` (`ai` or `manual`) from `edited`.

The file is absent before the first run. Persisted statuses are `running`,
`cancelled`, `failed`, and `completed`. Invalid JSON, arrays, extra root fields,
or incompatible nested records are rejected by the strict document reader. The
new root and checkpoint fields are a hard break: documents missing them are
invalid and use the established Reset-only recovery rather than silent repair.
Characters-page state catches only that expected document error and remains
read-only: it preserves valid chunk evidence, disables Start and all manual
mutations, and leaves Reset available to remove the invalid artifact through
the established reset policy. Completed page summaries state only the persisted
speaking-character count; they do not invent an analyzed-window count.

## 7. Workflow Integration

Character Discovery follows Chunking and optional Translation. Translation
approval/edit/reset actions recalculate the effective source and invalidate
Character Discovery only when kind or fingerprint changes. Character Voices,
Speech Blocks, export, manifest summaries, and UI previews consume the new
document or its profile projection. When the strict reader rejects an invalid
Character Discovery document, export readiness treats the Characters artifact
as unavailable so project open can reach the existing Reset-only recovery
state; it does not repair or expose the invalid inventory.

## 8. Usage

Call `start_or_continue_discovery()` with the project root, manifest, and
current profile. A resumable run retains its saved instructions but always uses
the current profile configuration and records that stable ID as last used.
Characters-page refresh preserves an enabled live selection; without one it
prefers an enabled persisted ID, then the configured Character Discovery
default, then the first enabled profile. Call `reset_character_discovery()` to delete
the document and dependent artifacts. Manual add/edit/delete functions update
the same document atomically. Manual and operator-edited records in a compatible
cancelled or failed document remain authoritative when the run resumes;
force-rerun and incompatible-source paths retain their established fresh-run
behavior.

## 9. Validation And Tests

Primary coverage is in:

- `04_Software/AudioMancer/tests/test_character_discovery_service.py`
- `04_Software/AudioMancer/tests/test_character_discovery_state_service.py`
- `04_Software/AudioMancer/tests/test_characters_ui_controller.py`
- translation, runtime, export, and text-state consumer tests

The service regressions cover discovery and synthesis cancellation/resume,
provider failure, manual inventory in varied ordering, edited and deleted AI
profiles, cursor-based provider-call counts, source mismatch, force rerun,
explicit reset, token usage, instructions, and atomic document writes.

Unicode regressions cover manual add/edit and canonical/alias duplicates across
Cyrillic, Greek, CJK, Japanese, Korean, Hebrew, and Arabic names; composed and
accent-folded equivalents; distinct base spellings; empty keys; grouping order;
and one synthesis request for repeated mentions across discovery windows.

Recovery regressions prove malformed, invalid-root, and invalid-nested
documents remain strict direct-read errors while the Characters page and
MainWindow refresh render an English or Romanian Reset-only state. Completed
summary regressions prove token usage, warnings, rerun notice, and localization
format placeholders remain intact without a fabricated window count. Resume
regressions use real variable-sized window plans, including a source cursor near
chunk 40, and prove checkpoint, callback, manifest, and page progress never
exchange chunks, windows, or candidates as one unit.

Minimum validation includes focused pytest runs, Python compilation, and Ruff.

## 10. Limitations And Future Work

Character quality still depends on source clarity, provider behavior, and human
review. Synthesis deliberately uses one AI call per character; adaptive batch
synthesis is not implemented.

## Files

From the adopted component map:

- `04_Software/AudioMancer/prompts/character_discovery_*.txt`
- `04_Software/AudioMancer/prompts/character_profile_synthesis_user.txt`
- `04_Software/AudioMancer/src/audiomancer/services/character_discovery_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/character_discovery_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/characters_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/characters_page.py`
- `04_Software/AudioMancer/tests/test_character_discovery_service.py`
- `04_Software/AudioMancer/tests/test_character_discovery_state_service.py`
- `04_Software/AudioMancer/tests/test_characters_page.py`
- `04_Software/AudioMancer/tests/test_characters_ui_controller.py`
- `.agentic/requirements/functional/REQ-FUNC-57acf8bd.toml`
- `.agentic/requirements/functional/REQ-FUNC-df901739.toml`
- `.agentic/requirements/functional/REQ-FUNC-e3015445.toml`
- `.agentic/requirements/functional/REQ-FUNC-e3feefa9.toml`
- `.agentic/requirements/functional/REQ-FUNC-f5fc5dd8.toml`
- `.agentic/requirements/functional/REQ-FUNC-f878c579.toml`
- `.agentic/requirements/functional/REQ-FUNC-5cd8727a.toml`
- `.agentic/specs/REQ-FUNC-df901739.md`
- `.agentic/specs/REQ-FUNC-f5fc5dd8.md`
- `.agentic/specs/REQ-FUNC-f878c579.md`
