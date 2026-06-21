/*
 * Copyright (c) 2026 DDP Engineering
 * This software is licensed under the PolyForm Noncommercial License 1.0.0.
 * Commercial use requires a separate commercial license.
 * See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
 */

/**
 * Pi adapter extension for the agentic workflow template.
 *
 * Subscribes to Pi's `tool_call` (PreToolUse) and `tool_result` (PostToolUse)
 * events and bridges them to the shared, byte-for-byte Python guard hooks under
 * `.agentic/hooks/`. The gate contract, required order, and stop format come
 * from `AGENTS.md`, which Pi reads natively; this extension only enforces the
 * write-zone, secret, delivery-preflight, protected-read, and evidence guards.
 *
 * Auto-discovered as `.pi/extensions/agentic-guard/index.ts` after the project
 * is trusted, and as a Pi package via the `pi.extensions` manifest entry.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { handleToolCall, handleToolResult } from "./bridge";
import { createHookBridge } from "./hook-bridge";

export default function (pi: ExtensionAPI): void {
  const bridge = createHookBridge();

  pi.on("tool_call", async (event, ctx) => handleToolCall(event, ctx.cwd, bridge));

  pi.on("tool_result", async (event, ctx) => {
    await handleToolResult(event, ctx.cwd, bridge);
  });
}
