<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer TTS Budget Service

## 1. Purpose

Provides shared conservative TTS text-budget estimates before runtime audio
generation. The current caller is Speech Blocks generation in `same_narrator`
mode, where the AI prompt needs practical segment-size guidance and
deterministic validation needs a budget warning threshold.

## 2. Responsibilities

- resolve a model token budget from cached VoiceWeaver discovered-model payloads
- prefer `default_model_parameters.max_new_tokens`
- fall back to generation-parameter range defaults when available
- fall back to conservative config defaults when no runtime budget is cached
- convert model token budget into estimated audio seconds and safe word count
- provide deterministic spoken-word estimates for validation

It does not contact VoiceWeaver, load models, or enforce the final runtime
generation limit. Audio Blocks still enforces the real model limit when audio is
generated.

## 3. Implementation Overview

The component is implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/tts_budget_service.py`

Public entrypoints:

- `resolve_cached_tts_budget(discovered_models)`
- `estimated_safe_word_count(budget_payload)`
- `estimated_word_count(text)`

High-level flow:

1. Speech Blocks passes cached `tts_runtime_discovered_models` from settings.
2. The service scans model metadata for a positive `max_new_tokens` value.
3. The service returns a normalized budget payload containing the model token
   budget, derived audio-second estimates, safety factor, safe word count, and
   budget source.
4. Speech Blocks injects the budget into narrator-only prompts and flags model
   output that exceeds the safe word count.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`
- External dependencies:
  none beyond the Python standard runtime

## 5. Inputs And Outputs

Inputs:

- cached VoiceWeaver discovered-model payload list from `settings.json`
- fallback constants from `src/audiomancer/config.py`

Outputs:

- normalized budget payload dictionaries
- estimated safe word counts
- estimated word counts for generated block text

## 6. Data Contracts

Budget payload fields:

- `model_token_budget`
- `model_audio_seconds_budget`
- `split_audio_seconds_budget`
- `safe_word_count`
- `approx_audio_seconds_per_token`
- `split_safety_factor`
- `model_budget_source`

Current fallback constants:

- `DEFAULT_TTS_NARRATOR_ONLY_TOKEN_BUDGET`
- `DEFAULT_TTS_APPROX_AUDIO_SECONDS_PER_TOKEN`
- `DEFAULT_TTS_SPLIT_SAFETY_FACTOR`
- `DEFAULT_TTS_WORDS_PER_AUDIO_SECOND`

## 7. Workflow Integration

Upstream:

- TTS Settings stores the cached discovered-model list in `settings.json`.

Downstream:

- Speech Blocks narrator-only prompting uses the budget payload for prompt
  instructions.
- Speech Blocks normalization adds `tts_budget_exceeded` when narrator-only
  output is longer than the safe estimate.
- Audio Blocks remains the final guard for actual runtime model limits.

## 8. Usage

Representative service call:

```python
budget = tts_budget_service.resolve_cached_tts_budget(settings_payload.get("tts_runtime_discovered_models"))
safe_words = tts_budget_service.estimated_safe_word_count(budget)
```

## 9. Validation And Tests

Focused coverage is included through:

- `04_Software/AudioMancer/tests/test_speech_blocks_service.py`

Minimum validation after changes:

```powershell
uv run python -m py_compile src/audiomancer/services/tts_budget_service.py
uv run pytest tests/test_speech_blocks_service.py
```

## 10. Limitations And Future Work

- The budget is an estimate for prompt guidance and early review warnings.
- Runtime generation can still split over-budget text as a final guard.
