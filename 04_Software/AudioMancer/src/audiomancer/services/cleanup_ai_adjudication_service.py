#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""
@file cleanup_ai_adjudication_service.py
@brief Bounded two-pass AI adjudication for uncertain Cleanup V2 questions.
@details Uses small homogeneous batches, strict provider JSON Schema, and an
         independent verifier. A disagreement or failure always preserves text.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
import json
from pathlib import Path

from audiomancer.services import (
    cleanup_analysis_service,
    llm_provider_service,
    prompt_template_service,
    token_usage_service,
)
from audiomancer.services.operation_runtime_service import raise_if_cancelled

MINIMUM_CONTEXT_WINDOW = 16_000
MAX_OUTPUT_TOKENS = 512
PROMPT_SCHEMA_VERSION = 1


def adjudicate_questions(
    questions: list[dict[str, object]],
    profile_payload: dict[str, object] | None,
    *,
    log_path: str | Path | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cancel_requested=None,
) -> dict[str, object]:
    """Return only operations independently accepted by both AI passes."""
    usage = token_usage_service.empty_token_usage()
    if not questions:
        return {"operations": [], "answers": [], "warnings": [], "token_usage": usage}
    compatibility_warning = _compatibility_warning(profile_payload)
    if compatibility_warning is not None:
        return {
            "operations": [],
            "answers": [],
            "warnings": [compatibility_warning],
            "token_usage": usage,
        }
    assert profile_payload is not None
    batch_size = 8 if int(profile_payload["context_window"]) >= 32_768 else 4
    batches = _homogeneous_batches(questions, batch_size)
    total_requests = len(batches) * 2
    accepted_operations: list[dict[str, object]] = []
    answer_records: list[dict[str, object]] = []
    warnings: list[str] = []
    for batch_index, batch in enumerate(batches):
        raise_if_cancelled(cancel_requested)
        batch_id = f"cleanup-batch-{batch_index + 1:04d}"
        completed_requests = batch_index * 2
        try:
            _emit_progress(
                progress_callback,
                completed_requests,
                total_requests,
                f"AI Cleanup — Batch {batch_index + 1}/{len(batches)} — Primary request...",
            )
            primary, primary_usage = _ask(
                profile_payload,
                batch_id,
                batch,
                verifier=False,
                log_path=log_path,
                cancel_requested=cancel_requested,
            )
            usage = token_usage_service.merge_token_usage(usage, primary_usage)
            completed_requests += 1
            _emit_progress(
                progress_callback,
                completed_requests,
                total_requests,
                f"AI Cleanup — Batch {batch_index + 1}/{len(batches)} — Verifier request...",
            )
            verifier, verifier_usage = _ask(
                profile_payload,
                batch_id,
                batch,
                verifier=True,
                log_path=log_path,
                cancel_requested=cancel_requested,
            )
            usage = token_usage_service.merge_token_usage(usage, verifier_usage)
            completed_requests += 1
        except Exception as error:  # Provider failure is a safe preserve fallback.
            warnings.append(
                f"AI Cleanup stopped at {batch_id}; this and all remaining questions were preserved: {error}"
            )
            break
        verifier_by_id = {str(item["question_id"]): str(item["choice"]) for item in verifier}
        for primary_answer in primary:
            question_id = str(primary_answer["question_id"])
            primary_choice = str(primary_answer["choice"])
            verifier_choice = verifier_by_id.get(question_id)
            agreed = verifier_choice == primary_choice
            question = next(item for item in batch if item["question_id"] == question_id)
            operation = (
                cleanup_analysis_service.operation_from_answer(question, primary_choice, verifier=True)
                if agreed
                else None
            )
            if operation is not None:
                accepted_operations.append(operation)
            answer_records.append(
                {
                    "question_id": question_id,
                    "primary_choice": primary_choice,
                    "verifier_choice": verifier_choice,
                    "accepted": operation is not None,
                }
            )
        _emit_progress(
            progress_callback,
            completed_requests,
            total_requests,
            f"AI Cleanup — Batch {batch_index + 1}/{len(batches)} — Verified.",
        )
    return {
        "operations": accepted_operations,
        "answers": answer_records,
        "warnings": warnings,
        "token_usage": usage,
    }


def _emit_progress(
    callback: Callable[[int, int, str], None] | None,
    current: int,
    total: int,
    message: str,
) -> None:
    """Emit one bounded AI work-unit progress update."""
    if callable(callback):
        callback(max(0, min(current, total)), total, message)


def _ask(
    profile: dict[str, object],
    batch_id: str,
    questions: list[dict[str, object]],
    *,
    verifier: bool,
    log_path,
    cancel_requested,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Execute and strictly validate one primary or verifier request."""
    schema = _answer_schema(batch_id, questions)
    system_prompt = prompt_template_service.load_prompt(
        "text_cleanup_adjudication_verifier_system"
        if verifier
        else "text_cleanup_adjudication_primary_system"
    )
    question_payload = [
        {
            "question_id": item["question_id"],
            "type": item["question_type"],
            "left": item["left_text"],
            "right": item["right_text"],
            "choices": item["choices"],
        }
        for item in questions
    ]
    user_prompt = json.dumps(
        {"batch_id": batch_id, "questions": question_payload},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    _require_context_budget(profile, system_prompt, user_prompt, schema)
    response = llm_provider_service.chat_json(
        profile,
        system_prompt,
        user_prompt,
        log_path=log_path,
        log_context={"operation": "cleanup_v2", "pass": "verifier" if verifier else "primary"},
        cancel_requested=cancel_requested,
        structured_output=True,
        response_schema=schema,
        response_schema_name="audiomancer_cleanup_answers",
        require_response_schema=True,
        allow_unconstrained_fallback=False,
        allow_model_json_repair=False,
        retry_count_override=1,
        max_output_tokens_override=MAX_OUTPUT_TOKENS,
    )
    payload = response.get("payload")
    answers = _validate_answers(payload, batch_id, questions)
    return answers, token_usage_service.coerce_token_usage(response.get("usage"))


def _validate_answers(
    payload: object,
    batch_id: str,
    questions: list[dict[str, object]],
) -> list[dict[str, str]]:
    """Validate exact answer coverage and choices without repair."""
    if not isinstance(payload, dict) or set(payload) != {"batch_id", "answers"}:
        raise ValueError("Cleanup AI response fields are invalid.")
    if payload.get("batch_id") != batch_id or not isinstance(payload.get("answers"), list):
        raise ValueError("Cleanup AI response batch is invalid.")
    expected = {str(item["question_id"]): set(item["choices"]) for item in questions}
    answers: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in payload["answers"]:
        if not isinstance(item, dict) or set(item) != {"question_id", "choice"}:
            raise ValueError("Cleanup AI answer fields are invalid.")
        question_id = str(item["question_id"])
        choice = str(item["choice"])
        if question_id not in expected or question_id in seen or choice not in expected[question_id]:
            raise ValueError("Cleanup AI answer references an invalid question or choice.")
        seen.add(question_id)
        answers.append({"question_id": question_id, "choice": choice})
    if seen != set(expected):
        raise ValueError("Cleanup AI response did not answer the complete batch.")
    return answers


def _answer_schema(batch_id: str, questions: list[dict[str, object]]) -> dict[str, object]:
    """Build the exact JSON Schema for one homogeneous question batch."""
    question_ids = [str(item["question_id"]) for item in questions]
    choices = sorted({str(choice) for item in questions for choice in item["choices"]})
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["batch_id", "answers"],
        "properties": {
            "batch_id": {"type": "string", "const": batch_id},
            "answers": {
                "type": "array",
                "minItems": len(questions),
                "maxItems": len(questions),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["question_id", "choice"],
                    "properties": {
                        "question_id": {"type": "string", "enum": question_ids},
                        "choice": {"type": "string", "enum": choices},
                    },
                },
            },
        },
    }


def _homogeneous_batches(
    questions: list[dict[str, object]],
    batch_size: int,
) -> list[list[dict[str, object]]]:
    """Assign stable ids and split questions by type and context tier."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for index, source in enumerate(questions):
        item = dict(source)
        item["question_id"] = f"q-{index + 1:06d}"
        grouped[str(item["question_type"])].append(item)
    return [
        group[start : start + batch_size]
        for question_type in sorted(grouped)
        for group in (grouped[question_type],)
        for start in range(0, len(group), batch_size)
    ]


def _compatibility_warning(profile: dict[str, object] | None) -> str | None:
    if profile is None:
        return "AI profile was not selected; uncertain cases were preserved."
    if not bool(profile.get("supports_structured_output", False)):
        return "AI profile does not support strict structured output; uncertain cases were preserved."
    if int(profile.get("context_window", 0) or 0) < MINIMUM_CONTEXT_WINDOW:
        return "AI profile context window is below 16K; uncertain cases were preserved."
    return None


def _require_context_budget(
    profile: dict[str, object],
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, object],
) -> None:
    """Enforce the conservative UTF-8 byte estimator and 70% context ceiling."""
    estimated_input = (
        len(system_prompt.encode("utf-8"))
        + len(user_prompt.encode("utf-8"))
        + len(json.dumps(schema, ensure_ascii=False).encode("utf-8"))
    ) // 2
    required = estimated_input + MAX_OUTPUT_TOKENS
    if required > int(int(profile["context_window"]) * 0.70):
        raise ValueError("Cleanup question batch exceeds the safe context budget.")
