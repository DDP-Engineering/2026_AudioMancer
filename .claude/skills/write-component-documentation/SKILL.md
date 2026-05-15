---
name: write-component-documentation
description: Create or update component documentation under `05_SoftwareDocu/` for this repository. Use when Codex needs to write a new software-component document, expand an existing one, or keep `05_SoftwareDocu/README.md` in sync with a new component page while following the repository template and the established `AudioMancer_Logging_Service.md` style.
---

# Write Component Documentation

Read these files before drafting the document:

- `05_SoftwareDocu/component_documentation_template.md`
- the target implementation files being documented
- `05_SoftwareDocu/README.md` if adding a new component page

Use this workflow:

1. Identify the implementation boundary.
   Determine the component's purpose, responsibilities, main public entrypoints, configuration inputs, outputs, and current tests from the actual code.
2. Follow the template structure.
   Keep the section numbering and headings from `component_documentation_template.md` unless a section is clearly irrelevant.
3. Match the established writing style.
   Write concise engineering prose, not marketing copy.
   Prefer concrete repository paths, function names, and runtime behavior over generic description.
   Use flat bullet lists where the content is naturally list-shaped.
4. Describe the current implementation truthfully.
   Do not describe planned behavior as if it already exists.
   Call out current limitations and future work explicitly in section 10.
5. Keep scope boundaries clear.
   State what the component owns and what it does not own when that prevents confusion with nearby modules.
6. Update the software-doc index.
   If a new file is added under `05_SoftwareDocu/`, add it to `05_SoftwareDocu/README.md` in the same change.

Content expectations by section:

- `1. Purpose`: explain what the component exists to do in the application.
- `2. Responsibilities`: list owned behaviors and important non-goals.
- `3. Implementation Overview`: name the key files, functions, classes, and runtime flow.
- `4. Dependencies`: separate internal dependencies from external packages or runtimes.
- `5. Inputs And Outputs`: cover config, arguments, files, produced artifacts, logs, or state changes.
- `6. Data Contracts`: document stable fields, file naming, schemas, invariants, and deterministic fallbacks if relevant.
- `7. Workflow Integration`: explain upstream callers, downstream consumers, and current in-repo usage.
- `8. Usage`: show short repo-relevant examples, not generic pseudocode unless no direct usage pattern exists.
- `9. Validation And Tests`: list focused tests and minimum validation expected after changes.
- `10. Limitations And Future Work`: keep this honest and implementation-based.

Formatting rules:

- Preserve the repository copyright header style used in other `05_SoftwareDocu/*.md` files.
- Use exact repository-relative paths in backticks when naming files.
- Keep the document compact; avoid repeating content already covered in another section.
- Prefer present tense for implemented behavior and future tense only for actual future work.

When updating an existing component document:

- preserve its title and section numbering
- replace stale statements rather than appending contradictory notes
- keep the detail level aligned with `AudioMancer_Logging_Service.md`

When creating a new component document:

- name it `05_SoftwareDocu/<Component_Name>.md` using the repository's current naming style
- add one short bullet to `05_SoftwareDocu/README.md` describing the new document
