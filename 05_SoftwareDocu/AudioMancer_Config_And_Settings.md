<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Config And Settings

## 1. Purpose

Defines the current configuration constants and app-level settings scaffold used
by the initial `AudioMancer` application baseline.

## 2. Responsibilities

- define developer-owned application constants in `audiomancer.config`
- provide the initial persisted `settings.json` shape for later settings work
- preserve the earlier Audiomancer definitions in an adapted form for the new project

It now includes settings loading, validation, self-healing, and save behavior
through a dedicated settings service, but it still does not implement settings
UI editing.

## 3. Implementation Overview

The current baseline consists of:

- `src/audiomancer/config.py`
- `src/audiomancer/services/settings_service.py`
- `settings.json`
- focused contract and service tests for the configuration and settings scaffold

The configuration module currently centralizes:

- app identity and paths
- project artifact naming
- workflow and UI defaults
- AI/provider defaults
- export defaults
- logging defaults

Current logging defaults define:

- app log directory naming
- default log output mode
- default global log level
- per-component log-level overrides
- retention period for old run logs
- stable component identifiers for initial modules

The persisted settings scaffold is adapted from the earlier `DDP_Audiomancer`
application settings payload. It preserves the useful settings shape while
removing old project-path bindings and currently starts with no default LLM
profiles in the new repository.

## 4. Dependencies

- Internal dependencies:
  package-local `pathlib`-based path resolution and the app subtree layout
- External dependencies:
  none beyond the Python standard library

## 5. Inputs And Outputs

Inputs:

- source layout of the installed package
- current application subtree root
- adapted earlier Audiomancer settings payload

Outputs:

- constants consumed by future modules
- persisted default settings payload in `settings.json`
- validated in-memory settings payloads returned by the settings service

## 6. Data Contracts

Current stable contracts are:

- `audiomancer.config`
- `audiomancer.services.settings_service`
- `04_Software/AudioMancer/settings.json`

The settings scaffold currently includes fields for:

- language and recent projects
- default project and runtime-model paths
- provider profile placeholders
- LLM profile storage with no default selected profile-id fields
- AI cleanup and chunking profile defaults
- notification and UI text-scale preferences

## 7. Workflow Integration

This module will later provide defaults and file contracts for:

- settings loading and saving
- project workspace layout
- AI workflow defaults
- export configuration
- logging configuration

## 8. Usage

Example import:

```python
from audiomancer import config

app_name = config.APP_NAME
settings_path = config.APP_SETTINGS_PATH
```

Logging example:

```python
from audiomancer import config

default_level = config.DEFAULT_LOG_LEVEL
components = config.AVAILABLE_LOG_COMPONENTS
```

Settings service example:

```python
from audiomancer.services.settings_service import load_settings

settings_payload = load_settings()
```

## 9. Validation And Tests

Current automated checks:

- `tests/test_config_contract.py`
- `tests/test_settings_service.py`

Minimum validation after changes:

- `python -m py_compile` for changed files
- focused `pytest` run for the config contract test

## 10. Limitations And Future Work

- settings are still JSON-object based and not modeled with typed classes yet
- unknown extra settings keys are preserved but not explicitly validated
- provider and LLM profile settings will likely be normalized later into explicit models
