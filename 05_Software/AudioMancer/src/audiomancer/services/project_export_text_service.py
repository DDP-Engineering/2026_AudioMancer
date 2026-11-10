#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""Build and render the readable TXT and Markdown export projections."""

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    character_discovery_service,
    chunking_document_service,
    speech_blocks_service,
    text_cleanup_service,
    token_usage_service,
)
from audiomancer.services.operation_runtime_service import try_resolve_project_relative_path
from audiomancer.services.time_service import utc_now_iso


@dataclass(frozen=True)
class ExportDocument:
    """
    @brief      Normalized export document model shared by text renderers.
    @details    `character_dossiers` carries the structured per-character
                label/value records so the Markdown renderer never re-parses
                the plain-text projection.
    @return     Immutable export document payload.
    @exception  None
    """

    title: str
    header_fields: list[tuple[str, str]]
    parameter_fields: list[tuple[str, str]]
    sections: list[tuple[str, str]]
    character_dossiers: list[list[tuple[str, str]]] | None = None


def build_cleaned_text_document(project_root: Path, manifest: dict[str, object], label: str) -> ExportDocument:
    """
    @brief      Build the cleaned-text export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  label Export type label.
    @return     Normalized export document.
    @exception  None
    """
    report = {}
    if _paths_are_project_local(
        project_root, config.CLEANUP_DOCUMENT_FILE_NAME, config.EXTRACTED_TEXT_FILE_NAME, config.SOURCE_LEDGER_FILE_NAME
    ):
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
        header_fields=header_fields(manifest, label),
        parameter_fields=parameters,
        sections=[("Cleaned Text", cleaned_text)],
    )


def build_text_chunks_document(project_root: Path, manifest: dict[str, object], label: str) -> ExportDocument:
    """
    @brief      Build the text-chunks export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  label Export type label.
    @return     Normalized export document.
    @exception  None
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
                first_value(report.get("chunking_mode"), state.get("mode"), _chunk_mode_from_chunks(chunks)),
            ),
            *_ai_parameter_fields(
                project_root,
                report,
                state,
                first_value(report.get("ai_profile_id"), metadata.get("ai_profile_id")),
            ),
            ("Chunk Count", first_value(report.get("chunk_count"), len(chunks))),
            ("Word Count", _word_count(chunk_texts)),
            ("Character Count", sum(len(text) for text in chunk_texts)),
            (
                "Detected Chapters",
                first_value(report.get("detected_chapter_count"), metadata.get("detected_chapter_count")),
            ),
            (
                "Chunking Method",
                first_value(
                    report.get("semantic_strategy"),
                    metadata.get("semantic_strategy"),
                    _semantic_strategy_from_chunks(chunks),
                ),
            ),
        ]
    )
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=header_fields(manifest, label),
        parameter_fields=parameters,
        sections=[("Text Chunks", combined_text)],
    )


def build_ai_translation_document(project_root: Path, manifest: dict[str, object], label: str) -> ExportDocument:
    """
    @brief      Build the AI-translation export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  label Export type label.
    @return     Normalized export document.
    @exception  None
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
            ("Output Reserve Tokens", budget_metadata.get("output_reserve_tokens")),
            ("Total Chunks", summary["total_count"]),
            ("Translated Count", summary["translated_count"]),
            ("Approved Count", summary["approved_count"]),
            *_token_usage_fields(document),
        ]
    )
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=header_fields(manifest, label),
        parameter_fields=parameters,
        sections=[("Translated Text", "\n\n".join(translated_texts))],
    )


def build_characters_document(project_root: Path, manifest: dict[str, object], label: str) -> ExportDocument:
    """
    @brief      Build the character dossier export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  label Export type label.
    @return     Normalized export document.
    @exception  None
    """
    document = character_discovery_service.load_character_document(project_root) or {}
    characters = character_discovery_service.load_character_profiles(project_root)
    source = document.get("source", {}) if isinstance(document, dict) else {}
    source = source if isinstance(source, dict) else {}
    operation_summary = character_discovery_service.character_operation_summary(document)
    parameters = _compact_fields(
        [
            ("Source Kind", source.get("kind")),
            ("Source Language", source.get("language")),
            ("Character Count", len(characters)),
            ("Warnings Count", operation_summary["warning_count"]),
            *_token_usage_fields(document, {}),
        ]
    )
    dossier_records = _character_dossier_records(characters)
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=header_fields(manifest, label),
        parameter_fields=parameters,
        sections=[("Character Dossiers", _render_character_dossiers(dossier_records))],
        character_dossiers=dossier_records,
    )


def build_speech_blocks_document(project_root: Path, manifest: dict[str, object], label: str) -> ExportDocument:
    """
    @brief      Build the Speech Blocks export document.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  label Export type label.
    @return     Normalized export document.
    @exception  None
    """
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    source_paths_safe = _paths_are_project_local(
        project_root, config.PROJECT_MANIFEST_FILE_NAME, config.CHUNK_ARTIFACT_FILE_NAME,
        config.TRANSLATED_CHUNKS_FILE_NAME,
    )
    # A missing or unsafe optional source must not prevent exporting the persisted speech.
    fallback_count = None if source_paths_safe else len({block["chunk_id"] for block in speech_blocks})
    report = speech_blocks_service.load_speech_blocks_report(project_root, fallback_count) or {}
    state = speech_blocks_service.load_operation_state(project_root, fallback_count) or {}
    metadata = _metadata_from_state(state)
    source_kind = first_value(report.get("source_kind"), metadata.get("source_kind"))
    parameters = _compact_fields(
        [
            ("Source Language", first_value(report.get("source_language"), metadata.get("source_language"))),
            ("Source Kind", source_kind),
            *_ai_parameter_fields(
                project_root,
                report,
                state,
                first_value(report.get("speech_blocks_profile_id_last_used"), metadata.get("ai_profile_id")),
            ),
            ("Source Chunk Count", report.get("source_chunk_count")),
            ("Speech Block Count", first_value(report.get("speech_block_count"), len(speech_blocks))),
            ("Warnings Count", first_value(report.get("warning_count"), state.get("warning_count"))),
            *_token_usage_fields(report, metadata),
        ]
    )
    return ExportDocument(
        title="AudioMancer Export",
        header_fields=header_fields(manifest, label),
        parameter_fields=parameters,
        sections=[("Speech Blocks", _render_speech_blocks(speech_blocks))],
    )


def render_txt_document(document: ExportDocument) -> str:
    """
    @brief      Render a normalized export document as plain text.
    @param[in]  document Normalized export document.
    @return     Plain-text document content.
    @exception  None
    """
    lines = [document.title, "=" * len(document.title), ""]
    lines.extend(render_txt_fields(document.header_fields))
    lines.extend(["", "Operation Parameters", "--------------------"])
    lines.extend(render_txt_fields(document.parameter_fields))
    for section_title, section_body in document.sections:
        lines.extend(["", section_title, "-" * len(section_title), section_body.strip()])
    return "\n".join(lines).rstrip() + "\n"


def render_markdown_document(document: ExportDocument) -> str:
    """
    @brief      Render a normalized export document as Markdown.
    @param[in]  document Normalized export document.
    @return     Markdown document content.
    @exception  None
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


def render_txt_fields(fields: Iterable[tuple[str, str]]) -> list[str]:
    """
    @brief      Render plain `Label: value` lines.
    @param[in]  fields Ordered label/value pairs.
    @return     Plain-text field lines.
    @exception  None
    """
    return [f"{label}: {value}" for label, value in fields]


def header_fields(manifest: dict[str, object], export_type_label: str) -> list[tuple[str, str]]:
    """
    @brief      Build common export header fields.
    @param[in]  manifest Active project manifest.
    @param[in]  export_type_label Operator-facing export type label.
    @return     Ordered header fields.
    @exception  None
    """
    source_name = _source_original_name(manifest)
    return [
        ("Project", str(manifest.get("display_name") or manifest.get("project_name") or "-")),
        ("Original Source Filename", source_name),
        ("Original Extension", Path(source_name).suffix or "-"),
        ("Export Type", export_type_label),
        ("Export Timestamp", utc_now_iso()),
    ]


def _character_dossier_records(characters: list[dict[str, object]]) -> list[list[tuple[str, str]]]:
    """
    @brief      Build the structured per-character label/value records.
    @details    Single source of truth shared by the plain-text and Markdown
                character renderers so neither re-parses the other's output.
    @param[in]  characters Normalized character profile payloads.
    @return     Ordered per-character label/value records (empty records dropped).
    @exception  None
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
    """
    dossiers = ["\n".join(f"{label}: {value}" for label, value in record) for record in records]
    return "\n\n----\n\n".join(dossier for dossier in dossiers if dossier.strip())


def _render_speech_blocks(speech_blocks: list[dict[str, object]]) -> str:
    """
    @brief      Render Speech Blocks as speaker/text pairs without internal ids.
    @param[in]  speech_blocks Normalized Speech Blocks payloads.
    @return     Speaker/text export body.
    @exception  None
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
    """
    request_record = _first_ai_request_record(project_root, state)
    request_payload = request_record.get("request_payload")
    request_payload = dict(request_payload) if isinstance(request_payload, dict) else {}
    resolved_profile_id = first_value(profile_id, request_record.get("profile_id"))
    if resolved_profile_id in (None, "") and not request_record and str(state.get("mode", "")).strip() != "ai_assisted":
        return []
    return [
        ("AI Profile", resolved_profile_id),
        ("AI Backend", first_value(request_record.get("backend_kind"), report.get("backend_kind"))),
        ("AI Base URL", first_value(request_record.get("base_url"), report.get("base_url"))),
        (
            "AI Model",
            first_value(
                request_payload.get("model"),
                request_record.get("model_name"),
                report.get("model_name"),
            ),
        ),
        ("AI Temperature", request_payload.get("temperature")),
    ]


def _paths_are_project_local(project_root: Path, *file_names: str) -> bool:
    """Check the paths used by optional text export metadata loaders."""
    return all(try_resolve_project_relative_path(project_root, name) is not None for name in file_names)


def _first_ai_request_record(project_root: Path, state: dict[str, object]) -> dict[str, object]:
    """
    @brief      Read the first request record from one operation-local AI transaction log.
    @param[in]  project_root Active project root folder.
    @param[in]  state Operation state payload.
    @return     First request record or an empty dictionary.
    @exception  None
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
    """
    metadata = _metadata_from_state(state)
    candidate = first_value(metadata.get("ai_log_relative_path"), metadata.get("log_relative_path"))
    if candidate not in (None, ""):
        return try_resolve_project_relative_path(project_root, candidate)
    artifact_paths = state.get("artifact_paths")
    if isinstance(artifact_paths, list):
        for artifact_path in artifact_paths:
            artifact_name = str(artifact_path).strip()
            if Path(artifact_name).name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX) and artifact_name.endswith(
                config.AI_TRANSACTION_LOG_FILE_EXTENSION
            ):
                return try_resolve_project_relative_path(project_root, artifact_name)
    return None


def _compact_fields(fields: Iterable[tuple[str, object]]) -> list[tuple[str, str]]:
    """
    @brief      Normalize export fields into display-safe text values.
    @param[in]  fields Ordered raw label/value pairs.
    @return     Ordered display label/value pairs.
    @exception  None
    """
    return [(label, _format_value(value)) for label, value in fields]


def _format_value(value: object) -> str:
    """
    @brief      Convert a raw export field value to readable text.
    @param[in]  value Candidate value.
    @return     Readable field value.
    @exception  None
    """
    if value in (None, ""):
        return "-"
    if isinstance(value, list | tuple):
        return ", ".join(str(item) for item in value if str(item).strip()) or "-"
    return str(value)


def first_value(*values: object) -> object:
    """
    @brief      Return the first non-empty candidate value.
    @param[in]  values Candidate values.
    @return     First non-empty value or `None`.
    @exception  None
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
    """
    metadata = state.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _sorted_by_sequence(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    @brief      Sort artifact records by sequence index when present.
    @param[in]  items Artifact record dictionaries.
    @return     Ordered artifact record dictionaries.
    @exception  None
    """
    return sorted(items, key=lambda item: int(item.get("sequence_index", 0) or item.get("block_index", 0) or 0))


def _word_count(texts: Iterable[str]) -> int:
    """
    @brief      Count whitespace-separated words across text spans.
    @param[in]  texts Text spans.
    @return     Word count.
    @exception  None
    """
    return sum(len(text.split()) for text in texts)


def _chunk_mode_from_chunks(chunks: list[dict[str, object]]) -> str | None:
    """
    @brief      Resolve a chunking mode fallback from chunk records.
    @param[in]  chunks Chunk payload list.
    @return     Chunking mode or `None`.
    @exception  None
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
    """
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        return "-"
    return str(source_document.get("original_name") or "-")


def _escape_markdown(value: str) -> str:
    """
    @brief      Escape Markdown table delimiters in field values.
    @param[in]  value Candidate table value.
    @return     Escaped table value.
    @exception  None
    """
    return value.replace("|", "\\|").replace("\n", "<br>")
