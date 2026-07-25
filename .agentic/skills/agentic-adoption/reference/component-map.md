<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: component-map

Load this module only while in the `component-map` stage.

- Create or update `.agentic/components.toml` with component names, paths,
  status, baseline notes, and approved bundles when applicable.
- Use `<workflow> adoption component-status` and `<workflow> adoption baseline`
  to review the map when those commands are available.
- Mark unknown or risky areas honestly instead of stretching a component
  boundary to make the map look complete.
- Present the component map approval gate. Do not continue to
  component-adoption until the human approves the map or a specific slice.
- Stop with the proposed map, unresolved questions, and exact approval prompt.
