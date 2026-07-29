#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_chunking_descriptor_contract.py
@brief Contract tests for descriptor-based AI chunking.
@details Verifies REQ-FUNC-065 tolerant anchored descriptor validation, fallback
         behavior, cursor advancement, final closure, reporting, and checkpoint
         resume.
@author Eng. Dan Dumitru Pasare
@date 2026-07-16
@version 0.2.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import ai_chunking_service, operation_runtime_service, project_workspace_service
from chunking_test_support import read_chunking_document, write_cleanup_input


def _profile() -> dict[str, object]:
    """Return one valid local AI profile for focused chunking checks."""
    return {
        "id": "profile_1",
        "label": "Chunking Profile",
        "backend_kind": "lmstudio",
        "base_url": "http://127.0.0.1:1234",
        "api_key": "",
        "model_name": "qwen3-8b",
        "context_window": 4096,
        "max_output_tokens": 512,
        "request_timeout_seconds": 30,
        "temperature": 0.2,
    }


def _usage(total_tokens: int = 12) -> dict[str, object]:
    """Return deterministic token usage for one fake provider response."""
    return {
        "input_tokens": total_tokens - 2,
        "output_tokens": 2,
        "total_tokens": total_tokens,
        "usage_available": True,
    }


def _response(chunks: list[dict[str, object]], total_tokens: int = 12) -> dict[str, object]:
    """Wrap descriptor chunks in the provider result shape."""
    return {"payload": {"chunks": chunks}, "usage": _usage(total_tokens)}


def _descriptor(start: int, text: str, end: int) -> dict[str, object]:
    """Build one canonical chunk descriptor."""
    return {
        "start_paragraph": start,
        "start_text": text,
        "break_after_paragraph": end,
    }


def _records(*paragraphs: str) -> list[dict[str, object]]:
    """Build minimal absolute paragraph records for validation helpers."""
    return [
        {
            "unit_id": f"paragraph-{index:04d}",
            "text": text,
            "line_start": index,
            "line_end": index,
        }
        for index, text in enumerate(paragraphs, start=1)
    ]


def _prepare_project(tmp_path, monkeypatch, paragraph_count: int = 6):
    """
    @brief      Create a chunking-ready project with deterministic paragraph windows.
    @return     Project root and mutable manifest payload.
    @version    0.1.0
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "text_chunking_system.txt").write_text("{strategy}", encoding="utf-8")
    (prompt_root / "text_chunking_user.txt").write_text("{strategy}\n{units_block}", encoding="utf-8")
    monkeypatch.setattr(config, "APP_PROMPTS_PATH", prompt_root)
    monkeypatch.setattr(
        config,
        "AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY",
        {**config.AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY, "paragraph": 4},
    )
    project_root, manifest = project_workspace_service.create_project("AiChunkDescriptorProject", tmp_path)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path.write_text(
        "\n\n".join(f"Paragraph {index} has stable text." for index in range(1, paragraph_count + 1)) + "\n",
        encoding="utf-8",
    )
    write_cleanup_input(project_root, cleaned_path.read_text(encoding="utf-8"))
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-07-16T12:00:00+00:00",
        "size_bytes": 10,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    manifest["operations"]["cleanup"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}"
    ]
    return project_root, manifest


def test_descriptor_schema_contains_only_the_approved_fields() -> None:
    """
    @brief      Verify S-0001 and REQ-FUNC-065 expose only the strict chunks contract.
    @return     None.
    @version    0.1.0
    """
    schema = ai_chunking_service._build_response_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["chunks"]
    item_schema = schema["properties"]["chunks"]["items"]
    assert item_schema["additionalProperties"] is False
    assert item_schema["required"] == ["start_paragraph", "start_text", "break_after_paragraph"]
    assert set(item_schema["properties"]) == {"start_paragraph", "start_text", "break_after_paragraph"}


@pytest.mark.parametrize(
    ("paragraph_text", "expected_anchor"),
    [
        ("One two three four five six seven eight nine ten.", "One two three four five six seven eight"),
        ("  Short\n paragraph.  ", "Short paragraph."),
    ],
)
def test_descriptor_anchor_uses_first_eight_normalized_words(paragraph_text, expected_anchor) -> None:
    """
    @brief      Verify S-0001 and REQ-FUNC-065 use whole short text or exactly eight words.
    @return     None.
    @version    0.1.0
    """
    assert ai_chunking_service._paragraph_start_anchor(paragraph_text) == expected_anchor


def test_descriptor_validation_accepts_five_consecutive_normalized_anchor_words() -> None:
    """
    @brief      Verify S-0005 and REQ-FUNC-065 accept five normalized prefix words.
    @return     None.
    @version    0.1.0
    """
    records = _records("“It is a truth universally acknowledged, that a single person exists.”")
    payload = {"chunks": [_descriptor(1, "IT is a truth universally", 1)]}

    assert ai_chunking_service._validate_chunk_descriptors(payload, records, 0, 0) == [
        {"start_index": 0, "end_index": 0}
    ]


def test_descriptor_validation_requires_complete_short_paragraph_anchor() -> None:
    """
    @brief      Verify S-0005 and REQ-FUNC-065 require every short-anchor word.
    @return     None.
    @version    0.1.0
    """
    records = _records("Mr. Bennet replied.")

    accepted = {"chunks": [_descriptor(1, "MR Bennet, REPLIED", 1)]}
    incomplete = {"chunks": [_descriptor(1, "Mr. Bennet", 1)]}

    assert ai_chunking_service._validate_chunk_descriptors(accepted, records, 0, 0) == [
        {"start_index": 0, "end_index": 0}
    ]
    assert ai_chunking_service._validate_chunk_descriptors(incomplete, records, 0, 0) is None


def test_descriptor_validation_accepts_exact_punctuation_only_scene_separator() -> None:
    """Cover S-0011 and REQ-FUNC-bd7cd503-2d84-4adb-94bc-d8f31d297368."""
    records = _records("* * *")
    payload = {"chunks": [_descriptor(1, "* * *", 1)]}

    assert ai_chunking_service._validate_chunk_descriptors(payload, records, 0, 0) == [
        {"start_index": 0, "end_index": 0}
    ]


def test_descriptor_validation_rejects_nonconsecutive_anchor_matches() -> None:
    """
    @brief      Verify S-0005 and REQ-FUNC-065 require one five-word matching run.
    @return     None.
    @version    0.1.0
    """
    records = _records("One two three four five six seven eight nine.")
    payload = {"chunks": [_descriptor(1, "One two wrong four five six wrong eight", 1)]}

    assert ai_chunking_service._validate_chunk_descriptors(payload, records, 0, 0) is None


def test_chunking_prompt_demonstrates_exactly_eight_anchor_words() -> None:
    """
    @brief      Verify S-0005 and REQ-FUNC-065 show one unambiguous long anchor.
    @return     None.
    @version    0.1.0
    """
    prompt = ai_chunking_service._render_chunking_user_prompt(
        {
            "strategy": "scene",
            "units_block": "Paragraph 1\nIt is a truth universally acknowledged that a single person exists.",
            "additional_chunking_instructions": "",
        }
    )

    assert '"start_text":"It is a truth universally acknowledged that a"' in prompt


def test_descriptor_validation_accepts_consecutive_multi_chunk_ranges() -> None:
    """
    @brief      Verify S-0001 and REQ-FUNC-065 accept consecutive descriptor spans.
    @return     None.
    @version    0.1.0
    """
    records = _records(
        "Alpha one two three four five six seven eight nine.",
        "Bravo short.",
        "Charlie short.",
        "Delta short.",
    )
    payload = {
        "chunks": [
            _descriptor(1, "Alpha one two three four five six seven", 2),
            _descriptor(3, "Charlie short.", 4),
        ]
    }

    assert ai_chunking_service._validate_chunk_descriptors(payload, records, 0, 3) == [
        {"start_index": 0, "end_index": 1},
        {"start_index": 2, "end_index": 3},
    ]


@pytest.mark.parametrize(
    "chunks",
    [
        [_descriptor(1, "wrong anchor", 1)],
        [_descriptor(2, "Bravo short.", 2)],
        [_descriptor(1, "Alpha short.", 1), _descriptor(3, "Charlie short.", 3)],
        [_descriptor(1, "Alpha short.", 2), _descriptor(2, "Bravo short.", 3)],
        [_descriptor(1, "Alpha short.", 4)],
        [{"start_paragraph": True, "start_text": "Alpha short.", "break_after_paragraph": 1}],
    ],
)
def test_descriptor_validation_rejects_the_entire_invalid_response(chunks) -> None:
    """
    @brief      Verify S-0001 and REQ-FUNC-065 reject invalid response fields atomically.
    @return     None.
    @version    0.1.0
    """
    records = _records("Alpha short.", "Bravo short.", "Charlie short.")

    assert ai_chunking_service._validate_chunk_descriptors({"chunks": chunks}, records, 0, 2) is None


def test_valid_non_final_split_advances_from_the_last_break_and_closes_final_remainder(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0002 and REQ-FUNC-065 re-submit the tail and close the remainder.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @return     None.
    @version    0.1.0
    """
    project_root, manifest = _prepare_project(tmp_path, monkeypatch)
    responses = iter(
        [
            _response([_descriptor(1, "Paragraph 1 has stable text.", 2)]),
            _response([_descriptor(3, "Paragraph 3 has stable text.", 4)]),
        ]
    )
    prompts: list[str] = []

    def _chat_json(_profile, _system_prompt, user_prompt, **kwargs):
        """
        @brief      Capture prompts and verify structured-output arguments.
        @return     Next queued fake provider response.
        @version    0.1.0
        """
        prompts.append(user_prompt)
        assert kwargs["response_schema_name"] == "text_chunk_descriptors"
        assert kwargs["response_schema"] == ai_chunking_service._build_response_schema()
        return next(responses)

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _chat_json)

    report = ai_chunking_service.chunk_text(project_root, manifest, _profile(), "paragraph")
    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]

    assert "Paragraph 1\n" in prompts[0]
    assert "Paragraph 3\n" in prompts[1]
    assert "Paragraph 2\n" not in prompts[1]
    assert [chunk["text"] for chunk in chunks] == [
        "Paragraph 1 has stable text.\n\nParagraph 2 has stable text.",
        "Paragraph 3 has stable text.\n\nParagraph 4 has stable text.",
        "Paragraph 5 has stable text.\n\nParagraph 6 has stable text.",
    ]
    assert report["context_window_fallback_count"] == 0


def test_empty_non_final_response_commits_one_fallback_window_and_reports_it(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0002/S-0003 and REQ-FUNC-065 report one non-final fallback.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @return     None.
    @version    0.1.0
    """
    project_root, manifest = _prepare_project(tmp_path, monkeypatch)
    responses = iter([_response([]), _response([])])
    progress_messages: list[str] = []
    monkeypatch.setattr(
        ai_chunking_service.llm_provider_service, "chat_json", lambda *_args, **_kwargs: next(responses)
    )

    report = ai_chunking_service.chunk_text(
        project_root,
        manifest,
        _profile(),
        "paragraph",
        progress_callback=lambda _current, _total, _percent, message, _usage_payload: progress_messages.append(message),
    )
    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]

    assert len(chunks) == 2
    assert "Paragraph 1 has stable text." in chunks[0]["text"]
    assert "Paragraph 4 has stable text." in chunks[0]["text"]
    assert "Paragraph 5 has stable text." in chunks[1]["text"]
    assert report["context_window_fallback_count"] == 1
    assert any(
        "paragraphs 1-4" in message and "saved this text window as one chunk" in message
        for message in progress_messages
    )
    assert any("One text window was saved as a fallback chunk" in warning for warning in report["warnings"])


def test_invalid_non_final_response_commits_valid_prefix_and_retries_the_tail(
    tmp_path, monkeypatch
) -> None:
    """
    @brief      Verify S-0011 preserves a valid semantic prefix before retrying an invalid tail.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @return     None.
    @version    0.1.0
    """
    project_root, manifest = _prepare_project(tmp_path, monkeypatch)
    responses = iter(
        [
            _response(
                [
                    _descriptor(1, "Paragraph 1 has stable text.", 2),
                    _descriptor(4, "Paragraph 4 has stable text.", 4),
                ]
            ),
            _response([_descriptor(3, "Paragraph 3 has stable text.", 4)]),
        ]
    )
    prompts: list[str] = []

    def _chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture one prompt and return the next fake provider response.
        @return     Next queued fake provider response.
        @version    0.1.0
        """
        prompts.append(user_prompt)
        return next(responses)

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _chat_json)

    report = ai_chunking_service.chunk_text(project_root, manifest, _profile(), "paragraph")
    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]

    assert [chunk["text"] for chunk in chunks] == [
        "Paragraph 1 has stable text.\n\nParagraph 2 has stable text.",
        "Paragraph 3 has stable text.\n\nParagraph 4 has stable text.",
        "Paragraph 5 has stable text.\n\nParagraph 6 has stable text.",
    ]
    assert "Paragraph 3\n" in prompts[1]
    assert "Paragraph 1\n" not in prompts[1]
    assert report["context_window_fallback_count"] == 0


def test_invalid_window_fallback_preserves_explicit_scene_separator_boundaries(
    tmp_path,
    monkeypatch,
) -> None:
    """Cover S-0011 and semantic fallback for user-edited Cleanup paragraphs."""
    project_root, manifest = _prepare_project(tmp_path, monkeypatch)
    cleaned_text = (
        "Opening scene closes.\n\n"
        "* * *\n\n"
        "A new scene begins.\n\n"
        "The new scene continues.\n\n"
        "A final beat starts.\n\n"
        "The final beat closes.\n"
    )
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        cleaned_text,
        encoding="utf-8",
    )
    write_cleanup_input(project_root, cleaned_text)
    responses = iter(
        [
            _response([_descriptor(1, "wrong anchor", 4)]),
            _response([]),
        ]
    )
    progress_messages: list[str] = []
    monkeypatch.setattr(
        ai_chunking_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: next(responses),
    )

    report = ai_chunking_service.chunk_text(
        project_root,
        manifest,
        _profile(),
        "paragraph",
        progress_callback=lambda _current, _total, _percent, message, _usage: (
            progress_messages.append(message)
        ),
    )
    chunks = read_chunking_document(project_root)["chunks"]

    assert [chunk["text"] for chunk in chunks[:2]] == [
        "Opening scene closes.",
        "A new scene begins.\n\nThe new scene continues.",
    ]
    assert all("* * *" not in chunk["text"] for chunk in chunks)
    assert report["context_window_fallback_count"] == 1
    assert any(
        "deterministic structural fallback" in message
        for message in progress_messages
    )


def test_ai_chunking_omits_and_splits_around_scene_separator_artifacts() -> None:
    """Cover S-0014 and REQ-FUNC-24dd4710-058c-481e-a207-a8252fff8e65."""
    records = _records(
        "* * *",
        "Opening narration.",
        "◆ ◆ ◆",
        "Second scene.",
        "Editorial separator label",
        "Closing narration.",
        "⁂",
    )
    records[4]["role"] = "scene_separator"
    chunks: list[dict[str, object]] = []

    ai_chunking_service._append_chunks_from_ranges(
        chunks,
        records,
        [{"start_index": 0, "end_index": len(records) - 1}],
        "paragraph",
    )

    assert [chunk["text"] for chunk in chunks] == [
        "Opening narration.",
        "Second scene.",
        "Closing narration.",
    ]
    assert [chunk["chunk_id"] for chunk in chunks] == [
        "chunk-0001",
        "chunk-0002",
        "chunk-0003",
    ]
    assert all(chunk["cleanup_role"] == "body" for chunk in chunks)


def test_new_checkpoint_resumes_at_next_paragraph_with_committed_chunks_and_usage(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0003 and REQ-FUNC-065 resume only the new descriptor checkpoint.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @return     None.
    @version    0.1.0
    """
    project_root, manifest = _prepare_project(tmp_path, monkeypatch)
    responses = iter(
        [
            _response([_descriptor(1, "Paragraph 1 has stable text.", 2)], total_tokens=20),
            operation_runtime_service.OperationCancelledError("stop"),
        ]
    )

    def _first_chat_json(*_args, **_kwargs):
        """
        @brief      Return one descriptor response and then simulate cancellation.
        @return     Next queued fake provider response.
        @version    0.1.0
        """
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _first_chat_json)
    with pytest.raises(operation_runtime_service.OperationCancelledError):
        ai_chunking_service.chunk_text(project_root, manifest, _profile(), "paragraph")

    checkpoint = read_chunking_document(project_root)
    assert checkpoint["status"] == "cancelled"
    assert checkpoint["next_paragraph"] == 3
    assert len(checkpoint["chunks"]) == 1
    assert checkpoint["token_usage"]["total_tokens"] == 20
    assert "metadata" not in checkpoint
    assert "progress_current" not in checkpoint

    resumed_prompts: list[str] = []

    def _resume_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        resumed_prompts.append(user_prompt)
        return _response([], total_tokens=10)

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _resume_chat_json)
    report = ai_chunking_service.chunk_text(project_root, manifest, _profile(), "paragraph")

    assert "Paragraph 3\n" in resumed_prompts[0]
    assert "Paragraph 1\n" not in resumed_prompts[0]
    assert report["chunk_count"] == 2
    assert report["token_usage"]["total_tokens"] == 30


def test_old_break_id_checkpoint_restarts_from_paragraph_one(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify S-0003 and REQ-FUNC-065 restart checkpoints from the removed contract.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  monkeypatch Pytest monkeypatch fixture used to install controlled test doubles.
    @return     None.
    @version    0.1.0
    """
    project_root, manifest = _prepare_project(tmp_path, monkeypatch)
    state_path = project_root / "chunking_state.json"
    state_path.write_text(
        json.dumps(
            {
                "status": "cancelled",
                "mode": "ai_assisted",
                "started_at": "2026-07-16T12:00:00+00:00",
                "metadata": {"token_usage": _usage(99)},
                "resume_checkpoint": {
                    "input_fingerprint": ai_chunking_service._compute_input_fingerprint(
                        (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
                    ),
                    "semantic_strategy": "paragraph",
                    "completed_unit_count": 4,
                    "committed_break_ids": ["paragraph-0002"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    prompts: list[str] = []
    responses = iter([_response([]), _response([])])

    def _chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture one prompt and return the next fake provider response.
        @return     Next queued fake provider response.
        @version    0.1.0
        """
        prompts.append(user_prompt)
        return next(responses)

    monkeypatch.setattr(ai_chunking_service.llm_provider_service, "chat_json", _chat_json)

    ai_chunking_service.chunk_text(project_root, manifest, _profile(), "paragraph")

    assert "Paragraph 1\n" in prompts[0]


# END OF FILE
