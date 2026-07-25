---
description: Show the active agentic workflow run status
agent: aegis
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

First validate and inspect repository policy:

```powershell
node .agentic/tools/run_hook.mjs .agentic/tools/run_aegis.py config validate --json
node .agentic/tools/run_hook.mjs .agentic/tools/run_aegis.py config show --effective --json
```

Report all effective restriction modes and active rule counts. Then run the
project-local workflow status command and summarize the selected run:

```powershell
node .agentic/tools/run_hook.mjs .agentic/tools/run_aegis.py status
```

If the operator supplies an existing run ID, append `--run-id <id>` instead of
using the worktree pointer. Report the selection source, current stage,
invariant status, and clear next prompt options. Distinguish AEGIS policy from
OpenCode host safety.
