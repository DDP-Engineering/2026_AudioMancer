#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009

import pytest

from audiomancer.services import book_analysis_state_service, llm_provider_service


def _settings() -> dict[str, object]:
    return {
        "default_book_analysis_profile_id": "profile-a",
        "llm_profiles": [
            {
                "id": "profile-a",
                "label": "Profile A",
                "enabled": True,
                "backend_kind": "lmstudio",
                "base_url": "http://localhost:1234/v1",
                "model_name": "model-a",
                "context_window": 16_384,
                "output_reserve_tokens": 2_048,
                "request_timeout_seconds": 120,
                "temperature": 0.2,
                "supports_structured_output": True,
                "reasoning_mode": "disabled",
            }
        ],
    }


def test_build_book_analysis_profile_state_uses_workflow_default() -> None:
    state = book_analysis_state_service.build_book_analysis_profile_state(_settings())

    assert state == {
        "entries": [("Profile A", "profile-a")],
        "selected_profile_id": "profile-a",
    }


def test_book_analysis_tests_use_no_live_provider() -> None:
    with pytest.raises(AssertionError, match="must not open network"):
        llm_provider_service.request.urlopen("http://127.0.0.1:1")


@pytest.mark.parametrize(
    ("state_name", "can_analyze", "can_reset"),
    (
        ("ready", True, False),
        ("running", False, True),
        ("interrupted", True, True),
        ("fresh_completed", False, True),
        ("stale_completed", True, True),
    ),
)
def test_book_analysis_control_state(
    state_name: str,
    can_analyze: bool,
    can_reset: bool,
    monkeypatch,
    tmp_path,
) -> None:
    chunks = [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Book text"}]
    monkeypatch.setattr(
        book_analysis_state_service.chunking_document_service,
        "load_chunking_document",
        lambda _root: {"status": "completed"},
    )
    monkeypatch.setattr(
        book_analysis_state_service.chunking_document_service,
        "load_chunks",
        lambda _root: chunks,
    )
    candidate = None
    completed = None
    operation_is_active = state_name == "running"
    if state_name in {"running", "interrupted"}:
        candidate = {"status": "running"}
    if state_name in {"fresh_completed", "stale_completed"}:
        completed = {"report": {"concise": {}, "details": {}}}
    monkeypatch.setattr(
        book_analysis_state_service.book_analysis_document_service,
        "load_document",
        lambda _root: {
            "schema_version": 1,
            "completed_report": completed,
            "candidate_run": candidate,
        }
        if candidate is not None or completed is not None
        else None,
    )
    monkeypatch.setattr(
        book_analysis_state_service.book_analysis_document_service,
        "completed_report_is_stale",
        lambda *_args: state_name == "stale_completed",
    )
    monkeypatch.setattr(
        book_analysis_state_service.book_analysis_document_service,
        "candidate_resume_matches",
        lambda *_args, **_kwargs: candidate is not None,
    )

    manifest: dict[str, object] = {"target_language": "ro"}
    if operation_is_active:
        manifest["operations"] = {"book_analysis": {"status": "running"}}
    state = book_analysis_state_service.build_book_analysis_state(
        tmp_path,
        manifest,
        "en",
        _settings(),
        "profile-a",
        operation_is_active=operation_is_active,
    )

    assert state["state"] == state_name
    assert state["can_analyze"] is can_analyze
    assert state["can_reset"] is can_reset


def test_book_analysis_without_completed_chunks_is_unavailable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        book_analysis_state_service.chunking_document_service,
        "load_chunking_document",
        lambda _root: None,
    )

    state = book_analysis_state_service.build_book_analysis_state(
        tmp_path,
        {"target_language": "ro"},
        "en",
        _settings(),
        "profile-a",
    )

    assert state["state"] == "unavailable"
    assert state["can_analyze"] is False
    assert state["can_reset"] is False


def test_started_operation_enables_reset_before_first_checkpoint(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        book_analysis_state_service.chunking_document_service,
        "load_chunking_document",
        lambda _root: {"status": "completed"},
    )
    monkeypatch.setattr(
        book_analysis_state_service.chunking_document_service,
        "load_chunks",
        lambda _root: [
            {"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Book text"}
        ],
    )
    monkeypatch.setattr(
        book_analysis_state_service.book_analysis_document_service,
        "load_document",
        lambda _root: None,
    )

    state = book_analysis_state_service.build_book_analysis_state(
        tmp_path,
        {
            "target_language": "ro",
            "operations": {"book_analysis": {"status": "running"}},
        },
        "en",
        _settings(),
        "profile-a",
        operation_is_active=True,
    )

    assert state["state"] == "running"
    assert state["can_analyze"] is False
    assert state["can_reset"] is True
