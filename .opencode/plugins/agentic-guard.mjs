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
 */

import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const PROTECTED_READ_PATTERNS = [
  ".env",
  ".env.*",
  "*.env",
  "*.pem",
  "*.key",
  "*.p12",
  "*.pfx",
  "*_rsa",
  "*_rsa.pub",
  "id_rsa",
  "id_rsa.pub",
  "id_ed25519",
  "id_ed25519.pub",
];

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
  return process.platform === "win32"
    ? { command: "python", args: [] }
    : { command: "python3", args: [] };
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

function fnmatchToRegExp(pattern) {
  let regex = "";
  for (const ch of pattern) {
    if (ch === "*") regex += ".*";
    else if (ch === "?") regex += ".";
    else regex += ch.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${regex}$`);
}

const PROTECTED_READ_MATCHERS = PROTECTED_READ_PATTERNS.map(fnmatchToRegExp);

export function protectedPathDeny(path) {
  if (!path) return null;
  const basename = String(path).replace(/\\/g, "/").split("/").filter(Boolean).pop();
  if (!basename) return null;
  const lower = basename.toLowerCase();
  if (PROTECTED_READ_MATCHERS.some((matcher) => matcher.test(lower))) {
    return `Reading protected path is blocked: ${path}`;
  }
  return null;
}

export function normalizeToolName(name) {
  const value = String(name ?? "").toLowerCase();
  if (value === "patch") return "apply_patch";
  return value;
}

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

export function createHookRunner(cwd, options = {}) {
  const spawnImpl = options.spawn ?? defaultSpawn;
  const interpreter = options.interpreter ?? resolveInterpreter();
  return async function runPythonHook(hookName, payload) {
    const hookPath = join(cwd, ".agentic", "hooks", hookName);
    let result;
    try {
      result = await spawnImpl(
        interpreter.command,
        [...interpreter.args, hookPath],
        JSON.stringify(payload),
        cwd,
      );
    } catch {
      return null;
    }
    return parseHookDecision(result.stdout);
  };
}

export async function handleBeforeTool(input, output, cwd, runPythonHook) {
  const tool = normalizeToolName(input?.tool);
  const args = output?.args ?? input?.args ?? {};

  if (tool === "read") {
    const reason = protectedPathDeny(pathFromArgs(args));
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
