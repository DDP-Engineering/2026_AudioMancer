---
description: Run the agentic workflow delivery preflight
agent: agentic-workflow
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

Run the project-local delivery preflight command:

```powershell
python .agentic/tools/run_agentic_workflow.py delivery-preflight
```

Report pass or fail with the blocking findings. Do not push, merge, publish, or
create a pull request unless preflight passes and the human explicitly approves.
