#!/usr/bin/env python3
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
@author Eng. Dan Dumitru Pasare
@date 2026-04-11
@version 0.1.0
"""

# IMPORTS

from typing import Any

TokenUsagePayload = dict[str, object]


def empty_token_usage() -> TokenUsagePayload:
    """
    @brief      Build the canonical empty token-usage payload.
    @return     Token-usage payload with unavailable counters.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    raw_usage = response_payload.get("usage")
    if not isinstance(raw_usage, dict):
        return empty_token_usage()
    input_tokens = _optional_non_negative_int(raw_usage.get("prompt_tokens"))
    output_tokens = _optional_non_negative_int(raw_usage.get("completion_tokens"))
    total_tokens = _optional_non_negative_int(raw_usage.get("total_tokens"))
    if None in {input_tokens, output_tokens, total_tokens}:
        return empty_token_usage()
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    if not isinstance(payload, dict):
        return empty_token_usage()
    usage_available = bool(payload.get("usage_available", False))
    if not usage_available:
        return empty_token_usage()
    input_tokens = _optional_non_negative_int(payload.get("input_tokens"))
    output_tokens = _optional_non_negative_int(payload.get("output_tokens"))
    total_tokens = _optional_non_negative_int(payload.get("total_tokens"))
    if None in {input_tokens, output_tokens, total_tokens}:
        return empty_token_usage()
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
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


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


# END OF FILE
