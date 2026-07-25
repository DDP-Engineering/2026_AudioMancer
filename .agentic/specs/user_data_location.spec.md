<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: Writable Application Data Location

Companion specification for the platform requirements covering where AudioMancer
stores writable per-user data, and for the non-functional requirement that
logging initialization can never abort application startup.

- Requirements: the `platform` set (writable data root resolution; settings and
  log placement; bundled default settings seeding) and the `non_functional` set
  (non-fatal logging initialization).
- Affected files:
  - `04_Software/AudioMancer/src/audiomancer/config.py`
  - `04_Software/AudioMancer/src/audiomancer/services/logging_service.py`
  - `04_Software/AudioMancer/src/audiomancer/services/settings_service.py`
  - `04_Software/AudioMancer/src/audiomancer/app.py`

## Behavior

### The problem

`config.APP_ROOT` is the root that owns *packaged* resources: `prompts/`,
`help/`, `LICENSE*.txt`, `pyproject.toml`. Two pieces of *writable* runtime data
were derived from it as well:

- `APP_SETTINGS_PATH = APP_ROOT / "settings.json"`
- the application log directory, `APP_ROOT / "Logs"`

For a frozen build installed into `C:\Program Files\AudioMancer` or a
system-wide Linux prefix, that root is not writable by the running user.
`initialize_logging()` calls `log_directory.mkdir(parents=True, exist_ok=True)`
and then `logging.FileHandler(...)`, and `app.main()` calls it *before* its
`try/except`, so the resulting `OSError` aborted startup with a bare traceback
and no log file to diagnose it from. The application therefore only worked when
run from source or from a writable portable folder.

### Writable data root resolution

A single resolver decides once, at `config` import time, which folder owns
writable data. Candidates are tried in order and the first usable one wins:

1. **Explicit override.** The `AUDIOMANCER_DATA_DIR` environment variable, when
   set to a non-empty value. Expanded (`~`) and resolved. This is the escape
   hatch for portable installs, CI, and operators who want data on another
   volume. It is never validated for writability: an explicit instruction is
   honoured, and a bad value surfaces as a normal settings or logging error
   rather than being silently ignored.
2. **Portable: the application root, when it accepts writes.** This preserves
   today's behaviour exactly for source-tree runs, developer runs, and portable
   ZIP installs — settings and logs stay next to the application. Excluded from
   this branch is the PyInstaller `_MEIPASS` extraction directory: it is
   writable but temporary, so selecting it would silently discard settings on
   every exit.
3. **Per-user OS data location.** Used when the application root is not
   writable.

Writability is decided by an actual probe file created and removed inside the
candidate directory, not by `os.access(path, os.W_OK)`. On Windows `os.access`
only reflects the read-only attribute and ignores directory ACLs, so it reports
`C:\Program Files` as writable and would defeat the whole fix.

The resolver is pure standard library — `sys.platform`, `os.environ`,
`pathlib`, `tempfile`. `config` is imported by every module and by every
headless test, so it must not import PySide6. Qt's
`QStandardPaths.AppDataLocation` is also unusable here: it appends
`QCoreApplication::applicationName`, which is still empty at the moment `config`
is first imported during bootstrap.

### Settings placement and seeding

`APP_SETTINGS_PATH` moves to the resolved data root. The app-root
`settings.json` keeps its own name, `APP_DEFAULT_SETTINGS_PATH`, and becomes a
read-only bundled default. It is still a valid runtime-resource marker for
`_has_runtime_resource_markers()`, and it is never written to.

`APP_ROOT/settings.json` is the correct seed source in both layouts that matter:

- In a **packaged build** it is the scaffold the installer places beside the
  executable. `02_Tools/package_linux_release.sh` copies the developer's
  `settings.json` into the delivery staging directory with operator API keys and
  the runtime discovery cache stripped out.
- In a **source or portable tree** it is the operator's own live settings file
  (it is gitignored, so it is local state rather than a committed artifact). When
  that root is writable the active and bundled paths coincide and no seeding
  happens; when a previously-portable install becomes read-only, seeding from it
  is exactly the migration that preserves the operator's configuration.

`settings.example.json` is explicitly **not** a seed source. It is committed
documentation carrying placeholder values — `YOUR_LMSTUDIO_HOST`,
`REPLACE_WITH_YOUR_API_KEY`, two example AI profiles — and seeding from it would
hand a fresh installation two unusable AI profiles. It stays a reference file
only.

When the active settings file does not exist, `ensure_settings_file()` seeds it:

- If the active path *is* the bundled path (the portable and source-tree case),
  there is nothing to seed from — use `build_default_settings()`.
- Otherwise read the bundled default. If it is readable, valid JSON, and a JSON
  object, validate it and use that as the seed. This is what migrates an
  existing installation: the settings the operator already had become the
  starting point of their per-user copy.
- On any failure (missing, unreadable, malformed, not an object) fall back to
  `build_default_settings()`.

The seeded payload is written to the active per-user path.

### Non-fatal logging initialization

`initialize_logging()` returns `Path | None` and never raises on a filesystem
error. It installs the console handler first, so a diagnostic is always
reachable, then attempts the file handler:

- `mkdir` failure or `FileHandler` failure leaves the root logger with the
  console handler only, emits one `logging-degraded` warning naming the path and
  the underlying error, and returns `None`.
- Retention cleanup (`_cleanup_old_log_files`) tolerates filesystem errors: a
  directory it cannot list, or a file it cannot `stat` or `unlink`, must not
  prevent the run from logging.

`app.main()` accepts `None` and reports the log file as unavailable in its
bootstrap-failure message rather than interpolating `None`.

### Out of scope

Read-only packaged resources stay under `APP_ROOT`. Project workspaces and
per-project artifacts are already operator-chosen paths and are untouched. The
settings schema, defaults, validation rules and settings UI are unchanged, as
are log format, level and retention policy. The `APP_ROOT` default directory
offered by the project open/create dialogs is unchanged.

## Data Structures

Resolved per-user locations, when the application root is not writable:

| Platform | Data root |
| --- | --- |
| Windows | `%LOCALAPPDATA%\AudioMancer`, falling back to `%APPDATA%\AudioMancer`, then `~\AppData\Local\AudioMancer` |
| macOS | `~/Library/Application Support/AudioMancer` |
| Linux and other POSIX | `$XDG_DATA_HOME/AudioMancer`, falling back to `~/.local/share/AudioMancer` |

Resulting layout under the resolved data root:

```text
<data root>/
  settings.json
  Logs/
    AudioMancer_<YYYYMMDD>_<HHMMSS>.log
```

New `config` surface:

```python
APP_DATA_DIR_ENVIRONMENT_VARIABLE = "AUDIOMANCER_DATA_DIR"

def resolve_user_data_root(app_root: Path | None = None) -> Path: ...

APP_USER_DATA_ROOT: Path        # resolved writable data root
APP_DEFAULT_SETTINGS_PATH: Path # APP_ROOT / "settings.json", read-only bundled default
APP_SETTINGS_PATH: Path         # APP_USER_DATA_ROOT / "settings.json", active
```

Changed `logging_service` surface:

```python
def initialize_logging() -> Path | None: ...  # None means console-only
```

## Examples

| Input | Expected result |
| --- | --- |
| `AUDIOMANCER_DATA_DIR=D:\AM-data`, any platform | data root is `D:\AM-data`; settings at `D:\AM-data\settings.json` |
| `AUDIOMANCER_DATA_DIR=""` (empty or whitespace) | override ignored; resolution continues to the next candidate |
| Run from the source tree (writable app root) | data root is the app root; `APP_SETTINGS_PATH == APP_DEFAULT_SETTINGS_PATH`; unchanged from today |
| Portable ZIP extracted to `D:\Apps\AudioMancer` | data root is `D:\Apps\AudioMancer` |
| Installed at `C:\Program Files\AudioMancer` (not writable), `LOCALAPPDATA=C:\Users\u\AppData\Local` | data root is `C:\Users\u\AppData\Local\AudioMancer` |
| Installed at `/opt/audiomancer` (not writable), `XDG_DATA_HOME` unset | data root is `~/.local/share/AudioMancer` |
| Installed at `/opt/audiomancer` (not writable), `XDG_DATA_HOME=/home/u/.share` | data root is `/home/u/.share/AudioMancer` |
| macOS bundle in `/Applications` (not writable) | data root is `~/Library/Application Support/AudioMancer` |
| PyInstaller onefile, `APP_ROOT` inside `_MEIPASS` (writable temp) | `_MEIPASS` rejected; per-user location used |
| First run, no active settings file, bundled default readable and valid | active file created from the bundled payload; bundled file unmodified |
| First run, bundled default is malformed JSON | active file created from `build_default_settings()` |
| Log directory cannot be created | `initialize_logging()` returns `None`; root logger has the console handler only; one `logging-degraded` warning emitted |
| `logging.FileHandler` raises `OSError` | same as above |
| `initialize_logging()` returned `None` | `app.main()` completes normally; a bootstrap failure reports the log file as unavailable |

## Acceptance

- [ ] `AUDIOMANCER_DATA_DIR` overrides the resolved data root ahead of every other candidate, on every platform.
- [ ] A writable application root resolves to itself, keeping source-tree and portable paths unchanged.
- [ ] A non-writable application root resolves to the documented per-user location on Windows, macOS and Linux.
- [ ] A writable `_MEIPASS` extraction directory is never selected as the data root.
- [ ] `config.APP_SETTINGS_PATH` and the application log directory both derive from the resolved data root.
- [ ] Writability is determined by a real probe file, not `os.access`.
- [ ] `initialize_logging()` returns `None` and installs a console-only root logger instead of raising when the log directory or log file cannot be opened.
- [ ] Log retention cleanup does not propagate filesystem errors.
- [ ] `app.main()` completes its bootstrap when `initialize_logging()` returned `None`.
- [ ] A missing active settings file is seeded from the bundled default when it differs and is usable, and from `build_default_settings()` otherwise; the bundled file is never written.
- [ ] `config` exposes the bundled default settings path separately from the active settings path.
- [ ] The frozen-bundle resource contract still resolves prompts, help, licences and version from the bundle root.
