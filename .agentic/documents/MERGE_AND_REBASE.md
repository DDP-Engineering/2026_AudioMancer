<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# Merging and Rebasing AEGIS State

Use this page when Git reports a conflict under `.agentic/`, or after a clean
merge or rebase brings another developer's AEGIS state into the branch. It
supplements [WHY_AEGIS.md](WHY_AEGIS.md), [GLOSSARY.md](GLOSSARY.md), and
[INVARIANTS.md](INVARIANTS.md); it does not replace their lifecycle, waiver,
or invariant guidance.

## What merges cleanly by design

Most merges need no AEGIS-specific action. Each run has a globally unique ID,
so independently created `.agentic/runs/<run-id>/` directories are disjoint and
additive. New requirement snapshots use UUID-based IDs and are exclusively
published into separate files. A separate run on another branch is therefore
normal merge content, not competing state.

The selected-run pointer and AEGIS lock files are worktree-local under
`.agentic/.workspace/`. They are never staged and must not be copied between
worktrees. Do not try to reconcile them in Git.

## Files that can conflict

### One requirement snapshot edited on both branches

Resolve this as one TOML record: decide the intended current requirement, keep
its one existing `id`, category, and filename identity, then make every field
internally consistent. Do not concatenate two records or put two IDs in one
file. The requirement schema is closed and the filename must match the record
identity, so a malformed merge fails loudly when AEGIS loads requirements.

After resolving, run:

```text
aegis verify traceability
```

If a concurrent local write races the resolution, the CLI reports
`REQUIREMENT-STALE-UPDATE`; reload the requirement and retry rather than
overwriting the newer file.

### `workflow.toml` and `components.toml`

These are repository policy files, not generated run state. Resolve by policy
intent: retain every deliberate rule change only when the combined policy is
what the project now intends. In particular, do not use one branch merely to
make a gate, guardrail, component path, or baseline status disappear.

After resolving, run:

```text
aegis config validate
```

### Coverage-waiver list

`.agentic/requirements/coverage_waivers.txt` is a line-set policy file. A
union of the distinct, still-justified lines is usually correct; remove only a
line that is no longer an approved exception. Keep one path per line.

After resolving, run:

```text
aegis verify coverage
```

### Component knowledge index

Resolve `.agentic/knowledge/components/index.md` as an index of the component
documents that exist after the merge. Keep entries for both independently added
components, and reconcile a shared component entry with its final boundaries,
interfaces, and ownership. Then review the matching component documents rather
than treating the index as the source of truth.

After resolving, run:

```text
aegis config validate
```

## After a clean merge

Git cleanliness does not mean that earlier approvals still describe the merged
state. Run `aegis run status`, then run `aegis verify run` for each active run
whose requirements, checks, design, or policy changed in the merge. Target one
run without moving the worktree pointer with `aegis --run <run-id> verify run`,
or switch the selected run first with `aegis run select <run-id>`.

- **INV-10 is stale.** A cited requirement changed after design approval. This
  is detection working as intended. Review the new contract, update the design
  where needed, and consciously repeat the affected lifecycle approval. If an
  eligible process blocker remains after review, discover it with
  `aegis waive list` and have a human add the exact waiver with a reason; see
  [INVARIANTS.md](INVARIANTS.md).
- **Citation or coverage findings appear.** The merge changed requirement,
  check, or path relationships. Repair the citations or coverage, or keep only
  a documented, still-justified coverage-waiver line. `aegis verify traceability`
  and `aegis verify coverage` isolate those audits.
- **A run-local waiver is stale.** Its digest-pinned blocker state changed.
  Review the new state; a previous waiver is not approval for it. Use
  `aegis waive list` to see the current blocker, then have a human add a new
  exact waiver only if it is still justified.
- **Quick-run bypass records remain.** They are durable records in that run's
  graph and journal, created when intake closes. A clean merge does not turn
  bypassed stages into passed stages; quick-run-specific invariant and audit
  results remain `not-applicable` as described in [INVARIANTS.md](INVARIANTS.md).

## Rebase specifics

Resolve each replayed conflict with the same rules above. A rebase can present
the same policy or snapshot decision more than once because it reapplies commits
one at a time; validate again after the final replay, not just after the first
resolution. Independent run directories remain additive. Their timestamps show
when their events were recorded, not a cross-branch ordering that a rebase must
rewrite. Journals are append-only JSON Lines files; independently added run
journals normally rebase cleanly because they live in separate run directories.

## What not to do

- Never hand-edit a run `graph.json` to silence a conflict. It is authoritative
  schema-3 state, coupled to its journal and approvals. Invalid content fails
  graph loading with a schema error; overwriting state loaded by another process
  is rejected as `GRAPH-STALE-UPDATE`.
- Never delete another developer's run directory to make a merge easy. It
  discards their graph, evidence, reports, and journal history; later selection
  or loading fails because the run graph is missing. Keep the directory and let
  its independent state merge additively.
- Never resolve a requirement-snapshot conflict by accepting both IDs into one
  file. A snapshot has exactly one identity and its path must match that ID;
  the requirement loader raises `RequirementValidationError` for the invalid
  schema or identity tuple. Keep one record per file, or create a separate
  requirement through the normal stage workflow.

## Quick reference

1. Finish the Git merge or rebase; do not stage `.agentic/.workspace/`.
2. Keep independent run directories from both branches.
3. Resolve a shared requirement as one valid TOML snapshot and one identity.
4. Resolve policy and component-map conflicts by final project intent.
5. Union still-justified coverage-waiver lines.
6. Reconcile the component index with the component documents.
7. Run `aegis config validate`.
8. Run `aegis run status` and `aegis verify run` for affected active runs.
9. Repair citation or coverage drift; re-approve stale design consciously.
10. Use an exact, human-approved waiver only for a current eligible blocker.
