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
@version 0.4.4
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
    """
    @brief      Validate ai cleanup writes cleanup artifacts and log.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.2.1
    """
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
                        {
                            "unit_id": "unit-0001",
                            "artifact_type": "chapter_heading",
                            "action": "keep",
                            "confidence": "high",
                        },
                        {"unit_id": "unit-0002", "artifact_type": "story", "action": "keep", "confidence": "high"},
                        {"unit_id": "unit-0003", "artifact_type": "separator", "action": "keep", "confidence": "high"},
                        {"unit_id": "unit-0004", "artifact_type": "story", "action": "keep", "confidence": "high"},
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
    assert "cleaned_text_metadata_relative_path" not in report_payload
    assert report_payload["ai_profile_id"] == "profile_1"
    assert report_payload["model_settings"]["model_name"] == "qwen3-8b"
    assert report_payload["model_settings"]["temperature"] == 0.2
    assert report_payload["model_settings"]["context_window"] == 4096
    assert report_payload["model_settings_history"] == [
        {
            "profile_id": "profile_1",
            "backend_kind": "lmstudio",
            "base_url": "http://127.0.0.1:1234",
            "model_name": "qwen3-8b",
            "temperature": 0.2,
            "context_window": 4096,
            "max_output_tokens": 512,
        }
    ]
    assert report_payload["budget_metadata"]["context_window"] == 4096
    assert report_payload["budget_metadata"]["max_output_tokens"] == 512
    assert report_payload["budget_metadata"]["max_window_units"] == config.DEFAULT_AI_CLEANUP_MAX_WINDOW_UNITS
    assert "Story paragraph one." in (cleanup_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    assert any(path.name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX) for path in cleanup_root.glob("*.log"))

    state_payload = json.loads((cleanup_root / config.CLEANUP_STATE_FILE_NAME).read_text(encoding="utf-8"))
    metadata_payload = json.loads((cleanup_root / config.CLEANED_TEXT_METADATA_FILE_NAME).read_text(encoding="utf-8"))
    assert state_payload["mode"] == "ai_assisted"
    assert state_payload["status"] == "completed"
    assert state_payload["resume_checkpoint"] is None
    assert state_payload["metadata"]["model_settings"] == report_payload["model_settings"]
    assert state_payload["metadata"]["budget_metadata"] == report_payload["budget_metadata"]
    assert metadata_payload["cleanup_mode"] == "ai_assisted"
    assert "text" not in metadata_payload["paragraphs"][0]
    assert metadata_payload["paragraphs"][0]["source_page_start"] is None
    manifest_payload = json.loads((project_root / config.PROJECT_MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    assert manifest_payload["operations"]["cleanup"]["status"] == "completed"
    assert manifest_payload["operations"]["cleanup"]["mode"] == "ai_assisted"


@pytest.mark.parametrize(
    "source_text, ai_results, token_usage, expected_in, expected_out",
    [
        # Heals soft line breaks inside one continuing sentence
        (
            "Ottmar Drenthe was watching reviews of his latest project and fuming at\n"
            "the idiocy of the\nDominion's reviewing elites.\n",
            [{"unit_id": "unit-0001", "artifact_type": "story", "action": "keep", "confidence": "high"}],
            {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
            "idiocy of the Dominion's reviewing elites.",
            "idiocy of the\nDominion's reviewing elites.",
        ),
        # Joins unfinished wrapped lines before one capitalized continuation
        (
            '"This is below\nDrenthe."\n',
            [{"unit_id": "unit-0001", "artifact_type": "dialogue", "action": "keep", "confidence": "high"}],
            {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
            '"This is below Drenthe."',
            '"This is below\nDrenthe."',
        ),
        # Merges adjacent kept paragraphs when a page split interrupts one sentence
        (
            "Drenthe will shoot this industrial if\n\n3\n\nyou swear that Heroes of the Periphery will then be the next project.\n",
            [
                {"unit_id": "unit-0001", "artifact_type": "story", "action": "keep", "confidence": "high"},
                {"unit_id": "unit-0002", "artifact_type": "page_number", "action": "remove", "confidence": "high"},
                {"unit_id": "unit-0003", "artifact_type": "story", "action": "keep", "confidence": "high"},
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
    """
    @brief      Validate ai cleanup text transformations.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.2.0
    """
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
    """
    @brief      Validate ai cleanup corrects invalid tail labels and persists warnings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
                    {"unit_id": "unit-0001", "artifact_type": "story", "action": "keep", "confidence": "high"},
                    {"unit_id": "unit-0002", "artifact_type": "separator", "action": "keep", "confidence": "high"},
                    {"unit_id": "unit-0003", "artifact_type": "page_number", "action": "remove", "confidence": "high"},
                    {"unit_id": "unit-0004", "artifact_type": "story", "action": "keep", "confidence": "high"},
                    {"unit_id": "unit-0005", "artifact_type": "page_number", "action": "remove", "confidence": "high"},
                    {"unit_id": "unit-0006", "artifact_type": "story", "action": "keep", "confidence": "high"},
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
    """
    @brief      Validate ai cleanup accepts artifact action confidence schema.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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


def test_ai_cleanup_ignores_legacy_label_only_schema(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """
    @brief      Validate ai cleanup ignores legacy label-only result items.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text("Book Title\n\nRunning Head\n\nStory paragraph.\n", encoding="utf-8")

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {
                "results": [
                    {"unit_id": "unit-0001", "label": "header"},
                    {"unit_id": "unit-0002", "artifact_type": "header", "confidence": "high"},
                    {"unit_id": "unit-0003", "artifact_type": "story", "action": "keep", "confidence": "high"},
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "usage_available": True},
        },
    )

    ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    cleaned_text = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    ).read_text(encoding="utf-8")
    assert "Book Title" in cleaned_text
    assert "Running Head" in cleaned_text
    assert "Story paragraph." in cleaned_text


def test_ai_cleanup_preserves_low_confidence_removals(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """
    @brief      Validate ai cleanup preserves low confidence removals.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
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
    """
    @brief      Validate ai cleanup prompt includes language script and neighbor context.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, manifest = mock_extracted_project
    (mock_prompt_environment / "text_cleanup_user.txt").write_text(
        "Language: {source_language_hint}\nScript: {dominant_script_hint}\nCount: {unit_count}\n{units_block}",
        encoding="utf-8",
    )
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text("First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n", encoding="utf-8")
    captured_user_prompts: list[str] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        captured_user_prompts.append(user_prompt)
        return {
            "payload": {
                "results": [
                    {"unit_id": "unit-0001", "artifact_type": "story", "action": "keep", "confidence": "high"},
                    {"unit_id": "unit-0002", "artifact_type": "story", "action": "keep", "confidence": "high"},
                    {"unit_id": "unit-0003", "artifact_type": "story", "action": "keep", "confidence": "high"},
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


def test_ai_cleanup_appends_operator_instructions_to_prompt_and_state(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """
    @brief      Validate ai cleanup appends operator rules and persists them with operation state.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    project_root, manifest = mock_extracted_project
    (mock_prompt_environment / "text_cleanup_user.txt").write_text(
        "Language: {source_language_hint}\n{units_block}",
        encoding="utf-8",
    )
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text("First paragraph.\n\nSecond paragraph.\n", encoding="utf-8")
    captured_user_prompts: list[str] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     Fake AI cleanup response payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-12
        @version    0.1.0
        """
        captured_user_prompts.append(user_prompt)
        return {
            "payload": {
                "results": [
                    {"unit_id": "unit-0001", "artifact_type": "story", "action": "keep", "confidence": "high"},
                    {"unit_id": "unit-0002", "artifact_type": "story", "action": "keep", "confidence": "high"},
                ]
            },
            "usage": {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16, "usage_available": True},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)

    report_payload = ai_cleanup_service.clean_text(
        project_root,
        manifest,
        _MOCK_PROFILE,
        additional_cleanup_instructions="Preserve all glossary terms exactly.",
    )

    assert captured_user_prompts
    assert "Additional operator cleanup instructions:" in captured_user_prompts[0]
    assert "Preserve all glossary terms exactly." in captured_user_prompts[0]
    assert report_payload["additional_cleanup_instructions"] == "Preserve all glossary terms exactly."
    state_payload = json.loads(
        (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANUP_STATE_FILE_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert state_payload["metadata"]["additional_cleanup_instructions"] == "Preserve all glossary terms exactly."
    assert state_payload["metadata"]["additional_cleanup_instructions_fingerprint"]


def test_ai_cleanup_splits_long_input_into_multiple_windows(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """
    @brief      Validate ai cleanup splits long input into multiple windows.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_text = "\n\n".join(f"Paragraph {index} keeps enough words." for index in range(1, 31)) + "\n"
    extracted_path.write_text(extracted_text, encoding="utf-8")

    call_contexts: list[dict[str, object]] = []

    def _fake_chat_json(_profile, _system_prompt, _user_prompt, **kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        log_context = kwargs.get("log_context", {})
        call_contexts.append(dict(log_context))
        window_index = int(log_context.get("window_index", 1))
        start_unit = (window_index - 1) * config.DEFAULT_AI_CLEANUP_MAX_WINDOW_UNITS + 1
        end_unit = min(start_unit + config.DEFAULT_AI_CLEANUP_MAX_WINDOW_UNITS - 1, 30)
        return {
            "payload": {
                "results": [
                    {
                        "unit_id": f"unit-{unit_index:04d}",
                        "artifact_type": "story",
                        "action": "keep",
                        "confidence": "high",
                    }
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


def test_ai_cleanup_rejects_profiles_with_no_input_budget(mock_prompt_environment) -> None:
    """
    @brief      Validate ai cleanup rejects profiles with no input budget.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    with pytest.raises(ValueError, match="too little room"):
        ai_cleanup_service._build_budget_metadata(
            {
                "context_window": 1024,
                "max_output_tokens": 900,
            },
            "en",
            "latin",
            "cleanup",
            "",
        )


def test_ai_cleanup_small_context_limits_unit_windows() -> None:
    """
    @brief      Validate ai cleanup small context limits unit windows.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    units = [
        {
            "unit_id": f"unit-{index:04d}",
            "text": "x" * 500,
            "estimated_tokens": 157,
        }
        for index in range(1, 9)
    ]

    windows = ai_cleanup_service._build_windows(
        units,
        {
            "context_window": 2048,
            "max_output_tokens": 512,
            "prompt_budget_tokens": 20,
            "text_budget_tokens": 512,
            "safety_margin_tokens": 256,
            "max_window_units": config.DEFAULT_AI_CLEANUP_MAX_WINDOW_UNITS,
        },
    )

    assert len(windows) > 1
    assert windows[0]["end_index"] < len(units) - 1


def test_ai_cleanup_online_profile_uses_direct_context_fraction_without_unit_cap(mock_prompt_environment) -> None:
    """
    @brief      Validate online cleanup budgets ignore local unit caps and output-token budget subtraction.
    @param[in]  mock_prompt_environment Shared prompt-template fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    _ = mock_prompt_environment
    profile_payload = {
        **_MOCK_PROFILE,
        "backend_kind": config.ONLINE_AI_BACKEND_KIND,
        "context_window": 10000,
        "max_output_tokens": 9900,
    }

    budget_metadata = ai_cleanup_service._build_budget_metadata(
        profile_payload,
        "English",
        "Latin",
        "system",
        "",
    )
    units = [{"unit_id": f"unit-{index:04d}", "text": "Short cleanup unit."} for index in range(1, 30)]

    assert budget_metadata["text_budget_tokens"] == 3000
    assert budget_metadata["max_window_units"] == 0
    assert ai_cleanup_service._build_windows(units, budget_metadata) == [{"start_index": 0, "end_index": 28}]


def test_ai_cleanup_resumes_with_new_model_settings(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """
    @brief      Validate ai cleanup resumes with new model settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text(
        "\n\n".join(f"Paragraph {index} keeps enough words." for index in range(1, 41)) + "\n",
        encoding="utf-8",
    )
    responses = iter(
        [
            {
                "payload": {
                    "results": [
                        {
                            "unit_id": f"unit-{unit_index:04d}",
                            "artifact_type": "story",
                            "action": "keep",
                            "confidence": "high",
                        }
                        for unit_index in range(1, 25)
                    ]
                },
                "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
            },
            RuntimeError("stop"),
        ]
    )

    def _first_chat_json(*_args, **_kwargs):
        """
        @brief      Provide the first chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _first_chat_json)
    with pytest.raises(RuntimeError, match="stop"):
        ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    interrupted_manifest = json.loads((project_root / config.PROJECT_MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    interrupted_state = json.loads(
        (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANUP_STATE_FILE_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert interrupted_manifest["operations"]["cleanup"]["status"] == "failed"
    assert interrupted_state["status"] == "failed"
    assert interrupted_state["resume_checkpoint"]["classifications"]

    captured_prompts: list[str] = []

    def _second_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Provide the second chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        captured_prompts.append(user_prompt)
        return {
            "payload": {
                "results": [
                    {
                        "unit_id": f"unit-{unit_index:04d}",
                        "artifact_type": "story",
                        "action": "keep",
                        "confidence": "high",
                    }
                    for unit_index in range(1, 41)
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
        }

    second_profile = {
        **_MOCK_PROFILE,
        "id": "profile_2",
        "model_name": "qwen3-14b",
        "context_window": 8192,
        "temperature": 0.7,
    }
    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _second_chat_json)

    report_payload = ai_cleanup_service.clean_text(project_root, manifest, second_profile)
    state_payload = json.loads(
        (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANUP_STATE_FILE_NAME).read_text(
            encoding="utf-8"
        )
    )

    assert captured_prompts
    assert "unit_id: unit-0001" not in captured_prompts[0]
    assert "unit_id: unit-0025" in captured_prompts[0]
    assert report_payload["ai_profile_id"] == "profile_2"
    assert report_payload["model_settings"]["model_name"] == "qwen3-14b"
    assert report_payload["model_settings"]["temperature"] == 0.7
    assert report_payload["model_settings"]["context_window"] == 8192
    assert len(report_payload["model_settings_history"]) == 2
    assert state_payload["metadata"]["model_settings"]["model_name"] == "qwen3-14b"
    assert state_payload["resume_checkpoint"] is None


def test_ai_cleanup_restarts_when_extracted_text_changes(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """
    @brief      Validate ai cleanup restarts when extracted text changes.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text(
        "\n\n".join(f"Original paragraph {index} keeps words." for index in range(1, 30)) + "\n",
        encoding="utf-8",
    )
    responses = iter(
        [
            {
                "payload": {
                    "results": [
                        {
                            "unit_id": f"unit-{unit_index:04d}",
                            "artifact_type": "story",
                            "action": "keep",
                            "confidence": "high",
                        }
                        for unit_index in range(1, 25)
                    ]
                },
                "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
            },
            RuntimeError("stop"),
        ]
    )

    def _first_chat_json(*_args, **_kwargs):
        """
        @brief      Provide the first chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _first_chat_json)
    with pytest.raises(RuntimeError, match="stop"):
        ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    extracted_path.write_text("Replacement paragraph one.\n\nReplacement paragraph two.\n", encoding="utf-8")
    captured_prompts: list[str] = []

    def _second_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Provide the second chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        captured_prompts.append(user_prompt)
        return {
            "payload": {
                "results": [
                    {"unit_id": "unit-0001", "artifact_type": "story", "action": "keep", "confidence": "high"},
                    {"unit_id": "unit-0002", "artifact_type": "story", "action": "keep", "confidence": "high"},
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _second_chat_json)

    report_payload = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    assert captured_prompts
    assert "unit_id: unit-0001" in captured_prompts[0]
    assert len(report_payload["model_settings_history"]) == 1


def test_ai_cleanup_tolerates_corrupt_state_and_restarts(
    mock_extracted_project, mock_prompt_environment, monkeypatch
) -> None:
    """
    @brief      Validate AI cleanup treats corrupt state as absent and restarts cleanly.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-12
    @version    0.1.0
    """
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text("Replacement paragraph one.\n\nReplacement paragraph two.\n", encoding="utf-8")
    (project_root / config.CLEANUP_STATE_FILE_NAME).write_text("{", encoding="utf-8")

    def _fake_chat_json(_profile, _system_prompt, _user_prompt, **_kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     Fake AI cleanup response payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-12
        @version    0.1.0
        """
        return {
            "payload": {
                "results": [
                    {"unit_id": "unit-0001", "artifact_type": "story", "action": "keep", "confidence": "high"},
                    {"unit_id": "unit-0002", "artifact_type": "story", "action": "keep", "confidence": "high"},
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12, "usage_available": True},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)

    report_payload = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    assert report_payload["paragraph_count"] == 2
    state_payload = json.loads((project_root / config.CLEANUP_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert state_payload["status"] == "completed"


# END OF FILE
