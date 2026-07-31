<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# Why AEGIS

AEGIS is a project-local way to keep an AI-assisted change connected to the
human intent that justified it. It stores the working agreement beside the
code, so it can be read in a normal review, carried to another machine, and
resumed after a conversation or agent session ends. It is guidance with an
honest audit trail, not a substitute for engineering judgment or a claim of
enforcement.

AI assistance is useful precisely where it can also go wrong: an agent can
lose the original intent between sessions, infer a requirement that was never
approved, report a command as successful without durable evidence, or wander
when it does not know the next safe action. AEGIS makes these failure modes
visible in ordinary files and commands.

| Failure mode | AEGIS mechanism | What it makes visible |
| --- | --- | --- |
| Intent is lost or rewritten | [Requirement snapshots](GLOSSARY.md#requirement-snapshot) | The durable, atomic behavior being changed. |
| A merged change silently invalidates an approved solution | Digest-pinned design approval and [INV-10](INVARIANTS.md#inv-10--solution-design) | The design or a requirement it cites changed after approval. |
| An agent says “it passes” without a reproducible record | [Red-before-green](GLOSSARY.md#red-before-green) evidence | A fix had a failing check before it had a passing one. |
| Work stalls or expands without a decision | The exact-next-command response | The next supported action, artifact, or blocker. |

## A caught-drift example

A developer approves a design that cites a requirement snapshot. Later, a
merged branch changes that requirement's observable behavior. Before the
developer continues through check or a later stage, AEGIS evaluates INV-10.
Its saved digest no longer matches the cited snapshot, so verification reports
that the design approval is stale. The developer reviews the changed contract,
updates the design if needed, and consciously approves it again. The stale
design does not quietly become the basis for implementation.

That is the intended cost: a short, explicit reconsideration at the moment the
project's meaning changed. It does not prove the new design is good; it proves
that a human saw the change instead of shipping an old approval by accident.

## Proportionate use

AEGIS should be as small as the risk permits. A genuinely small `fix` or
`change` can use `aegis run start fix --quick` (or `change --quick`) and retain
only intake, implementation, validation, and delivery. The skipped collection
stages are recorded as `bypassed`, not passed. An eligible process failure can
also be consciously recorded once with `aegis waive list` followed by
`aegis waive add <blocker-id> --reason "<human-approved reason>"`; the failed
result remains visible as `WAIVED` and becomes stale if its pinned state
changes.

The shipped gate and guardrail defaults are open: disabled checks are reported
as disabled, not as passed. Teams can use the records first and enable policy
only when it helps them. AEGIS guides work; it does not gate it.

Next: read [GLOSSARY.md](GLOSSARY.md) for the vocabulary and
[INVARIANTS.md](INVARIANTS.md) for the verification rules.
