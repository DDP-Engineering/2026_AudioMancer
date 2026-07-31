<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AEGIS 1.4.1 Legacy State

This directory preserves the execution history that existed immediately before
AudioMancer adopted AEGIS 2.1.0 on the migration branch.

The archived run graphs use the pre-hard-break schema. They are audit evidence,
not resumable AEGIS 2.1 runs. They must not be copied back into
.agentic/runs/ unless the repository is deliberately rolled back to the
archived AEGIS 1.4.1 payload and schema-2 configuration.

Contents:

- runs-schema-2/ - 38 run graphs, their journals, and available reports.
- install-manifest-aegis-1.4.1.json - pre-migration install manifest.
- workflow-schema-2.toml - pre-migration repository policy.
- archive-sha256.json - checksums for the preserved files.

The previous worktree-local selected run was:

    change-2026-07-29T123056Z-fa16e595

No schema-3 design, stage_records, complete, or human-close records were
synthesized for these runs. Doing so would invent approvals and provenance that
the earlier workflow did not record.
