#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chunking_single_document_contract.py
@brief Red-first contract tests for the authoritative Chunking document.
@details Covers S-0001 through S-0007 and the linked functional and data
         requirements for exact persistence, resume, projections, and routing.
"""

# IMPORTS

from copy import deepcopy
from hashlib import sha256
from importlib import import_module
import inspect
import json
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import (
    ai_chunking_service,
    deterministic_chunking_service,
    operation_runtime_service,
    project_workspace_service,
    text_chunking_state_service,
)
from chunking_test_support import write_cleanup_input

# CONSTANTS

_DOCUMENT_FIELDS = {
    "status",
    "mode",
    "manual_adjusted",
    "source_fingerprint",
    "plan_fingerprint",
    "request_fingerprint",
    "semantic_strategy",
    "additional_chunking_instructions",
    "token_usage",
    "warnings",
    "next_paragraph",
    "context_window_fallback_count",
    "chunks",
}
_CHUNK_FIELDS = {
    "chunk_id",
    "sequence_index",
    "text",
    "source_paragraph_start",
    "source_paragraph_end",
    "cleanup_boundary_confidence",
    "cleanup_joined_across_page_break",
    "cleanup_warning_flags",
    "cleanup_role",
    "starts_after_scene_separator",
}
_FORBIDDEN_PERSISTED_FIELDS = {
    "schema_version",
    "metadata",
    "progress_current",
    "progress_total",
    "warning_count",
    "budget_metadata",
    "profile_runtime_metadata",
    "profile_usage_history",
    "ai_profile_id",
    "model_name",
    "temperature",
    "context_window",
    "output_reserve_tokens",
    "transaction_log_path",
}


# TESTS


def test_document_api_round_trips_exact_contract_and_returns_defensive_chunks(tmp_path) -> None:
    """
    @brief Verify S-0001, REQ-FUNC-048, and REQ-DATA-001 strict document persistence.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    service = _chunking_document_service()
    document = _valid_document(
        [_chunk("chunk-0001", 1, "Chapter I\nOpening paragraph.")],
        source_text="Chapter I\nOpening paragraph.\n",
    )

    written_path = service.write_chunking_document(tmp_path, document)
    loaded = service.load_chunking_document(tmp_path)
    chunks = service.load_chunks(tmp_path)

    assert written_path == tmp_path / config.CHUNK_ARTIFACT_FILE_NAME
    assert loaded == document
    assert set(loaded) == _DOCUMENT_FIELDS
    assert set(loaded["chunks"][0]) == _CHUNK_FIELDS
    chunks[0]["text"] = "mutated caller copy"
    assert service.load_chunks(tmp_path)[0]["text"] == "Chapter I\nOpening paragraph."
    assert service.load_chunking_document(tmp_path / "missing") is None
    assert service.load_chunks(tmp_path / "missing") == []


def test_document_api_rejects_non_boolean_scene_boundary_flag(tmp_path) -> None:
    """@brief Cover S-0016 and REQ-FUNC-d08915c2-cdea-49bf-a769-7e6405f38012."""
    service = _chunking_document_service()
    document = _valid_document([_chunk("chunk-0001", 1, "Opening paragraph.")])
    document["chunks"][0]["starts_after_scene_separator"] = "yes"

    with pytest.raises(service.IncompatibleChunkingDocumentError) as error:
        service.write_chunking_document(tmp_path, document)
    assert isinstance(error.value.__cause__, TypeError)
    assert "scene-separator boundary flag" in str(error.value.__cause__)


@pytest.mark.parametrize(
    ("case_name", "payload_factory"),
    [
        ("non-object root", lambda: []),
        ("extra root field", lambda: {**_valid_document(), "metadata": {}}),
        (
            "missing root field",
            lambda: {key: value for key, value in _valid_document().items() if key != "warnings"},
        ),
        ("invalid source fingerprint", lambda: {**_valid_document(), "source_fingerprint": "not-a-hash"}),
        (
            "completed document with checkpoint",
            lambda: {**_valid_document(), "next_paragraph": 1},
        ),
        (
            "negative token usage",
            lambda: {
                **_valid_document(),
                "token_usage": {
                    "input_tokens": -1,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "usage_available": True,
                },
            },
        ),
        (
            "extra chunk field",
            lambda: _valid_document([{**_chunk("chunk-0001", 1, "Text"), "source_start_line": 1}]),
        ),
        (
            "missing scene boundary field",
            lambda: _valid_document(
                [
                    {
                        key: value
                        for key, value in _chunk("chunk-0001", 1, "Text").items()
                        if key != "starts_after_scene_separator"
                    }
                ]
            ),
        ),
        (
            "out of order chunk",
            lambda: _valid_document([_chunk("chunk-0002", 2, "Text")]),
        ),
    ],
)
def test_document_api_rejects_incompatible_root_and_chunk_shapes(
    tmp_path,
    case_name: str,
    payload_factory,
) -> None:
    """
    @brief Verify S-0001 and REQ-FUNC-048 reject invalid documents.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  case_name Stable name identifying the parametrized contract case.
    @param[in]  payload_factory Factory producing the candidate payload under test.
    @return     None.
    """
    service = _chunking_document_service()
    payload = payload_factory()
    (tmp_path / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Reset Chunking"):
        service.load_chunking_document(tmp_path)


def test_deterministic_chunking_commits_one_document_without_persisted_progress(tmp_path) -> None:
    """
    @brief Verify S-0001/S-0002 and REQ-FUNC-048/049 deterministic completion.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunk_ready_project(
        tmp_path,
        "DeterministicSingleDocument",
        "Chapter I\n\nParagraph one.\n\nParagraph two.\n",
    )
    progress_updates: list[tuple[int, int]] = []

    deterministic_chunking_service.chunk_text(
        project_root,
        manifest,
        progress_callback=lambda current, total, *_args: progress_updates.append((current, total)),
    )

    document = _read_document(project_root)
    assert set(document) == _DOCUMENT_FIELDS
    assert document["status"] == "completed"
    assert document["mode"] == "deterministic"
    assert document["semantic_strategy"] is None
    assert document["next_paragraph"] is None
    assert document["token_usage"] == _empty_usage()
    assert len(document["chunks"]) == 3
    assert progress_updates[-1] == (3, 3)
    assert not (_FORBIDDEN_PERSISTED_FIELDS & set(document))


def test_deterministic_cancellation_preserves_committed_chunks_and_next_paragraph(tmp_path) -> None:
    """
    @brief Verify S-0003/S-0005 and REQ-FUNC-3a22db38/REQ-FUNC-bdc31247 cancellation.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = _create_chunk_ready_project(
        tmp_path,
        "DeterministicCancelledDocument",
        "Paragraph one.\n\nParagraph two.\n\nParagraph three.\n",
    )
    cancel_checks = {"count": 0}

    def _cancel_after_one_paragraph() -> bool:
        """
        @brief Request cancellation before processing the second paragraph.
        @return     True after one paragraph has been processed.
        """
        cancel_checks["count"] += 1
        return cancel_checks["count"] >= 2

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        deterministic_chunking_service.chunk_text(
            project_root,
            manifest,
            cancel_requested=_cancel_after_one_paragraph,
        )

    document = _read_document(project_root)
    assert document["status"] == "cancelled"
    assert document["next_paragraph"] == len(document["chunks"]) + 1
    assert document["chunks"]
    assert not (_FORBIDDEN_PERSISTED_FIELDS & set(document))


def test_ai_chunking_persists_minimal_document_and_separate_log(tmp_path, monkeypatch) -> None:
    """
    @brief Verify S-0001/S-0002/S-0003, REQ-FUNC-049/050, and REQ-DATA-001.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @return     None.
    """
    project_root, manifest = _create_chunk_ready_project(
        tmp_path,
        "AiSingleDocument",
        "Paragraph one.\n\nParagraph two.\n",
    )
    _configure_chunking_prompts(tmp_path, monkeypatch)
    monkeypatch.setattr(
        ai_chunking_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {"chunks": []},
            "usage": {
                "input_tokens": 12,
                "output_tokens": 3,
                "total_tokens": 15,
                "usage_available": True,
            },
        },
    )

    ai_chunking_service.chunk_text(
        project_root,
        manifest,
        _profile("current-profile", context_window=4096),
        "meaning",
        additional_chunking_instructions="Keep prologues separate.",
    )

    document = _read_document(project_root)
    assert set(document) == _DOCUMENT_FIELDS
    assert document["status"] == "completed"
    assert document["mode"] == "ai_assisted"
    assert document["semantic_strategy"] == "meaning"
    assert document["additional_chunking_instructions"] == "Keep prologues separate."
    assert document["token_usage"]["total_tokens"] == 15
    assert document["next_paragraph"] is None
    assert not (_FORBIDDEN_PERSISTED_FIELDS & set(document))
    assert all(not (_FORBIDDEN_PERSISTED_FIELDS & set(chunk)) for chunk in document["chunks"])
    assert any(path.name.startswith("log_ai_chunking_") for path in project_root.glob("*.log"))


def test_ai_resume_uses_stored_strategy_and_instructions_with_current_profile(tmp_path, monkeypatch) -> None:
    """
    @brief Verify S-0003 and REQ-FUNC-050 current-profile resume semantics.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @return     None.
    """
    source_text = "Paragraph one.\n\nParagraph two.\n\nParagraph three.\n"
    project_root, manifest = _create_chunk_ready_project(tmp_path, "AiResumeDocument", source_text)
    _configure_chunking_prompts(tmp_path, monkeypatch)
    document = _valid_document(
        [_chunk("chunk-0001", 1, "Paragraph one.")],
        source_text=source_text,
        status="cancelled",
        mode="ai_assisted",
        semantic_strategy="meaning",
        additional_instructions="Stored operator instruction.",
        next_paragraph=2,
        token_usage={
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
            "usage_available": True,
        },
    )
    from audiomancer.chunking import materialization

    records = ai_chunking_service._build_paragraph_records(source_text, project_root)
    document["plan_fingerprint"] = materialization.plan_fingerprint(records)
    document["chunks"] = [materialization._build_chunk_from_range(records, 0, 0, 1)]
    document["context_window_fallback_count"] = 1
    _write_document(project_root, document)
    captured: dict[str, object] = {}

    def _chat_json(profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief Capture resume inputs while returning one valid fallback response.
        @param[in]  profile AI profile payload supplied to the controlled request.
        @param[in]  _system_prompt System prompt intentionally unused by the test double.
        @param[in]  user_prompt Rendered user prompt inspected by the test double.
        @param[in]  _kwargs Ignored keyword arguments accepted by the test double.
        @return     Controlled AI chat response payload.
        """
        captured["profile_id"] = profile["id"]
        captured["prompt"] = user_prompt
        return {
            "payload": {"chunks": []},
            "usage": {
                "input_tokens": 7,
                "output_tokens": 1,
                "total_tokens": 8,
                "usage_available": True,
            },
        }

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _chat_json)

    ai_chunking_service.chunk_text(
        project_root,
        manifest,
        _profile("replacement-profile", context_window=8192),
        "scene",
        additional_chunking_instructions=None,
    )

    resumed = _read_document(project_root)
    assert captured["profile_id"] == "replacement-profile"
    assert "Stored operator instruction." in str(captured["prompt"])
    assert "Paragraph 2" in str(captured["prompt"])
    assert "Paragraph 1\n" not in str(captured["prompt"])
    assert resumed["semantic_strategy"] == "meaning"
    assert resumed["additional_chunking_instructions"] == "Stored operator instruction."
    assert resumed["token_usage"]["total_tokens"] == 20
    assert resumed["context_window_fallback_count"] == 2


def test_manual_mutations_preserve_document_origin_and_set_manual_adjusted(tmp_path) -> None:
    """
    @brief Verify S-0004 and REQ-FUNC-051 atomic manual mutation semantics.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    source_text = "First chunk.\n\nSecond chunk.\n"
    project_root, manifest = _create_chunk_ready_project(tmp_path, "ManualDocumentMutation", source_text)
    manifest["operations"]["chunking"]["status"] = "completed"
    _write_document(
        project_root,
        _valid_document(
            [_chunk("chunk-0001", 1, "First chunk."), _chunk("chunk-0002", 2, "Second chunk.")],
            source_text=source_text,
            mode="ai_assisted",
            semantic_strategy="scene",
            additional_instructions="Preserve scene beats.",
            token_usage={
                "input_tokens": 40,
                "output_tokens": 10,
                "total_tokens": 50,
                "usage_available": True,
            },
        ),
    )

    text_chunking_state_service.save_chunk_text_edit(project_root, manifest, "chunk-0001", "Edited first chunk.")
    text_chunking_state_service.insert_chunk_after_selected(project_root, manifest, "chunk-0001")
    text_chunking_state_service.delete_selected_chunk(project_root, manifest, "chunk-0002")

    document = _read_document(project_root)
    assert set(document) == _DOCUMENT_FIELDS
    assert document["status"] == "completed"
    assert document["mode"] == "ai_assisted"
    assert document["semantic_strategy"] == "scene"
    assert document["additional_chunking_instructions"] == "Preserve scene beats."
    assert document["token_usage"]["total_tokens"] == 50
    assert document["manual_adjusted"] is True
    assert document["next_paragraph"] is None
    assert [chunk["sequence_index"] for chunk in document["chunks"]] == list(range(1, len(document["chunks"]) + 1))
    assert all(set(chunk) == _CHUNK_FIELDS for chunk in document["chunks"])
    assert "last_workflow_impact" not in document


def test_chunking_default_state_is_not_created_and_reset_deletes_all_owned_artifacts(tmp_path) -> None:
    """
    @brief Verify S-0005 and REQ-FUNC-052 page-open and Reset Chunking behavior.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    assert operation_runtime_service.ensure_default_operation_state(tmp_path, "chunking") is None
    _write_document(tmp_path, _valid_document([_chunk("chunk-0001", 1, "Text")]))
    owned_paths = [
        tmp_path / "log_ai_chunking_20260720T220000Z.log",
    ]
    for path in owned_paths:
        path.write_text("{}\n", encoding="utf-8")

    operation_runtime_service.reset_operation_data(tmp_path, "chunking", include_current=True)

    assert not (tmp_path / config.CHUNK_ARTIFACT_FILE_NAME).exists()
    assert all(not path.exists() for path in owned_paths)


def test_project_completion_evidence_uses_only_the_authoritative_document(tmp_path) -> None:
    """
    @brief Verify S-0005 and REQ-FUNC-052 manifest evidence derives from one document.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    document = _valid_document(
        [_chunk("chunk-0001", 1, "Chapter I\nText")],
        warnings=["One warning"],
    )
    _write_document(tmp_path, document)

    evidence = project_workspace_service._chunking_completion_evidence(tmp_path, [])

    assert evidence is not None
    assert evidence["operation"]["status"] == "completed"
    assert evidence["operation"]["mode"] == "deterministic"
    assert evidence["report"]["chunk_count"] == 1
    assert evidence["report"]["warning_count"] == 1


def test_downstream_consumers_use_shared_document_reader() -> None:
    """
    @brief Verify S-0006, REQ-FUNC-053, and REQ-DATA-001 production routing.
    @return     None.
    """
    consumer_module_names = (
        "audiomancer.services.ai_translation_service",
        "audiomancer.services.character_discovery_service",
        "audiomancer.services.narrator_profile_generation_service",
        "audiomancer.services.speech_blocks_service",
        "audiomancer.services.audio_blocks_state_service",
        "audiomancer.services.project_export_service",
    )
    for module_name in consumer_module_names:
        source = inspect.getsource(import_module(module_name))
        assert "chunking_document_service" in source, module_name


def test_text_chunking_state_projects_resumable_document_without_durable_progress(tmp_path) -> None:
    """
    @brief Verify S-0007 and REQ-FUNC-054 UI state derives from the document.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    source_text = "Paragraph one.\n\nParagraph two.\n"
    project_root, manifest = _create_chunk_ready_project(tmp_path, "ChunkingUiDocument", source_text)
    _write_document(
        project_root,
        _valid_document(
            [_chunk("chunk-0001", 1, "Paragraph one.")],
            source_text=source_text,
            status="cancelled",
            mode="ai_assisted",
            semantic_strategy="meaning",
            additional_instructions="Stored instruction.",
            next_paragraph=2,
            warnings=["Window warning"],
        ),
    )

    state = text_chunking_state_service.build_text_chunking_state(
        project_root,
        manifest,
        "en",
        settings_payload={
            "llm_profiles": [{"id": "profile-2", "label": "Current", "enabled": True}],
            "default_ai_chunking_profile_id": "profile-2",
            "default_ai_chunking_strategy": "scene",
        },
    )

    notes = "\n".join(state["notes"]).lower()
    assert [chunk["chunk_id"] for chunk in state["chunks"]] == ["chunk-0001"]
    assert "resume" in notes
    assert "window warning" in notes
    assert "1 / 2" not in notes
    assert "1 of 2" not in notes
    assert state["selected_strategy"] == "meaning"


# LOCAL HELPERS


def _chunking_document_service():
    """@brief Import the not-yet-implemented authoritative document module inside each test."""
    return import_module("audiomancer.services.chunking_document_service")


def _chunk(chunk_id: str, sequence_index: int, text: str) -> dict[str, object]:
    """@brief Build one exact canonical Chunking chunk record."""
    return {
        "chunk_id": chunk_id,
        "sequence_index": sequence_index,
        "text": text,
        "source_paragraph_start": None,
        "source_paragraph_end": None,
        "cleanup_boundary_confidence": "strong",
        "cleanup_joined_across_page_break": False,
        "cleanup_warning_flags": [],
        "cleanup_role": "body",
        "starts_after_scene_separator": False,
    }


def _empty_usage() -> dict[str, object]:
    """@brief Build canonical empty token usage."""
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "usage_available": False,
    }


def _valid_document(
    chunks: list[dict[str, object]] | None = None,
    *,
    source_text: str = "Text\n",
    status: str = "completed",
    mode: str = "deterministic",
    semantic_strategy: str | None = None,
    additional_instructions: str = "",
    next_paragraph: int | None = None,
    token_usage: dict[str, object] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    """@brief Build one valid exact Chunking document fixture."""
    return {
        "status": status,
        "mode": mode,
        "manual_adjusted": False,
        "source_fingerprint": f"sha256:{sha256(source_text.encode('utf-8')).hexdigest()}",
        "plan_fingerprint": None,
        "request_fingerprint": None,
        "semantic_strategy": semantic_strategy,
        "additional_chunking_instructions": additional_instructions,
        "token_usage": deepcopy(token_usage) if token_usage is not None else _empty_usage(),
        "warnings": list(warnings or []),
        "next_paragraph": next_paragraph,
        "context_window_fallback_count": 0,
        "chunks": deepcopy(chunks or []),
    }


def _write_document(project_root: Path, document: dict[str, object]) -> Path:
    """
    @brief Write one raw exact document fixture without invoking production code.
    @param[in]  project_root Active project root folder.
    @param[in]  document Authoritative operation document payload.
    @return     Resolved filesystem path.
    """
    path = project_root / config.CHUNK_ARTIFACT_FILE_NAME
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _read_document(project_root: Path) -> dict[str, object]:
    """
    @brief Read one raw document fixture for persisted-shape assertions.
    @param[in]  project_root Active project root folder.
    @return     Loaded document.
    """
    payload = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _create_chunk_ready_project(tmp_path, name: str, source_text: str):
    """
    @brief Create one project whose cleanup stage exposes canonical clean text.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  name Stable name associated with the requested object.
    @param[in]  source_text Canonical source text processed by the callable.
    @return     Created chunk ready project.
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("placeholder", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-07-20T20:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [config.CLEANED_TEXT_FILE_NAME]
    write_cleanup_input(project_root, source_text)
    project_workspace_service.save_manifest(manifest, project_root)
    return project_root, manifest


def _configure_chunking_prompts(tmp_path, monkeypatch) -> None:
    """
    @brief Install minimal local prompt templates for AI Chunking tests.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @return     None.
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir(exist_ok=True)
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text(
        "{strategy}\n{additional_chunking_instructions}\n{units_block}",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)


def _profile(profile_id: str, *, context_window: int) -> dict[str, object]:
    """
    @brief Build one enabled local AI profile fixture.
    @param[in]  profile_id Stable AI profile identifier.
    @param[in]  context_window Configured AI context-window size under test.
    @return     Validated AI profile payload used by the contract tests.
    """
    return {
        "id": profile_id,
        "label": profile_id,
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234",
        "api_key": "",
        "model_name": "qwen3-8b",
        "context_window": context_window,
        "output_reserve_tokens": 512,
        "request_timeout_seconds": 30,
        "temperature": 0.2,
    }


# END OF FILE
