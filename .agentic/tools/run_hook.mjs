#!/usr/bin/env node
/*
 * Copyright (c) 2026 DDP Engineering
 * This software is licensed under the PolyForm Noncommercial License 1.0.0.
 * Commercial use requires a separate commercial license.
 * See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
 */

/**
 * Cross-platform hook launcher. It keeps hook configuration independent of a
 * system Python by resolving AEGIS_PYTHON, the per-user WAEGIS runtime pointer,
 * and then a supported system launcher, in that order.
 *
 * Fail-closed contract: the shared Python guards always exit 0 and signal a
 * denial by printing a decision on stdout, so a non-zero exit is always an
 * abnormal guard failure, never an allow. Every such failure — no interpreter,
 * an unlaunchable interpreter, or a hook that crashed — exits 2, the blocking
 * hook status for Claude Code, Codex, and Qwen Code. Exiting with the child's
 * own status instead would report a crashed guard as a *non-blocking* hook
 * error on those hosts, and the tool call would proceed unchecked.
 *
 * This module is importable: the launcher body runs only when the file is the
 * process entry point, so the resolution order below stays a single source of
 * truth for the adapters that spawn the same hooks themselves.
 */

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, join } from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

/**
 * Blocking status shared by the Claude Code, Codex, and Qwen Code hook
 * protocols. Any other non-zero status is only a non-blocking hook error.
 */
export const BLOCKING_EXIT_CODE = 2;

/** Actionable reason used whenever no interpreter can be resolved. */
export const NO_INTERPRETER_REASON =
  "AEGIS guard could not run: no Python runtime was found. " +
  "Set AEGIS_PYTHON to an interpreter, or run a packaged WAEGIS command to register one.";

function runtimePointer() {
  if (process.env.WAEGIS_HOME) return join(process.env.WAEGIS_HOME, "runtime-python");
  if (process.platform === "win32") {
    return join(process.env.APPDATA || join(homedir(), "AppData", "Roaming"), "waegis", "runtime-python");
  }
  return join(homedir(), ".config", "waegis", "runtime-python");
}

function registeredRuntime() {
  try {
    const value = readFileSync(runtimePointer(), "utf8").trim();
    return value && existsSync(value) ? value : null;
  } catch {
    return null;
  }
}

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
 * System launcher candidates, in order. Every transport that spawns the shared
 * hooks must offer the same list so one repository policy cannot resolve to a
 * different interpreter depending on which agent is driving.
 */
export function interpreterCandidates() {
  return process.platform === "win32"
    ? [{ command: "py", args: ["-3"] }, { command: "python", args: [] }]
    : [{ command: "python3", args: [] }, { command: "python", args: [] }];
}

export function resolveInterpreter() {
  const explicit = process.env.AEGIS_PYTHON?.trim();
  if (explicit) return { command: explicit, args: [] };
  const registered = registeredRuntime();
  if (registered) return { command: registered, args: [] };
  return interpreterCandidates().find(({ command }) => pathCommandExists(command)) ?? null;
}

function runLauncher(argv) {
  const hook = argv[2];
  if (!hook) {
    process.stderr.write("usage: node .agentic/tools/run_hook.mjs HOOK.py\n");
    return BLOCKING_EXIT_CODE;
  }
  const interpreter = resolveInterpreter();
  if (!interpreter) {
    process.stderr.write(`${NO_INTERPRETER_REASON}\n`);
    return BLOCKING_EXIT_CODE;
  }
  const result = spawnSync(interpreter.command, [...interpreter.args, hook, ...argv.slice(3)], {
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.error) {
    process.stderr.write(`AEGIS guard could not run ${hook}: ${result.error.message}\n`);
    return BLOCKING_EXIT_CODE;
  }
  if (result.status === 0) return 0;
  // The child already wrote its own diagnostics to the inherited stderr; name
  // the failure so the host shows an actionable blocking reason rather than a
  // bare traceback.
  process.stderr.write(
    `AEGIS guard ${hook} exited with status ${result.status ?? "null"} without a decision; blocking.\n`,
  );
  return BLOCKING_EXIT_CODE;
}

const entryPoint = process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href;
if (entryPoint) {
  process.exit(runLauncher(process.argv));
}
