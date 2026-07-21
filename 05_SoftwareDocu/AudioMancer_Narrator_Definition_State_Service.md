<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Narrator Definition State Service

## 1. Purpose

Builds the presentation state for the project-local `Narator Voice` page
without owning persistence.

## 2. State Sources

The service initializes a missing `narrator_voice.json` through
`narrator_definition_service`, then derives profile rows, inspected and selected
profiles, selected language, sample availability, and runtime capabilities.
There are no profile, selection, or selected-sample sidecars.

## 3. Readiness

Profile sample readiness requires inline sample metadata and the matching
canonical `audio_narator_<profile_id>.wav`. Selection alone may be valid before
a sample exists. Runtime generation readiness is derived from discovered Qwen
Voice Designer capabilities and current settings.

## 4. Workflow Integration

The state service supplies read-only page payloads and notes. Mutations remain
in `narrator_definition_service`; controller actions continue to update compact
manifest narrator name, language, stage, and operation summary fields.

## 5. Validation

Use `test_narrator_definition_state_service.py` together with narrator service
and UI/controller tests. Contract failures from a malformed current narrator
document are operator-visible and are not converted into empty state.
