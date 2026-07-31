<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Agentic Components Configuration

This document explains `.agentic/components.toml`, the component manifest used
by the agentic workflow during existing-project adoption and component baseline
checks.

The manifest is intentionally human-approved. Agents may propose entries, but
component boundaries should represent real ownership, responsibility, and
verification boundaries in the repository.

## Mental Model

`components.toml` answers these questions:

- Which repository paths belong to each component?
- Which tests or checks verify that component?
- How critical is the component?
- Is the component adopted enough for behavior-changing work?
- Are related components approved to move together as a bundle?

The workflow reads the manifest through the path configured in
`.agentic/workflow.toml`:

```toml
[components]
manifest = ".agentic/components.toml"
```

Commands that read the manifest include:

- `<workflow> adoption component-status`
- `<workflow> adoption scope-check <path>`
- `<workflow> adoption baseline`
- `<workflow> verify invariants`
- `<workflow> verify working-tree`

## File Shape

The file has two top-level tables:

```toml
[components]

[bundles]
```

Each component is a nested table under `[components]`. Each bundle is a nested
table under `[bundles]`.

An empty manifest is valid:

```toml
[components]

[bundles]
```

With an empty manifest, paths are not mapped to components. Adoption commands
can still run, but component baseline checks cannot protect behavior-changing
work by component boundary until entries are added.

## Component Fields

Example component:

```toml
[components.storage]
paths = [
  "src/package/storage/**",
  "tests/storage/**"
]
tests = [
  "tests/storage/test_repository.py"
]
criticality = "high"
adoption_status = "baseline-usable"
owner = "platform"
notes = "Owns durable data access and migration behavior."
```

Fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `paths` | Recommended | Repository-relative glob patterns owned by the component. |
| `tests` | Recommended | Tests, checks, or test roots associated with the component. |
| `criticality` | Optional | Human severity hint, commonly `low`, `medium`, or `high`. |
| `adoption_status` | Optional | Current adoption baseline level. Defaults to `unknown` when omitted. |
| `owner` | Optional | Team, role, or maintainer label. |
| `notes` | Optional | Short human context for boundaries, risks, or special handling. |

Path matching uses normalized forward slashes. Prefer patterns such as
`src/package/storage/**` over operating-system-specific separators.
A bare directory path such as `src/package/storage` owns that directory and its
entire subtree, using the same tree-root semantics as configured stage paths. An
explicit `src/package/storage/**` pattern remains supported. Matching retains
Python `fnmatch` semantics, so `*` can cross `/`; use deliberate component
boundaries and verify them with `adoption scope-check`.

## Adoption Status Levels

The workflow compares status levels in this order:

| Status | Meaning |
| --- | --- |
| `unknown` | The component boundary is not understood yet. |
| `discovered` | The component has been found and roughly mapped. |
| `characterized` | Responsibilities, paths, risks, and checks are described. |
| `baseline-usable` | The component has enough requirements, tests, and documentation for normal behavior-changing work. |
| `baseline-strict` | The component has stronger-than-default coverage or review expectations. |

The minimum status required before behavior-changing work is configured in
`.agentic/workflow.toml` by the component baseline guard:

```toml
[components.baseline_guard]
mode = "enforce"
minimum_completion_level = "baseline-usable"
```

If a run records changes to a mapped component below that level, the component
baseline invariant (`INV-9`) can block delivery until adoption is completed or
scope is revised. When the guard is `disabled`, the level is not enforced.

## Bundle Fields

Bundles let a human approve related components as one adoption unit.

```toml
[bundles.identity-flow]
components = ["auth", "profile", "session"]
reason = "These components share request context and cannot be adopted independently."
adoption_status = "baseline-usable"
approved = true
```

Fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `components` | Yes | Component names included in the bundle. |
| `reason` | Recommended | Why these components should move together. |
| `adoption_status` | Optional | Bundle-level status. |
| `approved` | Optional | Whether the bundle has human approval. Defaults to `false` when omitted. |

Bundle rules:

- A bundle should name only components that exist in `[components]`.
- A bundle only helps satisfy baseline checks when `approved = true`.
- Bundle size is limited by `[adoption].max_bundle_components` in
  `workflow.toml`.
- Bundles are rejected when `[adoption].allow_component_bundles = false`.

## Minimal Example

```toml
[components]

[components.api]
paths = ["src/package/api/**", "tests/api/**"]
tests = ["tests/api"]
criticality = "medium"
adoption_status = "baseline-usable"
owner = "application"
notes = "Owns public request and response behavior."

[components.worker]
paths = ["src/package/worker/**", "tests/worker/**"]
tests = ["tests/worker"]
criticality = "high"
adoption_status = "characterized"
owner = "application"
notes = "Owns asynchronous job execution."

[bundles]
```

In this example, behavior-changing work under `src/package/api/**` can proceed
when the required baseline is `baseline-usable`. Behavior-changing work under
`src/package/worker/**` should route through adoption first because the worker
component is only `characterized`.

## Bundle Example

```toml
[components]

[components.importer]
paths = ["src/package/importer/**", "tests/importer/**"]
tests = ["tests/importer"]
criticality = "medium"
adoption_status = "characterized"
owner = "data"
notes = "Reads external files and normalizes records."

[components.validator]
paths = ["src/package/validator/**", "tests/validator/**"]
tests = ["tests/validator"]
criticality = "medium"
adoption_status = "characterized"
owner = "data"
notes = "Validates normalized records before persistence."

[bundles.ingestion]
components = ["importer", "validator"]
reason = "Importer and validator share the same input contract."
adoption_status = "baseline-usable"
approved = true
```

If bundle usage is allowed in `workflow.toml`, the approved `ingestion` bundle
can satisfy the required baseline for both `importer` and `validator`.

## Real Case Pattern: First Adoption Pass

During the first adoption pass, avoid pretending a component is complete.
Start with discovered or characterized entries:

```toml
[components.billing]
paths = ["src/package/billing/**", "tests/billing/**"]
tests = ["tests/billing"]
criticality = "high"
adoption_status = "discovered"
owner = "domain"
notes = "Boundary identified; requirements and component documentation still need review."
```

Then move the component through adoption:

1. Confirm paths and responsibilities.
2. Document behavior and risks.
3. Link durable requirements to tests.
4. Run the relevant checks.
5. Change `adoption_status` to `baseline-usable` only after the baseline is
   real.

## Real Case Pattern: Feature Work Touches An Unready Component

Suppose a feature expects to edit:

```text
src/package/worker/scheduler.py
```

And the manifest says:

```toml
[components.worker]
paths = ["src/package/worker/**"]
adoption_status = "characterized"
```

If the configured default completion level is `baseline-usable`, the feature
should stop before behavior-changing implementation and run an adoption slice
for `worker`. After the component reaches `baseline-usable`, the feature can
resume with a clearer requirement and verification base.

## Real Case Pattern: Unmapped Paths

If a changed path does not match any component pattern, adoption scope checks
report it as informational rather than blocking. This is useful during early
adoption, but it means the manifest is not yet protecting that area.

Example unmapped path:

```text
src/package/export/report_writer.py
```

Add a component when the path belongs to a meaningful boundary:

```toml
[components.export]
paths = ["src/package/export/**", "tests/export/**"]
tests = ["tests/export"]
criticality = "medium"
adoption_status = "discovered"
owner = "application"
notes = "Owns generated export files and their formatting rules."
```

## Good Component Boundaries

Good component boundaries are:

- named after responsibility, not file type
- stable across small refactors
- small enough to adopt and verify incrementally
- large enough to contain a real behavior contract
- connected to tests, requirements, and documentation

Avoid components such as:

- `utils` when it mixes unrelated helpers
- `misc`
- one component per file when files are not meaningful behavior boundaries
- one repository-wide component unless the project is genuinely tiny

## Change Checklist

When editing `components.toml`:

- Keep component names stable where possible.
- Normalize paths with forward slashes.
- Keep `paths` broad enough to catch real changes, but not so broad that one
  component owns unrelated behavior.
- Do not mark a component `baseline-usable` until its requirements, tests, and
  documentation are good enough for behavior-changing work.
- Keep bundle membership below the configured maximum.
- Include a `reason` for every bundle.
- Run:

```powershell
<workflow> adoption component-status
<workflow> adoption baseline
<workflow> adoption scope-check <changed-path>
```

Use representative paths for `<changed-path>` when checking a proposed boundary.
