<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: adoption-intake

Load this module only while in the `adoption-intake` stage.

- Classify the request as existing-project adoption, component adoption, or
  feature work blocked by adoption.
- Run `<workflow> start --kind adoption --statement "<request>"` if no active
  adoption run exists.
- Read `AGENTS.md`, `.agentic/workflow.toml`, and existing adoption or component
  files when present.
- Confirm the intended adoption slice. Default to one component.
- If a bundle is requested, ask for explicit approval and record why the bundled
  components must be adopted together.
- Run `<workflow> next` to enter `adoption-alignment` when alignment is enabled
  by `.agentic/workflow.toml`.
- Stop with the current scope, uncertainties, and next prompt options.
