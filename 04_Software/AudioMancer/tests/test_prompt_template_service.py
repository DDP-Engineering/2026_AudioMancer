#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_prompt_template_service.py
@brief Focused tests for the AudioMancer prompt-template service.
@details Verifies prompt loading and strict placeholder rendering for the new
         AI-assisted cleanup prompt files.
"""

# IMPORTS

import pytest

from audiomancer.services import prompt_template_service


def test_render_prompt_requires_exact_placeholders(tmp_path) -> None:
    """
    @brief      Verify prompt rendering rejects missing and extra placeholders.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "sample.txt").write_text("Hello {name}", encoding="utf-8")

    assert (
        prompt_template_service.render_prompt(
            "sample",
            {"name": "AudioMancer"},
            prompt_root=prompt_root,
        )
        == "Hello AudioMancer"
    )
    with pytest.raises(ValueError):
        prompt_template_service.render_prompt("sample", {}, prompt_root=prompt_root)
    with pytest.raises(ValueError):
        prompt_template_service.render_prompt(
            "sample",
            {"name": "AudioMancer", "extra": "value"},
            prompt_root=prompt_root,
        )


def test_render_prompt_allows_braced_source_text_values(tmp_path) -> None:
    """
    @brief      Verify inserted source text with braces is not treated as a template placeholder.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "cleanup.txt").write_text("Clean this:\n{text}", encoding="utf-8")

    rendered = prompt_template_service.render_prompt(
        "cleanup",
        {"text": "Chapter index markers: {ix}, {x}, {xi}."},
        prompt_root=prompt_root,
    )

    assert rendered == "Clean this:\nChapter index markers: {ix}, {x}, {xi}."


# END OF FILE
