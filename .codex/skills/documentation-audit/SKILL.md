---
name: documentation-audit
description: Review AudioMancer component documentation against the current software implementation, using broad README, HowToTest, and Overview review only when explicitly requested or when their scope changes.
---

# Documentation Audit

Use this workflow:

1. Read `AGENTS.md` and `01_Documentation/Code_Style.md`.
2. Run the deterministic audit:

   ```powershell
   python 02_Tools/audits/audit_documentation.py --changed-only
   ```

   Add `--include-broad-docs` only when the user asks for a broad
   documentation review or when the change affects repository scope, setup,
   validation workflow, operator workflow, release notes, or README-level
   navigation.
3. Inspect the implementation files reported by the tool.
4. Update stale or missing component documentation directly:
   - `05_SoftwareDocu/*.md`
   - `05_SoftwareDocu/README.md` when adding or renaming component pages
5. Update broad documentation only when the change materially affects that
   document's scope:
   - `README.MD` for repository-level scope or first-reader navigation changes
   - `04_Software/README.md` for software-folder scope changes
   - `04_Software/AudioMancer/README.MD` for app setup, run, validation, or
     packaging entry point changes
   - `0_Planning/Overview.md` for planning overview changes
   - `HowToTest*.md` for setup, validation, or operator workflow changes
6. Do not describe planned behavior as implemented. Mark limitations and future work explicitly.
7. Re-run the audit after edits and report remaining warnings that require human judgment.

When creating or updating a component document, also use `$write-component-documentation`.
