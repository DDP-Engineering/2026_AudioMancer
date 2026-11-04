<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AGENTS.md

AudioMancer uses **AEGIS**: a companion engineering workflow that
advises and records but never blocks. The full contract is
`.agentic/AGENTS.md`; this repository's own rules - the binding code
style and the release version workflow - are in `.agentic/PROJECT.md`.
Read both before changing code.

## Changelog - every delivery

Before the delivery commit, record what this task changed under
`## [Unreleased]` in `CHANGELOG.md`, in user language. This applies to
every delivery, not only to releases.

Assigning a version to that section makes the task a release, and a
release must then carry the same version into the project and both help
files - see `.agentic/PROJECT.md`, *Delivery - the version workflow*.

<!-- AEGIS:BEGIN (managed by .agentic/aegis.py init) -->

## AEGIS workflow

This repository uses AEGIS to guide software implementation, one feature,
fix or change per task. Before changing the product, read
`.agentic/AGENTS.md`; it routes you to one step file per stage.

- New work: run `python .agentic/aegis.py status` (an open task may cover
  it), then follow `.agentic/steps/1_frame.md`.
- An existing task: run `python .agentic/aegis.py brief TASK-<id>` and read
  what its `Read next` line names.

Stages: frame -> specify -> design -> build -> validate -> done; the quick
path is frame -> build -> validate -> done. The CLI writes the journal state:
`advance` finishes a stage, `pause` stops for the user, `log` and `ruling`
record events and decisions. End every session with `advance` or `pause`.

AEGIS guides and never blocks; `python .agentic/aegis.py check` is advisory.
Commits, pushes, merges, tickets, releases and packaging follow the
repository's own procedures, not AEGIS.

Say a deviation when you record one, as one line -
`DEVIATION <stage>: <what> - <why accepted, or what it costs>` - then carry on.

<!-- AEGIS:END -->
