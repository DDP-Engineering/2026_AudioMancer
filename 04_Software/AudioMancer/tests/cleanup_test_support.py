#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file cleanup_test_support.py
@brief Shared fixtures for the Cleanup and Chunking quality contract.
@details Builds source-ledger projects and exact contract assertions without
         depending on production persistence helpers.
"""

from __future__ import annotations

from collections.abc import Iterable
import hashlib
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import project_workspace_service, source_ledger_service

CLEANUP_ROOT_FIELDS = frozenset(
    {
        "status",
        "phase",
        "started_at",
        "updated_at",
        "completed_at",
        "source_hash",
        "ledger_hash",
        "policy_hash",
        "prompt_hash",
        "profile_fingerprint",
        "document_profile",
        "unit_operations",
        "boundaries",
        "paragraphs",
        "progress",
        "warnings",
        "token_usage",
        "quality_report",
        "output_hash",
        "user_modified",
        "structure_source",
    }
)

BOUNDARY_CHOICES = frozenset(
    {
        "join_with_space",
        "set_paragraph_break",
        "set_semantic_line_break",
        "dehyphenate",
        "join_preserving_hyphen",
        "document_end",
    }
)

UNIT_ROLES = frozenset(
    {
        "body",
        "heading",
        "scene_separator",
        "list_item",
        "verse",
        "preformatted",
        "footnote",
        "page_artifact",
    }
)


def build_ledger(
    texts: Iterable[str],
    *,
    source_format: str = "txt",
    kinds: Iterable[str] | None = None,
    boundaries: Iterable[tuple[str, str]] | None = None,
    origins: Iterable[str] | None = None,
    layouts: Iterable[dict[str, object] | None] | None = None,
    locators: Iterable[dict[str, object] | None] | None = None,
    structure_quality: str = "text_only",
    warnings: Iterable[str] | None = None,
) -> tuple[str, dict[str, object]]:
    """Build one compact canonical source ledger for behavior tests."""
    text_items = list(texts)
    kind_items = list(kinds or ["unknown"] * len(text_items))
    boundary_items = list(boundaries or [("\n", "physical_line")] * max(0, len(text_items) - 1))
    origin_items = list(origins or ["inferred"] * len(text_items))
    layout_items = list(layouts or [None] * len(text_items))
    locator_items = list(locators or [None] * len(text_items))
    if not (
        len(kind_items)
        == len(origin_items)
        == len(layout_items)
        == len(locator_items)
        == len(text_items)
    ):
        raise AssertionError("Cleanup ledger fixture columns must have equal lengths.")
    if len(boundary_items) != max(0, len(text_items) - 1):
        raise AssertionError("Cleanup ledger fixture requires one boundary between adjacent units.")

    pages = []
    page_indexes = {
        int(item["page_index"])
        for item in locator_items
        if isinstance(item, dict) and isinstance(item.get("page_index"), int)
    }
    if page_indexes:
        pages = [{"page_index": page_index} for page_index in sorted(page_indexes)]
    builder = source_ledger_service.CanonicalDocumentBuilder(
        source_format=source_format,
        source_sha256=f"{source_format}-source",
        structure_quality=structure_quality,
        pages=pages,
        warnings=list(warnings or []),
    )
    for index, text in enumerate(text_items):
        separator, boundary_kind = (None, "document_start") if index == 0 else boundary_items[index - 1]
        builder.add(
            source_ledger_service.SourceEvent(
                text,
                kind=kind_items[index],
                structure_origin=origin_items[index],
                boundary_before=separator,
                boundary_kind=boundary_kind,
                locator=dict(locator_items[index] or {}),
                layout=None if layout_items[index] is None else dict(layout_items[index]),
            )
        )
    return builder.build()


def build_project(
    tmp_path: Path,
    name: str,
    canonical_text: str,
    ledger: dict[str, object],
) -> tuple[Path, dict[str, object]]:
    """Create one project whose Extraction artifacts are already complete."""
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    source_format = str(ledger["source"]["format"])
    source_path = project_root / f"story.{source_format}"
    source_path.write_text(canonical_text, encoding="utf-8")
    manifest["source_document"] = {
        "original_name": source_path.name,
        "stored_relative_path": source_path.name,
        "file_type": source_format,
        "imported_at": "2026-07-28T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    source_ledger_service.write_source_artifacts(project_root, canonical_text, ledger)
    project_workspace_service.save_manifest(manifest, project_root)
    return project_root, manifest


def read_cleanup_document(project_root: Path) -> dict[str, object]:
    """Read one persisted Cleanup document without production normalization."""
    payload = json.loads((project_root / config.CLEANUP_DOCUMENT_FILE_NAME).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError("Expected cleanup.json to contain one object.")
    return payload


def assert_strict_cleanup_document(document: dict[str, object]) -> None:
    """Assert the exact root contract and the non-duplicating nested records."""
    assert set(document) == CLEANUP_ROOT_FIELDS
    assert document["status"] in {"running", "paused", "finalizing", "completed", "failed"}
    assert document["phase"] in {"analysis", "adjudication", "rendering", "done"}
    assert document["structure_source"] in {"cleanup_roles", "user_edited"}
    assert "schema_version" not in document
    assert "prompt_schema_version" not in document
    assert all("text" not in paragraph for paragraph in document["paragraphs"])
    for decision in document["boundaries"]:
        assert set(decision) == {
            "boundary_id",
            "left_unit_id",
            "right_unit_id",
            "kind",
            "page_transition",
            "left_role",
            "right_role",
            "prior",
            "adjudication",
            "final",
        }
        assert decision["final"]["choice"] in BOUNDARY_CHOICES


def make_profile(
    *,
    profile_id: str = "local",
    model_name: str = "qwen3.6-27b",
    context_window: int = 32_768,
    max_output_tokens: int = config.DEFAULT_LLM_MAX_OUTPUT_TOKENS,
    supports_structured_output: bool = True,
) -> dict[str, object]:
    """Return one minimal Cleanup adjudication profile."""
    return {
        "id": profile_id,
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "",
        "model_name": model_name,
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "request_timeout_seconds": 90,
        "temperature": 0.0,
        "supports_structured_output": supports_structured_output,
        "enabled": True,
    }


def write_completed_cleanup(
    project_root: Path,
    canonical_text: str,
    ledger: dict[str, object],
    cleaned_text: str,
    paragraph_specs: Iterable[tuple[str, str]],
) -> dict[str, object]:
    """Persist a strict completed Cleanup fixture for downstream tests."""
    paragraphs = []
    search_start = 0
    for index, (paragraph_text, role) in enumerate(paragraph_specs, start=1):
        output_start = cleaned_text.index(paragraph_text, search_start)
        output_end = output_start + len(paragraph_text)
        search_start = output_end
        paragraphs.append(
            {
                "paragraph_id": f"paragraph-{index:06d}",
                "output_start": output_start,
                "output_end": output_end,
                "role": role,
                "confidence": "strong",
                "reason_codes": ["test_fixture"],
                "source_page_start": None,
                "source_page_end": None,
                "starts_after_page_transition": False,
                "crosses_page_transition": False,
                "source_unit_ids": [f"u-{index:06d}"],
                "provenance_available": True,
            }
        )
    document = {
        "status": "completed",
        "phase": "done",
        "started_at": "2026-07-28T12:00:00+00:00",
        "updated_at": "2026-07-28T12:00:01+00:00",
        "completed_at": "2026-07-28T12:00:01+00:00",
        "source_hash": source_ledger_service.text_sha256(canonical_text),
        "ledger_hash": _json_hash(ledger),
        "policy_hash": "0" * 64,
        "prompt_hash": "1" * 64,
        "profile_fingerprint": None,
        "document_profile": {
            "source_format": ledger["source"]["format"],
            "structure_quality": ledger["structure_quality"],
            "language": "en",
        },
        "unit_operations": [],
        "boundaries": [],
        "paragraphs": paragraphs,
        "progress": {
            "question_count": 0,
            "batch_order": [],
            "next_batch_index": 0,
            "completed_request_count": 0,
            "estimated_request_count": 0,
            "estimated_input_tokens": 0,
        },
        "warnings": [],
        "token_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "usage_available": False,
        },
        "quality_report": {
            "introduced_fusion_count": 0,
            "projection_violation_count": 0,
            "invalid_operation_count": 0,
            "unclassified_boundary_count": 0,
            "low_confidence_count": 0,
            "fallback_count": 0,
            "override_count": 0,
            "override_rate": 0.0,
            "failed_batch_count": 0,
            "online_fragment_count": 0,
            "online_backend": None,
        },
        "output_hash": source_ledger_service.text_sha256(cleaned_text),
        "user_modified": False,
        "structure_source": "cleanup_roles",
    }
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(cleaned_text, encoding="utf-8")
    (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return document


def _json_hash(payload: object) -> str:
    """Return the canonical JSON hash used by Cleanup fixtures."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# END OF FILE
