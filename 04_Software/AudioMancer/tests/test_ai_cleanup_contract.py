#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_cleanup_contract.py
@brief Red/green checks for exact-source AI Cleanup blocks.
@details Verifies exact ordered source slices, deterministic artifact replacement,
         whitespace reconstruction, checkpoint invalidation, and durable
         requirements REQ-FUNC-058 through REQ-FUNC-060 plus REQ-NFR-019.
@author Eng. Dan Dumitru Pasare
@date 2026-07-15
@version 1.2.0
"""

# IMPORTS

import json

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


def _payload(window_id: str, blocks: list[dict[str, object]]) -> dict[str, object]:
    """
    @brief      Build one cleanup response fixture.
    @param[in]  window_id Expected cleanup window identity.
    @param[in]  blocks Ordered cleanup response blocks.
    @return     Cleanup response payload.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.2.0
    """
    return {"window_id": window_id, "text_blocks": blocks}


def _block(
    block_id: int,
    text: str,
    artifact_type: str,
    confidence: str = "high",
) -> dict[str, object]:
    """
    @brief      Build one exact-source cleanup block fixture.
    @param[in]  block_id Sequential cleanup block identifier.
    @param[in]  text Exact source text for the block.
    @param[in]  artifact_type Cleanup artifact classification.
    @param[in]  confidence Model confidence metadata.
    @return     Cleanup response block payload.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.2.0
    """
    return {
        "text_block_id": block_id,
        "text_block": text,
        "artifact_type": artifact_type,
        "confidence": confidence,
    }


def test_cleanup_validation_preserves_exact_order_for_every_block() -> None:
    """
    @brief      Verify every returned block is an exact ordered source slice.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    pages = ai_cleanup_service._build_source_pages(
        ai_cleanup_service._canonicalize_source_text(
            "Page 1 It was a sunny day.\r\n\r\n\f\r\n\r\nThe Warhound\r\nThe street was quiet.\r\n"
        )
    )
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "Page 1 ", "noise"),
            _block(2, "It was a sunny day.\n", "story"),
            _block(3, "The Warhound\n", "header"),
            _block(4, "The street was quiet.\n", "story"),
        ],
    )

    validated = ai_cleanup_service._validate_response(
        response,
        pages,
        "cleanup-window-0001",
    )

    assert [item["text_block"] for item in validated["preserved_blocks"]] == [
        "It was a sunny day.\n",
        "The street was quiet.\n",
    ]
    assert validated["removed_character_count"] == len("Page 1 ") + len("The Warhound\n")


@pytest.mark.parametrize(
    ("blocks", "error_match"),
    [
        ([_block(1, "It was a bright day.\n", "story")], "exact source slice"),
        ([_block(1, "page.\n", "story")], "unexplained source gap"),
        (
            [
                _block(1, "Second page.\n", "story"),
                _block(2, "First page.\n", "story"),
            ],
            "unexplained source gap",
        ),
        ([_block(2, "First page.\n", "story")], "sequential"),
    ],
)
def test_cleanup_validation_rejects_changed_unexplained_or_reordered_preserved_text(
    blocks: list[dict[str, object]],
    error_match: str,
) -> None:
    """
    @brief      Verify changed, skipped, reordered, or misnumbered source blocks are rejected.
    @param[in]  blocks Ordered cleanup response blocks.
    @param[in]  error_match Expected validation-error message fragment.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    pages = ai_cleanup_service._build_source_pages("First page.\n\n\f\n\nSecond page.\n")

    with pytest.raises(ValueError, match=error_match):
        ai_cleanup_service._validate_response(
            _payload("cleanup-window-0001", blocks),
            pages,
            "cleanup-window-0001",
        )


def test_cleanup_removal_policy_ignores_confidence() -> None:
    """
    @brief      Verify confidence does not change artifact-specific rendering.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.2.0
    """
    pages = ai_cleanup_service._build_source_pages("Page 1\n\n\f\n\nDiscarded title page\n")
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "Page 1\n", "noise", "medium"),
            _block(2, "Discarded title page\n", "noise", "low"),
        ],
    )

    validated = ai_cleanup_service._validate_response(
        response,
        pages,
        "cleanup-window-0001",
    )

    assert validated["preserved_blocks"] == []
    assert validated["reconstructed_text"] == ""
    assert any(detail["kind"] == "entire_page_removed" for detail in validated["warning_details"])


def test_cleanup_prompt_uses_once_canonicalized_source_inside_resolved_markers() -> None:
    """
    @brief      Verify the prompt contains canonical source text once between stable markers.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    canonical = ai_cleanup_service._canonicalize_source_text("Prima pagin?.\r\n\r\n\f\r\n\r\nA doua pagin?.\r\n")
    pages = ai_cleanup_service._build_source_pages(canonical)

    prompt = ai_cleanup_service._render_cleanup_user_prompt(
        pages,
        "cleanup-window-0001",
        "Romanian",
        "Latin",
        "Preserve names exactly.",
    )

    assert "\r" not in prompt
    assert prompt.count("Prima pagin?.\n") == 1
    assert prompt.count("A doua pagin?.\n") == 1
    assert "<<< SOURCE WINDOW START >>>" in prompt
    assert "<<< SOURCE WINDOW END >>>" in prompt
    assert "{" not in prompt and "}" not in prompt


def test_cleanup_schema_and_budget_target_four_pages_with_output_reservation() -> None:
    """
    @brief      Verify cleanup budgeting targets four pages while reserving response capacity.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    schema = ai_cleanup_service._build_response_schema()
    assert set(schema["properties"]) == {"window_id", "text_blocks"}
    assert schema["properties"]["text_blocks"]["minItems"] == 1

    pages = ai_cleanup_service._build_source_pages("One.\n\n\f\n\nTwo.\n\n\f\n\nThree.\n\n\f\n\nFour.\n\n\f\n\nFive.\n")
    windows = ai_cleanup_service._build_windows(
        pages,
        {
            "context_window": 32768,
            "max_output_tokens": 8192,
            "prompt_budget_tokens": 100,
            "safety_margin_tokens": 512,
            "response_expansion_factor": 2.0,
            "target_page_count": 4,
        },
    )

    assert [len(window["pages"]) for window in windows] == [4, 1]
    assert all(window["estimated_output_tokens"] <= 8192 for window in windows)


def test_cleanup_budget_rejects_profile_that_cannot_return_one_page() -> None:
    """
    @brief      Verify insufficient response capacity rejects even a one-page window.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    pages = ai_cleanup_service._build_source_pages("A long enough source page for JSON output reservation.\n")

    with pytest.raises(ValueError, match="output capacity"):
        ai_cleanup_service._build_windows(
            pages,
            {
                "context_window": 1024,
                "max_output_tokens": 1,
                "prompt_budget_tokens": 100,
                "safety_margin_tokens": 256,
                "response_expansion_factor": 2.0,
                "target_page_count": 4,
            },
        )


def test_cleanup_checkpoint_compatibility_requires_schema_and_input_identity() -> None:
    """
    @brief      Verify checkpoint compatibility requires current contract and input identities.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    compatible = {
        "contract_fingerprint": ai_cleanup_service._CONTRACT_FINGERPRINT,
        "input_fingerprint": "input-a",
        "additional_cleanup_instructions_fingerprint": "instructions-a",
        "completed_windows": [{"window_id": "cleanup-window-0001"}],
    }

    assert ai_cleanup_service._checkpoint_is_compatible(
        compatible,
        "input-a",
        "instructions-a",
    )
    assert not ai_cleanup_service._checkpoint_is_compatible(
        {"classifications": {"unit-0001": "story"}},
        "input-a",
        "instructions-a",
    )
    assert not ai_cleanup_service._checkpoint_is_compatible(
        compatible,
        "input-b",
        "instructions-a",
    )


def test_ai_cleanup_integration_reconstructs_whitespace_and_artifact_separators(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify SPEC-AICR-003, SPEC-AICR-004, and REQ-FUNC-060 reconstruction.
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
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_bytes(
        b"HEADER\r\n\r\nFirst paragraph.\r\n\r\n* * *\r\n\r\nChapter 2\r\n\r\nSecond paragraph.\r\n"
    )
    (mock_prompt_environment / "text_cleanup_user.txt").write_text(
        "Window: {window_id}\nLanguage: {source_language_hint}\nScript: {dominant_script_hint}\n"
        "{source_window_block}\nInstructions: {additional_cleanup_instructions}",
        encoding="utf-8",
    )

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **kwargs):
        """
        @brief      Return an exact-source cleanup provider response fixture.
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
        assert "HEADER\n\nFirst paragraph.\n\n* * *\n\nChapter 2\n\nSecond paragraph.\n" in user_prompt
        assert kwargs["response_schema_name"] == "text_cleanup_blocks"
        assert "schema_version" not in kwargs["response_schema"]["properties"]
        return {
            "payload": _payload(
                "cleanup-window-0001",
                [
                    _block(1, "HEADER", "header", "low"),
                    _block(2, "First paragraph.", "story"),
                    _block(3, "* * *", "separator", "medium"),
                    _block(4, "Chapter 2", "heading"),
                    _block(5, "Second paragraph.", "story"),
                ],
            ),
            "usage": {"input_tokens": 10, "output_tokens": 8, "total_tokens": 18, "usage_available": True},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)

    report = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    assert cleaned_path.read_text(encoding="utf-8") == ("First paragraph.\n\n\n\nSecond paragraph.")
    assert "schema_version" not in report
    assert report["removed_character_count"] == len("HEADER") + len("* * *") + len("Chapter 2")
    assert report["restored_whitespace_character_count"] == 9
    assert report["validated_window_decisions"][0]["removed_ranges"][0]["text"] == "HEADER"
    state = json.loads(
        (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANUP_STATE_FILE_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert state["resume_checkpoint"] is None


def test_cleanup_window_contract_uses_one_canonical_source_without_page_indices() -> None:
    """
    @brief      Verify the provider contract uses one canonical source without page indices.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    source = "1\n\nStory one.\n\n2\n\nStory two.\n"
    pages = ai_cleanup_service._build_source_pages(source)
    response = _payload(
        "cleanup-window-0001",
        [
            {
                "text_block_id": 1,
                "text_block": "1\n\n",
                "artifact_type": "noise",
                "confidence": "high",
            },
            {
                "text_block_id": 2,
                "text_block": "Story one.\n\n",
                "artifact_type": "story",
                "confidence": "high",
            },
            {
                "text_block_id": 3,
                "text_block": "2\n\n",
                "artifact_type": "noise",
                "confidence": "high",
            },
            {
                "text_block_id": 4,
                "text_block": "Story two.\n",
                "artifact_type": "story",
                "confidence": "high",
            },
        ],
    )

    schema = ai_cleanup_service._build_response_schema()
    block_properties = schema["properties"]["text_blocks"]["items"]["properties"]
    validated = ai_cleanup_service._validate_response(
        response,
        pages,
        "cleanup-window-0001",
    )

    assert "source_page_index" not in block_properties
    assert [item["text_block"] for item in validated["preserved_blocks"]] == [
        "Story one.\n\n",
        "Story two.\n",
    ]
    assert validated["removed_character_count"] == len("1\n\n") + len("2\n\n")

    response_with_page_field = _payload(
        "cleanup-window-0001",
        [
            {
                "text_block_id": 1,
                "source_page_index": 1,
                "text_block": source,
                "artifact_type": "story",
                "confidence": "high",
            }
        ],
    )
    with pytest.raises(ValueError, match="unsupported fields"):
        ai_cleanup_service._validate_response(
            response_with_page_field,
            pages,
            "cleanup-window-0001",
        )


def test_cleanup_runtime_uses_only_neutral_cleanup_prompt_names(monkeypatch) -> None:
    """
    @brief      Verify runtime prompt lookup uses only neutral cleanup prompt names.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    validated_names: list[tuple[str, ...]] = []
    rendered_names: list[str] = []

    def _validate(names: list[str]) -> None:
        """
        @brief      Capture prompt names passed to template validation.
        @param[in]  names Prompt template names to validate.
        @return     None.
        @exception  None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-15
        @version    1.1.0
        """
        validated_names.append(tuple(names))

    def _render(name: str, _values: dict[str, object]) -> str:
        """
        @brief      Capture the selected prompt name and return placeholder text.
        @param[in]  name Prompt template name.
        @param[in]  _values Unused prompt substitution values.
        @return     Rendered placeholder prompt text.
        @exception  None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-15
        @version    1.1.0
        """
        rendered_names.append(name)
        return "rendered prompt"

    monkeypatch.setattr(
        ai_cleanup_service.prompt_template_service,
        "validate_required_prompts",
        _validate,
    )
    monkeypatch.setattr(
        ai_cleanup_service.prompt_template_service,
        "render_prompt",
        _render,
    )

    prompt = ai_cleanup_service._render_cleanup_user_prompt(
        ai_cleanup_service._build_source_pages("Story.\n"),
        "cleanup-window-0001",
        "English",
        "Latin",
        "",
    )

    assert prompt == "rendered prompt"
    assert validated_names == []
    assert rendered_names == ["text_cleanup_user"]


def test_response_contract_has_six_artifact_types_without_version_or_action() -> None:
    """
    @brief      Verify the response schema has six artifact types and no version or action.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    schema = ai_cleanup_service._build_response_schema()
    assert set(schema["required"]) == {"window_id", "text_blocks"}
    assert set(schema["properties"]) == {"window_id", "text_blocks"}
    block_schema = schema["properties"]["text_blocks"]["items"]
    assert set(block_schema["required"]) == {
        "text_block_id",
        "text_block",
        "artifact_type",
        "confidence",
    }
    assert set(block_schema["properties"]) == set(block_schema["required"])
    assert set(block_schema["properties"]["artifact_type"]["enum"]) == {
        "header",
        "footer",
        "noise",
        "separator",
        "heading",
        "story",
    }


def test_whitespace_only_source_gaps_are_retained_for_spacing_rendering() -> None:
    """
    @brief      Verify AICU-004 and REQ-FUNC-058 retained whitespace-gap rendering.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.1.0
    """
    source = "First paragraph.\n\nSecond paragraph.\n"
    pages = ai_cleanup_service._build_source_pages(source)
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "First paragraph.", "story"),
            _block(2, "Second paragraph.", "story"),
        ],
    )

    validated = ai_cleanup_service._validate_response(response, pages, "cleanup-window-0001")

    assert validated["reconstructed_text"] == "First paragraph.Second paragraph."
    assert validated["restored_whitespace_character_count"] == 3
    assert validated["restored_whitespace_ranges"] == [
        {
            "source_window_start": len("First paragraph."),
            "source_window_end": len("First paragraph.\n\n"),
            "text": "\n\n",
            "reason": "restored_whitespace_gap",
        },
        {
            "source_window_start": len("First paragraph.\n\nSecond paragraph."),
            "source_window_end": len(source),
            "text": "\n",
            "reason": "restored_whitespace_gap",
        },
    ]


def test_artifact_types_apply_deterministic_rendering() -> None:
    """
    @brief      Verify AISP-001 and REQ-FUNC-059 selectable artifact rendering.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.2.0
    """
    source = "HeaderStory.SeparatorHeadingFooterNoise"
    pages = ai_cleanup_service._build_source_pages(source)
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "Header", "header", "low"),
            _block(2, "Story.", "story", "low"),
            _block(3, "Separator", "separator", "low"),
            _block(4, "Heading", "heading", "medium"),
            _block(5, "Footer", "footer", "medium"),
            _block(6, "Noise", "noise", "high"),
        ],
    )

    validated = ai_cleanup_service._validate_response(response, pages, "cleanup-window-0001")

    assert validated["reconstructed_text"] == "Story.\n\n\n\n"
    assert [item["replacement"] for item in validated["removed_ranges"]] == [
        "",
        "\n\n",
        "\n\n",
        "",
        "",
    ]

    selected_rendering = ai_cleanup_service._render_validated_window(
        validated,
        {"header", "footer", "noise"},
    )

    assert selected_rendering["reconstructed_text"] == "\n\nStory.\n\n\n\n"
    assert [item["replacement"] for item in selected_rendering["removed_ranges"]] == [
        "\n\n",
        "",
        "",
        "\n\n",
        "\n\n",
    ]

    for selected_category in ("header", "separator", "heading", "footer", "noise"):
        category_rendering = ai_cleanup_service._render_validated_window(
            validated,
            {selected_category},
        )
        rendered_by_category = {
            str(item["decision"]["artifact_type"]): item["replacement"] for item in category_rendering["removed_ranges"]
        }

        assert rendered_by_category[selected_category] == "\n\n"
        assert all(
            replacement == "" for category, replacement in rendered_by_category.items() if category != selected_category
        )

    empty_rendering = ai_cleanup_service._render_validated_window(validated, set())
    assert empty_rendering["reconstructed_text"] == "Story."
    assert all(item["replacement"] == "" for item in empty_rendering["removed_ranges"])


def test_ai_cleanup_spacing_reapplication_persists_selection_without_provider(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify AISP-002 and REQ-FUNC-061 retained-decision spacing reapplication.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_text("Header\n\nStory.\nFooter\nNoise", encoding="utf-8")
    (mock_prompt_environment / "text_cleanup_user.txt").write_text(
        "Window: {window_id}\nLanguage: {source_language_hint}\nScript: {dominant_script_hint}\n"
        "{source_window_block}\nInstructions: {additional_cleanup_instructions}",
        encoding="utf-8",
    )

    provider_call_count = 0

    def _fake_chat_json(*_args, **_kwargs):
        """
        @brief      Return one exact-source classification response.
        @return     Provider-compatible cleanup response fixture.
        @exception  None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-15
        @version    0.1.0
        """
        nonlocal provider_call_count
        provider_call_count += 1
        return {
            "payload": _payload(
                "cleanup-window-0001",
                [
                    _block(1, "Header", "header"),
                    _block(2, "Story.", "story"),
                    _block(3, "Footer", "footer"),
                    _block(4, "Noise", "noise"),
                ],
            ),
            "usage": {},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)
    ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    assert provider_call_count == 1

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: pytest.fail("Spacing reapplication must not call the provider."),
    )
    first_report = ai_cleanup_service.apply_spacing_selection(project_root, {"header", "noise"})
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    first_text = cleaned_path.read_text(encoding="utf-8")
    second_report = ai_cleanup_service.apply_spacing_selection(project_root, {"noise", "header"})

    assert first_text == "\n\nStory.\n\n"
    assert cleaned_path.read_text(encoding="utf-8") == first_text
    assert first_report["selected_spacing_categories"] == ["header", "noise"]
    assert second_report["selected_spacing_categories"] == ["header", "noise"]
    empty_report = ai_cleanup_service.apply_spacing_selection(project_root, set())
    assert cleaned_path.read_text(encoding="utf-8") == "Story."
    assert empty_report["selected_spacing_categories"] == []
    persisted_report = json.loads(
        (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANUP_REPORT_FILE_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert persisted_report["selected_spacing_categories"] == []


# END OF FILE
