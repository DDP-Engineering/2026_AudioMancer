/*
 * Copyright (c) 2026 DDP Engineering
 * This software is licensed under the PolyForm Noncommercial License 1.0.0.
 * Commercial use requires a separate commercial license.
 * See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  AgenticGuard,
  createHookRunner,
  decideFromResult,
  interpreterCandidates,
  parseHookDecision,
  NO_INTERPRETER_REASON,
} from "../plugins/agentic-guard.mjs";

test("parseHookDecision returns deny reason from hook stdout", () => {
  const stdout = JSON.stringify({
    hookSpecificOutput: {
      permissionDecision: "deny",
      permissionDecisionReason: "blocked",
    },
  });

  assert.equal(parseHookDecision(stdout), "blocked");
});

test("read tools use the shared configured Python hook", async () => {
  const calls = [];
  const hooks = await AgenticGuard(
    { directory: "/repo" },
    {
      cwd: "/repo",
      runPythonHook: async (hook, payload) => {
        calls.push({ hook, payload });
        return null;
      },
    },
  );

  await hooks["tool.execute.before"](
    { tool: "read" },
    { args: { filePath: "private/data.json" } },
  );

  assert.equal(calls.length, 1);
  assert.equal(calls[0].hook, "guard_read_path.py");
  // The real tool name is forwarded, not a hardcoded "Read": the shared guard
  // keys its strictness off it, denying a read that names no file while
  // allowing an unscoped search.
  assert.equal(calls[0].payload.tool_name, "read");
  assert.equal(calls[0].payload.tool_input.file_path, "private/data.json");
});

test("grep, glob and list run the protected-read hook too", async () => {
  // A protected-read policy enforced only on `read` was bypassable by asking
  // OpenCode for the same bytes through `grep`, and for the file names through
  // `glob` or `list`.
  for (const [tool, args, expectedInput] of [
    ["grep", { path: "private" }, { file_path: "private" }],
    ["glob", { pattern: "private/**" }, { pattern: "private/**" }],
    ["list", { path: "private" }, { file_path: "private" }],
  ]) {
    const calls = [];
    const hooks = await AgenticGuard(
      { directory: "/repo" },
      {
        cwd: "/repo",
        runPythonHook: async (hook, payload) => {
          calls.push({ hook, payload });
          return null;
        },
      },
    );

    await hooks["tool.execute.before"]({ tool }, { args });

    assert.equal(calls.length, 1, `${tool} should reach exactly one hook`);
    assert.equal(calls[0].hook, "guard_read_path.py");
    assert.equal(calls[0].payload.tool_name, tool);
    for (const [key, value] of Object.entries(expectedInput)) {
      assert.equal(calls[0].payload.tool_input[key], value);
    }
  }
});

test("a blocked search throws instead of returning the reason", async () => {
  const hooks = await AgenticGuard(
    { directory: "/repo" },
    { cwd: "/repo", runPythonHook: async () => "protected path" },
  );

  await assert.rejects(
    () => hooks["tool.execute.before"]({ tool: "grep" }, { args: { path: "private" } }),
    /protected path/,
  );
});

test("write tools run write-zone and secret hooks", async () => {
  const calls = [];
  const hooks = await AgenticGuard(
    { directory: "/repo" },
    {
      cwd: "/repo",
      runPythonHook: async (hook, payload) => {
        calls.push({ hook, payload });
        return null;
      },
    },
  );

  await hooks["tool.execute.before"](
    { tool: "write" },
    { args: { filePath: "src/app.py", content: "print('ok')" } },
  );

  assert.deepEqual(
    calls.map((call) => call.hook),
    ["guard_write_zone.py", "secret_scan.py"],
  );
  assert.equal(calls[0].payload.tool_name, "Write");
  assert.equal(calls[0].payload.tool_input.file_path, "src/app.py");
});

test("bash tools run shell-write, secret and delivery hooks", async () => {
  const calls = [];
  const hooks = await AgenticGuard(
    { directory: "/repo" },
    {
      cwd: "/repo",
      runPythonHook: async (hook, payload) => {
        calls.push({ hook, payload });
        return null;
      },
    },
  );

  await hooks["tool.execute.before"](
    { tool: "bash" },
    { args: { command: "git push origin main" } },
  );

  assert.deepEqual(
    calls.map((call) => call.hook),
    ["guard_shell_write.py", "secret_scan.py", "delivery_preflight.py"],
  );
  assert.equal(calls[0].payload.tool_name, "Bash");
  assert.equal(calls[0].payload.tool_input.command, "git push origin main");
});

test("hook deny reasons block the tool call", async () => {
  const hooks = await AgenticGuard(
    { directory: "/repo" },
    {
      cwd: "/repo",
      runPythonHook: async () => "blocked by hook",
    },
  );

  await assert.rejects(
    hooks["tool.execute.before"]({ tool: "edit" }, { args: { filePath: "src/app.py" } }),
    /blocked by hook/,
  );
});

test("decideFromResult allows only on a clean exit with no denial", () => {
  assert.equal(decideFromResult("secret_scan.py", { stdout: "", stderr: "", code: 0 }), null);
});

test("decideFromResult blocks a non-zero exit that printed no decision", () => {
  const reason = decideFromResult("guard_read_path.py", {
    stdout: "",
    stderr: "Traceback (most recent call last):\nValueError: broken policy",
    code: 1,
  });

  assert.match(reason, /guard_read_path\.py exited with status 1/);
  assert.match(reason, /ValueError: broken policy/);
});

test("decideFromResult prefers an explicit denial over the exit status", () => {
  const stdout = JSON.stringify({
    hookSpecificOutput: { permissionDecision: "deny", permissionDecisionReason: "blocked" },
  });

  assert.equal(decideFromResult("secret_scan.py", { stdout, stderr: "", code: 0 }), "blocked");
});

test("a missing interpreter blocks instead of allowing, and never spawns", async () => {
  let spawned = 0;
  const runPythonHook = createHookRunner("/repo", {
    interpreter: null,
    spawn: async () => {
      spawned += 1;
      return { stdout: "", stderr: "", code: 0 };
    },
  });

  assert.equal(await runPythonHook("guard_write_zone.py", {}), NO_INTERPRETER_REASON);
  assert.equal(spawned, 0);
});

test("a guard that cannot be spawned blocks the tool call", async () => {
  const hooks = await AgenticGuard(
    { directory: "/repo" },
    {
      cwd: "/repo",
      runPythonHook: createHookRunner("/repo", {
        interpreter: { command: "python3", args: [] },
        spawn: async () => {
          throw new Error("ENOENT");
        },
      }),
    },
  );

  await assert.rejects(
    hooks["tool.execute.before"]({ tool: "edit" }, { args: { filePath: "src/app.py" } }),
    /could not run guard_write_zone\.py.*ENOENT/s,
  );
});

test("interpreter candidates match the shared run_hook.mjs launcher order", () => {
  const expected = process.platform === "win32"
    ? [{ command: "py", args: ["-3"] }, { command: "python", args: [] }]
    : [{ command: "python3", args: [] }, { command: "python", args: [] }];

  assert.deepEqual(interpreterCandidates(), expected);
});

test("after tools record evidence", async () => {
  const calls = [];
  const hooks = await AgenticGuard(
    { directory: "/repo" },
    {
      cwd: "/repo",
      runPythonHook: async (hook, payload) => {
        calls.push({ hook, payload });
        return null;
      },
    },
  );

  await hooks["tool.execute.after"](
    { tool: "bash", toolCallId: "call-1" },
    { output: "ok" },
  );

  assert.equal(calls.length, 1);
  assert.equal(calls[0].hook, "post_tool_evidence.py");
  assert.equal(calls[0].payload.hook_event_name, "PostToolUse");
  assert.equal(calls[0].payload.tool_use_id, "call-1");
});
