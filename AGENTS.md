<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AGENTS.md

AudioMancer uses **AEGIS Light**: a companion engineering workflow that
advises and records but never blocks. The full contract is
`.agentic/AGENTS.md`; this repository's own rules - the binding code
style and the release version workflow - are in `.agentic/PROJECT.md`.
Read both before changing code.

<!-- AEGIS-LIGHT:BEGIN (managed by .agentic/aegis.py init) -->

## AEGIS Light workflow

The full contract is `.agentic/AGENTS.md` - read it before starting work.
This digest is enough to act on if you read nothing else.

Stages, one step file each in `.agentic/steps/`: **frame** (agree scope,
open the task journal) -> **specify** (write the requirement, and a spec
when useful) -> **design** (a short note for non-trivial work) -> **build**
(failing test first, then the implementation, until green) -> **validate**
(review, knowledge, full suite and strict check) -> **deliver** (approval,
report, commit/PR). A small fix or change may take the quick path,
frame -> build -> validate -> deliver.

To resume: `python .agentic/aegis.py status` lists the task journals; open
`.agentic/tasks/TASK-<id>.md`, read its `stage:` line and `## Log`, open
that stage's step file, and continue at the first unticked item of
`## Done checklist`.

Artifacts: requirements in `.agentic/requirements/<category>/`, specs in
`.agentic/specs/`, journals in `.agentic/tasks/`, component pages in
`.agentic/knowledge/`. `python .agentic/aegis.py check` is advisory - read
its findings and self-correct; nothing here blocks you mid-flight.

<!-- AEGIS-LIGHT:END -->

## Changelog - every delivery

Before the delivery commit, record what this task changed under
`## [Unreleased]` in `CHANGELOG.md`, in user language. This applies to
every delivery, not only to releases.

Assigning a version to that section makes the task a release, and a
release must then carry the same version into the project and both help
files - see `.agentic/PROJECT.md`, *Delivery - the version workflow*.
