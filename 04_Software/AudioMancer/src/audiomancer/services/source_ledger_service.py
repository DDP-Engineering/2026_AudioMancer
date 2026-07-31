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
@brief Canonical extracted-text ledger primitives for AudioMancer.
@details Builds text and structural offsets in one pass so Cleanup can apply
         source-referenced operations without asking an AI model to reproduce
         story text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from audiomancer import config
from audiomancer.services.persistence_service import write_json_atomic, write_text_atomic

SOURCE_LEDGER_SCHEMA_VERSION = 1
_VALID_STRUCTURE_ORIGINS = frozenset(("native", "layout", "inferred"))
_VALID_STRUCTURE_QUALITIES = frozenset(
    ("native", "native_partial", "geometry_full", "geometry_partial", "text_only", "unusable")
)


class SourceLedgerError(ValueError):
    """Raised when extracted text and its structural ledger are incompatible."""


@dataclass(frozen=True)
class SourceEvent:
    """One canonical text unit emitted by a source-format adapter."""

    text: str
    kind: str = "unknown"
    structure_origin: str = "inferred"
    boundary_before: str | None = None
    boundary_kind: str = "line"
    parent_id: str | None = None
    locator: dict[str, object] = field(default_factory=dict)
    native: dict[str, object] | None = None
    layout: dict[str, object] | None = None


class CanonicalDocumentBuilder:
    """Build canonical text and its ledger from the same ordered event stream."""

    def __init__(
        self,
        *,
        source_format: str,
        source_sha256: str,
        adapter_version: int = 1,
        encoding: str | None = None,
        structure_quality: str = "text_only",
        eligibility_mode: str | None = None,
        eligibility_reason_codes: list[str] | None = None,
        pages: list[dict[str, object]] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        if structure_quality not in _VALID_STRUCTURE_QUALITIES:
            raise SourceLedgerError(f"Unsupported structure quality: {structure_quality}")
        self._source_format = str(source_format)
        self._source_sha256 = str(source_sha256)
        self._adapter_version = int(adapter_version)
        self._encoding = encoding
        self._structure_quality = structure_quality
        self._eligibility_mode = eligibility_mode or structure_quality
        self._eligibility_reason_codes = list(eligibility_reason_codes or [])
        self._pages = [dict(item) for item in pages or []]
        self._warnings = [str(item) for item in warnings or []]
        self._parts: list[str] = []
        self._units: list[dict[str, object]] = []
        self._boundaries: list[dict[str, object]] = []
        self._length = 0
        self._last_unit_id: str | None = None

    def add(self, event: SourceEvent) -> str | None:
        """Append one non-empty source event and return its stable unit id."""
        origin = str(event.structure_origin)
        if origin not in _VALID_STRUCTURE_ORIGINS:
            raise SourceLedgerError(f"Unsupported structure origin: {origin}")
        text = _normalize_line_endings(str(event.text))
        if not text:
            return None

        unit_id = f"u-{len(self._units) + 1:06d}"
        if self._last_unit_id is not None:
            boundary_text = _normalize_line_endings(
                event.boundary_before if event.boundary_before is not None else "\n"
            )
            self._append_boundary(
                boundary_text,
                left_unit_id=self._last_unit_id,
                right_unit_id=unit_id,
                kind=str(event.boundary_kind or "line"),
                structure_origin=origin,
            )

        start = self._length
        self._parts.append(text)
        self._length += len(text)
        end = self._length
        self._units.append(
            {
                "unit_id": unit_id,
                "start": start,
                "end": end,
                "kind": str(event.kind or "unknown"),
                "structure_origin": origin,
                "parent_id": event.parent_id,
                "locator": dict(event.locator),
                "native": None if event.native is None else dict(event.native),
                "layout": None if event.layout is None else dict(event.layout),
            }
        )
        self._last_unit_id = unit_id
        return unit_id

    def build(self, *, trailing_newline: bool = True) -> tuple[str, dict[str, object]]:
        """Return canonical text and a strictly validated source ledger."""
        if not self._units:
            raise SourceLedgerError("Source did not contain extractable text units.")
        if trailing_newline:
            self._append_boundary(
                "\n",
                left_unit_id=self._last_unit_id,
                right_unit_id=None,
                kind="document_end",
                structure_origin="inferred",
            )

        canonical_text = "".join(self._parts)
        ledger: dict[str, object] = {
            "schema_version": SOURCE_LEDGER_SCHEMA_VERSION,
            "source": {
                "format": self._source_format,
                "sha256": self._source_sha256,
                "adapter_version": self._adapter_version,
                "encoding": self._encoding,
            },
            "canonical_text": {
                "sha256": text_sha256(canonical_text),
                "length_codepoints": len(canonical_text),
            },
            "structure_quality": self._structure_quality,
            "eligibility": {
                "mode": self._eligibility_mode,
                "reason_codes": list(self._eligibility_reason_codes),
            },
            "units": [dict(item) for item in self._units],
            "boundaries": [dict(item) for item in self._boundaries],
            "pages": [dict(item) for item in self._pages],
            "warnings": list(self._warnings),
        }
        validate_source_ledger(ledger, canonical_text)
        return canonical_text, ledger

    def _append_boundary(
        self,
        text: str,
        *,
        left_unit_id: str | None,
        right_unit_id: str | None,
        kind: str,
        structure_origin: str,
    ) -> None:
        """Append one exact source gap as a ledger boundary."""
        if not text:
            return
        start = self._length
        self._parts.append(text)
        self._length += len(text)
        self._boundaries.append(
            {
                "boundary_id": f"b-{len(self._boundaries) + 1:06d}",
                "start": start,
                "end": self._length,
                "left_unit_id": left_unit_id,
                "right_unit_id": right_unit_id,
                "kind": str(kind or "line"),
                "structure_origin": structure_origin,
            }
        )


def text_sha256(text: str) -> str:
    """Return the SHA-256 digest of one UTF-8 text payload."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of one source file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_source_artifacts(
    project_root: str | Path,
    canonical_text: str,
    ledger: dict[str, object],
) -> tuple[Path, Path]:
    """Atomically write canonical text and its source ledger."""
    root = Path(project_root)
    text_path = root / config.EXTRACTED_TEXT_FILE_NAME
    ledger_path = root / config.SOURCE_LEDGER_FILE_NAME
    validate_source_ledger(ledger, canonical_text)
    write_text_atomic(text_path, canonical_text)
    write_json_atomic(ledger_path, ledger)
    return text_path, ledger_path


def load_source_ledger(project_root: str | Path) -> dict[str, object]:
    """Load and validate the ledger against the canonical extracted text."""
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
    """Return one unit's exact canonical source slice."""
    return str(canonical_text)[int(unit["start"]) : int(unit["end"])]


def validate_source_ledger(payload: object, canonical_text: str) -> None:
    """Validate schema, hashes, interval ownership, and referenced unit ids."""
    if not isinstance(payload, dict):
        raise SourceLedgerError("Source ledger must be one JSON object.")
    required_fields = {
        "schema_version",
        "source",
        "canonical_text",
        "structure_quality",
        "eligibility",
        "units",
        "boundaries",
        "pages",
        "warnings",
    }
    if set(payload) != required_fields:
        raise SourceLedgerError("Source ledger fields do not match schema version 1.")
    if payload.get("schema_version") != SOURCE_LEDGER_SCHEMA_VERSION:
        raise SourceLedgerError("Unsupported source ledger schema version.")
    source = payload.get("source")
    canonical = payload.get("canonical_text")
    eligibility = payload.get("eligibility")
    units = payload.get("units")
    boundaries = payload.get("boundaries")
    pages = payload.get("pages")
    warnings = payload.get("warnings")
    if not isinstance(source, dict) or set(source) != {"format", "sha256", "adapter_version", "encoding"}:
        raise SourceLedgerError("Source ledger source metadata is invalid.")
    if not isinstance(canonical, dict) or set(canonical) != {"sha256", "length_codepoints"}:
        raise SourceLedgerError("Source ledger canonical-text metadata is invalid.")
    if payload.get("structure_quality") not in _VALID_STRUCTURE_QUALITIES:
        raise SourceLedgerError("Source ledger structure quality is invalid.")
    if not isinstance(eligibility, dict) or set(eligibility) != {"mode", "reason_codes"}:
        raise SourceLedgerError("Source ledger eligibility metadata is invalid.")
    if not isinstance(eligibility.get("reason_codes"), list):
        raise SourceLedgerError("Source ledger eligibility reason codes must be a list.")
    if not isinstance(units, list) or not units:
        raise SourceLedgerError("Source ledger requires at least one unit.")
    if not isinstance(boundaries, list) or not isinstance(pages, list) or not isinstance(warnings, list):
        raise SourceLedgerError("Source ledger collections are invalid.")
    if canonical.get("length_codepoints") != len(canonical_text):
        raise SourceLedgerError("Source ledger text length does not match extracted_text.txt.")
    if canonical.get("sha256") != text_sha256(canonical_text):
        raise SourceLedgerError("Source ledger text hash does not match extracted_text.txt.")

    unit_ids: set[str] = set()
    intervals: list[tuple[int, int, str]] = []
    for unit in units:
        if not isinstance(unit, dict):
            raise SourceLedgerError("Source ledger unit must be an object.")
        expected = {
            "unit_id",
            "start",
            "end",
            "kind",
            "structure_origin",
            "parent_id",
            "locator",
            "native",
            "layout",
        }
        if set(unit) != expected:
            raise SourceLedgerError("Source ledger unit fields are invalid.")
        unit_id = str(unit.get("unit_id") or "")
        if not unit_id or unit_id in unit_ids:
            raise SourceLedgerError("Source ledger unit ids must be unique.")
        unit_ids.add(unit_id)
        _validate_interval(unit, len(canonical_text), "unit")
        if unit.get("structure_origin") not in _VALID_STRUCTURE_ORIGINS:
            raise SourceLedgerError("Source ledger unit origin is invalid.")
        intervals.append((int(unit["start"]), int(unit["end"]), unit_id))

    boundary_ids: set[str] = set()
    for boundary in boundaries:
        if not isinstance(boundary, dict):
            raise SourceLedgerError("Source ledger boundary must be an object.")
        expected = {
            "boundary_id",
            "start",
            "end",
            "left_unit_id",
            "right_unit_id",
            "kind",
            "structure_origin",
        }
        if set(boundary) != expected:
            raise SourceLedgerError("Source ledger boundary fields are invalid.")
        boundary_id = str(boundary.get("boundary_id") or "")
        if not boundary_id or boundary_id in boundary_ids:
            raise SourceLedgerError("Source ledger boundary ids must be unique.")
        boundary_ids.add(boundary_id)
        _validate_interval(boundary, len(canonical_text), "boundary")
        for field_name in ("left_unit_id", "right_unit_id"):
            reference = boundary.get(field_name)
            if reference is not None and reference not in unit_ids:
                raise SourceLedgerError("Source ledger boundary references an unknown unit.")
        if boundary.get("structure_origin") not in _VALID_STRUCTURE_ORIGINS:
            raise SourceLedgerError("Source ledger boundary origin is invalid.")
        intervals.append((int(boundary["start"]), int(boundary["end"]), boundary_id))

    intervals.sort(key=lambda item: (item[0], item[1]))
    cursor = 0
    for start, end, _identifier in intervals:
        if start != cursor:
            raise SourceLedgerError("Source ledger intervals contain a gap or overlap.")
        cursor = end
    if cursor != len(canonical_text):
        raise SourceLedgerError("Source ledger intervals do not cover extracted_text.txt.")


def _validate_interval(item: dict[str, Any], source_length: int, label: str) -> None:
    """Validate one half-open source interval."""
    start = item.get("start")
    end = item.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start or end > source_length:
        raise SourceLedgerError(f"Source ledger {label} interval is invalid.")


def _normalize_line_endings(text: str) -> str:
    """Normalize line endings without changing other source characters."""
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


# END OF FILE
