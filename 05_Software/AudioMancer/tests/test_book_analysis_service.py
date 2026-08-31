#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009

import json

import pytest

from audiomancer.services import book_analysis_document_service, book_analysis_service, chunking_document_service
from audiomancer.services.operation_runtime_service import OperationCancelledError


def _profile(profile_id: str = "profile-a") -> dict[str, object]:
    return {
        "id": profile_id,
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234/v1",
        "model_name": "any-compatible-model",
        "context_window": 16_384,
        "output_reserve_tokens": 2_048,
        "request_timeout_seconds": 120,
        "temperature": 0.2,
        "supports_structured_output": True,
        "reasoning_mode": "disabled",
    }


def _write_completed_chunks(project_root, texts: list[str]) -> None:
    chunks = [
        {
            "chunk_id": f"chunk-{index:04d}",
            "sequence_index": index,
            "text": text,
            "cleanup_boundary_confidence": "high",
            "cleanup_joined_across_page_break": False,
            "cleanup_warning_flags": [],
            "cleanup_role": "body",
            "starts_after_scene_separator": False,
        }
        for index, text in enumerate(texts, start=1)
    ]
    document = chunking_document_service.build_document(
        status="completed",
        mode="deterministic",
        source_text="\n".join(texts),
        chunks=chunks,
    )
    chunking_document_service.write_chunking_document(project_root, document)


def _intermediate(summary: str = "Summary") -> dict[str, object]:
    return {
        "summary": summary,
        "characters": [{"name": "Ana", "role": "protagonist"}],
        "subjects": ["memory"],
        "themes": ["identity"],
        "settings": ["Bucharest"],
        "narrative_notes": ["third-person limited"],
        "audiobook_notes": ["restrained suspense"],
        "uncertainties": [],
    }


def _report() -> dict[str, object]:
    return {
        "concise": {
            "book_type": "novel",
            "genres": ["mystery"],
            "subjects": ["memory"],
            "setting_time": ["Bucharest, present day"],
            "summary": "Ana investigates a hidden archive.",
            "main_characters": [{"name": "Ana", "role": "protagonist"}],
            "themes": ["identity"],
        },
        "details": {
            "detailed_summary": "Ana follows the archive's history.",
            "supporting_characters": [],
            "narrative_perspective": "third-person limited",
            "narrative_structure": "linear",
            "tone": ["intimate"],
            "pacing": "measured",
            "diction": "literary and direct",
            "emotional_range": ["curiosity", "resolve"],
            "audiobook_guidance": {
                "narration_style": "restrained suspense",
                "character_voice_notes": [],
            },
            "uncertainties": [],
            "source_evidence": [
                {"chunk_ids": ["chunk-0001"], "note": "Introduces Ana."}
            ],
        },
    }


def _usage() -> dict[str, object]:
    return {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "usage_available": True,
    }


def _install_budget(monkeypatch, source_budget: int = 2, item_tokens: int = 1) -> None:
    monkeypatch.setattr(
        book_analysis_service.book_analysis_budget_service,
        "build_request_budget",
        lambda *_args, **_kwargs: {
            "context_window": 16_384,
            "source_budget_tokens": source_budget,
            "output_reserve_tokens": 2_048,
            "reasoning_reserve_tokens": 0,
            "prompt_reserve_tokens": 100,
            "safety_reserve_tokens": 819,
            "reasoning_mode": "disabled",
        },
    )
    monkeypatch.setattr(
        book_analysis_service,
        "_estimate_item_tokens",
        lambda _item: item_tokens,
    )


def _install_successful_provider(monkeypatch) -> dict[str, list[object]]:
    calls: dict[str, list[object]] = {
        "leaf_chunk_ids": [],
        "consolidation_sizes": [],
        "prompts": [],
        "log_paths": [],
        "log_contexts": [],
    }

    def fake_chat_json(_profile_payload, _system_prompt, user_prompt, **kwargs):
        schema_name = kwargs["response_schema_name"]
        marker = "SOURCE_JSON:\n"
        source_items = json.loads(user_prompt.split(marker, maxsplit=1)[1])
        calls["prompts"].append(user_prompt)
        calls["log_paths"].append(kwargs.get("log_path"))
        calls["log_contexts"].append(kwargs.get("log_context"))
        if schema_name == "book_analysis_leaf":
            calls["leaf_chunk_ids"].append([item["chunk_id"] for item in source_items])
            return {"payload": _intermediate(), "usage": _usage()}
        if schema_name == "book_analysis_report":
            return {"payload": _report(), "usage": _usage()}
        calls["consolidation_sizes"].append(len(source_items))
        return {"payload": _intermediate("Consolidated"), "usage": _usage()}

    monkeypatch.setattr(book_analysis_service.llm_provider_service, "chat_json", fake_chat_json)
    return calls


def test_analyze_book_resumes_after_validated_leaf_without_repeating_it(
    monkeypatch,
    tmp_path,
) -> None:
    _write_completed_chunks(tmp_path, ["one", "two", "three", "four"])
    cancelled = {"value": False}
    leaf_chunk_ids: list[list[str]] = []

    _install_budget(monkeypatch)

    def fake_chat_json(_profile_payload, _system_prompt, user_prompt, **kwargs):
        schema_name = kwargs["response_schema_name"]
        if schema_name == "book_analysis_leaf":
            marker = "SOURCE_JSON:\n"
            source_items = json.loads(user_prompt.split(marker, maxsplit=1)[1])
            leaf_chunk_ids.append([item["chunk_id"] for item in source_items])
            if len(leaf_chunk_ids) == 1:
                cancelled["value"] = True
            return {"payload": _intermediate(), "usage": _usage()}
        if schema_name == "book_analysis_report":
            return {"payload": _report(), "usage": _usage()}
        return {"payload": _intermediate("Consolidated"), "usage": _usage()}

    monkeypatch.setattr(book_analysis_service.llm_provider_service, "chat_json", fake_chat_json)

    with pytest.raises(OperationCancelledError):
        book_analysis_service.analyze_book(
            tmp_path,
            _profile(),
            "ro",
            cancel_requested=lambda: cancelled["value"],
        )

    first_document = book_analysis_document_service.load_document(tmp_path)
    assert first_document is not None
    first_leaf = first_document["candidate_run"]["leaf_summaries"][0]
    assert first_document["candidate_run"]["status"] == "cancelled"
    assert len(first_document["candidate_run"]["leaf_summaries"]) == 1

    cancelled["value"] = False
    report = book_analysis_service.analyze_book(tmp_path, _profile(), "ro")

    assert leaf_chunk_ids.count(first_leaf["chunk_ids"]) == 1
    assert report["status"] == "completed"


def test_analyze_book_covers_every_chunk_once_in_order(monkeypatch, tmp_path) -> None:
    _write_completed_chunks(tmp_path, ["one", "two", "three", "four", "five"])
    _install_budget(monkeypatch)
    calls = _install_successful_provider(monkeypatch)

    result = book_analysis_service.analyze_book(tmp_path, _profile(), "ro")

    flattened = [chunk_id for window in calls["leaf_chunk_ids"] for chunk_id in window]
    assert flattened == [f"chunk-{index:04d}" for index in range(1, 6)]
    assert result["status"] == "completed"


def test_ai_requests_share_candidate_transaction_log(monkeypatch, tmp_path) -> None:
    _write_completed_chunks(tmp_path, ["one", "two", "three", "four"])
    _install_budget(monkeypatch)
    calls = _install_successful_provider(monkeypatch)

    book_analysis_service.analyze_book(tmp_path, _profile(), "ro")

    document = book_analysis_document_service.load_document(tmp_path)
    run_token = document["candidate_run"]["run_id"].replace("-", "")
    expected_path = tmp_path / f"log_ai_book_analysis_{run_token}.log"
    assert calls["log_paths"]
    assert set(calls["log_paths"]) == {expected_path}
    assert all(
        context["operation_kind"] == "book_analysis"
        for context in calls["log_contexts"]
    )
    assert {context["stage_label"] for context in calls["log_contexts"]} == {
        "leaf",
        "consolidation",
        "final_report",
    }


def test_analyze_book_builds_recursive_consolidation_levels(monkeypatch, tmp_path) -> None:
    _write_completed_chunks(tmp_path, [str(index) for index in range(8)])
    _install_budget(monkeypatch)
    calls = _install_successful_provider(monkeypatch)

    book_analysis_service.analyze_book(tmp_path, _profile(), "ro")

    document = book_analysis_document_service.load_document(tmp_path)
    assert document is not None
    assert len(document["candidate_run"]["consolidation_levels"]) == 2
    assert calls["consolidation_sizes"] == [2, 2, 2]


def test_invalid_leaf_response_is_checkpointed_as_failure_not_success(
    monkeypatch,
    tmp_path,
) -> None:
    _write_completed_chunks(tmp_path, ["one"])
    _install_budget(monkeypatch)
    monkeypatch.setattr(
        book_analysis_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {"payload": {"summary": "incomplete"}, "usage": _usage()},
    )

    with pytest.raises(book_analysis_document_service.BookAnalysisDocumentError):
        book_analysis_service.analyze_book(tmp_path, _profile(), "ro")

    document = book_analysis_document_service.load_document(tmp_path)
    assert document is not None
    assert document["candidate_run"]["status"] == "failed"
    assert document["candidate_run"]["leaf_summaries"] == []


def test_different_profile_replaces_candidate_but_preserves_completed_report(
    monkeypatch,
    tmp_path,
) -> None:
    _write_completed_chunks(tmp_path, ["old source"])
    _install_budget(monkeypatch)
    _install_successful_provider(monkeypatch)
    book_analysis_service.analyze_book(tmp_path, _profile("profile-a"), "ro")
    original_document = book_analysis_document_service.load_document(tmp_path)
    original_completed = original_document["completed_report"]

    _write_completed_chunks(tmp_path, ["changed source", "second chunk"])
    cancelled = {"value": False}

    def cancel_after_leaf(_profile_payload, _system_prompt, _user_prompt, **kwargs):
        if kwargs["response_schema_name"] == "book_analysis_leaf":
            cancelled["value"] = True
        return {"payload": _intermediate(), "usage": _usage()}

    monkeypatch.setattr(book_analysis_service.llm_provider_service, "chat_json", cancel_after_leaf)
    with pytest.raises(OperationCancelledError):
        book_analysis_service.analyze_book(
            tmp_path,
            _profile("profile-b"),
            "ro",
            cancel_requested=lambda: cancelled["value"],
        )

    changed_document = book_analysis_document_service.load_document(tmp_path)
    assert changed_document["completed_report"] == original_completed
    assert changed_document["candidate_run"]["profile_id"] == "profile-b"


def test_context_overflow_repacks_once_with_smaller_budget(monkeypatch, tmp_path) -> None:
    _write_completed_chunks(tmp_path, ["one", "two"])
    _install_budget(monkeypatch, source_budget=4, item_tokens=2)
    monkeypatch.setattr(
        book_analysis_service,
        "_estimate_item_tokens",
        lambda item: 2 if "text" in item else 1,
    )
    attempts = {"overflow": 0}
    successful_leaf_windows: list[list[str]] = []

    def fake_chat_json(_profile_payload, _system_prompt, user_prompt, **kwargs):
        schema_name = kwargs["response_schema_name"]
        source_items = json.loads(user_prompt.split("SOURCE_JSON:\n", maxsplit=1)[1])
        if schema_name == "book_analysis_leaf":
            if attempts["overflow"] == 0:
                attempts["overflow"] += 1
                raise RuntimeError("provider error: context_length_exceeded")
            successful_leaf_windows.append([item["chunk_id"] for item in source_items])
            return {"payload": _intermediate(), "usage": _usage()}
        if schema_name == "book_analysis_report":
            return {"payload": _report(), "usage": _usage()}
        return {"payload": _intermediate("Consolidated"), "usage": _usage()}

    monkeypatch.setattr(book_analysis_service.llm_provider_service, "chat_json", fake_chat_json)

    book_analysis_service.analyze_book(tmp_path, _profile(), "ro")

    document = book_analysis_document_service.load_document(tmp_path)
    assert attempts["overflow"] == 1
    assert successful_leaf_windows == [["chunk-0001"], ["chunk-0002"]]
    assert document["candidate_run"]["budget"]["source_budget_tokens"] == 3
    assert document["candidate_run"]["budget"]["overflow_retry_used"] is True


def test_oversized_single_chunk_sends_no_provider_request(monkeypatch, tmp_path) -> None:
    _write_completed_chunks(tmp_path, ["oversized"])
    _install_budget(monkeypatch, source_budget=2, item_tokens=3)
    provider_called = {"value": False}

    def fail_if_called(*_args, **_kwargs):
        provider_called["value"] = True
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(book_analysis_service.llm_provider_service, "chat_json", fail_if_called)

    with pytest.raises(ValueError, match="Text Chunking"):
        book_analysis_service.analyze_book(tmp_path, _profile(), "ro")

    assert provider_called["value"] is False


def test_completed_report_uses_project_target_language(monkeypatch, tmp_path) -> None:
    _write_completed_chunks(tmp_path, ["one"])
    _install_budget(monkeypatch)
    calls = _install_successful_provider(monkeypatch)

    book_analysis_service.analyze_book(tmp_path, _profile(), "Romanian")

    document = book_analysis_document_service.load_document(tmp_path)
    assert document["completed_report"]["target_language"] == "Romanian"
    assert all("Romanian" in prompt for prompt in calls["prompts"])


def test_final_report_has_every_concise_and_detail_field(monkeypatch, tmp_path) -> None:
    _write_completed_chunks(tmp_path, ["one"])
    _install_budget(monkeypatch)
    _install_successful_provider(monkeypatch)

    result = book_analysis_service.analyze_book(tmp_path, _profile(), "ro")

    assert set(result["report"]["concise"]) == {
        "book_type",
        "genres",
        "subjects",
        "setting_time",
        "summary",
        "main_characters",
        "themes",
    }
    assert set(result["report"]["details"]) == {
        "detailed_summary",
        "supporting_characters",
        "narrative_perspective",
        "narrative_structure",
        "tone",
        "pacing",
        "diction",
        "emotional_range",
        "audiobook_guidance",
        "uncertainties",
        "source_evidence",
    }
