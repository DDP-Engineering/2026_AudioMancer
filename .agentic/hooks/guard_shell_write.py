#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file guard_shell_write.py
@brief Pre-tool hook extending the write policy to shell file writes.
@details ``guard_write_zone.py`` inspects the dedicated editing tools
         (``Edit``/``Write``/``apply_patch``/...); it is not wired to the shell
         tool, so a repository file could be written outside the active stage's
         write zone — or a protected path overwritten — through a shell
         redirection or a copy/move command. This guard closes that gap for the
         obvious, reliably detectable shell write forms and reuses the exact
         same configured write-zone and protected-path policy, so a shell write
         is judged identically to an editor write.
@details **Best-effort by design.** A pre-tool hook cannot fully model a shell:
         only the common, unambiguous write constructs are recognized —
         output redirection (``>``/``>>`` and file-descriptor variants),
         ``tee``, ``cp``/``mv``/``install`` destinations, ``dd of=``, and
         ``sed -i``. Obfuscated writes (a write performed by a script the
         command merely launches, an operator glued to a bare word without a
         space, ``eval`` of assembled text) are not caught. The delivery
         working-tree audit remains the backstop that inspects the tree itself.
@details Only targets that resolve **inside** the repository are governed. A
         shell write to ``/tmp``, ``/dev/null``, or any path outside the
         workspace is not a repository write-zone concern and is ignored, which
         keeps ordinary commands (``… > /dev/null``, temp files) unaffected.
@author Eng. Dan Dumitru Pasare
@date 2026-07-24
@version 0.1.0
"""

# IMPORTS

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path


# CONSTANTS

# @brief Shell tool identifiers this guard inspects, matching the set
#        ``delivery_preflight.py`` acts on. Codex/Claude Code send ``Bash``;
#        Qwen Code sends ``run_shell_command``.
SHELL_TOOLS = frozenset({"Bash", "run_shell_command"})

# @brief Control operators that separate one command from the next. Splitting on
#        these before tokenizing keeps a redirection or write command scoped to
#        its own command. A well-formed segment then tokenizes cleanly, and an
#        operator that appears *inside* quotes lands in a segment that fails to
#        tokenize (unbalanced quote) and is skipped — a missed write, never a
#        misattributed one.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|&\n()]")

# @brief A token that opens an output redirection: an optional leading file
#        descriptor (digits) or ``&`` (redirect-all), then ``>`` or ``>>``, then
#        an optional ``|`` (noclobber override) and any attached target. Input
#        redirection (``<``) is a read and is deliberately not matched.
_REDIRECT_TOKEN_RE = re.compile(r"^(?:[0-9]+|&)?>>?\|?(?P<target>.*)$")

# @brief Leading tokens that precede the real command word without being it:
#        environment prefixes and simple launchers. Skipped so the command that
#        actually writes is the one classified.
_PREFIX_COMMANDS = frozenset({"sudo", "command", "nice", "nohup", "env", "time"})

# @brief ``NAME=value`` environment assignment prefix.
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


# PUBLIC API


def main() -> int:
    """
    @brief      Enforce the configured write policy on a shell command's writes.
    @return     Zero after allowing the command or emitting a deny decision.
    @details    Repository policy, run state, and path resolution are consulted
                only once at least one in-repository write target is found, so a
                read-only shell command is never blocked and never forces an
                active-run selection.
    @exception  None Configuration and state failures become hook denials.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    if payload.get("tool_name") not in SHELL_TOOLS:
        return 0
    tool_input = payload.get("tool_input", {})
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str) or not command:
        return 0
    targets = extract_write_targets(command)
    if not targets:
        return 0

    cwd = Path(payload.get("cwd") or ".").resolve()
    try:
        from workflow_config_bootstrap import find_repository_root, load_workflow_config

        repo_root = find_repository_root(cwd)
        source_text = str(repo_root / ".agentic" / "cli" / "src")
        if source_text not in sys.path:
            sys.path.insert(0, source_text)
        from aegis.paths import contained_relative_path, matches_pattern
    except Exception as exc:
        return deny(str(exc))

    in_repo = []
    for target in targets:
        relative = contained_relative_path(target, repo_root)
        if relative is not None and relative not in in_repo:
            in_repo.append(relative)
    if not in_repo:
        return 0

    try:
        config = load_workflow_config(repo_root)
        if config.write_access.mode == "unrestricted":
            stage = "unrestricted"
            zones = None
        else:
            _, stage, access_mode = read_run_state(repo_root)
            zones = None if access_mode == "repo-wide" else config.write_access.stages[stage]
    except Exception as exc:
        return deny(str(exc))

    if zones == ():
        return deny(
            f"Stage '{stage}' is read-only; shell file writes are not allowed: {', '.join(in_repo)}"
        )
    blocked = []
    for relative in in_repo:
        if is_protected_path(relative, config.protected_paths, matches_pattern):
            blocked.append(relative)
            continue
        if zones is not None and not any(matches_pattern(relative, pattern) for pattern in zones):
            blocked.append(relative)
    if blocked:
        return deny(
            f"Shell command writes outside '{stage}' write zone: {', '.join(blocked)}"
        )
    return 0


# HELPER FUNCTIONS


def extract_write_targets(command: str) -> list[str]:
    """
    @brief      Collect the file paths a shell command writes, best-effort.
    @param[in]  command Raw shell command text.
    @return     Distinct write-target paths in discovery order.
    @details    The command is split into per-command segments, each tokenized
                with a POSIX-quoted lexer that preserves backslashes (so a
                Windows path survives), and every segment is scanned for output
                redirections and for the operand a write command names.
    @exception  None A segment that cannot be tokenized yields no targets.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    targets: list[str] = []
    for segment in _SEGMENT_SPLIT_RE.split(command):
        tokens = _tokenize(segment)
        if not tokens:
            continue
        targets.extend(_redirect_targets(tokens))
        targets.extend(_command_targets(tokens))
    return list(dict.fromkeys(target for target in targets if target))


def _tokenize(segment: str) -> list[str]:
    """
    @brief      Split one command segment into argv, quote-aware and backslash-
                preserving on every platform.
    @param[in]  segment One command segment with no top-level control operators.
    @return     Argv tokens, or an empty list when the segment cannot be lexed.
    @details    POSIX mode groups quoted spans correctly; ``escape = ""`` keeps
                backslashes literal so a Windows path is not mangled. Matches the
                lexer configuration used by ``aegis.gates`` for the same reason.
    @exception  None Unbalanced quoting yields an empty token list.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    lexer = shlex.shlex(segment, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.escape = ""
    try:
        return list(lexer)
    except ValueError:
        return []


def _redirect_targets(tokens: list[str]) -> list[str]:
    """
    @brief      Extract file targets of output redirections from a token list.
    @param[in]  tokens Argv tokens of one command segment.
    @return     Redirection target paths.
    @details    A redirection token either carries its target directly
                (``>out``) or names the following token (``> out``). A target
                that begins with ``&`` is a file-descriptor duplication
                (``2>&1``, ``>&2``), not a file, and is ignored.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    targets: list[str] = []
    for index, token in enumerate(tokens):
        match = _REDIRECT_TOKEN_RE.match(token)
        if match is None:
            continue
        target = match.group("target")
        if not target:
            target = tokens[index + 1] if index + 1 < len(tokens) else ""
        if target and not target.startswith("&"):
            targets.append(target)
    return targets


def _command_targets(tokens: list[str]) -> list[str]:
    """
    @brief      Extract the file a write command names as its destination.
    @param[in]  tokens Argv tokens of one command segment.
    @return     Destination paths a recognized write command targets.
    @details    Recognizes ``tee`` (every file operand), ``cp``/``mv``/
                ``install`` (the last operand — the destination), ``dd of=``,
                and ``sed -i`` (the last operand, present only when a script and
                at least one file are both given).
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _ASSIGNMENT_RE.match(token) or _basename(token) in _PREFIX_COMMANDS:
            index += 1
            continue
        break
    if index >= len(tokens):
        return []
    name = _basename(tokens[index])
    rest = tokens[index + 1 :]
    non_flags = [token for token in rest if not token.startswith("-")]
    if name == "tee":
        return list(non_flags)
    if name in {"cp", "mv", "install"}:
        return [non_flags[-1]] if len(non_flags) >= 2 else []
    if name == "dd":
        return [token[len("of=") :] for token in rest if token.startswith("of=") and len(token) > len("of=")]
    if name in {"sed", "gsed"} and len(non_flags) >= 2 and _has_inplace_flag(rest):
        return [non_flags[-1]]
    return []


def _has_inplace_flag(tokens: list[str]) -> bool:
    """
    @brief      Report whether a ``sed`` argument list requests in-place editing.
    @param[in]  tokens Arguments following the ``sed`` command word.
    @return     True when an ``-i``/``-i<suffix>``/``--in-place`` flag is present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    return any(
        token == "-i" or token.startswith("-i") or token == "--in-place" or token.startswith("--in-place=")
        for token in tokens
    )


def _basename(token: str) -> str:
    """
    @brief      Return the final path component of a command word.
    @param[in]  token Command word, possibly a path such as ``/usr/bin/tee``.
    @return     The basename with either slash style handled.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    return token.replace("\\", "/").rsplit("/", 1)[-1]


def read_run_state(cwd: Path) -> tuple[Path, str, str]:
    """
    @brief      Load stage and access mode through the shared state API.
    @param[in]  cwd Hook working directory or a path inside the repository.
    @return     Repository root, active stage, and run-local access mode.
    @exception  RunResolutionError If no valid worktree selection exists.
    @exception  RuntimeError If the delivered AEGIS package cannot be found.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    from workflow_config_bootstrap import find_repository_root

    repo_root = find_repository_root(cwd)
    source_root = repo_root / ".agentic" / "cli" / "src"
    source_text = str(source_root)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    from aegis.store import load_graph, resolve_run_id

    run_id = resolve_run_id(repo_root)
    graph = load_graph(repo_root, run_id)
    return repo_root, graph.stage, graph.access_mode


def is_protected_path(path: str, policy, matcher) -> bool:  # type: ignore[no-untyped-def]
    """
    @brief      Report whether configured policy blocks a write to ``path``.
    @param[in]  path Normalized repository-relative path.
    @param[in]  policy Validated protected-path policy.
    @param[in]  matcher Shared ``matches_pattern`` callable.
    @return     Whether protected-path policy blocks a write to ``path``.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    return (
        policy.mode == "enforce"
        and "write" in policy.operations
        and any(matcher(path, pattern) for pattern in policy.patterns)
    )


def deny(message: str) -> int:
    """
    @brief      Emit the common pre-tool denial envelope.
    @param[in]  message Actionable reason shown to the agent.
    @return     Zero as required by adapter hook transports.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": message,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# END OF FILE
