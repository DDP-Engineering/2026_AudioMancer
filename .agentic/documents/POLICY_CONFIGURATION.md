<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# Policy Configuration

AEGIS 2.1 reads workflow policy only from the mandatory schema-3
`.agentic/workflow.toml`. Validate with `aegis config validate`; inspect with
`aegis config show --json`.

Policy areas are:

- source/test/requirement/documentation/knowledge roots;
- component baseline and adoption behavior;
- traceability coverage;
- alignment pause and protected-scope behavior;
- interface retention and check execution;
- independent build, typecheck, lint, test, and security gates;
- secrets, protected paths, working tree, write access, scope, and delivery.

Disabled optional policies remain explicit. Gate commands may be retained while
their group is disabled. Other disabled rule policies retain their existing
closed-schema semantics.

Configuration errors include a stable code, key path, received value, expected
shape, and remediation. `CONFIG-SCHEMA-UNSUPPORTED` means deploy a fresh schema-3
configuration; AEGIS does not rewrite schema 2.

Host sandbox, approval, and tool permissions remain separate from AEGIS policy
and always apply.

The optional schema-1 `.agentic/integrations/repowise.toml` is an integration
policy, not workflow policy. Absence means disabled. Advisory mode may
pre-populate repository-discovery fields only after evidence validation;
required mode may block that stage when evidence is unavailable or stale.
Neither mode grants RepoWise authority over requirements, design, checks,
evidence, approvals, hooks, agent prompts, or graph state.
