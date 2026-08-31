#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_book_analysis_budget_service.py
@brief Verify conservative model-agnostic Book Analysis request budgets.
@details Covers the minimum context, local and online input fractions, prompt,
         output/reasoning and safety reserves, exact-fit text, and the single
         smaller retry budget without contacting an AI provider.
"""

# IMPORTS

from importlib import import_module

import pytest

# LOCAL HELPERS


def _service():
    """Return the Book Analysis budget service or fail as missing behavior."""
    try:
        return import_module("audiomancer.services.book_analysis_budget_service")
    except ModuleNotFoundError:
        pytest.fail("Book Analysis budget service is not implemented.")


def _profile(
    backend_kind: str,
    *,
    context_window: int = 16_384,
    output_reserve_tokens: int = 8_192,
    reasoning_mode: str = "provider_default",
) -> dict[str, object]:
    """Build one normalized test profile without credentials."""
    return {
        "backend_kind": backend_kind,
        "context_window": context_window,
        "output_reserve_tokens": output_reserve_tokens,
        "reasoning_mode": reasoning_mode,
    }


# TESTS


def test_build_request_budget_accepts_exact_16k_local_context() -> None:
    """Exact 16K local profiles retain a useful whole-chunk input budget."""
    budget = _service().build_request_budget(
        _profile("lmstudio", reasoning_mode="disabled"),
        "system and user shell",
    )

    assert budget["context_window"] == 16_384
    assert 512 <= budget["source_budget_tokens"] <= 8_192


@pytest.mark.parametrize(
    ("backend_kind", "maximum"),
    (("lmstudio", 8_192), ("ollama", 8_192), ("openai_compatible", 4_915)),
)
def test_build_request_budget_applies_backend_fraction(
    backend_kind: str,
    maximum: int,
) -> None:
    """Local profiles use at most 50 percent and online profiles 30 percent."""
    budget = _service().build_request_budget(
        _profile(backend_kind),
        "prompt",
    )

    assert budget["source_budget_tokens"] <= maximum


def test_build_request_budget_rejects_context_below_16k() -> None:
    """A declared context below 16,384 tokens is not accepted."""
    with pytest.raises(ValueError, match="at least 16,384"):
        _service().build_request_budget(
            _profile("lmstudio", context_window=16_383),
            "prompt",
        )


def test_prompt_and_reasoning_reserves_reduce_fraction_capacity() -> None:
    """Post-reserve capacity wins when it is smaller than the local fraction."""
    service = _service()
    disabled = service.build_request_budget(
        _profile("lmstudio", reasoning_mode="disabled"),
        "x" * 17_000,
    )
    enabled = service.build_request_budget(
        _profile("lmstudio", reasoning_mode="enabled"),
        "x" * 17_000,
    )

    assert disabled["source_budget_tokens"] < 8_192
    assert enabled["source_budget_tokens"] < disabled["source_budget_tokens"]
    assert enabled["reasoning_reserve_tokens"] > 0


def test_source_text_fits_exact_budget() -> None:
    """An estimated source exactly equal to the available budget is accepted."""
    service = _service()

    assert service.source_text_fits("x" * 2_048, 512) is True
    assert service.source_text_fits("x" * 2_052, 512) is False


def test_reduced_source_budget_uses_one_75_percent_retry() -> None:
    """The overflow retry budget is exactly 75 percent of the first budget."""
    assert _service().reduced_source_budget(8_000) == 6_000


# END OF FILE
