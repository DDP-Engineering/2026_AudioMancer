<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Narrator Profile Generation Service

## 1. Purpose

Implements the text-only AI narrator-profile suggestion workflow used by the
`Narator Voice` page. The component analyzes the current book text with a
selected AI profile, generates editable narrator voice-designer prompts and
short preview sentences, appends them to the project profile catalog, and
records a report/state sidecar.

The service does not generate WAV files, does not update `narator.wav`, and
does not select a narrator profile.

## 2. Responsibilities

- resolve the best available book text for narrator-style analysis
- window the resolved text with the shared AI context-budget service
- run compact style-observation calls followed by one profile-generation call
- append optional operator-supplied narrator-profile rules to the style-analysis
  and profile-generation prompts
- resume compatible unfinished runs from persisted style observations and
  cumulative token usage
- persist `cancelled` or `failed` terminal operation states with the resumable
  checkpoint when an interrupted run does not complete
- validate profile count, gender allocation, names, prompt text, preview text,
  and preview character limits before persistence
- append generated profiles to `audio_profiles.json` only after full
  validation succeeds
- persist `narator_profile_generation_report.json` and
  `narator_profile_generation_state.json`
- preserve AI transaction logs and resumable checkpoint details outside the
  compact profile records
- preserve existing manual and generated profiles
- propagate cancellation before any profile append

It does not:

- own the AI profile catalog in `settings.json`
- own the narrator sample-generation workflow
- mutate `narator.json`, `narator.wav`, or downstream narrator selection state
- approve or select one generated profile automatically

## 3. Implementation Overview

Main implementation:

- `04_Software/AudioMancer/src/audiomancer/services/narrator_profile_generation_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py`
  via `append_ai_generated_profiles(...)`
- prompt templates in `04_Software/AudioMancer/prompts/`:
  `narrator_profile_style_system.txt`,
  `narrator_profile_style_window_user.txt`,
  `narrator_profile_generation_user.txt`
- `01_Documentation/qwen_tts_voice_designer_guide.txt` is reflected in the
  generation prompt through prompt-length, structure, acoustic/emotional
  layering, stability, and anti-exaggeration guidance.

Public entrypoints:

- `generate_narrator_profiles(...)`
- `load_operation_state(...)`
- `load_generation_report(...)`

Processing flow:

1. Validate the selected enabled AI profile has an id, model name, and base URL.
2. Validate the three narrator-profile prompt templates exist.
3. Resolve source text using the selected voice language.
4. Build source windows from the selected profile context window, output-token
   limit, prompt budget, and safety margins.
5. Restore compatible checkpointed style observations from
   `narator_profile_generation_state.json` when the source fingerprint,
   selected AI profile, requested count, gender allocation, model settings, and
   context budget still match, including the saved operator prompt-rule
   fingerprint.
6. Ask the AI for compact observations for each remaining source window,
   including any operator-supplied profile rules.
7. Deterministically merge repeated style terms into a compact frequency
   summary, then ask the AI for strict JSON narrator profiles using the
   requested count, deterministic gender allocation, and any operator-supplied
   profile rules.
8. Validate the full response before writing any profile data; invalid final
   responses persist a `failed` state while keeping completed style
   observations available for resume.
9. Append generated profiles and persist report/state with cumulative token
   usage and source fingerprint metadata.

## 4. Dependencies

Internal dependencies:

- `config.py` for artifact names, count limits, and AI budget constants
- `ai_budget_service.py` for token estimates and context-window budgeting
- `ai_translation_service.py` for approved translation artifacts
- `deterministic_chunking_service.py` for canonical chunks
- `cleanup_metadata_service.py` for cleaned paragraph metadata and clean-text
  fallback records
- `llm_provider_service.py` for JSON AI calls
- `narrator_definition_service.py` for profile append and language
  normalization
- `prompt_template_service.py` for prompt loading/rendering
- `token_usage_service.py` for cumulative token usage
- `operation_runtime_service.py` for progress, cancellation, state payloads,
  and root-level operation paths

External dependencies:

- the selected OpenAI-compatible or local AI backend configured in AI Settings
- no VoiceWeaver dependency for this workflow

## 5. Inputs And Outputs

Inputs:

- active project root
- active project manifest
- selected AI profile payload
- requested profile count, `1..20`
- selected voice language code
- TTS preview character limit
- optional operator-supplied narrator-profile rules entered before a fresh AI
  generation run
- optional progress and cancellation callbacks

Source text selection order:

1. Approved `translated_text.json` when `translation_report.json.target_language`
   matches the selected voice language and every translated chunk is approved.
2. Canonical `chunks_text.json`.
3. `clean_text_metadata.json` paragraphs.
4. `clean_text.txt` split into fallback paragraph records.

Outputs:

- appended entries in `audio_profiles.json`
- `narator_profile_generation_report.json`
- `narator_profile_generation_state.json`
- one AI transaction log named with the `narrator_profiles` operation token

No audio artifact is created.

## 6. Data Contracts

Generated profile fields appended to `audio_profiles.json`:

- `profile_id = "ai_narrator_<uuid>"`
- `display_name`
- `language`
- `prompt_text`
- `preview_text`
- `sample = null`

Generated profile entries intentionally do not duplicate `profile_origin`,
`profile_kind`, `provider_family`, `editable`, `speaker_id`,
`source_model_id`, `sample_audio_path`, `sample_metadata`, or
`generation_metadata`. The profiles remain editable through the Narator Voice
workflow, while run provenance lives in the report/state sidecars and AI logs.

Generated `prompt_text` guidance follows the Qwen3-TTS Voice Designer guide:

- one English paragraph, recommended `80..220` words and preferably
  `120..180`
- age/gender, vocal timbre, speaking rhythm, emotional profile, articulation,
  delivery style, personality cues, and audiobook context
- acoustic and emotional descriptors instead of visual/lore-heavy description
- stable, human, grounded, restrained, cinematic audiobook delivery
- no contradictory descriptors, excessive plot summary, meme language,
  cartoon exaggeration, or celebrity/real-person imitation

Generated `preview_text` must be long enough to produce a useful Qwen TTS
reference sample:

- at least the configured minimum preview duration, currently `6.0` seconds
- estimated with `DEFAULT_TTS_WORDS_PER_AUDIO_SECOND`, currently `2.5`
- effectively at least `15` spoken words with the current defaults
- targeted at `15..24` spoken words, with a bounded implementation tolerance
  up to `30` estimated words so near-valid model output is not rejected solely
  for a small overage
- still a single-line original sentence and still capped by the TTS preview
  character limit

Duplicate generated display names are rejected within one AI response. Duplicate
names against existing project profiles are preserved with a suffix such as
` (2)` during append.

Report/state metadata includes:

- `ai_profile_id`
- `model_settings`
- `source`
- `source_unit_count`
- `input_fingerprint`
- `requested_count`
- `gender_allocation`
- `generated_profile_ids`
- `style_summary`
- `budget_metadata`
- `token_usage`
- `additional_profile_instructions`
- `additional_profile_instructions_fingerprint`

Running, cancelled, and failed-state `resume_checkpoint` includes:

- `input_fingerprint`
- `profile_id`
- `source`
- `requested_count`
- `gender_allocation`
- `completed_window_count`
- `total_window_count`
- compact `style_observations`
- `run_token`
- AI transaction `log_relative_path`
- `budget_metadata`
- `model_settings`
- `additional_profile_instructions_fingerprint`

Generated narrator profile reports and operation state do not persist operation
audit timestamps or generic path arrays. Resume uses the checkpoint,
fingerprints, prompt-rule fingerprints, token usage, and explicit AI log path.

The final profile-synthesis request does not inject every raw style observation
from large books. It sends a deterministic `style_summary` that counts repeated
normalized terms per style field, preserves the top recurring terms, and keeps
the raw per-window observations only in the resume checkpoint and AI log.
When operator-supplied profile rules are entered, the service appends them to
both the style-window and final profile-generation prompts unless a prompt
template provides an explicit `{additional_profile_instructions}` placeholder.

Gender allocation:

- even counts split evenly between male and female profiles
- odd counts split evenly and assign the extra profile randomly to male or
  female; the selected extra gender is written in `gender_allocation`

Successful runs write `status = "completed"` and clear the resume checkpoint.
Cancelled or failed runs keep the checkpoint and write `status = "cancelled"`
or `status = "failed"`, so a compatible retry can continue from the next
unfinished style window or replay only the final synthesis request.

## 7. Workflow Integration

The `Narator Voice` page exposes an AI profile selector and
`Generate Narator Profiles` button. The controller asks for confirmation,
requests the count, offers an optional word-wrapped prompt box for extra
profile rules, starts the shared threaded operation runner, and refreshes the
page after success, failure, or cancellation.

If a previous narrator profile generation run was interrupted, pressing
`Generate Narator Profiles` with the same compatible settings resumes from the
next unfinished style-analysis window with the original saved operator rules.
If all style windows were already checkpointed and only the final
profile-generation request failed or was cancelled, the service reuses the
saved observations and retries only the final request with the same saved rules.

The workflow can run before narrator selection and does not mark the
`narrator_definition` manifest operation complete. A generated profile becomes
part of the normal narrator workflow only after the operator inspects it,
generates an audio sample if desired, and explicitly selects it.

## 8. Usage

Representative service call:

```python
report = narrator_profile_generation_service.generate_narrator_profiles(
    project_root,
    manifest,
    ai_profile_payload,
    profile_count=6,
    voice_language="en",
    preview_text_character_limit=512,
    additional_profile_instructions="Favor intimate literary narration over trailer-style intensity.",
)
```

UI path:

- open a project with cleaned, chunked, or approved translated text
- open `Narator Voice`
- choose one enabled AI profile
- press `Generate Narator Profiles`
- confirm token/cost warning
- choose a profile count
- optionally add extra profile-generation rules, or leave the text box empty
- after interruption, press `Generate Narator Profiles` again with the same
  count/profile/source to continue from the saved checkpoint and saved rules
- review the appended editable profiles

## 9. Validation And Tests

Focused automated coverage:

- `04_Software/AudioMancer/tests/test_narrator_profile_generation_service.py`
- Narator Voice controller coverage in
  `04_Software/AudioMancer/tests/test_narator_voice_ui_controller.py`
- Narator Voice page coverage in
  `04_Software/AudioMancer/tests/test_narator_voice_page.py`
- AI Settings/default-profile coverage in
  `04_Software/AudioMancer/tests/test_ai_settings_page.py`
  and `04_Software/AudioMancer/tests/test_settings_service.py`

Documentation audit status:

- compact generated-profile metadata contract reviewed on 2026-05-18
- failed and cancelled terminal checkpoint behavior reviewed on 2026-06-11
- narrator preview-text bounded tolerance reviewed on 2026-07-03

Minimum validation after changes:

- `uv run python -m py_compile` for changed Python files
- `uv run ruff check <changed_python_files> --fix`
- `uv run ruff format <changed_python_files>`
- focused pytest runs for narrator generation, Narator Voice UI/controller, AI
  settings, and settings service

## 10. Limitations And Future Work

- The service trusts the selected AI backend's language ability; it validates
  shape and length but does not perform full linguistic verification of preview
  text.
- The style-analysis pass stores compact observations only; it does not persist
  source excerpts.
- Resume is compatible only while the source fingerprint, selected AI profile,
  requested count, gender allocation, context budget, and model settings match
  the checkpoint.
- Repeated runs append new suggestions and do not deduplicate against prior
  generated profile semantics beyond display-name suffixing.
