#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file prompt_template_service.py
@brief Prompt-template helpers for AudioMancer.
@details Loads UTF-8 prompt text files from the application-owned prompt folder
         and renders them through strict named placeholder substitution.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.1.0
"""

# IMPORTS

import re
from pathlib import Path

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function

# CONSTANTS

_PROMPT_LOGGER = get_component_logger("prompt_template")
_PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


# PUBLIC API


@trace_function(_PROMPT_LOGGER)
def load_prompt(
    prompt_name: str,
    prompt_root: str | Path | None = None,
) -> str:
    """
    @brief      Load one prompt template from the application prompt folder.
    @param[in]  prompt_name Prompt file identifier without the `.txt` suffix.
    @param[in]  prompt_root Optional filesystem override used by tests.
    @return     Loaded prompt text.
    @exception  FileNotFoundError Raised when the prompt file is missing.
    @exception  ValueError Raised when the prompt file is empty.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    prompt_path = _resolve_prompt_path(prompt_name, prompt_root)
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt file is missing: {prompt_path}")
    prompt_text = prompt_path.read_text(encoding="utf-8")
    if not prompt_text.strip():
        raise ValueError(f"Prompt file is empty: {prompt_path}")
    return prompt_text


@trace_function(_PROMPT_LOGGER)
def render_prompt(
    prompt_name: str,
    variables: dict[str, object],
    prompt_root: str | Path | None = None,
) -> str:
    """
    @brief      Render one prompt template through strict placeholder substitution.
    @param[in]  prompt_name Prompt file identifier without the `.txt` suffix.
    @param[in]  variables Named placeholder values used for substitution.
    @param[in]  prompt_root Optional filesystem override used by tests.
    @return     Fully rendered prompt text.
    @exception  ValueError Raised on missing or extra placeholders.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    template = load_prompt(prompt_name, prompt_root)
    placeholders = set(_PLACEHOLDER_PATTERN.findall(template))
    provided_variables = set(variables.keys())
    missing_variables = sorted(placeholders - provided_variables)
    extra_variables = sorted(provided_variables - placeholders)
    if missing_variables:
        raise ValueError(
            f"Prompt '{prompt_name}' is missing values for placeholders: {', '.join(missing_variables)}"
        )
    if extra_variables:
        raise ValueError(
            f"Prompt '{prompt_name}' received unexpected placeholders: {', '.join(extra_variables)}"
        )

    rendered = template
    for placeholder_name in sorted(placeholders):
        rendered = rendered.replace(
            f"{{{placeholder_name}}}",
            str(variables[placeholder_name]),
        )

    unresolved = sorted(set(_PLACEHOLDER_PATTERN.findall(rendered)))
    if unresolved:
        raise ValueError(
            f"Prompt '{prompt_name}' still contains unresolved placeholders: {', '.join(unresolved)}"
        )
    if not rendered.strip():
        raise ValueError(f"Rendered prompt is empty: {prompt_name}")
    return rendered


@trace_function(_PROMPT_LOGGER)
def validate_required_prompts(
    prompt_names: list[str],
    prompt_root: str | Path | None = None,
) -> None:
    """
    @brief      Validate that all listed prompt files can be loaded successfully.
    @param[in]  prompt_names Prompt identifiers without the `.txt` suffix.
    @param[in]  prompt_root Optional filesystem override used by tests.
    @return     None.
    @exception  FileNotFoundError Raised when one prompt file is missing.
    @exception  ValueError Raised when one prompt file is empty.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    for prompt_name in prompt_names:
        load_prompt(prompt_name, prompt_root)


# LOCAL HELPERS


def _resolve_prompt_path(prompt_name: str, prompt_root: str | Path | None) -> Path:
    prompt_directory = config.APP_PROMPTS_PATH if prompt_root is None else Path(prompt_root)
    return prompt_directory / f"{prompt_name}.txt"


# END OF FILE
