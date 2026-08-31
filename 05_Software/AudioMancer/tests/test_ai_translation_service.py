#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_translation_service.py
@brief Focused monofile-contract tests for AudioMancer AI Translation.
@details Verifies strict persistence, current-profile resume, interruption,
         review writes, same-language processing, and safe retranslation.
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import ai_translation_service, operation_runtime_service, project_workspace_service
from chunking_test_support import build_chunking_document

# PUBLIC API


def test_translation_document_is_the_only_authoritative_artifact(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 persists only the strict authoritative document.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationMonofile")
    _install_translations(monkeypatch, ["Traducerea unu", "Traducerea doi"])

    summary = ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
        additional_translation_instructions="Pastreaza registrul formal.",
    )

    document = json.loads((project_root / config.TRANSLATED_CHUNKS_FILE_NAME).read_text(encoding="utf-8"))
    assert set(document) == {
        "target_language",
        "status",
        "token_usage",
        "budget_metadata",
        "additional_translation_instructions",
        "chunks",
    }
    assert document["status"] == ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING
    assert document["additional_translation_instructions"] == "Pastreaza registrul formal."
    assert document["chunks"] == [
        {"chunk_id": "chunk-0001", "translated_text": "Traducerea unu", "approved": False},
        {"chunk_id": "chunk-0002", "translated_text": "Traducerea doi", "approved": False},
    ]
    assert all(set(item) == {"chunk_id", "translated_text", "approved"} for item in document["chunks"])
    assert not (project_root / "translation_report.json").exists()
    assert not (project_root / "translation_state.json").exists()
    assert summary["status"] == ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING
    assert summary["translated_count"] == 2
    assert summary["approved_count"] == 0


def test_translation_resume_uses_first_empty_chunk_and_current_profile_budget(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 resume skips completed chunks and uses the current profile.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationResume")
    ai_translation_service.write_translation_document(
        project_root,
        {
            "target_language": "ro",
            "status": ai_translation_service.TRANSLATION_STATUS_FAILED,
            "token_usage": _usage(30, 10),
            "budget_metadata": _budget(4096),
            "additional_translation_instructions": "Pastreaza numele proprii.",
            "chunks": [
                {"chunk_id": "chunk-0001", "translated_text": "Traducere existenta", "approved": False},
                {"chunk_id": "chunk-0002", "translated_text": "", "approved": False},
            ],
        },
    )
    calls = _install_translations(monkeypatch, ["Traducere noua"])
    current_profile = {**_profile_payload(), "id": "profile-2", "context_window": 8192}

    ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        current_profile,
        "ro",
        additional_translation_instructions=None,
    )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert len(calls) == 1
    assert document["chunks"][0]["translated_text"] == "Traducere existenta"
    assert document["chunks"][1]["translated_text"] == "Traducere noua"
    assert document["budget_metadata"]["context_window"] == 8192
    assert document["additional_translation_instructions"] == "Pastreaza numele proprii."
    assert document["token_usage"]["total_tokens"] == 55


@pytest.mark.parametrize(
    "persisted_status",
    [
        ai_translation_service.TRANSLATION_STATUS_RUNNING,
        ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS,
        ai_translation_service.TRANSLATION_STATUS_CANCELLED,
        ai_translation_service.TRANSLATION_STATUS_FAILED,
    ],
)
def test_resumable_translation_status_retains_stored_instructions(
    monkeypatch,
    tmp_path,
    persisted_status,
) -> None:
    """
    @brief      Verify resumable documents retain their persisted instruction contract.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  persisted_status Resumable status under test.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, f"ResumeInstructions{persisted_status}")
    _write_translation_document(
        project_root,
        persisted_status,
        [
            {"chunk_id": "chunk-0001", "translated_text": "Traducere existenta", "approved": False},
            {"chunk_id": "chunk-0002", "translated_text": "", "approved": False},
        ],
        instructions="Instructiuni pastrate",
    )
    prompts = _install_translations(monkeypatch, ["Traducere noua"])

    ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
        additional_translation_instructions="Instructiuni noi ignorate",
    )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert document["additional_translation_instructions"] == "Instructiuni pastrate"
    assert "Instructiuni pastrate" in prompts[0]
    assert "Instructiuni noi ignorate" not in prompts[0]


@pytest.mark.parametrize(
    "persisted_status",
    [
        ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
        ai_translation_service.TRANSLATION_STATUS_COMPLETED,
    ],
)
def test_non_resumable_translation_uses_normalized_new_instructions_everywhere(
    monkeypatch,
    tmp_path,
    persisted_status,
) -> None:
    """
    @brief      Verify a non-resume path uses one normalized caller instruction value.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  persisted_status Non-resumable status under test.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, f"RestartInstructions{persisted_status}")
    _write_translation_document(
        project_root,
        persisted_status,
        [{"chunk_id": "chunk-0001", "translated_text": "Traducere existenta", "approved": True}],
        instructions="Instructiuni vechi",
    )
    prompts = _install_translations(monkeypatch, ["Traducere noua"])
    budget_instructions: list[str] = []
    original_build_budget = ai_translation_service._build_budget_metadata

    def capture_budget_instructions(*args, **kwargs):
        """Capture the instruction value supplied to budget calculation."""
        budget_instructions.append(str(args[3]))
        return original_build_budget(*args, **kwargs)

    monkeypatch.setattr(ai_translation_service, "_build_budget_metadata", capture_budget_instructions)

    ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
        additional_translation_instructions="  Instructiuni noi  ",
    )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert budget_instructions == ["Instructiuni noi"]
    assert "Instructiuni noi" in prompts[0]
    assert "Instructiuni vechi" not in prompts[0]
    assert document["additional_translation_instructions"] == "Instructiuni noi"


def test_non_resumable_translation_without_new_instructions_retains_stored_value(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify an absent non-resume argument does not clear stored instructions.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "RestartInstructionsNone")
    _write_translation_document(
        project_root,
        ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
        [{"chunk_id": "chunk-0001", "translated_text": "Traducere existenta", "approved": False}],
        instructions="Instructiuni pastrate",
    )
    prompts = _install_translations(monkeypatch, ["Traducere noua"])

    ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
        additional_translation_instructions=None,
    )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert document["additional_translation_instructions"] == "Instructiuni pastrate"
    assert "Instructiuni pastrate" in prompts[0]


def test_new_translation_normalizes_instructions_for_budget_prompt_and_persistence(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify a new document consistently uses normalized caller instructions.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "NewInstructionsNormalized")
    prompts = _install_translations(monkeypatch, ["Traducere unu", "Traducere doi"])
    budget_instructions: list[str] = []
    original_build_budget = ai_translation_service._build_budget_metadata

    def capture_budget_instructions(*args, **kwargs):
        """Capture the instruction value supplied to budget calculation."""
        budget_instructions.append(str(args[3]))
        return original_build_budget(*args, **kwargs)

    monkeypatch.setattr(ai_translation_service, "_build_budget_metadata", capture_budget_instructions)

    ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
        additional_translation_instructions="  Instructiuni normalizate  ",
    )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert budget_instructions == ["Instructiuni normalizate"]
    assert all("Instructiuni normalizate" in prompt for prompt in prompts)
    assert document["additional_translation_instructions"] == "Instructiuni normalizate"


@pytest.mark.parametrize(
    ("raised_error", "expected_status"),
    [
        (RuntimeError("provider unavailable"), ai_translation_service.TRANSLATION_STATUS_FAILED),
        (
            operation_runtime_service.OperationCancelledError("cancelled"),
            ai_translation_service.TRANSLATION_STATUS_CANCELLED,
        ),
    ],
)
def test_translation_cancel_and_failure_preserve_completed_chunks(
    monkeypatch,
    tmp_path,
    raised_error,
    expected_status,
) -> None:
    """
    @brief      Verify REQ-FUNC-004 terminal interruption keeps prior completed chunks.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  raised_error Controlled exception used to exercise a failure path.
    @param[in]  expected_status Expected status used by the assertion.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, f"Translation{expected_status}")
    responses = iter(
        [
            {"payload": {"translated_text": "Traducere pastrata"}, "usage": _usage(10, 5)},
            raised_error,
        ]
    )

    def fake_chat_json(*_args, **_kwargs):
        """
        @brief      Return one translation and then raise the requested terminal error.
        @param[in]  _args Ignored positional arguments accepted by the test double.
        @param[in]  _kwargs Ignored keyword arguments accepted by the test double.
        @return     Controlled AI chat response payload.
        @exception  Exception Raised when the next controlled response is an exception.
        """
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(ai_translation_service.llm_provider_service, "chat_json", fake_chat_json)

    with pytest.raises(type(raised_error)):
        ai_translation_service.start_or_continue_translation(project_root, manifest, _profile_payload(), "ro")

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert document["status"] == expected_status
    assert document["chunks"][0]["translated_text"] == "Traducere pastrata"
    assert document["chunks"][1]["translated_text"] == ""
    assert document["token_usage"]["total_tokens"] == 15


@pytest.mark.parametrize(
    "raised_error",
    [
        RuntimeError("provider unavailable"),
        operation_runtime_service.OperationCancelledError("cancelled"),
    ],
)
def test_retranslate_interruption_preserves_completed_review_state(
    monkeypatch,
    tmp_path,
    raised_error,
) -> None:
    """
    @brief      Verify interrupted retranslation leaves completed review state available.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  raised_error Controlled exception used to exercise interruption handling.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, f"TranslationSafe{type(raised_error).__name__}")
    original_chunks = [
        {"chunk_id": "chunk-0001", "translated_text": "Text aprobat", "approved": True},
        {"chunk_id": "chunk-0002", "translated_text": "Alt text aprobat", "approved": True},
    ]
    _write_translation_document(
        project_root,
        ai_translation_service.TRANSLATION_STATUS_COMPLETED,
        original_chunks,
        instructions="Reguli generale",
    )
    monkeypatch.setattr(
        ai_translation_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(raised_error),
    )

    with pytest.raises(type(raised_error), match=str(raised_error)):
        ai_translation_service.retranslate_chunk(
            project_root,
            manifest,
            _profile_payload(),
            "ro",
            "chunk-0001",
            additional_translation_instructions="Regula doar pentru retraducere",
        )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert document["status"] == ai_translation_service.TRANSLATION_STATUS_COMPLETED
    assert document["chunks"] == original_chunks
    assert document["additional_translation_instructions"] == "Reguli generale"
    assert ai_translation_service.translation_is_completed(project_root) is True


@pytest.mark.parametrize(
    ("persisted_status", "chunks", "expected_status"),
    [
        (
            ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
            [
                {"chunk_id": "chunk-0001", "translated_text": "Text unu", "approved": False},
                {"chunk_id": "chunk-0002", "translated_text": "Text doi", "approved": True},
            ],
            ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
        ),
        (
            ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS,
            [
                {"chunk_id": "chunk-0001", "translated_text": "Text unu", "approved": True},
                {"chunk_id": "chunk-0002", "translated_text": "", "approved": False},
            ],
            ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS,
        ),
    ],
)
def test_retranslate_failure_rederives_status_from_unchanged_chunks(
    monkeypatch,
    tmp_path,
    persisted_status,
    chunks,
    expected_status,
) -> None:
    """
    @brief      Verify failed retranslation derives status from unchanged review records.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  persisted_status Persisted fixture status before the attempt.
    @param[in]  chunks Complete ordered chunk fixtures under test.
    @param[in]  expected_status Review-derived status expected after failure.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, f"RetranslateDerived{persisted_status}")
    _write_translation_document(project_root, persisted_status, chunks)
    monkeypatch.setattr(
        ai_translation_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        ai_translation_service.retranslate_chunk(
            project_root,
            manifest,
            _profile_payload(),
            "ro",
            "chunk-0001",
        )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert document["status"] == expected_status
    assert document["chunks"] == chunks


def test_retranslate_segment_failure_persists_usage_without_partial_text(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify paid retranslation segments persist usage but not partial text.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "RetranslateSegmentFailure")
    original_chunks = [
        {"chunk_id": "chunk-0001", "translated_text": "Text aprobat", "approved": True},
        {"chunk_id": "chunk-0002", "translated_text": "Alt text aprobat", "approved": True},
    ]
    _write_translation_document(
        project_root,
        ai_translation_service.TRANSLATION_STATUS_COMPLETED,
        original_chunks,
    )
    monkeypatch.setattr(
        ai_translation_service,
        "_split_translation_source_text",
        lambda *_args: [
            ai_translation_service._TranslationTextSegment("segment one", False),
            ai_translation_service._TranslationTextSegment("segment two", True),
        ],
    )
    responses = iter(
        [
            {"payload": {"translated_text": "segment tradus"}, "usage": _usage(10, 5)},
            RuntimeError("second segment failed"),
        ]
    )

    def fake_chat_json(*_args, **_kwargs):
        """Return one paid segment and fail the second provider request."""
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(ai_translation_service.llm_provider_service, "chat_json", fake_chat_json)

    with pytest.raises(RuntimeError, match="second segment failed"):
        ai_translation_service.retranslate_chunk(
            project_root,
            manifest,
            _profile_payload(),
            "ro",
            "chunk-0001",
        )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert document["status"] == ai_translation_service.TRANSLATION_STATUS_COMPLETED
    assert document["token_usage"]["total_tokens"] == 15
    assert document["chunks"] == original_chunks


def test_successful_retranslation_clears_only_selected_approval_and_keeps_general_instructions(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify successful one-off retranslation preserves unrelated review state.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "RetranslateSuccess")
    _write_translation_document(
        project_root,
        ai_translation_service.TRANSLATION_STATUS_COMPLETED,
        [
            {"chunk_id": "chunk-0001", "translated_text": "Text aprobat", "approved": True},
            {"chunk_id": "chunk-0002", "translated_text": "Alt text aprobat", "approved": True},
        ],
        instructions="Reguli generale",
    )
    prompts = _install_translations(monkeypatch, ["Text retradus"])

    ai_translation_service.retranslate_chunk(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
        "chunk-0001",
        additional_translation_instructions="Regula unica",
    )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert document["status"] == ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING
    assert document["chunks"][0] == {
        "chunk_id": "chunk-0001",
        "translated_text": "Text retradus",
        "approved": False,
    }
    assert document["chunks"][1] == {
        "chunk_id": "chunk-0002",
        "translated_text": "Alt text aprobat",
        "approved": True,
    }
    assert "Regula unica" in prompts[0]
    assert document["additional_translation_instructions"] == "Reguli generale"


def test_same_language_translation_uses_llm(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 same-language translation remains AI-assisted.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationSameLanguage")
    manifest["original_language"] = "en"
    calls = _install_translations(monkeypatch, ["Rewritten one", "Rewritten two"])

    ai_translation_service.start_or_continue_translation(project_root, manifest, _profile_payload(), "en")

    assert len(calls) == 2
    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert [item["translated_text"] for item in document["chunks"]] == ["Rewritten one", "Rewritten two"]


def test_translation_document_writes_once_per_completed_chunk_and_review_action(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-NFR-016 uses one atomic document write per durable event.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationWriteCount")
    _install_translations(monkeypatch, ["Traducere unu", "Traducere doi"])
    writes = []
    original_writer = ai_translation_service.write_json_atomic

    def spy_write(path, payload, **kwargs):
        """
        @brief      Record authoritative document writes while preserving persistence.
        @param[in]  path Filesystem path for path.
        @param[in]  payload Candidate structured payload.
        @param[in]  kwargs Keyword arguments forwarded to the test double.
        @return     None.
        """
        writes.append(path)
        original_writer(path, payload, **kwargs)

    monkeypatch.setattr(ai_translation_service, "write_json_atomic", spy_write)
    ai_translation_service.start_or_continue_translation(project_root, manifest, _profile_payload(), "ro")
    assert len(writes) == 4  # running, two completed chunks, review_pending

    writes.clear()
    ai_translation_service.approve_chunk(project_root, "chunk-0001")
    assert len(writes) == 1


def test_invalid_translation_document_is_rejected_without_overwrite(tmp_path) -> None:
    """
    @brief      Verify REQ-NFR-016 incompatible data is rejected and left untouched.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationStrictLoad")
    translation_path = project_root / config.TRANSLATED_CHUNKS_FILE_NAME
    invalid_text = json.dumps([{"chunk_id": "chunk-0001", "translated_text": "Invalid root"}]) + "\n"
    translation_path.write_text(invalid_text, encoding="utf-8")

    with pytest.raises(ai_translation_service.TranslationDocumentError, match="Reset Translation"):
        ai_translation_service.start_or_continue_translation(project_root, manifest, _profile_payload(), "ro")

    assert translation_path.read_text(encoding="utf-8") == invalid_text


def test_translation_budget_reserves_output_and_rejects_insufficient_input() -> None:
    """
    @brief      Verify current-profile budgeting reserves output capacity before requests.
    @return     None.
    """
    small = ai_translation_service._build_budget_metadata(
        {**_profile_payload(), "context_window": 8192, "output_reserve_tokens": 4096},
        "ro",
        "system",
    )
    large = ai_translation_service._build_budget_metadata(
        {**_profile_payload(), "context_window": 8192, "output_reserve_tokens": 6144},
        "ro",
        "system",
    )
    assert large["text_budget_tokens"] < small["text_budget_tokens"]

    with pytest.raises(ValueError, match="too little room"):
        ai_translation_service._build_budget_metadata(
            {**_profile_payload(), "context_window": 1024, "output_reserve_tokens": 900},
            "ro",
            "system",
        )


def test_translation_budget_is_bounded_by_profile_reply_capacity() -> None:
    """
    @brief      Verify REQ-FUNC-6c7c71d9 bounds source text by what the reply can return.
    @return     None.
    """
    context_window = 32_768
    output_reserve_tokens = 8192

    metadata = ai_translation_service._build_budget_metadata(
        {
            **_profile_payload(),
            "context_window": context_window,
            "output_reserve_tokens": output_reserve_tokens,
        },
        "ro",
        "system",
    )

    assert metadata["text_budget_tokens"] <= output_reserve_tokens
    assert metadata["text_budget_tokens"] < int(
        context_window * config.DEFAULT_AI_TRANSLATION_TEXT_CONTEXT_FRACTION
    )


def test_translation_refuses_a_profile_whose_reply_capacity_is_too_low() -> None:
    """
    @brief      Verify REQ-FUNC-cfa5468c names the output limit when it cannot fund a request.
    @return     None.
    """
    with pytest.raises(ValueError, match="maximum output tokens"):
        ai_translation_service._build_budget_metadata(
            {**_profile_payload(), "context_window": 16_384, "output_reserve_tokens": 512},
            "ro",
            "system",
        )


def test_budgeted_translation_preserves_paragraph_breaks_across_requests(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify separate source paragraphs retain a paragraph break across provider requests.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationParagraphRequests")
    _replace_source_chunks(
        project_root,
        [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "P1 P2 P3 P4\n\nQ1 Q2 Q3 Q4"}],
    )
    monkeypatch.setattr(ai_translation_service, "_estimate_text_tokens", lambda text: len(text.split()))
    monkeypatch.setattr(
        ai_translation_service,
        "_build_budget_metadata",
        lambda *_args, **_kwargs: {**_budget(4096), "text_budget_tokens": 4},
    )
    prompts = _install_translations(monkeypatch, ["TP1 TP2 TP3 TP4", "TQ1 TQ2 TQ3 TQ4"])

    ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
    )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert len(prompts) == 2
    assert "Source text:\nP1 P2 P3 P4\n\nReturn JSON" in prompts[0]
    assert "Source text:\nQ1 Q2 Q3 Q4\n\nReturn JSON" in prompts[1]
    assert document["chunks"][0]["translated_text"] == "TP1 TP2 TP3 TP4\n\nTQ1 TQ2 TQ3 TQ4"


def test_budgeted_translation_rejoins_oversized_paragraph_continuations(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify oversized continuation requests use spaces while mixed true boundaries remain paragraphs.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationContinuationRequests")
    _replace_source_chunks(
        project_root,
        [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "A1 A2 A3 A4 A5 A6\n\nB1 B2"}],
    )
    monkeypatch.setattr(ai_translation_service, "_estimate_text_tokens", lambda text: len(text.split()))
    monkeypatch.setattr(
        ai_translation_service,
        "_build_budget_metadata",
        lambda *_args, **_kwargs: {**_budget(4096), "text_budget_tokens": 4},
    )
    prompts = _install_translations(monkeypatch, ["TA1 TA2 TA3 TA4", "TA5 TA6\n\nTB1 TB2"])

    ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
    )

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert len(prompts) == 2
    assert "Source text:\nA1 A2 A3 A4\n\nReturn JSON" in prompts[0]
    assert "Source text:\nA5 A6\n\nB1 B2\n\nReturn JSON" in prompts[1]
    assert document["chunks"][0]["translated_text"] == "TA1 TA2 TA3 TA4 TA5 TA6\n\nTB1 TB2"


def test_translation_prompt_has_stable_rules_and_minimal_user_contract(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 keeps stable rules separate from per-request translation data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationPromptContract")
    captured: list[tuple[str, str]] = []

    def fake_chat_json(_profile, system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture both prompt roles and return a valid minimal response.
        @param[in]  _profile AI profile argument intentionally unused by the test double.
        @param[in]  system_prompt Rendered system prompt for the AI request.
        @param[in]  user_prompt Rendered user prompt inspected by the test double.
        @param[in]  _kwargs Ignored keyword arguments accepted by the test double.
        @return     Controlled AI chat response payload.
        """
        captured.append((system_prompt, user_prompt))
        return {"payload": {"translated_text": "Traducere"}, "usage": _usage(10, 5)}

    monkeypatch.setattr(ai_translation_service.llm_provider_service, "chat_json", fake_chat_json)
    ai_translation_service.start_or_continue_translation(
        project_root,
        manifest,
        _profile_payload(),
        "ro",
        additional_translation_instructions="Pastreaza numele proprii.",
    )

    system_prompt, user_prompt = captured[0]
    assert "translated_text" in system_prompt
    assert "Original one" not in system_prompt
    assert "Target language: ro" not in system_prompt
    assert "Target language: ro" in user_prompt
    assert "Additional translation instructions:" in user_prompt
    assert "Pastreaza numele proprii." in user_prompt
    assert "Source text:" in user_prompt
    assert "Original one" in user_prompt
    assert "fingerprint" not in user_prompt.lower()
    assert "regex" not in user_prompt.lower()


def test_manual_translation_edit_preserves_operator_whitespace(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 manual review persists the operator's exact text value.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "TranslationWhitespace")
    ai_translation_service.write_translation_document(
        project_root,
        {
            "target_language": "ro",
            "status": ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS,
            "token_usage": _usage(0, 0),
            "budget_metadata": _budget(4096),
            "additional_translation_instructions": "",
            "chunks": [
                {"chunk_id": "chunk-0001", "translated_text": "", "approved": False},
                {"chunk_id": "chunk-0002", "translated_text": "", "approved": False},
            ],
        },
    )

    ai_translation_service.update_translated_text(project_root, "chunk-0001", "\nTraducere exacta\n")

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert document["chunks"][0]["translated_text"] == "\nTraducere exacta\n"


def test_partial_segment_failure_preserves_usage_without_partial_chunk(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-004 a failed later segment keeps usage but no partial chunk text.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunked_project(tmp_path, "TranslationSegmentFailure")
    monkeypatch.setattr(
        ai_translation_service,
        "_split_translation_source_text",
        lambda *_args: [
            ai_translation_service._TranslationTextSegment("segment one", False),
            ai_translation_service._TranslationTextSegment("segment two", True),
        ],
    )
    responses = iter(
        [
            {"payload": {"translated_text": "segment tradus"}, "usage": _usage(10, 5)},
            RuntimeError("second segment failed"),
        ]
    )

    def fake_chat_json(*_args, **_kwargs):
        """
        @brief      Return one paid segment and fail the next segment.
        @param[in]  _args Ignored positional arguments accepted by the test double.
        @param[in]  _kwargs Ignored keyword arguments accepted by the test double.
        @return     Controlled AI chat response payload.
        @exception  Exception Raised when the next controlled response is an exception.
        """
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(ai_translation_service.llm_provider_service, "chat_json", fake_chat_json)

    with pytest.raises(RuntimeError, match="second segment failed"):
        ai_translation_service.start_or_continue_translation(project_root, manifest, _profile_payload(), "ro")

    document = ai_translation_service.load_translation_document(project_root)
    assert document is not None
    assert document["status"] == ai_translation_service.TRANSLATION_STATUS_FAILED
    assert document["token_usage"]["total_tokens"] == 15
    assert document["chunks"][0]["translated_text"] == ""


# TEST HELPERS


def _install_translations(monkeypatch, translations: list[str]) -> list[str]:
    """
    @brief      Install deterministic provider responses and return captured user prompts.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @param[in]  translations Ordered controlled translation responses.
    @return     Callable returning controlled translation responses.
    """
    captured_prompts: list[str] = []
    responses = iter(translations)

    def fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Return the next deterministic translation response.
        @param[in]  _profile AI profile argument intentionally unused by the test double.
        @param[in]  _system_prompt System prompt intentionally unused by the test double.
        @param[in]  user_prompt Rendered user prompt inspected by the test double.
        @param[in]  _kwargs Ignored keyword arguments accepted by the test double.
        @return     Controlled AI chat response payload.
        """
        captured_prompts.append(user_prompt)
        return {"payload": {"translated_text": next(responses)}, "usage": _usage(10, 5)}

    monkeypatch.setattr(ai_translation_service.llm_provider_service, "chat_json", fake_chat_json)
    return captured_prompts


def _write_translation_document(
    project_root,
    status: str,
    chunks: list[dict[str, object]],
    instructions: str = "Instructiuni pastrate",
) -> None:
    """
    @brief      Persist one strict translation-document fixture.
    @param[in]  project_root Active project root folder.
    @param[in]  status Persisted translation status token.
    @param[in]  chunks Ordered translated-chunk fixtures.
    @param[in]  instructions General persisted translation instructions.
    @return     None.
    """
    ai_translation_service.write_translation_document(
        project_root,
        {
            "target_language": "ro",
            "status": status,
            "token_usage": _usage(0, 0),
            "budget_metadata": _budget(4096),
            "additional_translation_instructions": instructions,
            "chunks": chunks,
        },
    )


def _replace_source_chunks(project_root, chunks: list[dict[str, object]]) -> None:
    """
    @brief      Replace canonical source chunks for one focused translation-path fixture.
    @param[in]  project_root Active project root folder.
    @param[in]  chunks Ordered compact chunk payloads.
    @return     None.
    """
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(build_chunking_document(chunks), indent=2) + "\n",
        encoding="utf-8",
    )


def _create_chunked_project(tmp_path, name: str):
    """
    @brief      Create one project with two canonical source chunks.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  name Stable name associated with the requested object.
    @return     Created project root and manifest payload.
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-07-16T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["target_language"] = "ro"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            build_chunking_document(
                [
                    {
                        "chunk_id": "chunk-0001",
                        "sequence_index": 1,
                        "chapter_label": "Chapter I",
                        "text": "Original one",
                        "source_start_line": 1,
                        "source_end_line": 1,
                        "chunking_mode": "deterministic",
                        "semantic_strategy": None,
                        "scene_note": None,
                    },
                    {
                        "chunk_id": "chunk-0002",
                        "sequence_index": 2,
                        "chapter_label": "Chapter I",
                        "text": "Original two",
                        "source_start_line": 3,
                        "source_end_line": 3,
                        "chunking_mode": "deterministic",
                        "semantic_strategy": None,
                        "scene_note": None,
                    },
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, manifest


def _profile_payload() -> dict[str, object]:
    """Return one enabled OpenAI-compatible profile payload."""
    return {
        "id": "profile-1",
        "label": "Translation Profile",
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234",
        "api_key": "",
        "model_name": "qwen3-8b",
        "context_window": 4096,
        "output_reserve_tokens": 2048,
        "request_timeout_seconds": 30,
        "temperature": 0.2,
        "supports_structured_output": False,
        "enabled": True,
    }


def _usage(input_tokens: int, output_tokens: int) -> dict[str, object]:
    """Build normalized provider token usage."""
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "usage_available": True,
    }


def _budget(context_window: int) -> dict[str, int]:
    """Build complete persisted budget metadata for strict-loader fixtures."""
    return {
        "context_window": context_window,
        "output_reserve_tokens": 512,
        "prompt_budget_tokens": 100,
        "text_budget_tokens": 2048,
        "safety_margin_tokens": 512,
    }


# END OF FILE
