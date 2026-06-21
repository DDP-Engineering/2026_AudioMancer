/*
 * Copyright (c) 2026 DDP Engineering
 * This software is licensed under the PolyForm Noncommercial License 1.0.0.
 * Commercial use requires a separate commercial license.
 * See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
 */

import { describe, expect, it, vi } from "vitest";

import {
  handleToolCall,
  handleToolResult,
  type ToolCallLike,
} from "../extensions/agentic-guard/bridge";
import {
  createHookBridge,
  parseHookDecision,
  protectedPathDeny,
  type HookBridge,
  type SpawnResult,
} from "../extensions/agentic-guard/hook-bridge";

const CWD = "/repo";

/** Build a deny JSON line exactly as the Python hooks print it. */
function denyJson(reason: string): string {
  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: reason,
    },
  });
}

/** A recording HookBridge: maps hookName -> deny reason, captures every call. */
function fakeBridge(denyReasons: Record<string, string> = {}): HookBridge & {
  calls: Array<{ hookName: string; payload: Record<string, unknown> }>;
} {
  const calls: Array<{ hookName: string; payload: Record<string, unknown> }> = [];
  return {
    calls,
    async runPythonHook(_cwd, hookName, payload) {
      calls.push({ hookName, payload });
      return denyReasons[hookName] ?? null;
    },
    protectedPathDeny,
  };
}

describe("parseHookDecision", () => {
  it("returns the reason for a deny payload", () => {
    expect(parseHookDecision(denyJson("Edit outside zone"))).toBe("Edit outside zone");
  });

  it("returns null for empty stdout (allow)", () => {
    expect(parseHookDecision("")).toBeNull();
    expect(parseHookDecision("   \n")).toBeNull();
  });

  it("returns null for non-deny JSON", () => {
    expect(parseHookDecision(JSON.stringify({ hookSpecificOutput: {} }))).toBeNull();
  });

  it("falls back to the last non-empty line when stdout has noise", () => {
    const stdout = `warning: something\n${denyJson("Possible secret detected")}`;
    expect(parseHookDecision(stdout)).toBe("Possible secret detected");
  });

  it("uses a default reason when deny omits a reason string", () => {
    const stdout = JSON.stringify({
      hookSpecificOutput: { permissionDecision: "deny" },
    });
    expect(parseHookDecision(stdout)).toBe("Blocked by agentic workflow guard.");
  });
});

describe("protectedPathDeny", () => {
  it.each([".env", ".env.local", "config/app.env", "deep/dir/server.pem", "tls.key", "deploy/id_rsa", "secrets.p12"])(
    "blocks reading %s",
    (path) => {
      expect(protectedPathDeny(path, CWD)).not.toBeNull();
    },
  );

  it.each(["src/app.py", "README.md", "tests/test_app.py", "envfile.txt"])(
    "allows reading %s",
    (path) => {
      expect(protectedPathDeny(path, CWD)).toBeNull();
    },
  );

  it("allows an undefined path", () => {
    expect(protectedPathDeny(undefined, CWD)).toBeNull();
  });
});

describe("handleToolCall mapping", () => {
  it("maps write to guard_write_zone with file_path, then secret_scan with full input", async () => {
    const bridge = fakeBridge();
    const event: ToolCallLike = {
      toolName: "write",
      toolCallId: "t1",
      input: { path: "src/app.py", content: "print('ok')\n" },
    };

    const result = await handleToolCall(event, CWD, bridge);

    expect(result).toBeUndefined();
    expect(bridge.calls).toHaveLength(2);
    expect(bridge.calls[0].hookName).toBe("guard_write_zone.py");
    expect(bridge.calls[0].payload).toMatchObject({
      hook_event_name: "PreToolUse",
      tool_name: "Write",
      tool_input: { file_path: "src/app.py" },
      cwd: CWD,
    });
    expect(bridge.calls[1].hookName).toBe("secret_scan.py");
    expect(bridge.calls[1].payload.tool_input).toEqual({
      path: "src/app.py",
      content: "print('ok')\n",
    });
  });

  it("blocks a write outside the write zone and never reaches secret_scan", async () => {
    const bridge = fakeBridge({ "guard_write_zone.py": "Edit outside 'implementation' write zone: tests/x.py" });
    const event: ToolCallLike = {
      toolName: "write",
      toolCallId: "t2",
      input: { path: "tests/x.py", content: "x" },
    };

    const result = await handleToolCall(event, CWD, bridge);

    expect(result).toEqual({
      block: true,
      reason: "Edit outside 'implementation' write zone: tests/x.py",
    });
    expect(bridge.calls.map((c) => c.hookName)).toEqual(["guard_write_zone.py"]);
  });

  it("blocks a write whose content trips secret_scan", async () => {
    const bridge = fakeBridge({ "secret_scan.py": "Possible secret detected in tool input." });
    const event: ToolCallLike = {
      toolName: "write",
      toolCallId: "t3",
      input: { path: "src/app.py", content: "token = sk-aaaaaaaaaaaaaaaaaaaaaaaa" },
    };

    const result = await handleToolCall(event, CWD, bridge);

    expect(result).toEqual({ block: true, reason: "Possible secret detected in tool input." });
    expect(bridge.calls.map((c) => c.hookName)).toEqual(["guard_write_zone.py", "secret_scan.py"]);
  });

  it("maps edit to the Edit tool name", async () => {
    const bridge = fakeBridge();
    await handleToolCall(
      { toolName: "edit", toolCallId: "t4", input: { path: "src/app.py", edits: [] } },
      CWD,
      bridge,
    );
    expect(bridge.calls[0].payload.tool_name).toBe("Edit");
  });

  it("runs secret_scan then delivery_preflight for bash and blocks on preflight", async () => {
    const bridge = fakeBridge({ "delivery_preflight.py": "Delivery preflight failed." });
    const event: ToolCallLike = {
      toolName: "bash",
      toolCallId: "t5",
      input: { command: "git push origin main" },
    };

    const result = await handleToolCall(event, CWD, bridge);

    expect(result).toEqual({ block: true, reason: "Delivery preflight failed." });
    expect(bridge.calls.map((c) => c.hookName)).toEqual(["secret_scan.py", "delivery_preflight.py"]);
    expect(bridge.calls[0].payload).toMatchObject({
      tool_name: "Bash",
      tool_input: { command: "git push origin main" },
    });
  });

  it("blocks a read of a protected path natively (no Python call)", async () => {
    const bridge = fakeBridge();
    const result = await handleToolCall(
      { toolName: "read", toolCallId: "t6", input: { path: ".env" } },
      CWD,
      bridge,
    );
    expect(result).toMatchObject({ block: true });
    expect(bridge.calls).toHaveLength(0);
  });

  it("allows a read of an ordinary file", async () => {
    const bridge = fakeBridge();
    const result = await handleToolCall(
      { toolName: "read", toolCallId: "t7", input: { path: "src/app.py" } },
      CWD,
      bridge,
    );
    expect(result).toBeUndefined();
  });

  it("ignores unrelated tools", async () => {
    const bridge = fakeBridge();
    const result = await handleToolCall(
      { toolName: "grep", toolCallId: "t8", input: { pattern: "x" } },
      CWD,
      bridge,
    );
    expect(result).toBeUndefined();
    expect(bridge.calls).toHaveLength(0);
  });
});

describe("handleToolResult", () => {
  it("records post-tool evidence for any tool", async () => {
    const bridge = fakeBridge();
    await handleToolResult(
      { toolName: "write", toolCallId: "t9", content: [{ type: "text", text: "ok" }] },
      CWD,
      bridge,
    );
    expect(bridge.calls).toHaveLength(1);
    expect(bridge.calls[0].hookName).toBe("post_tool_evidence.py");
    expect(bridge.calls[0].payload).toMatchObject({
      hook_event_name: "PostToolUse",
      tool_name: "write",
      tool_use_id: "t9",
    });
    expect(bridge.calls[0].payload.tool_response).not.toBeNull();
  });
});

describe("createHookBridge.runPythonHook", () => {
  it("invokes the interpreter with the hook path and JSON payload, returning the deny reason", async () => {
    const spawn = vi.fn(async (): Promise<SpawnResult> => ({
      stdout: denyJson("blocked"),
      stderr: "",
      code: 0,
    }));
    const bridge = createHookBridge({
      spawn,
      interpreter: { command: "py", args: ["-3"] },
    });

    const reason = await bridge.runPythonHook(CWD, "guard_write_zone.py", { a: 1 });

    expect(reason).toBe("blocked");
    expect(spawn).toHaveBeenCalledTimes(1);
    const [command, args, input, cwd] = spawn.mock.calls[0];
    expect(command).toBe("py");
    expect(args[0]).toBe("-3");
    expect(args[1]).toContain("guard_write_zone.py");
    expect(JSON.parse(input as string)).toEqual({ a: 1 });
    expect(cwd).toBe(CWD);
  });

  it("returns null on empty stdout (allow)", async () => {
    const bridge = createHookBridge({
      spawn: async () => ({ stdout: "", stderr: "", code: 0 }),
      interpreter: { command: "python3", args: [] },
    });
    expect(await bridge.runPythonHook(CWD, "secret_scan.py", {})).toBeNull();
  });

  it("fails open (null) when the interpreter cannot be spawned", async () => {
    const bridge = createHookBridge({
      spawn: async () => {
        throw new Error("ENOENT");
      },
      interpreter: { command: "py", args: ["-3"] },
    });
    expect(await bridge.runPythonHook(CWD, "secret_scan.py", {})).toBeNull();
  });
});
