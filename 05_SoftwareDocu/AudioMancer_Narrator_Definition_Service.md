<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Narrator Definition Service

## 1. Purpose

Owns the strict project-local Narrator Voice document, narrator profiles,
explicit selection, and canonical per-profile sample WAV files.

## 2. Persistence Contract

`narrator_voice.json` is the only Narrator Voice metadata authority. Its exact
root fields are `status`, `token_usage`, `budget_metadata`,
`additional_profile_instructions`, `selected_profile_id`, `profiles`, and
`resume`. The loader initializes only a missing document. A malformed current
document raises `NarratorVoiceDocumentContractError` and remains untouched.

Each profile stores exactly its immutable ID, display name, language, prompt,
preview text, and optional compact sample metadata. Audio is never represented
by a persisted path. Its location is derived as
`audio_narator_<normalized_profile_id>.wav`.

The service does not read, migrate, repair, rename, or delete data from removed
Narrator Voice contracts. Those files are outside the current contract.

## 3. Selection And Samples

Selecting a profile updates only `selected_profile_id`. Selected language and
sample metadata are derived from the selected profile. No selected WAV or JSON
copy is created. `selected_narrator_sample_path()` returns the selected
profile-owned path and `load_selected_narrator_sample_metadata()` returns the
inline sample view.

Generated samples use `source_kind = "voice_designer"`; imported samples use
`source_kind = "imported"`, a null model ID, and the source file name. JSON and
WAV mutations use atomic persistence. Renaming a profile never changes its WAV
path because the profile ID is immutable.

## 4. Public API

- `load_narrator_voice_document`, `write_narrator_voice_document`, and
  `ensure_narrator_voice_document`
- profile load/create/edit/delete and language-update helpers
- sample store/import/delete and runtime-readiness helpers
- `select_narrator_profile`, `load_selected_profile_state`,
  `selected_narrator_sample_path`, and
  `load_selected_narrator_sample_metadata`

## 5. Workflow Integration

The Narrator Voice UI keeps its existing profile and sample workflow while the
service projects compact narrator name/language/operation summaries into
`project.json`. Character Voices and Audio Blocks resolve the selected profile
and canonical WAV at read time.

Reset ownership belongs to the operation runtime: narrator reset removes the
current document, all `audio_narator_*.wav` files, and actual
`log_ai_narrator_profiles_*.log` files. Preservation of `narrator_definition`
keeps those current artifacts.

## 6. Validation

Focused coverage is in `test_narrator_definition_service.py`,
`test_narrator_voice_single_document_contract.py`,
`test_narrator_definition_state_service.py`, and the narrator UI/controller
tests. Manual audition remains required because automated tests cannot judge
voice quality or suitability.

The strict profile validator preserves the existing UI behavior that allows a
new custom profile to begin with an empty prompt string; generated profiles and
sample operations continue to apply their existing prompt/preview rules.
