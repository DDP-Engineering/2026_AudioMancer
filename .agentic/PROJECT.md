<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer — project rules

Project-specific rules that sit on top of the generic AEGIS workflow.
`.agentic/AGENTS.md` points here. Keeping the rules in this repository-owned
file means payload upgrades replace generic guidance without replacing these
project requirements.

## Where things are

| Thing | Path |
|---|---|
| Application source | `05_Software/AudioMancer/src/audiomancer/` |
| Tests | `05_Software/AudioMancer/tests/` |
| Code style (binding) | `01_Documentation/Code_Style.md` |
| Changelog | `CHANGELOG.md` (repo root) |
| User help files | `06_SoftwareDocu/UserGuide/`, `06_SoftwareDocu/UserGuide_ro/` |

Tests run through `uv` from the application directory; `aegis test` and
`aegis check --run` already carry the right command.

## Code style — mandatory

**Read `01_Documentation/Code_Style.md` before writing or changing any
code in this repository, and follow it.** It is the binding definition of
code style, documentation style and implementation readability for
AudioMancer: clear simple modules, no speculative abstraction, and
documented intent and contracts.

The `build` stage is not done until the code you wrote matches that
document, and the `deliver` diff review checks it explicitly.

## Delivery — the version workflow

A release changes the version in **four** places. Do them in this order,
in the delivery commit, and record the chosen version in the journal log.

1. **CHANGELOG.md** — turn the `## [Unreleased]` section into
   `## [X.Y.Z] - YYYY-MM-DD` and open a fresh empty `## [Unreleased]`
   above it. Every user-visible change of this release must be described
   there in user language, not commit language.
2. **The project** — two files, which must always agree:
   - `05_Software/AudioMancer/pyproject.toml` → `version = "X.Y.Z"`
   - `05_Software/AudioMancer/src/audiomancer/__init__.py` →
     `__version__ = "X.Y.Z"`
3. **The English help file** — `06_SoftwareDocu/UserGuide/index.html`,
   three occurrences: the `<title>AudioMancer User Guide vX.Y.Z</title>`,
   the **Help version** line and the **Application version** line.
4. **The Romanian help file** —
   `06_SoftwareDocu/UserGuide_ro/index.html`, three occurrences: the
   `<title>Ghid AudioMancer vX.Y.Z</title>`, **Versiune ajutor** and
   **Versiune aplicatie**.

Then verify nothing was missed. The release-version test is the authoritative
check: it reads the version from `pyproject.toml` and fails on any surface that
disagrees, naming the one that drifted.

```
cd 05_Software/AudioMancer && uv run pytest tests/test_package_import.py
```

To eyeball the surfaces by hand, scope the search to them. A repository-wide
grep is not a useful count, because task journals record the versions they
delivered and accumulate over time.

```
git grep -n "X\.Y\.Z" -- 05_Software/AudioMancer/pyproject.toml \
  05_Software/AudioMancer/src/audiomancer/__init__.py \
  05_Software/AudioMancer/uv.lock CHANGELOG.md \
  06_SoftwareDocu/UserGuide/index.html \
  06_SoftwareDocu/UserGuide_ro/index.html
# expect 10 hits: pyproject 1, __init__ 1, uv.lock 1, CHANGELOG 1, each guide 3
git grep -n "<previous>"       # the old version: expect none outside CHANGELOG.md
```

Help-file content is part of the release, not an afterthought: if this
release changed behavior a user can see, update the guide text in **both
languages** before bumping their version numbers. A version bump on a
guide whose text no longer matches the application is worse than no
bump at all.

## Delivery checklist additions

Add these to the deliver stage's "Done when" list for this repository:

- [ ] code follows `01_Documentation/Code_Style.md`
- [ ] `CHANGELOG.md` release section written in user language
- [ ] version identical in `pyproject.toml` and `__init__.py`
- [ ] both help files updated (text first, then the three version spots
      in each)
- [ ] `git grep` shows the new version 8 times and the old version only
      in `CHANGELOG.md` history
