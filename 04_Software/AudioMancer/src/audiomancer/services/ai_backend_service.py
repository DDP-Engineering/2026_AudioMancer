#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ai_backend_service.py
@brief Backend connectivity helpers for AudioMancer AI profiles.
@details Probes configured AI backends, normalizes discovered models behind one
         internal contract, and returns operator-facing connect feedback for
         the AI Settings page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.2.0
"""

# IMPORTS

import json
from typing import Any
from urllib import error, parse, request

from .. import config
from .logging_service import get_component_logger, trace_function

# CONSTANTS

# @brief Component logger used by the AI backend probe helpers.
_AI_BACKEND_LOGGER = get_component_logger("ai_backend")

# @brief Normalized discovered-model payload type used by backend probes.
ModelDescriptorPayload = dict[str, str]

# @brief Normalized provider-probe result payload type returned to the UI layer.
ProviderProbeResultPayload = dict[str, object]


def _ensure_trailing_endpoint(base_url: str, endpoint: str) -> str:
    """
    @brief      Append one endpoint path to a base URL safely.
    @param[in]  base_url Operator-configured backend base URL.
    @param[in]  endpoint Relative endpoint path beginning with `/`.
    @return     Fully joined URL string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    normalized_base = (base_url or "").rstrip("/")
    return f"{normalized_base}{endpoint}"


def _resolve_ollama_tags_url(base_url: str) -> str:
    """
    @brief      Resolve the Ollama model-tags endpoint from a base URL.
    @param[in]  base_url Operator-configured backend base URL.
    @return     Fully qualified Ollama tags URL.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    parsed_url = parse.urlparse(base_url)
    normalized_path = parsed_url.path.rstrip("/")
    if normalized_path.endswith("/v1"):
        normalized_path = normalized_path[:-3]
    rebuilt_url = parsed_url._replace(path=normalized_path)
    return _ensure_trailing_endpoint(parse.urlunparse(rebuilt_url), "/api/tags")


def _build_request_headers(profile_payload: dict[str, object]) -> dict[str, str]:
    """
    @brief      Build HTTP request headers for one profile probe.
    @param[in]  profile_payload Normalized profile payload.
    @return     HTTP header map.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    headers = {"Accept": "application/json"}
    api_key = str(profile_payload.get("api_key", "")).strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


@trace_function(_AI_BACKEND_LOGGER)
def probe_profile(profile_payload: dict[str, object]) -> ProviderProbeResultPayload:
    """
    @brief      Probe one configured AI backend profile and discover models.
    @param[in]  profile_payload Normalized AI profile payload.
    @return     Normalized probe result payload with discovered models and feedback.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.1
    """
    backend_kind = str(profile_payload.get("backend_kind", "")).strip()
    base_url = str(profile_payload.get("base_url", "")).strip()
    selected_model_name = str(profile_payload.get("model_name", "")).strip()
    timeout_seconds = config.DEFAULT_AI_CONNECT_TIMEOUT_SECONDS

    if backend_kind not in config.LLM_BACKEND_OPTIONS:
        return _build_probe_result(
            success=False,
            message=f"Unsupported backend kind: {backend_kind or '<empty>'}.",
            discovered_models=[],
            discovered_context_window=None,
            selected_model_valid=False,
        )
    if not base_url:
        return _build_probe_result(
            success=False,
            message="Base URL is empty.",
            discovered_models=[],
            discovered_context_window=None,
            selected_model_valid=False,
        )

    try:
        if backend_kind == "ollama":
            discovered_models = _probe_ollama_models(
                profile_payload,
                timeout_seconds,
            )
        else:
            discovered_models = _probe_openai_compatible_models(
                profile_payload,
                timeout_seconds,
            )
    except error.HTTPError as exception:
        return _build_probe_result(
            success=False,
            message=f"Connection failed: HTTP {exception.code}.",
            discovered_models=[],
            discovered_context_window=None,
            selected_model_valid=False,
        )
    except error.URLError as exception:
        reason = getattr(exception, "reason", exception)
        return _build_probe_result(
            success=False,
            message=f"Connection failed: {reason}.",
            discovered_models=[],
            discovered_context_window=None,
            selected_model_valid=False,
        )
    except TimeoutError:
        return _build_probe_result(
            success=False,
            message="Connection failed: request timed out.",
            discovered_models=[],
            discovered_context_window=None,
            selected_model_valid=False,
        )
    except ValueError as exception:
        return _build_probe_result(
            success=False,
            message=f"Connection failed: {exception}.",
            discovered_models=[],
            discovered_context_window=None,
            selected_model_valid=False,
        )

    discovered_model_ids = {model["id"] for model in discovered_models}
    selected_model_valid = bool(selected_model_name) and selected_model_name in discovered_model_ids
    message = f"Connection successful. Discovered {len(discovered_models)} models."
    return _build_probe_result(
        success=True,
        message=message,
        discovered_models=discovered_models,
        discovered_context_window=None,
        selected_model_valid=selected_model_valid,
    )


def _probe_openai_compatible_models(
    profile_payload: dict[str, object],
    timeout_seconds: int,
) -> list[ModelDescriptorPayload]:
    """
    @brief      Discover models from an OpenAI-compatible backend.
    @param[in]  profile_payload Normalized AI profile payload.
    @param[in]  timeout_seconds HTTP request timeout.
    @return     Discovered model descriptors.
    @exception  ValueError When the response payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    models_url = _ensure_trailing_endpoint(
        str(profile_payload.get("base_url", "")),
        "/models",
    )
    payload = _read_json(
        models_url,
        _build_request_headers(profile_payload),
        timeout_seconds,
    )
    model_entries = payload.get("data")
    if not isinstance(model_entries, list):
        raise ValueError("backend returned an invalid models payload")
    discovered_models: list[ModelDescriptorPayload] = []
    for model_entry in model_entries:
        if not isinstance(model_entry, dict):
            continue
        model_id = str(model_entry.get("id", "")).strip()
        if not model_id:
            continue
        discovered_models.append({"id": model_id, "label": model_id})
    return discovered_models


def _probe_ollama_models(
    profile_payload: dict[str, object],
    timeout_seconds: int,
) -> list[ModelDescriptorPayload]:
    """
    @brief      Discover models from an Ollama backend.
    @param[in]  profile_payload Normalized AI profile payload.
    @param[in]  timeout_seconds HTTP request timeout.
    @return     Discovered model descriptors.
    @exception  ValueError When the response payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    payload = _read_json(
        _resolve_ollama_tags_url(str(profile_payload.get("base_url", ""))),
        _build_request_headers(profile_payload),
        timeout_seconds,
    )
    model_entries = payload.get("models")
    if not isinstance(model_entries, list):
        raise ValueError("backend returned an invalid models payload")
    discovered_models: list[ModelDescriptorPayload] = []
    for model_entry in model_entries:
        if not isinstance(model_entry, dict):
            continue
        model_id = str(model_entry.get("name") or model_entry.get("model") or "").strip()
        if not model_id:
            continue
        discovered_models.append({"id": model_id, "label": model_id})
    return discovered_models


def _read_json(
    url: str,
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    """
    @brief      Execute one JSON GET request and decode the response.
    @param[in]  url Fully qualified target URL.
    @param[in]  headers HTTP header mapping.
    @param[in]  timeout_seconds HTTP request timeout.
    @return     Decoded JSON object payload.
    @exception  ValueError When decoding fails or the payload root is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    http_request = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("backend returned a non-object JSON payload")
    return payload


def _build_probe_result(
    success: bool,
    message: str,
    discovered_models: list[ModelDescriptorPayload],
    discovered_context_window: int | None,
    selected_model_valid: bool,
) -> ProviderProbeResultPayload:
    """
    @brief      Build one normalized provider probe result payload.
    @param[in]  success True when the backend probe succeeded.
    @param[in]  message Operator-facing probe message.
    @param[in]  discovered_models Normalized discovered model payloads.
    @param[in]  discovered_context_window Optional discovered context window.
    @param[in]  selected_model_valid True when the chosen model is valid.
    @return     Normalized probe result dictionary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return {
        "success": success,
        "message": message,
        "discovered_models": list(discovered_models),
        "discovered_model_count": len(discovered_models),
        "discovered_context_window": discovered_context_window,
        "selected_model_valid": selected_model_valid,
    }


# END OF FILE
