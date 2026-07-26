#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file workflow_impact_service.py
@brief V2 workflow impact helpers for selective downstream preservation.
@details Defines shared workflow dependency policy, stable identity rules,
         reset summaries, manifest refresh helpers, and safe generated-artifact
         deletion helpers used by staged v2 downstream invalidation work.
@author Eng. Dan Dumitru Pasare
@date 2026-05-04
@version 0.1.3
"""

# IMPORTS

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from audiomancer import config
from audiomancer.services import operation_runtime_service, project_workspace_service
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.time_service import utc_now_iso

# CONSTANTS

# @brief Component logger used for shared workflow-impact mutations.
_WORKFLOW_IMPACT_LOGGER = get_component_logger("operation_runtime")

# @brief Canonical operation order used by the v2 workflow-impact layer.
WORKFLOW_OPERATION_ORDER = config.WORKFLOW_OPERATION_ORDER

# @brief Workflow stage promoted by each completed operation.
OPERATION_STAGE_BY_KIND = config.OPERATION_STAGE_BY_KIND

# @brief Stable identity fields that must survive local v2 edit operations.
STABLE_IDENTITY_FIELDS = frozenset(("chunk_id", "speech_block_id", "voice_target_id"))

# @brief Generated-audio folder holding artifacts derived from speech_block_id.
_GENERATED_AUDIO_FOLDER_NAME = config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME


# DATA MODELS / TYPEDEFINITIONS


@dataclass(frozen=True)
class ArtifactDeletionSummary:
    """
    @brief      Summarize one safe generated-artifact deletion pass.
    @details    Paths are project-relative where possible and absolute only when
                the helper rejected an unsafe persisted path.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """

    deleted_paths: tuple[str, ...] = ()
    missing_paths: tuple[str, ...] = ()
    skipped_paths: tuple[str, ...] = ()
    preserved_paths: tuple[str, ...] = ()

    @property
    def deleted_count(self) -> int:
        """
        @brief      Return the number of deleted files.
        @return     Deleted file count.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        return len(self.deleted_paths)

    def as_dict(self) -> dict[str, object]:
        """
        @brief      Convert the deletion summary into a JSON-ready dictionary.
        @return     JSON-ready deletion summary.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        return {
            "deleted_paths": list(self.deleted_paths),
            "missing_paths": list(self.missing_paths),
            "skipped_paths": list(self.skipped_paths),
            "preserved_paths": list(self.preserved_paths),
            "deleted_count": self.deleted_count,
        }


@dataclass(frozen=True)
class WorkflowImpactSummary:
    """
    @brief      Describe one workflow reset or selective invalidation action.
    @details    This summary is intentionally UI-neutral. Controllers can use it
                to build localized confirmation text without owning reset policy.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """

    source_operation_kind: str
    impact_kind: str
    reason: str
    reset_operation_kinds: tuple[str, ...] = ()
    preserved_operation_kinds: tuple[str, ...] = ()
    affected_chunk_ids: tuple[str, ...] = ()
    affected_speech_block_ids: tuple[str, ...] = ()
    affected_voice_target_ids: tuple[str, ...] = ()
    audio_assembly_reset: bool = False
    artifact_deletion: ArtifactDeletionSummary = field(default_factory=ArtifactDeletionSummary)
    updated_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, object]:
        """
        @brief      Convert the impact summary into a JSON-ready dictionary.
        @return     JSON-ready impact summary.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-04
        @version    0.1.0
        """
        return {
            "source_operation_kind": self.source_operation_kind,
            "impact_kind": self.impact_kind,
            "reason": self.reason,
            "reset_operation_kinds": list(self.reset_operation_kinds),
            "preserved_operation_kinds": list(self.preserved_operation_kinds),
            "affected_chunk_ids": list(self.affected_chunk_ids),
            "affected_speech_block_ids": list(self.affected_speech_block_ids),
            "affected_voice_target_ids": list(self.affected_voice_target_ids),
            "audio_assembly_reset": self.audio_assembly_reset,
            "artifact_deletion": self.artifact_deletion.as_dict(),
            "updated_at": self.updated_at,
        }


# PUBLIC API


def operation_index(operation_kind: str) -> int:
    """
    @brief      Return the workflow index for one operation kind.
    @param[in]  operation_kind Stable workflow operation token.
    @return     Zero-based workflow operation index.
    @exception  ValueError Raised when the operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    normalized_kind = str(operation_kind).strip()
    if normalized_kind not in WORKFLOW_OPERATION_ORDER:
        raise ValueError(f"Unsupported operation kind: {operation_kind}")
    return WORKFLOW_OPERATION_ORDER.index(normalized_kind)


def downstream_operation_kinds(operation_kind: str, include_current: bool = False) -> tuple[str, ...]:
    """
    @brief      Return ordered downstream operation kinds for v2 impact planning.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  include_current True to include the selected operation.
    @return     Ordered operation-kind tuple.
    @exception  ValueError Raised when the operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    start_index = operation_index(operation_kind)
    if not include_current:
        start_index += 1
    return WORKFLOW_OPERATION_ORDER[start_index:]


def stable_identity_fields() -> tuple[str, ...]:
    """
    @brief      Return stable persisted identity fields for local v2 edits.
    @return     Ordered stable identity field tuple.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    return tuple(sorted(STABLE_IDENTITY_FIELDS))


def is_stable_identity_field(field_name: str) -> bool:
    """
    @brief      Return whether one persisted field is a stable v2 identity.
    @param[in]  field_name Candidate field name.
    @return     True when the field is a stable identity field.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    return str(field_name).strip() in STABLE_IDENTITY_FIELDS


def resequence_records(records: Iterable[Mapping[str, object]], start_index: int = 1) -> list[dict[str, object]]:
    """
    @brief      Return copied records with updated `sequence_index` values only.
    @param[in]  records Ordered persisted records.
    @param[in]  start_index First sequence index to assign.
    @return     Copied records with stable identities preserved.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    resolved_start_index = max(int(start_index), 0)
    resequenced_records: list[dict[str, object]] = []
    for offset, record in enumerate(records):
        copied_record = dict(record)
        copied_record["sequence_index"] = resolved_start_index + offset
        resequenced_records.append(copied_record)
    return resequenced_records


def build_full_reset_impact_summary(
    operation_kind: str,
    *,
    include_current: bool = True,
    preserve_operation_kinds: Iterable[str] | None = None,
    reason: str = "",
) -> WorkflowImpactSummary:
    """
    @brief      Build a summary for a broad operation reset.
    @param[in]  operation_kind Selected workflow operation token.
    @param[in]  include_current True to reset the selected operation too.
    @param[in]  preserve_operation_kinds Operation kinds excluded from reset.
    @param[in]  reason Operator-readable reset reason.
    @return     UI-neutral impact summary.
    @exception  ValueError Raised when the operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    preserved_kinds = _normalize_operation_kinds(preserve_operation_kinds)
    candidate_kinds = downstream_operation_kinds(operation_kind, include_current=include_current)
    reset_kinds = tuple(candidate_kind for candidate_kind in candidate_kinds if candidate_kind not in preserved_kinds)
    return WorkflowImpactSummary(
        source_operation_kind=str(operation_kind).strip(),
        impact_kind="full_reset",
        reason=str(reason).strip(),
        reset_operation_kinds=reset_kinds,
        preserved_operation_kinds=preserved_kinds,
        audio_assembly_reset="audio_assembly" in reset_kinds,
    )


def apply_full_operation_reset(
    project_root: str | Path,
    operation_kind: str,
    *,
    include_current: bool = True,
    preserve_operation_kinds: Iterable[str] | None = None,
    reason: str = "",
) -> WorkflowImpactSummary:
    """
    @brief      Apply an existing broad reset through the v2 impact wrapper.
    @param[in]  project_root Active project root folder.
    @param[in]  operation_kind Selected workflow operation token.
    @param[in]  include_current True to reset the selected operation too.
    @param[in]  preserve_operation_kinds Operation kinds excluded from reset.
    @param[in]  reason Operator-readable reset reason.
    @return     UI-neutral impact summary.
    @exception  ValueError Raised when the operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    summary = build_full_reset_impact_summary(
        operation_kind,
        include_current=include_current,
        preserve_operation_kinds=preserve_operation_kinds,
        reason=reason,
    )
    operation_runtime_service.reset_operation_data(
        project_root,
        operation_kind,
        include_current=include_current,
        preserve_operation_kinds=preserve_operation_kinds,
    )
    refresh_manifest_from_artifacts(project_root)
    return summary


def build_selective_invalidation_summary(
    source_operation_kind: str,
    *,
    reason: str = "",
    affected_chunk_ids: Iterable[str] | None = None,
    affected_speech_block_ids: Iterable[str] | None = None,
    affected_voice_target_ids: Iterable[str] | None = None,
    reset_operation_kinds: Iterable[str] | None = None,
    audio_assembly_reset: bool = False,
    artifact_deletion: ArtifactDeletionSummary | None = None,
) -> WorkflowImpactSummary:
    """
    @brief      Build a summary for one selective v2 invalidation.
    @param[in]  source_operation_kind Operation that caused the impact.
    @param[in]  reason Operator-readable impact reason.
    @param[in]  affected_chunk_ids Exact affected chunk identifiers.
    @param[in]  affected_speech_block_ids Exact affected Speech Block identifiers.
    @param[in]  affected_voice_target_ids Exact affected voice target identifiers.
    @param[in]  reset_operation_kinds Operation data reset by this selective action.
    @param[in]  audio_assembly_reset True when Audio Assembly is reset.
    @param[in]  artifact_deletion Optional generated-artifact deletion summary.
    @return     UI-neutral impact summary.
    @exception  ValueError Raised when the source operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    operation_index(source_operation_kind)
    return WorkflowImpactSummary(
        source_operation_kind=str(source_operation_kind).strip(),
        impact_kind="selective_invalidation",
        reason=str(reason).strip(),
        reset_operation_kinds=_normalize_operation_kinds(reset_operation_kinds),
        affected_chunk_ids=_normalize_identity_tuple(affected_chunk_ids),
        affected_speech_block_ids=_normalize_identity_tuple(affected_speech_block_ids),
        affected_voice_target_ids=_normalize_identity_tuple(affected_voice_target_ids),
        audio_assembly_reset=bool(audio_assembly_reset),
        artifact_deletion=artifact_deletion or ArtifactDeletionSummary(),
    )


def build_impact_metadata(summary: WorkflowImpactSummary) -> dict[str, object]:
    """
    @brief      Build a persisted metadata note for one workflow impact.
    @param[in]  summary Impact summary to persist.
    @return     JSON-ready metadata note.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    payload = summary.as_dict()
    return {
        "workflow_impact_version": 2,
        "source_operation_kind": payload["source_operation_kind"],
        "impact_kind": payload["impact_kind"],
        "reason": payload["reason"],
        "affected_chunk_ids": payload["affected_chunk_ids"],
        "affected_speech_block_ids": payload["affected_speech_block_ids"],
        "affected_voice_target_ids": payload["affected_voice_target_ids"],
        "reset_operation_kinds": payload["reset_operation_kinds"],
        "preserved_operation_kinds": payload["preserved_operation_kinds"],
        "audio_assembly_reset": payload["audio_assembly_reset"],
        "artifact_deletion": payload["artifact_deletion"],
        "updated_at": payload["updated_at"],
    }


def delete_audio_block_artifacts(
    project_root: str | Path,
    audio_blocks: Iterable[Mapping[str, object]],
    *,
    chunk_ids: Iterable[str] | None = None,
    speech_block_ids: Iterable[str] | None = None,
    voice_target_ids: Iterable[str] | None = None,
    collect_preserved_paths: bool = True,
) -> ArtifactDeletionSummary:
    """
    @brief      Delete generated Audio Blocks files for exact affected IDs.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Persisted Audio Blocks payloads to inspect.
    @param[in]  chunk_ids Optional affected chunk identifiers.
    @param[in]  speech_block_ids Optional affected Speech Block identifiers.
    @param[in]  voice_target_ids Optional affected voice target identifiers.
    @param[in]  collect_preserved_paths True to check and report unaffected generated files.
    @return     Deletion summary with deleted, missing, skipped, and optionally preserved paths.
    @exception  ValueError Raised when no exact affected IDs are provided.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.2.0
    """
    normalized_chunk_ids = set(_normalize_identity_tuple(chunk_ids))
    normalized_speech_block_ids = set(_normalize_identity_tuple(speech_block_ids))
    normalized_voice_target_ids = set(_normalize_identity_tuple(voice_target_ids))
    if not (normalized_chunk_ids or normalized_speech_block_ids or normalized_voice_target_ids):
        raise ValueError("Selective Audio Blocks artifact deletion requires at least one affected ID.")

    deleted_paths: list[str] = []
    missing_paths: list[str] = []
    skipped_paths: list[str] = []
    preserved_paths: list[str] = []
    seen_paths: set[str] = set()
    resolved_project_root = Path(project_root)

    for audio_block in audio_blocks:
        should_delete = _audio_block_matches(
            audio_block,
            chunk_ids=normalized_chunk_ids,
            speech_block_ids=normalized_speech_block_ids,
            voice_target_ids=normalized_voice_target_ids,
        )
        if not should_delete and not collect_preserved_paths:
            continue
        for relative_path in _iter_audio_block_artifact_paths(audio_block):
            _collect_or_delete_artifact_path(
                resolved_project_root,
                relative_path,
                should_delete=should_delete,
                deleted_paths=deleted_paths,
                missing_paths=missing_paths,
                skipped_paths=skipped_paths,
                preserved_paths=preserved_paths,
                seen_paths=seen_paths,
            )

    return ArtifactDeletionSummary(
        deleted_paths=tuple(deleted_paths),
        missing_paths=tuple(missing_paths),
        skipped_paths=tuple(skipped_paths),
        preserved_paths=tuple(preserved_paths),
    )


def reset_audio_assembly_outputs(project_root: str | Path) -> ArtifactDeletionSummary:
    """
    @brief      Delete only Audio Assembly state, report, and audiobook outputs.
    @param[in]  project_root Active project root folder.
    @return     Deletion summary for assembly artifacts.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.1
    """
    resolved_project_root = Path(project_root)
    deleted_paths: list[str] = []
    missing_paths: list[str] = []
    skipped_paths: list[str] = []
    preserved_paths: list[str] = []
    seen_paths: set[str] = set()

    for file_name in (config.AUDIO_ASSEMBLY_REPORT_FILE_NAME, config.AUDIO_ASSEMBLY_STATE_FILE_NAME):
        _collect_or_delete_artifact_path(
            resolved_project_root,
            file_name,
            should_delete=True,
            deleted_paths=deleted_paths,
            missing_paths=missing_paths,
            skipped_paths=skipped_paths,
            preserved_paths=preserved_paths,
            seen_paths=seen_paths,
        )

    audiobook_root = resolved_project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME
    if audiobook_root.is_dir():
        for child_path in sorted(audiobook_root.rglob("*")):
            if not child_path.is_file():
                continue
            _collect_or_delete_resolved_path(
                resolved_project_root,
                child_path,
                deleted_paths=deleted_paths,
                missing_paths=missing_paths,
                skipped_paths=skipped_paths,
                seen_paths=seen_paths,
            )

    summary = ArtifactDeletionSummary(
        deleted_paths=tuple(deleted_paths),
        missing_paths=tuple(missing_paths),
        skipped_paths=tuple(skipped_paths),
        preserved_paths=tuple(preserved_paths),
    )
    _WORKFLOW_IMPACT_LOGGER.info(
        "Reset Audio Assembly outputs: deleted=%s missing=%s skipped=%s",
        summary.deleted_count,
        len(summary.missing_paths),
        len(summary.skipped_paths),
    )
    return summary


def refresh_manifest_from_artifacts(project_root: str | Path) -> dict[str, object]:
    """
    @brief      Reconcile project manifest metadata from persisted artifacts.
    @param[in]  project_root Active project root folder.
    @return     Current or repaired project manifest payload.
    @exception  ValueError Raised when project validation reports a non-metadata repair.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    validation_result = project_workspace_service.validate_project(project_root)
    status = str(validation_result.get("status", "")).strip()
    if status == "ok":
        return dict(validation_result["manifest"])
    if status != "repair_required" or not bool(validation_result.get("metadata_only", False)):
        raise ValueError("Project manifest could not be refreshed from local artifacts.")
    normalized_manifest = validation_result.get("normalized_manifest")
    if not isinstance(normalized_manifest, dict):
        raise ValueError("Project manifest repair did not include normalized metadata.")
    project_workspace_service.save_manifest(normalized_manifest, project_root)
    return project_workspace_service.load_manifest(project_root)


# LOCAL HELPERS


def _normalize_operation_kinds(operation_kinds: Iterable[str] | None) -> tuple[str, ...]:
    """
    @brief      Normalize optional operation-kind collections.
    @param[in]  operation_kinds Candidate operation-kind iterable.
    @return     Ordered deduplicated operation-kind tuple.
    @exception  ValueError Raised when any operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    if operation_kinds is None:
        return ()
    normalized_kinds: list[str] = []
    for operation_kind in operation_kinds:
        normalized_kind = str(operation_kind).strip()
        if not normalized_kind or normalized_kind in normalized_kinds:
            continue
        operation_index(normalized_kind)
        normalized_kinds.append(normalized_kind)
    return tuple(normalized_kinds)


def _normalize_identity_tuple(values: Iterable[str] | None) -> tuple[str, ...]:
    """
    @brief      Normalize persisted identity values while preserving input order.
    @param[in]  values Candidate identity values.
    @return     Ordered deduplicated identity tuple.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    if values is None:
        return ()
    normalized_values: list[str] = []
    for value in values:
        normalized_value = str(value).strip()
        if normalized_value and normalized_value not in normalized_values:
            normalized_values.append(normalized_value)
    return tuple(normalized_values)


def _audio_block_matches(
    audio_block: Mapping[str, object],
    *,
    chunk_ids: set[str],
    speech_block_ids: set[str],
    voice_target_ids: set[str],
) -> bool:
    """
    @brief      Return whether one Audio Block matches any affected ID set.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @param[in]  chunk_ids Affected chunk identifiers.
    @param[in]  speech_block_ids Affected Speech Block identifiers.
    @param[in]  voice_target_ids Affected voice target identifiers.
    @return     True when the block should have generated artifacts deleted.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    return (
        str(audio_block.get("chunk_id", "")).strip() in chunk_ids
        or str(audio_block.get("speech_block_id", "")).strip() in speech_block_ids
        or str(audio_block.get("voice_target_id", "")).strip() in voice_target_ids
    )


def _iter_audio_block_artifact_paths(audio_block: Mapping[str, object]) -> tuple[object, ...]:
    """
    @brief      Return persisted generated-artifact paths from one Audio Block.
    @param[in]  audio_block Candidate Audio Blocks payload.
    @return     Ordered artifact path tuple.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    from audiomancer.services import audio_blocks_artifact_service

    speech_block_id = str(audio_block.get("speech_block_id", "")).strip()
    if not speech_block_id:
        return ()
    file_stem = audio_blocks_artifact_service.audio_artifact_file_stem(speech_block_id)
    paths: list[object] = [f"{_GENERATED_AUDIO_FOLDER_NAME}/{file_stem}.wav"]
    split_part_count = audio_block.get("split_part_count")
    if isinstance(split_part_count, int) and split_part_count > 1:
        paths.extend(
            f"{_GENERATED_AUDIO_FOLDER_NAME}/parts/{file_stem}_part{part_index + 1:03d}.wav"
            for part_index in range(split_part_count)
        )
    return tuple(paths)


def _collect_or_delete_artifact_path(
    project_root: Path,
    relative_path: object,
    *,
    should_delete: bool,
    deleted_paths: list[str],
    missing_paths: list[str],
    skipped_paths: list[str],
    preserved_paths: list[str],
    seen_paths: set[str],
) -> None:
    """
    @brief      Resolve and collect or delete one persisted project-relative path.
    @param[in]  project_root Active project root folder.
    @param[in]  relative_path Candidate persisted project-relative path.
    @param[in]  should_delete True when the resolved file should be deleted.
    @param[in,out] deleted_paths Deleted path labels.
    @param[in,out] missing_paths Missing path labels.
    @param[in,out] skipped_paths Unsafe skipped path labels.
    @param[in,out] preserved_paths Preserved path labels.
    @param[in,out] seen_paths Deduplication set.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    path_text = str(relative_path or "").strip()
    if not path_text:
        return
    seen_paths.add(path_text)
    artifact_path = operation_runtime_service.try_resolve_project_relative_path(project_root, path_text)
    if artifact_path is None:
        if path_text not in skipped_paths:
            skipped_paths.append(path_text)
        return
    seen_paths.discard(path_text)
    if should_delete:
        _collect_or_delete_resolved_path(
            project_root,
            artifact_path,
            deleted_paths=deleted_paths,
            missing_paths=missing_paths,
            skipped_paths=skipped_paths,
            seen_paths=seen_paths,
        )
        return
    if artifact_path.is_file():
        relative_label = operation_runtime_service.relative_to_project(project_root, artifact_path)
        if relative_label in seen_paths:
            return
        seen_paths.add(relative_label)
        preserved_paths.append(relative_label)


def _collect_or_delete_resolved_path(
    project_root: Path,
    artifact_path: Path,
    *,
    deleted_paths: list[str],
    missing_paths: list[str],
    skipped_paths: list[str],
    seen_paths: set[str],
) -> None:
    """
    @brief      Delete one already resolved project-local file.
    @param[in]  project_root Active project root folder.
    @param[in]  artifact_path Resolved artifact path.
    @param[in,out] deleted_paths Deleted path labels.
    @param[in,out] missing_paths Missing path labels.
    @param[in,out] skipped_paths Unsafe skipped path labels.
    @param[in,out] seen_paths Deduplication set.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    if not operation_runtime_service.is_path_inside_project(project_root, artifact_path):
        skipped_paths.append(str(artifact_path))
        return
    relative_label = operation_runtime_service.relative_to_project(project_root, artifact_path)
    if relative_label in seen_paths:
        return
    seen_paths.add(relative_label)
    if artifact_path.is_file():
        artifact_path.unlink()
        deleted_paths.append(relative_label)
        return
    missing_paths.append(relative_label)


# END OF FILE
