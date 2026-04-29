#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_url_service.py
@brief Focused tests for shared URL helpers.
@details Verifies endpoint joining behavior shared by HTTP runtime services.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.1.0
"""

# IMPORTS

from audiomancer.services.url_service import join_endpoint_url, remove_trailing_endpoint


def test_join_endpoint_url_appends_missing_endpoint_once() -> None:
    """
    @brief      Verify endpoint joins handle missing and already-present suffixes.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    assert join_endpoint_url("http://localhost:11434/v1", "/models") == "http://localhost:11434/v1/models"
    assert join_endpoint_url("http://localhost:11434/v1/models", "/models") == "http://localhost:11434/v1/models"


def test_join_endpoint_url_collapses_duplicate_version_prefix() -> None:
    """
    @brief      Verify VoiceWeaver-style versioned endpoints avoid duplicated `/v1` segments.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    assert (
        join_endpoint_url("http://localhost:9000/v1", "/v1/health", collapse_duplicate_version=True)
        == "http://localhost:9000/v1/health"
    )


def test_remove_trailing_endpoint_strips_present_suffix_only() -> None:
    """
    @brief      Verify URL suffix removal leaves unrelated paths intact.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    assert remove_trailing_endpoint("http://localhost:11434/v1", "/v1") == "http://localhost:11434"
    assert remove_trailing_endpoint("http://localhost:11434/api/tags", "/v1") == "http://localhost:11434/api/tags"


# END OF FILE
