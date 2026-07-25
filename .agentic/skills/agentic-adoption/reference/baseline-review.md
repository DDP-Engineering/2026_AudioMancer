<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Stage: baseline-review

Load this module only while in the `baseline-review` stage.

- Run `<workflow> adoption baseline` when available.
- Review whether each adopted component meets the configured baseline, such as
  documented ownership, mapped paths, known gates, and traceability.
- Classify remaining gaps as blocking, follow-up, or accepted legacy risk.
- If a future behavior-changing run targets a component below `baseline-usable`,
  stop and recommend a component adoption slice first.
- Stop with baseline status and the next safe feature or adoption prompt.
