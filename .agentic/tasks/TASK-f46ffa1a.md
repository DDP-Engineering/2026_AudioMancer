# TASK-f46ffa1a - Create projects with source selection and autosaved confirmed options

stage: done
type: change
path: full
interaction: autopilot
requirements: REQ-FUNC-b27e4e87, REQ-FUNC-eb5d81aa, REQ-FUNC-1c28e0bf, REQ-FUNC-ad79f7c7, REQ-FUNC-f0999e62, REQ-FUNC-348f0aeb, REQ-FUNC-c3d29114, REQ-FUNC-3500196d, REQ-FUNC-3401b07e, REQ-FUNC-ec10fa36, REQ-FUNC-2083d3a1, REQ-FUNC-c1618303, REQ-FUNC-c132a7bf, REQ-FUNC-b1f49831, REQ-FUNC-3278aae6, REQ-UX-e4b0be69
parent:
branch: master
base: 36b1c375e8532c0c8160e184207de69a30717797
opened: 2026-11-04

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

Problem:
- STATED: the approved New Project refinement removes the separate Start Project action and makes later language/voice-mode changes explicit and understandable.
- OBSERVED: home_ui_controller.handle_new_project_requested creates and activates a source-less project; handle_project_options_lock_requested and project_workspace_service.lock_project_options persist and freeze source/language/mode.

Desired outcome:
- STATED: implement the preceding approved proposal on the current branch, using AEGIS, with automatic language saving, reset confirmations, updated tests and English/Romanian guides, without committing.

Actors:
- STATED: desktop operator creates or opens a book project and selects translation language or narration mode.

Primary scenario:
- STATED: New Project -> existing parent-folder and name dialogs -> document picker -> imported, configured, active project; Home has no Start Project action.
- STATED: later option selections persist automatically after any required confirmation, displaying the actual results to be removed.

Examples:
- STATED (approved proposal): changing narrator_and_characters to same_narrator preserves source/text/translation/characters/narrator and resets character samples plus Speech Blocks, generated audio and assembly; the reverse change has the same dependency boundary.
- STATED (approved proposal): language changes reset affected Translation and downstream results plus Book Analysis after confirmation when existing data is affected.

Counterexamples:
- STATED (approved proposal): cancelling any creation picker leaves the previous project active and creates no incomplete new project; cancelling a change restores the saved option without deletion; selecting the current value is a no-op.

In scope:
- STATED: integrated creation/import, source fixed after successful import, autosaved Home language and voice mode, actual-impact confirmations, busy-operation guards, compatibility of existing projects, tests, both UI languages and guides, Unreleased changelog.
- STATED: preserve character definitions and voice prompt edits on mode change; preserve narrator profiles, selected narrator and its sample; preserve exports outside the project.

Out of scope:
- STATED: commits (explicit user restriction).
- INFERRED from the approved Home-flow proposal: runtime/model/provider changes, external export removal, releases/version assignment and automatic expensive text/voice/audio generation are outside this implementation.

Constraints:
- STATED: work on the current branch; OBSERVED: branch is master, the repository default. No branch switch or creation is authorized.
- OBSERVED: existing uncommitted AEGIS 0.15.0 upgrade and changelog entry belong to the previous authorized operation and must be preserved.
- OBSERVED: .agentic/aegis.toml defaults to checkpoint (interaction table absent); explicit review enabled, max_fix_cycles=2; diagrams enabled for structure, sequence and state. STATED: user selected task-only autopilot through validation without commit on 2026-11-04.
- OBSERVED: binding code style is 01_Documentation/Code_Style.md; project rules are .agentic/PROJECT.md. Full verification uses configured commands.

Success signals:
- STATED: creation ends with a copied source and usable persisted options, without Start Project; cancelled/failed creation never activates an incomplete project.
- STATED: confirmed option changes have the displayed reset/preservation effects and survive reopening; cancellation and same-value selections preserve bytes and UI selection.
- STATED: loading/refreshing project state triggers no change confirmation or deletion; changes are blocked while operations run.
- STATED: English and Romanian UI/guides describe the same behavior and meaningful tests prove the reset, cancellation, preservation and persistence boundaries.

Evidence:
- OBSERVED: .agentic/knowledge/Project_Lifecycle.md owns creation/import/manifests; App_Shell.md owns MainWindow wiring; Character_Voices and Operation_Orchestration own voice artifacts/reset helpers.
- OBSERVED: exact source inspected in ui/controllers/home_ui_controller.py, ui/pages/home_page.py, ui/main_window.py, services/project_workspace_service.py, import_service.py, operation_runtime_service.py, narrator_definition_service.py and character_voices_state_service.py under 05_Software/AudioMancer/src/audiomancer/.
- OBSERVED: test_home_ui_controller.py, test_home_page.py and test_main_window_project_flow.py currently exercise separate creation/import/locking; tests need deliberate contract updates.
- OBSERVED: REQ-FUNC-1c28e0bf and REQ-FUNC-eb5d81aa describe locking and unlocked import drafts, conflicting with the newly authorized flow; specify must reconcile them rather than silently bypass them.
- OBSERVED: python .agentic/aegis.py status exit 0 found two unrelated legacy deliver tasks; neither covers this feature. git branch --show-current exit 0 returned master. No tests run at frame.

Assumptions:
- INFERRED: reuse current initial defaults (English, narrator_and_characters) for each new project rather than inheriting the preceding project's options; defaults remain visible and immediately editable.

Unknowns:
- UNKNOWN until design/verification: exact transaction/rollback seam for creation and multi-file reset failures; which existing legacy requirements additionally need revision; full-suite runtime on this checkout.

Decision-blocking questions:
- Product scope is STATED and approved by the user. User selected autopilot through validation without commit; no decision-blocking questions remain.

Proposed behaviors:
- No additional product behavior beyond the approved proposal. Technical design must make the displayed impact and executed reset agree and preserve unrelated files on failures.

Path and reason:
- Full path: changed user-visible creation, editing and data invalidation contracts require specify and design.

| Criterion | Holds? | Evidence |
|---|---|---|
| no new externally observable behavior | no | integrated creation and editable persisted options |
| no new interface or data format | no | Home signals and option-change service boundary change |
| no new dependency | yes | existing PySide6 and stdlib seams suffice |
| an existing requirement already covers the behavior | no | locking/draft contracts need revision and reset requirements |
| no security or data-handling change | no | confirmed deletion and preservation rules change |

- INFERRED: one integrated task; no child tasks are needed. Explicit independent review at validate remains required by the configured review policy.

## Requirement coverage

| Frame outcome | Atomic behavior | Requirement | Verification | Design decision or no impact |
|---|---|---|---|---|
| Approved Home-flow outcome | Create and activate a project with its book | REQ-FUNC-b27e4e87 | Mock all creation pickers, select a real supported document, and verify copied bytes, source metadata, initial options, current active project and absence of a Start Project button. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Keep the registered project book fixed | REQ-FUNC-eb5d81aa | Open projects with a source and either legacy lock value; verify the import control is disabled and a direct import request leaves every existing file unchanged. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Save project language automatically | REQ-FUNC-1c28e0bf | Select a different language in an empty project and reload project.json; verify both language fields and the Home selection, including an initially legacy-locked project. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Cancel project creation without switching projects | REQ-FUNC-ad79f7c7 | Cancel folder, name or book selection with an active project and modified draft; compare the project tree and active state. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Contain unsuccessful project creation and import | REQ-FUNC-f0999e62 | Inject copy and manifest-write errors, including an existing empty destination, and verify warning, unchanged active state and removal of only newly created artifacts. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Confirm narration-mode changes with selective reset | REQ-FUNC-348f0aeb | Test both mode directions with real project artifacts and sample metadata; compare preserved bytes, removed sample/audio/block artifacts, reset summaries and the localized dialog impact. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Confirm language-dependent result resets | REQ-FUNC-c3d29114 | Seed affected and preserved artifacts, change language, confirm, and verify the exact reset set including narrator and analysis data; change an empty project language without a destructive confirmation. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Preserve option state on cancellation or unchanged selection | REQ-FUNC-3500196d | Reject both change dialogs and reselect existing values; compare project bytes and selected combo data with no repeat dialogs. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Load existing projects without option-change side effects | REQ-FUNC-3401b07e | Refresh legacy locked/unlocked projects repeatedly with signal observers and verify no change requests, prompts or deletions. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Prevent project option changes during running operations | REQ-FUNC-ec10fa36 | Set active operation and trigger direct handlers as well as inspect controls; assert no picker, dialog, manifest write or artifact deletion. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Recover failed confirmed option changes | REQ-FUNC-2083d3a1 | Inject artifact-staging and manifest/voice-plan write errors after partial progress and compare all original project bytes, including approved blocks and samples. | project_options_service transaction and Home controller/UI seams |
| Approved Home-flow outcome | Explain project creation and reset behavior in both languages | REQ-FUNC-c1618303 | Inspection: compare both catalogs and guide creation/workflow sections with the implemented controls and reset tests; check that current instructions contain no Start Project step. | project_options_service transaction and Home controller/UI seams |
| Approved fixed-source boundary | Independent control editability | REQ-FUNC-c132a7bf | Home source/legacy/busy matrix | Home selector gating |
| Preserve low-level import guarantees | Source copy-first replacement API | REQ-FUNC-b1f49831 | Existing importer failure/collision tests | Importer unchanged; Home fixes source |
| Existing import safety | Stored-source identity is a low-level no-op | REQ-FUNC-3278aae6 | Importer identity and Home source-guard tests | Low-level importer unchanged |
| Localized source status | UI locale changes retain fixed-source availability | REQ-UX-e4b0be69 | Home source/locale matrix | Source presence controls status and import |

## Design

### Approach
- STATED: the approved flow and preservation boundaries are the implementation contract (REQ-FUNC-b27e4e87, REQ-FUNC-348f0aeb, REQ-FUNC-c3d29114).
- INFERRED: add project_options_service with source-ready creation plus a read-only option-change plan and transactional apply; keep Qt dialogs in home_ui_controller.
- INFERRED: create/import in a sibling temporary workspace, publish the completed folder, then activate it; preserve any pre-existing empty destination on failure (REQ-FUNC-f0999e62, REQ-FUNC-ad79f7c7).
- INFERRED: replace the Home Start button/signal with deliberate combo activation signals; MainWindow routes them to one controller. Programmatic refresh does not emit change requests (REQ-FUNC-3401b07e).

### Interfaces and data
- OBSERVED: existing project.json carries target_language, selected_voice_language, voice_assignment_mode and the legacy project_options_locked flag; retain schema compatibility and honor saved values on open.
- INFERRED: create_project_with_source(name, parent, source) returns (root, manifest), with current defaults and a registered fixed source; existing create_project remains the low-level workspace API (REQ-FUNC-b27e4e87, REQ-FUNC-eb5d81aa).
- INFERRED: plan_project_options_change(root, language, mode) captures manifest bytes, options, exact existing operation-owned files, affected operation labels and any replacement character-target document; apply_project_options_change(plan) rechecks the manifest and publishes exactly that plan (REQ-FUNC-1c28e0bf, REQ-FUNC-2083d3a1).
- INFERRED: add a public operation_reset_artifact_paths collector backed by the existing runtime registry; reject symlink/path escapes before mutation. Existing reset execution remains unchanged.
- INFERRED: mode changes reset Character Voices summary/sample metadata and samples plus Speech Blocks, Audio Blocks and Audio Assembly; preserve characters_voice.json prompt/preview edits, narrator targets/profiles/samples and all upstream data (REQ-FUNC-348f0aeb).
- INFERRED: language changes reset Translation and every later operation plus Book Analysis, retaining original-language evidence and data through Chunking (REQ-FUNC-c3d29114).
- INFERRED: lower current_stage only to the last retained workflow boundary, never promote an earlier project. Empty language changes save directly; every different mode requests confirmation, including a no-results message (REQ-FUNC-348f0aeb, REQ-FUNC-c3d29114).
- INFERRED: settle the Translation page debounce through its existing flush API before planning, so accepted or cancelled changes preserve the latest manual edit and no timer runs after reset (REQ-FUNC-348f0aeb, REQ-FUNC-c3d29114, REQ-FUNC-3500196d). Mode-only changes preserve legacy selected_voice_language; only a target-language change synchronizes it.
- INFERRED: stage affected originals under their project-relative names by rename in a project-local temporary backup, write any replacement target document and manifest atomically, and restore originals on expected failure. If restoration itself fails, keep recovery originals and report the backup path (REQ-FUNC-2083d3a1; filesystem-failure technical constraint).
- INFERRED: the confirmation lists actual affected categories and file counts; cancellation restores the saved selection and leaves project bytes unchanged. Handlers reject changes while busy and stop audio playback before confirmed file mutation (REQ-FUNC-3500196d, REQ-FUNC-ec10fa36).

### Files and test seams
- INFERRED: add services/project_options_service.py and tests/test_project_options_service.py for creation, planning, reset/preservation, containment and rollback; extend operation_runtime_service.py only with registry-backed collection.
- INFERRED: change home_ui_controller.py, home_page.py and MainWindow signal wiring; extend test_home_ui_controller.py, test_home_page.py and test_main_window_project_flow.py for wizard cancellation, autosave, confirmation, busy and legacy-refresh paths.
- STATED: update ui_state_service.py, both UserGuide index.html files and CHANGELOG.md; validate reconciles Project_Lifecycle, App_Shell, Operation_Orchestration and Character_Voices knowledge as needed (REQ-FUNC-c1618303).

### Risks and open decisions
- OBSERVED: existing Home tests and REQ-FUNC-b1f49831 include replacing an unlocked processed source. Revise controller coverage to the authorized fixed-source contract, while retaining low-level import copy-first guarantees and tests.
- INFERRED: no concurrent project worker is allowed during planning/application; stale manifest plans are rejected. Cross-process writers and process crashes remain outside the existing filesystem transaction guarantee.
- OBSERVED: AI/TTS providers and generation algorithms are unchanged. No dependency, app version, branch or commit changes are needed.
- Initial imports for legacy source-less projects share import_initial_source with staged creation, restoring the original manifest and removing the new copy on failure. No unresolved product decisions. Technical verification includes invalid voice metadata, symlink containment and injected staging/publication failures.

### Requirement map
- REQ-FUNC-c132a7bf and REQ-UX-e4b0be69: Home source presence controls source availability; language/mode remain editable independently of legacy flags.
- REQ-FUNC-b1f49831 and REQ-FUNC-3278aae6: preserve low-level importer copy/identity guarantees while Home fixes the registered book.
- REQ-FUNC-b27e4e87: Create and activate a project with its book; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-eb5d81aa: Keep the registered project book fixed; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-1c28e0bf: Save project language automatically; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-ad79f7c7: Cancel project creation without switching projects; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-f0999e62: Contain unsuccessful project creation and import; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-348f0aeb: Confirm narration-mode changes with selective reset; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-c3d29114: Confirm language-dependent result resets; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-3500196d: Preserve option state on cancellation or unchanged selection; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-3401b07e: Load existing projects without option-change side effects; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-ec10fa36: Prevent project option changes during running operations; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-2083d3a1: Recover failed confirmed option changes; service transaction tests or Home UI integration, with guide inspection for localization.
- REQ-FUNC-c1618303: Explain project creation and reset behavior in both languages; service transaction tests or Home UI integration, with guide inspection for localization.

Diagrams: [diagram_TASK-f46ffa1a.md](diagram_TASK-f46ffa1a.md)


## Log

- 2026-11-04 frame: journal opened
- 2026-11-04 frame: completed; next specify - Approved scope and explicit autopilot
- 2026-11-04 specify: completed; next design
- 2026-11-04 design: completed; next build
- 2026-11-04 build: red: uv run --project 05_Software/AudioMancer pytest -q tests/test_home_ui_controller.py selectors creates_and_activates_project and document_cancel (repository-relative paths) exit 1; source remained None and cancelled wizard activated a new project (REQ-FUNC-b27e4e87, REQ-FUNC-ad79f7c7)
- 2026-11-04 build: green: focused wizard creation and document-cancel tests exit 0 (2 passed). Source copy failure tests also pass for new and pre-existing empty destinations.
- 2026-11-04 build: red: uv run --project 05_Software/AudioMancer pytest -q 05_Software/AudioMancer/tests/test_project_options_service.py --tb=short exit 1; 7 tests fail because planning/apply API is absent, covering selective mode/language reset, autosave, no-op, stale plans and rollback
- 2026-11-04 build: green: test_project_options_service.py exit 0, 9 passed; both mode directions, language reset, direct autosave, no-op, stale-plan rejection and rollback verified.
- 2026-11-04 build: red: focused Home page/controller selectors exit 1 (3 failures): Start Project still exists and new change signal/handler are missing; cancellation/busy integration cases added before UI implementation.
- 2026-11-04 build: red: test_initial_import_manifest_failure_removes_new_copy exit 1; legacy source-less projects also need the source+manifest failure boundary (REQ-FUNC-f0999e62).
- 2026-11-04 build: Reconciled authorized fixed-source behavior with existing REQ-FUNC-c132a7bf and REQ-FUNC-b1f49831; retained the low-level importer copy-first API and existing tests, and replaced Home source-replacement coverage with unchanged-project guard coverage. No requirement retired.
- 2026-11-04 build: green: service option suite exit 0 (14 passed, 1 Windows symlink-privilege skip); real EN/RO confirmation button and impact tests exit 0 (6 passed).
- 2026-11-04 build: red: real confirmation tests exit 1 (4 failures) because Qt detail-button labels bypass the EN/RO catalog; extend localization at this existing dialog seam (REQ-FUNC-c1618303).
- 2026-11-04 build: The guide Home screenshots still show the removed Start Project action. Refresh these two existing images with a synthetic source-ready workspace and sanitized settings, preserving all other screenshots and user projects (REQ-FUNC-c1618303).
- 2026-11-04 build: Inspection: both guide project/manual/TTS/translation sections now describe autosave and confirmed resets; both Home PNGs were regenerated from a synthetic temporary book with sanitized settings, and visually inspected at 1920x1040. QT_QPA_FONTDIR was set to the installed Windows font folder for readable offscreen rendering. No user project was opened.
- 2026-11-04 build: green: EN/RO live confirmation tests exit 0 (6 passed), including localized details labels and default Cancel. Windows junction escape test exit 0, supplementing the privilege-dependent symlink case.
- 2026-11-04 build: red: summary-only EN/RO confirmation tests exit 1; recorded progress with zero artifact files misleadingly refers to unavailable file details. Clarify this actual-impact boundary before completing build.
- 2026-11-04 build: green: focused summary-only confirmation and name/document cancellation-with-unsaved-Cleanup tests exit 0 (4 passed). Both cancellation points preserve the old draft and active project.
- 2026-11-04 build: green: focused service/import/runtime/localization/package verification exit 0 (66 passed, 1 privilege-dependent symlink skip); the equivalent Windows junction containment case passed. Requirements for source-status localization were reconciled with the authorized fixed-source contract.
- 2026-11-04 build: green: targeted Home and MainWindow integration selection exit 0 (24 passed); current service/source-status/error-handling selection exit 0 (19 passed, 1 Windows symlink-privilege skip). Formatting, source-style and logging audits passed. Wider pre-review focused attempts were interrupted after candidate/runtime adjustments; no final suite result is claimed for them.
- 2026-11-04 build: Build evolution reviewed: exactly 15 product/test/help/changelog files changed since the anchor, including the two planned new Python files. AEGIS check exit 0: no format/coverage errors; remaining warnings concern pre-existing journals/ticket/fingerprint tracking and required guide/changelog files outside configured layout globs.
- 2026-11-04 build: completed; next validate
- 2026-11-04 validate: Validation reconciliation: updated Project Lifecycle, App Shell, Operation Orchestration, Character Voices and adjacent Book Analysis boundaries plus project/environment context. Migrated touched legacy knowledge headings and retired architecture sections while retaining current constraints. Re-read task requirements, reviewed product diff and inspected both guide captures.
- 2026-11-04 validate: Review round 1: spec requires preserving selected_voice_language on mode-only changes in legacy projects; quality requires settling pending Translation autosaves before planning and retaining project-relative paths in recovery backups. All three are concrete reproductions within the approved preservation/recovery contract.
- 2026-11-04 validate: returned to build - Apply the three round-1 review findings within the bounded fix loop
- 2026-11-04 build: red review fixes: targeted legacy voice-language and recoverable-backup tests exit 1 (2 failures); real pending-translation navigation/option-confirmation tests exit 1 (4 failures, both accept/cancel and mode/language).
- 2026-11-04 build: green review fixes: targeted legacy voice language, recoverable backup paths, partial rollback, pending Translation accept/cancel for both option kinds, and Home error handling exit 0 (11 passed). Source style, logging coverage and ruff checks exit 0. No scope or dependency change.
- 2026-11-04 build: completed; next validate
- 2026-11-04 validate: Round-1 corrections preserve the approved contract: mode-only updates retain legacy voice language; already-requested Translation edits settle before planning, including cancellation; rollback-denied originals retain a durable relative-path tree. Reconciled the affected Project Lifecycle and AI Translation knowledge.
- 2026-11-04 validate: Review round 2: independent specification and implementation-quality reviewers both approved the same corrected candidate. Quality re-ran the original pending-edit reproduction successfully; legacy voice-language and named-recovery-backup regressions are green.
- 2026-11-04 validate: Full proof interrupted at explicit user request after 2111.9s: check --task TASK-f46ffa1a --strict --run exit 1, test process terminated exit 4294967295; no complete test result. Codestyle and logging_coverage both exit 0. DEVIATION validate: full regression is replaced by focused proof because the user prohibited running all tests due to duration; unrelated application regressions remain unproven. Existing advisory warnings: old journals/ticket/fingerprint tracking and required guides/changelog outside configured layout globs.
- 2026-11-04 validate: final focused proof: uv run pytest -q tests/test_project_options_service.py tests/test_home_page.py tests/test_home_ui_controller.py::test_project_options_confirmation_buttons_and_actual_impact tests/test_home_ui_controller.py::test_home_option_failure_reports_error_and_restores_selection tests/test_home_ui_controller.py::test_empty_mode_confirmation_reports_no_existing_results tests/test_home_ui_controller.py::test_project_options_confirmation_distinguishes_progress_without_files exit 0; 53 passed, 1 Windows symlink-privilege skip in 3.91s (junction equivalent passed). Static check --task TASK-f46ffa1a --strict exit 0, errors=0 warnings=13; git diff --check exit 0. Codestyle and logging audits exit 0 in the interrupted full proof. Independent reviews approved round 2. No candidate edits after proof; full-suite limitation and advisory-warning reasons recorded above.
- 2026-11-04 validate: completed; next done

## Rulings

- RULING-001 | date=2026-11-04 | decision=Implement the approved Home project creation and autosaved options proposal on master, with AEGIS, tests and both guides, without commit | reason=User explicitly approved implementation and scope on 2026-11-04 | source=user | supersedes=none
- RULING-002 | date=2026-11-04 | decision=Use task-only autopilot through complete validation without commit | reason=User selected autopilot in the interaction-mode question | source=user | supersedes=none


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-f46ffa1a.md
changed: Implemented source-ready New Project flow, removed Start Project, automatic language/mode saving with selective-reset confirmations; tests, EN/RO guides/screenshots, requirements, knowledge and all 3 diagrams updated; no commit
evidence: Final focused pytest exit 0: 53 passed, 1 privilege skip in 3.91s; static AEGIS strict check exit 0, both repository audits exit 0; spec and quality approved round 2
issues: Full regression interrupted at user request; focused verification only. Windows symlink privilege skip covered by passing junction equivalent; 13 advisory warnings documented in journal.
spec_compliance: approved
implementation_quality: approved
review_round: 2

## Delivery report (2026-11-04)

- stage: validate; type: change; path: full; branch: master
- requirements:
  - REQ-FUNC-b27e4e87 - Create and activate a project with its book
  - REQ-FUNC-eb5d81aa - Keep the registered project book fixed
  - REQ-FUNC-1c28e0bf - Save project language automatically
  - REQ-FUNC-ad79f7c7 - Cancel project creation without switching projects
  - REQ-FUNC-f0999e62 - Contain unsuccessful project creation and import
  - REQ-FUNC-348f0aeb - Confirm narration-mode changes with selective reset
  - REQ-FUNC-c3d29114 - Confirm language-dependent result resets
  - REQ-FUNC-3500196d - Preserve option state on cancellation or unchanged selection
  - REQ-FUNC-3401b07e - Load existing projects without option-change side effects
  - REQ-FUNC-ec10fa36 - Prevent project option changes during running operations
  - REQ-FUNC-2083d3a1 - Recover failed confirmed option changes
  - REQ-FUNC-c1618303 - Explain project creation and reset behavior in both languages
  - REQ-FUNC-c132a7bf - Edit Home options independently of the fixed source
  - REQ-FUNC-b1f49831 - Preserve copy-first guarantees in the source import API
  - REQ-FUNC-3278aae6 - Selecting the stored source is an idempotent no-op
  - REQ-UX-e4b0be69 - Language switching preserves truthful source status
- deviations: 1 recorded
  - validate: full regression is replaced by focused proof because the user prohibited running all tests due to duration; unrelated application regressions remain unproven. Existing advisory warnings: old journals/ticket/fingerprint tracking and required guides/changelog outside configured layout globs.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=2
- diff vs task base 36b1c37: 62 file(s) changed, 4117 line(s) added
- checks: errors=0 warnings=13 notes=1
- checklist: 7/9 done; open: final `check --strict --run` result logged truthfully after the last edit; `report` appended
