<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

<!--
Task journal. One file per task, at .agentic/tasks/TASK-<id>.md, kept
after delivery as the task's historical record.

The header is the block of "key: value" lines directly under the title.
Keep it exactly in that form — one key per line, no blank lines inside
the block, no comments between the lines — so it stays machine-readable.

  stage         frame | specify | design | build | validate | deliver | done
                (adoption journals: survey | components | close | done)
  type          feature | fix | change | adopt
  path          full | quick
  requirements  comma-separated requirement IDs, empty until specify
  branch        the branch this task is delivered on
  base          the commit this task started from, filled in at creation;
                the delivery report and `check --task` measure the diff
                against it, so leave it alone once it is written. Empty
                when the repository had no history yet.
  opened        YYYY-MM-DD

Header lines are edited in place; log lines are only ever appended.
Keep each log line to one sentence.

Stage report is one replaceable latest snapshot, not an evidence store.
Use plain one-line fields with no fences or bullets inside that section.
stage is the reported stage; current must match the journal header after any
transition. result is in_progress | completed | paused | blocked | skipped.
Keep all observations and decisions in the append-only Log as well.
Leave unknown fields blank; summary prints not recorded, never an assumed pass.
Refresh after work or decisions even if current has not changed.
-->

# TASK-dc67b4dc — Provider-managed AI output limits

stage: build
type: change
path: full
requirements: REQ-PLAT-75d29093, REQ-NFR-414888ee, REQ-UX-34b436ff
branch: master
base: 2ec1d9d7a913def398e97ebaa2f6361413b37951
opened: 2026-08-30

## Done checklist (current stage)

- [ ] each automated requirement has a pre-implementation red record with exact selector or command, non-zero exit, and expected failure reason; each manual requirement has a post-implementation observation
- [ ] repository anchor recorded after red and evolution reviewed after implementation
- [ ] implementation makes those tests pass
- [ ] `test --impacted` green
- [ ] `affected_paths` and `linked_tests` updated on every requirement
- [ ] `status = "active"` on every requirement this task delivers - or `"retired"`, with the reason in its prose, where this task deliberately removed the behavior
- [ ] `check` clean, or each remaining warning explained in the log
- [ ] `stage: validate`

## Log

- 2026-08-30 frame: Scope is to make every generic AI chat request provider-managed for output length by omitting `max_tokens` and `max_completion_tokens`, while retaining a separately named profile output reserve solely for AudioMancer context planning.
- 2026-08-30 frame: In scope are normalized AI profile settings, AI Settings labels/help, generic and JSON-repair provider payload construction, shared operation budget callers, tests, user guidance, knowledge, and the Unreleased changelog; excluded are live-provider execution, model-specific defaults, output-token comparison policy, TTS token limits, version changes, packaging, commits, pushes, and pull requests.
- 2026-08-30 frame: Full path is required because this changes a user-visible profile contract, all AI-provider request payloads, and context budgeting across workflows.
- 2026-08-30 frame: DEVIATION frame: continued on `master` rather than creating a task branch because the user previously required the same branch; no commit or push is authorized.
- 2026-08-30 frame: Proposed requirements are provider-managed output-limit transport, planner-only output reserve semantics, and AI Settings/help clarity for the renamed reserve.
- 2026-08-30 frame: The user approved the full-path scope and requested targeted tests only; the full suite remains explicitly excluded.
- 2026-08-30 specify: Created draft transport, local-reserve, and AI Settings clarity requirements plus a provider-interface specification that defines legacy settings migration and unbounded provider payloads.
- 2026-08-30 specify: `aegis check --task TASK-dc67b4dc` reported zero errors; accepted warnings are the existing dirty Book Analysis feature, unrelated open tasks, pre-existing planning/layout paths, and the missing task anchor before build.
- 2026-08-30 design: The AI Runtime and Platform Settings UI knowledge pages have no `## Architecture` diagram; this is an internal contract change within their existing shapes, so no architecture revision is owed.
- 2026-08-30 design: `py -3.12 .agentic/aegis.py check --task TASK-dc67b4dc` exited zero with 53 pre-existing dirty-worktree, unrelated-journal, layout, and no-anchor warnings; no errors were reported and the warnings are accepted outside scope.
- 2026-08-30 build red: command=`05_Software/AudioMancer/.venv/Scripts/python.exe -m pytest -q tests/test_llm_provider_service.py::test_chat_json_omits_provider_output_limits tests/test_settings_service.py::test_validate_settings_migrates_legacy_output_limit_to_local_reserve tests/test_ai_settings_page.py::test_ai_settings_page_presents_output_reserve_not_provider_cap`; exit=1; expected missing behavior=the provider payload still contains max_tokens and the renamed settings/UI fields do not exist.
- 2026-08-30 build red: command=`05_Software/AudioMancer/.venv/Scripts/python.exe -m pytest -q tests/test_settings_service.py::test_validate_settings_migrates_legacy_output_limit_to_local_reserve`; exit=1; expected missing behavior=normalization exposes no output_reserve_tokens field.
- 2026-08-30 build: Anchor recorded after the red tests; provider payloads now omit output-limit fields, legacy profiles migrate to output reserves, and every shared workflow budget/provenance consumer uses the reserve only locally.
- 2026-08-30 build: Focused offline tests passed: 300 passed, 3 retired provider-token-compatibility tests skipped; focused ruff passed after retaining Cleanup's preflight reservation validation without serializing an override.
- 2026-08-30 build: Evolution reviewed 43 files: provider, settings, budget/workflow, UI, tests, guides, knowledge, and changelog changes match the design; concurrent Book Analysis files are pre-existing and excluded.
- 2026-08-30 build: AEGIS check exited zero with 21 accepted pre-existing layout, unrelated-journal, and Book Analysis coverage warnings.

## Design

- Settings normalization migrates legacy `max_output_tokens` into positive `output_reserve_tokens` and drops the legacy key; the renamed value is planner data only. [REQ-NFR-414888ee]
- `ai_budget_service` and every workflow metadata/provenance consumer rename their reserve input/output while retaining the same conservative source-capacity arithmetic. [REQ-NFR-414888ee]
- `llm_provider_service.chat_json` removes the per-call output override and constructs initial, fallback, and repair payloads without either provider output-limit field; a length finish remains a generic provider-limit failure. [REQ-PLAT-75d29093]
- AI Settings binds the renamed reserve field and English/Romanian label; the two guides explain that AudioMancer reserves local context but lets the provider select completion length. [REQ-UX-34b436ff]
- Existing Book Analysis profile fingerprints include the renamed planner field, intentionally treating legacy fingerprinted candidates as a different safe configuration. [REQ-NFR-414888ee]
- Rejected alternative: retaining the `max_output_tokens` name while omitting it from requests, because it continues to imply a provider cap and obscures the separate planner role. [REQ-PLAT-75d29093] [REQ-UX-34b436ff]
- Test seams: captured `urlopen` payloads for transport; `validate_settings` and budget metadata for migration/reserve; AI Settings widget state and localization catalogs for operator wording. [REQ-PLAT-75d29093] [REQ-NFR-414888ee] [REQ-UX-34b436ff]
- Expected files: config, settings, provider, budget/workflow/provenance, UI/localization, settings scaffold, user guides, changelog, knowledge, and their focused tests.

## Stage report

stage: design
result: completed
current: build
changed: Recorded and checked the provider-boundary, local-reserve, settings-migration, and UI wording decisions.
evidence: `py -3.12 .agentic/aegis.py check --task TASK-dc67b4dc` exited zero; both affected knowledge pages have no architecture diagram to revise.
issues: Existing dirty Book Analysis feature paths remain outside this task; full-suite validation is explicitly excluded by the user.
next: Add focused failing tests before implementation and then anchor the task.
needs_user: no - the user approved the full-path scope and requested continuation.
