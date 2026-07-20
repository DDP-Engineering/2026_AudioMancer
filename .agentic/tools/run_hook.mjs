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
 */

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, join } from "node:path";
import { spawnSync } from "node:child_process";

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

function pathCommandExists(command) {
  if (command.includes("/") || command.includes("\\")) return existsSync(command);
  const extensions = process.platform === "win32"
    ? (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";")
    : [""];
  return (process.env.PATH || "").split(delimiter).some((directory) =>
    extensions.some((extension) => existsSync(join(directory, command + extension))),
  );
}

export function resolveInterpreter() {
  const explicit = process.env.AEGIS_PYTHON?.trim();
  if (explicit) return { command: explicit, args: [] };
  const registered = registeredRuntime();
  if (registered) return { command: registered, args: [] };
  const candidates = process.platform === "win32"
    ? [{ command: "py", args: ["-3"] }, { command: "python", args: [] }]
    : [{ command: "python3", args: [] }, { command: "python", args: [] }];
  return candidates.find(({ command }) => pathCommandExists(command)) ?? null;
}

const hook = process.argv[2];
if (!hook) {
  process.stderr.write("usage: node .agentic/tools/run_hook.mjs HOOK.py\n");
  process.exit(2);
}
const interpreter = resolveInterpreter();
if (!interpreter) {
  process.stderr.write("No AEGIS Python runtime is available. Run a packaged WAEGIS command or set AEGIS_PYTHON.\n");
  process.exit(2);
}
const result = spawnSync(interpreter.command, [...interpreter.args, hook, ...process.argv.slice(3)], {
  stdio: "inherit",
  windowsHide: true,
});
if (result.error) {
  process.stderr.write(`${result.error.message}\n`);
  process.exit(3);
}
process.exit(result.status ?? 3);
