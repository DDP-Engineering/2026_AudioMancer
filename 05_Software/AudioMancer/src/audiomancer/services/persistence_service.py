#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file persistence_service.py
@brief Atomic file persistence helpers for AudioMancer services.
@details Provides same-directory temporary-file writes followed by atomic
         replacement for JSON and text files that must not be left partially
         written after interruptions.
"""

# IMPORTS

from contextlib import suppress
import json
import os
from pathlib import Path
import tempfile
from typing import Any

# PUBLIC API


def write_text_atomic(
    target_path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """
    @brief      Write text through a same-directory temporary file and atomic replacement.
    @param[in]  target_path Final file path to replace.
    @param[in]  text Complete text payload to persist.
    @param[in]  encoding Text encoding used for the temporary file.
    @return     None.
    @exception  OSError Raised when the temporary write or replacement fails.
    """
    resolved_path = Path(target_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=resolved_path.parent,
            prefix=f".{resolved_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "w", encoding=encoding, newline="") as temporary_file:
            temporary_file.write(text)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, resolved_path)
    except OSError:
        if temporary_path is not None:
            _unlink_temporary_file(temporary_path)
        raise


def write_bytes_atomic(target_path: str | Path, payload: bytes) -> None:
    """
    @brief      Write bytes through a same-directory temporary file and atomic replacement.
    @param[in]  target_path Final file path to replace.
    @param[in]  payload Complete byte payload to persist.
    @return     None.
    @exception  OSError Raised when the temporary write or replacement fails.
    """
    resolved_path = Path(target_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=resolved_path.parent,
            prefix=f".{resolved_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, resolved_path)
    except OSError:
        if temporary_path is not None:
            _unlink_temporary_file(temporary_path)
        raise


def write_json_atomic(
    target_path: str | Path,
    payload: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
    encoding: str = "utf-8",
) -> None:
    """
    @brief      Serialize and atomically persist one JSON payload.
    @param[in]  target_path Final JSON file path to replace.
    @param[in]  payload JSON-serializable payload.
    @param[in]  indent JSON indentation passed to `json.dumps`.
    @param[in]  ensure_ascii JSON ASCII escaping flag passed to `json.dumps`.
    @param[in]  sort_keys JSON key ordering flag passed to `json.dumps`.
    @param[in]  encoding Text encoding used for the temporary file.
    @return     None.
    @exception  TypeError Raised when the payload is not JSON-serializable.
    @exception  OSError Raised when the temporary write or replacement fails.
    """
    json_text = json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii, sort_keys=sort_keys) + "\n"
    write_text_atomic(target_path, json_text, encoding=encoding)


def _unlink_temporary_file(temporary_path: Path) -> None:
    """
    @brief      Best-effort cleanup for temporary persistence files.
    @param[in]  temporary_path Temporary file path to remove.
    @return     None.
    @exception  None
    """
    with suppress(OSError):
        temporary_path.unlink(missing_ok=True)


# END OF FILE
