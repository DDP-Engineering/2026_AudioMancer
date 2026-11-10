#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""Atomic ZIP publication for caller-selected archive members."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import zipfile

from audiomancer.services import operation_runtime_service
from audiomancer.services.logging_service import get_component_logger

ArchiveEntry = tuple[str, Path | None, str | None]
_LOGGER = get_component_logger("archive_writer")


def write_archive(
    destination: Path,
    entries: list[ArchiveEntry],
    *,
    progress_callback=None,
    cancel_requested=None,
) -> Path:
    """Write a cancellable ZIP and replace the destination only on success."""
    operation_runtime_service.raise_if_cancelled(cancel_requested)
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = len(entries)
    operation_runtime_service.emit_progress_update(
        progress_callback, 0, total, "Preparing ZIP archive...", include_token_usage=False
    )
    with NamedTemporaryFile(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for current, (name, source_path, text) in enumerate(entries, start=1):
                operation_runtime_service.raise_if_cancelled(cancel_requested)
                if source_path is None:
                    archive.writestr(name, text or "")
                else:
                    archive.write(source_path, name)
                operation_runtime_service.emit_progress_update(
                    progress_callback, current, total, f"Archiving {current}/{total}: {Path(name).name}",
                    include_token_usage=False,
                )
        operation_runtime_service.raise_if_cancelled(cancel_requested)
        os.replace(temporary_path, destination)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            _LOGGER.exception("Could not remove ZIP temporary file: %s", temporary_path)
    return destination
