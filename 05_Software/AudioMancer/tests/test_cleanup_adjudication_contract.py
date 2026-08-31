#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_adjudication_contract.py
@brief Red-first checks for bounded model-agnostic Cleanup adjudication.
@details Verifies context tiers, selective verification, retry isolation,
         recursive splitting, and deterministic fallback.
"""

from __future__ import annotations

import json

from audiomancer.services import (
    cleanup_ai_adjudication_service,
    prompt_template_service,
)
from cleanup_test_support import make_profile


def test_context_tiers_use_4_8_and_16_question_batches(monkeypatch) -> None:
    """Cover S-0006 and REQ-FUNC-70c1289d-d4c2-45c5-9ed1-97705824cc75."""
    observed: dict[int, list[int]] = {}

    def _run(context_window: int, question_count: int) -> None:
        batch_sizes: list[int] = []

        def _chat_json(_profile, _system, user_prompt, **_kwargs):
            payload = json.loads(user_prompt)
            batch_sizes.append(len(payload["questions"]))
            return {
                "payload": {
                    "batch_id": payload["batch_id"],
                    "answers": [
                        {
                            "question_id": item["question_id"],
                            "choice": "join_with_space",
                        }
                        for item in payload["questions"]
                    ],
                },
                "usage": {},
            }

        monkeypatch.setattr(cleanup_ai_adjudication_service.llm_provider_service, "chat_json", _chat_json)
        cleanup_ai_adjudication_service.adjudicate_questions(
            [_question(index) for index in range(question_count)],
            make_profile(context_window=context_window),
        )
        observed[context_window] = batch_sizes

    _run(16_384, 5)
    _run(32_768, 9)
    _run(131_072, 17)

    assert observed == {
        16_384: [4, 1],
        32_768: [8, 1],
        131_072: [16, 1],
    }


def test_authoritative_plan_matches_mixed_type_runtime_batches(monkeypatch) -> None:
    """Verify persisted-plan inputs and runtime top-level requests cannot drift."""
    questions = [
        _question(index, question_type=("line_boundary" if index % 3 else "hyphenation"))
        for index in range(13)
    ]
    profile = make_profile(context_window=16_384)
    planned = cleanup_ai_adjudication_service.plan_question_batches(
        questions,
        profile,
    )
    runtime: list[tuple[str, list[str]]] = []

    def _chat_json(_profile, _system, user_prompt, **_kwargs):
        payload = json.loads(user_prompt)
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": item["question_id"],
                        "choice": "join_with_space",
                    }
                    for item in payload["questions"]
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(
        cleanup_ai_adjudication_service.llm_provider_service,
        "chat_json",
        _chat_json,
    )
    result = cleanup_ai_adjudication_service.adjudicate_questions(
        questions,
        profile,
        request_callback=lambda _pass, batch_id, batch, _answers, _usage: runtime.append(
            (batch_id, [str(item["target_id"]) for item in batch])
        ),
    )

    planned_targets = [
        [str(item["target_id"]) for item in batch]
        for batch in planned
    ]
    assert planned_targets == [
        ["b-000001", "b-000004", "b-000007", "b-000010"],
        ["b-000013"],
        ["b-000002", "b-000003", "b-000005", "b-000006"],
        ["b-000008", "b-000009", "b-000011", "b-000012"],
    ]
    assert runtime == [
        (f"cleanup-batch-{index:04d}", targets)
        for index, targets in enumerate(planned_targets, start=1)
    ]
    assert result["batch_order"] == planned_targets
    assert result["estimated_request_count"] == len(planned_targets) * 2


def test_unusable_profile_has_no_authoritative_request_plan() -> None:
    """A deterministic-only run must not advertise fictitious AI work."""
    questions = [_question(index) for index in range(5)]
    profile = make_profile(supports_structured_output=False)

    assert cleanup_ai_adjudication_service.plan_question_batches(
        questions,
        profile,
    ) == []
    result = cleanup_ai_adjudication_service.adjudicate_questions(
        questions,
        profile,
    )
    assert result["batch_order"] == []
    assert result["estimated_request_count"] == 0


def test_resume_uses_durable_multi_question_request_baseline(monkeypatch) -> None:
    """One resumed multi-question primary pass contributes one request."""
    questions = [_question(index) for index in range(4)]
    resume_answers = {
        str(item["question_id"]): {
            "primary_choice": "set_paragraph_break",
            "verifier_choice": None,
        }
        for item in questions
    }
    progress: list[tuple[int, int]] = []
    passes: list[str] = []

    def _chat_json(_profile, _system, user_prompt, **kwargs):
        passes.append(str(kwargs["log_context"]["pass"]))
        payload = json.loads(user_prompt)
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": item["question_id"],
                        "choice": "set_paragraph_break",
                    }
                    for item in payload["questions"]
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(
        cleanup_ai_adjudication_service.llm_provider_service,
        "chat_json",
        _chat_json,
    )
    cleanup_ai_adjudication_service.adjudicate_questions(
        questions,
        make_profile(context_window=16_384),
        resume_answers=resume_answers,
        completed_request_count=1,
        progress_callback=lambda current, total, _message: progress.append(
            (current, total)
        ),
    )

    assert passes == ["verifier"]
    assert progress == [(2, 2)]


def test_completed_primary_and_verifier_resume_invents_no_requests(monkeypatch) -> None:
    """A completed two-pass batch resumes without a provider call."""
    questions = [_question(index) for index in range(4)]
    resume_answers = {
        str(item["question_id"]): {
            "primary_choice": "set_paragraph_break",
            "verifier_choice": "set_paragraph_break",
        }
        for item in questions
    }
    monkeypatch.setattr(
        cleanup_ai_adjudication_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Completed provider passes must not be repeated.")
        ),
    )

    result = cleanup_ai_adjudication_service.adjudicate_questions(
        questions,
        make_profile(context_window=16_384),
        resume_answers=resume_answers,
        completed_request_count=2,
    )

    assert result["estimated_request_count"] == 2
    assert all(item["accepted"] for item in result["answers"])


def test_recursive_splits_expand_request_progress_total(monkeypatch) -> None:
    """Actual split requests remain visible when they exceed the estimate."""
    progress: list[tuple[int, int]] = []

    def _ask(_profile, _batch_id, questions, *, verifier, log_path, cancel_requested):
        _ = verifier, log_path, cancel_requested
        if len(questions) > 1:
            raise cleanup_ai_adjudication_service.ContextBudgetExceededError(
                "split"
            )
        return (
            [
                {
                    "question_id": questions[0]["question_id"],
                    "choice": questions[0]["prior_choice"],
                }
            ],
            {},
        )

    monkeypatch.setattr(cleanup_ai_adjudication_service, "_ask", _ask)
    cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(index) for index in range(4)],
        make_profile(context_window=16_384),
        progress_callback=lambda current, total, _message: progress.append(
            (current, total)
        ),
    )

    assert progress == [(1, 2), (2, 2), (3, 3), (4, 4)]
    assert all(current <= total for current, total in progress)


def test_primary_agreement_keeps_prior_without_verifier(monkeypatch) -> None:
    """Cover S-0006 and REQ-FUNC-809ebb96-da19-4ccf-86ff-1648f7aeb047."""
    passes: list[str] = []

    def _chat_json(_profile, _system, user_prompt, **kwargs):
        passes.append(str(kwargs["log_context"]["pass"]))
        payload = json.loads(user_prompt)
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": payload["questions"][0]["question_id"],
                        "choice": "join_with_space",
                    }
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(cleanup_ai_adjudication_service.llm_provider_service, "chat_json", _chat_json)

    result = cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(0, prior_choice="join_with_space")],
        make_profile(),
    )

    assert passes == ["primary"]
    assert result["answers"][0]["accepted"] is False
    assert result["answers"][0]["final_choice"] == "join_with_space"


def test_matching_primary_and_verifier_may_override_prior(monkeypatch) -> None:
    """Cover S-0006 and REQ-FUNC-809ebb96-da19-4ccf-86ff-1648f7aeb047."""
    passes: list[str] = []

    def _chat_json(_profile, _system, user_prompt, **kwargs):
        passes.append(str(kwargs["log_context"]["pass"]))
        payload = json.loads(user_prompt)
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": payload["questions"][0]["question_id"],
                        "choice": "set_paragraph_break",
                    }
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(cleanup_ai_adjudication_service.llm_provider_service, "chat_json", _chat_json)

    result = cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(0, prior_choice="join_with_space")],
        make_profile(),
    )

    assert passes == ["primary", "verifier"]
    assert result["answers"][0] == {
        "question_id": "q-000001",
        "primary_choice": "set_paragraph_break",
        "verifier_choice": "set_paragraph_break",
        "accepted": True,
        "final_choice": "set_paragraph_break",
    }


def test_verifier_disagreement_keeps_deterministic_prior(monkeypatch) -> None:
    """Cover S-0006 and REQ-FUNC-809ebb96-da19-4ccf-86ff-1648f7aeb047."""
    choices = iter(("set_paragraph_break", "set_semantic_line_break"))

    def _chat_json(_profile, _system, user_prompt, **_kwargs):
        payload = json.loads(user_prompt)
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": payload["questions"][0]["question_id"],
                        "choice": next(choices),
                    }
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(cleanup_ai_adjudication_service.llm_provider_service, "chat_json", _chat_json)

    result = cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(0, prior_choice="join_with_space")],
        make_profile(),
    )

    assert result["answers"][0]["accepted"] is False
    assert result["answers"][0]["final_choice"] == "join_with_space"


def test_invalid_batch_retries_once_then_falls_back_and_continues(monkeypatch) -> None:
    """Cover S-0005/S-0006 and REQ-FUNC-9dcf0271-5fc7-4f07-9f58-885ca9f2f153."""
    call_count = {"value": 0}
    successful_batch_ids: list[str] = []

    def _chat_json(_profile, _system, user_prompt, **_kwargs):
        call_count["value"] += 1
        payload = json.loads(user_prompt)
        if call_count["value"] <= 2:
            return {"payload": {"invalid": True}, "usage": {}}
        successful_batch_ids.append(str(payload["batch_id"]))
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": item["question_id"],
                        "choice": "join_with_space",
                    }
                    for item in payload["questions"]
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(cleanup_ai_adjudication_service.llm_provider_service, "chat_json", _chat_json)

    result = cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(index) for index in range(5)],
        make_profile(context_window=16_384),
    )

    assert call_count["value"] == 3
    assert successful_batch_ids == ["cleanup-batch-0002"]
    assert result["failed_batch_count"] == 1
    assert [item["state"] for item in result["answers"][:4]] == ["fallback"] * 4
    assert result["answers"][4]["state"] == "completed"


def test_oversized_batch_splits_recursively_and_single_question_falls_back(monkeypatch) -> None:
    """Cover S-0006 and REQ-FUNC-70c1289d-d4c2-45c5-9ed1-97705824cc75."""
    observed_sizes: list[int] = []

    def _ask(_profile, _batch_id, questions, *, verifier, log_path, cancel_requested):
        _ = verifier, log_path, cancel_requested
        observed_sizes.append(len(questions))
        if len(questions) > 1:
            raise cleanup_ai_adjudication_service.ContextBudgetExceededError("too large")
        if questions[0]["question_id"] == "q-000003":
            raise cleanup_ai_adjudication_service.ContextBudgetExceededError("single too large")
        return (
            [
                {
                    "question_id": questions[0]["question_id"],
                    "choice": questions[0]["prior_choice"],
                }
            ],
            {},
        )

    monkeypatch.setattr(cleanup_ai_adjudication_service, "_ask", _ask)

    result = cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(index) for index in range(4)],
        make_profile(context_window=16_384),
    )

    assert observed_sizes == [4, 2, 1, 1, 2, 1, 1]
    assert result["answers"][2]["state"] == "fallback"
    assert result["failed_batch_count"] == 1


def test_incompatible_profile_uses_priors_without_provider_calls(monkeypatch) -> None:
    """Cover S-0005 and REQ-FUNC-26df5531-3acf-4c18-98ab-06d4e79112eb."""
    monkeypatch.setattr(
        cleanup_ai_adjudication_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("An incompatible profile must not call the provider.")
        ),
    )

    result = cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(0)],
        make_profile(supports_structured_output=False),
    )

    assert result["answers"][0]["state"] == "fallback"
    assert result["answers"][0]["final_choice"] == "join_with_space"
    assert result["failed_batch_count"] == 0


def test_cleanup_prompts_require_listed_choices() -> None:
    """Cover S-0006 and the strict adjudication-choice contract."""
    prompts = [
        prompt_template_service.load_prompt(
            "text_cleanup_adjudication_primary_system"
        ),
        prompt_template_service.load_prompt(
            "text_cleanup_adjudication_verifier_system"
        ),
    ]

    for prompt in prompts:
        normalized = prompt.casefold()
        assert "listed choices" in normalized
        assert "do not invent" in normalized


def test_cleanup_prompts_state_the_required_response_shape() -> None:
    """Cover REQ-FUNC-84cd9f47."""
    prompts = [
        prompt_template_service.load_prompt(
            "text_cleanup_adjudication_primary_system"
        ),
        prompt_template_service.load_prompt(
            "text_cleanup_adjudication_verifier_system"
        ),
    ]

    for prompt in prompts:
        normalized = prompt.casefold()
        for field_name in ("batch_id", "answers", "question_id", "choice"):
            assert field_name in normalized
        # The request supplies "questions" and the response owes "answers"; a
        # provider that leaves the schema unenforced needs that said out loud.
        assert "questions" in normalized
        assert normalized.index("answers") != normalized.index("questions")


def test_ai_adjudication_reports_each_primary_and_verifier_request(
    monkeypatch,
) -> None:
    """Cover S-0006/S-0010 and request-level progress reporting."""
    progress: list[tuple[int, int, str]] = []

    def _chat_json(_profile, _system, user_prompt, **_kwargs):
        payload = json.loads(user_prompt)
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": item["question_id"],
                        "choice": "set_paragraph_break",
                    }
                    for item in payload["questions"]
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(
        cleanup_ai_adjudication_service.llm_provider_service,
        "chat_json",
        _chat_json,
    )

    cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(0, prior_choice="join_with_space")],
        make_profile(),
        progress_callback=lambda current, total, message: progress.append(
            (current, total, message)
        ),
    )

    assert [(current, total) for current, total, _message in progress] == [
        (1, 2),
        (2, 2),
    ]
    assert "Primary" in progress[0][2]
    assert "Verifier" in progress[1][2]


def test_output_reservation_follows_profile_limit_and_context_ceiling() -> None:
    """Cover REQ-FUNC-644ff463."""
    system_prompt = "S" * 100
    schema = {"type": "object"}
    # (100 + 100 + 18) // 2 for the two prompts and the serialized schema.
    short_prompt_input_tokens = 109

    roomy = cleanup_ai_adjudication_service._resolve_output_reservation(
        make_profile(context_window=131_072, output_reserve_tokens=4_096),
        "cleanup-batch-0001",
        [_question(0)],
        system_prompt,
        "U" * 100,
        schema,
    )
    assert roomy == 4_096

    clamped = cleanup_ai_adjudication_service._resolve_output_reservation(
        make_profile(context_window=16_000, output_reserve_tokens=65_535),
        "cleanup-batch-0001",
        [_question(0)],
        system_prompt,
        "U" * 100,
        schema,
    )
    assert clamped == int(16_000 * 0.70) - short_prompt_input_tokens


def test_answer_room_below_the_answer_document_is_context_oversized() -> None:
    """Cover REQ-FUNC-644ff463."""
    # This prompt leaves 41 tokens under the ceiling: room to spare, but far
    # too little to hold even a one-question answer document.
    try:
        cleanup_ai_adjudication_service._resolve_output_reservation(
            make_profile(context_window=16_000, output_reserve_tokens=65_535),
            "cleanup-batch-0001",
            [_question(0)],
            "S" * 100,
            "U" * 22_200,
            {"type": "object"},
        )
    except cleanup_ai_adjudication_service.ContextBudgetExceededError:
        return
    raise AssertionError("An answer document that cannot fit must be context-oversized.")


def test_configured_output_limit_below_the_answer_document_splits_the_batch(monkeypatch) -> None:
    """Cover REQ-FUNC-644ff463."""
    batch_sizes: list[int] = []

    def _chat_json(_profile, _system, user_prompt, **_kwargs):
        payload = json.loads(user_prompt)
        batch_sizes.append(len(payload["questions"]))
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": item["question_id"],
                        "choice": "join_with_space",
                    }
                    for item in payload["questions"]
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(cleanup_ai_adjudication_service.llm_provider_service, "chat_json", _chat_json)
    # A 16-question answer document needs about 1100 tokens, so this profile's
    # own output limit - not its 128K context - is what the batch cannot fit.
    cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(index) for index in range(16)],
        make_profile(context_window=131_072, output_reserve_tokens=1_024),
    )

    assert batch_sizes == [8, 8]


def test_adjudication_request_keeps_output_reservation_local(monkeypatch) -> None:
    """Cleanup plans its reservation without sending an output-limit override."""
    observed_kwargs: list[dict[str, object]] = []

    def _chat_json(_profile, _system, user_prompt, **kwargs):
        observed_kwargs.append(dict(kwargs))
        payload = json.loads(user_prompt)
        return {
            "payload": {
                "batch_id": payload["batch_id"],
                "answers": [
                    {
                        "question_id": item["question_id"],
                        "choice": "join_with_space",
                    }
                    for item in payload["questions"]
                ],
            },
            "usage": {},
        }

    monkeypatch.setattr(cleanup_ai_adjudication_service.llm_provider_service, "chat_json", _chat_json)
    cleanup_ai_adjudication_service.adjudicate_questions(
        [_question(index) for index in range(3)],
        make_profile(context_window=131_072, output_reserve_tokens=4_096),
    )

    assert all("output_reserve_tokens_override" not in kwargs for kwargs in observed_kwargs)


def _question(
    index: int,
    *,
    prior_choice: str = "join_with_space",
    question_type: str = "line_boundary",
) -> dict[str, object]:
    """Build one medium-confidence boundary question."""
    return {
        "question_id": f"q-{index + 1:06d}",
        "question_type": question_type,
        "target_id": f"b-{index + 1:06d}",
        "left_text": f"Wrapped line {index}",
        "right_text": "continues here.",
        "choices": [
            "join_with_space",
            "set_paragraph_break",
            "set_semantic_line_break",
        ],
        "prior_choice": prior_choice,
        "prior_confidence": "medium",
    }


# END OF FILE
