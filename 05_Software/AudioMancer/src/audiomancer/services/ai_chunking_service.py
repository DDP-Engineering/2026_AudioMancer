#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_chunking_service.py
@brief AI-assisted text chunking helpers for AudioMancer.
@details Consumes canonical cleaned text, asks one configured AI profile to
         decide semantic chunk boundaries over ordered paragraphs, checkpoints
         validated descriptor prefixes in one strict `chunks_text.json`, and keeps AI
         transaction logs separate from the durable Chunking contract.
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.chunking import descriptors, materialization, planning
from audiomancer.services import (
    chunking_ai_service,
    chunking_document_service,
    chunking_input_service,
    chunking_publication_service,
    prompt_template_service,
    token_usage_service,
)
from audiomancer.services import (
    llm_provider_service as llm_provider_service,
)
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    build_operation_output_path,
    raise_if_cancelled,
)
from audiomancer.services.operation_runtime_service import (
    emit_progress_update as _emit_progress,
)
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

# @brief Component logger used by the AI-assisted chunking workflow.
_AI_CHUNKING_LOGGER = get_component_logger("ai_chunking")

# @brief Canonical chunk-record payload type persisted for downstream workflow steps.
ChunkPayload = dict[str, object]

# @brief Persisted AI chunking report payload type.
ChunkingReportPayload = dict[str, object]

# @brief Persisted AI chunking operation-state payload type.
OperationStatePayload = dict[str, object]
BudgetMetadataPayload = dict[str, int]


# PUBLIC API


@trace_function(_AI_CHUNKING_LOGGER)
def chunk_text(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object],
    semantic_strategy: str,
    progress_callback=None,
    cancel_requested=None,
    additional_chunking_instructions: str | None = None,
    chunking_context_mode: str | None = None,
    *,
    restart: bool = False,
) -> ChunkingReportPayload:
    """
    @brief      Run AI-assisted chunking for one active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  semantic_strategy Selected semantic strategy token.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  restart Explicitly discard an unfinished checkpoint and start from source.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @param[in]  chunking_context_mode Optional AI chunking context mode token.
    @return     Chunking report payload for the persisted AI chunking artifacts.
    @exception  FileNotFoundError Raised when the cleaned input is missing.
    @exception  ValueError Raised on missing profile data or unusable cleaned text.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @exception  IncompatibleChunkingDocumentError Raised when cleaned text changed; reset Chunking first.
    """
    resolved_project_root = Path(project_root)
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        raise ValueError("No imported source is available for AI-assisted chunking.")

    cleaned_relative_path = config.CLEANED_TEXT_FILE_NAME

    profile_id = str(ai_profile_payload.get("id", "")).strip()
    model_name = str(ai_profile_payload.get("model_name", "")).strip()
    base_url = str(ai_profile_payload.get("base_url", "")).strip()
    if not profile_id or not model_name or not base_url:
        raise ValueError("AI-assisted chunking requires a valid enabled AI profile.")

    if semantic_strategy not in config.AI_CHUNKING_STRATEGY_OPTIONS:
        raise ValueError("AI-assisted chunking requires a valid semantic strategy.")

    cleaned_path = resolved_project_root / cleaned_relative_path
    if not cleaned_path.is_file():
        raise FileNotFoundError("AI-assisted chunking requires cleaned text first.")

    input_text = cleaned_path.read_text(encoding="utf-8")
    paragraph_records = _build_paragraph_records(input_text, resolved_project_root)
    if not paragraph_records:
        raise ValueError("Cleaned text does not contain any paragraphs for AI chunking.")
    if not any(_is_narratable_record(record) for record in paragraph_records):
        raise ValueError("Cleaned text does not contain any narratable paragraphs.")

    _ = source_document
    existing_document = None if restart else chunking_document_service.load_checkpoint(resolved_project_root)
    committed_chunks: list[ChunkPayload] = []
    next_paragraph = 1
    context_window_fallback_count = 0
    token_usage = chunking_document_service.empty_token_usage()
    if existing_document is not None and existing_document["status"] in chunking_document_service.RESUMABLE_STATUSES:
        if existing_document["mode"] != "ai_assisted":
            raise chunking_document_service.IncompatibleChunkingDocumentError(
                "Chunking data is incompatible. Use Reset Chunking before continuing."
            )
        if existing_document["source_fingerprint"] != chunking_document_service.source_fingerprint(input_text):
            raise chunking_document_service.IncompatibleChunkingDocumentError(
                "Cleaned text changed. Use Reset Chunking before continuing."
            )
        semantic_strategy = str(existing_document["semantic_strategy"])
        additional_chunking_instructions = str(existing_document["additional_chunking_instructions"])
        committed_chunks = list(existing_document["chunks"])
        next_paragraph = int(existing_document["next_paragraph"])
        context_window_fallback_count = int(existing_document["context_window_fallback_count"])
        token_usage = dict(existing_document["token_usage"])
    else:
        additional_chunking_instructions = _normalized_additional_chunking_instructions(
            additional_chunking_instructions
        )

    plan_identity = materialization.plan_fingerprint(paragraph_records)
    resume_warnings = []
    if existing_document is not None and existing_document["status"] in chunking_document_service.RESUMABLE_STATUSES:
        if existing_document["plan_fingerprint"] != plan_identity:
            raise ValueError("Cleanup paragraph plan changed. Restart Chunking before continuing.")
        materialization.validate_coverage(committed_chunks, paragraph_records, next_paragraph - 1)
        resume_warnings = list(existing_document["warnings"])

    prompt_template_service.validate_required_prompts(["text_chunking_system", "text_chunking_user"])
    system_prompt = prompt_template_service.render_prompt(
        "text_chunking_system",
        {"strategy": semantic_strategy},
    )
    budget_metadata = _build_budget_metadata(
        ai_profile_payload,
        semantic_strategy,
        system_prompt,
        additional_chunking_instructions,
        chunking_context_mode=chunking_context_mode,
    )
    log_path = _build_ai_log_path(resolved_project_root, _utc_now_iso())
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    request_identity = chunking_ai_service.request_fingerprint(
        ai_profile_payload,
        system_prompt,
        prompt_template_service.load_prompt("text_chunking_user"),
        semantic_strategy,
        additional_chunking_instructions,
        budget_metadata,
    )
    policy_changed = bool(
        existing_document is not None
        and existing_document["status"] in chunking_document_service.RESUMABLE_STATUSES
        and existing_document["request_fingerprint"] != request_identity
    )
    if policy_changed:
        resume_warnings.append(
            "AI request policy changed; the verified prefix was retained "
            "and only remaining paragraphs use the new policy."
        )
    paragraph_costs = [_estimate_text_tokens(_build_units_block([record])) for record in paragraph_records]
    total_windows = len(paragraph_records)
    document = chunking_document_service.build_document(
        status="running",
        mode="ai_assisted",
        source_text=input_text,
        chunks=committed_chunks,
        plan_fingerprint=plan_identity,
        request_fingerprint=request_identity,
        warnings=resume_warnings,
        semantic_strategy=semantic_strategy,
        additional_chunking_instructions=additional_chunking_instructions,
        token_usage=token_usage,
        next_paragraph=next_paragraph,
        context_window_fallback_count=context_window_fallback_count,
    )
    checkpoint_path = chunking_document_service.write_checkpoint(resolved_project_root, document)
    _emit_progress(
        progress_callback,
        progress_current=next_paragraph - 1,
        progress_total=total_windows,
        message=(
            resume_warnings[-1]
            if policy_changed
            else "Resuming AI-assisted chunking..."
            if committed_chunks
            else "AI-assisted chunking in progress..."
        ),
        token_usage=token_usage,
    )

    try:
        while next_paragraph <= len(paragraph_records):
            raise_if_cancelled(cancel_requested)
            window_payload = planning.next_window(
                paragraph_costs,
                next_paragraph - 1,
                int(budget_metadata["text_budget_tokens"]),
                int(budget_metadata["strategy_paragraph_cap"]),
            )
            window_start_index = int(window_payload["start_index"])
            window_end_index = int(window_payload["end_index"])
            window_records = paragraph_records[window_start_index : window_end_index + 1]
            is_final_window = window_end_index == len(paragraph_records) - 1
            oversized = paragraph_costs[window_start_index] > int(budget_metadata["text_budget_tokens"])
            user_prompt = _render_chunking_user_prompt(
                {
                    "strategy": semantic_strategy,
                    "units_block": _build_units_block(window_records),
                    "additional_chunking_instructions": additional_chunking_instructions,
                },
            )
            if oversized:
                response_result = {"payload": {"chunks": []}}
                warning = (
                    f"Paragraph {window_start_index + 1} exceeds the AI text budget; retained whole "
                    "using deterministic fallback without a model request."
                )
                if warning not in document["warnings"]:
                    document["warnings"].append(warning)
            else:
                try:
                    response_result = chunking_ai_service.request_boundaries(
                        ai_profile_payload,
                        system_prompt,
                        user_prompt,
                        log_path=log_path,
                        log_context={
                            "operation_kind": "chunking",
                            "stage_label": "ai_chunking",
                            "profile_id": profile_id,
                            "semantic_strategy": semantic_strategy,
                            "source_paragraph_start": window_start_index + 1,
                            "source_paragraph_end": window_end_index + 1,
                        },
                        cancel_requested=cancel_requested,
                        response_schema=_build_response_schema(),
                        response_schema_name="text_chunk_descriptors",
                    )
                except OperationCancelledError as error:
                    raise OperationCancelledError(
                        "AI-assisted chunking cancelled while waiting for the model response."
                    ) from error
            response_payload = response_result.get("payload")
            if not isinstance(response_payload, dict):
                raise ValueError("AI chunking response must be one JSON object.")
            token_usage = _document_token_usage(
                token_usage_service.merge_token_usage(token_usage, response_result.get("usage"))
            )
            validated_ranges, response_complete = _validate_chunk_descriptor_prefix(
                response_payload,
                paragraph_records,
                window_start_index,
                window_end_index,
            )

            progress_message = "AI-assisted chunking in progress..."
            if validated_ranges:
                _append_chunks_from_ranges(
                    committed_chunks,
                    paragraph_records,
                    validated_ranges,
                )
                next_paragraph = int(validated_ranges[-1]["end_index"]) + 2
                if response_complete and is_final_window and next_paragraph <= len(paragraph_records):
                    _append_chunks_from_ranges(
                        committed_chunks,
                        paragraph_records,
                        [{"start_index": next_paragraph - 1, "end_index": len(paragraph_records) - 1}],
                    )
                    next_paragraph = len(paragraph_records) + 1
                elif not response_complete:
                    progress_message = (
                        "AI chunking accepted a valid descriptor prefix and "
                        f"will retry from paragraph {next_paragraph}."
                    )
            else:
                fallback_ranges = _deterministic_structural_fallback_ranges(
                    paragraph_records,
                    window_start_index,
                    window_end_index,
                )
                _append_chunks_from_ranges(
                    committed_chunks,
                    paragraph_records,
                    fallback_ranges,
                )
                context_window_fallback_count += 1
                next_paragraph = window_end_index + 2
                first_paragraph = window_start_index + 1
                last_paragraph = window_end_index + 1
                if len(fallback_ranges) > 1:
                    progress_message = (
                        "AI chunking returned no valid split for paragraphs "
                        f"{first_paragraph}-{last_paragraph}. AudioMancer used "
                        "a deterministic structural fallback."
                    )
                else:
                    progress_message = (
                        f"AI chunking returned no valid split for paragraphs {first_paragraph}-{last_paragraph}. "
                        "AudioMancer saved this text window as one chunk."
                    )

            if oversized:
                progress_message = warning
            document["chunks"] = committed_chunks
            document["token_usage"] = token_usage
            document["next_paragraph"] = next_paragraph
            document["context_window_fallback_count"] = context_window_fallback_count
            chunking_document_service.write_checkpoint(resolved_project_root, document)
            _emit_progress(
                progress_callback,
                progress_current=next_paragraph - 1,
                progress_total=total_windows,
                message=progress_message,
                token_usage=token_usage,
            )
    except OperationCancelledError:
        document["status"] = "cancelled"
        document["chunks"] = committed_chunks
        document["token_usage"] = token_usage
        document["next_paragraph"] = next_paragraph
        document["context_window_fallback_count"] = context_window_fallback_count
        chunking_document_service.write_checkpoint(resolved_project_root, document)
        raise
    except Exception:
        document["status"] = "failed"
        document["chunks"] = committed_chunks
        document["token_usage"] = token_usage
        document["next_paragraph"] = next_paragraph
        document["context_window_fallback_count"] = context_window_fallback_count
        chunking_document_service.write_checkpoint(resolved_project_root, document)
        raise

    chunks = committed_chunks
    chapter_count = _chapter_count_from_chunks(chunks)
    warnings = list(document["warnings"]) + materialization.build_warnings(chapter_count)
    if context_window_fallback_count:
        window_label = (
            "One text window was"
            if context_window_fallback_count == 1
            else (f"{context_window_fallback_count} text windows were")
        )
        warnings.append(
            f"{window_label} saved as a fallback chunk because AI chunking returned no valid internal split "
            "or a paragraph exceeded the text budget. "
            "Explicit heading and scene-separator boundaries were preserved when available."
        )
    document["status"] = "completed"
    document["chunks"] = chunks
    document["token_usage"] = token_usage
    document["warnings"] = list(dict.fromkeys(warnings))
    document["next_paragraph"] = None
    document["context_window_fallback_count"] = context_window_fallback_count
    try:
        materialization.validate_coverage(chunks, paragraph_records)
        chunking_publication_service.publish_chunks(
            resolved_project_root, document, check_cancelled=lambda: raise_if_cancelled(cancel_requested)
        )
    except Exception as error:
        document["status"] = "cancelled" if isinstance(error, OperationCancelledError) else "failed"
        document["next_paragraph"] = len(paragraph_records) + 1
        try:
            chunking_document_service.write_checkpoint(
                resolved_project_root, document, pending=checkpoint_path.name == config.CHUNKING_PENDING_FILE_NAME
            )
        except (OSError, ValueError):
            _AI_CHUNKING_LOGGER.exception("Could not persist terminal Chunking checkpoint after publication failure")
        raise
    _emit_progress(
        progress_callback,
        progress_current=total_windows,
        progress_total=total_windows,
        message="AI-assisted chunking completed.",
        token_usage=token_usage,
    )
    return chunking_document_service.derive_report(document)


@trace_function(_AI_CHUNKING_LOGGER)
def load_operation_state(project_root: str | Path) -> OperationStatePayload | None:
    """
    @brief      Load one optional AI chunking operation-state payload.
    @param[in]  project_root Active project root folder.
    @return     Persisted chunking operation-state payload or `None`.
    @exception  None
    """
    document = chunking_document_service.load_checkpoint(project_root)
    return None if document is None else chunking_document_service.derive_operation_state(document)


# LOCAL HELPERS


def _build_windows(paragraph_records, budget_metadata):
    """@brief Plan a complete preview using one token estimate per source paragraph."""
    costs = [_estimate_text_tokens(_build_units_block([record])) for record in paragraph_records]
    windows = []
    cursor = 0
    while cursor < len(costs):
        window = planning.next_window(
            costs, cursor, int(budget_metadata["text_budget_tokens"]), int(budget_metadata["strategy_paragraph_cap"])
        )
        windows.append(window)
        cursor = window["end_index"] + 1
    return windows


_build_budget_metadata = chunking_ai_service._build_budget_metadata


_render_chunking_user_prompt = chunking_ai_service._render_chunking_user_prompt


_normalized_additional_chunking_instructions = chunking_ai_service._normalized_additional_chunking_instructions


_append_additional_chunking_instructions = chunking_ai_service._append_additional_chunking_instructions


_estimate_text_tokens = chunking_ai_service._estimate_text_tokens


_build_paragraph_records = chunking_input_service.load_paragraph_records


_build_response_schema = descriptors._build_response_schema


_paragraph_start_anchor = descriptors._paragraph_start_anchor


_normalized_anchor_words = descriptors._normalized_anchor_words


_normalized_complete_anchor = descriptors._normalized_complete_anchor


_start_anchor_matches = descriptors._start_anchor_matches


_validate_chunk_descriptor_prefix = descriptors._validate_chunk_descriptor_prefix


_is_structural_boundary_record = materialization._is_structural_boundary_record


_effective_cleanup_role = materialization._effective_cleanup_role


_deterministic_structural_fallback_ranges = materialization._deterministic_structural_fallback_ranges


_build_units_block = materialization._build_units_block


_build_chunk_from_range = materialization._build_chunk_from_range


_is_narratable_record = materialization._is_narratable_record


_starts_after_scene_separator = materialization._starts_after_scene_separator


_narratable_subranges = materialization._narratable_subranges


_append_chunks_from_ranges = materialization._append_chunks_from_ranges


_merged_warning_flags = materialization._merged_warning_flags


def _chapter_count_from_chunks(chunks: list[ChunkPayload]) -> int:
    """
    @brief      Execute the chapter count from chunks helper.
    @param[in]  chunks Value for `chunks`.
    @return     Helper result.
    """
    chapter_labels: list[str] = []
    for chunk in chunks:
        chapter_label = chunking_document_service.chapter_label_from_text(str(chunk.get("text", "")))
        if chapter_label is not None and (not chapter_labels or chapter_labels[-1] != chapter_label):
            chapter_labels.append(chapter_label)
    return len(chapter_labels)


def _build_ai_log_path(project_root: Path, started_at: str) -> Path:
    """
    @brief      Build the ai log path.
    @param[in]  project_root Active project root folder.
    @param[in]  started_at Value for `started_at`.
    @return     Derived helper result.
    """
    timestamp_token = started_at.replace("-", "").replace(":", "").replace("+", "_").replace(".", "")
    candidate = build_operation_output_path(
        project_root,
        "chunking",
        config.ai_transaction_log_file_name("chunking", timestamp_token),
    )
    suffix = 2
    while candidate.exists():
        candidate = build_operation_output_path(
            project_root,
            "chunking",
            config.ai_transaction_log_file_name("chunking", f"{timestamp_token}_{suffix}"),
        )
        suffix += 1
    return candidate


def _document_token_usage(payload: object) -> dict[str, object]:
    """
    @brief Project provider usage into the strict integer-only document contract.
    @param[in] payload Provider-normalized cumulative usage.
    @return Exact Chunking document usage payload.
    @exception None
    """
    if not isinstance(payload, dict) or not bool(payload.get("usage_available", False)):
        return chunking_document_service.empty_token_usage()
    input_tokens = int(payload.get("input_tokens") or 0)
    output_tokens = int(payload.get("output_tokens") or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "usage_available": True,
    }


# END OF FILE
