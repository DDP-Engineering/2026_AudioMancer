<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AudioMancer Draft Component Map

Run: `adoption-2026-07-18T145821Z-782116f8`

Map date: 2026-07-18

## Draft Status

The component manifest now contains 13 domain-oriented components. Every
component is intentionally marked `discovered`, below the configured
`baseline-usable` threshold. No component bundle is defined or approved.

Discovered ownership evidence is DDP Engineering / Eng. Dan Dumitru Pasare.
Human confirmation is still required for component-level ownership.

## Components

| Component | Criticality | Primary responsibility | Status |
| --- | --- | --- | --- |
| `app-shell` | high | Bootstrap, main window, navigation, and shared Qt composition | discovered |
| `platform-settings-ui` | high | Configuration, settings, logging, theme, and shared UI state | discovered |
| `project-lifecycle` | high | Project manifests, import, persistence, snapshots, exports, and Home flow | discovered |
| `operation-orchestration` | high | Threaded operations, cancellation, progress, and workflow impact | discovered |
| `ai-runtime` | high | AI profiles, provider calls, budgets, token usage, and prompt loading | discovered |
| `text-cleanup` | high | Extraction, deterministic/AI cleanup, metadata, state, and UI | discovered |
| `text-chunking` | high | Deterministic/AI chunking, descriptors, state, and UI | discovered |
| `ai-translation` | medium | Translation service, state, prompts, and UI | discovered |
| `character-discovery` | medium | Character evidence extraction/synthesis, state, prompts, and UI | discovered |
| `voice-profiles` | high | Narrator profiles, character voice assignments, samples, and UI | discovered |
| `speech-blocks` | high | Speech/ambience generation, normalization, state, prompts, and UI | discovered |
| `tts-audio-blocks` | high | VoiceWeaver/TTS runtime, WAV block generation, state, playback, and UI | discovered |
| `audio-assembly` | high | WAV validation, mixing, splitting, output state, playback, and UI | discovered |

The exact primary paths and representative tests are the source of truth in
`.agentic/components.toml`.

## Validation

- The manifest parses successfully through `adoption component-status`.
- `adoption baseline` reports all 13 components as `discovered`.
- An independent path-match audit inspected 209 application modules/assets,
  tests, prompts, and selected package metadata files. All 209 match exactly
  one component; there are no overlaps or unmapped inventory files.
- `adoption scope-check` on one representative source path per component
  resolved all 13 paths to the intended component and reported the expected
  `COMPONENT-BASELINE-MISSING` result.
- Bundles remain empty because no bundle has human approval.

## Coverage Configuration Repair

`.agentic/workflow.toml` now limits `coverable_roots` to
`04_Software/AudioMancer/src/audiomancer`. This removes the project-local
`.venv` and the test suite from source requirement coverage.

The coverage audit now reports 88 missing application source mappings, reduced
from the discovery count of 2,388. These 88 findings are real adoption work:
each source module needs a linked durable requirement or an explicit approved
legacy waiver before the repository-wide coverage audit can pass.

## Approval Questions

1. Approve the 13 component boundaries and discovered statuses as the initial
   component map?
2. Confirm DDP Engineering / Eng. Dan Dumitru Pasare as the component owner,
   or provide different ownership labels?
3. Select one component for the first `component-adoption` slice.

Recommended first slice: `project-lifecycle`. It owns project manifests and
atomic persistence used by every downstream workflow, already has focused
tests and detailed legacy documentation, and provides a strong foundation for
later domain adoption. If a smaller workflow-proving slice is preferred,
`ai-translation` is the narrowest self-contained alternative.

