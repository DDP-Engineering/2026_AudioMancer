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
@author Eng. Dan Dumitru Pasare
@date 2026-07-29
@version 0.14.0
"""

# IMPORTS

import hashlib
from pathlib import Path
import re
import unicodedata

from audiomancer import config
from audiomancer.services import (
    ai_budget_service,
    chunking_document_service,
    cleanup_text_analysis_service,
    deterministic_chunking_service,
    llm_provider_service,
    project_workspace_service,
    prompt_template_service,
    token_usage_service,
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

# @brief Maximum number of paragraph-prefix words requested from the model.
_ANCHOR_WORD_LIMIT = 8

# @brief Consecutive normalized words required to confirm a non-short anchor.
_ANCHOR_MIN_CONSECUTIVE_WORDS = 5

# @brief Canonical chunk-record payload type persisted for downstream workflow steps.
ChunkPayload = dict[str, object]

# @brief Persisted AI chunking report payload type.
ChunkingReportPayload = dict[str, object]

# @brief Persisted AI chunking operation-state payload type.
OperationStatePayload = dict[str, object]
TokenUsagePayload = dict[str, object]
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
) -> ChunkingReportPayload:
    """
    @brief      Run AI-assisted chunking for one active project.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Active project manifest payload.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  semantic_strategy Selected semantic strategy token.
    @param[in]  progress_callback Optional progress callback for the modal popup.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @param[in]  chunking_context_mode Optional AI chunking context mode token.
    @return     Chunking report payload for the persisted AI chunking artifacts.
    @exception  FileNotFoundError Raised when the cleaned input is missing.
    @exception  ValueError Raised on missing profile data or unusable cleaned text.
    @exception  OperationCancelledError Raised when the operator cancels the run.
    @exception  IncompatibleChunkingDocumentError Raised when cleaned text changed; reset Chunking first.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.2.0
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
    existing_document = chunking_document_service.load_chunking_document(resolved_project_root)
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

    remaining_windows = _build_windows_from_index(
        paragraph_records,
        next_paragraph - 1,
        semantic_strategy,
        budget_metadata,
    )
    completed_window_count = 0
    total_windows = len(remaining_windows)
    document = chunking_document_service.build_document(
        status="running",
        mode="ai_assisted",
        source_text=input_text,
        chunks=committed_chunks,
        semantic_strategy=semantic_strategy,
        additional_chunking_instructions=additional_chunking_instructions,
        token_usage=token_usage,
        next_paragraph=next_paragraph,
        context_window_fallback_count=context_window_fallback_count,
    )
    chunking_document_service.write_chunking_document(resolved_project_root, document)
    _emit_progress(
        progress_callback,
        progress_current=completed_window_count,
        progress_total=total_windows,
        message="Resuming AI-assisted chunking..." if committed_chunks else "AI-assisted chunking in progress...",
        token_usage=token_usage,
    )

    try:
        while next_paragraph <= len(paragraph_records):
            raise_if_cancelled(cancel_requested)
            remaining_windows = _build_windows_from_index(
                paragraph_records,
                next_paragraph - 1,
                semantic_strategy,
                budget_metadata,
            )
            window_payload = remaining_windows[0]
            window_start_index = int(window_payload["start_index"])
            window_end_index = int(window_payload["end_index"])
            window_records = paragraph_records[window_start_index : window_end_index + 1]
            is_final_window = window_end_index == len(paragraph_records) - 1
            total_windows = completed_window_count + len(remaining_windows)
            user_prompt = _render_chunking_user_prompt(
                {
                    "strategy": semantic_strategy,
                    "units_block": _build_units_block(window_records),
                    "additional_chunking_instructions": additional_chunking_instructions,
                },
            )
            try:
                response_result = llm_provider_service.chat_json(
                    ai_profile_payload,
                    system_prompt,
                    user_prompt,
                    log_path=log_path,
                    log_context={
                        "operation_kind": "chunking",
                        "stage_label": "ai_chunking",
                        "profile_id": profile_id,
                        "semantic_strategy": semantic_strategy,
                        "window_index": completed_window_count + 1,
                        "window_total": total_windows,
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
                    semantic_strategy,
                )
                next_paragraph = int(validated_ranges[-1]["end_index"]) + 2
                if (
                    response_complete
                    and is_final_window
                    and next_paragraph <= len(paragraph_records)
                ):
                    _append_chunks_from_ranges(
                        committed_chunks,
                        paragraph_records,
                        [{"start_index": next_paragraph - 1, "end_index": len(paragraph_records) - 1}],
                        semantic_strategy,
                    )
                    next_paragraph = len(paragraph_records) + 1
                elif not response_complete:
                    progress_message = (
                        "AI chunking accepted a valid descriptor prefix and "
                        f"will retry from paragraph {next_paragraph}."
                    )
            elif is_final_window:
                fallback_ranges = _deterministic_structural_fallback_ranges(
                    paragraph_records,
                    window_start_index,
                    len(paragraph_records) - 1,
                )
                _append_chunks_from_ranges(
                    committed_chunks,
                    paragraph_records,
                    fallback_ranges,
                    semantic_strategy,
                )
                next_paragraph = len(paragraph_records) + 1
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
                    semantic_strategy,
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

            completed_window_count += 1
            remaining_windows = _build_windows_from_index(
                paragraph_records,
                next_paragraph - 1,
                semantic_strategy,
                budget_metadata,
            )
            total_windows = completed_window_count + len(remaining_windows)
            document["chunks"] = committed_chunks
            document["token_usage"] = token_usage
            document["next_paragraph"] = next_paragraph
            document["context_window_fallback_count"] = context_window_fallback_count
            chunking_document_service.write_chunking_document(resolved_project_root, document)
            _emit_progress(
                progress_callback,
                progress_current=completed_window_count,
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
        chunking_document_service.write_chunking_document(resolved_project_root, document)
        raise
    except Exception:
        document["status"] = "failed"
        document["chunks"] = committed_chunks
        document["token_usage"] = token_usage
        document["next_paragraph"] = next_paragraph
        document["context_window_fallback_count"] = context_window_fallback_count
        chunking_document_service.write_chunking_document(resolved_project_root, document)
        raise

    chunks = committed_chunks
    chapter_count = _chapter_count_from_chunks(chunks)
    warnings = deterministic_chunking_service._build_chunking_warnings(chapter_count)
    if context_window_fallback_count:
        window_label = (
            "One text window was"
            if context_window_fallback_count == 1
            else (f"{context_window_fallback_count} text windows were")
        )
        warnings.append(
            f"{window_label} saved as a fallback chunk because AI chunking returned no valid internal split. "
            "Explicit heading and scene-separator boundaries were preserved when available."
        )
    document["status"] = "completed"
    document["chunks"] = chunks
    document["token_usage"] = token_usage
    document["warnings"] = warnings
    document["next_paragraph"] = None
    document["context_window_fallback_count"] = context_window_fallback_count
    chunking_document_service.write_chunking_document(resolved_project_root, document)
    completed_state = chunking_document_service.derive_operation_state(document)
    project_workspace_service.sync_manifest_operation_summary(
        resolved_project_root,
        "chunking",
        completed_state,
        current_stage="translation_ready",
    )
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.2.0
    """
    document = chunking_document_service.load_chunking_document(project_root)
    return None if document is None else chunking_document_service.derive_operation_state(document)


# LOCAL HELPERS


def _compute_prompt_fingerprint(prompt_text: str) -> str:
    """
    @brief      Compute a stable fingerprint for operator-supplied prompt rules.
    @param[in]  prompt_text Operator prompt-rule text.
    @return     SHA-256 fingerprint for the prompt-rule text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def _build_windows(
    paragraph_records: list[dict[str, object]],
    semantic_strategy: str,
    budget_metadata: BudgetMetadataPayload,
) -> list[dict[str, int]]:
    """
    @brief      Build context-budgeted AI request windows.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @param[in]  budget_metadata Context-budget metadata for the selected profile.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.4.0
    """
    _ = semantic_strategy
    text_budget = int(budget_metadata["text_budget_tokens"])
    paragraph_cap = int(budget_metadata["strategy_paragraph_cap"])
    windows: list[dict[str, int]] = []
    start_index = 0
    while start_index < len(paragraph_records):
        end_index = start_index - 1
        current_window_tokens = 0
        current_paragraph_count = 0
        while end_index + 1 < len(paragraph_records) and (
            paragraph_cap <= 0 or current_paragraph_count < paragraph_cap
        ):
            candidate_record = paragraph_records[end_index + 1]
            candidate_tokens = _estimate_text_tokens(_build_units_block([candidate_record]))
            if current_paragraph_count > 0 and current_window_tokens + candidate_tokens > text_budget:
                break
            current_window_tokens += candidate_tokens
            current_paragraph_count += 1
            end_index += 1
        windows.append(
            {
                "start_index": start_index,
                "end_index": end_index,
            }
        )
        start_index = end_index + 1
    return windows


def _build_windows_from_index(
    paragraph_records: list[dict[str, object]],
    start_index: int,
    semantic_strategy: str,
    budget_metadata: BudgetMetadataPayload,
) -> list[dict[str, int]]:
    """
    @brief      Build context-budgeted AI request windows from one absolute paragraph index.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @param[in]  start_index First absolute paragraph index still needing AI processing.
    @param[in]  semantic_strategy Value for `semantic_strategy`.
    @param[in]  budget_metadata Context-budget metadata for the selected profile.
    @return     Absolute-index window payloads for the remaining text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.1.0
    """
    resolved_start_index = max(0, min(int(start_index), len(paragraph_records)))
    if resolved_start_index >= len(paragraph_records):
        return []
    relative_windows = _build_windows(
        paragraph_records[resolved_start_index:],
        semantic_strategy,
        budget_metadata,
    )
    return [
        {
            "start_index": int(window["start_index"]) + resolved_start_index,
            "end_index": int(window["end_index"]) + resolved_start_index,
        }
        for window in relative_windows
    ]


def _build_budget_metadata(
    ai_profile_payload: dict[str, object],
    semantic_strategy: str,
    system_prompt: str,
    additional_chunking_instructions: str,
    chunking_context_mode: str | None = None,
) -> BudgetMetadataPayload:
    """
    @brief      Build context-window budget metadata for AI chunking.
    @param[in]  ai_profile_payload Selected validated AI profile payload.
    @param[in]  semantic_strategy Selected semantic strategy token.
    @param[in]  system_prompt Rendered system prompt.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @param[in]  chunking_context_mode Optional AI chunking context mode token.
    @return     Context-budget metadata used for request-window construction.
    @exception  ValueError Raised when context and output settings leave too little input room.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.3.1
    """
    prompt_user_shell = _render_chunking_user_prompt(
        {
            "strategy": semantic_strategy,
            "units_block": "",
            "additional_chunking_instructions": additional_chunking_instructions,
        },
    )
    budget_metadata = ai_budget_service.context_budget_metadata(
        ai_profile_payload,
        f"{system_prompt}\n\n{prompt_user_shell}",
        config.DEFAULT_AI_CHUNKING_MIN_SAFETY_MARGIN_TOKENS,
        config.DEFAULT_AI_CHUNKING_SAFETY_MARGIN_CONTEXT_FRACTION,
        config.DEFAULT_AI_CHUNKING_TEXT_CONTEXT_FRACTION,
        config.DEFAULT_AI_CHUNKING_MIN_TEXT_BUDGET_TOKENS,
        "AI-assisted chunking cannot run because the selected AI profile context window "
        "and max output tokens leave too little room for chunking input",
        online_text_context_fraction=config.DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION,
    )
    if (
        ai_budget_service.uses_online_text_budget(ai_profile_payload)
        or chunking_context_mode == config.AI_CHUNKING_CONTEXT_MODE_MAXIMUM
    ):
        strategy_paragraph_cap = 0
    elif chunking_context_mode == config.AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE:
        strategy_paragraph_cap = config.AI_CHUNKING_WIDE_WINDOW_SIZE_BY_STRATEGY.get(
            semantic_strategy,
            config.AI_CHUNKING_WIDE_WINDOW_SIZE_BY_STRATEGY[config.DEFAULT_AI_CHUNKING_STRATEGY],
        )
    else:
        strategy_paragraph_cap = config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY.get(
            semantic_strategy,
            config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY[config.DEFAULT_AI_CHUNKING_STRATEGY],
        )
    return {
        **budget_metadata,
        "strategy_paragraph_cap": strategy_paragraph_cap,
    }


def _render_chunking_user_prompt(variables: dict[str, object]) -> str:
    """
    @brief      Render the AI chunking user prompt with optional operator rules.
    @param[in]  variables Prompt variables.
    @return     Rendered AI chunking user prompt.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    template = prompt_template_service.load_prompt("text_chunking_user")
    placeholder_names = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", template))
    rendered_prompt = prompt_template_service.render_prompt(
        "text_chunking_user",
        {key: value for key, value in variables.items() if key in placeholder_names},
    )
    additional_chunking_instructions = _normalized_additional_chunking_instructions(
        variables.get("additional_chunking_instructions")
    )
    if additional_chunking_instructions and "additional_chunking_instructions" not in placeholder_names:
        rendered_prompt = _append_additional_chunking_instructions(
            rendered_prompt,
            additional_chunking_instructions,
        )
    return rendered_prompt


def _normalized_additional_chunking_instructions(value: object) -> str:
    """
    @brief      Normalize optional operator chunking rules for prompt insertion and state storage.
    @param[in]  value Candidate instruction text.
    @return     Trimmed instruction text.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    if value is None:
        return ""
    return str(value).strip()


def _append_additional_chunking_instructions(prompt_text: str, additional_chunking_instructions: str) -> str:
    """
    @brief      Append operator chunking rules to one rendered AI chunking prompt.
    @param[in]  prompt_text Rendered prompt template text.
    @param[in]  additional_chunking_instructions Normalized operator rules.
    @return     Prompt text with an additional-rules section.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    if not additional_chunking_instructions:
        return prompt_text
    return f"{prompt_text.rstrip()}\n\nAdditional operator chunking instructions:\n{additional_chunking_instructions}\n"


def _estimate_text_tokens(text: str) -> int:
    """
    @brief      Estimate token usage for local budget checks.
    @param[in]  text Value for `text`.
    @return     Estimated token count.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    return ai_budget_service.estimate_text_tokens(text)


def _build_paragraph_records(cleaned_text: str, project_root: str | Path | None = None) -> list[dict[str, object]]:
    """
    @brief      Build the paragraph records.
    @param[in]  cleaned_text Text value for `cleaned_text`.
    @param[in]  project_root Active project root folder.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    records = deterministic_chunking_service._build_paragraph_records(cleaned_text, project_root)
    for index, record in enumerate(records, start=1):
        record["unit_id"] = str(record.get("paragraph_id") or f"paragraph-{index:04d}")
        record["paragraph_number"] = index
    return records


def _build_response_schema() -> dict[str, object]:
    """
    @brief      Build the strict AI chunk descriptor response schema.
    @return     Provider structured-output schema.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["chunks"],
        "properties": {
            "chunks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "start_paragraph",
                        "start_text",
                        "break_after_paragraph",
                    ],
                    "properties": {
                        "start_paragraph": {"type": "integer", "minimum": 1},
                        "start_text": {"type": "string", "minLength": 1},
                        "break_after_paragraph": {"type": "integer", "minimum": 1},
                    },
                },
            },
        },
    }


def _paragraph_start_anchor(paragraph_text: str) -> str:
    """
    @brief      Build the canonical start anchor for one paragraph.
    @param[in]  paragraph_text Canonical paragraph text.
    @return     First eight normalized words, or the whole shorter paragraph.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
    """
    return " ".join(str(paragraph_text).split()[:_ANCHOR_WORD_LIMIT])


def _normalized_anchor_words(anchor_text: str) -> list[str]:
    """
    @brief      Canonicalize anchor words for tolerant deterministic comparison.
    @param[in]  anchor_text Source or model-returned anchor text.
    @return     Up to eight case-folded compatibility-normalized words without punctuation.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    0.1.0
    """
    normalized_text = unicodedata.normalize("NFKC", str(anchor_text)).casefold()
    normalized_words: list[str] = []
    for raw_word in normalized_text.split():
        normalized_word = "".join(character for character in raw_word if character.isalnum())
        if normalized_word:
            normalized_words.append(normalized_word)
        if len(normalized_words) == _ANCHOR_WORD_LIMIT:
            break
    return normalized_words


def _normalized_complete_anchor(anchor_text: str) -> str:
    """
    @brief      Canonicalize one complete anchor while retaining punctuation.
    @param[in]  anchor_text Source or model-returned anchor text.
    @return     Compatibility-normalized, case-folded, whitespace-collapsed anchor.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    normalized_text = unicodedata.normalize("NFKC", str(anchor_text)).casefold()
    return " ".join(normalized_text.split())


def _start_anchor_matches(paragraph_text: str, returned_anchor: str) -> bool:
    """
    @brief      Confirm a model anchor against its declared source paragraph.
    @param[in]  paragraph_text Canonical source paragraph text.
    @param[in]  returned_anchor Model-returned start anchor.
    @return     True for an exact punctuation anchor, a complete short match, or a five-word run.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    0.2.0
    """
    expected_words = _normalized_anchor_words(_paragraph_start_anchor(paragraph_text))
    returned_words = _normalized_anchor_words(returned_anchor)
    if not expected_words:
        expected_anchor = _normalized_complete_anchor(
            _paragraph_start_anchor(paragraph_text)
        )
        return bool(expected_anchor) and (
            _normalized_complete_anchor(returned_anchor) == expected_anchor
        )
    if len(expected_words) < _ANCHOR_MIN_CONSECUTIVE_WORDS:
        return returned_words == expected_words

    longest_run = 0
    current_run = 0
    for expected_word, returned_word in zip(expected_words, returned_words, strict=False):
        if returned_word == expected_word:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    return longest_run >= _ANCHOR_MIN_CONSECUTIVE_WORDS


def _validate_chunk_descriptor_prefix(
    response_payload: dict[str, object],
    paragraph_records: list[dict[str, object]],
    window_start_index: int,
    window_end_index: int,
) -> tuple[list[dict[str, int]], bool]:
    """
    @brief      Validate the longest consecutive descriptor prefix.
    @param[in]  response_payload Provider JSON response object.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  window_start_index Zero-based absolute first paragraph index.
    @param[in]  window_end_index Zero-based absolute last paragraph index.
    @return     Validated absolute prefix ranges and whole-response validity.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    if set(response_payload) != {"chunks"}:
        return [], False
    raw_chunks = response_payload.get("chunks")
    if not isinstance(raw_chunks, list) or not raw_chunks:
        return [], False

    expected_start_paragraph = window_start_index + 1
    validated_ranges: list[dict[str, int]] = []
    required_fields = {"start_paragraph", "start_text", "break_after_paragraph"}
    for item in raw_chunks:
        if not isinstance(item, dict) or set(item) != required_fields:
            return validated_ranges, False
        start_paragraph = item.get("start_paragraph")
        break_after_paragraph = item.get("break_after_paragraph")
        start_text = item.get("start_text")
        if type(start_paragraph) is not int or type(break_after_paragraph) is not int:
            return validated_ranges, False
        if not isinstance(start_text, str):
            return validated_ranges, False
        if start_paragraph != expected_start_paragraph:
            return validated_ranges, False
        if not window_start_index + 1 <= start_paragraph <= window_end_index + 1:
            return validated_ranges, False
        if not start_paragraph <= break_after_paragraph <= window_end_index + 1:
            return validated_ranges, False
        paragraph_text = str(paragraph_records[start_paragraph - 1]["text"])
        if not _start_anchor_matches(paragraph_text, start_text):
            return validated_ranges, False
        validated_ranges.append(
            {
                "start_index": start_paragraph - 1,
                "end_index": break_after_paragraph - 1,
            }
        )
        expected_start_paragraph = break_after_paragraph + 1
    return validated_ranges, True


def _is_structural_boundary_record(record: dict[str, object]) -> bool:
    """
    @brief      Identify an explicit heading or scene-separator paragraph.
    @param[in]  record Canonical Cleanup paragraph record.
    @return     True when deterministic fallback must preserve this boundary.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    role = str(record.get("role") or "body")
    if role == "heading":
        return True
    return not _is_narratable_record(record)


def _effective_cleanup_role(record: dict[str, object]) -> str:
    """
    @brief      Return the role exposed by an AI chunk after user text edits.
    @param[in]  record Canonical Cleanup paragraph record.
    @return     Stored role or a recovered raw scene-separator role.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    role = str(record.get("role") or "body")
    if not _is_narratable_record(record):
        return "scene_separator"
    return role


def _deterministic_structural_fallback_ranges(
    paragraph_records: list[dict[str, object]],
    window_start_index: int,
    window_end_index: int,
) -> list[dict[str, int]]:
    """
    @brief      Split a rejected AI window around explicit structural paragraphs.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  window_start_index Zero-based inclusive first paragraph index.
    @param[in]  window_end_index Zero-based inclusive last paragraph index.
    @return     Consecutive ranges that preserve headings and scene separators.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-29
    @version    0.1.0
    """
    structural_indices = [
        index
        for index in range(window_start_index, window_end_index + 1)
        if _is_structural_boundary_record(paragraph_records[index])
    ]
    if not structural_indices:
        return [
            {
                "start_index": window_start_index,
                "end_index": window_end_index,
            }
        ]

    ranges: list[dict[str, int]] = []
    next_index = window_start_index
    for structural_index in structural_indices:
        if next_index < structural_index:
            ranges.append(
                {
                    "start_index": next_index,
                    "end_index": structural_index - 1,
                }
            )
        ranges.append(
            {
                "start_index": structural_index,
                "end_index": structural_index,
            }
        )
        next_index = structural_index + 1
    if next_index <= window_end_index:
        ranges.append(
            {
                "start_index": next_index,
                "end_index": window_end_index,
            }
        )
    return ranges


def _build_units_block(paragraph_records: list[dict[str, object]]) -> str:
    """
    @brief      Build the units block.
    @param[in]  paragraph_records Value for `paragraph_records`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    blocks: list[str] = []
    for index, record in enumerate(paragraph_records):
        paragraph_number = int(record.get("paragraph_number", index + 1))
        blocks.append(f"Paragraph {paragraph_number}\n{record['text']}")
    return "\n\n".join(blocks).strip()


def _build_chunk_from_range(
    paragraph_records: list[dict[str, object]],
    start_index: int,
    end_index: int,
    semantic_strategy: str,
    sequence_index: int,
) -> ChunkPayload:
    """
    @brief      Build one canonical AI chunk from an absolute paragraph range.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  start_index Zero-based inclusive first paragraph index.
    @param[in]  end_index Zero-based inclusive last paragraph index.
    @param[in]  semantic_strategy Selected semantic strategy.
    @param[in]  sequence_index One-based canonical chunk sequence number.
    @return     Canonical chunk payload.
    @exception  ValueError Raised when the selected range is empty or invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.2.0
    """
    selected_records = paragraph_records[start_index : end_index + 1]
    if not selected_records:
        raise ValueError("AI chunk range does not contain any paragraphs.")
    _ = semantic_strategy
    return {
        "chunk_id": f"chunk-{sequence_index:04d}",
        "sequence_index": sequence_index,
        "text": "\n\n".join(str(item["text"]) for item in selected_records).strip(),
        "cleanup_boundary_confidence": selected_records[0].get("boundary_confidence"),
        "cleanup_joined_across_page_break": any(
            bool(item.get("joined_across_page_break", False)) for item in selected_records
        ),
        "cleanup_warning_flags": _merged_warning_flags(selected_records),
        "cleanup_role": next(
            (
                _effective_cleanup_role(item)
                for item in selected_records
                if _effective_cleanup_role(item) != "body"
            ),
            _effective_cleanup_role(selected_records[0]),
        ),
        "starts_after_scene_separator": _starts_after_scene_separator(
            paragraph_records,
            start_index,
        ),
    }


def _is_narratable_record(record: dict[str, object]) -> bool:
    """Return whether one Cleanup paragraph should be materialized as audio text."""
    return not cleanup_text_analysis_service.is_scene_separator_artifact(
        str(record.get("text") or ""),
        str(record.get("role") or "body"),
    )


def _starts_after_scene_separator(
    paragraph_records: list[dict[str, object]],
    start_index: int,
) -> bool:
    """Return whether the narratable range starts immediately after a scene separator."""
    return start_index > 0 and not _is_narratable_record(paragraph_records[start_index - 1])


def _narratable_subranges(
    paragraph_records: list[dict[str, object]],
    start_index: int,
    end_index: int,
) -> list[dict[str, int]]:
    """Split one selected range at non-narratable scene-separator paragraphs."""
    if start_index < 0 or end_index < start_index or end_index >= len(paragraph_records):
        raise ValueError("AI chunk range is outside the available paragraphs.")
    ranges: list[dict[str, int]] = []
    segment_start: int | None = None
    for index in range(start_index, end_index + 1):
        if _is_narratable_record(paragraph_records[index]):
            if segment_start is None:
                segment_start = index
            continue
        if segment_start is not None:
            ranges.append(
                {
                    "start_index": segment_start,
                    "end_index": index - 1,
                }
            )
            segment_start = None
    if segment_start is not None:
        ranges.append(
            {
                "start_index": segment_start,
                "end_index": end_index,
            }
        )
    return ranges


def _append_chunks_from_ranges(
    chunks: list[ChunkPayload],
    paragraph_records: list[dict[str, object]],
    ranges: list[dict[str, int]],
    semantic_strategy: str,
) -> None:
    """
    @brief      Append canonical chunks for validated absolute paragraph ranges.
    @param[in,out] chunks Existing committed chunk payload list.
    @param[in]  paragraph_records Full ordered paragraph record list.
    @param[in]  ranges Validated absolute paragraph ranges.
    @param[in]  semantic_strategy Selected semantic strategy.
    @return     None.
    @exception  ValueError Raised when a range is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    1.0.0
    """
    for range_payload in ranges:
        narratable_ranges = _narratable_subranges(
            paragraph_records,
            int(range_payload["start_index"]),
            int(range_payload["end_index"]),
        )
        for narratable_range in narratable_ranges:
            chunks.append(
                _build_chunk_from_range(
                    paragraph_records,
                    narratable_range["start_index"],
                    narratable_range["end_index"],
                    semantic_strategy,
                    len(chunks) + 1,
                )
            )


def _merged_warning_flags(paragraph_records: list[dict[str, object]]) -> list[str]:
    """
    @brief      Merge cleanup warning flags across selected paragraph records.
    @param[in]  paragraph_records Paragraph records in one AI chunk span.
    @return     Ordered unique warning flags.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    flags: list[str] = []
    for record in paragraph_records:
        for flag in list(record.get("warning_flags", [])):
            resolved_flag = str(flag)
            if resolved_flag and resolved_flag not in flags:
                flags.append(resolved_flag)
    return flags


def _chapter_count_from_chunks(chunks: list[ChunkPayload]) -> int:
    """
    @brief      Execute the chapter count from chunks helper.
    @param[in]  chunks Value for `chunks`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return deterministic_chunking_service._chapter_count_from_chunks(chunks)


def _build_ai_log_path(project_root: Path, started_at: str) -> Path:
    """
    @brief      Build the ai log path.
    @param[in]  project_root Active project root folder.
    @param[in]  started_at Value for `started_at`.
    @return     Derived helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
    @author Eng. Dan Dumitru Pasare
    @date 2026-07-20
    @version 0.1.0
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
