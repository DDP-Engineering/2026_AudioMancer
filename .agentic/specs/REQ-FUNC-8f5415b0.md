# REQ-FUNC-8f5415b0 - Warn for unsupported Cleanup source languages

## Behavior

At deterministic Cleanup analysis, the detected `document_profile.language` is
compared with `config.CLEANUP_SUPPORTED_SOURCE_LANGUAGES`. A non-empty value
outside that tuple appends one stable warning naming the detected value and
asking the operator to review carefully. Supported values and `None` do not
receive this warning. Predominantly CJK or Hangul text remains rejected before
Cleanup artifacts are published.

## Data / interface

The initial `warnings` list in `cleanup.json` is the sole persistence seam.
Existing checkpoint reuse, profile-change handling, adjudication, finalization,
state notes, and manifest summary projection retain that list. No UI-specific
warning reconstruction or language substitution is permitted.

## Examples

Detected `el` completes with `Detected source language 'el' is outside the
supported Cleanup languages; review the result carefully.` exactly once.
Detected `ro` and unavailable detection add no unsupported-language warning.

## Acceptance

Tests control detection directly and verify deterministic, AI, cancellation and
resume, and finalization paths retain exactly one warning, clean output,
state-note visibility, and manifest `warning_count`.
