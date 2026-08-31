<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-e73cba08 - Resumable hierarchical book analysis

## Behavior

Book Analysis is an optional AI operation available after Text Chunking has
produced a completed, valid `chunks_text.json`. It reads canonical chunks in
their stored order and never edits them. It groups only whole chunks into
budgeted leaf windows, requests a validated structured summary for each window,
then recursively groups and consolidates validated summaries until one final
structured synthesis fits. Every accepted leaf or consolidation result is an
atomic checkpoint. Cancellation, process exit, or a recoverable failure leaves
those checkpoints available to an exact-match resume.

The final report has two presentation layers. The concise layer contains book
type/genre, subjects, setting/time, a spoiler-light summary, main characters and
roles, and themes. The expandable layer contains a spoiler-labelled detailed
summary, supporting characters and relationships, narrative perspective and
structure, tone/pacing/diction/emotional range, audiobook guidance,
uncertainties, and optional technical source evidence. All generated report
content uses the project's selected translation target language. English and
Romanian localization applies only to application controls and labels.

Structured output uses JSON Schema when the selected backend supports it;
otherwise it requests strict JSON and permits one bounded correction request.
A provider-confirmed context overflow permits one retry with a smaller input
budget. Other invalid results or exhausted retries preserve the candidate and
surface an actionable failure. A single canonical chunk larger than the safe
source budget is never split by this operation; the UI directs the user to
create smaller chunks on Text Chunking.

## Model and request contract

Book Analysis accepts any LM Studio, Ollama, or generic OpenAI-compatible
profile whose configured or discovered context is at least 16,384 tokens. It
does not identify supported models by name. Profiles expose `reasoning_mode`
with values `provider_default`, `enabled`, and `disabled`. Backends translate a
non-default preference only when they have a supported capability; otherwise
they omit the control and use provider default. The effective preference and
context remain visible in AI Settings, not on the Book Analysis page.

For every request, source capacity is the smaller of:

1. context minus prompt, output/reasoning, and safety reserves; and
2. 50 percent of context for LM Studio and Ollama, or 30 percent for generic
   OpenAI-compatible online profiles.

Token estimates and reserve values are recorded in the candidate for diagnosis
and deterministic resume matching. No API key, authorization header, or other
secret may be persisted.

## Data / interface

The project artifact is one atomically replaced `book_analysis.json` document:

```json
{
  "schema_version": 1,
  "completed_report": null,
  "candidate_run": null
}
```

`completed_report`, when present, contains the source fingerprint and chunk
count, target language, AI profile identifier and safe request-configuration
fingerprint, completion timestamp, structured concise and detailed report, and
diagnostic token totals. Its freshness is derived only from the current source
and project target language; selecting another profile does not make a finished
report stale or re-enable Analyze. Staleness never deletes the report.

`candidate_run`, when present, contains a run identifier, status, source
fingerprint and chunk count, target language, profile identifier, safe
request-configuration fingerprint, reasoning mode and effective budgets,
phase/cursor, ordered validated leaf and consolidation summaries, token totals,
and the latest non-secret failure. A candidate is resumable only when source,
target language, profile identifier, and request-relevant configuration match
exactly. Selecting a different profile or changing relevant profile settings
starts a new candidate while preserving `completed_report`. A persisted
`running` candidate is presented as interrupted/resumable after application
restart.

The page follows Text Chunking and exposes an AI profile selector plus exactly
two action buttons: Analyze and Reset. Analyze starts or exact-match resumes and
is disabled while running and after a fresh completion. It is enabled for a
stale completed report and starts replacement work while that report remains
visible. Reset is enabled after any run has started and removes the completed
report, candidate, Book Analysis logs, and its manifest operation summary only.
Operation state is visible through the existing left-side Operation Status
control, and active work uses the existing standard progress dialog/bar.

Book Analysis is a supporting operation, not a canonical workflow stage. Its
state cannot block Translation or any downstream page, complete a Home
milestone, or write characters, narrator, voice, or other downstream artifacts.

## Examples

Normal: a 40-chunk novel is grouped into five whole-chunk leaf windows. Three
leaf results are checkpointed before cancellation. Pressing Analyze with the
same source, target language, profile, and relevant settings requests only the
remaining two leaves, then consolidation and final synthesis.

Profile change: an incomplete candidate from profile A is not resumable with
profile B. If analysis is otherwise startable, Analyze with B creates a new
candidate while any older completed report remains visible. A fresh completed
report remains current regardless of the selector value, so Reset is still
required before an intentional repeat.

Stale source: re-chunking changes the canonical source fingerprint. The prior
completed report is labelled stale and Analyze is enabled. Its former candidate
is not resumable. Translation remains available regardless.

Edge: one canonical chunk estimates above the safe source capacity for a
16,384-token local profile. No provider request is sent; the operation explains
that the user must return to Text Chunking and create smaller chunks.

## Acceptance

- Deterministic tests prove every canonical chunk is represented in order and
  no validated checkpoint is recomputed during an exact-match resume.
- Persistence tests prove completed-report preservation across cancellation,
  failure, stale input, profile/config change, and replacement work.
- Request tests prove minimum context, local/online fractions, reserves,
  reasoning capability handling, structured-output fallback, and bounded
  retries without model-name gates.
- Qt tests prove page order, exact controls, state-dependent enablement,
  stale-report visibility, layered rendering, localization, and integration
  with standard operation status/progress.
- Workflow tests prove Book Analysis never changes canonical stage continuity
  or downstream artifacts.
- All automated tests use deterministic doubles; live model validation is
  explicitly left to the user and is not claimed by the automated evidence.

## Supporting requirements

- REQ-DATA-8e648624 - atomic completed-report and candidate persistence
- REQ-PLAT-4b56b5de - model-agnostic reasoning preference handling
- REQ-NFR-057ca9b2 - context budgeting and minimum context
- REQ-UX-7a9404e3 - optional layered page experience
- REQ-FUNC-4fad33e4 - canonical workflow independence
- REQ-TEST-5a3dcf8d - hermetic automated validation
