#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file cleanup_ai_adjudication_service.py
@brief Bounded model-agnostic adjudication for ambiguous Cleanup boundaries.
@details Uses context-tiered batches, recursive budget splitting, one retry,
         deterministic per-batch fallback, and a blind verifier only when a
         primary answer disagrees with the deterministic prior.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    llm_provider_service,
    prompt_template_service,
    token_usage_service,
)
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    raise_if_cancelled,
)

MINIMUM_CONTEXT_WINDOW = 16_000
PROMPT_CONTRACT_ID = "cleanup-adjudication-2026-07-28"

# @brief Fraction of the context window one request may occupy.
_SAFE_CONTEXT_FRACTION = 0.70


class ContextBudgetExceededError(ValueError):
    """Raised when one Cleanup request cannot fit its safe context budget."""


def plan_question_batches(
    questions: list[dict[str, object]],
    profile_payload: dict[str, object] | None,
) -> list[list[dict[str, object]]]:
    """
    @brief      Build the authoritative top-level Cleanup AI request plan.
    @param[in]  questions Candidate ambiguous boundary questions.
    @param[in]  profile_payload Selected provider profile, or None.
    @return     Stable homogeneous context-tier batches, or no batches when
                the profile cannot perform strict AI adjudication.
    @exception  None.
    """
    normalized_questions = _normalized_questions(questions)
    if (
        not normalized_questions
        or _compatibility_warning(profile_payload) is not None
    ):
        return []
    assert profile_payload is not None
    batch_size = _batch_size_for_context(
        int(profile_payload["context_window"])
    )
    return _homogeneous_batches(normalized_questions, batch_size)


def adjudicate_questions(
    questions: list[dict[str, object]],
    profile_payload: dict[str, object] | None,
    *,
    log_path: str | Path | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cancel_requested=None,
    resume_answers: dict[str, dict[str, object]] | None = None,
    completed_request_count: int = 0,
    request_callback: Callable[
        [
            str,
            str,
            list[dict[str, object]],
            list[dict[str, str]],
            dict[str, object],
        ],
        None,
    ]
    | None = None,
    submission_callback: Callable[
        [str, str, list[dict[str, object]]],
        None,
    ]
    | None = None,
) -> dict[str, object]:
    """Adjudicate ambiguous boundaries while preserving deterministic priors."""
    normalized_questions = _normalized_questions(questions)
    usage = token_usage_service.empty_token_usage()
    if not normalized_questions:
        return _result([], [], usage, 0, [])
    compatibility_warning = _compatibility_warning(profile_payload)
    if compatibility_warning is not None:
        fallbacks = [_fallback_record(item) for item in normalized_questions]
        return _result(
            fallbacks,
            [compatibility_warning],
            usage,
            0,
            [],
        )

    assert profile_payload is not None
    batches = plan_question_batches(normalized_questions, profile_payload)
    estimated_requests = len(batches) * 2
    completed_requests = max(0, int(completed_request_count))
    answer_records: list[dict[str, object]] = []
    warnings: list[str] = []
    failed_batch_count = 0
    batch_order = [
        [str(item["target_id"]) for item in batch]
        for batch in batches
    ]
    resume = resume_answers or {}

    def _request_finished(
        pass_name: str,
        batch_id: str,
        batch: list[dict[str, object]],
        answers: list[dict[str, str]],
        request_usage: dict[str, object],
    ) -> None:
        nonlocal completed_requests
        completed_requests += 1
        if callable(request_callback):
            request_callback(
                pass_name,
                batch_id,
                batch,
                answers,
                request_usage,
            )
        _emit_progress(
            progress_callback,
            completed_requests,
            max(completed_requests, estimated_requests),
            f"AI Cleanup - {pass_name.title()} request completed.",
        )
        raise_if_cancelled(cancel_requested)

    for batch_index, batch in enumerate(batches, start=1):
        raise_if_cancelled(cancel_requested)
        batch_id = f"cleanup-batch-{batch_index:04d}"
        records, batch_warnings, batch_usage, batch_failures = _process_batch(
            profile_payload,
            batch_id,
            batch,
            log_path=log_path,
            cancel_requested=cancel_requested,
            resume_answers=resume,
            request_finished=_request_finished,
            submission_callback=submission_callback,
        )
        usage = token_usage_service.merge_token_usage(usage, batch_usage)
        answer_records.extend(records)
        warnings.extend(batch_warnings)
        failed_batch_count += batch_failures

    if any(record.get("state") == "fallback" for record in answer_records):
        for record in answer_records:
            record.setdefault("state", "completed")
    return {
        "answers": answer_records,
        "warnings": warnings,
        "token_usage": usage,
        "failed_batch_count": failed_batch_count,
        "batch_order": batch_order,
        "estimated_request_count": estimated_requests,
    }


def _process_batch(
    profile: dict[str, object],
    batch_id: str,
    questions: list[dict[str, object]],
    *,
    log_path: str | Path | None,
    cancel_requested,
    resume_answers: dict[str, dict[str, object]],
    request_finished,
    submission_callback,
) -> tuple[
    list[dict[str, object]],
    list[str],
    dict[str, object],
    int,
]:
    """Process one batch, recursively splitting only context-budget failures."""
    usage = token_usage_service.empty_token_usage()
    prior_primary = _resume_pass_answers(
        questions,
        resume_answers,
        "primary_choice",
    )
    try:
        if prior_primary is None:
            primary, primary_usage = _request_with_retry(
                profile,
                batch_id,
                questions,
                verifier=False,
                log_path=log_path,
                cancel_requested=cancel_requested,
                submission_callback=submission_callback,
            )
            request_finished(
                "primary",
                batch_id,
                questions,
                primary,
                primary_usage,
            )
        else:
            primary = prior_primary
            primary_usage = token_usage_service.empty_token_usage()
        usage = token_usage_service.merge_token_usage(usage, primary_usage)
    except ContextBudgetExceededError as error:
        if len(questions) == 1:
            return (
                [_fallback_record(questions[0])],
                [f"{batch_id} exceeded the context budget: {error}"],
                usage,
                1,
            )
        midpoint = len(questions) // 2
        return _combine_split_results(
            _process_batch(
                profile,
                f"{batch_id}-1",
                questions[:midpoint],
                log_path=log_path,
                cancel_requested=cancel_requested,
                resume_answers=resume_answers,
                request_finished=request_finished,
                submission_callback=submission_callback,
            ),
            _process_batch(
                profile,
                f"{batch_id}-2",
                questions[midpoint:],
                log_path=log_path,
                cancel_requested=cancel_requested,
                resume_answers=resume_answers,
                request_finished=request_finished,
                submission_callback=submission_callback,
            ),
        )
    except OperationCancelledError:
        raise
    except Exception as error:
        return (
            [_fallback_record(item) for item in questions],
            [f"{batch_id} failed twice; deterministic priors were used: {error}"],
            usage,
            1,
        )

    primary_by_id = {
        str(item["question_id"]): str(item["choice"])
        for item in primary
    }
    disagreements = [
        item
        for item in questions
        if primary_by_id[str(item["question_id"])]
        != str(item.get("prior_choice") or "")
    ]
    if not disagreements:
        return (
            [
                _completed_record(
                    item,
                    primary_by_id[str(item["question_id"])],
                    None,
                )
                for item in questions
            ],
            [],
            usage,
            0,
        )

    prior_verifier = _resume_pass_answers(
        disagreements,
        resume_answers,
        "verifier_choice",
    )
    try:
        if prior_verifier is None:
            verifier, verifier_usage = _request_with_retry(
                profile,
                batch_id,
                disagreements,
                verifier=True,
                log_path=log_path,
                cancel_requested=cancel_requested,
                submission_callback=submission_callback,
            )
            request_finished(
                "verifier",
                batch_id,
                disagreements,
                verifier,
                verifier_usage,
            )
        else:
            verifier = prior_verifier
            verifier_usage = token_usage_service.empty_token_usage()
        usage = token_usage_service.merge_token_usage(usage, verifier_usage)
    except ContextBudgetExceededError as error:
        if len(disagreements) == 1:
            verifier_by_id: dict[str, str] = {}
            warning = f"{batch_id} verifier exceeded the context budget: {error}"
            failed = 1
        else:
            midpoint = len(disagreements) // 2
            left_result = _process_verifier_split(
                profile,
                f"{batch_id}-verifier-left",
                disagreements[:midpoint],
                log_path,
                cancel_requested,
                request_finished,
                submission_callback,
            )
            right_result = _process_verifier_split(
                profile,
                f"{batch_id}-verifier-right",
                disagreements[midpoint:],
                log_path,
                cancel_requested,
                request_finished,
                submission_callback,
            )
            verifier_by_id = {**left_result[0], **right_result[0]}
            warning = " ".join(left_result[1] + right_result[1])
            usage = token_usage_service.merge_token_usage(usage, left_result[2])
            usage = token_usage_service.merge_token_usage(usage, right_result[2])
            failed = left_result[3] + right_result[3]
    except OperationCancelledError:
        raise
    except Exception as error:
        verifier_by_id = {}
        warning = f"{batch_id} verifier failed twice; deterministic priors were used: {error}"
        failed = 1
    else:
        verifier_by_id = {
            str(item["question_id"]): str(item["choice"])
            for item in verifier
        }
        warning = ""
        failed = 0

    records = []
    for question in questions:
        question_id = str(question["question_id"])
        primary_choice = primary_by_id[question_id]
        verifier_choice = verifier_by_id.get(question_id)
        records.append(
            _completed_record(
                question,
                primary_choice,
                verifier_choice,
            )
        )
    return records, ([warning] if warning else []), usage, failed


def _process_verifier_split(
    profile: dict[str, object],
    batch_id: str,
    questions: list[dict[str, object]],
    log_path,
    cancel_requested,
    request_finished,
    submission_callback,
) -> tuple[dict[str, str], list[str], dict[str, object], int]:
    """Recursively split an oversized verifier request."""
    usage = token_usage_service.empty_token_usage()
    try:
        answers, request_usage = _request_with_retry(
            profile,
            batch_id,
            questions,
            verifier=True,
            log_path=log_path,
            cancel_requested=cancel_requested,
            submission_callback=submission_callback,
        )
        request_finished(
            "verifier",
            batch_id,
            questions,
            answers,
            request_usage,
        )
        return (
            {
                str(item["question_id"]): str(item["choice"])
                for item in answers
            },
            [],
            request_usage,
            0,
        )
    except ContextBudgetExceededError as error:
        if len(questions) == 1:
            return {}, [f"{batch_id} exceeded the context budget: {error}"], usage, 1
        midpoint = len(questions) // 2
        left = _process_verifier_split(
            profile,
            f"{batch_id}-1",
            questions[:midpoint],
            log_path,
            cancel_requested,
            request_finished,
            submission_callback,
        )
        right = _process_verifier_split(
            profile,
            f"{batch_id}-2",
            questions[midpoint:],
            log_path,
            cancel_requested,
            request_finished,
            submission_callback,
        )
        return (
            {**left[0], **right[0]},
            left[1] + right[1],
            token_usage_service.merge_token_usage(left[2], right[2]),
            left[3] + right[3],
        )
    except OperationCancelledError:
        raise
    except Exception as error:
        return (
            {},
            [f"{batch_id} failed twice; deterministic priors were used: {error}"],
            usage,
            1,
        )


def _request_with_retry(
    profile: dict[str, object],
    batch_id: str,
    questions: list[dict[str, object]],
    *,
    verifier: bool,
    log_path,
    cancel_requested,
    submission_callback=None,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Execute one request and retry one non-budget failure."""
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            if callable(submission_callback):
                return _ask(
                    profile,
                    batch_id,
                    questions,
                    verifier=verifier,
                    log_path=log_path,
                    cancel_requested=cancel_requested,
                    submission_callback=submission_callback,
                )
            return _ask(
                profile,
                batch_id,
                questions,
                verifier=verifier,
                log_path=log_path,
                cancel_requested=cancel_requested,
            )
        except ContextBudgetExceededError:
            raise
        except Exception as error:
            last_error = error
            raise_if_cancelled(cancel_requested)
    assert last_error is not None
    raise last_error


def _ask(
    profile: dict[str, object],
    batch_id: str,
    questions: list[dict[str, object]],
    *,
    verifier: bool,
    log_path,
    cancel_requested,
    submission_callback=None,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Execute and strictly validate one primary or blind-verifier request."""
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
    _resolve_output_reservation(
        profile,
        batch_id,
        questions,
        system_prompt,
        user_prompt,
        schema,
    )
    if callable(submission_callback):
        submission_callback(
            "verifier" if verifier else "primary",
            batch_id,
            questions,
        )
    response = llm_provider_service.chat_json(
        profile,
        system_prompt,
        user_prompt,
        log_path=log_path,
        log_context={
            "operation": "cleanup",
            "pass": "verifier" if verifier else "primary",
        },
        cancel_requested=cancel_requested,
        structured_output=True,
        response_schema=schema,
        response_schema_name="audiomancer_cleanup_answers",
        require_response_schema=True,
        allow_unconstrained_fallback=False,
        allow_model_json_repair=False,
        retry_count_override=0,
    )
    answers = _validate_answers(response.get("payload"), batch_id, questions)
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
    expected = {
        str(item["question_id"]): set(item["choices"])
        for item in questions
    }
    answers: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in payload["answers"]:
        if not isinstance(item, dict) or set(item) != {"question_id", "choice"}:
            raise ValueError("Cleanup AI answer fields are invalid.")
        question_id = str(item["question_id"])
        choice = str(item["choice"])
        if (
            question_id not in expected
            or question_id in seen
            or choice not in expected[question_id]
        ):
            raise ValueError(
                "Cleanup AI answer references an invalid question or choice."
            )
        seen.add(question_id)
        answers.append({"question_id": question_id, "choice": choice})
    if seen != set(expected):
        raise ValueError("Cleanup AI response did not answer the complete batch.")
    return answers


def _answer_schema(
    batch_id: str,
    questions: list[dict[str, object]],
) -> dict[str, object]:
    """Build the exact JSON Schema for one question batch."""
    question_ids = [str(item["question_id"]) for item in questions]
    choices = sorted(
        {
            str(choice)
            for item in questions
            for choice in item["choices"]
        }
    )
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
                        "question_id": {
                            "type": "string",
                            "enum": question_ids,
                        },
                        "choice": {
                            "type": "string",
                            "enum": choices,
                        },
                    },
                },
            },
        },
    }


def _normalized_questions(
    questions: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Normalize stable IDs and omit strong deterministic decisions."""
    normalized = []
    for index, source in enumerate(questions, start=1):
        item = dict(source)
        if str(item.get("prior_confidence") or "") == "strong":
            continue
        item["question_id"] = str(item.get("question_id") or f"q-{index:06d}")
        normalized.append(item)
    return normalized


def _homogeneous_batches(
    questions: list[dict[str, object]],
    batch_size: int,
) -> list[list[dict[str, object]]]:
    """Group questions by type and split them into stable context-tier batches."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in questions:
        grouped[str(item["question_type"])].append(item)
    return [
        group[start : start + batch_size]
        for question_type in sorted(grouped)
        for group in (grouped[question_type],)
        for start in range(0, len(group), batch_size)
    ]


def _batch_size_for_context(context_window: int) -> int:
    """Return the approved 4/8/16 context-tier batch size."""
    if context_window >= 128_000:
        return 16
    if context_window >= 32_000:
        return 8
    return 4


def _compatibility_warning(
    profile: dict[str, object] | None,
) -> str | None:
    """Return why one profile cannot be used for Cleanup adjudication."""
    if profile is None:
        return "AI profile was not selected; deterministic priors were used."
    if not bool(profile.get("supports_structured_output", False)):
        return (
            "AI profile does not support strict structured output; "
            "deterministic priors were used."
        )
    if int(profile.get("context_window", 0) or 0) < MINIMUM_CONTEXT_WINDOW:
        return (
            "AI profile context window is below 16K; "
            "deterministic priors were used."
        )
    return None


def _resolve_output_reservation(
    profile: dict[str, object],
    batch_id: str,
    questions: list[dict[str, object]],
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, object],
) -> int:
    """
    @brief      Resolve one request's output-token reservation.
    @details    The operator's configured profile limit, lowered to whatever the
                safe context ceiling still leaves free. Returning the value the
                budget decision used keeps the request from carrying a different
                limit than the one it was admitted under.
    @param[in]  profile Normalized AI profile payload.
    @param[in]  batch_id Identifier the answers must echo.
    @param[in]  questions Questions this request must answer.
    @param[in]  system_prompt System-role prompt body.
    @param[in]  user_prompt User-role prompt body.
    @param[in]  schema JSON Schema sent as the structured-output contract.
    @return     Output-token reservation for this request.
    @exception  ContextBudgetExceededError Raised when the free room cannot hold
                the answers this request has to produce.
    """
    estimated_input = (
        len(system_prompt.encode("utf-8"))
        + len(user_prompt.encode("utf-8"))
        + len(json.dumps(schema, ensure_ascii=False).encode("utf-8"))
    ) // 2
    ceiling = int(int(profile["context_window"]) * _SAFE_CONTEXT_FRACTION)
    reservation = min(
        int(profile.get("output_reserve_tokens", config.DEFAULT_LLM_OUTPUT_RESERVE_TOKENS)),
        ceiling - estimated_input,
    )
    if reservation < _answer_token_floor(batch_id, questions):
        raise ContextBudgetExceededError(
            "Cleanup question batch exceeds the safe context budget."
        )
    return reservation


def _answer_token_floor(
    batch_id: str,
    questions: list[dict[str, object]],
) -> int:
    """
    @brief      Tokens the largest answer document for one batch can need.
    @details    Every question paired with its longest choice, counted at one
                token per UTF-8 byte rather than at the input estimator's byte
                pair rate: answer JSON is punctuation-dense, and a floor that
                under-counts admits a request that truncates instead of
                splitting one that does not fit.
    @param[in]  batch_id Identifier the answers must echo.
    @param[in]  questions Questions this request must answer.
    @return     Smallest reservation that can still hold the answers.
    @exception  None
    """
    largest_answers = {
        "batch_id": batch_id,
        "answers": [
            {
                "question_id": str(item["question_id"]),
                "choice": max(
                    (str(choice) for choice in item["choices"]),
                    key=len,
                    default="",
                ),
            }
            for item in questions
        ],
    }
    return len(json.dumps(largest_answers, ensure_ascii=False).encode("utf-8"))


def _resume_pass_answers(
    questions: list[dict[str, object]],
    resume_answers: dict[str, dict[str, object]],
    field: str,
) -> list[dict[str, str]] | None:
    """Return a complete persisted pass or None when any answer is absent."""
    result = []
    for question in questions:
        question_id = str(question["question_id"])
        value = resume_answers.get(question_id, {}).get(field)
        if value is None:
            return None
        result.append(
            {
                "question_id": question_id,
                "choice": str(value),
            }
        )
    return result


def _completed_record(
    question: dict[str, object],
    primary_choice: str,
    verifier_choice: str | None,
) -> dict[str, object]:
    """Resolve one completed primary/verifier outcome against its prior."""
    prior_choice = str(question.get("prior_choice") or "")
    accepted = (
        primary_choice != prior_choice
        and verifier_choice == primary_choice
    )
    return {
        "question_id": str(question["question_id"]),
        "primary_choice": primary_choice,
        "verifier_choice": verifier_choice,
        "accepted": accepted,
        "final_choice": primary_choice if accepted else prior_choice,
    }


def _fallback_record(question: dict[str, object]) -> dict[str, object]:
    """Build one deterministic fallback answer."""
    return {
        "question_id": str(question["question_id"]),
        "primary_choice": None,
        "verifier_choice": None,
        "accepted": False,
        "final_choice": str(question.get("prior_choice") or ""),
        "state": "fallback",
    }


def _combine_split_results(left, right):
    """Combine two recursive batch results while preserving source order."""
    return (
        left[0] + right[0],
        left[1] + right[1],
        token_usage_service.merge_token_usage(left[2], right[2]),
        left[3] + right[3],
    )


def _result(
    answers: list[dict[str, object]],
    warnings: list[str],
    usage: dict[str, object],
    failed_batch_count: int,
    batch_order: list[list[str]],
) -> dict[str, object]:
    """Build one complete adjudication result."""
    return {
        "answers": answers,
        "warnings": warnings,
        "token_usage": usage,
        "failed_batch_count": failed_batch_count,
        "batch_order": batch_order,
        "estimated_request_count": 0,
    }


def _emit_progress(
    callback: Callable[[int, int, str], None] | None,
    current: int,
    total: int,
    message: str,
) -> None:
    """Emit one truthful AI work-unit update, expanding totals as needed."""
    if callable(callback):
        bounded_current = max(0, int(current))
        bounded_total = max(1, int(total), bounded_current)
        callback(bounded_current, bounded_total, message)


# END OF FILE
