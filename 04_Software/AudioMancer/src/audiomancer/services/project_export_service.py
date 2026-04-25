#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file project_export_service.py
@brief User-facing project artifact export projections for AudioMancer.
@details Builds readiness state and TXT/Markdown export documents from runtime
         project artifacts without modifying the active project workspace.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.3.0
"""

# IMPORTS

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    character_discovery_service,
    deterministic_chunking_service,
    deterministic_cleanup_service,
    speech_blocks_service,
    token_usage_service,
)

# CONSTANTS

# @brief Export kind for the cleaned-text artifact.
EXPORT_KIND_CLEANED_TEXT = "cleaned_text"
# @brief Export kind for the text-chunk artifact.
EXPORT_KIND_TEXT_CHUNKS = "text_chunks"
# @brief Export kind for translated text.
EXPORT_KIND_AI_TRANSLATION = "ai_translation"
# @brief Export kind for discovered character dossiers.
EXPORT_KIND_CHARACTERS = "characters"
# @brief Export kind for generated Speech Blocks.
EXPORT_KIND_SPEECH_BLOCKS = "speech_blocks"
# @brief Stable ordered Home export kind list.
EXPORT_KIND_OPTIONS = (
    EXPORT_KIND_CLEANED_TEXT,
    EXPORT_KIND_TEXT_CHUNKS,
    EXPORT_KIND_AI_TRANSLATION,
    EXPORT_KIND_CHARACTERS,
    EXPORT_KIND_SPEECH_BLOCKS,
)

# @brief Plain-text export format token.
EXPORT_FORMAT_TXT = "txt"
# @brief Markdown export format token.
EXPORT_FORMAT_MARKDOWN = "markdown"
# @brief Stable export format list.
EXPORT_FORMAT_OPTIONS = (EXPORT_FORMAT_TXT, EXPORT_FORMAT_MARKDOWN)

# @brief Readiness token used when an export can be created.
EXPORT_STATUS_AVAILABLE = "available"
# @brief Readiness token used when the workflow is not completed yet.
EXPORT_STATUS_NOT_READY = "not_ready"
# @brief Readiness token used when the workflow is complete but the artifact is absent.
EXPORT_STATUS_MISSING_ARTIFACT = "missing_artifact"

_EXPORT_KIND_LABELS = {
    EXPORT_KIND_CLEANED_TEXT: "Cleaned Text",
    EXPORT_KIND_TEXT_CHUNKS: "Text Chunks",
    EXPORT_KIND_AI_TRANSLATION: "AI Translation",
    EXPORT_KIND_CHARACTERS: "Characters",
    EXPORT_KIND_SPEECH_BLOCKS: "Speech Blocks",
}

_EXPORT_OPERATION_BY_KIND = {
    EXPORT_KIND_CLEANED_TEXT: "cleanup",
    EXPORT_KIND_TEXT_CHUNKS: "chunking",
    EXPORT_KIND_AI_TRANSLATION: "translation",
    EXPORT_KIND_CHARACTERS: "character_discovery",
    EXPORT_KIND_SPEECH_BLOCKS: "speech_blocks",
}

_EXPORT_ARTIFACT_BY_KIND = {
    EXPORT_KIND_CLEANED_TEXT: config.CLEANED_TEXT_FILE_NAME,
    EXPORT_KIND_TEXT_CHUNKS: config.CHUNK_ARTIFACT_FILE_NAME,
    EXPORT_KIND_AI_TRANSLATION: config.TRANSLATED_CHUNKS_FILE_NAME,
    EXPORT_KIND_CHARACTERS: config.CHARACTER_PROFILE_FILE_NAME,
    EXPORT_KIND_SPEECH_BLOCKS: config.SPEECH_BLOCKS_OUTPUT_FILE_NAME,
}

# DATA MODELS / TYPEDEFINITIONS


@dataclass(frozen=True)
class ExportDocument:
    """
    @brief      Normalized export document model shared by text renderers.
    @return     Immutable export document payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """

    title: str
    header_fields: list[tuple[str, str]]
    parameter_fields: list[tuple[str, str]]
    sections: list[tuple[str, str]]


# PUBLIC API


def build_export_states(
    project_root: str | Path | None,
    manifest: dict[str, object] | None,
) -> list[dict[str, object]]:
    """
    @brief      Build Home-page export readiness rows for one project.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @return     Ordered export readiness state dictionaries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return [_build_export_state(project_root, manifest, export_kind) for export_kind in EXPORT_KIND_OPTIONS]


def default_export_file_name(manifest: dict[str, object] | None, export_kind: str, export_format: str) -> str:
    """
    @brief      Build the default user-facing export file name.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  export_kind Stable export kind token.
    @param[in]  export_format Stable export format token.
    @return     Filesystem-safe default file name.
    @exception  ValueError Raised when the export kind or format is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _validate_export_kind(export_kind)
    extension = export_extension(export_format)
    project_name = str((manifest or {}).get("display_name") or (manifest or {}).get("project_name") or "AudioMancer")
    kind_name = _EXPORT_KIND_LABELS[export_kind].lower().replace(" ", "_")
    return f"{_safe_file_stem(project_name)}_{kind_name}{extension}"


def export_extension(export_format: str) -> str:
    """
    @brief      Resolve one export format to a default file suffix.
    @param[in]  export_format Stable export format token.
    @return     File extension including the leading dot.
    @exception  ValueError Raised when the format is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if export_format == EXPORT_FORMAT_TXT:
        return ".txt"
    if export_format == EXPORT_FORMAT_MARKDOWN:
        return ".md"
    raise ValueError(f"Unsupported export format: {export_format}")


def is_path_inside_project(project_root: str | Path, export_path: str | Path) -> bool:
    """
    @brief      Determine whether a selected export path is inside the project root.
    @param[in]  project_root Active project root folder.
    @param[in]  export_path Candidate save path.
    @return     True when the candidate is equal to or below the project root.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    resolved_root = Path(project_root).resolve()
    resolved_export_path = Path(export_path).resolve()
    try:
        resolved_export_path.relative_to(resolved_root)
    except ValueError:
        return False
    return True


def render_export(
    project_root: str | Path,
    manifest: dict[str, object],
    export_kind: str,
    export_format: str,
) -> str:
    """
    @brief      Render one user-facing export document from project artifacts.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  export_kind Stable export kind token.
    @param[in]  export_format Stable export format token.
    @return     Rendered UTF-8 text content.
    @exception  ValueError Raised when the export is unavailable or unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _validate_export_kind(export_kind)
    _validate_export_format(export_format)
    state = _build_export_state(project_root, manifest, export_kind)
    if not bool(state.get("can_export", False)):
        raise ValueError("The requested export is not available yet.")
    document = _build_export_document(Path(project_root), manifest, export_kind)
    if export_format == EXPORT_FORMAT_MARKDOWN:
        return _render_markdown_document(document)
    return _render_txt_document(document)


# LOCAL HELPERS


def _build_export_state(
    project_root: str | Path | None,
    manifest: dict[str, object] | None,
    export_kind: str,
) -> dict[str, object]:
    """
    @brief      Build one Home-page export readiness row.
    @param[in]  project_root Active project root or `None`.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  export_kind Stable export kind token.
    @return     Export readiness state dictionary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    operation_kind = _EXPORT_OPERATION_BY_KIND[export_kind]
    status = EXPORT_STATUS_NOT_READY
    if project_root is not None and manifest is not None and _operation_is_completed(manifest, operation_kind):
        status = (
            EXPORT_STATUS_AVAILABLE
            if _artifact_ready(Path(project_root), export_kind)
            else EXPORT_STATUS_MISSING_ARTIFACT
        )
    return {
        "export_kind": export_kind,
        "label_key": f"home.export.{export_kind}",
        "status": status,
        "can_export": status == EXPORT_STATUS_AVAILABLE,
        "default_file_name": default_export_file_name(manifest, export_kind, EXPORT_FORMAT_TXT),
    }


def _build_export_document(project_root: Path, manifest: dict[str, object], export_kind: str) -> ExportDocument:
    """
    @brief      Build one normalized export document before format rendering.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  export_kind Stable export kind token.
    @return     Normalized export document.
    @exception  ValueError Raised when the export kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    builders: dict[str, Callable[[Path, dict[str, object]], ExportDocument]] = {
        EXPORT_KIND_CLEANED_TEXT: _build_cleaned_text_document,
        EXPORT_KIND_TEXT_CHUNKS: _build_text_chunks_document,
        EXPORT_KIND_AI_TRANSLATION: _build_ai_translation_document,
        EXPORT_KIND_CHARACTERS: _build_characters_document,
        EXPORT_KIND_SPEECH_BLOCKS: _build_speech_blocks_document,
    }
    return builders[export_kind](project_root, manifest)


def _build_cleaned_text_document(project_root: Path, manifest: dict[str, object]) -> ExportDocument:
    """
    @brief      Build the cleaned-text export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @return     Normalized export document.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    report = deterministic_cleanup_service.load_cleanup_report(project_root) or {}
    state = deterministic_cleanup_service.load_operation_state(project_root) or {}
    metadata = _metadata_from_state(state)
    cleaned_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8").strip()
    parameters = _compact_fields(
        [
            ("Cleanup Mode", _first_value(report.get("cleanup_mode"), state.get("mode"), "deterministic")),
            *_ai_parameter_fields(
                project_root,
                report,
                state,
                _first_value(report.get("ai_profile_id"), metadata.get("ai_profile_id")),
            ),
            ("Paragraph Count", _first_value(report.get("paragraph_count"), metadata.get("paragraph_count"))),
            ("Removed Line Count", _first_value(report.get("removed_line_count"), _removed_line_count(metadata))),
            (
                "Detected Chapters",
                _first_value(report.get("detected_chapter_count"), metadata.get("detected_chapter_count")),
            ),
            ("Detected Language", _first_value(report.get("detected_language"), metadata.get("detected_language"))),
            ("Warnings Count", _first_value(len(report.get("warnings", [])), state.get("warning_count"))),
        ]
    )
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=_header_fields(manifest, _EXPORT_KIND_LABELS[EXPORT_KIND_CLEANED_TEXT]),
        parameter_fields=parameters,
        sections=[("Cleaned Text", cleaned_text)],
    )


def _build_text_chunks_document(project_root: Path, manifest: dict[str, object]) -> ExportDocument:
    """
    @brief      Build the text-chunks export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @return     Normalized export document.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    report = deterministic_chunking_service.load_chunking_report(project_root) or {}
    state = deterministic_chunking_service.load_operation_state(project_root) or {}
    metadata = _metadata_from_state(state)
    chunks = _sorted_by_sequence(deterministic_chunking_service.load_chunks(project_root))
    chunk_texts = [str(chunk.get("text", "")).strip() for chunk in chunks if str(chunk.get("text", "")).strip()]
    combined_text = "\n\n----\n\n".join(chunk_texts)
    parameters = _compact_fields(
        [
            (
                "Chunking Mode",
                _first_value(report.get("chunking_mode"), state.get("mode"), _chunk_mode_from_chunks(chunks)),
            ),
            *_ai_parameter_fields(
                project_root,
                report,
                state,
                _first_value(report.get("ai_profile_id"), metadata.get("ai_profile_id")),
            ),
            ("Chunk Count", _first_value(report.get("chunk_count"), len(chunks))),
            ("Word Count", _word_count(chunk_texts)),
            ("Character Count", sum(len(text) for text in chunk_texts)),
            (
                "Detected Chapters",
                _first_value(report.get("detected_chapter_count"), metadata.get("detected_chapter_count")),
            ),
            (
                "Chunking Method",
                _first_value(
                    report.get("semantic_strategy"),
                    metadata.get("semantic_strategy"),
                    _semantic_strategy_from_chunks(chunks),
                ),
            ),
        ]
    )
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=_header_fields(manifest, _EXPORT_KIND_LABELS[EXPORT_KIND_TEXT_CHUNKS]),
        parameter_fields=parameters,
        sections=[("Text Chunks", combined_text)],
    )


def _build_ai_translation_document(project_root: Path, manifest: dict[str, object]) -> ExportDocument:
    """
    @brief      Build the AI-translation export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @return     Normalized export document.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    report = ai_translation_service.load_translation_report(project_root) or {}
    state = ai_translation_service.load_operation_state(project_root) or {}
    metadata = _metadata_from_state(state)
    translated_chunks = _sorted_by_sequence(ai_translation_service.load_translated_chunks(project_root))
    translated_texts = [
        str(chunk.get("translated_text", "")).strip()
        for chunk in translated_chunks
        if str(chunk.get("translated_text", "")).strip()
    ]
    parameters = _compact_fields(
        [
            ("Target Language", _first_value(report.get("target_language"), metadata.get("target_language"))),
            *_ai_parameter_fields(
                project_root,
                report,
                state,
                _first_value(report.get("translation_profile_id_last_used"), metadata.get("translation_profile_id")),
            ),
            (
                "Total Chunks",
                _first_value(
                    report.get("total_chunk_count"), metadata.get("total_chunk_count"), len(translated_chunks)
                ),
            ),
            (
                "Translated Count",
                _first_value(
                    report.get("translated_chunk_count"), metadata.get("translated_chunk_count"), len(translated_texts)
                ),
            ),
            (
                "Approved Count",
                _first_value(
                    report.get("approved_chunk_count"),
                    metadata.get("approved_chunk_count"),
                    _approved_count(translated_chunks),
                ),
            ),
            *_token_usage_fields(report, metadata),
        ]
    )
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=_header_fields(manifest, _EXPORT_KIND_LABELS[EXPORT_KIND_AI_TRANSLATION]),
        parameter_fields=parameters,
        sections=[("Translated Text", "\n\n".join(translated_texts))],
    )


def _build_characters_document(project_root: Path, manifest: dict[str, object]) -> ExportDocument:
    """
    @brief      Build the character dossier export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @return     Normalized export document.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    report = character_discovery_service.load_character_discovery_report(project_root) or {}
    state = character_discovery_service.load_operation_state(project_root) or {}
    metadata = _metadata_from_state(state)
    characters = character_discovery_service.load_character_profiles(project_root)
    parameters = _compact_fields(
        [
            *_ai_parameter_fields(
                project_root,
                report,
                state,
                _first_value(report.get("character_profile_id_last_used"), metadata.get("ai_profile_id")),
            ),
            (
                "Analyzed Windows",
                _first_value(report.get("analyzed_window_count"), metadata.get("analyzed_window_count")),
            ),
            ("Analyzed Chunks", _first_value(report.get("input_chunk_count"), metadata.get("input_chunk_count"))),
            ("Character Count", _first_value(report.get("character_count"), len(characters))),
            *_token_usage_fields(report, metadata),
        ]
    )
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=_header_fields(manifest, _EXPORT_KIND_LABELS[EXPORT_KIND_CHARACTERS]),
        parameter_fields=parameters,
        sections=[("Character Dossiers", _render_character_dossiers(characters))],
    )


def _build_speech_blocks_document(project_root: Path, manifest: dict[str, object]) -> ExportDocument:
    """
    @brief      Build the Speech Blocks export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @return     Normalized export document.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    report = speech_blocks_service.load_speech_blocks_report(project_root) or {}
    state = speech_blocks_service.load_operation_state(project_root) or {}
    metadata = _metadata_from_state(state)
    speech_blocks = _sorted_by_sequence(speech_blocks_service.load_speech_blocks(project_root))
    parameters = _compact_fields(
        [
            ("Source Language", _first_value(report.get("source_language"), metadata.get("source_language"))),
            ("Source Kind", _first_value(report.get("source_kind"), metadata.get("source_kind"))),
            *_ai_parameter_fields(
                project_root,
                report,
                state,
                _first_value(report.get("speech_blocks_profile_id_last_used"), metadata.get("ai_profile_id")),
            ),
            ("Source Chunk Count", _first_value(report.get("source_chunk_count"), metadata.get("source_chunk_count"))),
            ("Speech Block Count", _first_value(report.get("speech_block_count"), len(speech_blocks))),
            ("Warnings Count", _first_value(report.get("warning_count"), state.get("warning_count"))),
            *_token_usage_fields(report, metadata),
        ]
    )
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=_header_fields(manifest, _EXPORT_KIND_LABELS[EXPORT_KIND_SPEECH_BLOCKS]),
        parameter_fields=parameters,
        sections=[("Speech Blocks", _render_speech_blocks(speech_blocks))],
    )


def _render_txt_document(document: ExportDocument) -> str:
    """
    @brief      Render a normalized export document as plain text.
    @param[in]  document Normalized export document.
    @return     Plain-text document content.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    lines = [document.title, "=" * len(document.title), ""]
    lines.extend(_render_txt_fields(document.header_fields))
    lines.extend(["", "Operation Parameters", "--------------------"])
    lines.extend(_render_txt_fields(document.parameter_fields))
    for section_title, section_body in document.sections:
        lines.extend(["", section_title, "-" * len(section_title), section_body.strip()])
    return "\n".join(lines).rstrip() + "\n"


def _render_markdown_document(document: ExportDocument) -> str:
    """
    @brief      Render a normalized export document as Markdown.
    @param[in]  document Normalized export document.
    @return     Markdown document content.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    lines = [f"# {document.title}", "", "## Header", "", "| Field | Value |", "| --- | --- |"]
    lines.extend(
        f"| {_escape_markdown(label)} | {_escape_markdown(value)} |" for label, value in document.header_fields
    )
    lines.extend(["", "## Operation Parameters", "", "| Field | Value |", "| --- | --- |"])
    lines.extend(
        f"| {_escape_markdown(label)} | {_escape_markdown(value)} |" for label, value in document.parameter_fields
    )
    for section_title, section_body in document.sections:
        lines.extend(["", f"## {section_title}", "", _render_markdown_section_body(section_title, section_body)])
    return "\n".join(lines).rstrip() + "\n"


def _render_markdown_section_body(section_title: str, section_body: str) -> str:
    """
    @brief      Render one Markdown section body with export-specific shaping.
    @param[in]  section_title Section heading.
    @param[in]  section_body Plain normalized section body.
    @return     Markdown-ready section body.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if section_title == "Character Dossiers":
        return _render_character_dossiers_markdown(section_body)
    return section_body.strip()


def _render_character_dossiers_markdown(section_body: str) -> str:
    """
    @brief      Render character dossiers as Markdown subsections and attribute tables.
    @param[in]  section_body Plain character dossier section body.
    @return     Markdown-ready character dossier section body.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    rendered_dossiers: list[str] = []
    for dossier_text in section_body.split("\n\n----\n\n"):
        fields = _parse_character_dossier_fields(dossier_text)
        if not fields:
            continue
        name = next((value for label, value in fields if label == "Name"), "Character")
        lines = [f"### {_escape_markdown(name)}", "", "| Attribute | Value |", "| --- | --- |"]
        for label, value in fields:
            if label == "Name":
                continue
            lines.append(f"| **{_escape_markdown(label)}** | {_escape_markdown(value)} |")
        rendered_dossiers.append("\n".join(lines))
    return "\n\n".join(rendered_dossiers).strip()


def _parse_character_dossier_fields(dossier_text: str) -> list[tuple[str, str]]:
    """
    @brief      Parse plain character dossier label lines into Markdown table fields.
    @param[in]  dossier_text Plain dossier text.
    @return     Ordered label/value pairs.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    fields: list[tuple[str, str]] = []
    for raw_line in dossier_text.splitlines():
        if ":" not in raw_line:
            continue
        label, value = raw_line.split(":", maxsplit=1)
        normalized_label = label.strip()
        normalized_value = value.strip()
        if normalized_label and normalized_value:
            fields.append((normalized_label, normalized_value))
    return fields


def _render_txt_fields(fields: Iterable[tuple[str, str]]) -> list[str]:
    """
    @brief      Render plain `Label: value` lines.
    @param[in]  fields Ordered label/value pairs.
    @return     Plain-text field lines.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return [f"{label}: {value}" for label, value in fields]


def _header_fields(manifest: dict[str, object], export_type_label: str) -> list[tuple[str, str]]:
    """
    @brief      Build common export header fields.
    @param[in]  manifest Active project manifest.
    @param[in]  export_type_label Operator-facing export type label.
    @return     Ordered header fields.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    source_name = _source_original_name(manifest)
    return [
        ("Project", str(manifest.get("display_name") or manifest.get("project_name") or "-")),
        ("Original Source Filename", source_name),
        ("Original Extension", Path(source_name).suffix or "-"),
        ("Export Type", export_type_label),
        ("Export Timestamp", datetime.now(UTC).replace(microsecond=0).isoformat()),
    ]


def _artifact_ready(project_root: Path, export_kind: str) -> bool:
    """
    @brief      Check whether one completed export artifact exists and has usable content.
    @param[in]  project_root Active project root folder.
    @param[in]  export_kind Stable export kind token.
    @return     True when the artifact can be exported.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    artifact_path = project_root / _EXPORT_ARTIFACT_BY_KIND[export_kind]
    if not artifact_path.is_file():
        return False
    if export_kind == EXPORT_KIND_CLEANED_TEXT:
        return bool(artifact_path.read_text(encoding="utf-8").strip())
    if export_kind == EXPORT_KIND_TEXT_CHUNKS:
        return bool(deterministic_chunking_service.load_chunks(project_root))
    if export_kind == EXPORT_KIND_AI_TRANSLATION:
        return any(
            str(item.get("translated_text", "")).strip()
            for item in ai_translation_service.load_translated_chunks(project_root)
        )
    if export_kind == EXPORT_KIND_CHARACTERS:
        return bool(character_discovery_service.load_character_profiles(project_root))
    if export_kind == EXPORT_KIND_SPEECH_BLOCKS:
        return bool(speech_blocks_service.load_speech_blocks(project_root))
    return False


def _operation_is_completed(manifest: dict[str, object], operation_kind: str) -> bool:
    """
    @brief      Check whether one manifest operation is completed.
    @param[in]  manifest Active project manifest.
    @param[in]  operation_kind Stable operation kind token.
    @return     True when the operation status is completed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        return False
    operation = operations.get(operation_kind)
    return isinstance(operation, dict) and str(operation.get("status", "")).strip() == "completed"


def _render_character_dossiers(characters: list[dict[str, object]]) -> str:
    """
    @brief      Render character profiles into readable dossiers.
    @param[in]  characters Normalized character profile payloads.
    @return     Character dossier text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    dossiers: list[str] = []
    fields = [
        ("Name", "canonical_name"),
        ("Gender Hint", "gender_hint"),
        ("Age Band", "age_band"),
        ("Role", "role_summary"),
        ("Description", "description"),
        ("Temperament", "temperament"),
        ("Speaking Style", "speaking_style"),
        ("Voice Notes", "voice_notes"),
        ("Voice Persona", "voice_persona_summary"),
        ("Voice Timbre And Range", "voice_timbre_and_range"),
        ("Voice Pacing And Rhythm", "voice_pacing_and_rhythm"),
        ("Voice Emotional Baseline", "voice_emotional_baseline"),
        ("Voice Articulation And Pronunciation", "voice_articulation_and_pronunciation"),
        ("Voice Delivery Constraints", "voice_delivery_constraints"),
        ("Voice Definition Prompt", "voice_definition_prompt"),
    ]
    for character in characters:
        lines = []
        for label, key in fields:
            value = _format_value(character.get(key))
            if value != "-":
                lines.append(f"{label}: {value}")
        dossiers.append("\n".join(lines))
    return "\n\n----\n\n".join(dossier for dossier in dossiers if dossier.strip())


def _render_speech_blocks(speech_blocks: list[dict[str, object]]) -> str:
    """
    @brief      Render Speech Blocks as speaker/text pairs without internal ids.
    @param[in]  speech_blocks Normalized Speech Blocks payloads.
    @return     Speaker/text export body.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    rendered_blocks: list[str] = []
    for block in speech_blocks:
        speaker_name = str(block.get("speaker_display_name") or block.get("speaker_name") or "Unknown").strip()
        block_text = str(block.get("text", "")).strip()
        if block_text:
            rendered_blocks.append(f"Speaker: {speaker_name}\n{block_text}")
    return "\n\n".join(rendered_blocks)


def _token_usage_fields(*payloads: object) -> list[tuple[str, object]]:
    """
    @brief      Build optional token-usage parameter fields.
    @param[in]  payloads Candidate payloads containing token-usage data.
    @return     Token-usage fields when available.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    token_usage = token_usage_service.restore_token_usage(
        *[payload.get("token_usage") for payload in payloads if isinstance(payload, dict)]
    )
    if not bool(token_usage.get("usage_available", False)):
        return []
    return [
        ("Input Tokens", token_usage.get("input_tokens")),
        ("Output Tokens", token_usage.get("output_tokens")),
        ("Total Tokens", token_usage.get("total_tokens")),
    ]


def _ai_parameter_fields(
    project_root: Path,
    report: dict[str, object],
    state: dict[str, object],
    profile_id: object,
) -> list[tuple[str, object]]:
    """
    @brief      Build export fields for the AI request parameters used by one operation.
    @param[in]  project_root Active project root folder.
    @param[in]  report Operation report payload.
    @param[in]  state Operation state payload.
    @param[in]  profile_id Profile identifier resolved from report or state.
    @return     AI parameter fields when an AI profile or transaction log exists.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    request_record = _first_ai_request_record(project_root, state)
    request_payload = request_record.get("request_payload")
    request_payload = dict(request_payload) if isinstance(request_payload, dict) else {}
    resolved_profile_id = _first_value(profile_id, request_record.get("profile_id"))
    if resolved_profile_id in (None, "") and not request_record and str(state.get("mode", "")).strip() != "ai_assisted":
        return []
    return [
        ("AI Profile", resolved_profile_id),
        ("AI Backend", _first_value(request_record.get("backend_kind"), report.get("backend_kind"))),
        ("AI Base URL", _first_value(request_record.get("base_url"), report.get("base_url"))),
        (
            "AI Model",
            _first_value(
                request_payload.get("model"),
                request_record.get("model_name"),
                report.get("model_name"),
            ),
        ),
        ("AI Temperature", request_payload.get("temperature")),
        ("AI Max Tokens", request_payload.get("max_tokens")),
        ("AI Max Completion Tokens", request_payload.get("max_completion_tokens")),
    ]


def _first_ai_request_record(project_root: Path, state: dict[str, object]) -> dict[str, object]:
    """
    @brief      Read the first request record from one operation-local AI transaction log.
    @param[in]  project_root Active project root folder.
    @param[in]  state Operation state payload.
    @return     First request record or an empty dictionary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    log_path = _ai_log_path(project_root, state)
    if log_path is None or not log_path.is_file():
        return {}
    with log_path.open("r", encoding="utf-8") as log_handle:
        for raw_line in log_handle:
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and str(payload.get("exchange_event", "")).strip() == "request":
                return payload
    return {}


def _ai_log_path(project_root: Path, state: dict[str, object]) -> Path | None:
    """
    @brief      Resolve one operation-local AI transaction log path from persisted state.
    @param[in]  project_root Active project root folder.
    @param[in]  state Operation state payload.
    @return     Log file path or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    metadata = _metadata_from_state(state)
    candidate = _first_value(metadata.get("ai_log_relative_path"), metadata.get("log_relative_path"))
    if candidate not in (None, ""):
        return project_root / str(candidate)
    artifact_paths = state.get("artifact_paths")
    if isinstance(artifact_paths, list):
        for artifact_path in artifact_paths:
            artifact_name = str(artifact_path).strip()
            if Path(artifact_name).name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX) and artifact_name.endswith(
                config.AI_TRANSACTION_LOG_FILE_EXTENSION
            ):
                return project_root / artifact_name
    return None


def _compact_fields(fields: Iterable[tuple[str, object]]) -> list[tuple[str, str]]:
    """
    @brief      Normalize export fields into display-safe text values.
    @param[in]  fields Ordered raw label/value pairs.
    @return     Ordered display label/value pairs.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return [(label, _format_value(value)) for label, value in fields]


def _format_value(value: object) -> str:
    """
    @brief      Convert a raw export field value to readable text.
    @param[in]  value Candidate value.
    @return     Readable field value.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if value in (None, ""):
        return "-"
    if isinstance(value, list | tuple):
        return ", ".join(str(item) for item in value if str(item).strip()) or "-"
    return str(value)


def _first_value(*values: object) -> object:
    """
    @brief      Return the first non-empty candidate value.
    @param[in]  values Candidate values.
    @return     First non-empty value or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _metadata_from_state(state: dict[str, object]) -> dict[str, object]:
    """
    @brief      Extract the metadata dictionary from an operation-state payload.
    @param[in]  state Operation-state payload.
    @return     Metadata dictionary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    metadata = state.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _removed_line_count(metadata: dict[str, object]) -> int:
    """
    @brief      Sum cleanup removed-line counters from metadata.
    @param[in]  metadata Cleanup metadata payload.
    @return     Total removed-line count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return sum(
        int(metadata.get(key, 0) or 0)
        for key in (
            "removed_header_footer_line_count",
            "removed_page_number_line_count",
            "removed_separator_line_count",
        )
    )


def _sorted_by_sequence(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Sort artifact records by sequence index when present.
    @param[in]  items Artifact record dictionaries.
    @return     Ordered artifact record dictionaries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return sorted(items, key=lambda item: int(item.get("sequence_index", 0) or item.get("block_index", 0) or 0))


def _word_count(texts: Iterable[str]) -> int:
    """
    @brief      Count whitespace-separated words across text spans.
    @param[in]  texts Text spans.
    @return     Word count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return sum(len(text.split()) for text in texts)


def _approved_count(items: Iterable[dict[str, object]]) -> int:
    """
    @brief      Count approved translation records.
    @param[in]  items Translation records.
    @return     Approved record count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return sum(1 for item in items if bool(item.get("approved", False)))


def _chunk_mode_from_chunks(chunks: list[dict[str, object]]) -> str | None:
    """
    @brief      Resolve a chunking mode fallback from chunk records.
    @param[in]  chunks Chunk payload list.
    @return     Chunking mode or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    for chunk in chunks:
        mode = str(chunk.get("chunking_mode") or "").strip()
        if mode:
            return mode
    return None


def _semantic_strategy_from_chunks(chunks: list[dict[str, object]]) -> str | None:
    """
    @brief      Resolve a semantic strategy fallback from chunk records.
    @param[in]  chunks Chunk payload list.
    @return     Semantic strategy or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    for chunk in chunks:
        strategy = str(chunk.get("semantic_strategy") or "").strip()
        if strategy:
            return strategy
    return None


def _source_original_name(manifest: dict[str, object]) -> str:
    """
    @brief      Read the original source name from a manifest.
    @param[in]  manifest Active project manifest.
    @return     Original source file name or placeholder.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        return "-"
    return str(source_document.get("original_name") or "-")


def _safe_file_stem(value: str) -> str:
    """
    @brief      Normalize one default export file stem.
    @param[in]  value Candidate file stem.
    @return     Filesystem-safe file stem.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", str(value).strip())
    normalized = re.sub(r"\s+", "_", normalized).strip("._ ")
    return normalized or "AudioMancer"


def _escape_markdown(value: str) -> str:
    """
    @brief      Escape Markdown table delimiters in field values.
    @param[in]  value Candidate table value.
    @return     Escaped table value.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return value.replace("|", "\\|").replace("\n", "<br>")


def _validate_export_kind(export_kind: str) -> None:
    """
    @brief      Validate one export kind token.
    @param[in]  export_kind Candidate export kind.
    @return     None.
    @exception  ValueError Raised when the export kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if export_kind not in EXPORT_KIND_OPTIONS:
        raise ValueError(f"Unsupported export kind: {export_kind}")


def _validate_export_format(export_format: str) -> None:
    """
    @brief      Validate one export format token.
    @param[in]  export_format Candidate export format.
    @return     None.
    @exception  ValueError Raised when the export format is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if export_format not in EXPORT_FORMAT_OPTIONS:
        raise ValueError(f"Unsupported export format: {export_format}")


# END OF FILE
