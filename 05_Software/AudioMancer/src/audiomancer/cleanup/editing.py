#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file editing.py
@brief Conservative paragraph metadata matching for operator edits.
@details Carries metadata only across unique matches; lexical edits require exact text.
"""

# IMPORTS

from . import text as cleanup_text_analysis_service

# PUBLIC API


def realign_paragraph_roles(
    previous_records: list[dict[str, object]],
    current_records: list[dict[str, object]],
    *,
    exact: bool = False,
) -> None:
    """
    @brief      Carry prior Cleanup metadata across unambiguous content matches.
    @param[in]  previous_records Prior runtime paragraph records with text.
    @param[out] current_records Rebuilt runtime records receiving safe metadata.
    @return     None.
    @exception  None
    """
    key = str if exact else cleanup_text_analysis_service.normalized_compare_key
    marker = "user_exact_paragraph_match" if exact else "user_whitespace_realign"
    previous_by_text: dict[str, list[dict[str, object]]] = {}
    for record in previous_records:
        comparison_key = key(str(record.get("text") or ""))
        if comparison_key:
            previous_by_text.setdefault(comparison_key, []).append(record)

    current_by_text: dict[str, list[dict[str, object]]] = {}
    for record in current_records:
        comparison_key = key(str(record.get("text") or ""))
        if comparison_key:
            current_by_text.setdefault(comparison_key, []).append(record)

    for record in current_records:
        classified_role = str(record.get("role") or "body")
        record["role"] = classified_role
        if not exact:
            record["reason_codes"] = _reason_codes_with_whitespace_realign(record.get("reason_codes"), marker)
        comparison_key = key(str(record.get("text") or ""))
        prior_matches = previous_by_text.get(comparison_key, [])
        current_matches = current_by_text.get(comparison_key, [])
        if len(prior_matches) != 1 or len(current_matches) != 1:
            continue

        prior = prior_matches[0]
        prior_role = str(prior.get("role") or "body")
        if classified_role != "scene_separator" and prior_role != "scene_separator":
            record["role"] = prior_role
        record["confidence"] = str(prior.get("confidence") or "strong")
        record["reason_codes"] = _reason_codes_with_whitespace_realign(prior.get("reason_codes"), marker)

        raw_source_ids = prior.get("source_unit_ids")
        source_ids = (
            list(dict.fromkeys(str(unit_id) for unit_id in raw_source_ids if str(unit_id)))
            if isinstance(raw_source_ids, list)
            else []
        )
        if prior.get("provenance_available") is not True or not source_ids:
            continue
        record["source_unit_ids"] = source_ids
        record["provenance_available"] = True
        record["source_page_start"] = prior.get("source_page_start")
        record["source_page_end"] = prior.get("source_page_end")
        record["starts_after_page_transition"] = bool(prior.get("starts_after_page_transition", False))
        record["crosses_page_transition"] = bool(prior.get("crosses_page_transition", False))


def _reason_codes_with_whitespace_realign(value: object, marker: str) -> list[str]:
    """@brief Return ordered unique reason codes with the realignment marker."""
    existing = [str(item) for item in value] if isinstance(value, list) else []
    return list(dict.fromkeys([*existing, marker]))


# END OF FILE
