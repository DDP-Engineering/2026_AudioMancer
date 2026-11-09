# TASK-8a4de5b4 - Use Italian synthesis hint for Romanian VoiceWeaver requests

stage: done
type: change
path: full
interaction: autopilot
requirements: REQ-FUNC-1562fca1
parent:
branch: master
base: 90b250e1e624c9f97614d10d66dd607e2b5c7107
opened: 2026-11-09

Edit Frame, Requirement coverage and Design directly. Write State, Log and
Rulings with `python .agentic/aegis.py` (advance, pause, log, ruling, verdict);
end each session with `advance` or `pause`.

## Done checklist (current stage)

- [x] diff reviewed against scope, requirements, design, error paths,
      portability, security and unrequested work
- [x] knowledge pages of changed components current with the reviewed code
- [x] project and environment context reconciled with the candidate
- [x] requirements re-read: status, prose, verification, paths and links true
- [x] manual or inspection verification recorded where applicable
- [x] explicit review approved, when enabled
- [x] final `check --strict --run` result logged truthfully after the last edit
- [x] remaining warnings and pre-existing failures explained
- [x] `report` appended

## Frame

Problem: STATED Qwen Voice Designer and Voice Clone need an Italian workaround for Romanian. OBSERVED the current request omits Romanian from the optional language field, and the local VoiceWeaver REST contract offers it but not ro.
Desired outcome: STATED use Italian for Romanian synthesis. INFERRED keep Romanian content and project metadata, using Italian only as the outgoing TTS language hint.
Actors: AudioMancer operator generating a sample or audiobook in Romanian.
Primary scenario: Generate a Romanian voice sample and synthesize Romanian speech blocks through Qwen.
Examples: Romanian preview with diacritics is sent unchanged as text alongside language it. A Romanian reference transcript remains unchanged in a clone-prompt request.
Counterexamples: English and French keep their own codes; when Voice Designer reports no Italian support, the existing omit behavior applies.
In scope: The shared VoiceWeaver request-language adapter, focused payload tests, and user-facing behavior docs.
Out of scope: Profile generation changes, translation changes, project metadata changes, changes to VoiceWeaver itself, and commit.
Constraints: Current master branch; focused tests and autopilot as in recent implementation work; preserve existing capability gating.
Success signals: All four TTS request shapes map ro to it while preserving text. Other language and unsupported-list behavior stays intact.
Evidence: VoiceWeaver REST Interface section 6.1, Qwen3-TTS upstream README, AudioMancer runtime helper, and REQ-FUNC-1562fca1.
Assumptions: Italian is the runtime hint requested by the operator. The adapter's callers continue to pass logical project and sample languages.
Unknowns: Actual Romanian pronunciation quality with the workaround.
Decision-blocking questions: None.
Proposed behaviors: Use it only at the shared outbound boundary.
Path and reason: Full. Outbound payload changes, while interface, storage, dependencies and data handling stay the same. Existing REQ-FUNC-1562fca1 needs revision.

## Requirement coverage

| Behavior | Requirement | Design |
|---|---|---|
| Italian runtime hint for Romanian text, preserving other request rules | REQ-FUNC-1562fca1 | Apply the substitution in the existing shared payload helper before its capability check |

## Design

Single-file implementation. REQ-FUNC-1562fca1 uses the existing shared request
helper to map ro to it before applying the current supported-list guard. All
four routes share it. Logical languages and text are kept at callers. Current
VoiceWeaver adapter creates the reusable prompt from audio and transcript, so
existing clone prompt artifacts need no change.

Design diagrams skipped for the single-file change with no new interface,
format, dependency or state.

## Log

- 2026-11-09 frame: journal opened
- 2026-11-09 frame: completed; next specify
- 2026-11-09 specify: completed; next design
- 2026-11-09 design: skipped; next build - One existing helper, no new interface, format, dependency or state
- 2026-11-09 build: red: three focused runtime contract tests fail as expected because design, direct clone and both reusable clone wrappers still omit the Romanian request hint; pytest exit 1 (REQ-FUNC-1562fca1).
- 2026-11-09 build: green: focused runtime/UI support, narrator text/sample, Speech Blocks source, clone reference language, and package metadata tests exit 0 (35 passed). Ruff and diff --check pass. Evolution has the expected five product paths. Strict AEGIS check has 15 baseline and three expected bilingual help/changelog advisories.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validate inspection: matched VoiceWeaver REST section 6.1 and Qwen adapter source. Reviewed all four request call sites, narrator metadata save, and target-text sources. Italian is used only for the outbound hint. Requirement, both guides and knowledge/context agree. No live pronunciation measurement.
- 2026-11-09 validate: DEVIATION validate: full test suite omitted per user preference. Use focused request, narrator, speech source and clone-language tests plus Ruff and AEGIS strict check.
- 2026-11-09 validate: final: uv run pytest on VoiceWeaver runtime, shared TTS UI support, narrator source and sample, Speech Blocks source, clone language and package metadata exit 0 (35 passed). Ruff, style/logging delta and git diff --check exit 0. AEGIS check --strict exit 0 with 15 baseline and three expected help/changelog advisories. No live synthesis or pronunciation test.
- 2026-11-09 validate: completed; next done

## Rulings


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-8a4de5b4.md
changed: Italian VoiceWeaver hint for Romanian speech, with Romanian content preserved.
evidence: 35 focused tests passed; Ruff, audits, diff and AEGIS strict checks passed.
issues: No live synthesis or pronunciation test; full suite omitted.
spec_compliance: approved
implementation_quality: approved
review_round: 1

## Delivery report (2026-11-09)

- stage: validate; type: change; path: full; branch: master
- requirements:
  - REQ-FUNC-1562fca1 - Send generation requests using the simplified VoiceWeaver contract
- deviations: 1 recorded
  - validate: full test suite omitted per user preference. Use focused request, narrator, speech source and clone-language tests plus Ruff and AEGIS strict check.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=1
- diff vs task base 90b250e: 9 file(s) changed, 157 line(s) added
- checks: errors=0 warnings=18 notes=2
- checklist: 8/9 done; open: `report` appended
