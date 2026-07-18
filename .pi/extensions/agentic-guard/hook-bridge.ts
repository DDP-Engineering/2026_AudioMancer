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
 * Pi's `pi.exec()` cannot feed stdin (its ExecOptions is { signal, timeout, cwd }
 * only), so the hooks are spawned through Node's `child_process` instead. The
 * Python hooks are reused byte-for-byte; only the transport differs from a plain
 * `pi.exec`.
 */

import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

/**
 * Secret/key file patterns that must never be read. Mirrors the Read denies in
 * `.claude/settings.json` and the secret subset of `PROTECTED_PATH_PATTERNS` in
 * `.agentic/hooks/guard_write_zone.py`. Matched against the file basename so a
 * secret is blocked wherever it lives.
 */
export const PROTECTED_READ_PATTERNS: readonly string[] = [
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

/** Options for {@link createHookBridge}. */
export interface HookBridgeOptions {
  spawn?: SpawnFn;
  interpreter?: Interpreter;
}

/** Bridge surface consumed by the tool-event handlers in `bridge.ts`. */
export interface HookBridge {
  /**
   * Run one Python hook with `payload` on stdin and return the deny reason, or
   * `null` when the hook allows the action (empty stdout) or cannot be run.
   */
  runPythonHook(
    cwd: string,
    hookName: string,
    payload: Record<string, unknown>,
  ): Promise<string | null>;
  /** Return a deny reason when `path` points at a protected secret/key file, else `null`. */
  protectedPathDeny(path: string | undefined, cwd: string): string | null;
}

/**
 * Resolve explicit `AEGIS_PYTHON`, the per-user WAEGIS runtime pointer, then
 * supported system launchers. The hooks are stdlib-only.
 */
export function resolveInterpreter(): Interpreter {
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
  if (process.platform === "win32") {
    return { command: "py", args: ["-3"] };
  }
  return { command: "python3", args: [] };
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

/** Translate a simple fnmatch-style pattern (`*`, `?`) into a `RegExp`. */
function fnmatchToRegExp(pattern: string): RegExp {
  let regex = "";
  for (const ch of pattern) {
    if (ch === "*") regex += ".*";
    else if (ch === "?") regex += ".";
    else regex += ch.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${regex}$`);
}

const PROTECTED_READ_MATCHERS = PROTECTED_READ_PATTERNS.map(fnmatchToRegExp);

/**
 * Deny reads of secret/key files. Matches the file basename against
 * {@link PROTECTED_READ_PATTERNS}. `cwd` is accepted for signature parity with
 * the other guard checks; the basename test is location-independent.
 */
export function protectedPathDeny(
  path: string | undefined,
  _cwd: string,
): string | null {
  if (!path) return null;
  const basename = path.replace(/\\/g, "/").split("/").filter(Boolean).pop();
  if (!basename) return null;
  const lower = basename.toLowerCase();
  if (PROTECTED_READ_MATCHERS.some((matcher) => matcher.test(lower))) {
    return `Reading protected path is blocked: ${path}`;
  }
  return null;
}

/** Build a {@link HookBridge}, optionally injecting a spawn function/interpreter for tests. */
export function createHookBridge(options: HookBridgeOptions = {}): HookBridge {
  const spawnImpl = options.spawn ?? defaultSpawn;
  const interpreter = options.interpreter ?? resolveInterpreter();
  return {
    async runPythonHook(cwd, hookName, payload) {
      const hookPath = join(cwd, ".agentic", "hooks", hookName);
      let result: SpawnResult;
      try {
        result = await spawnImpl(
          interpreter.command,
          [...interpreter.args, hookPath],
          JSON.stringify(payload),
          cwd,
        );
      } catch {
        // Python unavailable or hook missing: fail open. The guard contract is
        // that a denial is an explicit stdout signal; absence means allow. The
        // Python prerequisite is documented in the adapter README.
        return null;
      }
      return parseHookDecision(result.stdout);
    },
    protectedPathDeny,
  };
}
