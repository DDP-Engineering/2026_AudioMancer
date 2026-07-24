/*
 * Copyright (c) 2026 DDP Engineering
 * This software is licensed under the PolyForm Noncommercial License 1.0.0.
 * Commercial use requires a separate commercial license.
 * See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
 */

/**
 * agentic-guard.mjs
 *
 * OpenCode plugin that maps tool.execute.before/after events onto the shared
 * `.agentic/hooks/` Python guard scripts. The Python hooks are reused
 * byte-for-byte; this file is only the OpenCode transport adapter.
 *
 * Interpreter resolution and the fail-closed decision contract are kept
 * identical to `.agentic/tools/run_hook.mjs` (the Claude Code / Codex / Qwen
 * Code launcher) and to `.pi/extensions/agentic-guard/hook-bridge.ts`, so one
 * repository policy cannot resolve to a different interpreter — or to a
 * different answer — depending on which agent is driving.
 */

import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, join } from "node:path";

/** Actionable reason used whenever no interpreter can be resolved. */
export const NO_INTERPRETER_REASON =
  "AEGIS guard could not run: no Python runtime was found. "
  + "Set AEGIS_PYTHON to an interpreter, or run a packaged WAEGIS command to register one.";

export function pathCommandExists(command) {
  if (command.includes("/") || command.includes("\\")) return existsSync(command);
  const extensions = process.platform === "win32"
    ? (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";")
    : [""];
  return (process.env.PATH || "").split(delimiter).some((directory) =>
    extensions.some((extension) => existsSync(join(directory, command + extension))),
  );
}

/**
 * System launcher candidates, in order. Must match `interpreterCandidates()`
 * in `.agentic/tools/run_hook.mjs`.
 */
export function interpreterCandidates() {
  return process.platform === "win32"
    ? [{ command: "py", args: ["-3"] }, { command: "python", args: [] }]
    : [{ command: "python3", args: [] }, { command: "python", args: [] }];
}

export function resolveInterpreter() {
  const override = process.env.AEGIS_PYTHON;
  if (override && override.trim()) return { command: override.trim(), args: [] };
  const home = process.env.WAEGIS_HOME
    ?? (process.platform === "win32"
      ? join(process.env.APPDATA ?? join(homedir(), "AppData", "Roaming"), "waegis")
      : join(homedir(), ".config", "waegis"));
  try {
    const registered = readFileSync(join(home, "runtime-python"), "utf8").trim();
    if (registered && existsSync(registered)) return { command: registered, args: [] };
  } catch {
    // No valid registered WAEGIS runtime; continue with system launchers.
  }
  // Bare `python` on Windows resolves to the Microsoft Store alias stub when no
  // real interpreter is installed: it spawns successfully, exits non-zero, and
  // writes nothing to stdout. Probing PATH first keeps that from being mistaken
  // for a guard that ran and allowed.
  return interpreterCandidates().find(({ command }) => pathCommandExists(command)) ?? null;
}

export function defaultSpawn(command, args, input, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, windowsHide: true });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => resolve({ stdout, stderr, code: code ?? 0 }));
    child.stdin.on("error", () => {
      /* ignore EPIPE when a hook exits before reading stdin */
    });
    child.stdin.write(input);
    child.stdin.end();
  });
}

export function parseHookDecision(stdout) {
  const text = (stdout ?? "").trim();
  if (!text) return null;
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    const lastLine = text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .pop();
    if (!lastLine) return null;
    try {
      data = JSON.parse(lastLine);
    } catch {
      return null;
    }
  }
  const output = data?.hookSpecificOutput;
  if (output?.permissionDecision === "deny") {
    return output.permissionDecisionReason || "Blocked by agentic workflow guard.";
  }
  return null;
}

export function normalizeToolName(name) {
  const value = String(name ?? "").toLowerCase();
  if (value === "patch") return "apply_patch";
  return value;
}

/**
 * OpenCode tools that expose repository file content or file names, and the
 * tool name each is reported to the shared guard as. The guard keys its
 * strictness off the name: a `read` that names no file is a malformed read and
 * is denied, while a `grep` without a scope is a whole-repository search and is
 * allowed.
 */
export const OPENCODE_TOOL_NAMES = {
  read: "read",
  grep: "grep",
  glob: "glob",
  list: "list",
};

export const READ_LIKE_TOOLS = new Set(Object.keys(OPENCODE_TOOL_NAMES));

export function pathFromArgs(args = {}) {
  return args.filePath ?? args.file_path ?? args.path ?? args.filename;
}

export function commandFromArgs(args = {}) {
  return args.command ?? args.cmd ?? args.script ?? "";
}

export function hookPayload(cwd, hookEventName, toolName, toolInput, toolUseId, toolResponse) {
  const payload = {
    hook_event_name: hookEventName,
    tool_name: toolName,
    tool_input: toolInput,
    cwd,
  };
  if (toolUseId) payload.tool_use_id = toolUseId;
  if (toolResponse !== undefined) payload.tool_response = toolResponse;
  return payload;
}

/**
 * Turn one completed hook run into a block reason, or `null` to allow.
 *
 * The shared Python guards always exit 0 and signal a denial by printing a
 * decision on stdout, so a non-zero exit is always an abnormal guard failure
 * and never an allow. Reading only stdout — the previous behavior — made a
 * crashed guard indistinguishable from one that ran and permitted the call.
 */
export function decideFromResult(hookName, result) {
  const denial = parseHookDecision(result?.stdout ?? "");
  if (denial) return denial;
  const code = result?.code ?? 0;
  if (code === 0) return null;
  const stderr = (result?.stderr ?? "").trim();
  const detail = stderr
    ? stderr.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).pop()
    : "no diagnostic output";
  return `AEGIS guard ${hookName} exited with status ${code} without a decision; blocking. ${detail}`;
}

export function createHookRunner(cwd, options = {}) {
  const spawnImpl = options.spawn ?? defaultSpawn;
  // `?? resolveInterpreter()` would silently re-resolve an explicit null, so an
  // injected "no interpreter available" case must be honored by key presence.
  const interpreter = "interpreter" in options ? options.interpreter ?? null : resolveInterpreter();
  return async function runPythonHook(hookName, payload) {
    if (!interpreter) return NO_INTERPRETER_REASON;
    const hookPath = join(cwd, ".agentic", "hooks", hookName);
    let result;
    try {
      result = await spawnImpl(
        interpreter.command,
        [...interpreter.args, hookPath],
        JSON.stringify(payload),
        cwd,
      );
    } catch (error) {
      return `AEGIS guard could not run ${hookName}: ${error?.message ?? String(error)}`;
    }
    return decideFromResult(hookName, result);
  };
}

export async function handleBeforeTool(input, output, cwd, runPythonHook) {
  const tool = normalizeToolName(input?.tool);
  const args = output?.args ?? input?.args ?? {};

  // `read` returns file contents; `grep` returns matching lines from them;
  // `glob` and `list` enumerate paths. All four can target a protected path, so
  // all four are checked. The real tool name is forwarded rather than a
  // hardcoded "Read" so the guard can tell a read that must name a file from a
  // search whose scope argument is optional.
  if (READ_LIKE_TOOLS.has(tool)) {
    const toolInput = { file_path: pathFromArgs(args) };
    if (tool === "glob") toolInput.pattern = args.pattern;
    const reason = await runPythonHook(
      "guard_read_path.py",
      hookPayload(cwd, "PreToolUse", OPENCODE_TOOL_NAMES[tool], toolInput, undefined, undefined),
    );
    if (reason) throw new Error(reason);
    return;
  }

  if (tool === "write" || tool === "edit") {
    const toolName = tool === "write" ? "Write" : "Edit";
    const filePath = pathFromArgs(args);
    for (const [hook, payload] of [
      [
        "guard_write_zone.py",
        hookPayload(cwd, "PreToolUse", toolName, { file_path: filePath }, undefined, undefined),
      ],
      [
        "secret_scan.py",
        hookPayload(cwd, "PreToolUse", toolName, args, undefined, undefined),
      ],
    ]) {
      const reason = await runPythonHook(hook, payload);
      if (reason) throw new Error(reason);
    }
    return;
  }

  if (tool === "apply_patch") {
    const command = commandFromArgs(args) || args.patch || args.input || "";
    for (const [hook, payload] of [
      [
        "guard_write_zone.py",
        hookPayload(cwd, "PreToolUse", "apply_patch", { command }, undefined, undefined),
      ],
      [
        "secret_scan.py",
        hookPayload(cwd, "PreToolUse", "apply_patch", args, undefined, undefined),
      ],
    ]) {
      const reason = await runPythonHook(hook, payload);
      if (reason) throw new Error(reason);
    }
    return;
  }

  if (tool === "bash") {
    const command = commandFromArgs(args);
    for (const hook of ["secret_scan.py", "delivery_preflight.py"]) {
      const reason = await runPythonHook(
        hook,
        hookPayload(cwd, "PreToolUse", "Bash", { command }, undefined, undefined),
      );
      if (reason) throw new Error(reason);
    }
  }
}

export async function handleAfterTool(input, output, cwd, runPythonHook) {
  const tool = input?.tool ?? "unknown";
  const callId = input?.toolCallID ?? input?.toolCallId ?? input?.id;
  await runPythonHook(
    "post_tool_evidence.py",
    hookPayload(cwd, "PostToolUse", tool, {}, callId, output ?? null),
  );
}

export const AgenticGuard = async (ctx = {}, options = {}) => {
  const cwd = options.cwd ?? ctx.worktree ?? ctx.directory ?? process.cwd();
  const runPythonHook = options.runPythonHook ?? createHookRunner(cwd, options);
  return {
    "tool.execute.before": async (input, output) => {
      await handleBeforeTool(input, output, cwd, runPythonHook);
    },
    "tool.execute.after": async (input, output) => {
      await handleAfterTool(input, output, cwd, runPythonHook);
    },
  };
};
