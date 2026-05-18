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

## GitHub Delivery Rules

- Do not commit generated delivery archives, such as Windows or Linux zip files,
  into the Git repository.
- Publish delivery archives only through GitHub Releases for
  `DDP-Engineering/2026_AudioMancer`.
- When publishing a delivery archive, update or replace the relevant GitHub
  Release asset so only the current delivery archive is attached for that
  platform.
- If a GitHub deployment record is needed, update the deployments page to point
  at the current commit SHA and keep only the current deployment entry.
- If useful for operators, update release notes or README text with the current
  delivery SHA and a short description of the package contents, but do not mix
  unrelated code changes into the delivery-only publish.
- A delivery-only publish must stage and push only release metadata or
  documentation explicitly needed for the delivery record; application code,
  prompt files, tests, and generated archives must not be committed as part of
  that publish unless the user explicitly requests it.

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
- Do not write the current application version in README files. Keep README
  files simple and refer version-sensitive readers to the changelog, project
  version metadata, and help-file versioning so help files can be kept in sync
  with the project without forcing broad README churn on fast revisions.
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






