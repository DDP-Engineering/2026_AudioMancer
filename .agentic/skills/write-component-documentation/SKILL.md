---
name: write-component-documentation
description: Create or update component documentation under `05_SoftwareDocu/` for a repository using this workflow template. Use when Codex needs to document a new software component, refresh an existing component document, or keep the software documentation index aligned with implementation changes.
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->


# Write Component Documentation

Use this skill when creating a new component document or updating an existing
component document after a material implementation change.

Read these files before drafting the document:

- `05_SoftwareDocu/component_documentation_template.md`
- the implementation files being documented
- `05_SoftwareDocu/README.md` if adding a new component page

Use this workflow:

1. Identify the implementation boundary.
   Determine the component's purpose, responsibilities, public entrypoints,
   configuration inputs, outputs, persistence behavior, and tests from the
   current code.
2. Follow the template structure.
   Keep the section numbering and headings from
   `component_documentation_template.md` unless a section is clearly irrelevant.
3. Match the repository writing style.
   Write concise engineering prose, not marketing copy. Prefer concrete
   repository paths, function names, commands, and runtime behavior over generic
   description.
4. Describe current truth.
   Do not describe planned behavior as implemented. Put known gaps or future
   work in section 10.
5. Keep scope boundaries clear.
   State what the component owns and what it does not own when that prevents
   confusion with nearby modules.
6. Update the software-doc index.
   If a new file is added under `05_SoftwareDocu/`, add a short entry to
   `05_SoftwareDocu/README.md` in the same change.

Content expectations by section:

- `1. Purpose`: explain what the component exists to do.
- `2. Responsibilities`: list owned behaviors and important non-goals.
- `3. Implementation Overview`: name key files, functions, classes, and flow.
- `4. Dependencies`: separate internal dependencies from external packages or
  runtimes.
- `5. Inputs And Outputs`: cover arguments, config, files, artifacts, logs, and
  state changes.
- `6. Data Contracts`: document stable fields, schemas, file naming,
  invariants, and deterministic fallbacks when relevant.
- `7. Workflow Integration`: explain upstream callers, downstream consumers, and
  in-repo usage.
- `8. Usage`: show short repo-relevant examples or command patterns.
- `9. Validation And Tests`: list focused tests and minimum validation expected
  after changes.
- `10. Limitations And Future Work`: keep this honest and implementation-based.

Formatting rules:

- Preserve the repository copyright header style used in nearby
  `05_SoftwareDocu/*.md` files.
- Use exact repository-relative paths in backticks when naming files.
- Keep the document compact and avoid repeating the same detail across sections.
- Prefer present tense for implemented behavior and future tense only for actual
  future work.

When updating an existing component document:

- preserve its title and section numbering
- replace stale statements instead of appending contradictory notes
- keep the detail level aligned with nearby component documents

When creating a new component document:

- name it `05_SoftwareDocu/<Component_Name>.md` using the repository's current
  naming style
- add one short bullet to `05_SoftwareDocu/README.md` describing the new
  document
