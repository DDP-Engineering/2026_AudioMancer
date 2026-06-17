<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AGENTS.md - AudioMancer

Guidance for Codex, Claude Code, and other AI agents in this repository.

## Scope

These instructions apply to the repository rooted at:
`2026_AudioMancer/`

A deeper `AGENTS.md` overrides this file for its subtree.

## Agentic Development Workflow

This repository uses a manual, human-steered agentic development workflow.
When the user asks to implement a feature, fix a bug, or change behavior:

1. Start or resume an `.agentic` run.
2. Complete only one workflow gate at a time.
3. Keep intent/spec, checks/tests, source implementation, validation, and
   delivery as separate steps.
4. Stop after each gate with a concise summary and next prompt options.

Use the project-local wrappers when available:

```text
.\.agentic\tools\run.ps1 <command>
bash .agentic/tools/run.sh <command>
```

If the workflow package is installed in the active environment,
`agentic-workflow` or `python -m agentic_workflow` may also be used.

## Repository Rules

- Treat this repository as independent.
- Prefer implementation work under `04_Software/`.
- Keep folder boundaries clear across planning, documentation, tools,
  software, software documentation, delivery, and support material.
- Do not add subtree-level `AGENTS.md` files unless explicitly requested.
- Keep the project offline-first unless an online dependency is explicitly
  required and approved.
- Preserve public interfaces unless change is explicitly requested.

## Durable Requirements Contract

- Long-lived requirements live under `.agentic/requirements/`, one Markdown
  register per requirement type.
- The active run graph under `.agentic/runs/` records one workflow run; the
  requirement registers describe durable project behavior.
- Every behavior change starts by checking impact against existing requirement
  rows before implementation code is written.
- New requirement rows start as `Planned` and become `Active` only when a
  linked test exists and passes, or when an explicit manual verification method
  is documented.
- Preserve `Created On` for existing requirements. Set it only when a new
  requirement ID is introduced.
- Update `Last Updated` only when that requirement row is materially changed.
- Link each active requirement to exact test identifiers when practical.
- When adding or changing tests, cite relevant requirement IDs in comments,
  docstrings, or test names where practical.
- New source files under configured `coverable_roots` need a file-level
  requirement row naming the file in `Related Components` and a linked check,
  unless the file is listed in `.agentic/requirements/coverage_waivers.txt`.
- Waivers are a legacy baseline only. Remove stale waivers once a module is
  covered or deleted.
- When requirements are added or updated, state the changed requirement IDs in
  the final summary.

## Component Documentation Contract

- New software components require a new or updated component document under
  `05_SoftwareDocu/`.
- Material changes to a component's behavior, contracts, responsibilities, data
  formats, dependencies, or workflow integration require updating the matching
  `05_SoftwareDocu/*.md` document in the same change.
- Component documents must follow
  `05_SoftwareDocu/component_documentation_template.md`.
- When adding a new component page, update `05_SoftwareDocu/README.md` in the
  same change.
- Component documentation complements requirements and tests. It does not
  replace durable requirement rows or linked verification.

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

## Required Order

1. Intake: classify request, inspect current requirements, and ask clarifying
   questions.
2. Requirement: create or update minimal spec items and durable requirement
   rows.
3. Check: create checks/tests that cite spec/requirement IDs and fail first.
4. Implementation: edit source and required component documentation until
   checks pass.
5. Validation: run deterministic gates, documentation review, code-style
   review, and read-only scope review.
6. Delivery: run preflight and ask before PR, push, merge, or publish.

## Working Rules

- Prefer simple, maintainable solutions.
- Avoid unnecessary abstraction and speculative architecture.
- Make changes incrementally.
- Update documentation in the same change when behavior or contracts change.
- When changing any operator-facing UI text, labels, titles, buttons, menu
  entries, page names, or dialog content, update the runtime UI translation
  mechanism in the same change so the interface remains language-complete.
- Keep repository instructions in `AGENTS.md` and broad style rules in
  documentation files.
- Do not edit specs during implementation unless the human routes back to the
  requirement stage.
- Do not edit tests during implementation unless the human routes back to the
  check stage.
- Do not weaken or delete tests to make implementation pass.

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
- Do not push, create a PR, merge, or publish until delivery preflight passes
  and the human explicitly approves that action.

## Validation Rules

For Python changes, run at minimum:

- `python -m py_compile <changed_file.py>`

For the `04_Software/AudioMancer/` application subtree, prefer `uv run ...`
for Python-based validation and test commands when the project environment is
managed by `uv`.

Examples:

- `uv run python -m py_compile <changed_file.py>`
- `uv run pytest tests/<targeted_test>.py`

Code quality: run after every set of Python changes inside
`04_Software/AudioMancer/`:

```powershell
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

Ruff is already configured in `pyproject.toml` (`line-length = 120`,
`target-version = "py312"`). Remaining `E501` warnings on long inline string
literals in tests are accepted and may be ignored. Prefer changed-file `ruff`
runs during normal feature work to avoid unrelated formatting churn. Run
full-tree `ruff` passes only for one intentional repository-wide cleanup or
baseline normalization change.

When behavior changes:

- add or update targeted tests
- prefer focused tests before broad runs
- state what was validated and what remains unverified

Use `04_Software/AudioMancer/tests/` for local logic and focused integration
coverage.

## Documentation Rules

- Update `README.MD` when module scope or behavior changes.
- Keep README files scoped by location:
  - the repository-root `README.MD` is a concise product and repository
    overview for first-time readers
  - folder-level README files describe only what is in that folder, where to
    find the next layer of detail, and how to use that folder
  - application README files may include local setup, run, validation, and
    packaging entry points
  - detailed behavior, internal workflow contracts, artifact formats, and
    component-specific implementation notes belong in `05_SoftwareDocu/`,
    `HowToTest*.md`, `CHANGELOG.md`, or the relevant planning document, not
    duplicated across multiple README files
- Do not write the current application version in README files. Keep README
  files simple and refer version-sensitive readers to the changelog, project
  version metadata, and help-file versioning so help files can be kept in sync
  with the project without forcing broad README churn on fast revisions.
- Update `05_SoftwareDocu/` when implementation behavior or contracts change.
- Update `HowToTest*.md` when setup, validation, or operator workflow changes.

## Safety Rules

- Do not commit secrets, tokens, keys, `.env` files, or credential stores.
- Do not report work complete while `agentic-workflow audit traceability` or
  `agentic-workflow audit coverage` has blocking findings.
- Do not consider work complete until implementation, relevant documentation,
  tests, py-compile, ruff check, ruff format, and final validation reporting are
  complete or explicitly reported as blocked/not applicable.

## Stage Stop Format

End each workflow gate with:

```text
Stage: <stage>
Artifacts changed: <paths or none>
Evidence: <ids and short results>
Invariant status: <pass/fail summary>
Traceability status: <audit/impact summary>
Documentation status: <component docs/audit summary>
Needs human: <questions or approval needed>
Next prompt options:
- Continue to <next stage>
- Revise <specific artifact>
- Abort or park this run
```
