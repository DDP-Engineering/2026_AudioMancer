"""Focused unit coverage for canonical token-usage payload helpers."""

from audiomancer.services import token_usage_service


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
