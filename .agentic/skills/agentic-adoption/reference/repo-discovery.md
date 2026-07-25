<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: repo-discovery

Load this module only while in the `repo-discovery` stage.

- Inventory configured source roots, test roots, requirement snapshot roots,
  documentation roots, gate commands, and adapters.
- Run `<workflow> audit traceability` and `<workflow> audit coverage` when the
  current configuration can support them.
- Identify likely components, owners, boundaries, external dependencies,
  important entry points, and existing tests.
- Do not rewrite application code while discovering.
- Stop with the discovered repo shape and recommended component-map updates.
