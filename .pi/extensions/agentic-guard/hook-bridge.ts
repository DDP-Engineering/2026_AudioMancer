/*
 * Copyright (c) 2026 DDP Engineering
 * This software is licensed under the PolyForm Noncommercial License 1.0.0.
 * Commercial use requires a separate commercial license.
 * See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
 */

/**
 * hook-bridge.ts
 *
 * Transport layer for the Pi adapter. Runs the shared, stdlib-only Python guard
 * hooks under `.agentic/hooks/` and translates their stdout JSON into a block
 * reason. The Python hooks read their payload from stdin and signal a denial by
 * printing `{ hookSpecificOutput: { permissionDecision: "deny", ... } }` (exit
 * code is always 0; stdout is the signal).
 *
 * Pi's `pi.exec()` cannot feed stdin (its ExecOptions is { signal, timeout }
 * only, with no `cwd` option either), so the hooks are spawned through Node's
 * `child_process` instead, which also gives explicit control over the working
 * directory. The Python hooks are reused byte-for-byte; only the transport
 * differs from a plain `pi.exec`.
 *
 * Fail-closed contract: because the guards always exit 0 and answer on stdout,
 * a non-zero exit is always an abnormal guard failure, never an allow. A
 * missing interpreter, an unlaunchable interpreter, and a crashed hook all
 * block with an actionable reason. Interpreter resolution and this decision
 * contract are kept identical to `.agentic/tools/run_hook.mjs` (the Claude
 * Code / Codex / Qwen Code launcher) and to
 * `.opencode/plugins/agentic-guard.mjs`, so one repository policy cannot
 * resolve to a different interpreter — or a different answer — depending on
 * which agent is driving.
 */

import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, join } from "node:path";

/** Actionable reason used whenever no interpreter can be resolved. */
export const NO_INTERPRETER_REASON =
  "AEGIS guard could not run: no Python runtime was found. "
  + "Set AEGIS_PYTHON to an interpreter, or run a packaged WAEGIS command to register one.";

/** Result of running a spawned process. */
export interface SpawnResult {
  stdout: string;
  stderr: string;
  code: number;
}

/** Pluggable spawn function so the bridge can be unit-tested without a real process. */
export type SpawnFn = (
  command: string,
  args: string[],
  input: string,
  cwd: string,
) => Promise<SpawnResult>;

/** Python interpreter invocation (command plus any leading args, e.g. `py -3`). */
export interface Interpreter {
  command: string;
  args: string[];
}

/**
 * Options for {@link createHookBridge}. Passing `interpreter: null` explicitly
 * models "no interpreter is available" and is distinct from omitting the key,
 * which resolves one from the environment.
 */
export interface HookBridgeOptions {
  spawn?: SpawnFn;
  interpreter?: Interpreter | null;
}

/** Bridge surface consumed by the tool-event handlers in `bridge.ts`. */
export interface HookBridge {
  /**
   * Run one Python hook with `payload` on stdin and return the block reason, or
   * `null` only when the hook actually ran and allowed the action. A guard that
   * could not run returns a reason, so an unavailable guard blocks.
   */
  runPythonHook(
    cwd: string,
    hookName: string,
    payload: Record<string, unknown>,
  ): Promise<string | null>;
}

/** Whether a bare command name resolves on PATH (or an explicit path exists). */
export function pathCommandExists(command: string): boolean {
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
export function interpreterCandidates(): Interpreter[] {
  return process.platform === "win32"
    ? [{ command: "py", args: ["-3"] }, { command: "python", args: [] }]
    : [{ command: "python3", args: [] }, { command: "python", args: [] }];
}

/**
 * Resolve explicit `AEGIS_PYTHON`, the per-user WAEGIS runtime pointer, then
 * supported system launchers. The hooks are stdlib-only. Returns `null` when
 * no interpreter is available, which the bridge turns into a block rather than
 * an allow.
 */
export function resolveInterpreter(): Interpreter | null {
  const override = process.env.AEGIS_PYTHON;
  if (override && override.trim()) {
    return { command: override.trim(), args: [] };
  }
  const home = process.env.WAEGIS_HOME
    ?? (process.platform === "win32"
      ? join(process.env.APPDATA ?? join(homedir(), "AppData", "Roaming"), "waegis")
      : join(homedir(), ".config", "waegis"));
  try {
    const registered = readFileSync(join(home, "runtime-python"), "utf8").trim();
    if (registered && existsSync(registered)) {
      return { command: registered, args: [] };
    }
  } catch {
    // No valid registered WAEGIS runtime; continue with system launchers.
  }
  return interpreterCandidates().find(({ command }) => pathCommandExists(command)) ?? null;
}

/** Default {@link SpawnFn} backed by `child_process.spawn`, writing `input` to stdin. */
export const defaultSpawn: SpawnFn = (command, args, input, cwd) =>
  new Promise<SpawnResult>((resolve, reject) => {
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

/**
 * Parse a hook's stdout. Returns the `permissionDecisionReason` when the hook
 * denied the action, otherwise `null`. Tolerates extra non-JSON lines by
 * retrying with the last non-empty line.
 */
export function parseHookDecision(stdout: string): string | null {
  const text = (stdout ?? "").trim();
  if (!text) return null;
  let data: unknown;
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
  const output = (data as { hookSpecificOutput?: Record<string, unknown> } | null)
    ?.hookSpecificOutput;
  if (output && output.permissionDecision === "deny") {
    const reason = output.permissionDecisionReason;
    return typeof reason === "string" && reason
      ? reason
      : "Blocked by agentic workflow guard.";
  }
  return null;
}

/**
 * Turn one completed hook run into a block reason, or `null` to allow.
 *
 * The guards always exit 0 and answer on stdout, so a non-zero exit is always
 * an abnormal failure. Reading only stdout — the previous behavior — made a
 * crashed guard indistinguishable from one that ran and permitted the call.
 */
export function decideFromResult(hookName: string, result: SpawnResult): string | null {
  const denial = parseHookDecision(result.stdout ?? "");
  if (denial) return denial;
  const code = result.code ?? 0;
  if (code === 0) return null;
  const stderr = (result.stderr ?? "").trim();
  const detail = stderr
    ? stderr.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).pop()
    : "no diagnostic output";
  return `AEGIS guard ${hookName} exited with status ${code} without a decision; blocking. ${detail}`;
}

/** Build a {@link HookBridge}, optionally injecting a spawn function/interpreter for tests. */
export function createHookBridge(options: HookBridgeOptions = {}): HookBridge {
  const spawnImpl = options.spawn ?? defaultSpawn;
  // `?? resolveInterpreter()` would silently re-resolve an explicit null, so an
  // injected "no interpreter available" case must be honored by key presence.
  const interpreter = "interpreter" in options ? options.interpreter ?? null : resolveInterpreter();
  return {
    async runPythonHook(cwd, hookName, payload) {
      // No interpreter is a guard that cannot run, not a guard that allowed.
      if (!interpreter) return NO_INTERPRETER_REASON;
      const hookPath = join(cwd, ".agentic", "hooks", hookName);
      let result: SpawnResult;
      try {
        result = await spawnImpl(
          interpreter.command,
          [...interpreter.args, hookPath],
          JSON.stringify(payload),
          cwd,
        );
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        return `AEGIS guard could not run ${hookName}: ${detail}`;
      }
      return decideFromResult(hookName, result);
    },
  };
}
