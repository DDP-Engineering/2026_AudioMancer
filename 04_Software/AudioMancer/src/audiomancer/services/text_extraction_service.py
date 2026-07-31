#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""
@file text_extraction_service.py
@brief Structural source extraction orchestration for AudioMancer.
@details Builds canonical extracted text, source ledgers, and strict extraction
         metadata while coordinating cancellation and downstream resets.
"""

from functools import partial
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import source_ledger_service, text_extraction_adapters
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    emit_progress_update,
    raise_if_cancelled,
    reset_operation_data,
    resolve_project_relative_path,
)
from audiomancer.services.persistence_service import write_json_atomic

_EXTRACTION_LOGGER = get_component_logger("text_extraction")
_emit_progress = partial(emit_progress_update, include_token_usage=False)
ExtractionMetadataPayload = dict[str, object]
_METADATA_FIELDS = frozenset(
    (
        "status",
        "progress_current",
        "progress_total",
        "warnings",
        "character_count",
        "word_count",
        "line_count",
        "page_count",
    )
)
_PERSISTED_STATUSES = frozenset(("running", "cancelled", "failed", "completed"))
_LEGACY_EXTRACTION_FILE_NAMES = ("extraction_report.json", "extraction_state.json")


class ExtractionMetadataError(ValueError):
    """Raised when Extraction artifacts do not match the current strict contract."""


@trace_function(_EXTRACTION_LOGGER)
def extract_text(
    project_root: str | Path,
    manifest: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> ExtractionMetadataPayload:
    """Rebuild canonical text and its structural ledger from the registered source."""
    root = Path(project_root)
    source_document = _source_document_from_manifest(manifest)
    if source_document is None:
        raise ValueError("No imported source is available for text extraction.")
    source_path = _source_path_from_manifest(root, source_document)
    metadata_path = root / config.EXTRACTION_METADATA_FILE_NAME
    file_type = str(source_document["file_type"])
    _emit_status(progress_callback, f"Preparing {file_type.upper()} extraction...")

    for artifact_name in (config.EXTRACTED_TEXT_FILE_NAME, config.SOURCE_LEDGER_FILE_NAME):
        (root / artifact_name).unlink(missing_ok=True)
    running_metadata = _build_metadata(
        status="running",
        progress_current=0,
        progress_total=1,
        warnings=[],
        character_count=None,
        word_count=None,
        line_count=None,
        page_count=None,
    )
    write_json_atomic(metadata_path, running_metadata)

    def _record_progress(current: int, total: int, message: str) -> None:
        running_metadata["progress_current"] = max(0, int(current))
        running_metadata["progress_total"] = max(1, int(total))
        write_json_atomic(metadata_path, running_metadata)
        _emit_progress(progress_callback, current, total, message)

    try:
        adapter_result = text_extraction_adapters.extract_source_events(
            source_path,
            file_type,
            progress_callback=_record_progress,
            cancel_requested=cancel_requested,
        )
        raise_if_cancelled(cancel_requested)
        builder = source_ledger_service.CanonicalDocumentBuilder(
            source_format=file_type,
            source_sha256=source_ledger_service.file_sha256(source_path),
            encoding=adapter_result.encoding,
            structure_quality=adapter_result.structure_quality,
            eligibility_mode=adapter_result.eligibility_mode,
            eligibility_reason_codes=adapter_result.eligibility_reason_codes,
            pages=adapter_result.pages,
            warnings=adapter_result.warnings,
        )
        for event in adapter_result.events:
            raise_if_cancelled(cancel_requested)
            builder.add(event)
        canonical_text, ledger = builder.build()
        source_ledger_service.write_source_artifacts(root, canonical_text, ledger)
        display_text = canonical_text.rstrip("\n")
        completed = _build_metadata(
            status="completed",
            progress_current=max(1, adapter_result.progress_total),
            progress_total=max(1, adapter_result.progress_total),
            warnings=adapter_result.warnings,
            character_count=len(display_text),
            word_count=len(display_text.split()),
            line_count=len(display_text.splitlines()),
            page_count=adapter_result.page_count,
        )
        write_extraction_metadata(root, completed)
        return completed
    except OperationCancelledError:
        _persist_interrupted_metadata(metadata_path, "cancelled")
        raise
    except Exception:
        _persist_interrupted_metadata(metadata_path, "failed")
        raise


@trace_function(_EXTRACTION_LOGGER)
def load_extraction_metadata(project_root: str | Path) -> ExtractionMetadataPayload | None:
    """Load strict Extraction metadata and validate completed artifacts."""
    root = Path(project_root)
    if _legacy_sidecars_exist(root):
        raise _incompatible_metadata_error("Legacy extraction sidecars require Reset Extraction.")
    metadata_path = root / config.EXTRACTION_METADATA_FILE_NAME
    if not metadata_path.is_file():
        if any(
            (root / name).exists()
            for name in (config.EXTRACTED_TEXT_FILE_NAME, config.SOURCE_LEDGER_FILE_NAME)
        ):
            raise _incompatible_metadata_error("Extraction artifacts exist without current metadata.")
        return None
    metadata = _load_metadata_path(metadata_path)
    _validate_artifact_pair(root, metadata)
    return metadata


@trace_function(_EXTRACTION_LOGGER)
def write_extraction_metadata(
    project_root: str | Path,
    metadata: ExtractionMetadataPayload,
) -> Path:
    """Validate and atomically persist Extraction metadata."""
    root = Path(project_root)
    if _legacy_sidecars_exist(root):
        raise _incompatible_metadata_error("Legacy extraction sidecars require Reset Extraction.")
    _validate_metadata(metadata)
    _validate_artifact_pair(root, metadata)
    path = root / config.EXTRACTION_METADATA_FILE_NAME
    write_json_atomic(path, metadata)
    return path


@trace_function(_EXTRACTION_LOGGER)
def reset_extraction_and_downstream(project_root: str | Path) -> None:
    """Remove Extraction and every downstream generated artifact."""
    reset_operation_data(project_root, "extraction", include_current=True)


def _write_running_metadata(
    metadata_path: Path,
    progress_current: int,
    progress_total: int,
    warnings: list[str],
    page_count: int | None,
) -> None:
    """Persist one running progress snapshot atomically."""
    write_json_atomic(
        metadata_path,
        _build_metadata(
            status="running",
            progress_current=progress_current,
            progress_total=progress_total,
            warnings=warnings,
            character_count=None,
            word_count=None,
            line_count=None,
            page_count=page_count,
        ),
    )


def _build_metadata(
    *,
    status: str,
    progress_current: int,
    progress_total: int,
    warnings: list[str],
    character_count: int | None,
    word_count: int | None,
    line_count: int | None,
    page_count: int | None,
) -> ExtractionMetadataPayload:
    return {
        "status": str(status),
        "progress_current": int(progress_current),
        "progress_total": int(progress_total),
        "warnings": [str(item) for item in warnings],
        "character_count": character_count,
        "word_count": word_count,
        "line_count": line_count,
        "page_count": page_count,
    }


def _source_path_from_manifest(project_root: Path, source_document: dict[str, object]) -> Path:
    source_path = resolve_project_relative_path(
        project_root,
        str(source_document["stored_relative_path"]),
    )
    if not source_path.is_file():
        raise FileNotFoundError(f"Imported source file is missing: {source_path}")
    return source_path


def _source_document_from_manifest(manifest: dict[str, object]) -> dict[str, object] | None:
    source_document = manifest.get("source_document")
    return dict(source_document) if isinstance(source_document, dict) else None


def _load_metadata_path(path: Path) -> ExtractionMetadataPayload:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _incompatible_metadata_error("extraction_metadata.json is unreadable or malformed.") from error
    _validate_metadata(payload)
    return payload


def _validate_metadata(payload: object) -> None:
    if not isinstance(payload, dict) or set(payload) != _METADATA_FIELDS:
        raise _incompatible_metadata_error("Metadata fields do not match the current schema.")
    if payload.get("status") not in _PERSISTED_STATUSES:
        raise _incompatible_metadata_error("Extraction status is unsupported.")
    for field_name in ("progress_current", "progress_total"):
        value = payload[field_name]
        if type(value) is not int or int(value) < 0:
            raise _incompatible_metadata_error(f"{field_name} must be a non-negative integer.")
    current = int(payload["progress_current"])
    total = int(payload["progress_total"])
    if current > total:
        raise _incompatible_metadata_error("progress_current cannot exceed progress_total.")
    warnings = payload["warnings"]
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        raise _incompatible_metadata_error("warnings must be an array of strings.")
    page_count = payload["page_count"]
    if page_count is not None and (type(page_count) is not int or page_count < 0):
        raise _incompatible_metadata_error("page_count must be null or a non-negative integer.")
    statistics = (payload["character_count"], payload["word_count"], payload["line_count"])
    if payload["status"] == "completed":
        if current != total:
            raise _incompatible_metadata_error("Completed extraction progress must equal its total.")
        if any(type(value) is not int or value < 0 for value in statistics):
            raise _incompatible_metadata_error("Completed extraction statistics must be non-negative integers.")
    elif any(value is not None for value in statistics):
        raise _incompatible_metadata_error("Incomplete extraction statistics must be null.")


def _validate_artifact_pair(project_root: Path, metadata: ExtractionMetadataPayload) -> None:
    if metadata["status"] != "completed":
        return
    try:
        source_ledger_service.load_source_ledger(project_root)
    except (OSError, UnicodeError, source_ledger_service.SourceLedgerError) as error:
        raise _incompatible_metadata_error(
            "Completed metadata requires matching extracted_text.txt and source_ledger.json."
        ) from error


def _persist_interrupted_metadata(metadata_path: Path, status: str) -> None:
    metadata = (
        _load_metadata_path(metadata_path)
        if metadata_path.is_file()
        else _build_metadata(
            status=status,
            progress_current=0,
            progress_total=0,
            warnings=[],
            character_count=None,
            word_count=None,
            line_count=None,
            page_count=None,
        )
    )
    metadata["status"] = status
    metadata["character_count"] = None
    metadata["word_count"] = None
    metadata["line_count"] = None
    _validate_metadata(metadata)
    write_json_atomic(metadata_path, metadata)


def _legacy_sidecars_exist(project_root: Path) -> bool:
    return any((project_root / name).exists() for name in _LEGACY_EXTRACTION_FILE_NAMES)


def _incompatible_metadata_error(reason: str) -> ExtractionMetadataError:
    return ExtractionMetadataError(
        f"Extraction data is incompatible: {reason} Use Reset Extraction before continuing."
    )


def _emit_status(progress_callback, message: str) -> None:
    if callable(progress_callback):
        progress_callback(0, 1, 0, message)
