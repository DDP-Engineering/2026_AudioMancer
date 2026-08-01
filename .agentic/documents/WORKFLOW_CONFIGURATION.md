<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# Workflow Configuration

Every AEGIS 2.1 workspace begins with:

```toml
schema_version = 3
```

Inspect it with `<workflow> config validate --json` and
`<workflow> config show --json`.

The selected run is worktree-local state at
`.agentic/.workspace/state/current_run`; use global `--run <run-id>` to pin a
different existing run without rewriting that pointer.

## Persistence and Concurrency

AEGIS publishes graph, journal, requirement, active-run pointer, and normalized
RepoWise JSON through uniquely named, exclusively created sibling temporary
files. Each completed temporary file is flushed and fsynced before atomic
replacement; parent-directory metadata is fsynced where the operating system
supports it. A failed replacement leaves the previous complete file in place
and cleans the unpublished temporary file.

Graph mutation holds one repository/run-scoped Windows or POSIX process lock
across authoritative reload, validation, mutation, graph publication, and its
journal calls. Journal publication has its own run-scoped lock and preserves
one complete UTF-8 JSON object per line. Evidence IDs retain the `E-NNNN`
format and are allocated monotonically from the locked authoritative graph.

Same-requirement updates use a requirement-scoped lock and compare the exact
source digest captured at load with the file present immediately before
publication. A stale graph or requirement update fails closed with
`GRAPH-STALE-UPDATE` or `REQUIREMENT-STALE-UPDATE`; it never silently replaces
the newer state. Requirement reads remain lock-free, UUID-per-file creation
remains exclusive, and edits on different branches retain the normal Git
conflict model.

Lock acquisition waits for at most 15 seconds, then returns
`PERSISTENCE-LOCK-TIMEOUT` with the lock path and retry guidance. Lock files
under `.agentic/.workspace/locks/` persist deliberately. The operating system
releases a lock when its process exits, so an unlocked stale file is reused
safely and must not be deleted based on uncertain ownership.

`.agentic/workflow.toml` is a strict, closed schema-3 document. Missing,
unknown, malformed, schema-2, or inconsistent configuration blocks before state
mutation. There is no migration.

## Workspace Interface

```toml
[interface]
stage_form_retention = "discard"
check_execution = "external"
```

Retention is `versioned`, `latest`, or `discard`. It applies only to transient
input forms; design, requirement/spec snapshots, graph state, evidence,
journals, validation summaries, and delivery reports are always durable.

The policy is captured when a stage is prepared. Configuration changes affect
the next prepared revision, never the current one.

Check execution is `external` or `managed`. External mode generates immutable
evidence forms. Managed mode executes imported commands.

## Quick Run Proportionality

The optional quick-run changed-path advisory is configured with:

```toml
[quick.changed_paths]
mode = "advise"
max_paths = 10
```

Modes are `disabled` and `advise`, and `max_paths` must be a positive integer.
When this table is absent, AEGIS normalizes the ship-open default to
`mode = "disabled"` and `max_paths = 10`; the starter file therefore omits the
active table. In advise mode, a quick implementation that closes with more
than the configured number of unique changed paths receives guidance to carry
its context into a new full run. This is a soft response only: it does not
block, route, or change the current run.

Current WAEGIS `new`/`adopt` interviews and doctor/configuration parsing do not
yet manage this optional AEGIS table. That cross-tool awareness is a deliberate
follow-up; use AEGIS `config validate/show` as the authority for the key.

## Deterministic Gates

Every group has its own mode and commands:

```toml
[gates.build]
mode = "disabled"
commands = []

[gates.typecheck]
mode = "disabled"
commands = []

[gates.lint]
mode = "disabled"
commands = []

[gates.test]
mode = "disabled"
commands = []

[gates.security]
mode = "disabled"
commands = []
```

Modes are `disabled` and `enforce`. Disabled groups may retain commands.
Enforced groups require at least one command. Execution order is build,
typecheck, lint, test, security. Security commands must be explicit and provide
tool evidence only—not a general security assurance.

All remaining source, tests, requirements, documentation, component,
traceability, adoption, alignment, and guardrail tables remain required. Use
`<workflow> config show --json` to inspect the normalized effective policy.

## Optional Integrations

Optional discovery integration is deliberately outside `.agentic/workflow.toml`
and does not change schema 3. `<workflow> config validate/show` also inspects the
strict schema-1 `.agentic/integrations/repowise.toml`; absence means disabled.
See `REPOWISE_INTEGRATION.md`.
