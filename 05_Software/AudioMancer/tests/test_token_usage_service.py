#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_token_usage_service.py
@brief Focused unit coverage for canonical token-usage payload helpers.
@details Verifies provider normalization, persistence coercion, aggregation,
         and ordered restoration of durable token-usage payloads.
"""

# IMPORTS

import json
import math

import pytest

from audiomancer.services import token_usage_service


@pytest.mark.parametrize(
    ("numeric_value", "expected_value"),
    [
        (0, 0),
        (1234, 1234),
        (1234.0, 1234),
        ("1234", 1234),
        (" 1234 ", 1234),
    ],
)
def test_coerce_token_usage_accepts_non_negative_integral_numeric_forms(
    numeric_value,
    expected_value,
) -> None:
    """Verify supported integer representations normalize to Python integers."""
    coerced = token_usage_service.coerce_token_usage(
        {
            "input_tokens": numeric_value,
            "output_tokens": numeric_value,
            "total_tokens": numeric_value,
            "usage_available": True,
        }
    )

    assert coerced == {
        "input_tokens": expected_value,
        "output_tokens": expected_value,
        "total_tokens": expected_value,
        "usage_available": True,
    }


@pytest.mark.parametrize(
    "invalid_value",
    [True, False, -1, -1.0, 1.25, math.nan, math.inf, -math.inf, "1.5", "-1", "tokens", ""],
)
def test_coerce_token_usage_rejects_invalid_numeric_forms(invalid_value) -> None:
    """Verify unsupported counter forms make the canonical payload unavailable."""
    assert token_usage_service.coerce_token_usage(
        {
            "input_tokens": invalid_value,
            "output_tokens": 2,
            "total_tokens": 2,
            "usage_available": True,
        }
    ) == token_usage_service.empty_token_usage()


def test_normalize_provider_usage_derives_absent_and_null_total() -> None:
    """Verify both omitted and explicit-null totals use input plus output."""
    for raw_usage in (
        {"prompt_tokens": 10.0, "completion_tokens": "4"},
        {"prompt_tokens": 10.0, "completion_tokens": "4", "total_tokens": None},
    ):
        assert token_usage_service.normalize_provider_usage({"usage": raw_usage}) == {
            "input_tokens": 10,
            "output_tokens": 4,
            "total_tokens": 14,
            "usage_available": True,
        }


def test_normalize_provider_usage_preserves_valid_reported_total() -> None:
    """Verify a valid provider total remains authoritative even when it differs from the sum."""
    assert token_usage_service.normalize_provider_usage(
        {
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 20.0,
            }
        }
    ) == {
        "input_tokens": 10,
        "output_tokens": 4,
        "total_tokens": 20,
        "usage_available": True,
    }


@pytest.mark.parametrize(
    "raw_usage",
    [
        {},
        {"prompt_tokens": 1},
        {"completion_tokens": 1},
        {"prompt_tokens": 1, "completion_tokens": None},
        {"prompt_tokens": None, "completion_tokens": 1},
        {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": "invalid"},
    ],
)
def test_normalize_provider_usage_keeps_unusable_counts_unavailable(raw_usage) -> None:
    """Verify missing required counters and malformed supplied totals are not invented."""
    assert token_usage_service.normalize_provider_usage(
        {"usage": raw_usage}
    ) == token_usage_service.empty_token_usage()


def test_token_usage_round_trip_and_merge_derive_missing_totals_consistently() -> None:
    """Verify coercion, restore, persistence, and merge share derived-total semantics."""
    persisted_without_total = {
        "input_tokens": "10",
        "output_tokens": 4.0,
        "total_tokens": None,
        "usage_available": True,
    }
    restored = token_usage_service.restore_token_usage(
        json.loads(json.dumps(persisted_without_total))
    )

    assert restored == {
        "input_tokens": 10,
        "output_tokens": 4,
        "total_tokens": 14,
        "usage_available": True,
    }
    assert token_usage_service.merge_token_usage(
        restored,
        {
            "input_tokens": 2,
            "output_tokens": 3,
            "total_tokens": None,
            "usage_available": True,
        },
    ) == {
        "input_tokens": 12,
        "output_tokens": 7,
        "total_tokens": 19,
        "usage_available": True,
    }


def test_merge_token_usage_sums_available_usage_and_tolerates_missing_base() -> None:
    """REQ-FUNC-024: combine available provider totals into one canonical payload."""
    merged = token_usage_service.merge_token_usage(
        {"usage_available": False},
        {"input_tokens": "120", "output_tokens": 5, "total_tokens": 125, "usage_available": True},
    )

    assert merged == {
        "input_tokens": 120,
        "output_tokens": 5,
        "total_tokens": 125,
        "usage_available": True,
    }


def test_restore_token_usage_selects_first_valid_persisted_payload() -> None:
    """REQ-FUNC-024: restore the ordered first valid persisted usage payload."""
    restored = token_usage_service.restore_token_usage(
        {"input_tokens": -1, "output_tokens": 3, "total_tokens": 2, "usage_available": True},
        {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30, "usage_available": True},
        {"input_tokens": 99, "output_tokens": 99, "total_tokens": 198, "usage_available": True},
    )

    assert restored == {
        "input_tokens": 10,
        "output_tokens": 20,
        "total_tokens": 30,
        "usage_available": True,
    }


# END OF FILE
