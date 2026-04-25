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
@details Copies one operation-local input snapshot, extracts normalized text
         from the supported source formats, persists extraction artifacts, and
         maintains resumable extraction state in `00_extraction`.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.4.2
"""

# IMPORTS

from datetime import UTC, datetime
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
    progress_percent,
    raise_if_cancelled,
    reset_operation_data,
)

# CONSTANTS

# @brief Component logger used by deterministic text extraction.
_EXTRACTION_LOGGER = get_component_logger("text_extraction")
# @brief Persisted extraction operation-state payload type.
OperationStatePayload = dict[str, object]
# @brief Persisted extraction report payload type.
ExtractionReportPayload = dict[str, object]
# @brief Internal extraction-units payload type used during format-specific parsing.
ExtractionUnitsPayload = dict[str, object]
# @brief Stable extraction-folder name used for local artifact path construction.
_EXTRACTION_FOLDER_NAME = config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
# @brief Stable prefix used for copied extraction input snapshots.
_EXTRACTION_INPUT_PREFIX = "input_"
# @brief Stable file name used for extracted raw text output.
_EXTRACTION_OUTPUT_NAME = config.EXTRACTED_TEXT_FILE_NAME
# @brief Stable file name used for the extraction report artifact.
_EXTRACTION_REPORT_NAME = config.EXTRACTION_REPORT_FILE_NAME
# @brief Stable file name used for persisted extraction runtime state.
_EXTRACTION_STATE_NAME = config.EXTRACTION_STATE_FILE_NAME
# @brief Canonical separator inserted between extracted pages for downstream cleanup.
_PAGE_BREAK_SEPARATOR = "\n\n\f\n\n"


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
) -> ExtractionReportPayload:
    """
    @brief      Extract source text for one active AudioMancer project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  progress_callback Optional zero-copy progress callback.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Extraction report payload describing the persisted artifacts.
    @exception  FileNotFoundError Raised when the imported source file is missing.
    @exception  ValueError Raised when no extractable text is available.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.2
    """
    resolved_project_root = Path(project_root)
    source_document = _source_document_from_manifest(manifest)
    if source_document is None:
        raise ValueError("No imported source is available for text extraction.")

    extraction_dir = resolved_project_root / _EXTRACTION_FOLDER_NAME
    extraction_dir.mkdir(parents=True, exist_ok=True)
    input_snapshot_path = _source_path_from_manifest(resolved_project_root, source_document)
    output_path = extraction_dir / _EXTRACTION_OUTPUT_NAME
    report_path = extraction_dir / _EXTRACTION_REPORT_NAME
    state_path = extraction_dir / _EXTRACTION_STATE_NAME

    file_type = str(source_document["file_type"])
    resume_state = _load_operation_state(state_path)
    warnings = _warnings_from_state(resume_state)
    _emit_status(progress_callback, _preparation_message_for_file_type(file_type))
    if _supports_incremental_resume(file_type) and _can_resume_from_state(
        resume_state,
        input_snapshot_path,
        output_path,
    ):
        progress_payload = _resume_extraction(
            input_snapshot_path,
            output_path,
            state_path,
            file_type,
            warnings,
            progress_callback,
            cancel_requested,
        )
    else:
        progress_payload = _start_fresh_extraction(
            input_snapshot_path,
            output_path,
            state_path,
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

    final_text = normalized_text + "\n"
    output_path.write_text(final_text, encoding="utf-8")

    report_payload: ExtractionReportPayload = {
        "source_relative_path": _relative_to_project(resolved_project_root, input_snapshot_path),
        "source_type": file_type,
        "extracted_text_relative_path": _relative_to_project(resolved_project_root, output_path),
        "extracted_at": _utc_now_iso(),
        "page_count": progress_payload.get("page_count"),
        "warnings": list(progress_payload["warnings"]),
        "character_count": len(normalized_text),
        "word_count": len(normalized_text.split()),
        "line_count": len(normalized_text.splitlines()),
    }
    report_path.write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    completed_state = _build_operation_state(
        status="completed",
        input_paths=[_relative_to_project(resolved_project_root, input_snapshot_path)],
        output_paths=[_relative_to_project(resolved_project_root, output_path)],
        artifact_paths=[_relative_to_project(resolved_project_root, report_path)],
        warning_count=len(report_payload["warnings"]),
        progress_current=int(progress_payload["progress_total"]),
        progress_total=int(progress_payload["progress_total"]),
        started_at=str(progress_payload["started_at"]),
        completed_at=report_payload["extracted_at"],
        metadata={
            "warnings": list(report_payload["warnings"]),
            "word_count": report_payload["word_count"],
            "line_count": report_payload["line_count"],
            "character_count": report_payload["character_count"],
            "page_count": report_payload["page_count"],
            "source_type": file_type,
        },
        resume_checkpoint=None,
    )
    state_path.write_text(
        json.dumps(completed_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report_payload


@trace_function(_EXTRACTION_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional extraction operation-state file.
    @param[in]  project_root Active project root folder.
    @return     Persisted extraction operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    state_path = Path(project_root) / _EXTRACTION_FOLDER_NAME / _EXTRACTION_STATE_NAME
    return _load_operation_state(state_path)


@trace_function(_EXTRACTION_LOGGER)
def load_extraction_report(project_root: str | Path) -> ExtractionReportPayload | None:
    """
    @brief      Load one optional persisted extraction report.
    @param[in]  project_root Active project root folder.
    @return     Extraction report payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    report_path = Path(project_root) / _EXTRACTION_FOLDER_NAME / _EXTRACTION_REPORT_NAME
    if not report_path.is_file():
        return None
    return dict(json.loads(report_path.read_text(encoding="utf-8")))


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
        keep_input_snapshots=True,
    )


# HELPER FUNCTIONS


def _start_fresh_extraction(
    input_snapshot_path: Path,
    output_path: Path,
    state_path: Path,
    file_type: str,
    warnings: list[str],
    progress_callback,
    cancel_requested,
) -> dict[str, object]:
    """
    @brief      Start extraction from the beginning of one copied input snapshot.
    @param[in]  input_snapshot_path Operation-local source snapshot path.
    @param[in]  output_path Canonical extracted output path.
    @param[in]  state_path Operation-state file path.
    @param[in]  file_type Normalized source-type token.
    @param[in,out] warnings Mutable warnings list shared with the extraction pass.
    @return     Summary payload with progress metadata and warnings.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.2
    """
    if output_path.exists():
        output_path.unlink()
    started_at = _utc_now_iso()
    progress_payload = _build_progress_units(input_snapshot_path, file_type)
    progress_units = list(progress_payload["units"])
    warnings[:] = [*warnings, *list(progress_payload["warnings"])]
    total_units = len(progress_units)
    _write_running_state(
        state_path,
        input_snapshot_path,
        output_path,
        started_at,
        0,
        total_units,
        warnings,
        file_type,
        progress_callback,
    )
    _process_units(
        progress_units,
        input_snapshot_path,
        output_path,
        state_path,
        started_at,
        warnings,
        file_type,
        0,
        progress_callback,
        cancel_requested,
    )
    return {
        "started_at": started_at,
        "progress_total": total_units,
        "warnings": list(warnings),
        "page_count": progress_payload["page_count"],
    }


def _resume_extraction(
    input_snapshot_path: Path,
    output_path: Path,
    state_path: Path,
    file_type: str,
    warnings: list[str],
    progress_callback,
    cancel_requested,
) -> dict[str, object]:
    """
    @brief      Continue one previously interrupted incremental extraction.
    @param[in]  input_snapshot_path Operation-local source snapshot path.
    @param[in]  output_path Canonical extracted output path.
    @param[in]  state_path Operation-state file path.
    @param[in]  file_type Normalized source-type token.
    @param[in,out] warnings Mutable warnings list restored from the previous state.
    @return     Summary payload with progress metadata and warnings.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.2
    """
    existing_state = _load_operation_state(state_path) or {}
    resume_checkpoint = dict(existing_state.get("resume_checkpoint") or {})
    next_unit_index = int(resume_checkpoint.get("next_unit_index", 0))
    started_at = str(existing_state.get("started_at") or _utc_now_iso())
    progress_payload = _build_progress_units(input_snapshot_path, file_type)
    progress_units = list(progress_payload["units"])
    warnings[:] = [*warnings, *list(progress_payload["warnings"])]
    total_units = len(progress_units)
    _write_running_state(
        state_path,
        input_snapshot_path,
        output_path,
        started_at,
        next_unit_index,
        total_units,
        warnings,
        file_type,
        progress_callback,
    )
    _process_units(
        progress_units,
        input_snapshot_path,
        output_path,
        state_path,
        started_at,
        warnings,
        file_type,
        next_unit_index,
        progress_callback,
        cancel_requested,
    )
    return {
        "started_at": started_at,
        "progress_total": total_units,
        "warnings": list(warnings),
        "page_count": progress_payload["page_count"],
    }


def _process_units(
    progress_units: list[object],
    input_snapshot_path: Path,
    output_path: Path,
    state_path: Path,
    started_at: str,
    warnings: list[str],
    file_type: str,
    start_index: int,
    progress_callback,
    cancel_requested,
) -> None:
    """
    @brief      Process one ordered list of extracted text units into the output artifact.
    @param[in]  progress_units Ordered extracted units for the source.
    @param[in]  input_snapshot_path Operation-local source snapshot path.
    @param[in]  output_path Canonical extracted output path.
    @param[in]  state_path Operation-state file path.
    @param[in]  started_at Stable operation start timestamp.
    @param[in,out] warnings Mutable warnings list.
    @param[in]  file_type Normalized source-type token.
    @param[in]  start_index First unit index to process.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.1
    """
    if start_index == 0 and output_path.exists():
        output_path.unlink()

    total_units = len(progress_units)
    _emit_progress(progress_callback, start_index, total_units, "Text extraction in progress...")
    if file_type == "pdf":
        with fitz.open(input_snapshot_path) as document:
            for unit_index in range(start_index, total_units):
                raise_if_cancelled(cancel_requested)
                page_index = int(progress_units[unit_index])
                unit_text = _normalize_text(document.load_page(page_index).get_text("text")).strip()
                if not unit_text:
                    warnings.append(f"PDF page {page_index + 1} did not contain extractable text.")
                if unit_text:
                    prefix = ""
                    if output_path.exists() and output_path.stat().st_size > 0:
                        prefix = _PAGE_BREAK_SEPARATOR
                    with output_path.open("a", encoding="utf-8") as handle:
                        handle.write(prefix + unit_text)
                _write_running_state(
                    state_path,
                    input_snapshot_path,
                    output_path,
                    started_at,
                    unit_index + 1,
                    total_units,
                    warnings,
                    file_type,
                    progress_callback,
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
            prefix = ""
            if output_path.exists() and output_path.stat().st_size > 0:
                prefix = "\n\n"
            with output_path.open("a", encoding="utf-8") as handle:
                handle.write(prefix + unit_text)
        _write_running_state(
            state_path,
            input_snapshot_path,
            output_path,
            started_at,
            unit_index + 1,
            total_units,
            warnings,
            file_type,
            progress_callback,
        )
        _emit_progress(
            progress_callback,
            unit_index + 1,
            total_units,
            "Text extraction in progress...",
        )


def _write_running_state(
    state_path: Path,
    input_snapshot_path: Path,
    output_path: Path,
    started_at: str,
    progress_current: int,
    progress_total: int,
    warnings: list[str],
    file_type: str,
    progress_callback,
) -> None:
    """
    @brief      Persist one running extraction state snapshot.
    @param[in]  state_path Operation-state file path.
    @param[in]  input_snapshot_path Operation-local source snapshot path.
    @param[in]  output_path Canonical extracted output path.
    @param[in]  started_at Stable operation start timestamp.
    @param[in]  progress_current Completed unit count.
    @param[in]  progress_total Total unit count.
    @param[in]  warnings Current warning list.
    @param[in]  file_type Normalized source-type token.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    project_root = state_path.parent
    input_paths = []
    if input_snapshot_path.exists():
        input_paths.append(_relative_to_project(project_root, input_snapshot_path))
    output_paths = []
    if output_path.exists():
        output_paths.append(_relative_to_project(project_root, output_path))
    running_state = _build_operation_state(
        status="running",
        input_paths=input_paths,
        output_paths=output_paths,
        artifact_paths=[],
        warning_count=len(warnings),
        progress_current=progress_current,
        progress_total=progress_total,
        started_at=started_at,
        completed_at=None,
        metadata={
            "warnings": list(warnings),
            "source_type": file_type,
        },
        resume_checkpoint={"next_unit_index": progress_current},
    )
    state_path.write_text(
        json.dumps(running_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _ = progress_callback


def _build_operation_state(
    status: str,
    input_paths: list[str],
    output_paths: list[str],
    artifact_paths: list[str],
    warning_count: int,
    progress_current: int,
    progress_total: int,
    started_at: str | None,
    completed_at: str | None,
    metadata: dict[str, object],
    resume_checkpoint: dict[str, object] | None,
) -> OperationStatePayload:
    """
    @brief      Build one extraction operation-state payload.
    @param[in]  status Persisted extraction status token.
    @param[in]  input_paths Relative input artifact paths.
    @param[in]  output_paths Relative output artifact paths.
    @param[in]  artifact_paths Relative report artifact paths.
    @param[in]  warning_count Warning count.
    @param[in]  progress_current Completed progress count.
    @param[in]  progress_total Total progress count.
    @param[in]  started_at Optional operation start timestamp.
    @param[in]  completed_at Optional operation completion timestamp.
    @param[in]  metadata Extra extraction metadata payload.
    @param[in]  resume_checkpoint Optional resume checkpoint payload.
    @return     JSON-ready operation-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return {
        "folder_relative_path": _EXTRACTION_FOLDER_NAME,
        "status": status,
        "input_paths": list(input_paths),
        "output_paths": list(output_paths),
        "artifact_paths": list(artifact_paths),
        "progress_current": progress_current,
        "progress_total": progress_total,
        "mode": "deterministic",
        "started_at": started_at,
        "completed_at": completed_at,
        "updated_at": _utc_now_iso(),
        "warning_count": warning_count,
        "metadata": dict(metadata),
        "resume_checkpoint": None if resume_checkpoint is None else dict(resume_checkpoint),
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


def _can_resume_from_state(
    state_payload: OperationStatePayload | None,
    input_snapshot_path: Path,
    output_path: Path,
) -> bool:
    """
    @brief      Decide whether one saved extraction state can continue safely.
    @param[in]  state_payload Optional saved operation-state payload.
    @param[in]  input_snapshot_path Operation-local source snapshot path.
    @param[in]  output_path Canonical extracted output path.
    @return     True when the extraction may continue from the saved checkpoint.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(state_payload, dict):
        return False
    if str(state_payload.get("status")) not in {"running", "failed"}:
        return False
    if not input_snapshot_path.is_file():
        return False
    checkpoint = state_payload.get("resume_checkpoint")
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("next_unit_index"), int):
        return False
    if output_path.exists():
        return True
    return len(list(state_payload.get("output_paths", []))) == 0


def _load_operation_state(state_path: Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional extraction operation-state payload.
    @param[in]  state_path Absolute extraction state file path.
    @return     Operation-state payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not state_path.is_file():
        return None
    return dict(json.loads(state_path.read_text(encoding="utf-8")))


def _source_path_from_manifest(project_root: Path, source_document: dict[str, object]) -> Path:
    """
    @brief      Resolve the root-level imported source file for extraction.
    @param[in]  project_root Active project root folder.
    @param[in]  source_document Normalized source-document payload.
    @return     Absolute imported source path.
    @exception  FileNotFoundError Raised when the root-level source file is missing.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.0
    """
    source_relative_path = str(source_document["stored_relative_path"])
    source_path = project_root / source_relative_path
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


def _warnings_from_state(state_payload: OperationStatePayload | None) -> list[str]:
    """
    @brief      Restore persisted warning strings from one saved extraction state.
    @param[in]  state_payload Optional saved operation-state payload.
    @return     Ordered warning list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(state_payload, dict):
        return []
    metadata = state_payload.get("metadata")
    if not isinstance(metadata, dict):
        return []
    warnings = metadata.get("warnings", [])
    if not isinstance(warnings, list):
        return []
    return [str(item) for item in warnings]


def _emit_progress(progress_callback, progress_current: int, progress_total: int, message: str) -> None:
    """
    @brief      Emit one optional extraction progress snapshot.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_current Completed unit count.
    @param[in]  progress_total Total unit count.
    @param[in]  message Operator-facing progress status message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if callable(progress_callback):
        progress_callback(
            progress_current,
            progress_total,
            progress_percent(progress_current, progress_total),
            message,
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
    lines = [line.rstrip() for line in normalized.split("\n")]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        if line.strip():
            collapsed.append(line)
            previous_blank = False
            continue
        if not previous_blank:
            collapsed.append("")
        previous_blank = True
    return "\n".join(collapsed).strip()


def _relative_to_project(project_root: Path, artifact_path: Path) -> str:
    """
    @brief      Convert one absolute project-local path to a manifest-relative string.
    @param[in]  project_root Active project root folder.
    @param[in]  artifact_path Absolute project-local artifact path.
    @return     POSIX-style relative path string.
    @exception  ValueError Raised when the artifact is outside the project root.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return artifact_path.relative_to(project_root).as_posix()


def _utc_now_iso() -> str:
    """
    @brief      Build one timezone-aware UTC timestamp string.
    @return     ISO 8601 UTC timestamp.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return datetime.now(UTC).isoformat()


# END OF FILE
