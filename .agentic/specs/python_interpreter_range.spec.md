<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: Supported Python Interpreter Range

Companion specification for the platform requirements covering which Python
interpreters AudioMancer supports and the removal of the last stdlib blocker.

- Requirements: the `platform` set (no removed-stdlib dependency; declared
  interpreter range).
- Affected file: `04_Software/AudioMancer/pyproject.toml`

## Behavior

`audioop` was removed from the standard library in Python 3.13 with no stdlib
replacement. AudioMancer used it for every PCM conversion in Audio Assembly and
Scene Mix, so the package pin `requires-python = ">=3.12,<3.13"` was the only
thing preventing a hard `ModuleNotFoundError` at import time.

Once PCM conversion is served by the internal codec, that blocker is gone and the
declared interpreter range widens to include 3.13. The upper bound stays
exclusive so a future interpreter is an explicit decision rather than an
accident.

The application must import and run its Audio Assembly and Scene Mix paths on
both 3.12 and 3.13, and the configured test and lint gates must pass on both.

### Out of scope

No dependency version is changed by this contract. Widening the interpreter
range does not imply support for Python 3.14; that upper bound remains excluded
pending its own validation.

## Data Structures

The declared range in `pyproject.toml`:

```toml
requires-python = ">=3.12,<3.14"
```

Ruff's `target-version` stays at the lowest supported interpreter, so lint keeps
flagging syntax that would break on 3.12:

```toml
[tool.ruff]
target-version = "py312"
```

## Examples

| Input | Expected result |
| --- | --- |
| `import audiomancer.services.audio_assembly_service` on Python 3.13 | imports cleanly; no `ModuleNotFoundError: No module named 'audioop'` |
| `grep -r "import audioop" src/` | no matches |
| Test gate on Python 3.12 | passes |
| Test gate on Python 3.13 | passes, with the differential parity test reported as skipped |
| Lint gate on both interpreters | passes |
| Installing on Python 3.14 | rejected by the `<3.14` bound |

## Acceptance

- [ ] `requires-python` is `>=3.12,<3.14`.
- [ ] No module under `04_Software/AudioMancer/src` imports `audioop`.
- [ ] The configured test and lint gates pass on Python 3.12.
- [ ] The configured test and lint gates pass on Python 3.13.
- [ ] Ruff `target-version` remains `py312`.
