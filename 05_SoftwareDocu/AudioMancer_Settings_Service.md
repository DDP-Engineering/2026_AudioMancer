<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Settings Service

## 1. Purpose

Provides the shared `settings.json` lifecycle for the `AudioMancer`
application.

It gives the app one place to build default settings, load persisted settings,
validate and self-heal payloads, and save normalized settings back to disk.

## 2. Responsibilities

- build the default app settings payload
- load `settings.json` from the application root
- create `settings.json` automatically when it is missing
- validate persisted and in-memory settings payloads
- replace missing or invalid values with defaults
- save validated settings back to disk
- keep unknown extra keys unless they do not create a concrete validation risk

It does not own the settings UI, typed settings models, or provider discovery.

## 3. Implementation Overview

The component is implemented in:

- `src/audiomancer/services/settings_service.py`

Main public functions:

- `build_default_settings()`
- `validate_settings(settings_payload)`
- `load_settings()`
- `save_settings(settings_payload)`
- `ensure_settings_file()`

High-level flow:

1. `audiomancer.app.main()` initializes logging.
2. Startup calls `load_settings()` before Qt UI creation.
3. If `settings.json` is missing, the service writes a default file and returns
   that payload.
4. If `settings.json` exists, the service loads JSON, validates the payload,
   and replaces missing or invalid values with defaults.
5. If validation changes the payload, the service writes the healed settings
   back to disk.
6. Other modules may call `save_settings()` to persist updated settings.

Validation currently covers:

- primitive fields such as language and booleans
- path-like string fields
- HTTP and HTTPS URL validation for LLM profile `base_url` values and the
  VoiceWeaver `tts_runtime_base_url`
- list fields such as recent projects and provider/profile lists
- nested `llm_profiles` entries for required keys and supported backend values
  when profiles exist
- UI theme settings: selected `ui_theme_id`, normalized custom `ui_themes`
  with separate UI-control and text-window font payloads, and removal of the
  deprecated top-level `ui_text_scale` field
- UI scroll settings: `ui_scroll_steps_per_wheel_notch`, validated as an
  integer from `1` to `5` and repaired to the default `1` when missing or
  invalid
- Scene Ambience settings: placement policy, soft maximum sequence duration,
  maximum blocks per sequence, guidance scale, inference-step count, and
  optional seed; placement `none` disables Speech Blocks ambience generation

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`, `audiomancer.app`, and
  `audiomancer.services.logging_service`
- External dependencies:
  Python standard library only: `json`, `copy`, `pathlib`, and `typing`

## 5. Inputs And Outputs

Inputs:

- `config.APP_SETTINGS_PATH`
- developer-owned defaults from `audiomancer.config`
- the current persisted `settings.json` payload
- in-memory settings payloads passed to `validate_settings()` or
  `save_settings()`

Outputs:

- validated settings payloads returned as plain Python dicts
- a created or updated `settings.json` file in the app root
- settings lifecycle log messages through the `"settings"` component logger

## 6. Data Contracts

Stable persisted file contract:

- file path: `APP_SETTINGS_PATH`
- format: JSON object
- encoding: UTF-8

Stable public API contract:

- `build_default_settings() -> dict[str, Any]`
- `validate_settings(settings_payload: dict[str, Any]) -> dict[str, Any]`
- `load_settings() -> dict[str, Any]`
- `save_settings(settings_payload: dict[str, Any]) -> None`
- `ensure_settings_file() -> dict[str, Any]`

Current deterministic behavior:

- missing file creates a default `settings.json`
- invalid supported enum-like values fall back to defaults
- `llm_profiles` is empty by default
- no default selected LLM profile id fields are persisted in the settings
  contract
- unknown extra keys are preserved, except deprecated keys with an explicit
  migration path such as `ui_text_scale`
- invalid non-empty AI or TTS runtime base URLs heal back to their defaults
  instead of remaining in one broken-but-persisted state
- invalid scroll-step values outside `1..5`, or non-integer values, heal back
  to the configured default
- invalid Scene Ambience placement, duration/count, guidance, step, or seed
  values heal back to their configured defaults
- normalized payloads are written back when healing is required

## 7. Workflow Integration

This component sits early in the application startup flow.

Upstream:

- `audiomancer.app.main()`

Downstream:

- future settings UI and persistence workflows
- future modules that need validated settings for runtime decisions

Current in-repo usage:

- startup ensures settings are present and valid before the main window is
  created

## 8. Usage

Startup usage:

```python
from audiomancer.services.settings_service import load_settings

settings_payload = load_settings()
```

Save usage:

```python
from audiomancer.services.settings_service import save_settings

save_settings(updated_settings_payload)
```

## 9. Validation And Tests

Documentation audit status:

- reviewed against the current implementation on 2026-06-08

Automated tests:

- `tests/test_settings_service.py`
- `tests/test_config_contract.py`
- `tests/test_app_entrypoint.py`

Covered behaviors:

- default settings generation
- automatic file creation when missing
- persisted settings self-healing
- preservation of unknown extra keys
- validated save behavior
- startup integration
- scroll-step defaulting and validation

Minimum validation after a change:

- `python -m py_compile` for changed Python files
- focused `pytest` run for settings service, Settings page, config contract,
  bootstrap, and scroll-service tests

## 10. Limitations And Future Work

- the first version is dict-based and does not use typed settings models
- some default values still reflect the current committed scaffold rather than a
  fully normalized config-only source
- `online_provider_profiles` is preserved as a raw list and not yet validated
  deeply
- selected LLM profile id fields are intentionally absent from the current
  settings contract

## Documentation Review Notes

Reviewed for the AI chunking context mode feature. The settings contract includes `default_ai_chunking_context_mode`. The settings service validates that value against the configured Balanced, Wide scene context, and Maximum context options, repairs missing or invalid values to Balanced, and preserves current behavior for older settings payloads. Validation should include settings-service and AI Settings tests when AI defaults change.
