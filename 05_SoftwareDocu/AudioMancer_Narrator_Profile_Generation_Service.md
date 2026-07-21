<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Narrator Profile Generation Service

## 1. Purpose

Generates editable narrator profile suggestions from project text through the
configured AI provider. It does not generate WAV files or select a profile.

## 2. Inputs And Analysis

The service prefers an approved translation matching the voice language and
otherwise uses canonical chunk text. It validates the configured profile,
prompt templates, requested count, context budget, language, preview bounds,
and explicit odd-count gender allocation before accepting generated profiles.

## 3. Durable Generation State

All durable state belongs to `narrator_voice.json`. A fresh attempt sets
`status = "running"`, resets token usage, records budget metadata and operator
instructions, and creates a compact `resume` checkpoint. After each complete
style window, usage and observations are atomically updated.

The resume fingerprint covers source selector/content, voice language, AI
profile/backend/model limits and temperature, budget, requested count, and the
instruction fingerprint. Gender allocation is persisted explicitly so an
odd-count retry does not rerandomize it.

Cancellation or failure retains the matching checkpoint and leaves profiles
unchanged. A matching retry skips completed windows and may open a new log. On
success, all validated profiles are appended, `status` becomes `completed`, and
`resume` becomes null in one atomic document write. Generated IDs remain only
in the in-memory result returned to the current UI call.

## 4. Diagnostics And Exclusions

Each invocation may create `log_ai_narrator_profiles_<timestamp>.log`. Log
paths, raw model responses, timestamps, reports, warnings, progress counters,
and generated-ID arrays are not persisted in the narrator document. There are
no report or state sidecars.

## 5. Workflow Integration

The Narrator Voice controller runs generation through the shared cancellable
operation runner. Generated profiles join the normal inventory but do not mark
narrator selection complete; the operator must inspect, sample, and explicitly
select a profile.

## 6. Validation

`test_narrator_profile_generation_service.py` verifies source choice,
allocation, prompt rules, token usage, cancellation/failure, matching resume,
final retry, compact observations, atomic success, and absence of sidecars.
`test_narrator_voice_single_document_contract.py` verifies the shared artifact
boundary.
