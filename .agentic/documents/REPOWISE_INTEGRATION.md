<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# Optional RepoWise Integration

RepoWise is an optional, process-isolated repository-discovery provider.
WAEGIS installs/configures and executes it; AEGIS only validates and reads its
artifacts. RepoWise never becomes authoritative AEGIS workflow state and never
replaces human-entered discovery.

## Policy

The optional strict file is `.agentic/integrations/repowise.toml`:

```toml
schema_version = 1
provider = "repowise"
mode = "disabled"                 # disabled | advisory | required
source = "none"                   # none | bundled | external
version_spec = ">=0.37.0,<0.38.0"
artifact = ".repowise/knowledge-graph.json"
state = ".repowise/state.json"
require_head_match = true
require_worktree_match = true
```

Absence means disabled. This file is separate from schema-3
`.agentic/workflow.toml`; enabling it does not migrate or alter workflow or
run-graph schema.

Use WAEGIS to change it:

```text
waegis configure --repo "<project>"
waegis repowise status --repo "<project>"
waegis repowise sync --repo "<project>"
```

Do not hand-edit WAEGIS runtime metadata or receipts. No credentials are stored.
Only loopback Ollama endpoints are permitted.

`.repowise/`, the project-local runtime, execution metadata, and generated
receipt are reproducible local state and are excluded from Git. The validated
run-local discovery snapshot remains the durable AEGIS record.

## Freshness and Authority

A successful WAEGIS synchronization writes a generated receipt containing:

- RepoWise version, bundled/external source, and profile;
- completion state and timestamp;
- Git HEAD and a worktree fingerprint;
- knowledge-graph and state paths and SHA-256 digests.

At `repo-discovery`, AEGIS validates the strict policy, receipt, RepoWise 0.37.x
version, graph/state JSON schemas, hashes, HEAD, and worktree fingerprint. It
then writes normalized proposals and provenance to:

```text
.agentic/runs/<run-id>/discovery/repowise.json
```

Current data may pre-populate otherwise empty source-root, component,
dependency, entry-point, and existing-test fields. Existing human content is
preserved. `advisory` mode warns when evidence is unavailable or stale;
`required` mode blocks repository-discovery closure until it is current.

AEGIS never imports RepoWise Python code, runs a RepoWise command, registers its
MCP server, or treats generated prose as evidence. Even with the optional Ollama
profile, AEGIS consumes only structural graph data.

## Offline Delivery

A deployment's RepoWise portability is exactly one of three states:

- `source-only` — the integration is disabled; no RepoWise runtime or link
  exists. A Git clone is fully self-contained.
- `external-runtime` — the deployment links a machine-level external RepoWise
  installation. The command is not part of the repository, so a fresh clone on
  another machine must re-link its own external RepoWise before the
  integration can run there.
- `offline-bundled-runtime` — WAEGIS Complete installed a pinned RepoWise
  0.37.0 runtime under:

  ```text
  .agentic/tools/repowise/0.37.0/<platform>/
  ```

  That directory is excluded from normal Git and RepoWise discovery, so a Git
  clone is **not** self-contained for this state: only a delivered working
  directory (the runtime files present on disk) or a fresh run of the WAEGIS
  Complete installer restores the runtime.

WAEGIS Core has no RepoWise payload and defaults the integration to
`source-only`. Target installation/indexing does not invoke pip, uv, package
registries, GitHub, telemetry, editor/agent setup, or update services. A
failed index leaves the AEGIS installation and RepoWise configuration intact
and reports its log plus the exact resume command.

RepoWise is licensed separately under AGPL-3.0-or-later. Complete distributions
must retain its exact corresponding source, notices, SBOM, provenance, and
hashes. Review combined-distribution obligations before public or commercial
delivery.
