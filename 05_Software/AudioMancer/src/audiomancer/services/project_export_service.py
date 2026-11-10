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
"""

# IMPORTS

from dataclasses import dataclass
import json
from pathlib import Path
import wave

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    archive_writer,
    audio_assembly_service,
    audio_assembly_wav,
    audio_blocks_artifact_service,
    character_discovery_service,
    character_voices_service,
    chunking_document_service,
    narrator_definition_service,
    operation_runtime_service,
    persistence_service,
    project_export_text_service,
    speech_blocks_service,
)
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.operation_runtime_service import (
    append_required_extension,
    safe_file_stem,
    try_resolve_project_relative_path,
)
from audiomancer.services.operation_runtime_service import (
    is_path_inside_project as _is_path_inside_project,
)
from audiomancer.services.project_export_text_service import first_value

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
EXPORT_STATUS_PARTIAL = "partial"
EXPORT_STATUS_INVALID_ARTIFACT = "invalid_artifact"

_EXPORT_KIND_LABELS = {
    EXPORT_KIND_CLEANED_TEXT: "Cleaned Text",
    EXPORT_KIND_TEXT_CHUNKS: "Text Chunks",
    EXPORT_KIND_AI_TRANSLATION: "AI Translation",
    EXPORT_KIND_CHARACTERS: "Characters",
    EXPORT_KIND_NARRATOR_VOICE: "Narrator Voice",
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
    """
    return [build_export_state(project_root, manifest, export_kind) for export_kind in EXPORT_KIND_OPTIONS]


def default_export_file_name(manifest: dict[str, object] | None, export_kind: str, export_format: str) -> str:
    """
    @brief      Build the default user-facing export file name.
    @param[in]  manifest Active project manifest or `None`.
    @param[in]  export_kind Stable export kind token.
    @param[in]  export_format Stable export format token.
    @return     Filesystem-safe default file name.
    @exception  ValueError Raised when the export kind or format is unsupported.
    """
    _validate_export_kind(export_kind)
    extension = export_extension(export_format)
    project_name = str((manifest or {}).get("display_name") or (manifest or {}).get("project_name") or "AudioMancer")
    kind_name = _EXPORT_KIND_LABELS[export_kind].lower().replace(" ", "_")
    return f"{safe_file_stem(project_name)}_{kind_name}{extension}"


def export_extension(export_format: str) -> str:
    """
    @brief      Resolve one export format to a default file suffix.
    @param[in]  export_format Stable export format token.
    @return     File extension including the leading dot.
    @exception  ValueError Raised when the format is unsupported.
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
    """
    return operation_runtime_service.is_destination_inside_project(project_root, export_path)


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
    """
    _PROJECT_EXPORT_LOGGER.info("Rendering project export kind=%s format=%s", export_kind, export_format)
    _validate_export_kind(export_kind)
    _validate_export_format(export_format)
    if export_format == EXPORT_FORMAT_ZIP:
        raise ValueError("ZIP exports must be written with create_archive_export.")
    if export_kind in _ARCHIVE_EXPORT_KINDS:
        raise ValueError("Archive export kinds support ZIP only.")
    state = build_export_state(project_root, manifest, export_kind)
    if not bool(state.get("can_export", False)):
        _PROJECT_EXPORT_LOGGER.warning("Project export unavailable kind=%s status=%s", export_kind, state.get("status"))
        raise ValueError("The requested export is not available yet.")
    document = _build_export_document(Path(project_root), manifest, export_kind)
    if export_format == EXPORT_FORMAT_MARKDOWN:
        return project_export_text_service.render_markdown_document(document)
    return project_export_text_service.render_txt_document(document)


def write_text_export(
    project_root: str | Path,
    manifest: dict[str, object],
    export_kind: str,
    export_format: str,
    export_path: str | Path,
) -> Path:
    """Render and publish a UTF-8 text export outside the active project."""
    destination = append_required_extension(export_path, export_extension(export_format))
    if is_path_inside_project(project_root, destination):
        raise ValueError("Export destination must be outside the active project folder.")
    content = render_export(project_root, manifest, export_kind, export_format)
    persistence_service.write_text_atomic(destination, content)
    return destination


@dataclass(frozen=True)
class ArchiveExportResult:
    """Published stage archive and optional exported/planned count for a partial run."""

    path: Path
    partial_counts: tuple[int, int] | None = None


def create_archive_export(
    project_root: str | Path,
    manifest: dict[str, object],
    export_kind: str,
    export_path: str | Path,
    *,
    progress_callback=None,
    cancel_requested=None,
) -> Path:
    """Publish a stage ZIP and return its path."""
    return publish_archive_export(
        project_root, manifest, export_kind, export_path,
        progress_callback=progress_callback, cancel_requested=cancel_requested,
    ).path


def publish_archive_export(
    project_root: str | Path,
    manifest: dict[str, object],
    export_kind: str,
    export_path: str | Path,
    *,
    progress_callback=None,
    cancel_requested=None,
) -> ArchiveExportResult:
    """Publish a stage ZIP and describe any partial Assembly result."""
    _PROJECT_EXPORT_LOGGER.info("Creating project archive export kind=%s path=%s", export_kind, export_path)
    _validate_export_kind(export_kind)
    if export_kind not in _ARCHIVE_EXPORT_KINDS:
        raise ValueError(f"Export kind is not an archive export: {export_kind}")
    archive_path = append_required_extension(export_path, ".zip")
    if is_path_inside_project(project_root, archive_path):
        raise ValueError("Archive destination must be outside the active project folder.")
    operation_runtime_service.raise_if_cancelled(cancel_requested)
    partial_counts = None
    if export_kind == EXPORT_KIND_AUDIO_ASSEMBLY:
        entries, partial_counts = _build_audio_assembly_archive_entries(
            Path(project_root), manifest, cancel_requested
        )
    else:
        entries = _build_archive_entries(Path(project_root), export_kind)
    if not entries:
        raise ValueError("The requested archive has no generated audio assets to export.")
    archive_writer.write_archive(
        archive_path, entries, progress_callback=progress_callback, cancel_requested=cancel_requested,
    )
    return ArchiveExportResult(archive_path, partial_counts)


def build_export_state(
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
    """
    _validate_export_kind(export_kind)
    status = EXPORT_STATUS_NOT_READY
    if project_root is not None and manifest is not None:
        completed = _operation_is_completed(manifest, _EXPORT_OPERATION_BY_KIND[export_kind])
        if completed or export_kind in _ARCHIVE_EXPORT_KINDS:
            try:
                root = Path(project_root)
                if export_kind == EXPORT_KIND_AUDIO_ASSEMBLY:
                    report = _load_assembly_report(root)
                    candidates = _assembly_candidates(root, report)
                    if candidates:
                        status = (
                            EXPORT_STATUS_PARTIAL
                            if _assembly_is_partial(report, completed, len(candidates))
                            else EXPORT_STATUS_AVAILABLE
                        )
                    elif completed:
                        status = EXPORT_STATUS_MISSING_ARTIFACT
                elif _artifact_ready(root, export_kind):
                    status = EXPORT_STATUS_AVAILABLE
                elif completed:
                    status = EXPORT_STATUS_MISSING_ARTIFACT
            except (OSError, ValueError, TypeError, OverflowError) as error:
                _PROJECT_EXPORT_LOGGER.warning("Cannot read export artifact kind=%s: %s", export_kind, error)
                status = EXPORT_STATUS_INVALID_ARTIFACT
    return {
        "export_kind": export_kind,
        "label_key": f"home.export.{export_kind}",
        "status": status,
        "can_export": status in {EXPORT_STATUS_AVAILABLE, EXPORT_STATUS_PARTIAL},
        "default_file_name": default_export_file_name(manifest, export_kind, EXPORT_FORMAT_TXT),
    }


# LOCAL HELPERS


def _build_export_document(
    project_root: Path, manifest: dict[str, object], export_kind: str
) -> project_export_text_service.ExportDocument:
    """
    @brief      Build one normalized export document before format rendering.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest.
    @param[in]  export_kind Stable export kind token.
    @return     Normalized export document.
    @exception  ValueError Raised when the export kind is unsupported.
    """
    builders = {
        EXPORT_KIND_CLEANED_TEXT: project_export_text_service.build_cleaned_text_document,
        EXPORT_KIND_TEXT_CHUNKS: project_export_text_service.build_text_chunks_document,
        EXPORT_KIND_AI_TRANSLATION: project_export_text_service.build_ai_translation_document,
        EXPORT_KIND_CHARACTERS: project_export_text_service.build_characters_document,
        EXPORT_KIND_SPEECH_BLOCKS: project_export_text_service.build_speech_blocks_document,
    }
    return builders[export_kind](project_root, manifest, _EXPORT_KIND_LABELS[export_kind])


def _artifact_ready(project_root: Path, export_kind: str) -> bool:
    """
    @brief      Check whether one completed export artifact exists and has usable content.
    @param[in]  project_root Active project root folder.
    @param[in]  export_kind Stable export kind token.
    @return     True when the artifact can be exported.
    @exception  None
    """
    if export_kind == EXPORT_KIND_NARRATOR_VOICE:
        return bool(_narrator_voice_archive_items(project_root))
    if export_kind == EXPORT_KIND_CHARACTER_VOICES:
        return bool(_character_voice_archive_items(project_root))
    artifact_path = try_resolve_project_relative_path(project_root, _EXPORT_ARTIFACT_BY_KIND[export_kind])
    if artifact_path is None or not artifact_path.is_file():
        return False
    if export_kind == EXPORT_KIND_CLEANED_TEXT:
        return bool(artifact_path.read_text(encoding="utf-8").strip())
    if export_kind == EXPORT_KIND_TEXT_CHUNKS:
        return bool(chunking_document_service.load_chunks(project_root))
    if export_kind == EXPORT_KIND_AI_TRANSLATION:
        if try_resolve_project_relative_path(project_root, config.CHUNK_ARTIFACT_FILE_NAME) is None:
            raise ValueError("The source chunks are outside the project folder.")
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
    export_kind: str,
) -> list[tuple[str, Path | None, str | None]]:
    """
    @brief      Build ZIP entries for one voice archive export kind.
    @param[in]  project_root Active project root folder.
    @param[in]  export_kind Stable archive export kind token.
    @return     Ordered tuples of archive name, optional source path, and optional text content.
    @exception  ValueError Raised when the export kind is unsupported.
    """
    if export_kind == EXPORT_KIND_NARRATOR_VOICE:
        return _build_narrator_voice_archive_entries(project_root)
    if export_kind == EXPORT_KIND_CHARACTER_VOICES:
        return _build_character_voice_archive_entries(project_root)
    raise ValueError(f"Unsupported archive export kind: {export_kind}")


def _build_narrator_voice_archive_entries(project_root: Path) -> list[tuple[str, Path | None, str | None]]:
    """
    @brief      Build the authoritative narrator document and canonical sample WAV entries.
    @param[in]  project_root Active project root folder.
    @return     Ordered ZIP entries.
    @exception  None
    """
    document_path = project_root / config.NARRATOR_VOICE_FILE_NAME
    entries: list[tuple[str, Path | None, str | None]] = [
        (config.NARRATOR_VOICE_FILE_NAME, document_path, None)
    ]
    for _profile, audio_path, _metadata in _narrator_voice_archive_items(project_root):
        entries.append((audio_path.name, audio_path, None))
    return entries if len(entries) > 1 else []


def _build_character_voice_archive_entries(project_root: Path) -> list[tuple[str, Path | None, str | None]]:
    """
    @brief      Build character voice sample WAV and companion TXT archive entries.
    @param[in]  project_root Active project root folder.
    @return     Ordered ZIP entries.
    @exception  None
    """
    entries: list[tuple[str, Path | None, str | None]] = []
    used_names: set[str] = set()
    voice_language = narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE
    if try_resolve_project_relative_path(project_root, config.PROJECT_MANIFEST_FILE_NAME) is not None:
        voice_language = character_voices_service.load_selected_voice_language(project_root)
    for target, audio_path, metadata in _character_voice_archive_items(project_root):
        base_name = _unique_archive_stem(
            first_value(metadata.get("display_name"), target.get("display_name"), target.get("target_id")),
            used_names,
        )
        entries.append((f"character_voices/{base_name}.wav", audio_path, None))
        entries.append(
            (
                f"character_voices/{base_name}.txt",
                None,
                _build_voice_companion_text(
                    "Character Voice",
                    str(first_value(metadata.get("display_name"), target.get("display_name"), base_name)),
                    str(first_value(metadata.get("prompt_text"), target.get("prompt_text"), "")),
                    str(
                        first_value(
                            metadata.get("preview_text"),
                            target.get("preview_text"),
                            character_voices_service.effective_target_preview_text(target, voice_language),
                        )
                    ),
                ),
            )
        )
    return entries


@dataclass(frozen=True)
class _AssemblyWav:
    """Verified Assembly WAV and its ZIP member information."""

    member_name: str
    path: Path
    size_bytes: int
    duration_seconds: float
    block_count: int


def _build_audio_assembly_archive_entries(
    project_root: Path,
    manifest: dict[str, object],
    cancel_requested,
) -> tuple[list[archive_writer.ArchiveEntry], tuple[int, int] | None]:
    """Build an archive inventory from usable generated Assembly WAVs."""
    report = _load_assembly_report(project_root)
    items: list[_AssemblyWav] = []
    used_names: set[str] = set()
    for output, audio_path in _assembly_candidates(project_root, report):
        operation_runtime_service.raise_if_cancelled(cancel_requested)
        measurements = _measure_assembly_wav(audio_path)
        if measurements is None:
            continue
        reported_name = Path(str(output.get("file_name") or "")).stem
        source_file_name = f"{reported_name or audio_path.stem}.wav"
        file_name = _unique_archive_file_name(source_file_name, used_names)
        block_count = output.get("block_count")
        items.append(_AssemblyWav(
            f"audio_assembly/{file_name}", audio_path, *measurements,
            block_count if type(block_count) is int else 0,
        ))
    if not items:
        raise ValueError("Audio Assembly has no usable generated WAV files to export.")
    planned_count = _assembly_planned_count(report)
    partial = _assembly_is_partial(report, _operation_is_completed(manifest, "audio_assembly"), len(items))
    entries: list[tuple[str, Path | None, str | None]] = [(item.member_name, item.path, None) for item in items]
    entries.append((
        "audio_assembly/audio_assembly_manifest.txt",
        None,
        _build_audio_assembly_manifest_text(project_root, manifest, report, items, partial, planned_count),
    ))
    return entries, (len(items), planned_count) if partial else None


def _measure_assembly_wav(path: Path) -> tuple[int, float] | None:
    """Measure a supported WAV only if its declared frames are present."""
    try:
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getsampwidth() not in audio_assembly_wav.SUPPORTED_SAMPLE_WIDTHS
                or not audio_blocks_artifact_service.has_complete_frames(audio)
            ):
                return None
            return path.stat().st_size, audio.getnframes() / audio.getframerate()
    except (OSError, EOFError, wave.Error):
        return None


def _narrator_voice_archive_items(project_root: Path) -> list[tuple[dict[str, object], Path, dict[str, object]]]:
    """
    @brief      Collect narrator profiles that have an exportable sample WAV.
    @param[in]  project_root Active project root folder.
    @return     Ordered narrator profile, audio path, and metadata tuples.
    @exception  None
    """
    items: list[tuple[dict[str, object], Path, dict[str, object]]] = []
    document_path = try_resolve_project_relative_path(project_root, config.NARRATOR_VOICE_FILE_NAME)
    if document_path is None or not document_path.is_file():
        return items
    for profile in narrator_definition_service.load_profiles(project_root):
        profile_id = str(profile.get("profile_id", "")).strip()
        metadata = profile.get("sample")
        audio_path, _metadata_path = narrator_definition_service.profile_sample_paths(project_root, profile_id)
        if (
            profile_id
            and isinstance(metadata, dict)
            and _is_path_inside_project(project_root, audio_path)
            and audio_path.is_file()
        ):
            items.append((profile, audio_path, metadata))
    return items


def _character_voice_archive_items(project_root: Path) -> list[tuple[dict[str, object], Path, dict[str, object]]]:
    """
    @brief      Collect character voice targets that have an exportable sample WAV.
    @param[in]  project_root Active project root folder.
    @return     Ordered character target, audio path, and metadata tuples.
    @exception  None
    """
    items: list[tuple[dict[str, object], Path, dict[str, object]]] = []
    document_path = try_resolve_project_relative_path(project_root, config.CHARACTER_VOICES_TARGETS_FILE_NAME)
    if document_path is None or not document_path.is_file():
        return items
    targets = character_voices_service.load_voice_plan(project_root, strict=True)
    for target in targets:
        if str(target.get("target_kind", "")).strip() != character_voices_service.TARGET_KIND_CHARACTER:
            continue
        target_id = str(target.get("target_id", "")).strip()
        metadata = target.get("sample_metadata")
        if not target_id or not isinstance(metadata, dict):
            continue
        audio_reference = target.get("sample_audio_path")
        if not audio_reference:
            canonical_path, _metadata_path = character_voices_service.target_sample_paths(
                project_root, target_id, targets
            )
            audio_reference = canonical_path.relative_to(project_root).as_posix()
        audio_path = try_resolve_project_relative_path(project_root, audio_reference)
        if audio_path is not None and audio_path.is_file():
            items.append((target, audio_path, metadata))
    return items


def _load_assembly_report(project_root: Path) -> dict[str, object]:
    """Load the report only from its project-local location."""
    path = try_resolve_project_relative_path(project_root, config.AUDIO_ASSEMBLY_REPORT_FILE_NAME)
    if path is None:
        raise ValueError("Audio Assembly report is outside the project folder.")
    if not path.is_file():
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("Audio Assembly report must be a JSON object.")
    return report


def _assembly_candidates(project_root: Path, report: dict[str, object]) -> list[tuple[dict[str, object], Path]]:
    """Select distinct, project-local WAV paths reported as generated."""
    outputs = report.get("outputs", [])
    if not isinstance(outputs, list):
        raise ValueError("Invalid Audio Assembly output list.")
    items: list[tuple[dict[str, object], Path]] = []
    seen: set[Path] = set()
    for output in outputs:
        if not isinstance(output, dict) or output.get("generated") is not True:
            continue
        audio_path = try_resolve_project_relative_path(project_root, output.get("audio_relative_path"))
        if audio_path is None or audio_path.suffix.lower() != ".wav" or audio_path in seen or not audio_path.is_file():
            continue
        seen.add(audio_path)
        items.append((output, audio_path))
    return items


def _assembly_planned_count(report: dict[str, object]) -> int:
    """Count planned WAVs, falling back to listed records when needed."""
    outputs = report.get("outputs")
    output_count = len(outputs) if isinstance(outputs, list) else 0
    count = report.get("planned_output_count")
    return max(count, output_count) if type(count) is int else output_count


def _assembly_is_partial(report: dict[str, object], completed: bool, exported_count: int) -> bool:
    """Identify unfinished Assembly runs and omissions from the archive."""
    operation_status = report.get("operation_status")
    stage_status = report.get("audio_assembly_stage_status")
    report_completed = operation_status == "completed" if operation_status is not None else completed
    return (
        not report_completed
        or (stage_status is not None and stage_status != audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED)
        or exported_count < _assembly_planned_count(report)
    )


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
    report: dict[str, object],
    items: list[_AssemblyWav],
    partial: bool,
    planned_count: int,
) -> str:
    """Render the Assembly manifest using the actual archive member inventory."""
    settings = audio_assembly_service.normalize_audio_assembly_settings(
        report.get("settings", manifest.get("audio_assembly_settings"))
    )
    fields = project_export_text_service.header_fields(manifest, _EXPORT_KIND_LABELS[EXPORT_KIND_AUDIO_ASSEMBLY])
    lines = [
        "Audio Assembly Export",
        "=====================",
        "",
        *project_export_text_service.render_txt_fields(fields),
        "",
        f"Export Status: {'Partial' if partial else 'Complete'}",
        f"Exported WAVs: {len(items)}/{planned_count}",
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
    for item in items:
        total_size += item.size_bytes
        total_duration += item.duration_seconds
        lines.extend(
            [
                f"- {item.member_name}",
                f"  Project Path: {item.path.relative_to(project_root.resolve())}",
                f"  Duration: {_format_seconds(item.duration_seconds)}",
                f"  Size: {item.size_bytes} bytes",
                f"  Audio Blocks: {item.block_count}",
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
    """
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        return False
    operation = operations.get(operation_kind)
    return isinstance(operation, dict) and str(operation.get("status", "")).strip() == "completed"


def _unique_archive_stem(value: object, used_names: set[str]) -> str:
    """
    @brief      Build one unique archive-safe file stem.
    @param[in]  value Candidate display name.
    @param[in]  used_names Case-folded names already emitted.
    @return     Unique archive file stem.
    @exception  None
    """
    base_name = safe_file_stem(str(value or "AudioMancer"))
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
    """
    file_name = Path(str(value or "audio.wav")).name
    suffix = Path(file_name).suffix or ".wav"
    stem = safe_file_stem(Path(file_name).stem or "audio")
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
    """
    total_seconds = max(0, int(round(duration_seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _validate_export_kind(export_kind: str) -> None:
    """
    @brief      Validate one export kind token.
    @param[in]  export_kind Candidate export kind.
    @return     None.
    @exception  ValueError Raised when the export kind is unsupported.
    """
    if export_kind not in EXPORT_KIND_OPTIONS:
        raise ValueError(f"Unsupported export kind: {export_kind}")


def _validate_export_format(export_format: str) -> None:
    """
    @brief      Validate one export format token.
    @param[in]  export_format Candidate export format.
    @return     None.
    @exception  ValueError Raised when the export format is unsupported.
    """
    if export_format not in EXPORT_FORMAT_OPTIONS:
        raise ValueError(f"Unsupported export format: {export_format}")


# END OF FILE
