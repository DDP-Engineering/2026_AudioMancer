#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file source_ledger_service.py
@brief Project artifact IO for extracted text and provenance.
@details Canonical construction and validation belong to the isolated extraction engine.
"""

# IMPORTS

import json
from pathlib import Path

from audiomancer import config
from audiomancer.extraction.document import (
    CanonicalDocumentBuilder as CanonicalDocumentBuilder,
)
from audiomancer.extraction.document import (
    SourceLedgerError as SourceLedgerError,
)
from audiomancer.extraction.document import (
    file_sha256 as file_sha256,
)
from audiomancer.extraction.document import (
    text_sha256 as text_sha256,
)
from audiomancer.extraction.document import (
    validate_source_ledger,
)
from audiomancer.extraction.models import SourceEvent as SourceEvent
from audiomancer.services.persistence_service import write_json_atomic, write_text_atomic

# PUBLIC API


def write_source_artifacts(
    project_root: str | Path,
    canonical_text: str,
    ledger: dict[str, object],
) -> tuple[Path, Path]:
    """@brief Atomically write canonical text and its source ledger."""
    root = Path(project_root)
    text_path = root / config.EXTRACTED_TEXT_FILE_NAME
    ledger_path = root / config.SOURCE_LEDGER_FILE_NAME
    validate_source_ledger(ledger, canonical_text)
    write_text_atomic(text_path, canonical_text)
    write_json_atomic(ledger_path, ledger)
    return text_path, ledger_path


def load_source_ledger(project_root: str | Path) -> dict[str, object]:
    """@brief Load and validate the ledger against the canonical extracted text."""
    root = Path(project_root)
    text_path = root / config.EXTRACTED_TEXT_FILE_NAME
    ledger_path = root / config.SOURCE_LEDGER_FILE_NAME
    if not text_path.is_file() or not ledger_path.is_file():
        raise SourceLedgerError("Extraction requires extracted_text.txt and source_ledger.json.")
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceLedgerError("source_ledger.json is unreadable or malformed.") from error
    canonical_text = text_path.read_text(encoding="utf-8")
    validate_source_ledger(payload, canonical_text)
    return payload


def unit_text(canonical_text: str, unit: dict[str, object]) -> str:
    """@brief Return one unit's exact canonical source slice."""
    return str(canonical_text)[int(unit["start"]) : int(unit["end"])]


# END OF FILE
