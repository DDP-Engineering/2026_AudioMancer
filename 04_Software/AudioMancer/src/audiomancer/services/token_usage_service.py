#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file token_usage_service.py
@brief Shared token-usage normalization helpers for AudioMancer AI workflows.
@details Normalizes backend-reported token usage, merges cumulative usage
         across multiple AI requests, and restores persisted usage payloads
         from step-local reports or operation-state metadata.
"""

# IMPORTS

import math
from typing import Any

TokenUsagePayload = dict[str, object]


def empty_token_usage() -> TokenUsagePayload:
    """
    @brief      Build the canonical empty token-usage payload.
    @return     Token-usage payload with unavailable counters.
    @exception  None
    """
    return {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "usage_available": False,
    }


def normalize_provider_usage(response_payload: dict[str, object]) -> TokenUsagePayload:
    """
    @brief      Normalize one OpenAI-compatible response `usage` object.
    @param[in]  response_payload Raw provider response payload.
    @return     Canonical token-usage payload.
    @exception  None
    """
    raw_usage = response_payload.get("usage")
    if not isinstance(raw_usage, dict):
        return empty_token_usage()
    normalized_values = _normalize_usage_values(
        raw_usage,
        input_field="prompt_tokens",
        output_field="completion_tokens",
        total_field="total_tokens",
    )
    if normalized_values is None:
        return empty_token_usage()
    input_tokens, output_tokens, total_tokens = normalized_values
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "usage_available": True,
    }


def coerce_token_usage(payload: object) -> TokenUsagePayload:
    """
    @brief      Restore one persisted token-usage payload into canonical shape.
    @param[in]  payload Candidate persisted token-usage payload.
    @return     Canonical token-usage payload.
    @exception  None
    """
    if not isinstance(payload, dict):
        return empty_token_usage()
    usage_available = bool(payload.get("usage_available", False))
    if not usage_available:
        return empty_token_usage()
    normalized_values = _normalize_usage_values(
        payload,
        input_field="input_tokens",
        output_field="output_tokens",
        total_field="total_tokens",
    )
    if normalized_values is None:
        return empty_token_usage()
    input_tokens, output_tokens, total_tokens = normalized_values
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "usage_available": True,
    }


def merge_token_usage(
    base_usage: object,
    increment_usage: object,
) -> TokenUsagePayload:
    """
    @brief      Sum two canonical or persisted token-usage payloads.
    @param[in]  base_usage Existing cumulative token-usage payload.
    @param[in]  increment_usage Additional token-usage payload to add.
    @return     Summed token-usage payload or one canonical unavailable payload.
    @exception  None
    """
    normalized_base = coerce_token_usage(base_usage)
    normalized_increment = coerce_token_usage(increment_usage)
    if not bool(normalized_base["usage_available"]) and not bool(normalized_increment["usage_available"]):
        return empty_token_usage()
    return {
        "input_tokens": _sum_usage_field(
            normalized_base,
            normalized_increment,
            "input_tokens",
        ),
        "output_tokens": _sum_usage_field(
            normalized_base,
            normalized_increment,
            "output_tokens",
        ),
        "total_tokens": _sum_usage_field(
            normalized_base,
            normalized_increment,
            "total_tokens",
        ),
        "usage_available": True,
    }


def restore_token_usage(*payloads: object) -> TokenUsagePayload:
    """
    @brief      Return the first valid persisted token-usage payload from candidates.
    @param[in]  payloads Ordered candidate token-usage payloads.
    @return     First valid token-usage payload or one unavailable payload.
    @exception  None
    """
    for payload in payloads:
        normalized = coerce_token_usage(payload)
        if bool(normalized["usage_available"]):
            return normalized
    return empty_token_usage()


def _sum_usage_field(
    base_usage: TokenUsagePayload,
    increment_usage: TokenUsagePayload,
    field_name: str,
) -> int | None:
    """
    @brief      Execute the sum usage field helper.
    @param[in]  base_usage Value for `base_usage`.
    @param[in]  increment_usage Value for `increment_usage`.
    @param[in]  field_name Value for `field_name`.
    @return     Helper result.
    """
    total = 0
    has_value = False
    for payload in (base_usage, increment_usage):
        if not bool(payload.get("usage_available", False)):
            continue
        field_value = payload.get(field_name)
        if not isinstance(field_value, int):
            continue
        total += field_value
        has_value = True
    return total if has_value else None


def _normalize_usage_values(
    payload: dict[object, object],
    input_field: str,
    output_field: str,
    total_field: str,
) -> tuple[int, int, int] | None:
    """
    @brief      Normalize one complete usage triplet and derive an absent total.
    @param[in]  payload Usage object containing provider or canonical field names.
    @param[in]  input_field Field that owns the input-token count.
    @param[in]  output_field Field that owns the output-token count.
    @param[in]  total_field Field that owns the optional total-token count.
    @return     Normalized counts, or None when required values are invalid.
    @exception  None
    """
    input_tokens = _optional_non_negative_int(payload.get(input_field))
    output_tokens = _optional_non_negative_int(payload.get(output_field))
    if input_tokens is None or output_tokens is None:
        return None
    raw_total = payload.get(total_field)
    total_tokens = _optional_non_negative_int(raw_total)
    if total_tokens is None:
        if raw_total is not None:
            return None
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


def _optional_non_negative_int(value: Any) -> int | None:
    """
    @brief      Resolve the optional non negative int.
    @param[in]  value Candidate value.
    @return     Helper result.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if math.isfinite(value) and value >= 0 and value.is_integer():
            return int(value)
        return None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


# END OF FILE
