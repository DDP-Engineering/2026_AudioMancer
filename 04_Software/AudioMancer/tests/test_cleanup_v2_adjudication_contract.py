#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_v2_adjudication_contract.py
@brief Red-first checks for bounded model-agnostic Cleanup adjudication.
@details Verifies context tiers, selective verification, retry isolation,
         recursive splitting, and deterministic fallback.
@author Eng. Dan Dumitru Pasare
@date 2026-07-28
@version 0.1.0
"""

from __future__ import annotations

import json

from audiomancer.services import (
    cleanup_ai_adjudication_service,
    prompt_template_service,
)
from cleanup_v2_test_support import make_profile


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


def test_cleanup_prompts_never_request_removed_choices() -> None:
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
        assert "choose preserve" not in normalized
        assert "join_without_space" not in normalized
        assert "listed choices" in normalized
        assert "do not invent" in normalized


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


def _question(index: int, *, prior_choice: str = "join_with_space") -> dict[str, object]:
    """Build one medium-confidence boundary question."""
    return {
        "question_id": f"q-{index + 1:06d}",
        "question_type": "line_boundary",
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
