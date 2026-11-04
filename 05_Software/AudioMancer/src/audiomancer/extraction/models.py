#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file models.py
@brief Shared extraction input units, results and cancellation.
@details Part of the isolated extraction engine; no project or Qt dependencies.
"""

# IMPORTS

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# PUBLIC API


@dataclass(frozen=True)
class SourceEvent:
    """@brief One canonical text unit emitted by a source-format adapter."""

    text: str
    kind: str = "unknown"
    structure_origin: str = "inferred"
    boundary_before: str | None = None
    boundary_kind: str = "line"
    parent_id: str | None = None
    locator: dict[str, object] = field(default_factory=dict)
    native: dict[str, object] | None = None
    layout: dict[str, object] | None = None


@dataclass(frozen=True)
class ExtractionAdapterResult:
    """@brief One adapter's canonical event stream and structural diagnostics."""

    events: list[SourceEvent]
    warnings: list[str]
    pages: list[dict[str, object]]
    structure_quality: str
    eligibility_mode: str
    eligibility_reason_codes: list[str]
    encoding: str | None
    progress_total: int
    page_count: int | None


@dataclass(frozen=True)
class ExtractedDocument:
    """@brief Validated canonical text, provenance and format diagnostics."""

    text: str
    ledger: dict[str, object]
    page_count: int | None


class ExtractionCancelledError(Exception):
    """@brief A caller requested cooperative cancellation of document extraction."""


def check_cancelled(requested: Callable[[], bool] | None) -> None:
    """@brief Stop at an extraction boundary when the caller requested cancellation."""
    if requested is not None and requested():
        raise ExtractionCancelledError("Text extraction cancelled.")


def _emit_adapter_progress(callback, current: int, total: int, message: str) -> None:
    """@brief Emit one adapter progress update when requested."""
    if callback is not None:
        callback(int(current), max(1, int(total)), str(message))


# END OF FILE
