#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_extraction_service.py
@brief Deterministic source-text extraction helpers for AudioMancer.
@details Extracts normalized text from supported source formats and persists
         exactly one text artifact plus one strict, resumable metadata document.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.5.4
"""

# IMPORTS

from functools import partial
from html.parser import HTMLParser
import json
from pathlib import Path

from docx import Document
import ebooklib
from ebooklib import epub
import fitz
from odf import teletype
from odf.opendocument import load as load_odf_document
from striprtf.striprtf import rtf_to_text

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    emit_progress_update,
    raise_if_cancelled,
    reset_operation_data,
    resolve_project_relative_path,
)
from audiomancer.services.persistence_service import write_json_atomic, write_text_atomic

# CONSTANTS

# @brief Component logger used by deterministic text extraction.
_EXTRACTION_LOGGER = get_component_logger("text_extraction")
_emit_progress = partial(emit_progress_update, include_token_usage=False)
# @brief Authoritative persisted extraction metadata payload type.
ExtractionMetadataPayload = dict[str, object]
# @brief Internal extraction-units payload type used during format-specific parsing.
ExtractionUnitsPayload = dict[str, object]
# @brief Stable extraction-folder name used for local artifact path construction.
_EXTRACTION_FOLDER_NAME = config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
# @brief Stable file name used for extracted raw text output.
_EXTRACTION_OUTPUT_NAME = config.EXTRACTED_TEXT_FILE_NAME
# @brief Stable file name used for authoritative extraction metadata.
_EXTRACTION_METADATA_NAME = config.EXTRACTION_METADATA_FILE_NAME
# @brief Reset-only legacy extraction sidecars rejected by the strict contract.
_LEGACY_EXTRACTION_FILE_NAMES = ("extraction_report.json", "extraction_state.json")
# @brief Canonical separator inserted between extracted pages for downstream cleanup.
_PAGE_BREAK_SEPARATOR = "\n\n\f\n\n"
# @brief Exact root fields accepted by the strict extraction metadata contract.
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
# @brief Persisted extraction status tokens.
_PERSISTED_STATUSES = frozenset(("running", "cancelled", "failed", "completed"))
# @brief Extraction statuses that support granular continuation.
_RESUMABLE_STATUSES = frozenset(("running", "cancelled", "failed"))


class ExtractionMetadataError(ValueError):
    """
    @brief      Raised when persisted extraction artifacts do not match the strict contract.
    @exception  None
    @version    0.1.0
    """


class _HtmlTextExtractor(HTMLParser):
    """
    @brief      Convert one simple HTML or XHTML fragment into plain text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """

    def __init__(self) -> None:
        """
        @brief      Initialize one HTML text extractor.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        """
        @brief      Insert block separators for relevant HTML tags.
        @param[in]  tag Lowercase HTML tag name.
        @param[in]  attrs Ignored HTML attributes.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        _ = attrs
        if tag in {
            "p",
            "div",
            "section",
            "article",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "br",
        }:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """
        @brief      Insert block separators after relevant HTML tags.
        @param[in]  tag Lowercase HTML tag name.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        if tag in {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "li"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        """
        @brief      Append one plain-text data fragment.
        @param[in]  data HTML data fragment.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        self._parts.append(data)

    def plain_text(self) -> str:
        """
        @brief      Return the accumulated plain text.
        @return     Extracted plain text string.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-06
        @version    0.1.0
        """
        return "".join(self._parts)


# PUBLIC API


@trace_function(_EXTRACTION_LOGGER)
def extract_text(
    project_root: str | Path,
    manifest: dict[str, object],
    progress_callback=None,
    cancel_requested=None,
) -> ExtractionMetadataPayload:
    """
    @brief      Extract source text for one active AudioMancer project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  progress_callback Optional zero-copy progress callback.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Completed authoritative extraction metadata document.
    @exception  FileNotFoundError Raised when the imported source file is missing.
    @exception  ValueError Raised when no extractable text is available.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.6
    """
    resolved_project_root = Path(project_root)
    source_document = _source_document_from_manifest(manifest)
    if source_document is None:
        raise ValueError("No imported source is available for text extraction.")

    extraction_dir = resolved_project_root / _EXTRACTION_FOLDER_NAME
    extraction_dir.mkdir(parents=True, exist_ok=True)
    source_path = _source_path_from_manifest(resolved_project_root, source_document)
    output_path = extraction_dir / _EXTRACTION_OUTPUT_NAME
    metadata_path = extraction_dir / _EXTRACTION_METADATA_NAME

    file_type = str(source_document["file_type"])
    existing_metadata = load_extraction_metadata(resolved_project_root)
    warnings = _warnings_from_metadata(existing_metadata)
    _emit_status(progress_callback, _preparation_message_for_file_type(file_type))
    try:
        if _supports_incremental_resume(file_type) and _can_resume_from_metadata(
            existing_metadata,
            source_path,
            output_path,
        ):
            progress_payload = _resume_extraction(
                source_path,
                output_path,
                metadata_path,
                file_type,
                warnings,
                progress_callback,
                cancel_requested,
            )
        else:
            progress_payload = _start_fresh_extraction(
                source_path,
                output_path,
                metadata_path,
                file_type,
                warnings,
                progress_callback,
                cancel_requested,
            )

        if not output_path.is_file():
            if file_type == "pdf":
                raise ValueError("PDF source did not contain extractable text. OCR is not supported in this phase.")
            raise ValueError("Source did not contain extractable text.")

        normalized_text = _normalize_text(output_path.read_text(encoding="utf-8")).strip()
        if not normalized_text:
            if file_type == "pdf":
                raise ValueError("PDF source did not contain extractable text. OCR is not supported in this phase.")
            raise ValueError("Source did not contain extractable text.")

        write_text_atomic(output_path, normalized_text + "\n")
        completed_metadata = _build_metadata(
            status="completed",
            progress_current=int(progress_payload["progress_total"]),
            progress_total=int(progress_payload["progress_total"]),
            warnings=list(progress_payload["warnings"]),
            character_count=len(normalized_text),
            word_count=len(normalized_text.split()),
            line_count=len(normalized_text.splitlines()),
            page_count=_optional_non_negative_int(progress_payload.get("page_count")),
        )
        write_extraction_metadata(resolved_project_root, completed_metadata)
        return completed_metadata
    except OperationCancelledError:
        _persist_interrupted_metadata(metadata_path, "cancelled")
        raise
    except Exception:
        _persist_interrupted_metadata(metadata_path, "failed")
        raise


@trace_function(_EXTRACTION_LOGGER)
def load_extraction_metadata(project_root: str | Path) -> ExtractionMetadataPayload | None:
    """
    @brief      Load and strictly validate the authoritative extraction metadata.
    @param[in]  project_root Active project root folder.
    @return     Persisted extraction metadata or `None`.
    @exception  ExtractionMetadataError Raised for legacy or incompatible artifacts.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.1
    """
    resolved_project_root = Path(project_root)
    if _legacy_sidecars_exist(resolved_project_root):
        raise _incompatible_metadata_error("Legacy extraction sidecars require Reset Extraction.")
    metadata_path = resolved_project_root / _EXTRACTION_FOLDER_NAME / _EXTRACTION_METADATA_NAME
    if not metadata_path.is_file():
        if (resolved_project_root / _EXTRACTION_OUTPUT_NAME).exists():
            raise _incompatible_metadata_error("Extracted text exists without current extraction metadata.")
        return None
    metadata = _load_metadata_path(metadata_path)
    _validate_artifact_pair(resolved_project_root, metadata)
    return metadata


@trace_function(_EXTRACTION_LOGGER)
def write_extraction_metadata(
    project_root: str | Path,
    metadata: ExtractionMetadataPayload,
) -> Path:
    """
    @brief      Validate and atomically persist the authoritative extraction metadata.
    @param[in]  project_root Active project root folder.
    @param[in]  metadata Candidate strict extraction metadata document.
    @return     Resolved metadata path.
    @exception  ExtractionMetadataError Raised when the payload is incompatible.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    resolved_project_root = Path(project_root)
    if _legacy_sidecars_exist(resolved_project_root):
        raise _incompatible_metadata_error("Legacy extraction sidecars require Reset Extraction.")
    _validate_metadata(metadata)
    _validate_artifact_pair(resolved_project_root, metadata)
    metadata_path = resolved_project_root / _EXTRACTION_FOLDER_NAME / _EXTRACTION_METADATA_NAME
    write_json_atomic(metadata_path, metadata)
    return metadata_path


def build_extraction_summary(
    metadata: ExtractionMetadataPayload | None,
) -> dict[str, object]:
    """
    @brief      Derive display and workflow summary values from extraction metadata.
    @param[in]  metadata Optional authoritative extraction metadata.
    @return     Derived non-authoritative summary.
    @exception  ExtractionMetadataError Raised when the payload is incompatible.
    @version    0.1.0
    """
    if metadata is None:
        return {
            "status": "not_started",
            "progress_current": 0,
            "progress_total": 0,
            "warning_count": 0,
        }
    _validate_metadata(metadata)
    return {
        "status": str(metadata["status"]),
        "progress_current": int(metadata["progress_current"]),
        "progress_total": int(metadata["progress_total"]),
        "warning_count": len(metadata["warnings"]),
    }


@trace_function(_EXTRACTION_LOGGER)
def reset_extraction_and_downstream(project_root: str | Path) -> None:
    """
    @brief      Clear extraction outputs and every downstream operation folder.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    reset_operation_data(
        project_root,
        "extraction",
        include_current=True,
    )


# HELPER FUNCTIONS


def _start_fresh_extraction(
    source_path: Path,
    output_path: Path,
    metadata_path: Path,
    file_type: str,
    warnings: list[str],
    progress_callback,
    cancel_requested,
) -> dict[str, object]:
    """Start extraction from the beginning of the imported source."""
    if output_path.exists():
        output_path.unlink()
    progress_payload = _build_progress_units(source_path, file_type)
    progress_units = list(progress_payload["units"])
    warnings[:] = [*warnings, *list(progress_payload["warnings"])]
    total_units = len(progress_units)
    page_count = _optional_non_negative_int(progress_payload.get("page_count"))
    _write_running_metadata(metadata_path, 0, total_units, warnings, page_count)
    _process_units(
        progress_units,
        source_path,
        output_path,
        metadata_path,
        warnings,
        file_type,
        page_count,
        0,
        progress_callback,
        cancel_requested,
    )
    return {
        "progress_total": total_units,
        "warnings": list(warnings),
        "page_count": page_count,
    }


def _resume_extraction(
    source_path: Path,
    output_path: Path,
    metadata_path: Path,
    file_type: str,
    warnings: list[str],
    progress_callback,
    cancel_requested,
) -> dict[str, object]:
    """Continue one interrupted incremental extraction."""
    existing_metadata = _load_metadata_path(metadata_path)
    next_unit_index = int(existing_metadata["progress_current"])
    progress_payload = _build_progress_units(source_path, file_type)
    progress_units = list(progress_payload["units"])
    warnings[:] = [*warnings, *list(progress_payload["warnings"])]
    total_units = len(progress_units)
    if next_unit_index > total_units:
        raise _incompatible_metadata_error("Saved progress exceeds the current source unit count.")
    page_count = _optional_non_negative_int(progress_payload.get("page_count"))
    _write_running_metadata(metadata_path, next_unit_index, total_units, warnings, page_count)
    _process_units(
        progress_units,
        source_path,
        output_path,
        metadata_path,
        warnings,
        file_type,
        page_count,
        next_unit_index,
        progress_callback,
        cancel_requested,
    )
    return {
        "progress_total": total_units,
        "warnings": list(warnings),
        "page_count": page_count,
    }


def _process_units(
    progress_units: list[object],
    source_path: Path,
    output_path: Path,
    metadata_path: Path,
    warnings: list[str],
    file_type: str,
    page_count: int | None,
    start_index: int,
    progress_callback,
    cancel_requested,
) -> None:
    """Append ordered source units and checkpoint authoritative metadata."""
    if start_index == 0 and output_path.exists():
        output_path.unlink()

    total_units = len(progress_units)
    _emit_progress(progress_callback, start_index, total_units, "Text extraction in progress...")
    if file_type == "pdf":
        with fitz.open(source_path) as document:
            for unit_index in range(start_index, total_units):
                raise_if_cancelled(cancel_requested)
                page_index = int(progress_units[unit_index])
                unit_text = _normalize_text(document.load_page(page_index).get_text("text")).strip()
                if not unit_text:
                    warnings.append(f"PDF page {page_index + 1} did not contain extractable text.")
                if unit_text:
                    prefix = _PAGE_BREAK_SEPARATOR if output_path.exists() and output_path.stat().st_size > 0 else ""
                    with output_path.open("a", encoding="utf-8") as handle:
                        handle.write(prefix + unit_text)
                _write_running_metadata(
                    metadata_path,
                    unit_index + 1,
                    total_units,
                    warnings,
                    page_count,
                )
                _emit_progress(
                    progress_callback,
                    unit_index + 1,
                    total_units,
                    "Text extraction in progress...",
                )
        return

    for unit_index in range(start_index, total_units):
        raise_if_cancelled(cancel_requested)
        unit_text = _normalize_text(str(progress_units[unit_index])).strip()
        if unit_text:
            prefix = "\n\n" if output_path.exists() and output_path.stat().st_size > 0 else ""
            with output_path.open("a", encoding="utf-8") as handle:
                handle.write(prefix + unit_text)
        _write_running_metadata(
            metadata_path,
            unit_index + 1,
            total_units,
            warnings,
            page_count,
        )
        _emit_progress(
            progress_callback,
            unit_index + 1,
            total_units,
            "Text extraction in progress...",
        )


def _write_running_metadata(
    metadata_path: Path,
    progress_current: int,
    progress_total: int,
    warnings: list[str],
    page_count: int | None,
) -> None:
    """Persist one running extraction metadata checkpoint atomically."""
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
    status: str,
    progress_current: int,
    progress_total: int,
    warnings: list[str],
    character_count: int | None,
    word_count: int | None,
    line_count: int | None,
    page_count: int | None,
) -> ExtractionMetadataPayload:
    """Build one strict extraction metadata document."""
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


def _build_progress_units(source_path: Path, file_type: str) -> ExtractionUnitsPayload:
    """
    @brief      Extract one ordered list of normalized text units from one source snapshot.
    @param[in]  source_path Operation-local source snapshot path.
    @param[in]  file_type Normalized source-type token.
    @return     Ordered extracted text units with warning metadata.
    @exception  ValueError Raised when the source type is unsupported or empty.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.1
    """
    if file_type in {"txt", "md"}:
        return {"units": _text_units_from_plain_text(source_path), "warnings": [], "page_count": None}
    if file_type == "pdf":
        units, warnings = _pdf_progress_units(source_path)
        return {"units": units, "warnings": warnings, "page_count": len(units)}
    if file_type == "rtf":
        return {"units": _text_units_from_rtf(source_path), "warnings": [], "page_count": None}
    if file_type == "docx":
        return {"units": _text_units_from_docx(source_path), "warnings": [], "page_count": None}
    if file_type == "odt":
        return {"units": _text_units_from_odt(source_path), "warnings": [], "page_count": None}
    if file_type == "epub":
        return {"units": _text_units_from_epub(source_path), "warnings": [], "page_count": None}
    raise ValueError(f"Unsupported source type for extraction: {file_type}")


def _text_units_from_plain_text(source_path: Path) -> list[str]:
    """
    @brief      Extract one plain-text unit from a text-like source file.
    @param[in]  source_path Operation-local plain-text source path.
    @return     List containing one normalized text unit.
    @exception  UnicodeDecodeError Raised when decoding fails for all fallbacks.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    for encoding_name in ("utf-8-sig", "utf-8", "cp1250", "cp1252", "latin-1"):
        try:
            return [source_path.read_text(encoding=encoding_name)]
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("text", b"", 0, 1, f"Unable to decode text source: {source_path}")


def _pdf_progress_units(source_path: Path) -> tuple[list[int], list[str]]:
    """
    @brief      Build one ordered page-index list for incremental PDF extraction.
    @param[in]  source_path Operation-local PDF source path.
    @return     Tuple with ordered page-index list and static warnings list.
    @exception  ValueError Raised when the PDF contains no extractable text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    with fitz.open(source_path) as document:
        page_count = len(document)
    if page_count == 0:
        raise ValueError("PDF source did not contain extractable text. OCR is not supported in this phase.")
    return list(range(page_count)), []


def _text_units_from_rtf(source_path: Path) -> list[str]:
    """
    @brief      Extract one plain-text unit from an RTF source.
    @param[in]  source_path Operation-local RTF source path.
    @return     List containing one plain-text unit.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.1
    """
    source_bytes = source_path.read_bytes()
    if source_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise ValueError(
            "The selected .rtf file is actually a legacy Word .doc container. "
            "Legacy .doc extraction is not supported in this phase."
        )
    if not source_bytes.lstrip().startswith(b"{\\rtf"):
        raise ValueError("The selected .rtf file does not contain a valid RTF header.")
    for encoding_name in ("utf-8-sig", "utf-8", "cp1250", "cp1252", "latin-1"):
        try:
            plain_text = rtf_to_text(source_path.read_text(encoding=encoding_name))
            return _paragraph_units_from_text(plain_text)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("text", b"", 0, 1, f"Unable to decode RTF source: {source_path}")


def _text_units_from_docx(source_path: Path) -> list[str]:
    """
    @brief      Extract paragraph text units from one DOCX source.
    @param[in]  source_path Operation-local DOCX source path.
    @return     Ordered extracted paragraph list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    document = Document(source_path)
    return [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]


def _text_units_from_odt(source_path: Path) -> list[str]:
    """
    @brief      Extract paragraph text units from one ODT source.
    @param[in]  source_path Operation-local ODT source path.
    @return     Ordered extracted paragraph list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    document = load_odf_document(str(source_path))
    raw_text = teletype.extractText(document.text)
    return [line for line in _normalize_text(raw_text).split("\n") if line.strip()]


def _text_units_from_epub(source_path: Path) -> list[str]:
    """
    @brief      Extract ordered XHTML text units from one EPUB source.
    @param[in]  source_path Operation-local EPUB source path.
    @return     Ordered extracted item-text list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    book = epub.read_epub(str(source_path), options={"ignore_ncx": False})
    units: list[str] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        parser = _HtmlTextExtractor()
        parser.feed(item.get_content().decode("utf-8", errors="ignore"))
        units.extend(_paragraph_units_from_text(parser.plain_text()))
    return units


def _paragraph_units_from_text(text: str) -> list[str]:
    """
    @brief      Split one extracted text payload into stable paragraph-sized units.
    @param[in]  text Raw extracted text payload.
    @return     Ordered non-empty paragraph unit list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    normalized = _normalize_text(text)
    return [paragraph.strip() for paragraph in normalized.split("\n\n") if paragraph.strip()]


def _supports_incremental_resume(file_type: str) -> bool:
    """
    @brief      Determine whether one source type supports granular extraction resume.
    @param[in]  file_type Normalized source-type token.
    @return     True when the type supports checkpoint continuation.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    return file_type in {"pdf", "rtf", "docx", "odt", "epub"}


def _can_resume_from_metadata(
    metadata: ExtractionMetadataPayload | None,
    source_path: Path,
    output_path: Path,
) -> bool:
    """
    @brief      Decide whether saved extraction metadata can continue safely.
    @param[in]  metadata Optional authoritative extraction metadata.
    @param[in]  source_path Imported project-local source path.
    @param[in]  output_path Canonical extracted output path.
    @return     True when the extraction may continue from the saved checkpoint.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(metadata, dict):
        return False
    if str(metadata.get("status")) not in _RESUMABLE_STATUSES:
        return False
    if not source_path.is_file():
        return False
    if output_path.exists():
        return True
    return int(metadata.get("progress_current", 0)) == 0


def _source_path_from_manifest(project_root: Path, source_document: dict[str, object]) -> Path:
    """
    @brief      Resolve the root-level imported source file for extraction.
    @param[in]  project_root Active project root folder.
    @param[in]  source_document Normalized source-document payload.
    @return     Absolute imported source path.
    @exception  FileNotFoundError Raised when the root-level source file is missing.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.4.0
    """
    source_relative_path = str(source_document["stored_relative_path"])
    source_path = resolve_project_relative_path(project_root, source_relative_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Imported source file is missing: {source_path}")

    return source_path


def _source_document_from_manifest(manifest: dict[str, object]) -> dict[str, object] | None:
    """
    @brief      Extract one normalized source-document payload from the manifest.
    @param[in]  manifest Active project manifest payload.
    @return     Normalized source-document payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        return None
    return dict(source_document)


def _warnings_from_metadata(metadata: ExtractionMetadataPayload | None) -> list[str]:
    """
    @brief      Restore persisted warnings from authoritative extraction metadata.
    @param[in]  metadata Optional authoritative extraction metadata.
    @return     Ordered warning list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(metadata, dict):
        return []
    warnings = metadata.get("warnings", [])
    if not isinstance(warnings, list):
        return []
    return [str(item) for item in warnings]


def _load_metadata_path(metadata_path: Path) -> ExtractionMetadataPayload:
    """Load and strictly validate one exact extraction metadata path."""
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _incompatible_metadata_error("The metadata file is not valid JSON.") from exc
    _validate_metadata(payload)
    return dict(payload)


def _validate_metadata(payload: object) -> None:
    """Validate the exact extraction metadata schema and status invariants."""
    if not isinstance(payload, dict):
        raise _incompatible_metadata_error("The metadata root must be an object.")
    if set(payload) != _METADATA_FIELDS:
        raise _incompatible_metadata_error("The metadata root fields do not match the current contract.")
    if payload["status"] not in _PERSISTED_STATUSES:
        raise _incompatible_metadata_error("The extraction status is not supported.")
    for field_name in ("progress_current", "progress_total"):
        if type(payload[field_name]) is not int or int(payload[field_name]) < 0:
            raise _incompatible_metadata_error(f"{field_name} must be a non-negative integer.")
    progress_current = int(payload["progress_current"])
    progress_total = int(payload["progress_total"])
    if progress_current > progress_total:
        raise _incompatible_metadata_error("progress_current cannot exceed progress_total.")
    warnings = payload["warnings"]
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        raise _incompatible_metadata_error("warnings must be an array of strings.")
    page_count = payload["page_count"]
    if page_count is not None and (type(page_count) is not int or int(page_count) < 0):
        raise _incompatible_metadata_error("page_count must be null or a non-negative integer.")
    statistics = (
        payload["character_count"],
        payload["word_count"],
        payload["line_count"],
    )
    if payload["status"] == "completed":
        if progress_current != progress_total:
            raise _incompatible_metadata_error("Completed extraction progress must equal its total.")
        if any(type(value) is not int or int(value) < 0 for value in statistics):
            raise _incompatible_metadata_error("Completed extraction statistics must be non-negative integers.")
    elif any(value is not None for value in statistics):
        raise _incompatible_metadata_error("Incomplete extraction statistics must be null.")


def _validate_artifact_pair(project_root: Path, metadata: ExtractionMetadataPayload) -> None:
    """Require a non-empty canonical text artifact for completed metadata."""
    if metadata["status"] != "completed":
        return
    output_path = project_root / _EXTRACTION_OUTPUT_NAME
    if not output_path.is_file():
        raise _incompatible_metadata_error("Completed metadata requires non-empty extracted_text.txt.")
    try:
        extracted_text = output_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise _incompatible_metadata_error("Completed metadata requires valid UTF-8 extracted text.") from exc
    if not extracted_text.strip():
        raise _incompatible_metadata_error("Completed metadata requires non-empty extracted_text.txt.")


def _persist_interrupted_metadata(metadata_path: Path, status: str) -> None:
    """Persist a failed or cancelled status without discarding resumable progress."""
    if metadata_path.is_file():
        metadata = _load_metadata_path(metadata_path)
    else:
        metadata = _build_metadata(
            status=status,
            progress_current=0,
            progress_total=0,
            warnings=[],
            character_count=None,
            word_count=None,
            line_count=None,
            page_count=None,
        )
    metadata["status"] = status
    metadata["character_count"] = None
    metadata["word_count"] = None
    metadata["line_count"] = None
    _validate_metadata(metadata)
    write_json_atomic(metadata_path, metadata)


def _legacy_sidecars_exist(project_root: Path) -> bool:
    """Return whether reset-only legacy extraction sidecars are present."""
    return any((project_root / file_name).exists() for file_name in _LEGACY_EXTRACTION_FILE_NAMES)


def _optional_non_negative_int(value: object) -> int | None:
    """Normalize one optional non-negative integer."""
    if value is None:
        return None
    resolved = int(value)
    if resolved < 0:
        raise ValueError("Expected a non-negative integer.")
    return resolved


def _incompatible_metadata_error(reason: str) -> ExtractionMetadataError:
    """Build the operator-facing strict extraction contract error."""
    return ExtractionMetadataError(
        f"Extraction data is incompatible: {reason} Use Reset Extraction before continuing."
    )


def _emit_status(progress_callback, message: str) -> None:
    """
    @brief      Emit one immediate non-advancing extraction status update.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  message Operator-facing status message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if callable(progress_callback):
        progress_callback(0, 1, 0, message)


def _preparation_message_for_file_type(file_type: str) -> str:
    """
    @brief      Build one operator-facing preparation message for the selected extraction format.
    @param[in]  file_type Normalized source-type token.
    @return     Preparation status message.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return {
        "pdf": "Preparing PDF page extraction...",
        "rtf": "Preparing RTF text extraction...",
        "epub": "Preparing EPUB content extraction...",
        "docx": "Preparing document extraction...",
        "odt": "Preparing document extraction...",
        "txt": "Preparing text extraction...",
        "md": "Preparing text extraction...",
    }.get(file_type, "Preparing text extraction...")


def _normalize_text(text: str) -> str:
    """
    @brief      Normalize line endings and excessive blank runs in extracted text.
    @param[in]  text Raw extracted text fragment.
    @return     Normalized text fragment.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        if line.strip(" \t") == "\f":
            collapsed.append("\f")
            previous_blank = False
            continue
        if line.strip():
            collapsed.append(line)
            previous_blank = False
            continue
        if not previous_blank:
            collapsed.append("")
        previous_blank = True
    return "\n".join(collapsed).strip()


# END OF FILE
