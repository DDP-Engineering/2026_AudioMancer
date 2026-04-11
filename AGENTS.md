<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AGENTS.md - AudioMancer

## Scope

These instructions apply to the repository rooted at:
`2026_AudioMancer/`

A deeper `AGENTS.md` overrides this file for its subtree.

## Repository Rules

- Treat this repository as independent.
- Prefer implementation work under `04_Software/`.
- Keep folder boundaries clear across planning, documentation, tools,
  software, software documentation, delivery, and support material.
- Do not add subtree-level `AGENTS.md` files unless explicitly requested.
- Keep the project offline-first unless an online dependency is explicitly
  required and approved.

## Style Rules

Code style and Python documentation style are defined in:
`01_Documentation/Code_Style.md`

Follow that file for implementation and documentation conventions.

When changing the implementation of a function, method, or documented nested
helper, update that callable's local `@version` tag in its documentation block
in the same change.

When adding or removing a function, method, class, or documented nested helper
from a Python file, update the file-level `@version` tag in that file's module
documentation header in the same change.

## Working Rules

- Prefer simple, maintainable solutions.
- Avoid unnecessary abstraction and speculative architecture.
- Make changes incrementally.
- Update documentation in the same change when behavior or contracts change.
- Preserve public interfaces unless change is explicitly requested.
- When changing any operator-facing UI text, labels, titles, buttons, menu
  entries, page names, or dialog content, update the runtime UI translation
  mechanism in the same change so the interface remains language-complete.
- Keep repository instructions in `AGENTS.md` and broad style rules in
  documentation files.

## Validation Rules

For Python changes, run at minimum:

- `python -m py_compile <changed_file.py>`

For the `04_Software/AudioMancer/` application subtree, prefer `uv run ...`
for Python-based validation and test commands when the project environment is
managed by `uv`.

Examples:

- `uv run python -m py_compile <changed_file.py>`
- `uv run pytest tests/<targeted_test>.py`

**Code quality — run after every set of Python changes inside `04_Software/AudioMancer/`:**

```powershell
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

Ruff is already configured in `pyproject.toml` (`line-length = 120`, `target-version = "py312"`).
Remaining `E501` warnings on long inline string literals in tests are accepted and may be ignored.
Prefer changed-file `ruff` runs during normal feature work to avoid unrelated formatting churn.
Run full-tree `ruff` passes only for one intentional repository-wide cleanup or baseline normalization change.

When behavior changes:

- add or update targeted tests
- prefer focused tests before broad runs
- state what was validated and what remains unverified

Use:

- `tests/` for local logic and focused integration coverage

## Documentation Rules

- Update `README.MD` when module scope or behavior changes.
- Update `05_SoftwareDocu/` when implementation behavior or contracts change.
- Update `HowToTest*.md` when setup, validation, or operator workflow changes.

## Completion Rules

Do not consider work complete until all applicable items below are satisfied:

- implementation changes are finished
- relevant documentation is updated in the same change
- relevant tests are added or updated for behavior changes
- `python -m py_compile <changed_file.py>` has been run for each changed Python file
- `uv run ruff check <changed_python_files> --fix` has been run and output reviewed
- `uv run ruff format <changed_python_files>` has been run
- the final summary states what changed, what was validated, and what remains unverified






