# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path


def relative_to_root(path: str | Path, root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        rel = candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace root: {path}") from exc
    return rel.as_posix()


def is_allowed_path(path: str | Path, root: Path, patterns: list[str]) -> bool:
    rel = relative_to_root(path, root)
    normalized = rel.lower()
    for pattern in patterns:
        glob = pattern.replace("\\", "/").lower()
        if fnmatch(normalized, glob) or fnmatch(normalized, glob.rstrip("/") + "/**"):
            return True
    return False
