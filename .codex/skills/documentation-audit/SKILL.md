---
name: documentation-audit
description: Review AudioMancer documentation against the current software implementation and update stale README, HowToTest, Overview, and 05_SoftwareDocu content. Use when the user asks to review, synchronize, or refresh project documentation after implementation changes.
---

# Documentation Audit

Use this workflow:

1. Read `AGENTS.md` and `01_Documentation/Code_Style.md`.
2. Run the deterministic audit:

   ```powershell
   python 02_Tools/audits/audit_documentation.py --changed-only
   ```

   Omit `--changed-only` when the user asks for a full documentation review.
3. Inspect the implementation files reported by the tool.
4. Update stale or missing documentation directly:
   - `README.MD`
   - `04_Software/README.md`
   - `04_Software/AudioMancer/README.MD`
   - `05_SoftwareDocu/*.md`
   - `05_SoftwareDocu/README.md`
   - `0_Planning/Overview.md`
   - `HowToTest*.md` when present or needed
5. Do not describe planned behavior as implemented. Mark limitations and future work explicitly.
6. Re-run the audit after edits and report remaining warnings that require human judgment.

When creating or updating a component document, also use `$write-component-documentation`.
