<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Adoption Report: <component-name-or-bundle>

Durable summary of one component (or bundle) adopted toward a documented
baseline. Keep sections that apply; remove empty sections rather than filling
them with placeholder text. The component manifest remains the source of
truth for names, paths, tests, bundles, and adoption status — this report
explains the evidence and reasoning behind a status change, it does not
replace the manifest.

- Component(s): `<component-name>` (or bundle: `<bundle-name>`)
- Baseline status: `<unknown|discovered|characterized|baseline-usable|baseline-strict>`
- Criticality: `<as recorded in the component manifest>`

## Scope

What this report covers: one component, a bundle, or a cross-cutting concern
touching several components. State what is explicitly out of scope.

## Current State (Discovery)

What repository discovery and component mapping found before this adoption
pass: existing behavior, existing tests, existing documentation, and known
gaps. Cite concrete paths rather than describing them abstractly.

## Evidence

Checks run and their outcome: automated tests (with counts), manual
verification performed, and any coverage measured. Link durable evidence
records rather than pasting raw logs.

## Local-Scope Findings

Issues found that are scoped to this component and do not block adopting the
rest of the repository: known risks, deferred cleanup, quality concerns
accepted as legacy. State whether each is accepted, tracked, or blocking.

## Baseline Status Rationale

Why the component moved to its current baseline status (or why it remains at
its prior status): which completion level was reached, and what evidence
supports it.

## Follow-Ups

Concrete remaining work needed to reach the next completion level, if any.
