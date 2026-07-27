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
         project artifacts plus ZIP archive exports for generated voice and
         audiobook assets without modifying the active project workspace.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.5.1
"""

# IMPORTS

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import json
from pathlib import Path
import zipfile

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    audio_assembly_service,
    character_discovery_service,
    character_voices_service,
    chunking_document_service,
    narrator_definition_service,
    speech_blocks_service,
    text_cleanup_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.operation_runtime_service import is_path_inside_project as _is_path_inside_project
from audiomancer.services.operation_runtime_service import safe_file_stem as _shared_safe_file_stem
from audiomancer.services.time_service import utc_now_iso

# CONSTANTS

_PROJECT_EXPORT_LOGGER = get_component_logger("project_export")

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
# @brief Export kind for narrator voice sample archives.
EXPORT_KIND_NARRATOR_VOICE = "narrator_voice"
# @brief Export kind for character voice sample archives.
EXPORT_KIND_CHARACTER_VOICES = "character_voices"
# @brief Export kind for final Audio Assembly archives.
EXPORT_KIND_AUDIO_ASSEMBLY = "audio_assembly"
# @brief Stable ordered Home export kind list.
EXPORT_KIND_OPTIONS = (
    EXPORT_KIND_CLEANED_TEXT,
    EXPORT_KIND_TEXT_CHUNKS,
    EXPORT_KIND_AI_TRANSLATION,
    EXPORT_KIND_CHARACTERS,
    EXPORT_KIND_NARRATOR_VOICE,
    EXPORT_KIND_CHARACTER_VOICES,
    EXPORT_KIND_SPEECH_BLOCKS,
    EXPORT_KIND_AUDIO_ASSEMBLY,
)

# @brief Plain-text export format token.
EXPORT_FORMAT_TXT = "txt"
# @brief Markdown export format token.
EXPORT_FORMAT_MARKDOWN = "markdown"
# @brief ZIP archive export format token.
EXPORT_FORMAT_ZIP = "zip"
# @brief Stable export format list.
EXPORT_FORMAT_OPTIONS = (EXPORT_FORMAT_TXT, EXPORT_FORMAT_MARKDOWN, EXPORT_FORMAT_ZIP)

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
    EXPORT_KIND_NARRATOR_VOICE: "Narator Voice",
    EXPORT_KIND_CHARACTER_VOICES: "Character Voices",
    EXPORT_KIND_SPEECH_BLOCKS: "Speech Blocks",
    EXPORT_KIND_AUDIO_ASSEMBLY: "Audio Assembly",
}

_EXPORT_OPERATION_BY_KIND = {
    EXPORT_KIND_CLEANED_TEXT: "cleanup",
    EXPORT_KIND_TEXT_CHUNKS: "chunking",
    EXPORT_KIND_AI_TRANSLATION: "translation",
    EXPORT_KIND_CHARACTERS: "character_discovery",
    EXPORT_KIND_NARRATOR_VOICE: "narrator_definition",
    EXPORT_KIND_CHARACTER_VOICES: "character_voices",
    EXPORT_KIND_SPEECH_BLOCKS: "speech_blocks",
    EXPORT_KIND_AUDIO_ASSEMBLY: "audio_assembly",
}

_EXPORT_ARTIFACT_BY_KIND = {
    EXPORT_KIND_CLEANED_TEXT: config.CLEANED_TEXT_FILE_NAME,
    EXPORT_KIND_TEXT_CHUNKS: config.CHUNK_ARTIFACT_FILE_NAME,
    EXPORT_KIND_AI_TRANSLATION: config.TRANSLATED_CHUNKS_FILE_NAME,
    EXPORT_KIND_CHARACTERS: config.CHARACTERS_DOCUMENT_FILE_NAME,
    EXPORT_KIND_NARRATOR_VOICE: config.NARRATOR_VOICE_FILE_NAME,
    EXPORT_KIND_CHARACTER_VOICES: config.CHARACTER_VOICES_TARGETS_FILE_NAME,
    EXPORT_KIND_SPEECH_BLOCKS: config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
    EXPORT_KIND_AUDIO_ASSEMBLY: config.AUDIO_ASSEMBLY_REPORT_FILE_NAME,
}

_ARCHIVE_EXPORT_KINDS = {
    EXPORT_KIND_NARRATOR_VOICE,
    EXPORT_KIND_CHARACTER_VOICES,
    EXPORT_KIND_AUDIO_ASSEMBLY,
}

# DATA MODELS / TYPEDEFINITIONS


@dataclass(frozen=True)
class ExportDocument:
    """
    @brief      Normalized export document model shared by text renderers.
    @details    `character_dossiers` carries the structured per-character
                label/value records so the Markdown renderer never re-parses
                the plain-text projection.
    @return     Immutable export document payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.3.0
    """

    title: str
    header_fields: list[tuple[str, str]]
    parameter_fields: list[tuple[str, str]]
    sections: list[tuple[str, str]]
    character_dossiers: list[list[tuple[str, str]]] | None = None


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
    @version    0.2.0
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
    @version    0.2.0
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
    @version    0.2.0
    """
    if export_format == EXPORT_FORMAT_TXT:
        return ".txt"
    if export_format == EXPORT_FORMAT_MARKDOWN:
        return ".md"
    if export_format == EXPORT_FORMAT_ZIP:
        return ".zip"
    raise ValueError(f"Unsupported export format: {export_format}")


def export_formats_for_kind(export_kind: str) -> tuple[str, ...]:
    """
    @brief      Return the supported file formats for one Home export kind.
    @param[in]  export_kind Stable export kind token.
    @return     Ordered export format tokens.
    @exception  ValueError Raised when the export kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    _validate_export_kind(export_kind)
    if export_kind in _ARCHIVE_EXPORT_KINDS:
        return (EXPORT_FORMAT_ZIP,)
    return (EXPORT_FORMAT_TXT, EXPORT_FORMAT_MARKDOWN)


def is_path_inside_project(project_root: str | Path, export_path: str | Path) -> bool:
    """
    @brief      Determine whether a selected export path is inside the project root.
    @param[in]  project_root Active project root folder.
    @param[in]  export_path Candidate save path.
    @return     True when the candidate is equal to or below the project root.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.3.0
    """
    return _is_path_inside_project(project_root, export_path)


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
    @version    0.2.0
    """
    _PROJECT_EXPORT_LOGGER.info("Rendering project export kind=%s format=%s", export_kind, export_format)
    _validate_export_kind(export_kind)
    _validate_export_format(export_format)
    if export_format == EXPORT_FORMAT_ZIP:
        raise ValueError("ZIP exports must be written with create_archive_export.")
    if export_kind in _ARCHIVE_EXPORT_KINDS:
        raise ValueError("Archive export kinds support ZIP only.")
    state = _build_export_state(project_root, manifest, export_kind)
    if not bool(state.get("can_export", False)):
        _PROJECT_EXPORT_LOGGER.warning("Project export unavailable kind=%s status=%s", export_kind, state.get("status"))
        raise ValueError("The requested export is not available yet.")
    document = _build_export_document(Path(project_root), manifest, export_kind)
    if export_format == EXPORT_FORMAT_MARKDOWN:
        return _render_markdown_document(document)
    return _render_txt_document(document)


def create_archive_export(
    project_root: str | Path,
    manifest: dict[str, object],
    export_kind: str,
    export_path: str | Path,
) -> Path:
    """
    @brief      Create one ZIP archive export from generated audio assets and companion text metadata.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  export_kind Stable archive export kind token.
    @param[in]  export_path Destination ZIP path outside the active project.
    @return     Final ZIP path.
    @exception  ValueError Raised when the export is unavailable or unsupported.
    @exception  OSError Raised when the archive cannot be written.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    _PROJECT_EXPORT_LOGGER.info("Creating project archive export kind=%s path=%s", export_kind, export_path)
    _validate_export_kind(export_kind)
    if export_kind not in _ARCHIVE_EXPORT_KINDS:
        raise ValueError(f"Export kind is not an archive export: {export_kind}")
    state = _build_export_state(project_root, manifest, export_kind)
    if not bool(state.get("can_export", False)):
        _PROJECT_EXPORT_LOGGER.warning("Archive export unavailable kind=%s status=%s", export_kind, state.get("status"))
        raise ValueError("The requested export is not available yet.")
    archive_path = Path(export_path)
    if archive_path.suffix.lower() != ".zip":
        archive_path = archive_path.with_suffix(".zip")
    archive_entries = _build_archive_entries(Path(project_root), manifest, export_kind)
    if not archive_entries:
        raise ValueError("The requested archive has no generated audio assets to export.")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_name, source_path, text_content in archive_entries:
            if source_path is not None:
                archive.write(source_path, archive_name)
            else:
                archive.writestr(archive_name, text_content or "")
    return archive_path


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
    @version    0.2.0
    """
    operation_kind = _EXPORT_OPERATION_BY_KIND[export_kind]
    status = EXPORT_STATUS_NOT_READY
    if project_root is not None and manifest is not None and export_kind in _ARCHIVE_EXPORT_KINDS:
        if _artifact_ready(Path(project_root), export_kind):
            status = EXPORT_STATUS_AVAILABLE
        elif _operation_is_completed(manifest, operation_kind):
            status = EXPORT_STATUS_MISSING_ARTIFACT
    elif project_root is not None and manifest is not None and _operation_is_completed(manifest, operation_kind):
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
    report = text_cleanup_service.load_cleanup_document(project_root) or {}
    cleaned_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8").strip()
    parameters = _compact_fields(
        [
            ("Cleanup Mode", "hybrid"),
            ("Validation", report.get("validation_state")),
            ("Uncertain Decisions Preserved", report.get("uncertainty_count")),
            ("Detected Language", dict(report.get("document_profile") or {}).get("language")),
            ("Warnings Count", len(report.get("warnings", []))),
            *_token_usage_fields(report),
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
    document = chunking_document_service.load_chunking_document(project_root)
    report = {} if document is None else chunking_document_service.derive_report(document)
    state = {} if document is None else chunking_document_service.derive_operation_state(document)
    metadata = _metadata_from_state(state)
    chunks = _sorted_by_sequence(chunking_document_service.load_chunks(project_root))
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
    document = ai_translation_service.load_translation_document(project_root)
    if document is None:
        raise ValueError("AI Translation export requires translated_text.json.")
    summary = ai_translation_service.load_translation_summary(project_root)
    budget_metadata = dict(document["budget_metadata"])
    translated_chunks = _sorted_by_sequence(ai_translation_service.load_translated_chunks(project_root))
    translated_texts = [
        str(chunk.get("translated_text", "")).strip()
        for chunk in translated_chunks
        if str(chunk.get("translated_text", "")).strip()
    ]
    parameters = _compact_fields(
        [
            ("Target Language", document["target_language"]),
            ("Status", summary["status"]),
            ("Context Window", budget_metadata.get("context_window")),
            ("Maximum Output Tokens", budget_metadata.get("max_output_tokens")),
            ("Total Chunks", summary["total_count"]),
            ("Translated Count", summary["translated_count"]),
            ("Approved Count", summary["approved_count"]),
            *_token_usage_fields(document),
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
    @date       2026-05-19
    @version    0.2.0
    """
    document = character_discovery_service.load_character_document(project_root) or {}
    characters = character_discovery_service.load_character_profiles(project_root)
    source = document.get("source", {}) if isinstance(document, dict) else {}
    source = source if isinstance(source, dict) else {}
    parameters = _compact_fields(
        [
            ("Source Kind", source.get("kind")),
            ("Source Language", source.get("language")),
            ("Character Count", len(characters)),
            *_token_usage_fields(document, {}),
        ]
    )
    dossier_records = _character_dossier_records(characters)
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=_header_fields(manifest, _EXPORT_KIND_LABELS[EXPORT_KIND_CHARACTERS]),
        parameter_fields=parameters,
        sections=[("Character Dossiers", _render_character_dossiers(dossier_records))],
        character_dossiers=dossier_records,
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
    @version    0.1.2
    """
    report = speech_blocks_service.load_speech_blocks_report(project_root) or {}
    state = speech_blocks_service.load_operation_state(project_root) or {}
    metadata = _metadata_from_state(state)
    speech_blocks = speech_blocks_service.sort_speech_blocks(speech_blocks_service.load_speech_blocks(project_root))
    source_kind = _first_value(report.get("source_kind"), metadata.get("source_kind"))
    source_chunks = (
        ai_translation_service.load_translated_chunks(project_root)
        if source_kind == "translated_chunks"
        else chunking_document_service.load_chunks(project_root)
    )
    source_chunk_count = len(source_chunks) if source_chunks else None
    parameters = _compact_fields(
        [
            ("Source Language", _first_value(report.get("source_language"), metadata.get("source_language"))),
            ("Source Kind", source_kind),
            *_ai_parameter_fields(
                project_root,
                report,
                state,
                _first_value(report.get("speech_blocks_profile_id_last_used"), metadata.get("ai_profile_id")),
            ),
            ("Source Chunk Count", _first_value(report.get("source_chunk_count"), source_chunk_count)),
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
    @date       2026-05-19
    @version    0.2.0
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
        lines.extend(
            ["", f"## {section_title}", "", _render_markdown_section_body(section_title, section_body, document)]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_markdown_section_body(section_title: str, section_body: str, document: ExportDocument) -> str:
    """
    @brief      Render one Markdown section body with export-specific shaping.
    @param[in]  section_title Section heading.
    @param[in]  section_body Plain normalized section body.
    @param[in]  document Source export document carrying structured payloads.
    @return     Markdown-ready section body.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.2.0
    """
    if section_title == "Character Dossiers" and document.character_dossiers is not None:
        return _render_character_dossiers_markdown(document.character_dossiers)
    if section_title == "Speech Blocks":
        return _render_speech_blocks_markdown(section_body)
    return section_body.strip()


def _render_speech_blocks_markdown(section_body: str) -> str:
    """
    @brief      Render Speech Blocks with Markdown hard line breaks inside each block.
    @param[in]  section_body Plain Speech Blocks section body.
    @return     Markdown-ready Speech Blocks section body.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    rendered_blocks: list[str] = []
    for block_text in section_body.strip().split("\n\n"):
        block_lines = [line.strip() for line in block_text.splitlines() if line.strip()]
        if block_lines:
            rendered_blocks.append("  \n".join(block_lines))
    return "\n\n".join(rendered_blocks)


def _render_character_dossiers_markdown(records: list[list[tuple[str, str]]]) -> str:
    """
    @brief      Render structured character dossiers as Markdown subsections and attribute tables.
    @param[in]  records Ordered per-character label/value records.
    @return     Markdown-ready character dossier section body.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.2.0
    """
    rendered_dossiers: list[str] = []
    for record in records:
        if not record:
            continue
        name = next((value for label, value in record if label == "Name"), "Character")
        lines = [f"### {_escape_markdown(name)}", "", "| Attribute | Value |", "| --- | --- |"]
        for label, value in record:
            if label == "Name":
                continue
            lines.append(f"| **{_escape_markdown(label)}** | {_escape_markdown(value)} |")
        rendered_dossiers.append("\n".join(lines))
    return "\n\n".join(rendered_dossiers).strip()


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
        ("Export Timestamp", utc_now_iso()),
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
    @version    0.2.0
    """
    if export_kind == EXPORT_KIND_NARRATOR_VOICE:
        return bool(_narrator_voice_archive_items(project_root))
    if export_kind == EXPORT_KIND_CHARACTER_VOICES:
        return bool(_character_voice_archive_items(project_root))
    if export_kind == EXPORT_KIND_AUDIO_ASSEMBLY:
        return bool(_audio_assembly_archive_items(project_root))
    artifact_path = project_root / _EXPORT_ARTIFACT_BY_KIND[export_kind]
    if not artifact_path.is_file():
        return False
    if export_kind == EXPORT_KIND_CLEANED_TEXT:
        return bool(artifact_path.read_text(encoding="utf-8").strip())
    if export_kind == EXPORT_KIND_TEXT_CHUNKS:
        return bool(chunking_document_service.load_chunks(project_root))
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


def _build_archive_entries(
    project_root: Path,
    manifest: dict[str, object],
    export_kind: str,
) -> list[tuple[str, Path | None, str | None]]:
    """
    @brief      Build ZIP entries for one archive export kind.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  export_kind Stable archive export kind token.
    @return     Ordered tuples of archive name, optional source path, and optional text content.
    @exception  ValueError Raised when the export kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    if export_kind == EXPORT_KIND_NARRATOR_VOICE:
        return _build_narrator_voice_archive_entries(project_root)
    if export_kind == EXPORT_KIND_CHARACTER_VOICES:
        return _build_character_voice_archive_entries(project_root)
    if export_kind == EXPORT_KIND_AUDIO_ASSEMBLY:
        return _build_audio_assembly_archive_entries(project_root, manifest)
    raise ValueError(f"Unsupported archive export kind: {export_kind}")


def _build_narrator_voice_archive_entries(project_root: Path) -> list[tuple[str, Path | None, str | None]]:
    """
    @brief      Build the authoritative narrator document and canonical sample WAV entries.
    @param[in]  project_root Active project root folder.
    @return     Ordered ZIP entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    1.0.0
    """
    document_path = project_root / config.NARRATOR_VOICE_FILE_NAME
    entries: list[tuple[str, Path | None, str | None]] = [
        (config.NARRATOR_VOICE_FILE_NAME, document_path, None)
    ]
    for _profile, audio_path, _metadata in _narrator_voice_archive_items(project_root):
        entries.append((audio_path.name, audio_path, None))
    return entries


def _build_character_voice_archive_entries(project_root: Path) -> list[tuple[str, Path | None, str | None]]:
    """
    @brief      Build character voice sample WAV and companion TXT archive entries.
    @param[in]  project_root Active project root folder.
    @return     Ordered ZIP entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    entries: list[tuple[str, Path | None, str | None]] = []
    used_names: set[str] = set()
    voice_language = character_voices_service.load_selected_voice_language(project_root)
    for target, audio_path, metadata in _character_voice_archive_items(project_root):
        base_name = _unique_archive_stem(
            _first_value(metadata.get("display_name"), target.get("display_name"), target.get("target_id")),
            used_names,
        )
        entries.append((f"character_voices/{base_name}.wav", audio_path, None))
        entries.append(
            (
                f"character_voices/{base_name}.txt",
                None,
                _build_voice_companion_text(
                    "Character Voice",
                    str(_first_value(metadata.get("display_name"), target.get("display_name"), base_name)),
                    str(_first_value(metadata.get("prompt_text"), target.get("prompt_text"), "")),
                    str(
                        _first_value(
                            metadata.get("preview_text"),
                            target.get("preview_text"),
                            character_voices_service.effective_target_preview_text(target, voice_language),
                        )
                    ),
                ),
            )
        )
    return entries


def _build_audio_assembly_archive_entries(
    project_root: Path,
    manifest: dict[str, object],
) -> list[tuple[str, Path | None, str | None]]:
    """
    @brief      Build final audiobook WAV entries plus one assembly manifest TXT entry.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @return     Ordered ZIP entries.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    items = _audio_assembly_archive_items(project_root)
    entries: list[tuple[str, Path | None, str | None]] = []
    used_names: set[str] = set()
    for output, audio_path in items:
        source_file_name = Path(str(output.get("file_name", "") or audio_path.name)).name
        file_name = _unique_archive_file_name(source_file_name, used_names)
        entries.append((f"audio_assembly/{file_name}", audio_path, None))
    entries.append(
        (
            "audio_assembly/audio_assembly_manifest.txt",
            None,
            _build_audio_assembly_manifest_text(project_root, manifest, items),
        )
    )
    return entries


def _narrator_voice_archive_items(project_root: Path) -> list[tuple[dict[str, object], Path, dict[str, object]]]:
    """
    @brief      Collect narrator profiles that have an exportable sample WAV.
    @param[in]  project_root Active project root folder.
    @return     Ordered narrator profile, audio path, and metadata tuples.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.2.0
    """
    items: list[tuple[dict[str, object], Path, dict[str, object]]] = []
    if not (project_root / config.NARRATOR_VOICE_FILE_NAME).is_file():
        return items
    for profile in narrator_definition_service.load_profiles(project_root):
        profile_id = str(profile.get("profile_id", "")).strip()
        metadata = narrator_definition_service.load_profile_sample_metadata(project_root, profile_id)
        audio_path, _metadata_path = narrator_definition_service.profile_sample_paths(project_root, profile_id)
        if profile_id and isinstance(metadata, dict) and audio_path.is_file():
            items.append((profile, audio_path, metadata))
    return items


def _character_voice_archive_items(project_root: Path) -> list[tuple[dict[str, object], Path, dict[str, object]]]:
    """
    @brief      Collect character voice targets that have an exportable sample WAV.
    @param[in]  project_root Active project root folder.
    @return     Ordered character target, audio path, and metadata tuples.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.2.0
    """
    items: list[tuple[dict[str, object], Path, dict[str, object]]] = []
    if not (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).is_file():
        return items
    for target in character_voices_service.load_voice_plan(project_root):
        if str(target.get("target_kind", "")).strip() != character_voices_service.TARGET_KIND_CHARACTER:
            continue
        target_id = str(target.get("target_id", "")).strip()
        metadata = character_voices_service.load_target_sample_metadata(project_root, target_id)
        audio_path, _metadata_path = character_voices_service.target_sample_paths(project_root, target_id)
        if target_id and isinstance(metadata, dict) and audio_path.is_file():
            items.append((target, audio_path, metadata))
    return items


def _audio_assembly_archive_items(project_root: Path) -> list[tuple[dict[str, object], Path]]:
    """
    @brief      Collect generated Audio Assembly outputs that still exist on disk.
    @param[in]  project_root Active project root folder.
    @return     Ordered output record and audio path tuples.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    items: list[tuple[dict[str, object], Path]] = []
    for output in audio_assembly_service.load_generated_outputs(project_root):
        audio_relative_path = str(output.get("audio_relative_path", "")).strip()
        if not audio_relative_path:
            continue
        audio_path = project_root / audio_relative_path
        if audio_path.is_file() and is_path_inside_project(project_root, audio_path):
            items.append((output, audio_path))
    return items


def _build_voice_companion_text(
    voice_type: str,
    display_name: str,
    prompt_text: str,
    preview_text: str,
) -> str:
    """
    @brief      Build one companion text file for a voice sample export.
    @param[in]  voice_type Operator-facing voice type label.
    @param[in]  display_name Voice display name.
    @param[in]  prompt_text Voice definition prompt.
    @param[in]  preview_text Preview text used for the sample.
    @return     UTF-8 companion text content.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    return (
        f"{voice_type}: {display_name.strip() or '-'}\n\n"
        "Voice Definition\n"
        "----------------\n"
        f"{prompt_text.strip() or '-'}\n\n"
        "Preview Text\n"
        "------------\n"
        f"{preview_text.strip() or '-'}\n"
    )


def _build_audio_assembly_manifest_text(
    project_root: Path,
    manifest: dict[str, object],
    items: list[tuple[dict[str, object], Path]],
) -> str:
    """
    @brief      Build the text manifest included in Audio Assembly ZIP exports.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  items Exported output record and audio path tuples.
    @return     UTF-8 manifest text content.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    report = audio_assembly_service.load_audio_assembly_report(project_root) or {}
    settings = audio_assembly_service.normalize_audio_assembly_settings(
        report.get("settings") if isinstance(report, dict) else manifest.get("audio_assembly_settings")
    )
    lines = [
        "Audio Assembly Export",
        "=====================",
        "",
        *_render_txt_fields(_header_fields(manifest, _EXPORT_KIND_LABELS[EXPORT_KIND_AUDIO_ASSEMBLY])),
        "",
        "Method of Composure",
        "-------------------",
        f"Output Mode: {settings['output_mode']}",
        f"Output Format: {settings['output_format']}",
        f"Inter-block Silence: {settings['inter_block_silence_ms']} ms",
        f"Inter-chunk Silence: {settings['inter_chunk_silence_ms']} ms",
        f"Max Duration: {settings['max_duration_minutes']} minutes",
        "",
        "Files",
        "-----",
    ]
    total_size = 0
    total_duration = 0.0
    for output, audio_path in items:
        size_bytes = audio_path.stat().st_size
        duration_seconds = float(output.get("duration_seconds", 0.0) or 0.0)
        total_size += size_bytes
        total_duration += duration_seconds
        lines.extend(
            [
                f"- {audio_path.name}",
                f"  Project Path: {audio_path.relative_to(project_root)}",
                f"  Duration: {_format_seconds(duration_seconds)}",
                f"  Size: {size_bytes} bytes",
                f"  Audio Blocks: {int(output.get('block_count', 0) or 0)}",
            ]
        )
    lines.extend(
        [
            "",
            "Totals",
            "------",
            f"File Count: {len(items)}",
            f"Total Duration: {_format_seconds(total_duration)}",
            f"Total Size: {total_size} bytes",
            "",
        ]
    )
    return "\n".join(lines)


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


def _character_dossier_records(characters: list[dict[str, object]]) -> list[list[tuple[str, str]]]:
    """
    @brief      Build the structured per-character label/value records.
    @details    Single source of truth shared by the plain-text and Markdown
                character renderers so neither re-parses the other's output.
    @param[in]  characters Normalized character profile payloads.
    @return     Ordered per-character label/value records (empty records dropped).
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.1.0
    """
    field_map = [
        ("Name", "canonical_name"),
        ("Gender Hint", "gender_hint"),
        ("Age Hint", "age_hint"),
        ("Voice Definition Prompt", "voice_definition_prompt"),
    ]
    records: list[list[tuple[str, str]]] = []
    for character in characters:
        record: list[tuple[str, str]] = []
        for label, key in field_map:
            value = _format_value(character.get(key))
            if value != "-":
                record.append((label, value))
        if record:
            records.append(record)
    return records


def _render_character_dossiers(records: list[list[tuple[str, str]]]) -> str:
    """
    @brief      Render structured character records into readable plain dossiers.
    @param[in]  records Ordered per-character label/value records.
    @return     Character dossier text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.4.0
    """
    dossiers = ["\n".join(f"{label}: {value}" for label, value in record) for record in records]
    return "\n\n----\n\n".join(dossier for dossier in dossiers if dossier.strip())


def _render_speech_blocks(speech_blocks: list[dict[str, object]]) -> str:
    """
    @brief      Render Speech Blocks as speaker/text pairs without internal ids.
    @param[in]  speech_blocks Normalized Speech Blocks payloads.
    @return     Speaker/text export body.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.1
    """
    rendered_blocks: list[str] = []
    for block in speech_blocks:
        speaker_name = str(block.get("speaker_display_name") or block.get("speaker_name") or "Unknown").strip()
        block_text = str(block.get("text", "")).strip()
        if block_text:
            rendered_blocks.append(f"{speaker_name}\n{block_text}")
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
    @brief      Normalize one default export file stem via the shared helper.
    @param[in]  value Candidate file stem.
    @return     Filesystem-safe file stem.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-19
    @version    0.2.0
    """
    return _shared_safe_file_stem(value)


def _unique_archive_stem(value: object, used_names: set[str]) -> str:
    """
    @brief      Build one unique archive-safe file stem.
    @param[in]  value Candidate display name.
    @param[in]  used_names Case-folded names already emitted.
    @return     Unique archive file stem.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    base_name = _safe_file_stem(str(value or "AudioMancer"))
    candidate_name = base_name
    suffix = 2
    while candidate_name.casefold() in used_names:
        candidate_name = f"{base_name}_{suffix}"
        suffix += 1
    used_names.add(candidate_name.casefold())
    return candidate_name


def _unique_archive_file_name(value: object, used_names: set[str]) -> str:
    """
    @brief      Build one unique archive-safe file name while preserving the suffix.
    @param[in]  value Candidate file name.
    @param[in]  used_names Case-folded names already emitted.
    @return     Unique archive file name.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    file_name = Path(str(value or "audio.wav")).name
    suffix = Path(file_name).suffix or ".wav"
    stem = _safe_file_stem(Path(file_name).stem or "audio")
    candidate_name = f"{stem}{suffix}"
    counter = 2
    while candidate_name.casefold() in used_names:
        candidate_name = f"{stem}_{counter}{suffix}"
        counter += 1
    used_names.add(candidate_name.casefold())
    return candidate_name


def _format_seconds(duration_seconds: float) -> str:
    """
    @brief      Format seconds as a compact duration string for archive manifests.
    @param[in]  duration_seconds Duration in seconds.
    @return     Human-readable duration.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    total_seconds = max(0, int(round(duration_seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


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
