<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: component-adoption

Load this module only while in the `component-adoption` stage.

- Work only inside the approved local component scope or approved bundle
  exception.
- Run `<workflow> adoption scope-check <paths>` for planned touched paths when
  the component manifest is available.
- Add or update component documentation, requirement links, known test commands,
  and adoption notes for the approved slice.
- Preserve behavior. If implementation changes appear necessary, stop and ask to
  switch to an `agentic-development` run.
- Record what was adopted and which gaps remain.
