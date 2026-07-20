<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AEGIS Configuration

This document explains `.agentic/workflow.toml`, the main repository-local
configuration file for the agentic workflow. It defines where the workflow looks
for source code, tests, requirements, documentation, component maps, validation
commands, secret patterns, alignment policy, and stage-specific write zones.

The file is intentionally repository-relative. Paths should normally use
forward slashes and should not be absolute unless a local wrapper command
requires it.

## Mental Model

`workflow.toml` answers these questions:

- Where are the implementation files?
- Where are the tests?
- Where are durable requirements stored?
- Where should component documentation live?
- Which files need requirement coverage?
- Which commands make up validation gates?
- Which secret-like patterns must block delivery?
- Which paths may be edited at each workflow stage?
- When must intent alignment pause for human input?
- Which component manifest should adoption commands read?

The workflow CLI and hooks read this file during commands such as:

- `<workflow> audit traceability`
- `<workflow> audit coverage`
- `<workflow> impact`
- `<workflow> gates run`
- `<workflow> adoption component-status`
- `<workflow> adoption scope-check`
- `<workflow> working-tree audit`
- `<workflow> delivery-preflight`
- write-zone hook checks before edits

## Root Sections

### `[source]`

Defines implementation roots used by scope checks and impact analysis.

```toml
[source]
roots = ["src/package"]
```

Use this for code that implements product or library behavior. Do not include
tests, generated reports, or workflow state here.

### `[tests]`

Defines test roots used by traceability and impact checks.

```toml
[tests]
roots = ["tests"]
```

Use every root that contains first-party tests the workflow should discover.

### `[requirements]`

Defines where durable requirement registers live.

```toml
[requirements]
roots = [".agentic/requirements"]
```

Requirement registers are long-lived Markdown files. Run-local specs are stored
in the active workflow graph, while durable requirements live under these roots.

### `[documentation]`

Defines component documentation roots and the template used when a new component
document is created.

```toml
[documentation]
roots = ["docs/components"]
component_template = "docs/components/component_template.md"
```

`roots` is used by scope invariants when implementation changes must be paired
with matching component documentation. `component_template` tells agents which
document structure to follow.

## Adoption Sections

### `[adoption]`

Controls existing-project adoption behavior.

```toml
[adoption]
default_completion_level = "baseline-usable"
allow_component_bundles = true
max_bundle_components = 5
behavior_changes_allowed = false
```

Settings:

| Setting | Meaning |
| --- | --- |
| `default_completion_level` | Minimum component status required before behavior-changing work proceeds. |
| `allow_component_bundles` | Whether related components may be adopted as an approved bundle. |
| `max_bundle_components` | Maximum components allowed in one bundle. |
| `behavior_changes_allowed` | Whether adoption work may include behavior changes by default. |

Common completion levels are described in
`.agentic/documents/COMPONENTS_CONFIGURATION.md`.

### `[components]`

Points to the component manifest.

```toml
[components]
manifest = ".agentic/components.toml"
```

The manifest is read by adoption commands and component baseline checks.

### `[knowledge]`

Defines roots used by adoption and documentation-oriented workflows.

```toml
[knowledge]
roots = [".agentic/knowledge"]
```

Use this for workflow knowledge files, adoption notes, reusable references, or
other agentic context that is not product source.

### `[reports]`

Defines where adoption reports are written.

```toml
[reports]
adoption_root = ".agentic/reports/adoption"
```

## Traceability

The `[traceability]` section controls requirement coverage and test discovery.

```toml
[traceability]
language = "python"
source_extensions = [".py"]
coverable_roots = ["src/package/services", "src/package/controllers"]
coverable_exclude = ["__init__.py"]
test_file_patterns = ["test_*.py", "*_test.py"]
```

Settings:

| Setting | Meaning |
| --- | --- |
| `language` | Primary language used by requirement and test resolution helpers. |
| `source_extensions` | File extensions considered source files for coverage. |
| `coverable_roots` | Source subtrees where files must have requirement coverage or waivers. |
| `coverable_exclude` | File names or glob patterns excluded from coverable scans. |
| `test_file_patterns` | Test filename patterns used when resolving linked tests. |

Use `coverable_roots` narrowly at first. A broad value such as `src` makes every
source file require requirement coverage unless explicitly waived.

### Linked-test resolution by language

AEGIS has structure-aware linked-test resolvers for `python`, `java`, `c`, and
`cpp`. Every other configured language — including WAEGIS presets such as
`typescript`, `javascript`, `go`, `rust`, and `csharp` — uses name-substring
matching inside the configured test roots. For those languages, choose stable,
distinct linked-test identifiers and confirm them with `audit traceability`.

### Pattern semantics

All AEGIS path matchers use the same `fnmatch`-based policy. In this policy,
`*` crosses `/`: `src/*` behaves like `src/**`, and `*.tmp` also matches nested
temporary files. A bare directory pattern such as `src/module` additionally
covers its subtree, but does not match a sibling such as `src/module2`. Configure
write zones, component paths, coverage exclusions, and working-tree blockers
with these semantics in mind rather than assuming Git-glob behavior.

## Gates

The `[gates]` section defines named command groups for `<workflow> gates run`.

```toml
[gates]
test = [
  "python -m pytest -q tests"
]
lint = [
  "python -m ruff check src tests"
]
docs = [
  "python tools/check_docs.py"
]
```

Each key is a gate name. Each value is an ordered list of shell commands. A
plain string value is also accepted and treated as a one-command list; any
other value type stops with an error naming the offending key. A command that
cannot be launched (missing executable) or exceeds the timeout is recorded as
a normal failing gate (exit 127 / 124, with the error text in the journal)
rather than crashing the run.

Examples:

```powershell
<workflow> gates run
<workflow> gates run --name test
<workflow> gates run --name test --name lint --timeout 600
```

Guidelines:

- Keep commands deterministic and local.
- Prefer repository-local wrappers or pinned environments.
- Avoid interactive commands.
- Avoid commands that publish, deploy, push, or mutate external systems.
- Split slow or specialized checks into named gates so they can be run
  selectively.

## Secrets

The `[secrets]` section defines regular expressions treated as secret-like
content.

```toml
[secrets]
patterns = [
  "sk-[A-Za-z0-9_-]{20,}",
  "ghp_[A-Za-z0-9_]{20,}",
  "-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----"
]
```

These patterns are used by secret checks and delivery readiness. The
`secret_scan.py` PreToolUse hook scans their union with its built-in credential
formats, so project-specific tokens are protected during shell commands and
file edits too. If the hook cannot read or parse `workflow.toml`, it continues
with built-in patterns; invalid configured regular expressions are ignored by
the hook instead of crashing or blocking tool use. Keep valid patterns specific
enough to avoid constant false positives, but broad enough to catch common
credential formats used by the repository.

## Working Tree

The `[working_tree]` section declares Git status path patterns that should block
delivery preflight.

```toml
[working_tree]
blocked_patterns = [
  "dist/**",
  "build/**",
  "*.tmp"
]
```

Use this for generated artifacts or local scratch files that should never be
present during delivery. Leave the list empty when untracked files should be
treated as advisory unless they match other protected rules.

## Alignment

The `[alignment]` section controls the Intent Alignment stage.

```toml
[alignment]
enabled = true
pause_on_open_questions = true
risk_threshold = "medium"
allow_recommended_responses = true
protected_scope_patterns = ["infrastructure/**", "security/**"]
```

Settings:

| Setting | Meaning |
| --- | --- |
| `enabled` | Whether `next` routes through `alignment` after `intake`. |
| `pause_on_open_questions` | Whether open questions force `decision pause`. |
| `risk_threshold` | Minimum risk level that forces `decision pause`; valid values are `low`, `medium`, and `high`. |
| `allow_recommended_responses` | Whether every open question can be paired with a recommended response to permit automated continuation. |
| `protected_scope_patterns` | Planned path globs that force a pause even when other alignment fields look safe. |

Example: automated continuation for a low-risk documentation change.

```powershell
<workflow> alignment `
  --source "human prompt" `
  --understanding "Refresh a configuration manual." `
  --scope "in: manual files; out: runtime behavior" `
  --acceptance "Manual describes each setting and includes examples." `
  --risk low `
  --decision proceed `
  --reason "No open questions and no protected paths."
```

Example: forced pause for a protected path.

```powershell
<workflow> alignment `
  --source "ticket" `
  --understanding "Change deployment credentials handling." `
  --scope "in: security configuration" `
  --acceptance "Credential loading is updated safely." `
  --risk medium `
  --decision pause `
  --reason "Risk meets the configured threshold and protected paths are planned." `
  --planned-path security/credentials.py
```

## Write Zones

The `[write_zones]` section maps workflow stages to edit allowlists. The
write-zone hook reads these values before allowing edit tools.

```toml
[write_zones]
intake = [".agentic/**"]
alignment = [".agentic/**"]
requirement = [".agentic/requirements/**"]
check = ["tests/**"]
implementation = ["src/**", "tests/**", "docs/components/**"]
validation = []
delivery = [".agentic/**", "CHANGELOG.md"]
```

Normal stages:

| Stage | Typical write zone |
| --- | --- |
| `intake` | Workflow state only. |
| `alignment` | Workflow state only. |
| `requirement` | Durable requirements and run-local requirement state. |
| `check` | Tests and checks only. |
| `implementation` | Source, required docs, and sometimes tests when the approved workflow allows it. |
| `validation` | Usually read-only. |
| `delivery` | Workflow reports, registries, changelog, and delivery notes. |

Adoption stages:

| Stage | Typical write zone |
| --- | --- |
| `adoption-intake` | Workflow state only. |
| `adoption-alignment` | Workflow state only. |
| `repo-discovery` | Discovery notes and workflow state. |
| `component-map` | Component manifest and workflow state. |
| `component-adoption` | Component docs, tests, adoption records, and approved local files. |
| `baseline-review` | Adoption reports and workflow state. |
| `adoption-delivery` | Adoption reports and delivery state. |

Guidelines:

- Keep early stages narrow so requirements and checks cannot be bypassed.
- Keep `validation = []` when validation should be read-only.
- Add paths only when a stage genuinely needs to edit them.
- Protected files such as `.git`, credential files, key material, and `.env`
  files remain blocked even when the workflow is in repo-wide access mode.

## Complete Minimal Example

```toml
[source]
roots = ["src"]

[tests]
roots = ["tests"]

[requirements]
roots = [".agentic/requirements"]

[documentation]
roots = ["docs/components"]
component_template = "docs/components/component_template.md"

[components]
manifest = ".agentic/components.toml"

[traceability]
language = "python"
source_extensions = [".py"]
coverable_roots = ["src"]
coverable_exclude = ["__init__.py"]
test_file_patterns = ["test_*.py", "*_test.py"]

[gates]
test = ["python -m pytest -q tests"]

[alignment]
enabled = true
pause_on_open_questions = true
risk_threshold = "medium"
allow_recommended_responses = true
protected_scope_patterns = []

[write_zones]
intake = [".agentic/**"]
alignment = [".agentic/**"]
requirement = [".agentic/requirements/**"]
check = ["tests/**"]
implementation = ["src/**", "tests/**", "docs/components/**"]
validation = []
delivery = [".agentic/**", "CHANGELOG.md"]
```

## Real Case Pattern: Documentation-Only Change

For a documentation-only workflow, the configuration normally needs:

- source and test roots unchanged
- documentation root included in `documentation.roots`
- implementation write zone including the documentation folder
- validation write zone left empty
- a gate command only if the repository has a documentation checker

Example implementation zone:

```toml
[write_zones]
implementation = ["docs/**", ".agentic/documents/**"]
validation = []
```

This allows the implementation gate to update manuals while keeping validation
read-only.

## Real Case Pattern: Existing-Project Adoption

For an adoption run, the configuration normally needs:

- `[components].manifest` pointing to `.agentic/components.toml`
- `[adoption].default_completion_level = "baseline-usable"`
- `[adoption].behavior_changes_allowed = false`
- write zones for `repo-discovery`, `component-map`, and `component-adoption`

Example:

```toml
[adoption]
default_completion_level = "baseline-usable"
allow_component_bundles = true
max_bundle_components = 3
behavior_changes_allowed = false

[write_zones]
repo-discovery = [".agentic/**", "docs/discovery/**"]
component-map = [".agentic/**"]
component-adoption = [".agentic/**", "tests/**", "docs/components/**"]
```

This lets adoption document and verify existing behavior without changing the
runtime behavior by default.

## Change Checklist

When editing `workflow.toml`:

- Keep paths repository-relative.
- Verify renamed roots exist.
- Update write zones when folder layout changes.
- Update gate commands when test or tool commands change.
- Keep secret patterns current.
- Keep documentation roots aligned with component documentation rules.
- Run focused validation, usually:

```powershell
<workflow> status
<workflow> audit traceability
<workflow> audit coverage
<workflow> gates run --name test
```

Use the gates that are relevant for the repository and the change.
