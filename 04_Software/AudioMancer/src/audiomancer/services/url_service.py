#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file url_service.py
@brief Shared URL normalization helpers for AudioMancer service clients.
@details Joins configured HTTP base URLs and REST endpoint paths without
         duplicating trailing-slash and version-prefix handling.
"""

# IMPORTS

from urllib import parse

# PUBLIC API


def join_endpoint_url(
    base_url: str,
    endpoint: str,
    *,
    collapse_duplicate_version: bool = False,
) -> str:
    """
    @brief      Join one REST endpoint path to one configured base URL.
    @param[in]  base_url Operator-configured absolute base URL.
    @param[in]  endpoint Endpoint path to append.
    @param[in]  collapse_duplicate_version True to avoid `/v1/v1/...` joins.
    @return     Fully joined URL string.
    @exception  None
    """
    parsed_url = parse.urlparse(str(base_url or "").strip())
    normalized_path = parsed_url.path.rstrip("/")
    endpoint_path = _normalized_endpoint_path(endpoint)
    if normalized_path.endswith(endpoint_path):
        resolved_path = normalized_path
    elif collapse_duplicate_version and normalized_path.endswith("/v1") and endpoint_path.startswith("/v1/"):
        resolved_path = f"{normalized_path}{endpoint_path[3:]}"
    else:
        resolved_path = f"{normalized_path}{endpoint_path}" if normalized_path else endpoint_path
    return parse.urlunparse(parsed_url._replace(path=resolved_path))


def remove_trailing_endpoint(base_url: str, endpoint: str) -> str:
    """
    @brief      Remove one trailing endpoint path from a base URL when it is present.
    @param[in]  base_url Operator-configured absolute base URL.
    @param[in]  endpoint Endpoint suffix to remove.
    @return     URL string with the trailing endpoint path removed.
    @exception  None
    """
    parsed_url = parse.urlparse(str(base_url or "").strip())
    normalized_path = parsed_url.path.rstrip("/")
    endpoint_path = _normalized_endpoint_path(endpoint)
    if normalized_path.endswith(endpoint_path):
        normalized_path = normalized_path[: -len(endpoint_path)]
    return parse.urlunparse(parsed_url._replace(path=normalized_path))


def _normalized_endpoint_path(endpoint: str) -> str:
    """
    @brief      Normalize one endpoint token to an absolute path without a trailing slash.
    @param[in]  endpoint Candidate endpoint path.
    @return     Normalized endpoint path.
    @exception  None
    """
    endpoint_path = str(endpoint or "").strip().rstrip("/")
    if not endpoint_path.startswith("/"):
        endpoint_path = f"/{endpoint_path}"
    return endpoint_path


# END OF FILE
