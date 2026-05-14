---
name: codestyle-audit
description: Review and update AudioMancer Python code style against AGENTS.md and Code_Style.md, including module prologues, Doxygen file tags, section markers, function/class docstrings, and local @version tags.
---

# Code Style Audit

Use this workflow:

1. Read `AGENTS.md` and `01_Documentation/Code_Style.md`.
2. Run the deterministic audit:

   ```powershell
   python 02_Tools/audits/audit_codestyle.py --changed-only
   ```

   Omit `--changed-only` for a full repository scan.
3. Fix reported Python style issues directly when they are mechanical:
   - required prologue
   - module doc tags
   - meaningful section markers
   - public/non-trivial callable Doxygen docstrings
   - callable-local `@version` tags
4. When changing a callable implementation or documentation, update that callable's local `@version`.
5. When adding or removing a function, class, or documented nested helper, update the module-level `@version`.
6. Validate changed Python files with:

   ```powershell
   uv run python -m py_compile <changed_file.py>
   uv run ruff check <changed_python_files> --fix
   uv run ruff format <changed_python_files>
   ```

7. Re-run the audit and report remaining issues.
