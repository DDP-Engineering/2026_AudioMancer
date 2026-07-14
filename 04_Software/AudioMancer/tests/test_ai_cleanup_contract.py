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
@details Verifies SPEC-AIC-001 through SPEC-AIC-005 and durable requirements
         REQ-FUNC-058 through REQ-FUNC-060 plus REQ-NFR-019.
@author Eng. Dan Dumitru Pasare
@date 2026-07-14
@version 0.1.0
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
    @param[in]  blocks Ordered response blocks.
    @return     Cleanup response payload.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-14
    @version    0.1.0
    """
    return {"window_id": window_id, "text_blocks": blocks}


def _block(
    block_id: int,
    text: str,
    artifact_type: str,
    confidence: str = "high",
) -> dict[str, object]:
    """
    @brief      Build one cleanup block fixture.
    @return     Cleanup response block.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-14
    @version    0.1.0
    """
    return {
        "text_block_id": block_id,
        "text_block": text,
        "artifact_type": artifact_type,
        "confidence": confidence,
    }


def test_cleanup_validation_preserves_exact_order_and_accepts_advisory_removal_text() -> None:
    """
    @brief      Handle test cleanup validation preserves exact order and accepts advisory removal text.
    @version    1.0.0
    """
    pages = ai_cleanup_service._build_source_pages(
        ai_cleanup_service._canonicalize_source_text(
            "Page 1 It was a sunny day.\r\n\r\n\f\r\n\r\nThe Warhound\r\nThe street was quiet.\r\n"
        )
    )
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "advisory text need not match", "noise"),
            _block(2, "It was a sunny day.\n", "story"),
            _block(3, "also advisory", "header"),
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
        ([_block(1, "sunny day.\n", "story")], "unexplained source gap"),
        (
            [
                _block(1, "Second page.\n", "story"),
                _block(2, "First page.\n", "story"),
            ],
            "exact source slice",
        ),
        ([_block(2, "First page.\n", "story")], "sequential"),
    ],
)
def test_cleanup_validation_rejects_changed_unexplained_or_reordered_preserved_text(
    blocks: list[dict[str, object]],
    error_match: str,
) -> None:
    """
    @brief      Handle test cleanup validation rejects changed unexplained or reordered preserved text.
    @version    1.0.0
    """
    pages = ai_cleanup_service._build_source_pages("First page.\n\n\f\n\nSecond page.\n")

    with pytest.raises(ValueError, match=error_match):
        ai_cleanup_service._validate_response(
            _payload("cleanup-window-0001", blocks),
            pages,
            "cleanup-window-0001",
        )


def test_cleanup_removal_policy_preserves_medium_confidence_and_warns_for_entire_page() -> None:
    """
    @brief      Handle test cleanup removal policy preserves medium confidence and warns for entire page.
    @version    1.0.0
    """
    pages = ai_cleanup_service._build_source_pages("Page 1\n\n\f\n\nDiscarded title page\n")
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "Page 1\n", "noise", "medium"),
            _block(2, "copied removal text is advisory", "noise", "high"),
        ],
    )

    validated = ai_cleanup_service._validate_response(
        response,
        pages,
        "cleanup-window-0001",
    )

    assert [item["text_block"] for item in validated["preserved_blocks"]] == ["Page 1\n"]
    assert any(detail["kind"] == "entire_page_removed" for detail in validated["warning_details"])


def test_cleanup_prompt_uses_once_canonicalized_source_inside_resolved_markers() -> None:
    """
    @brief      Handle test cleanup prompt uses once canonicalized source inside resolved markers.
    @version    1.0.0
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
    @brief      Handle test cleanup contract and budget target four pages with output reservation.
    @version    1.0.0
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
    @brief      Handle test cleanup budget rejects profile that cannot return one page.
    @version    1.0.0
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
    @brief      Verify SPEC-AIC-005 and REQ-FUNC-060 checkpoint compatibility.
    @version    1.0.0
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


def test_ai_cleanup_integration_uses_current_contract_and_preserves_story(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Handle test ai cleanup integration uses cleanup contract and preserves inline story.
    @version    1.0.0
    """
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    extracted_path.write_bytes(b"Copyright 2026 Example. It was a sunny day.\r\n")
    (mock_prompt_environment / "text_cleanup_user.txt").write_text(
        "Window: {window_id}\nLanguage: {source_language_hint}\nScript: {dominant_script_hint}\n"
        "{source_window_block}\nInstructions: {additional_cleanup_instructions}",
        encoding="utf-8",
    )

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **kwargs):
        """
        @brief      Handle fake chat json.
        @version    1.0.0
        """
        assert "Copyright 2026 Example. It was a sunny day.\n" in user_prompt
        assert kwargs["response_schema_name"] == "text_cleanup_blocks"
        assert "schema_version" not in kwargs["response_schema"]["properties"]
        return {
            "payload": _payload(
                "cleanup-window-0001",
                [
                    _block(1, "advisory", "noise"),
                    _block(2, "It was a sunny day.\n", "story"),
                ],
            ),
            "usage": {"input_tokens": 10, "output_tokens": 8, "total_tokens": 18, "usage_available": True},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)

    report = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)

    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    assert cleaned_path.read_text(encoding="utf-8") == "It was a sunny day.\n"
    assert "schema_version" not in report
    assert report["removed_character_count"] == len("Copyright 2026 Example. ")
    assert report["validated_window_decisions"][0]["removed_ranges"][0]["text"] == ("Copyright 2026 Example. ")
    state = json.loads(
        (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANUP_STATE_FILE_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert state["resume_checkpoint"] is None


def test_cleanup_window_contract_uses_one_canonical_source_without_page_indices() -> None:
    """
    @brief      Verify SPEC-AIC-001 and REQ-FUNC-058 use one canonical window source.
    @version    1.0.0
    """
    source = "1\n\nStory one.\n\n2\n\nStory two.\n"
    pages = ai_cleanup_service._build_source_pages(source)
    response = _payload(
        "cleanup-window-0001",
        [
            {
                "text_block_id": 1,
                "text_block": "printed page number",
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
                "text_block": "printed page number",
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
    @brief      Verify SPEC-AIC-003 and REQ-FUNC-060 use neutral prompt names only.
    @version    1.0.0
    """
    validated_names: list[tuple[str, ...]] = []
    rendered_names: list[str] = []

    def _validate(names: list[str]) -> None:
        """
        @brief      Capture prompt names passed to validation.
        @version    1.0.0
        """
        validated_names.append(tuple(names))

    def _render(name: str, _values: dict[str, object]) -> str:
        """
        @brief      Capture the selected prompt template name.
        @version    1.0.0
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
    @brief      Verify SPEC-AIC-002, SPEC-AIC-003, REQ-FUNC-059, and REQ-FUNC-060.
    @version    1.0.0
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


def test_whitespace_only_source_gap_is_recorded_and_accepted() -> None:
    """
    @brief      Verify SPEC-AIC-001 and REQ-FUNC-058 whitespace normalization.
    @version    1.0.0
    """
    pages = ai_cleanup_service._build_source_pages("Story paragraph.\n\n* * *\nNext paragraph.\n")
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "Story paragraph.\n", "story"),
            _block(2, "* * *\n", "separator"),
            _block(3, "Next paragraph.\n", "story"),
        ],
    )

    validated = ai_cleanup_service._validate_response(response, pages, "cleanup-window-0001")

    assert validated["preserved_text"] == "Story paragraph.\n* * *\nNext paragraph.\n"
    assert validated["normalized_whitespace_character_count"] == 1
    assert validated["normalized_whitespace_ranges"] == [
        {
            "source_window_start": len("Story paragraph.\n"),
            "source_window_end": len("Story paragraph.\n\n"),
            "text": "\n",
            "reason": "whitespace_only_gap",
        }
    ]


# END OF FILE
