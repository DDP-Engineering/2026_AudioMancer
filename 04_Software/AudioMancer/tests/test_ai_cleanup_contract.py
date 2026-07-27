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
@brief Red/green checks for source-grounded AI Cleanup blocks.
@details Verifies exact ordered source slices, uniquely anchored modified Story
         fallback, deterministic artifact replacement, whitespace reconstruction,
         checkpoint invalidation, and durable requirements REQ-FUNC-058 through
         REQ-FUNC-064 plus REQ-NFR-019.
@author Eng. Dan Dumitru Pasare
@date 2026-07-15
@version 1.5.0
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
_STORY_EDGE_START = (
    "Elizabeth walked through the quiet garden before sunrise and considered the sealed letter very carefully."
)
_STORY_EDGE_END = (
    "After breakfast she returned to the house and placed the folded paper beside the eastern window."
)
_MODIFIED_STORY_SOURCE = (
    f"{_STORY_EDGE_START}\n"
    "She was determined not to venture near her, lest she might hear too much.\n"
    f"{_STORY_EDGE_END}"
)
_MODIFIED_STORY_AI = _MODIFIED_STORY_SOURCE.replace("lest she", "llest she")
# @brief Document rendering unwraps the fixture's hard line wraps into one continuous paragraph.
_MODIFIED_STORY_AI_UNWRAPPED = _MODIFIED_STORY_AI.replace("\n", " ")
_OMITTED_SOURCE_LINE = "�To whom I have related the affair�"


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
    assert [item["match_mode"] for item in validated["preserved_blocks"]] == ["exact", "exact"]
    assert validated["modified_story_block_count"] == 0
    assert validated["removed_character_count"] == len("Page 1 ") + len("The Warhound\n")


def test_cleanup_validation_accepts_uniquely_bracketed_modified_story_text() -> None:
    """
    @brief      Verify AICU-007 and REQ-FUNC-062 accept one uniquely bounded Story correction.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    source = f"HEADER\n\n{_MODIFIED_STORY_SOURCE}\n\nFOOTER"
    pages = ai_cleanup_service._build_source_pages(source)
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "HEADER", "header"),
            _block(2, _MODIFIED_STORY_AI, "story"),
            _block(3, "FOOTER", "footer"),
        ],
    )

    validated = ai_cleanup_service._validate_response(response, pages, "cleanup-window-0001")

    preserved = validated["preserved_blocks"][0]
    source_start = source.index(_MODIFIED_STORY_SOURCE)
    assert validated["reconstructed_text"] == f"\n\n{_MODIFIED_STORY_AI}\n\n"
    assert validated["modified_story_block_count"] == 1
    assert preserved["text_block"] == _MODIFIED_STORY_AI
    assert preserved["source_text"] == _MODIFIED_STORY_SOURCE
    assert preserved["match_mode"] == "anchored_modified"
    assert preserved["source_window_start"] == source_start
    assert preserved["source_window_end"] == source_start + len(_MODIFIED_STORY_SOURCE)
    assert any(
        detail["kind"] == "modified_story_text_accepted" and detail["text_block_id"] == 2
        for detail in validated["warning_details"]
    )


def test_cleanup_validation_accepts_arbitrary_interior_with_normalized_story_edges() -> None:
    """
    @brief      Verify AICU-007 normalized anchors ignore edge case, punctuation, and whitespace.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    source_story = (
        f"\u201c{_STORY_EDGE_START.upper()}\u201d\n"
        "This original interior may be replaced without a similarity threshold.\n"
        f"\u201c{_STORY_EDGE_END.upper()}!\u201d"
    )
    ai_story = (
        f"{_STORY_EDGE_START.lower().replace(' ', '  ')}\n"
        "The provider supplied a completely different interior passage.\n"
        f"{_STORY_EDGE_END.lower()}"
    )

    validated = ai_cleanup_service._validate_response(
        _payload("cleanup-window-0001", [_block(1, ai_story, "story")]),
        ai_cleanup_service._build_source_pages(source_story),
        "cleanup-window-0001",
    )

    assert validated["reconstructed_text"] == ai_story
    assert validated["preserved_blocks"][0]["source_text"] == source_story
    assert validated["preserved_blocks"][0]["match_mode"] == "anchored_modified"


def test_cleanup_validation_preserves_uniquely_bounded_internal_source_gap() -> None:
    """
    @brief      Verify AICU-008 and REQ-FUNC-063 preserve one exact internal source gap.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    source = f"Opening story.\n\n{_OMITTED_SOURCE_LINE}\n\nPage 24\n\nClosing story."
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "Opening story.", "story"),
            _block(2, "Page 24", "noise"),
            _block(3, "Closing story.", "story"),
        ],
    )

    validated = ai_cleanup_service._validate_response(
        response,
        ai_cleanup_service._build_source_pages(source),
        "cleanup-window-0001",
    )

    preserved_gap = validated["preserved_source_gaps"][0]
    expected_gap = f"\n\n{_OMITTED_SOURCE_LINE}\n\n"
    assert validated["reconstructed_text"] == f"Opening story.{expected_gap}\n\nClosing story."
    assert validated["preserved_source_gap_count"] == 1
    assert preserved_gap == {
        "source_window_start": len("Opening story."),
        "source_window_end": len(f"Opening story.{expected_gap}"),
        "text": expected_gap,
        "reason": "unclassified_source_gap_preserved",
    }
    assert any(
        detail["kind"] == "unclassified_source_gap_preserved"
        and detail["source_window_start"] == preserved_gap["source_window_start"]
        and detail["source_window_end"] == preserved_gap["source_window_end"]
        for detail in validated["warning_details"]
    )


def test_cleanup_validation_rejects_ambiguous_internal_source_gap_delimiter() -> None:
    """
    @brief      Verify AICU-008 rejects a repeated exact delimiter after an omitted gap.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    source = "Opening story.\n\nOmitted text.\n\nPage 24\n\nPage 24\n\nClosing story."
    response = _payload(
        "cleanup-window-0001",
        [
            _block(1, "Opening story.", "story"),
            _block(2, "Page 24", "noise"),
            _block(3, "Closing story.", "story"),
        ],
    )

    with pytest.raises(ValueError, match="unexplained source gap"):
        ai_cleanup_service._validate_response(
            response,
            ai_cleanup_service._build_source_pages(source),
            "cleanup-window-0001",
        )


@pytest.mark.parametrize(
    ("source", "blocks"),
    [
        (
            f"{_MODIFIED_STORY_SOURCE}\n\n{_MODIFIED_STORY_SOURCE}",
            [
                _block(1, _MODIFIED_STORY_AI, "story"),
                _block(2, _MODIFIED_STORY_AI.replace("llest", "allest"), "story"),
            ],
        ),
        ("Short original text.", [_block(1, "Short changed text.", "story")]),
        (
            _MODIFIED_STORY_SOURCE,
            [_block(1, _MODIFIED_STORY_AI.replace("Elizabeth", "Darcy"), "story")],
        ),
        (_MODIFIED_STORY_SOURCE, [_block(1, _MODIFIED_STORY_AI, "noise")]),
        (
            f"{_MODIFIED_STORY_SOURCE}\nFOOTER\n{_MODIFIED_STORY_SOURCE}\nFOOTER",
            [_block(1, _MODIFIED_STORY_AI, "story"), _block(2, "FOOTER", "footer")],
        ),
    ],
    ids=[
        "adjacent-modified-story",
        "short-normalized-anchors",
        "changed-normalized-start",
        "modified-non-story",
        "ambiguous-next-delimiter",
    ],
)
def test_cleanup_validation_rejects_unsafe_modified_story_fallbacks(
    source: str,
    blocks: list[dict[str, object]],
) -> None:
    """
    @brief      Verify AICU-007 and REQ-FUNC-062 reject unsafe or ambiguous fallback cases.
    @param[in]  source Canonical source window fixture.
    @param[in]  blocks Provider response block fixtures.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    0.1.0
    """
    with pytest.raises(ValueError, match="exact source slice"):
        ai_cleanup_service._validate_response(
            _payload("cleanup-window-0001", blocks),
            ai_cleanup_service._build_source_pages(source),
            "cleanup-window-0001",
        )


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
    assert not validated["reconstructed_text"].strip()
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


def test_cleanup_document_contract_rejects_legacy_metadata_fields() -> None:
    """Verify the authoritative document accepts only the approved compact fields."""
    source = "Story."
    document = ai_cleanup_service._build_cleanup_document(
        "completed",
        ai_cleanup_service._source_fingerprint(source),
        "",
        ai_cleanup_service.token_usage_service.empty_token_usage(),
        [{"kind": "human_review_required"}],
        [{"start": 0, "end": len(source), "kind": "story"}],
        {"heading", "separator"},
    )

    validated = ai_cleanup_service._validate_cleanup_document(document)

    assert validated == document
    assert set(validated) == {
        "status",
        "mode",
        "source_fingerprint",
        "instructions",
        "token_usage",
        "warnings",
        "decisions",
    }
    with pytest.raises(ValueError, match="unsupported fields"):
        ai_cleanup_service._validate_cleanup_document({**document, "schema_version": 1})

def test_cleanup_source_offset_resume_trims_mid_page_with_absolute_offsets() -> None:
    """Verify retained decisions resume from their last absolute source offset."""
    source_stream = "First segment.\n\fSecond segment.\nThird segment."
    restored_offset = len("First segment.\n\fSec")
    prefix_items = [{"start": 0, "end": restored_offset, "kind": "story"}]

    source_offset = ai_cleanup_service._validate_decision_items(
        prefix_items,
        source_length=len(source_stream),
    )
    remaining_pages = ai_cleanup_service._source_pages_after_offset(
        ai_cleanup_service._build_source_pages(source_stream),
        source_offset,
    )

    assert source_offset == restored_offset
    assert remaining_pages[0]["source_start"] == restored_offset
    assert ai_cleanup_service._window_source_text(remaining_pages) == source_stream[restored_offset:]
    with pytest.raises(ValueError, match="exceeds"):
        ai_cleanup_service._source_pages_after_offset(remaining_pages, len(source_stream) + 1)
    with pytest.raises(ValueError, match="continuous"):
        ai_cleanup_service._validate_decision_items(
            [{"start": 1, "end": restored_offset, "kind": "story"}],
            source_length=len(source_stream),
        )


def test_ai_cleanup_resume_uses_source_offset_after_budget_repartition(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify AICU-009 and REQ-FUNC-064 resume only the unprocessed source suffix.
    @param[in]  mock_extracted_project Extracted-project pytest fixture.
    @param[in]  mock_prompt_environment Prompt-directory pytest fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-16
    @version    0.1.0
    """
    project_root, manifest = mock_extracted_project
    extracted_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.EXTRACTED_TEXT_FILE_NAME
    page_separator = "\n\n\f\n\n"
    page_texts = [f"Page {index} " + (chr(96 + index) * 1000) + ".\n" for index in range(1, 6)]
    extracted_path.write_text(page_separator.join(page_texts), encoding="utf-8")
    canonical_source = ai_cleanup_service._canonicalize_source_text(extracted_path.read_text(encoding="utf-8"))
    source_pages = ai_cleanup_service._build_source_pages(canonical_source)
    expected_source_stream = ai_cleanup_service._window_source_text(source_pages)
    expected_restored_offset = len(ai_cleanup_service._window_source_text(source_pages[:2]))
    (mock_prompt_environment / "text_cleanup_user.txt").write_text(
        "Window: {window_id}\nLanguage: {source_language_hint}\nScript: {dominant_script_hint}\n"
        "{source_window_block}\nInstructions: {additional_cleanup_instructions}",
        encoding="utf-8",
    )

    first_call_count = 0

    def _source_from_prompt(user_prompt: str) -> str:
        """
        @brief      Extract provider-visible source text from one cleanup prompt fixture.
        @param[in]  user_prompt Rendered cleanup user prompt.
        @return     Canonical source-window text between stable prompt markers.
        @exception  IndexError Raised when required source markers are absent.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-16
        @version    0.1.0
        """
        start_marker = "<<< SOURCE WINDOW START >>>\n"
        end_marker = "<<< SOURCE WINDOW END >>>"
        return user_prompt.split(start_marker, 1)[1].split(end_marker, 1)[0]

    def _first_provider(_profile, _system_prompt, user_prompt, **kwargs):
        """
        @brief      Validate the first narrow-budget window and fail the next request.
        @param[in]  _profile Unused AI profile payload.
        @param[in]  _system_prompt Unused cleanup system prompt.
        @param[in]  user_prompt Rendered cleanup user prompt.
        @param[in]  kwargs Provider call metadata containing the expected window ID.
        @return     Provider-compatible keep-all cleanup response.
        @exception  RuntimeError Raised on the second request to create a partial checkpoint.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-16
        @version    0.1.0
        """
        nonlocal first_call_count
        first_call_count += 1
        if first_call_count == 2:
            raise RuntimeError("stop after first narrow-budget window")
        context = dict(kwargs.get("log_context", {}))
        return {
            "payload": _payload(
                str(context["window_id"]),
                [_block(1, _source_from_prompt(user_prompt), "story")],
            ),
            "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20, "usage_available": True},
        }

    narrow_profile = {**_MOCK_PROFILE, "max_output_tokens": 2000}
    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _first_provider)
    with pytest.raises(RuntimeError, match="narrow-budget window"):
        ai_cleanup_service.clean_text(project_root, manifest, narrow_profile)

    failed_document = json.loads(
        (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).read_text(encoding="utf-8")
    )
    assert failed_document["status"] == "failed"
    assert "progress_current" not in failed_document
    assert failed_document["decisions"]["items"][-1]["end"] == expected_restored_offset

    resumed_prompts: list[str] = []

    def _resumed_provider(_profile, _system_prompt, user_prompt, **kwargs):
        """
        @brief      Retain and capture each source window submitted after resume.
        @param[in]  _profile Unused AI profile payload.
        @param[in]  _system_prompt Unused cleanup system prompt.
        @param[in]  user_prompt Rendered cleanup user prompt.
        @param[in]  kwargs Provider call metadata containing the expected window ID.
        @return     Provider-compatible keep-all cleanup response.
        @exception  None.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-16
        @version    0.1.0
        """
        resumed_prompts.append(user_prompt)
        context = dict(kwargs.get("log_context", {}))
        return {
            "payload": _payload(
                str(context["window_id"]),
                [_block(1, _source_from_prompt(user_prompt), "story")],
            ),
            "usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10, "usage_available": True},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _resumed_provider)
    report = ai_cleanup_service.clean_text(
        project_root,
        manifest,
        {**_MOCK_PROFILE, "id": "profile-wide", "max_output_tokens": 4096},
    )

    assert len(resumed_prompts) == 1
    assert "Page 1 " not in resumed_prompts[0]
    assert "Page 2 " not in resumed_prompts[0]
    assert "Page 3 " in resumed_prompts[0]
    assert "Page 5 " in resumed_prompts[0]
    assert report["status"] == "completed"
    assert report["decisions"]["items"][-1]["end"] == len(expected_source_stream)
    assert report["token_usage"]["total_tokens"] == 30
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME
    assert cleaned_path.read_text(encoding="utf-8") == expected_source_stream.replace("\n\n\n\f", "\n\n\f")


def test_cleanup_modified_story_is_stored_only_as_output_text() -> None:
    """Verify modified Story text is the only duplicated source decision text."""
    item = {
        "start": 0,
        "end": len(_MODIFIED_STORY_SOURCE),
        "kind": "story",
        "output_text": _MODIFIED_STORY_AI,
    }

    assert ai_cleanup_service._validate_decision_items([item]) == len(_MODIFIED_STORY_SOURCE)
    assert set(item) == {"start", "end", "kind", "output_text"}

def test_cleanup_preserved_source_gap_stores_no_duplicated_text() -> None:
    """Verify preserved gaps retain only absolute offsets and their kind."""
    item = {"start": 0, "end": len(_OMITTED_SOURCE_LINE), "kind": "preserved_source_gap"}

    assert ai_cleanup_service._validate_decision_items([item]) == len(_OMITTED_SOURCE_LINE)
    assert set(item) == {"start", "end", "kind"}

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
    assert cleaned_path.read_text(encoding="utf-8") == ("First paragraph.\n\nSecond paragraph.\n")
    assert set(report) == {
        "status",
        "mode",
        "source_fingerprint",
        "instructions",
        "token_usage",
        "warnings",
        "decisions",
    }
    items = report["decisions"]["items"]
    assert [item["kind"] for item in items] == [
        "header",
        "whitespace",
        "story",
        "whitespace",
        "separator",
        "whitespace",
        "heading",
        "whitespace",
        "story",
        "whitespace",
    ]
    assert not (project_root / config.CLEANUP_STATE_FILE_NAME).exists()
    assert not (project_root / config.CLEANUP_REPORT_FILE_NAME).exists()


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
    @brief      Verify AICU-004, S-0001, and REQ-FUNC-058 retained whitespace-gap rendering.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-15
    @version    1.2.0
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

    assert validated["reconstructed_text"] == "First paragraph.\n\nSecond paragraph.\n"
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


def test_render_document_restores_whitespace_gaps_and_collapses_blank_runs() -> None:
    """
    @brief      Verify S-0001 whitespace-gap restoration and blank-run collapsing.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    1.0.0
    """
    source = "First paragraph.\n\nHEADER\n\nSecond paragraph.\n"
    items = [
        {"start": 0, "end": 16, "kind": "story"},
        {"start": 16, "end": 18, "kind": "whitespace"},
        {"start": 18, "end": 24, "kind": "header", "confidence": "high"},
        {"start": 24, "end": 26, "kind": "whitespace"},
        {"start": 26, "end": 43, "kind": "story"},
        {"start": 43, "end": 44, "kind": "whitespace"},
    ]

    rendered = ai_cleanup_service._render_document(
        source,
        items,
        {"heading", "separator"},
        require_complete=True,
    )

    assert rendered == "First paragraph.\n\nSecond paragraph.\n"


def test_render_document_unwraps_intra_paragraph_line_breaks() -> None:
    """
    @brief      Verify S-0001 hard-wrap unwrapping in rendered cleanup output.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-27
    @version    1.0.0
    """
    source = (
        "The zerglings got Birch when they overran the base. Once again, the evacuation\n"
        "dropships were late.\n"
        "\n"
        "It was mind-\n"
        "numbing work.\n"
        "\n"
        "\f\n"
        "\n"
        "Second page opens here.\n"
    )
    items = [{"start": 0, "end": len(source), "kind": "story"}]

    rendered = ai_cleanup_service._render_document(
        source,
        items,
        {"heading", "separator"},
        require_complete=True,
    )

    assert rendered == (
        "The zerglings got Birch when they overran the base. Once again, the evacuation dropships were late.\n"
        "\n"
        "It was mind-numbing work.\n"
        "\n"
        "\f\n"
        "\n"
        "Second page opens here.\n"
    )


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

    assert first_text == "Story.\n"
    assert cleaned_path.read_text(encoding="utf-8") == first_text
    assert first_report["decisions"]["selected_spacing_categories"] == ["header", "noise"]
    assert second_report["decisions"]["selected_spacing_categories"] == ["header", "noise"]
    empty_report = ai_cleanup_service.apply_spacing_selection(project_root, set())
    assert cleaned_path.read_text(encoding="utf-8") == "Story.\n"
    assert empty_report["decisions"]["selected_spacing_categories"] == []
    persisted_document = json.loads(
        (project_root / config.CLEANUP_DOCUMENT_FILE_NAME).read_text(encoding="utf-8")
    )
    assert persisted_document["decisions"]["selected_spacing_categories"] == []


def test_ai_cleanup_spacing_reapplication_preserves_anchored_modified_story(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify AICU-007 and REQ-FUNC-061 reapply spacing around accepted AI Story text.
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
    extracted_path.write_text(f"Header\n\n{_MODIFIED_STORY_SOURCE}\nFooter", encoding="utf-8")
    (mock_prompt_environment / "text_cleanup_user.txt").write_text(
        "Window: {window_id}\nLanguage: {source_language_hint}\nScript: {dominant_script_hint}\n"
        "{source_window_block}\nInstructions: {additional_cleanup_instructions}",
        encoding="utf-8",
    )
    provider_call_count = 0

    def _fake_chat_json(*_args, **_kwargs):
        """
        @brief      Return one uniquely bounded modified Story response.
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
                    _block(2, _MODIFIED_STORY_AI, "story"),
                    _block(3, "Footer", "footer"),
                ],
            ),
            "usage": {},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)
    report = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME

    assert cleaned_path.read_text(encoding="utf-8") == f"{_MODIFIED_STORY_AI_UNWRAPPED}\n"
    modified_items = [item for item in report["decisions"]["items"] if "output_text" in item]
    assert len(modified_items) == 1
    assert modified_items[0]["output_text"] == _MODIFIED_STORY_AI
    assert provider_call_count == 1

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: pytest.fail("Spacing reapplication must not call the provider."),
    )
    reapplied = ai_cleanup_service.apply_spacing_selection(project_root, {"header", "footer"})

    assert cleaned_path.read_text(encoding="utf-8") == f"{_MODIFIED_STORY_AI_UNWRAPPED}\n"
    assert any(item.get("output_text") == _MODIFIED_STORY_AI for item in reapplied["decisions"]["items"])
    assert provider_call_count == 1


def test_ai_cleanup_spacing_reapplication_preserves_internal_source_gap(
    mock_extracted_project,
    mock_prompt_environment,
    monkeypatch,
) -> None:
    """
    @brief      Verify AICU-008 and REQ-FUNC-061 retain omitted source through spacing changes.
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
    source = f"Opening story.\n\n{_OMITTED_SOURCE_LINE}\n\nPage 24\n\nClosing story."
    expected_gap = f"\n\n{_OMITTED_SOURCE_LINE}\n\n"
    extracted_path.write_text(source, encoding="utf-8")
    (mock_prompt_environment / "text_cleanup_user.txt").write_text(
        "Window: {window_id}\nLanguage: {source_language_hint}\nScript: {dominant_script_hint}\n"
        "{source_window_block}\nInstructions: {additional_cleanup_instructions}",
        encoding="utf-8",
    )
    provider_call_count = 0

    def _fake_chat_json(*_args, **_kwargs):
        """
        @brief      Return one response that omits a uniquely bounded internal source line.
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
                    _block(1, "Opening story.", "story"),
                    _block(2, "Page 24", "noise"),
                    _block(3, "Closing story.", "story"),
                ],
            ),
            "usage": {},
        }

    monkeypatch.setattr(ai_cleanup_service.llm_provider_service, "chat_json", _fake_chat_json)
    report = ai_cleanup_service.clean_text(project_root, manifest, _MOCK_PROFILE)
    cleaned_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CLEANED_TEXT_FILE_NAME

    assert cleaned_path.read_text(encoding="utf-8") == f"Opening story.{expected_gap}Closing story."
    assert sum(item["kind"] == "preserved_source_gap" for item in report["decisions"]["items"]) == 1
    assert any(detail["kind"] == "unclassified_source_gap_preserved" for detail in report["warnings"])
    assert provider_call_count == 1

    monkeypatch.setattr(
        ai_cleanup_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: pytest.fail("Spacing reapplication must not call the provider."),
    )
    reapplied = ai_cleanup_service.apply_spacing_selection(project_root, {"noise"})

    assert cleaned_path.read_text(encoding="utf-8") == f"Opening story.{expected_gap}Closing story."
    assert sum(item["kind"] == "preserved_source_gap" for item in reapplied["decisions"]["items"]) == 1
    assert provider_call_count == 1


# END OF FILE
