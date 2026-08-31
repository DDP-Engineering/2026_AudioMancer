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
  parent        optional top-level TASK-id; blank for an ordinary task
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

# TASK-424ee4c6 — Repair Windows Qt DLL startup in portable bundle

stage: done
type: fix
path: full
requirements: REQ-PLAT-c9c8f2b1
parent:
branch: master
base: b7cefcf3600af33ca0c4f0f6992911c2d6e3dfe0
opened: 2026-08-31

## Done checklist (current stage)

- [x] The root cause, package repair, focused checks, archive integrity, and manual startup observations are recorded.
- [x] The operator explicitly excluded a full-suite rerun and manually confirmed the final Windows ZIP starts.
- [x] The operator approved delivery closure; no agent commit or push was performed.
- [x] `stage: done`

## Log

- 2026-08-31 frame: Scope is to repair the Windows portable bundle so its bundled Qt runtime loads before AudioMancer imports; diagnosis, packaging-script/spec/runtime-hook changes, focused regression tests, and a rebuilt Windows archive are in scope.
- 2026-08-31 frame: Excluded are application feature changes, Linux packaging changes, version changes, full-suite execution, commits, pushes, and release publication.
- 2026-08-31 frame: Full path is required because no existing requirement covers deterministic bundled-DLL startup and the repair needs a new independently verifiable platform requirement.
- 2026-08-31 frame: The task remains on `master` because the user previously directed the same branch; no commit or push is authorized.
- 2026-08-31 frame: Proposed requirement REQ-PLAT-c9c8f2b1 requires the frozen Windows executable to register its bundled Qt DLL directory before application imports and be verified by a focused packaging/runtime inspection.
- 2026-08-31 frame: The user approved the scoped Windows startup repair and continuation under the existing same-branch, no-commit/no-push authority.
- 2026-08-31 specify: REQ-PLAT-c9c8f2b1 defines one frozen-startup behavior with an automated hook seam and a manual rebuilt-archive startup inspection.
- 2026-08-31 specify: `aegis check` will be run after the new requirement is completed; no existing requirement owns the new runtime-hook behavior.
- 2026-08-31 design: A PyInstaller runtime hook will retain an os.add_dll_directory handle for `_MEIPASS/PySide6`, then the spec will register that hook before the entrypoint import. [REQ-PLAT-c9c8f2b1]
- 2026-08-31 design: The hook exposes a small callable for focused tests and returns without mutation outside a frozen Windows runtime; no persistent data or public application interface changes. [REQ-PLAT-c9c8f2b1]
- 2026-08-31 design: Rejected alternative: copying additional Qt DLLs into the package root, because it duplicates version-sensitive binaries rather than making the intended PySide6 directory deterministic. [REQ-PLAT-c9c8f2b1]
- 2026-08-31 design: Test seam is a mocked `os.add_dll_directory` with a frozen `_MEIPASS` path; expected files are the runtime hook, PyInstaller spec, and focused test. [REQ-PLAT-c9c8f2b1]
- 2026-08-31 design: Release_Packaging has no `## Architecture` diagram and this is an internal startup-path addition, so no knowledge-diagram revision is owed.
- 2026-08-31 build red: command=`05_Software/AudioMancer/.venv/Scripts/python.exe -m pytest -q tests/test_windows_runtime_hook.py`; exit=1; expected missing behavior=the PyInstaller runtime hook file does not exist, so no bundled PySide6 DLL directory can be registered.
- 2026-08-31 build: Added the PyInstaller runtime hook, registered it before the application entrypoint, and confirmed the focused test plus Ruff pass.
- 2026-08-31 build: Rebuilt the official Windows archive; PyInstaller reported the custom runtime hook included and ZIP integrity verified with 426 entries.
- 2026-08-31 build: Manual packaged-runtime observation: extracted the rebuilt ZIP, started AudioMancer.exe with QT_QPA_PLATFORM=offscreen, observed PID 35220 remain alive for eight seconds without the QtGui DLL dialog, then stopped that test process.
- 2026-08-31 build: `aegis test --impacted --base HEAD` expanded into unrelated staged UI tests and its final output was not retained by the host; the user excludes a full-suite rerun, so focused test, lint, package-integrity, checksum, and offscreen-startup evidence are retained instead.
- 2026-08-31 build: `aegis check --task TASK-424ee4c6` reported zero errors and 406 accepted warnings, dominated by pre-existing unrelated work, old open journals, and the generated diagnostic extraction that the host blocked from deletion.
- 2026-08-31 build: Root-cause comparison proved Book Analysis does not execute before the failing unchanged QtGui import; the 2.0 and failing 2.1 bundles carry byte-identical Qt DLLs, but only the failing bundle collected `icuuc.dll` and `icudt78.dll` from the Codex Poppler runtime on PATH.
- 2026-08-31 build: Rejected the first runtime-hook attempt after it reproduced the failure; the durable repair filters Codex runtime directories from PATH only while PyInstaller collects release binaries, preventing host ICU DLLs from entering the ZIP.
- 2026-08-31 build: Manual packaged-runtime observation: the rebuilt ZIP contains neither conflicting ICU DLL, passes ZIP integrity and SHA-256 verification, and its normally started AudioMancer.exe displayed the main window title before its test process was stopped.
- 2026-08-31 build: `aegis check --task TASK-424ee4c6` reported zero errors and 1 manual-verification note; accepted warnings are generated diagnostic bundles, a manual-only packaging requirement without a unit test, and pre-existing unrelated work and journals.
- 2026-08-31 build: User manually extracted the final Windows ZIP and confirmed that AudioMancer started successfully.
- 2026-08-31 deliver: The operator approved closure and requested staging for a user-owned commit; no agent commit or push was performed.

## Rulings

<!-- Append decisions here; never edit history. Supersede with a new ruling.
- RULING-001 | date=YYYY-MM-DD | decision=<decision> | reason=<reason> | source=user | supersedes=none
source: user | repository | requirement | technical
-->

## Handoff

<!-- Replace these fields with the latest minimal resume snapshot.
status: ready | waiting | blocked
-->

current: done
status: ready
next: None.
must_read: .agentic/requirements/platform/REQ-PLAT-c9c8f2b1.toml; 02_Tools/package_windows_release.ps1; .agentic/knowledge/Release_Packaging.md
blockers: None; the full-suite and repeat impacted-suite evidence remain intentionally excluded by user instruction.

## Stage report

stage: done
result: completed
current: done
changed: Replaced an ineffective runtime-hook attempt with Windows packager PATH sanitization, then rebuilt the Windows ZIP and checksum.
evidence: The old 2.0 archive starts on this host; the failing 2.1 archive starts after only the injected ICU DLLs are removed; the final ZIP omits those DLLs, passes integrity and checksum verification, displays the normal AudioMancer main window, and was manually started successfully by the user.
issues: The impacted runner expanded into unrelated staged UI tests and its final result was not retained; the user excludes full-suite reruns. Generated diagnostic extractions remain because the host blocked deletion.
next: None.
needs_user: The staged delivery record awaits the operator's user-owned commit; no agent commit or push was performed.
spec_compliance: disabled
implementation_quality: disabled
review_round: 1
