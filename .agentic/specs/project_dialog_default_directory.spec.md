<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: Project Dialog Default Directory

Companion specification for the platform requirement covering how AudioMancer
resolves the per-user documents directory, and for the UX requirement covering
which folder the project create and open dialogs start in.

- Requirements: the `platform` set (per-user documents directory resolution) and
  the `ux` set (project dialog start directory).
- Affected files:
  - `05_Software/AudioMancer/src/audiomancer/config.py`
  - `05_Software/AudioMancer/src/audiomancer/ui/controllers/home_ui_controller.py`

## Behavior

### Directory ownership

Project dialogs use an operator documents directory when no project is open.
Projects are operator content and remain separate from packaged application
resources and the per-user application data root.

### Per-user documents directory resolution

A resolver returns the folder that project dialogs should start in. Candidates
are tried in order and the first *existing directory* wins:

1. **`XDG_DOCUMENTS_DIR`**, on POSIX platforms other than macOS, when set to a
   non-empty value. Expanded (`~`) and resolved. This honours a
   freedesktop.org user-dirs configuration that points documents somewhere other
   than `~/Documents`. It is skipped on Windows and macOS, where the variable has
   no meaning and any value found would be accidental.
2. **`~/Documents`**, on every platform. Windows has kept `Documents` as the
   on-disk folder name since Vista and localizes only its display name, so a
   plain probe is correct without Qt or `ctypes`. macOS uses the same path.
3. **The home directory**, as the final fallback.

Every candidate is required to be an existing directory. `QFileDialog` silently
falls back to the process working directory when handed a path that does not
exist, which would reintroduce an arbitrary and install-dependent start folder —
exactly the defect being fixed. The home directory is returned unconditionally at
the end: if even that is missing the process has larger problems, and the dialog
degrades to Qt's own default rather than raising during a UI callback.

The resolver is pure standard library — `sys.platform`, `os.environ`,
`pathlib`. `config` is imported by every module and by every headless test, so
it must not import PySide6, which also rules out
`QStandardPaths.DocumentsLocation`.

Resolution runs per call rather than at import time, so it reflects the
environment at the moment the dialog opens and stays monkeypatchable in tests.
Cost is one or two `is_dir()` probes.

### Dialog start directories

`handle_new_project_requested()` browses for the *parent* folder that will
contain the new project; `handle_open_project_requested()` browses for the
project folder itself. That asymmetry is existing, intentional behavior and is
preserved — only the no-project-open fallback changes:

| Dialog | Project open | No project open |
| --- | --- | --- |
| New project (select parent) | active project's parent folder | resolved documents root |
| Open project | active project root | resolved documents root |

The source-import, export, and snapshot dialogs already derive their defaults
from the open project and are untouched.

### Out of scope

No settings field records a last-used project parent, and neither dialog writes
settings. Within one session the already-open project still supplies the start
folder; across sessions the dialog starts at the documents root. Persisting the
last-used parent is a separate, larger change that would touch the settings
schema, its validation, and the settings UI.

The writable application data root, `settings.json` placement, and the `Logs/`
directory are owned by run `fix-2026-07-25T151844Z-85bc2369` and its
`user_data_location.spec.md`. Packaged resources stay under `config.APP_ROOT`.

## Data Structures

New `config` surface:

```python
def resolve_user_documents_root() -> Path: ...
```

Resolved locations:

| Platform | Documents root |
| --- | --- |
| Windows | `~\Documents`, falling back to `~` |
| macOS | `~/Documents`, falling back to `~` |
| Linux and other POSIX | `$XDG_DOCUMENTS_DIR`, falling back to `~/Documents`, then `~` |

## Examples

| Input | Expected result |
| --- | --- |
| Windows, `~\Documents` exists | `~\Documents` |
| Windows, `~\Documents` missing | `~` |
| Windows, `XDG_DOCUMENTS_DIR=D:\docs` set and existing | `~\Documents` — the variable is ignored off POSIX |
| macOS, `~/Documents` exists | `~/Documents` |
| Linux, `XDG_DOCUMENTS_DIR=/home/u/docs` set and existing | `/home/u/docs` |
| Linux, `XDG_DOCUMENTS_DIR` set to a missing path, `~/Documents` exists | `~/Documents` |
| Linux, `XDG_DOCUMENTS_DIR` set to whitespace | ignored; resolution continues to `~/Documents` |
| Linux, no documents folder anywhere | `~` |
| New-project dialog, project `/data/books/Book5` open | `/data/books` |
| New-project dialog, no project open | resolved documents root |
| Open-project dialog, project `/data/books/Book5` open | `/data/books/Book5` |
| Open-project dialog, no project open, app installed at `C:\Program Files\AudioMancer` | resolved documents root, never the install root |

## Acceptance

- [ ] `config` exposes `resolve_user_documents_root()` returning an absolute existing directory that is independent of `config.APP_ROOT`.
- [ ] The resolver returns the home documents folder when it exists, on Windows, macOS, and POSIX.
- [ ] On POSIX the resolver prefers an existing `XDG_DOCUMENTS_DIR` over the home documents folder.
- [ ] A blank, missing, or non-existent `XDG_DOCUMENTS_DIR` is ignored rather than returned.
- [ ] `XDG_DOCUMENTS_DIR` is ignored on Windows and macOS.
- [ ] The resolver returns the home directory when no candidate documents folder exists.
- [ ] The new-project dialog opens at the active project's parent folder when a project is open, and at the resolved documents root otherwise.
- [ ] The open-project dialog opens at the active project root when a project is open, and at the resolved documents root otherwise.
