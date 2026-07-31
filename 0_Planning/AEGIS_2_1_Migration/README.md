<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AEGIS 2.1 Migration

## Scope

Deploy the unchanged AEGIS 2.1.0 payload with WAEGIS 1.1.0 into AudioMancer,
replace the incompatible schema-2 runtime policy with schema 3, preserve
compatible project metadata, and archive incompatible legacy execution state.

The AEGIS and WAEGIS source repository is a read-only deployment input. This
migration changes AudioMancer only and does not change application behavior.

## Pre-migration baseline

- Git base: 8981806 Cleanup requirements.
- Source branch: AudioMancer_V2
- Migration branch: codex/aegis-2.1-audiomancer-adoption
- Installed payload: AEGIS 1.4.1
- Installed by: WAEGIS 0.6.0
- Target payload: AEGIS 2.1.0
- Deployment wizard: WAEGIS 1.1.0
- Legacy policy: workflow schema 2
- Requirements: 495 Active snapshots with unique IDs
- Spec references: 97 references across 10 existing specification files
- Linked tests: 989 references, 945 unique, with no missing test files
- Affected paths: 646 references, 109 unique, with no missing targets
- Current AEGIS 2.1 in-memory compatibility check: zero traceability,
  coverage, or component-manifest findings
- Ruff baseline: passed
- Configured uv pytest command: blocked before test execution by a Windows
  uv trampoline failed to canonicalize script path environment error
- Equivalent package-root pytest run:
  1137 passed, 62 skipped, 1 deselected in 1000.74s

An intentionally invalid fallback run from the repository root is not the
baseline: it missed the package pytest configuration, included the normally
deselected performance test, and produced one failure with unknown-marker
warnings.

## Metadata disposition

Preserved in place:

- .agentic/requirements/
- .agentic/specs/
- .agentic/knowledge/components/
- .agentic/components.toml
- .agentic/reports/adoption/
- application tests referenced by requirement snapshots

Archived without conversion:

- pre-hard-break run graphs
- associated journals and reports
- old install manifest
- schema-2 workflow policy

The legacy graphs are not converted because schema-3 stage close records,
solution-design approval, completion state, and waiver provenance cannot be
inferred without fabricating human decisions.

## Acceptance

- WAEGIS reports an AEGIS 2.1.0 manifest and no unexplained drift.
- AEGIS validates the generated schema-3 policy.
- All 495 requirements load with zero traceability and coverage findings.
- Component metadata passes the current audit.
- Ruff and the package-root pytest baseline remain green.
- No application source or test file is changed by the migration.
- A new genuine schema-3 adoption run records post-deployment provenance.
