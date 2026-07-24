<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AEGIS Workflow Configuration

`.agentic/workflow.toml` is mandatory and is the only source of AEGIS
repository policy. Schema version 2 has no implicit Python, hook, or adapter
defaults. Missing, malformed, incomplete, unknown, or inconsistent policy is an
actionable error.

External platform safety remains independent. A valid unrestricted AEGIS
configuration does not disable host sandboxes, approvals, operating-system
permissions, organization policy, or network controls.

## Required Agent Bootstrap

Before repository inspection or edits, run:

```powershell
<workflow> config validate --json
<workflow> config show --effective --json
```

Report the effective write-access, protected-read/path, scope, secret, gate,
coverage, and delivery modes and their active rule counts. For graph-dependent
work, also report whether the worktree pointer or an explicit `--run-id` selects
the run.

## Schema Rules

- `schema_version = 2` is required and must be an integer.
- Every required table and key must be present.
- Unknown top-level keys, tables, policy keys, and stage names are errors.
- Scalar strings and command strings must be non-empty after trimming.
- Booleans and integers require exact TOML types; a Boolean is not an integer.
- Restrictive modes require their rules; disabled or unrestricted modes reject
  dormant non-empty rules.
- Configuration is validated once per operation and passed to consumers.
- Hooks import the canonical parser and never reinterpret TOML independently.

## Structural Tables

Structural values describe repository shape. They are explicit even when every
policy mode is unrestricted or disabled.

| Table | Required keys | Contract |
| --- | --- | --- |
| `source` | `roots` | Non-empty repository-relative source roots. |
| `tests` | `roots` | Non-empty test roots used for selector resolution. |
| `requirements` | `roots` | Non-empty roots containing canonical requirement snapshots. |
| `documentation` | `roots`, `component_template` | Component-document roots and template path. |
| `components` | `manifest` | Repository-relative component manifest path. |
| `knowledge` | `roots` | Non-empty knowledge roots. |
| `reports` | `adoption_root` | Repository-relative adoption-report root. |
| `traceability` | `language`, `source_extensions`, `test_file_patterns` | Language and deterministic discovery rules. |
| `adoption` | `allow_component_bundles`, `max_bundle_components` | Bundle behavior; maximum must be a positive integer. |
| `alignment` | `enabled`, `pause_on_open_questions`, `risk_threshold`, `allow_recommended_responses` | Intrinsic alignment behavior. |

`alignment.risk_threshold` accepts `low`, `medium`, or `high`.

## Policy Mode Truth Table

| Policy table | Modes | Rule contract |
| --- | --- | --- |
| `guardrails.secrets` | `disabled`, `enforce` | Disabled requires `patterns = []`; enforce requires valid non-empty regexes. |
| `guardrails.protected_paths` | `disabled`, `enforce` | Disabled requires empty `patterns` and `operations`; enforce requires both. |
| `guardrails.working_tree` | `unrestricted`, `restricted` | Unrestricted requires `blocked_patterns = []`; restricted requires patterns. |
| `guardrails.write_access` | `unrestricted`, `stage_restricted` | Unrestricted has no `stages`; restricted requires the complete stage map. |
| `guardrails.scope` | `unrestricted`, `advisory`, `enforce` | Unrestricted requires no roots; advisory/enforce require `allowed_roots`. |
| `guardrails.delivery` | `disabled`, `enforce` | Disabled requires no command patterns; enforce requires normalized patterns. |
| `traceability.coverage` | `disabled`, `enforce` | Disabled requires no roots; enforce requires `coverable_roots`. |
| `alignment.protected_scope` | `disabled`, `enforce` | Disabled requires no patterns; enforce requires patterns and enabled alignment. |
| `gates` | `disabled`, `enforce` | Disabled requires empty command lists; enforce requires at least one command. |
| `components.baseline_guard` | `disabled`, `enforce` | Enforce requires a valid manifest and completion threshold. |
| `adoption.source_changes` | `unrestricted`, `blocked` | Explicitly permits or blocks product source changes during adoption. |

### Secrets

```toml
[guardrails.secrets]
mode = "enforce"
patterns = ["(?i)api[_-]?key\\s*[:=]\\s*[^\\s]+"]
```

Patterns are Python regular expressions. The hook and delivery audit use only
configured patterns. There are no built-in credential patterns.

### Protected paths

Read policy applies to every tool that returns file content or file names —
the single-file read, grep-style search, glob, and directory listing — on all
adapters. It blocks a protected path from being **targeted**.

It cannot redact results: a repository-wide search that names no path is
allowed and may still surface a line from a protected file, because no
supported host lets a pre-tool hook rewrite tool output. Protected paths are a
guard against direct access, not a secrecy boundary — keep real secrets out of
the working tree.

Pattern shape decides whether a directory listing is blocked: `dir` matches the
directory entry and everything under it, while `dir/**` matches only what is
inside it. Use the bare directory to protect the listing itself.

```toml
[guardrails.protected_paths]
mode = "enforce"
patterns = ["secrets/**", ".env"]
operations = ["read", "write"]
```

`operations` accepts only `read` and `write`, without duplicates. The shared
repository glob matcher applies the same decision to CLI and adapter hooks.

### Working-tree blockers

```toml
[guardrails.working_tree]
mode = "restricted"
blocked_patterns = ["*.pem", "private/**"]
```

Matching Git status paths become blocking findings. Unmatched untracked files
remain advisory context unless another configured policy applies.

### Write access

Unrestricted mode has no stage map:

```toml
[guardrails.write_access]
mode = "unrestricted"
```

Stage-restricted mode requires every standard and adoption stage. An empty list
means the stage is read-only.

```toml
[guardrails.write_access]
mode = "stage_restricted"

[guardrails.write_access.stages]
intake = []
alignment = [".agentic/runs/**"]
requirement = [".agentic/requirements/**", ".agentic/runs/**"]
check = ["tests/**", ".agentic/runs/**"]
implementation = ["src/**", ".agentic/knowledge/**", ".agentic/runs/**"]
validation = [".agentic/runs/**"]
delivery = [".agentic/runs/**"]
adoption-intake = []
adoption-alignment = [".agentic/runs/**"]
repo-discovery = []
component-map = [".agentic/components.toml", ".agentic/runs/**"]
component-adoption = [".agentic/**"]
baseline-review = [".agentic/runs/**"]
adoption-delivery = [".agentic/runs/**"]
```

The run-local `standard` access mode applies the current stage list.
`repo-wide` bypasses stage lists only; it never bypasses enforced protected
paths. Under unrestricted write access, a run is not resolved merely to
authorize a write.

### Scope

```toml
[guardrails.scope]
mode = "advisory"
allowed_roots = ["src", "tests", ".agentic"]
```

`unrestricted` passes explicitly. `advisory` reports overflow without blocking.
`enforce` blocks. A run `scope_hint` may narrow intent inside configured roots;
it cannot authorize a path outside enforced roots.

### Coverage

```toml
[traceability.coverage]
mode = "enforce"
coverable_roots = ["src"]
exclude = ["src/generated/**"]
```

Coverage uses current requirement `affected_paths` and resolvable linked tests.
`exclude` may be empty in enforce mode. Disabled coverage returns an explicit
pass message and does not pretend an empty root list was audited.

### Alignment protected scope

```toml
[alignment.protected_scope]
mode = "enforce"
patterns = ["security/**", "infrastructure/**"]
```

This mode is inconsistent when `alignment.enabled = false`.

### Gates

```toml
[gates]
mode = "enforce"
test = ["python -m pytest -q"]
lint = ["python -m ruff check ."]
```

`test` and `lint` are lists of complete, non-empty command strings. Scalar
strings are invalid. Schema version 2 defines no additional gate names.

### Component baseline

```toml
[components.baseline_guard]
mode = "enforce"
minimum_completion_level = "baseline-usable"
```

The configured `[components].manifest` must resolve to a valid manifest.

### Adoption source changes

```toml
[adoption.source_changes]
mode = "blocked"
```

This replaces the retired Boolean `behavior_changes_allowed` contract.

### Delivery command matching

```toml
[guardrails.delivery]
mode = "enforce"
command_patterns = ["git push", "gh pr create"]
```

Patterns are lowercase command fragments after whitespace normalization. A
match triggers the shared delivery preflight. Passing preflight allows the
command; failing preflight denies it. External approval remains required.

## Path, Glob, Regex, and Command Normalization

- Repository paths and globs use `/` and are repository-relative.
- Absolute paths, drive prefixes, empty values, and `..` segments are invalid.
- The parser converts `\\` to `/`, removes leading `./`, collapses repeated
  separators, and removes a trailing `/` before duplicate detection.
- Case is preserved.
- Globs support `*`, `**`, `?`, and balanced bracket expressions.
- A pattern naming a directory matches that directory and everything beneath
  it, so `src/security` and `src/security/**` select the same subtree. The
  match is on whole path segments: `src/security` never matches
  `src/securityaudit/`. Every pattern setting in this file — secrets, protected
  paths, working-tree blockers, write access, scope, coverage, alignment
  protected scope, and component baselines — resolves through one shared
  matcher, so a pattern means the same thing wherever it appears.
- Malformed bracket expressions and invalid regular expressions are errors.
- Set-like lists reject duplicates after normalization instead of discarding
  them silently.
- Delivery fragments are non-empty, lowercase, and whitespace-normalized.

## Default Template

The shipped template is operationally unrestricted:

- secrets, protected paths, coverage, protected alignment scope, gates,
  component baseline, and delivery are `disabled`;
- working-tree, write-access, scope, and adoption source changes are
  `unrestricted`; and
- every inactive rule collection is empty.

This is explicit policy, not fallback behavior. Operators opt into restrictions
by choosing a restrictive mode and supplying its required rules.

## Configuration Errors

All failures use one typed error with `code`, `config_path`, `key_path`,
`received`, `expected`, and `remediation`. CLI configuration failures exit `2`;
JSON output contains the same fields and no traceback.

| Code | Meaning |
| --- | --- |
| `CONFIG-MISSING` | File is absent or not a readable regular file. |
| `CONFIG-TOML-INVALID` | TOML decoding failed. |
| `CONFIG-SCHEMA-UNSUPPORTED` | Schema version is missing, wrong-type, or not `2`. |
| `CONFIG-SECTION-MISSING` | A required table is absent. |
| `CONFIG-KEY-MISSING` | A required or conditionally required key is absent. |
| `CONFIG-TYPE-INVALID` | A value has the wrong type or an unknown key/table exists. |
| `CONFIG-MODE-INVALID` | A policy mode is not ratified. |
| `CONFIG-RULE-INVALID` | A path, glob, regex, operation, command, stage, threshold, manifest, or duplicate is invalid. |
| `CONFIG-INCONSISTENT` | Valid values contradict their mode or another option. |

Pre-tool hooks deny on configuration errors with the same remediation. Post-tool
hooks warn and avoid policy-dependent recording. No consumer continues under an
inferred configuration.

## Change Checklist

1. Edit `.agentic/workflow.toml` deliberately.
2. Run `config validate --json`.
3. Run `config show --effective --json`.
4. Confirm inactive modes have no dormant rules and restrictive modes have all
   required rules.
5. Exercise the affected CLI, hook, audit, invariant, adapter, and preflight
   paths.
6. Keep AEGIS repository policy distinct from external platform safety.
