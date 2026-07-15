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
@brief Integration checks for AI-assisted cleanup.
@details Verifies the AI Cleanup block contract, deterministic reconstruction,
         artifacts, prompts, budgeting, persistence, restart, and resume behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-07-15
@version 1.2.0
"""

# IMPORTS

import json
import re

import pytest

from audiomancer import config
from audiomancer.services import ai_cleanup_service

# CONSTANTS

_MOCK_PROFILE = {
    "id": "profile_1",
    "label": "Local model",
    "backend_kind": "lmstudio",
    "base_url": "http://127.0.0.1:1234/v1",
    "api_key": "",
    "model_name": "qwen3-8b",
    "context_window": 8192,
    "max_output_tokens": 4096,
    "request_timeout_seconds": 90,
    "temperature": 0.2,
    "supports_structured_output": True,
    "enabled": True,
}
_WINDOW_PATTERN = re.compile(
    r"<<< SOURCE WINDOW START >>>\n(?P<text>.*?)<<< SOURCE WINDOW END >>>",
    re.DOTALL,
)


def _configure_cleanup_prompts(prompt_root) -> None:
    """
    @brief      Write minimal cleanup prompt fixtures.
    @param[in]  prompt_root Prompt template directory.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    (prompt_root / "text_cleanup_system.txt").write_text("AI cleanup system prompt.", encoding="utf-8")
    (prompt_root / "text_cleanup_user.txt").write_text(
        "Window: {window_id}\nLanguage: {source_language_hint}\nScript: {dominant_script_hint}\n"
        "{source_window_block}\nInstructions: {additional_cleanup_instructions}",
        encoding="utf-8",
    )


def _block(
    block_id: int,
    text: str,
    artifact_type: str = "story",
    confidence: str = "high",
) -> dict[str, object]:
    """
    @brief      Build one cleanup response block fixture.
    @param[in]  block_id Sequential cleanup block identifier.
    @param[in]  text Exact source text for the block.
    @param[in]  artifact_type Cleanup artifact classification.
    @param[in]  confidence Model confidence metadata.
    @return     Cleanup response block payload.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return {
        "text_block_id": block_id,
        "text_block": text,
        "artifact_type": artifact_type,
        "confidence": confidence,
    }


def _payload(window_id: str, blocks: list[dict[str, object]]) -> dict[str, object]:
    """
    @brief      Build one cleanup response payload fixture.
    @param[in]  window_id Expected cleanup window identity.
    @param[in]  blocks Ordered cleanup response blocks.
    @return     Cleanup response payload.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return {"window_id": window_id, "text_blocks": blocks}


def _keep_all_payload(user_prompt: str, window_index: int) -> dict[str, object]:
    """
    @brief      Build a story-only payload from the rendered source window.
    @param[in]  user_prompt Rendered cleanup user prompt.
    @param[in]  window_index One-based cleanup window index.
    @return     Provider-compatible cleanup result payload.
    @exception  AssertionError Raised when the prompt omits canonical source markers.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    match = _WINDOW_PATTERN.search(user_prompt)
    if match is None:
        raise AssertionError("Cleanup prompt is missing the canonical source window.")
    return _payload(
        f"cleanup-window-{window_index:04d}",
        [_block(1, match.group("text"))],
    )


def _install_keep_all_provider(monkeypatch, captured_prompts: list[str] | None = None) -> None:
    """
    @brief      Install a provider fixture that retains each complete source window.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  captured_prompts Optional list that records rendered prompts.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **kwargs):
        """
        @brief      Return a deterministic cleanup provider response fixture.
        @param[in]  _profile Unused AI profile payload.
        @param[in]  _system_prompt Unused cleanup system prompt.
        @param[in]  user_prompt Rendered cleanup user prompt.
        @param[in]  kwargs Provider call options, including the response schema.
        @return     Provider-compatible cleanup result payload.
        @exception  AssertionError Raised when provider-call contract assertions fail.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-15
        @version    1.1.0
        """
        if captured_prompts is not None:
            captured_prompts.append(user_prompt)
        window_index = int(dict(kwargs.get("log_context", {})).get("window_index", 1))
        return {
            "payload": _keep_all_payload(user_prompt, window_index),
            "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20, "usage_available": True},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)


def _extracted_path(project_root):
    """
    @brief      Resolve the extracted-text artifact path for a test project.
    @param[in]  project_root Active test-project root.
    @return     Extracted-text artifact path.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    return project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME


def test_ai_cleanup_writes_cleanup_artifacts_and_log(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify AI Cleanup writes cleaned text, report, state, metadata, and log artifacts.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    _extracted_path(project_root).write_text("Chapter One\n\nIt was a sunny day.\n", encoding="utf-8")
    _install_keep_all_provider(monkeypatch)

    report = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    assert "schema_version" not in report
    assert report["paragraph_count"] == 2
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8").endswith("\n")
    assert (project_root / config.CLEANUP_REPORT_FILE_NAME).is_file()
    state = json.loads((project_root / config.CLEANUP_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["resume_checkpoint"] is None
    assert (project_root / report["ai_log_relative_path"]).is_file()


@pytest.mark.parametrize(
    ("source", "preserved", "expected"),
    [
        ("Copyright 2026. It was sunny.\n", "It was sunny.\n", "It was sunny.\n"),
        ("It was sunny. Page 4\n", "It was sunny. ", "It was sunny. "),
        ("Header\n\nNarration.\n", "Narration.\n", "Narration.\n"),
    ],
)
def test_ai_cleanup_text_transformations(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
    source: str,
    preserved: str,
    expected: str,
) -> None:
    """
    @brief      Verify prefix and suffix noise is removed without replacement whitespace.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  source Canonical source fixture text.
    @param[in]  preserved Exact story slice retained from the source.
    @param[in]  expected Expected reconstructed cleanup text.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.2.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    _extracted_path(project_root).write_text(source, encoding="utf-8")

    def _fake_chat_json(_profile, _system, _user, **_kwargs):
        """
        @brief      Return a deterministic cleanup provider response fixture.
        @param[in]  _profile Unused AI profile payload.
        @param[in]  _system Unused cleanup system prompt.
        @param[in]  _user Unused cleanup user prompt.
        @param[in]  _kwargs Unused provider call options.
        @return     Provider-compatible cleanup result payload.
        @exception  AssertionError Raised when provider-call contract assertions fail.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-15
        @version    1.1.0
        """
        if source.startswith(preserved):
            blocks = [_block(1, preserved), _block(2, source[len(preserved) :], "noise")]
        else:
            preserved_start = source.index(preserved)
            blocks = [_block(1, source[:preserved_start], "noise"), _block(2, preserved)]
        return {
            "payload": _payload("cleanup-window-0001", blocks),
            "usage": {},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)
    ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8") == expected


def test_ai_cleanup_corrects_invalid_tail_labels_and_persists_warnings(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify inconsistent repeated classifications produce persisted warnings.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    _extracted_path(project_root).write_text("Header\nStory one.\n\n\f\n\nHeader\nStory two.\n", encoding="utf-8")

    def _fake_chat_json(_profile, _system, _user, **_kwargs):
        """
        @brief      Return a deterministic cleanup provider response fixture.
        @param[in]  _profile Unused AI profile payload.
        @param[in]  _system Unused cleanup system prompt.
        @param[in]  _user Unused cleanup user prompt.
        @param[in]  _kwargs Unused provider call options.
        @return     Provider-compatible cleanup result payload.
        @exception  AssertionError Raised when provider-call contract assertions fail.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-15
        @version    0.1.0
        """
        return {
            "payload": _payload(
                "cleanup-window-0001",
                [
                    _block(1, "Header\n", "header"),
                    _block(2, "Story one.\n"),
                    _block(3, "Header\n", "story"),
                    _block(4, "Story two.\n"),
                ],
            ),
            "usage": {},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)
    report = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    assert any(detail["kind"] == "inconsistent_repeated_text_classification" for detail in report["warning_details"])


def test_ai_cleanup_uses_artifact_type_and_confidence_without_action(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify artifact type controls output while confidence remains metadata.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    _extracted_path(project_root).write_text("Page 1 Story.\n", encoding="utf-8")

    def _fake_chat_json(_profile, _system, _user, **_kwargs):
        """
        @brief      Return a deterministic cleanup provider response fixture.
        @param[in]  _profile Unused AI profile payload.
        @param[in]  _system Unused cleanup system prompt.
        @param[in]  _user Unused cleanup user prompt.
        @param[in]  _kwargs Unused provider call options.
        @return     Provider-compatible cleanup result payload.
        @exception  AssertionError Raised when provider-call contract assertions fail.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-15
        @version    0.1.0
        """
        return {
            "payload": _payload(
                "cleanup-window-0001",
                [_block(1, "Page 1 ", "noise"), _block(2, "Story.\n")],
            ),
            "usage": {},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)
    report = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    assert report["removed_character_count"] == len("Page 1 ")


def test_ai_cleanup_ignores_legacy_label_only_schema(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify legacy label-only responses are rejected.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {"payload": {"results": [{"unit_id": "unit-0001", "label": "story"}]}, "usage": {}},
    )
    with pytest.raises(ValueError, match="unsupported fields"):
        ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)


def test_ai_cleanup_replaces_low_confidence_non_story(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify low-confidence noise is removed without replacement whitespace.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.2.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    _extracted_path(project_root).write_text("Page 1\nStory.\n", encoding="utf-8")

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": _payload(
                "cleanup-window-0001",
                [_block(1, "Page 1\n", "noise", "low"), _block(2, "Story.\n")],
            ),
            "usage": {},
        },
    )
    ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8") == "Story.\n"


def test_ai_cleanup_prompt_includes_language_script_and_neighbor_context(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify cleanup prompts include language, script, and canonical window context.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    _extracted_path(project_root).write_text("First page.\n\n\f\n\nSecond page.\n", encoding="utf-8")
    prompts: list[str] = []
    _install_keep_all_provider(monkeypatch, prompts)

    ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    assert "Language:" in prompts[0] and "Script: latin" in prompts[0]
    assert prompts[0].count("<<< SOURCE WINDOW START >>>") == 1
    assert "First page.\nSecond page.\n" in prompts[0]
    assert "previous_unit_text" not in prompts[0]


def test_ai_cleanup_appends_operator_instructions_to_prompt_and_state(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify operator instructions are rendered and persisted.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    prompts: list[str] = []
    _install_keep_all_provider(monkeypatch, prompts)

    ai_cleanup_service.clean_text(
        project_root,
        manifest,
        _MOCK_PROFILE,
        additional_cleanup_instructions="Preserve glossary names exactly.",
    )

    assert "Preserve glossary names exactly." in prompts[0]
    report = json.loads((project_root / config.CLEANUP_REPORT_FILE_NAME).read_text(encoding="utf-8"))
    assert report["additional_cleanup_instructions"] == "Preserve glossary names exactly."


def test_ai_cleanup_splits_long_input_into_multiple_windows(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify long source text is processed through multiple bounded windows.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    _extracted_path(project_root).write_text(
        "\n\n\f\n\n".join(f"Page {index}.\n" for index in range(1, 7)), encoding="utf-8"
    )
    prompts: list[str] = []
    _install_keep_all_provider(monkeypatch, prompts)

    report = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    assert report["window_count"] == 2
    assert len(prompts) == 2
    assert "Page 4.\n" in prompts[0]
    assert "Page 5.\n" in prompts[1]


def test_ai_cleanup_rejects_profiles_with_no_input_budget(mock_prompt_environment) -> None:
    """
    @brief      Verify profiles without usable input capacity are rejected.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    _configure_cleanup_prompts(mock_prompt_environment)
    pages = ai_cleanup_service._build_source_pages("A source page.\n")
    with pytest.raises(ValueError, match="output capacity"):
        ai_cleanup_service._build_windows(
            pages,
            {
                "context_window": 1024,
                "max_output_tokens": 1,
                "prompt_budget_tokens": 900,
                "safety_margin_tokens": 256,
                "response_expansion_factor": 2.0,
                "target_page_count": 4,
            },
        )


def test_ai_cleanup_small_context_limits_unit_windows() -> None:
    """
    @brief      Verify small model contexts constrain cleanup window size.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    pages = ai_cleanup_service._build_source_pages("\n\n\f\n\n".join(("word " * 100) + "\n" for _ in range(3)))
    windows = ai_cleanup_service._build_windows(
        pages,
        {
            "context_window": 4096,
            "max_output_tokens": 1024,
            "prompt_budget_tokens": 100,
            "safety_margin_tokens": 256,
            "response_expansion_factor": 2.0,
            "target_page_count": 4,
        },
    )
    assert len(windows) >= 2
    assert all(window["pages"] for window in windows)


def test_ai_cleanup_online_profile_uses_direct_context_fraction_without_unit_cap(mock_prompt_environment) -> None:
    """
    @brief      Verify online profiles derive budget directly from the configured context.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    _configure_cleanup_prompts(mock_prompt_environment)
    budget = ai_cleanup_service._build_budget_metadata(
        {**_MOCK_PROFILE, "backend_kind": config.ONLINE_AI_BACKEND_KIND}, "system", "user"
    )
    assert budget["target_page_count"] == 4
    assert budget["response_expansion_factor"] == 2.0
    assert "max_window_units" not in budget


def test_ai_cleanup_resumes_with_new_model_settings(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify compatible checkpoints resume with updated model settings.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    _extracted_path(project_root).write_text(
        "\n\n\f\n\n".join(f"Page {index}.\n" for index in range(1, 6)), encoding="utf-8"
    )
    calls = 0

    def _first_provider(_profile, _system, user_prompt, **kwargs):
        """
        @brief      Return the first-window provider fixture and fail on unexpected calls.
        @param[in]  _profile Unused AI profile payload.
        @param[in]  _system Unused cleanup system prompt.
        @param[in]  user_prompt Rendered cleanup user prompt.
        @param[in]  kwargs Provider call options, including the response schema.
        @return     Provider-compatible cleanup result payload.
        @exception  AssertionError Raised when provider-call contract assertions fail.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-15
        @version    1.1.0
        """
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("stop")
        return {"payload": _keep_all_payload(user_prompt, 1), "usage": {}}

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _first_provider)
    with pytest.raises(RuntimeError, match="stop"):
        ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    prompts: list[str] = []
    _install_keep_all_provider(monkeypatch, prompts)
    second_profile = {**_MOCK_PROFILE, "id": "profile_2", "model_name": "qwen3-14b"}
    report = ai_cleanup_service.clean_text(project_root, manifest, second_profile)

    assert "Page 1.\n" not in prompts[0] and "Page 5.\n" in prompts[0]
    assert len(report["model_settings_history"]) == 2


def test_ai_cleanup_restarts_when_extracted_text_changes(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify changed extracted text invalidates prior cleanup checkpoints.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    _extracted_path(project_root).write_text("Old page.\n", encoding="utf-8")

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stop")),
    )
    with pytest.raises(RuntimeError, match="stop"):
        ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    _extracted_path(project_root).write_text("Replacement page.\n", encoding="utf-8")
    prompts: list[str] = []
    _install_keep_all_provider(monkeypatch, prompts)
    ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    assert "Replacement page.\n" in prompts[0]


def test_ai_cleanup_tolerates_corrupt_state_and_restarts(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify corrupt cleanup state is ignored and processing restarts.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    project_root, manifest = mock_extracted_project
    _configure_cleanup_prompts(mock_prompt_environment)
    (project_root / config.CLEANUP_STATE_FILE_NAME).write_text("{", encoding="utf-8")
    _install_keep_all_provider(monkeypatch)

    report = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    assert "schema_version" not in report
    state = json.loads((project_root / config.CLEANUP_STATE_FILE_NAME).read_text(encoding="utf-8"))
    assert state["status"] == "completed"


# END OF FILE
