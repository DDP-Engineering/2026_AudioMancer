<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# AEGIS Glossary

This page defines the terms used by the shipped workflow. For the reason behind
the workflow, see [WHY_AEGIS.md](WHY_AEGIS.md); for evaluated rules, see
[INVARIANTS.md](INVARIANTS.md); for integrating concurrent AEGIS state, see
[MERGE_AND_REBASE.md](MERGE_AND_REBASE.md).

## Access mode

The declared level of access the work needs, captured in intake and used by the
workflow's configured controls. It records the intended boundary; it does not
override host, sandbox, operating-system, or repository permissions.

## Adapter

A thin host-specific integration under `.codex/`, `.claude/`, `.pi/`,
`.opencode/`, or `.qwen/` that starts shared AEGIS hooks and skills. Adapters
do not define the workflow policy; [workflow.toml](#workflowtoml) does.

## Add

The `aegis stage add` step that generates another CLI-identified requirement
or check form within the current prepared stage revision. It is valid only
during the requirement and check stages and, like [prepare](#prepare), only
creates input forms; nothing is imported until [apply](#apply).

## Apply

The `aegis stage apply` step that validates and imports a prepared form into
the run graph. It is not approval: the human approval boundary is
[close](#close).

## Baseline guard

The component-baseline guardrail that can require changed paths to belong to
components at the configured adoption completion level. Its result is
[INV-9](INVARIANTS.md#inv-9--component-baseline-scope).

## Check

A deterministic assertion of observable behavior that can cite one or more
requirement snapshots. Checks and their evidence supply coverage, citation,
and [red-before-green](#red-before-green) results.

## Close

The `aegis stage close` action, which records explicit human approval of an
already imported stage. It is the authoritative approval boundary, unlike
[apply](#apply).

## Companion spec

A Markdown document referenced by a requirement snapshot for concrete examples
or supporting detail. The snapshot is the durable atomic contract; the
companion spec expands it and is not a second requirement identity.

## Component manifest

`.agentic/components.toml`, the declared map of repository components, their
paths, tests, ownership hints, and adoption status. It supplies the component
knowledge used by the [baseline guard](#baseline-guard).

## Control table

The generated form section that records a human-approved routing decision to
an earlier stage and its rationale. It is how the workflow changes direction
without hiding that decision in a command flag.

## Coverage waiver file

`.agentic/requirements/coverage_waivers.txt`, a policy file for documented
coverage-audit exceptions. It is distinct from a run-local [waiver](#waiver),
which is an exact, digest-pinned process exception created by the CLI.

## Delivery report

The durable run report prepared for handoff at delivery. Closing delivery
completes AEGIS state; it never pushes, publishes, merges, or creates a pull
request.

## Design approval

Human approval of the authoritative run-local `design.md` and its cited
requirement snapshots at [close](#close). Their digests are pinned so
[INV-10](INVARIANTS.md#inv-10--solution-design) can detect later drift.

## Evidence

A durable record that a check, gate, or manual observation occurred. In
`external` mode, the operator runs prepared commands and imports the complete
evidence form with `aegis check record`; in `managed` mode,
`aegis check run` executes imported commands; manual evidence uses
`aegis evidence prepare` and `aegis evidence apply`. Evidence is not a claim
that all policy passed; verification evaluates that separately.

## Form

A generated TOML input artifact for a stage, check evidence, or manual
evidence. The CLI creates it, validates its complete contents, and imports it
at [apply](#apply).

## Gate

One configured deterministic command group: build, typecheck, lint, test, or
security. Each is independently `disabled` or `enforce`; disabled means no
execution and is never reported as passed.

## Graph

The authoritative run state stored in the run's graph file. It contains the
imported lifecycle state, requirements/check relationships, evidence, design
approval, waivers, and journal-linked progress; edit it only through the CLI.

## Guard hook

A host-invoked script that applies configured read, write, shell-write,
secret, delivery, or evidence controls around a tool action. It is a transport
integration, not an independent policy source.

## Guardrail

A configured advisory or enforcing workflow policy outside the five
[gates](#gate), such as scope, secrets, traceability, coverage, or the
component baseline guard. Its mode determines whether a finding blocks.

## Invariant

A named `INV-*` rule evaluated from the current graph, durable requirements,
repository state, and policy. See [INVARIANTS.md](INVARIANTS.md) for all ten.

## Journal

An append-only durable sequence of lifecycle and waiver events for one run.
It records what happened and when; the [graph](#graph) remains the current
authoritative state.

## Prepare

The `aegis stage prepare` step that creates the next revision of the current
[form](#form) and captures the applicable interface policy. It starts the
prepare/apply/close lifecycle.

## Quick run

A proportional `fix` or `change` run started with `--quick`. It keeps intake,
implementation, validation, and delivery; alignment, requirement, design, and
check are journaled as `bypassed`, never passed or waived. Related invariants
are `not-applicable` as described in [INVARIANTS.md](INVARIANTS.md). The
optional `[quick.changed_paths]` policy table can add a soft advisory when
closing implementation touches more changed paths than its configured
`max_paths`; the advisory recommends restarting as a full run and never
blocks.

## Red-before-green

The full-run fix rule requiring recorded failing (`red`) evidence for a check
before recorded passing (`green`) evidence for that check. It is evaluated by
INV-3; quick runs do not collect checks, so INV-3 is `not-applicable` there.

## RepoWise

An optional, separate repository-discovery integration. AEGIS reads normalized
RepoWise artifacts during adoption discovery but neither imports RepoWise
Python code nor executes its CLI. Its deployment is one of three portability
states: `source-only` (not configured), `external-runtime` (linked to a
machine-level installation outside the repository), or
`offline-bundled-runtime` (a gitignored runtime installed beneath
`.agentic/tools/repowise/<version>/<platform>` by WAEGIS Complete). See
[REPOWISE_INTEGRATION.md](REPOWISE_INTEGRATION.md).

## Requirement snapshot

One complete durable TOML record under `.agentic/requirements/` for an atomic,
observable project contract. A [companion spec](#companion-spec) may add
detail; a snapshot supplies the stable ID, status, and traceability target.

## Retention mode

The `interface.stage_form_retention` policy: `versioned`, `latest`, or
`discard`. It controls transient input forms only; design, requirements,
evidence, journals, validation summaries, and delivery reports stay durable.

## Revision

The monotonically increasing prepared version of a transient form. A revision
captures the policy in effect when it was prepared, so later configuration
changes apply only to a future revision.

## Routing

Returning from the current stage to an earlier one through a form's
[control table](#control-table), with a human-approved reason. It preserves
the decision in run state rather than silently rewriting earlier work.

## Run

One named, durable instance of AEGIS work. A run has an intent, selected
[run kind](#run-kind), stage state, graph, journal, evidence, and reports.
`aegis run resume` continues the selected worktree-local run.

## Run kind

The lifecycle selected at `aegis run start`: `feature`, `fix`, `change`, or
`adoption`. Full feature/fix/change runs use eight stages; adoption has its
own ordered adoption stages; a `fix` or `change` may use a [quick run](#quick-run).

## Show

The `aegis stage show` step that reports the current stage's form files,
imported revision, readiness, and blockers. It reads state only and changes
nothing.

## Stage

One ordered workflow boundary. Full development stages are intake, alignment,
requirement, design, check, implementation, validation, and delivery; adoption
runs use adoption-intake, adoption-alignment, repo-discovery, component-map,
component-adoption, baseline-review, and adoption-delivery. Each stage uses
[prepare](#prepare), [apply](#apply), and [close](#close).

## Validation summary

The durable result written by `aegis verify run`, including deterministic
gates, invariants, traceability, coverage, impact, and working-tree review.
It preserves disabled, failed, waived, and not-applicable states distinctly.

## Waiver

A human-approved, run-local record for one exact eligible process blocker,
created with `aegis waive add <blocker-id> --reason "<reason>"`. It is pinned
to blocker state, turns stale when that state changes, and renders the failure
as `WAIVED`, never passed. Discover candidates with `aegis waive list`.

## WAEGIS vs AEGIS

The separate stdlib-only wizard that installs, adopts, configures, repairs,
and upgrades the AEGIS payload. WAEGIS is not copied into a governed project;
AEGIS is the copied project-local workflow and CLI.

## workflow.toml

`.agentic/workflow.toml`, the strict schema-3 source of AEGIS policy. It
defines interface modes, gates, guardrails, scope, and related workflow rules;
use `aegis config validate` and `aegis config show` to inspect it.
