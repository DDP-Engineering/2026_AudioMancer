---
name: logging-audit
description: Check AudioMancer principal non-UI functions for logging coverage through the logging service and add missing logging only where appropriate. Use when the user asks whether generated code has matching logging coverage.
---

# Logging Audit

Use this workflow:

1. Read `AGENTS.md`, `01_Documentation/Code_Style.md`, and `05_SoftwareDocu/AudioMancer_Logging_Service.md`.
2. Run the deterministic candidate audit:

   ```powershell
   python 02_Tools/audits/audit_logging_coverage.py --changed-only
   ```

   Omit `--changed-only` for a full service scan.
3. Treat the script output as candidates, not automatic truth.
4. Exclude UI widget construction, lambdas, trivial getters/setters, tests, and pure formatting helpers.
5. Add logging only to principal functions where it improves diagnosis:
   - workflow entry points
   - file/project artifact writes or destructive changes
   - state transitions
   - external model/API/provider calls
   - long-running generation operations
   - exception paths
6. Use `audiomancer.services.logging_service.get_component_logger` and the existing logging style.
7. If code is changed, update relevant Doxygen `@version` tags and run the required compile, Ruff, and targeted tests.
8. Re-run the audit and explain any remaining candidates intentionally left without logging.
