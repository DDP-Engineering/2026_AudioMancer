---
description: Generate the agentic workflow delivery report
agent: aegis
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

Validate and inspect policy first, reporting all effective restriction modes
and active rule counts. Then run the project-local workflow report command:

```powershell
node .agentic/tools/run_hook.mjs .agentic/tools/run_aegis.py delivery report
```

If the operator supplies an existing run ID, append `--run <id>`. Report
whether selection was explicit or worktree-local and distinguish AEGIS policy
from OpenCode host safety.

Summarize the report path and the remaining delivery risks, if any.
