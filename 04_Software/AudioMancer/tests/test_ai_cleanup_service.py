#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# ruff: noqa: E501
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_cleanup_service.py
@brief Focused tests for the AudioMancer AI cleanup service.
@details Verifies AI-assisted cleanup writes the expected cleanup artifacts,
         persists resumable state, and creates one AI transaction log file.
@author Eng. Dan Dumitru Pasare
@date 2026-04-11
@version 0.2.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import ai_cleanup_service

# FIXTURES & GLOBALS

_MOCK_PROFILE = {
    "id": "profile_1",
    "label": "Cleanup Profile",
    "backend_kind": "lmstudio",
    "base_url": "http://127.0.0.1:1234",
    "api_key": "",
    "model_name": "qwen3-8b",
    "context_window": 4096,
    "max_output_tokens": 512,
    "request_timeout_seconds": 30,
    "temperature": 0.2,
}

# TESTS


def test_ai_cleanup_writes_cleanup_artifacts_and_log(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """Verify AI-assisted cleanup writes output, report, state, and AI log artifacts."""
    project_root, manifest = mock_extracted_project

    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text(
        "CHAPTER I\n\nStory paragraph one.\n\n***\n\nStory paragraph two.\n",
        encoding="utf-8",
    )

    responses = iter(
        [
            {
                "payload": {
                    "results": [
                        {"unit_id": "unit-0001", "label": "story"},
                        {"unit_id": "unit-0002", "label": "story"},
                        {"unit_id": "unit-0003", "label": "separator"},
                        {"unit_id": "unit-0004", "label": "story"},
                    ]
                },
                "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25, "usage_available": True},
            }
        ]
    )
    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: next(responses),
    )

    report_payload = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    cleanup_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    assert (cleanup_root / config.EXTRACTED_TEXT_FILE_NAME).is_file()
    assert (cleanup_root / config.CLEANED_TEXT_FILE_NAME).is_file()
    assert (cleanup_root / config.CLEANED_TEXT_METADATA_FILE_NAME).is_file()
    assert (cleanup_root / config.CLEANUP_REPORT_FILE_NAME).is_file()
    assert (cleanup_root / config.CLEANUP_STATE_FILE_NAME).is_file()
    assert report_payload["cleanup_mode"] == "ai_assisted"
    assert report_payload["cleaned_text_metadata_relative_path"] == config.CLEANED_TEXT_METADATA_FILE_NAME
    assert report_payload["ai_profile_id"] == "profile_1"
    assert "Story paragraph one." in (cleanup_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert any(path.name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX) for path in cleanup_root.glob("*.log"))

    state_payload = json.loads((cleanup_root / config.CLEANUP_STATE_FILE_NAME).read_text(encoding="utf-8"))
    metadata_payload = json.loads((cleanup_root / config.CLEANED_TEXT_METADATA_FILE_NAME).read_text(encoding="utf-8"))
    assert state_payload["mode"] == "ai_assisted"
    assert state_payload["status"] == "completed"
    assert metadata_payload["cleanup_mode"] == "ai_assisted"
    assert metadata_payload["paragraphs"][0]["source_page_start"] is None


@pytest.mark.parametrize(
    "source_text, ai_results, token_usage, expected_in, expected_out",
    [
        # Heals soft line breaks inside one continuing sentence
        (
            "Ottmar Drenthe was watching reviews of his latest project and fuming at\n"
            "the idiocy of the\nDominion's reviewing elites.\n",
            [{"unit_id": "unit-0001", "label": "story"}],
            {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
            "idiocy of the Dominion's reviewing elites.",
            "idiocy of the\nDominion's reviewing elites.",
        ),
        # Joins unfinished wrapped lines before one capitalized continuation
        (
            '"This is below\nDrenthe."\n',
            [{"unit_id": "unit-0001", "label": "story"}],
            {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
            '"This is below Drenthe."',
            '"This is below\nDrenthe."',
        ),
        # Merges adjacent kept paragraphs when a page split interrupts one sentence
        (
            "Drenthe will shoot this industrial if\n\n3\n\nyou swear that Heroes of the Periphery will then be the next project.\n",
            [
                {"unit_id": "unit-0001", "label": "story"},
                {"unit_id": "unit-0002", "label": "page_number"},
                {"unit_id": "unit-0003", "label": "story"},
            ],
            {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15, "usage_available": True},
            "Drenthe will shoot this industrial if you swear that Heroes of the Periphery",
            "industrial if\n\nyou swear",
        ),
    ],
    ids=["soft_breaks", "proper_name_continuation", "page_split_continuation"],
)
def test_ai_cleanup_text_transformations(
    source_text: str,
    ai_results: list,
    token_usage: dict,
    expected_in: str,
    expected_out: str,
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """Verify various AI cleanup text join/heal permutations via parametrization."""
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text(source_text, encoding="utf-8")

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {"results": ai_results},
            "usage": token_usage,
        },
    )

    ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    cleaned_text = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    ).read_text(encoding="utf-8")
    assert expected_in in cleaned_text
    assert expected_out not in cleaned_text


def test_ai_cleanup_corrects_invalid_tail_labels_and_persists_warnings(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """Verify AI-assisted cleanup corrects page-number drift near one late window tail and persists warnings."""
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text(
        "Story before.\n\n* * *\n\nHi, I'm Dario Cerulli of Axiom Ordnance, and I'm here to tell you about the Warhound.\n\n"
        '22\n\n"You know what it wasn\'t for?" Drenthe asked.\n\n23\n\nHolorecorders were cheap, and they were everywhere.\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {
                "results": [
                    {"unit_id": "unit-0001", "label": "story"},
                    {"unit_id": "unit-0002", "label": "story"},
                    {"unit_id": "unit-0003", "label": "page_number"},
                    {"unit_id": "unit-0004", "label": "story"},
                    {"unit_id": "unit-0005", "label": "page_number"},
                    {"unit_id": "unit-0006", "label": "story"},
                ]
            },
            "usage": {"input_tokens": 18, "output_tokens": 6, "total_tokens": 24, "usage_available": True},
        },
    )

    report_payload = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    cleaned_text = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    ).read_text(encoding="utf-8")
    assert "Hi, I'm Dario Cerulli" in cleaned_text
    assert '"You know what it wasn\'t for?" Drenthe asked.' in cleaned_text
    assert "Holorecorders were cheap" in cleaned_text
    assert "\n\n22\n\n" not in cleaned_text
    assert "\n\n23\n\n" not in cleaned_text

    assert any(
        warning_detail["kind"] == "invalid_page_number_label_corrected"
        for warning_detail in report_payload["warning_details"]
    )
    state_payload = json.loads(
        (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANUP_STATE_FILE_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert state_payload["warning_count"] >= 1
    assert any(
        detail["kind"] == "invalid_page_number_label_corrected"
        for detail in state_payload["metadata"]["warning_details"]
    )


def test_ai_cleanup_accepts_artifact_action_confidence_schema(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """Verify AI cleanup accepts the artifact/action/confidence response schema."""
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text(
        "Book Title\n\nChapter One\n\nStory paragraph.\n\nPage 12\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {
                "results": [
                    {
                        "unit_id": "unit-0001",
                        "artifact_type": "header",
                        "action": "remove",
                        "confidence": "high",
                        "reason": "running title",
                    },
                    {
                        "unit_id": "unit-0002",
                        "artifact_type": "chapter_heading",
                        "action": "keep",
                        "confidence": "high",
                        "reason": "chapter marker",
                    },
                    {
                        "unit_id": "unit-0003",
                        "artifact_type": "story",
                        "action": "keep",
                        "confidence": "high",
                        "reason": "narrative",
                    },
                    {
                        "unit_id": "unit-0004",
                        "artifact_type": "page_number",
                        "action": "remove",
                        "confidence": "medium",
                        "reason": "page marker",
                    },
                ]
            },
            "usage": {"input_tokens": 20, "output_tokens": 8, "total_tokens": 28, "usage_available": True},
        },
    )

    ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    cleaned_text = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    ).read_text(encoding="utf-8")
    assert "Book Title" not in cleaned_text
    assert "Chapter One" in cleaned_text
    assert "Story paragraph." in cleaned_text
    assert "Page 12" not in cleaned_text


def test_ai_cleanup_preserves_low_confidence_removals(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """Verify low-confidence removable classifications are preserved for review."""
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text("A short but meaningful line.\n", encoding="utf-8")

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {
                "results": [
                    {
                        "unit_id": "unit-0001",
                        "artifact_type": "header",
                        "action": "remove",
                        "confidence": "low",
                        "reason": "possibly a running head",
                    }
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "usage_available": True},
        },
    )

    report_payload = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    cleaned_text = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    ).read_text(encoding="utf-8")
    assert "A short but meaningful line." in cleaned_text
    assert any(
        warning_detail["kind"] == "low_confidence_removal_preserved"
        for warning_detail in report_payload["warning_details"]
    )


def test_ai_cleanup_prompt_includes_language_script_and_neighbor_context(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """Verify the AI cleanup user prompt exposes language, script, and neighbor context."""
    project_root, manifest = mock_extracted_project
    (mock_prompt_environment / "text_cleanup_user.txt").write_text(
        "Language: {source_language_hint}\nScript: {dominant_script_hint}\nCount: {unit_count}\n{units_block}",
        encoding="utf-8",
    )
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text("First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n", encoding="utf-8")
    captured_user_prompts: list[str] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        captured_user_prompts.append(user_prompt)
        return {
            "payload": {
                "results": [
                    {"unit_id": "unit-0001", "label": "story"},
                    {"unit_id": "unit-0002", "label": "story"},
                    {"unit_id": "unit-0003", "label": "story"},
                ]
            },
            "usage": {"input_tokens": 16, "output_tokens": 6, "total_tokens": 22, "usage_available": True},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)

    ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    assert captured_user_prompts
    prompt = captured_user_prompts[0]
    assert "Language:" in prompt
    assert "Script: latin" in prompt
    assert "Count: 3" in prompt
    assert "previous_unit_text: First paragraph." in prompt
    assert "unit_text: Second paragraph." in prompt
    assert "next_unit_text: Third paragraph." in prompt


def test_ai_cleanup_splits_long_input_into_multiple_windows(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """Verify AI-assisted cleanup splits long extracted input into multiple request windows."""
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_text = "\n\n".join(f"Paragraph {index} keeps enough words." for index in range(1, 31)) + "\n"
    extracted_path.write_text(extracted_text, encoding="utf-8")

    call_contexts: list[dict[str, object]] = []

    def _fake_chat_json(_profile, _system_prompt, _user_prompt, **kwargs):
        log_context = kwargs.get("log_context", {})
        call_contexts.append(dict(log_context))
        window_index = int(log_context.get("window_index", 1))
        start_unit = (window_index - 1) * config.DEFAULT_AI_CLEANUP_MAX_WINDOW_UNITS + 1
        end_unit = min(start_unit + config.DEFAULT_AI_CLEANUP_MAX_WINDOW_UNITS - 1, 30)
        return {
            "payload": {
                "results": [
                    {"unit_id": f"unit-{unit_index:04d}", "label": "story"}
                    for unit_index in range(start_unit, end_unit + 1)
                ]
            },
            "usage": {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60, "usage_available": True},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)

    profile_large_window = dict(_MOCK_PROFILE)
    profile_large_window["context_window"] = 32000

    report_payload = ai_cleanup_service.clean_text(project_root, manifest, profile_large_window)

    assert len(call_contexts) == 2
    assert report_payload["window_count"] == 2
    assert report_payload["token_usage"]["total_tokens"] == 120
    assert call_contexts[0]["window_index"] == 1
    assert call_contexts[1]["window_index"] == 2


# END OF FILE
