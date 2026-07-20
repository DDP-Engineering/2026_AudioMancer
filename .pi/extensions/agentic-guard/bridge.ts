/*
 * Copyright (c) 2026 DDP Engineering
 * This software is licensed under the PolyForm Noncommercial License 1.0.0.
 * Commercial use requires a separate commercial license.
 * See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
 */

/**
 * bridge.ts
 *
 * Pure mapping of Pi tool events onto the shared Python guard hooks. Kept free
 * of any `@earendil-works/pi-coding-agent` import so it can be unit-tested with a
 * mocked {@link HookBridge}. `index.ts` wires these handlers to `pi.on(...)`.
 *
 * Mapping (PreToolUse via `tool_call`):
 *   write -> guard_write_zone.py (Write), then secret_scan.py (full input)
 *   edit  -> guard_write_zone.py (Edit),  then secret_scan.py (full input)
 *   bash  -> secret_scan.py (Bash), then delivery_preflight.py (Bash)
 *   read  -> native protected-path deny (no Python equivalent)
 * PostToolUse via `tool_result`:
 *   any   -> post_tool_evidence.py (fire-and-forget)
 */

import type { HookBridge } from "./hook-bridge";

/** Minimal shape of a Pi `tool_call` event (structural subset of ToolCallEvent). */
export interface ToolCallLike {
  toolName: string;
  toolCallId: string;
  input: Record<string, unknown>;
}

/** Minimal shape of a Pi `tool_result` event (structural subset of ToolResultEvent). */
export interface ToolResultLike {
  toolName: string;
  toolCallId: string;
  content?: unknown;
}

/** Block decision returned to Pi to stop a tool call. */
export interface BlockResult {
  block: true;
  reason: string;
}

/**
 * Translate a `tool_call` event into the matching Python guard hook(s) and
 * return a block decision, or `undefined` to allow the call.
 */
export async function handleToolCall(
  event: ToolCallLike,
  cwd: string,
  bridge: HookBridge,
): Promise<BlockResult | undefined> {
  switch (event.toolName) {
    case "write":
    case "edit": {
      const toolName = event.toolName === "write" ? "Write" : "Edit";
      const path = event.input?.path;

      const zoneReason = await bridge.runPythonHook(cwd, "guard_write_zone.py", {
        hook_event_name: "PreToolUse",
        tool_name: toolName,
        tool_input: { file_path: path },
        cwd,
      });
      if (zoneReason) return { block: true, reason: zoneReason };

      // Pass the full input so secrets in file *content* are caught too, not
      // just the path, matching the edit-content scan used by every adapter.
      const secretReason = await bridge.runPythonHook(cwd, "secret_scan.py", {
        hook_event_name: "PreToolUse",
        tool_name: toolName,
        tool_input: event.input,
        cwd,
      });
      if (secretReason) return { block: true, reason: secretReason };
      return undefined;
    }

    case "bash": {
      const command = event.input?.command;
      for (const hook of ["secret_scan.py", "delivery_preflight.py"]) {
        const reason = await bridge.runPythonHook(cwd, hook, {
          hook_event_name: "PreToolUse",
          tool_name: "Bash",
          tool_input: { command },
          cwd,
        });
        if (reason) return { block: true, reason };
      }
      return undefined;
    }

    case "read": {
      const reason = bridge.protectedPathDeny(event.input?.path as string | undefined, cwd);
      if (reason) return { block: true, reason };
      return undefined;
    }

    default:
      return undefined;
  }
}

/**
 * Record post-tool evidence for any tool. `post_tool_evidence.py` is a no-op
 * when there is no active `.agentic` run, so this is safe to call unconditionally.
 */
export async function handleToolResult(
  event: ToolResultLike,
  cwd: string,
  bridge: HookBridge,
): Promise<void> {
  await bridge.runPythonHook(cwd, "post_tool_evidence.py", {
    hook_event_name: "PostToolUse",
    tool_name: event.toolName,
    tool_use_id: event.toolCallId,
    tool_response: event.content ?? null,
    cwd,
  });
}
