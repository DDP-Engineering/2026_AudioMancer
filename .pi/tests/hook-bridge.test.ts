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
  decideFromResult,
  interpreterCandidates,
  parseHookDecision,
  NO_INTERPRETER_REASON,
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

  it("runs guard_shell_write, secret_scan then delivery_preflight for bash and blocks on preflight", async () => {
    const bridge = fakeBridge({ "delivery_preflight.py": "Delivery preflight failed." });
    const event: ToolCallLike = {
      toolName: "bash",
      toolCallId: "t5",
      input: { command: "git push origin main" },
    };

    const result = await handleToolCall(event, CWD, bridge);

    expect(result).toEqual({ block: true, reason: "Delivery preflight failed." });
    expect(bridge.calls.map((c) => c.hookName)).toEqual([
      "guard_shell_write.py",
      "secret_scan.py",
      "delivery_preflight.py",
    ]);
    expect(bridge.calls[0].payload).toMatchObject({
      tool_name: "Bash",
      tool_input: { command: "git push origin main" },
    });
  });

  it("routes reads through the shared configured Python hook", async () => {
    const bridge = fakeBridge({ "guard_read_path.py": "Reading configured protected path is blocked: private/data" });
    const result = await handleToolCall(
      { toolName: "read", toolCallId: "t6", input: { path: "private/data" } },
      CWD,
      bridge,
    );
    expect(result).toEqual({
      block: true,
      reason: "Reading configured protected path is blocked: private/data",
    });
    expect(bridge.calls).toHaveLength(1);
    expect(bridge.calls[0]).toMatchObject({
      hookName: "guard_read_path.py",
      payload: {
        hook_event_name: "PreToolUse",
        // The real Pi tool name, not a hardcoded "Read": the shared guard keys
        // its strictness off it, denying a read that names no file while
        // allowing an unscoped search.
        tool_name: "read",
        tool_input: { path: "private/data" },
        cwd: CWD,
      },
    });
  });

  it.each([
    ["grep", { path: "private" }, { path: "private" }],
    ["ls", { path: "private" }, { path: "private" }],
    ["find", { pattern: "private/**" }, { pattern: "private/**" }],
  ])("routes %s through the protected-read hook", async (toolName, input, expected) => {
    // A protected-read policy enforced only on `read` was bypassable by asking
    // Pi for the same bytes through `grep`, and for the file names through
    // `find` or `ls`. Pi's built-in set is read/grep/find/ls — no glob or list.
    const bridge = fakeBridge({ "guard_read_path.py": "blocked" });

    const result = await handleToolCall(
      { toolName, toolCallId: "t-search", input },
      CWD,
      bridge,
    );

    expect(result).toEqual({ block: true, reason: "blocked" });
    expect(bridge.calls).toHaveLength(1);
    expect(bridge.calls[0]).toMatchObject({
      hookName: "guard_read_path.py",
      payload: { tool_name: toolName, tool_input: expected },
    });
  });

  it("allows a read of an ordinary file", async () => {
    const bridge = fakeBridge();
    const result = await handleToolCall(
      { toolName: "read", toolCallId: "t7", input: { path: "src/app.py" } },
      CWD,
      bridge,
    );
    expect(result).toBeUndefined();
    expect(bridge.calls.map((c) => c.hookName)).toEqual(["guard_read_path.py"]);
  });

  it("ignores unrelated tools", async () => {
    // `grep` used to stand in for "unrelated" here, which is exactly the
    // protected-read bypass this suite now covers above: it reads file content
    // and is routed to the guard. A tool that touches no repository file is the
    // right example of one the bridge should ignore.
    const bridge = fakeBridge();
    const result = await handleToolCall(
      { toolName: "todowrite", toolCallId: "t8", input: { items: [] } },
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

  it("fails closed when the interpreter cannot be spawned", async () => {
    const bridge = createHookBridge({
      spawn: async () => {
        throw new Error("ENOENT");
      },
      interpreter: { command: "py", args: ["-3"] },
    });
    const reason = await bridge.runPythonHook(CWD, "secret_scan.py", {});
    expect(reason).toContain("could not run secret_scan.py");
    expect(reason).toContain("ENOENT");
  });

  it("fails closed when no interpreter could be resolved", async () => {
    const spawn = vi.fn();
    const bridge = createHookBridge({ spawn, interpreter: null });
    expect(await bridge.runPythonHook(CWD, "guard_write_zone.py", {})).toBe(NO_INTERPRETER_REASON);
    // A guard that cannot run must never reach the spawn path and report allow.
    expect(spawn).not.toHaveBeenCalled();
  });

  it("fails closed when the hook exits non-zero without a decision", async () => {
    const bridge = createHookBridge({
      spawn: async () => ({
        stdout: "",
        stderr: "Traceback (most recent call last):\nValueError: broken policy",
        code: 1,
      }),
      interpreter: { command: "python3", args: [] },
    });
    const reason = await bridge.runPythonHook(CWD, "guard_read_path.py", {});
    expect(reason).toContain("guard_read_path.py exited with status 1");
    expect(reason).toContain("ValueError: broken policy");
  });
});

describe("decideFromResult", () => {
  it("allows only on a clean exit with no denial", () => {
    expect(decideFromResult("secret_scan.py", { stdout: "", stderr: "", code: 0 })).toBeNull();
  });

  it("prefers an explicit denial over the exit status", () => {
    expect(
      decideFromResult("secret_scan.py", { stdout: denyJson("Possible secret"), stderr: "", code: 0 }),
    ).toBe("Possible secret");
  });

  it("blocks a non-zero exit even when stderr is empty", () => {
    const reason = decideFromResult("delivery_preflight.py", { stdout: "", stderr: "", code: 9 });
    expect(reason).toContain("exited with status 9");
    expect(reason).toContain("no diagnostic output");
  });
});

describe("interpreter resolution parity", () => {
  it("offers the same ordered launchers as the shared run_hook.mjs launcher", () => {
    const expected = process.platform === "win32"
      ? [{ command: "py", args: ["-3"] }, { command: "python", args: [] }]
      : [{ command: "python3", args: [] }, { command: "python", args: [] }];
    expect(interpreterCandidates()).toEqual(expected);
  });
});
