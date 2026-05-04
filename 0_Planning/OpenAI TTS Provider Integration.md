# OpenAI TTS Provider Integration

## Summary
Add OpenAI as a first-class paid online TTS provider beside the existing local VoiceWeaver runtime. The first implementation will support OpenAI for **Narator Voice** and **Character Voices** sample generation only; final **Audio Blocks** generation stays on the current VoiceWeaver clone-prompt flow so full-book voice consistency is not changed yet.

OpenAI behavior will follow the official Speech API docs: default model `gpt-4o-mini-tts`, endpoint `POST /v1/audio/speech`, Romanian text supported, built-in voices supported, and `instructions` used for tone/emotion/style control. Docs: [OpenAI Text to Speech](https://platform.openai.com/docs/guides/text-to-speech), [gpt-4o-mini-tts](https://platform.openai.com/docs/models/gpt-4o-mini-tts).

## Key Changes
- Add a TTS provider layer with provider kind values:
  - `voiceweaver`: existing local runtime, unchanged default for offline-first behavior.
  - `openai`: paid online provider using OpenAI-compatible `/v1` endpoint.
- Extend `TTS Settings`:
  - Provider selector: `VoiceWeaver Local` / `OpenAI Online`.
  - OpenAI fields: endpoint default `https://api.openai.com/v1`, API key, model selector, default voice selector.
  - Model defaults: `gpt-4o-mini-tts`, with legacy options `tts-1` and `tts-1-hd`.
  - Built-in voice list: `alloy`, `ash`, `ballad`, `coral`, `echo`, `fable`, `nova`, `onyx`, `sage`, `shimmer`, `verse`, `marin`, `cedar`; default `marin`.
  - `Test Connection` validates endpoint/key/model through OpenAI metadata endpoints without generating audio.
- Persist new settings fields:
  - `tts_provider_kind`
  - `openai_tts_base_url`
  - `openai_tts_api_key`
  - `openai_tts_model`
  - `openai_tts_default_voice`
  - `openai_tts_probe_succeeded`
  - `openai_tts_probe_message`
- Add per-profile/per-target OpenAI voice selection:
  - Narrator profiles and character targets store resolved `tts_provider_kind`, `openai_model`, `openai_voice`, and generated sample metadata.
  - Existing narrator/character prompt text is sent as OpenAI `instructions`.
  - Existing preview text is sent as OpenAI `input`.
  - Output format is `wav` so current playback and sample storage remain compatible.
- Add mandatory paid-use warnings:
  - Persistent paid-provider notice in TTS Settings when OpenAI is selected.
  - Confirmation before every OpenAI narrator or character sample generation.
  - Confirmation text must clearly say the operation calls an online paid OpenAI TTS service and may incur API charges.
  - Add EN and RO translations for all new labels, dialogs, warnings, statuses, and progress text.

## Implementation Notes
- Use Python standard-library HTTP helpers, matching the current VoiceWeaver service style; do not add the `openai` SDK dependency for this pass.
- Add a new OpenAI TTS runtime service that returns the same normalized shape expected by the narrator and character controllers: success/failure probe payloads and generated WAV bytes.
- Route narrator and character sample generation through the selected provider:
  - VoiceWeaver path keeps the current Qwen capability checks and model loading.
  - OpenAI path skips VoiceWeaver model loading and directly stores returned WAV bytes with OpenAI metadata.
- Keep Audio Blocks generation on VoiceWeaver for now. If OpenAI-created samples are selected, Audio Blocks can still use those WAV samples as reference input to the existing VoiceWeaver clone-prompt flow.
- Update `README.MD` and `05_SoftwareDocu/AudioMancer_TTS_Settings_And_VoiceWeaver_Runtime.md` to document the provider split, paid OpenAI behavior, and first-pass scope.

## Test Plan
- Add focused tests for OpenAI settings validation/defaults and self-healing.
- Add TTS Settings page tests for provider switching, OpenAI field visibility, model/voice defaults, and paid warning text.
- Add OpenAI runtime service tests for:
  - endpoint normalization
  - auth failure handling
  - model probe success/failure
  - speech payload shape: `model`, `voice`, `input`, `instructions`, `response_format="wav"`
  - returned WAV bytes propagation
- Add narrator and character controller tests proving:
  - OpenAI generation requires paid-use confirmation
  - cancelled confirmation makes no API call
  - generated OpenAI sample metadata is persisted
  - VoiceWeaver path still works unchanged
- Run required validation for changed Python files:
  - `uv run python -m py_compile <changed_file.py>`
  - `uv run ruff check <changed_python_files> --fix`
  - `uv run ruff format <changed_python_files>`
  - targeted `uv run pytest` for settings, TTS page, OpenAI runtime, narrator controller, and character voices controller.

## Assumptions
- First pass supports OpenAI built-in preset voices, not OpenAI custom voice creation.
- OpenAI model and voice lists are static curated defaults, with connection testing validating the selected model when possible.
- API keys remain stored in `settings.json`, consistent with the current application settings pattern.
- Final Audio Blocks OpenAI generation is intentionally deferred to a later plan because preset OpenAI voices do not guarantee the same voice identity as generated narrator/character samples.
