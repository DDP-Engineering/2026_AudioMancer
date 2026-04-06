#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
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


# END OF FILE
