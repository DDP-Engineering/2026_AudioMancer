# TASK-0e2636ed - Unify text context menus and search across the desktop UI

stage: done
type: feature
path: full
interaction: autopilot
requirements: REQ-UX-0ceb3822, REQ-FUNC-439bbdcf, REQ-FUNC-05f3481f, REQ-FUNC-094a7552, REQ-REL-00228582, REQ-SEC-ea6952c2, REQ-FUNC-82eb0f19, REQ-UX-aa109e16
parent:
branch: master
base: dac62e0d1c7338fa5ca1d2af6991e2b24760eac6
opened: 2026-11-05

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

Problem: OBSERVED: most text controls retain only Qt's basic menu; Chunking and Characters duplicate page-local Find implementations.
Desired outcome: STATED: common right-click Copy, editable Cut/Paste/Delete, Find/Next plus accepted Select All, Undo/Redo, Previous, shortcuts and circular search.
Actors: STATED: desktop operator reviewing or editing book and workflow text.
Primary scenario: STATED: right-click or search a text field/preview/dialog, then copy or edit according to its current state.
Examples: STATED: Cleanup read-only source versus editable cleaned draft; Op Status text; Chunking and Characters previews.
Counterexamples: OBSERVED: masked credential fields rely on native protected clipboard behavior; preserve that behavior rather than exposing their text to Find.
In scope: STATED: shared text interaction component, existing page Find consolidation, standard keyboard shortcuts, literal local search, plain-text paste, English/Romanian UI and guides, relevant tests.
Out of scope: STATED: commits and full suite under continuing session constraints; INFERRED: project persistence, source transformations, regex/replace and decorative labels are not part of text-field interaction.
Constraints: STATED: current branch and AEGIS autopilot. OBSERVED: current/default branch master is clean at dac62e0; no new dependency is needed.
Success signals: INFERRED: every supported text control, including later-created dialogs, gets one consistent menu; read-only text is immutable; Find preserves project/editor text; search history stays local to each control.
Evidence: OBSERVED: app.py; ui/pages/text_chunking_page.py; characters_page.py; ui_scroll_service.py application event-filter precedent; related Qt tests.
Assumptions: INFERRED: QLineEdit, QPlainTextEdit and QTextEdit encompass app-owned text inputs and previews; ordinary labels/buttons are not editors.
Unknowns: UNKNOWN: native desktop clipboard integrations beyond injected Qt tests; no live provider calls needed.
Decision-blocking questions: None; user accepted the menu proposal and requested implementation.
Proposed behaviors: Accepted previous proposal; defaults preserve existing case-insensitive literal search and native editing validation.
Path and reason:
| Criterion | Holds? | Evidence |
| --- | --- | --- |
| no new observable behavior | no | app-wide commands and Previous |
| no new interface/data format | no | shared Qt interaction component |
| no new dependency | yes | installed PySide6 |
| existing requirements fully cover behavior | no | search is currently page-local |
| no data handling change | yes | UI operations only, no persistence changes |
Full path; one coherent task with no child tasks.

## Requirement coverage

| Requirement | Design | Verification |
| --- | --- | --- |
| REQ-UX-0ceb3822 | shared Qt interaction controller | test_text_interaction.py |
| REQ-FUNC-439bbdcf | shared Qt interaction controller | test_text_interaction.py |
| REQ-FUNC-05f3481f | shared Qt interaction controller | test_text_interaction.py |
| REQ-FUNC-094a7552 | shared Qt interaction controller | test_text_interaction.py |
| REQ-REL-00228582 | shared Qt interaction controller | test_text_interaction.py |
| REQ-SEC-ea6952c2 | shared Qt interaction controller | test_text_interaction.py |
| REQ-FUNC-82eb0f19 | Chunking delegates to shared interactions | test_text_chunking_page.py |
| REQ-UX-aa109e16 | runtime English/Romanian catalog | test_text_interaction.py and localization parity |


## Design

### Approach
INFERRED: Add ui/text_interaction.py with one application-owned QObject event filter, following the existing scroll-filter lifecycle precedent (REQ-UX-0ceb3822).
INFERRED: Intercept only text-control context/search/Paste events; existing native edit operations, validators and undo stacks remain authoritative.
INFERRED: Remove duplicated page-local Find code from Chunking and Characters; central installation also covers future dialogs without widget subclasses.
### Interfaces and data
INFERRED: install_text_interactions(application, language_provider) installs idempotently and retains the controller on QApplication.
INFERRED: build_menu, prompt_find, find_text and find_next provide focused Qt test seams; an editor runtime property stores its last accepted query (REQ-FUNC-439bbdcf).
INFERRED: Menus are rebuilt from current selection/read-only/clipboard/history state and use the current EN/RO catalog. Edit callbacks recheck state (REQ-UX-0ceb3822, REQ-UX-aa109e16).
INFERRED: Native QTextDocument search handles literal case-insensitive UTF-16 offsets; a temporary plain document adapts QLineEdit. Search failure/cancellation preserves cursor and text (REQ-REL-00228582).
INFERRED: Ctrl+F/F3/Shift+F3 target the receiving editor; shortcut-override events prevent parent actions from consuming them (REQ-FUNC-05f3481f).
INFERRED: Paste inserts clipboard text through native insert APIs for both menu and keyboard paths (REQ-FUNC-094a7552).
INFERRED: Non-normal echo modes use native Qt interaction; a reentrancy guard keeps the modal Find prompt from spawning another Find (REQ-SEC-ea6952c2).
### Files and test seams
INFERRED: ui/text_interaction.py, app.py, two existing page modules, ui_state_service.py, new shared tests and adjusted bootstrap/page tests.
INFERRED: Relevant tests cover context dispatch, live edit-state changes, keyboard focus and parent shortcuts, Unicode, clipboard/undo, dynamic dialogs and locale changes. Both guides and CHANGELOG.md document the commands.
### Risks and open decisions
OBSERVED: app startup tests use a QApplication fake; the new installer is injected there, while dedicated Qt tests exercise actual event filtering.
INFERRED: Clipboard content is not logged or persisted; disabled/masked controls retain protection. No project operation is started by navigation.
UNKNOWN: Platform-native clipboard formats beyond plain text are outside the accepted Paste contract.
### Requirement map
REQ-UX-0ceb3822: state-aware shared menus and app installation.
REQ-FUNC-439bbdcf: per-control literal wraparound search.
REQ-FUNC-05f3481f: focused keyboard dispatch.
REQ-FUNC-094a7552: native plain-text insertion.
REQ-REL-00228582: cancellation/no-match selection preservation.
REQ-SEC-ea6952c2: native masked-field behavior.
REQ-FUNC-82eb0f19: Chunking delegates to the shared controller.
REQ-UX-aa109e16: all new app-owned strings use the locale catalog.
Diagrams: [diagram_TASK-0e2636ed.md](diagram_TASK-0e2636ed.md).

## Log

- 2026-11-05 frame: journal opened
- 2026-11-05 frame: completed; next specify
- 2026-11-05 specify: completed; next design
- 2026-11-05 design: completed; next build
- 2026-11-05 build: red: uv run pytest -q tests/test_text_interaction.py exit 1; the new shared text_interaction API is absent (not a misspelled existing import). Functional contracts will run after introducing this module.
- 2026-11-05 build: red: bootstrap test exit 1; shared text interactions not installed at startup. Isolated offscreen controller contracts pass 20 cases; native Windows clipboard contention requires offscreen isolation for reliable Qt clipboard assertions.
- 2026-11-05 build: green: QT_QPA_PLATFORM=offscreen uv run pytest -q tests/test_text_interaction.py tests/test_app_entrypoint.py tests/test_text_chunking_page.py tests/test_characters_page.py tests/test_text_cleanup_page.py tests/test_localization_parity.py tests/test_operation_status_dialog.py tests/test_operation_status_button.py --tb=short --show-capture=no exit 0: 66 passed in 26.28s. Broader MainWindow lifecycle/localization selection was stopped to keep proof focused; no full suite. New-file code-style audit, changed-file audits and Ruff pass. Offscreen clipboard MIME ownership is released at fixture teardown to prevent a Windows test-exit crash; native operator clipboard is isolated.
- 2026-11-05 build: completed; next validate
- 2026-11-05 validate: DEVIATION validate: full suite omitted per standing user instruction; final proof uses focused offscreen Qt tests and direct integration checks. Native desktop clipboard behavior beyond Qt semantics is not part of this automated proof.
- 2026-11-05 validate: final: QT_QPA_PLATFORM=offscreen uv run pytest -q tests/test_text_interaction.py tests/test_app_entrypoint.py tests/test_text_chunking_page.py tests/test_characters_page.py tests/test_text_cleanup_page.py tests/test_localization_parity.py tests/test_operation_status_dialog.py tests/test_operation_status_button.py --tb=short --show-capture=no exit 0: 66 passed in 39.28s. Ruff src/tests, changed-file code-style/logging audits, direct new-file style audits and git diff --check exit 0. aegis check --task TASK-0e2636ed --strict exit 0, errors=0, warnings=18 (15 pre-existing repository records, 3 expected documentation-layout notices). Both reviews approved round 1. Full suite omitted per user; native desktop clipboard/manual GUI smoke not claimed. Knowledge and project context reconciled; environment/toolchain unchanged.
- 2026-11-05 validate: completed; next done

## Rulings


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-0e2636ed.md
changed: Meniuri text si cautare comune, integrare in aplicatie si ghiduri EN/RO; fara commit
evidence: 66 teste Qt relevante trecute; Ruff si audituri exit 0; ambele revizuiri aprobate
issues: Suita completa omisa la cererea utilizatorului; validare Qt izolata; avertismente AEGIS fara erori
spec_compliance: approved
implementation_quality: approved
review_round: 1

## Delivery report (2026-11-05)

- stage: validate; type: feature; path: full; branch: master
- requirements:
  - REQ-UX-0ceb3822 - Provide state-aware text context menus across desktop controls
  - REQ-FUNC-439bbdcf - Find literal text with per-control repeat and backward navigation
  - REQ-FUNC-05f3481f - Route text search shortcuts to the focused control
  - REQ-FUNC-094a7552 - Paste plain text through native editor validation and undo
  - REQ-REL-00228582 - Preserve text selection when search is cancelled or not found
  - REQ-SEC-ea6952c2 - Preserve native masked-field clipboard and search behavior
  - REQ-FUNC-82eb0f19 - The Text Chunking page shall provide preview find with context menus
  - REQ-UX-aa109e16 - Every app-owned operator-facing string on persistent windows, pages
- deviations: 1 recorded
  - validate: full suite omitted per standing user instruction; final proof uses focused offscreen Qt tests and direct integration checks. Native desktop clipboard behavior beyond Qt semantics is not part of this automated proof.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=1
- diff vs task base dac62e0: 26 file(s) changed, 1239 line(s) added
- checks: errors=0 warnings=18 notes=1
- checklist: 9/9 done
