---
description: Run AEGIS deterministic verification before delivery
---

<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

Validate and inspect policy first, reporting all effective restriction modes
and active rule counts:

```powershell
node .agentic/tools/run_hook.mjs .agentic/tools/run_aegis.py config validate --json
node .agentic/tools/run_hook.mjs .agentic/tools/run_aegis.py config show --json
```

Then run deterministic verification and inspect delivery state:

```powershell
node .agentic/tools/run_hook.mjs .agentic/tools/run_aegis.py verify run
node .agentic/tools/run_hook.mjs .agentic/tools/run_aegis.py delivery show
```

If the operator supplies an existing run ID, append `--run <id>` and use the
same selection for the report. Distinguish AEGIS policy from Qwen host safety.
Report pass or fail with every gate state and blocking finding. Do not push,
merge, publish, or create a pull request unless AEGIS delivery is closed and the
human separately approves.
