---
name: documentation-audit
description: Review changed implementation files against relevant component documentation, updating broad README, overview, setup, or validation docs only when explicitly requested or when their scope changes.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# Documentation Audit

Read and follow these shared workflow rule sources:

- `AGENTS.md`
- `.agentic/skills/documentation-audit/SKILL.md`

Codex invocation: `$documentation-audit`.

If a deterministic documentation audit exists in the target repository, run it
in changed-only mode. Otherwise perform the manual review described by the
shared skill.
