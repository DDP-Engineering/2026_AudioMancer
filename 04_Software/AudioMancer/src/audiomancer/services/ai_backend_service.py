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
"""

# IMPORTS

from http import client
import json
from typing import Any
from urllib import error, parse, request

from .. import config
from .logging_service import get_component_logger, trace_function
from .url_service import join_endpoint_url, remove_trailing_endpoint

# CONSTANTS

# @brief Component logger used by the AI backend probe helpers.
_AI_BACKEND_LOGGER = get_component_logger("ai_backend")

# @brief Largest context value representable by the AI Settings editor.
_MAX_DISCOVERED_CONTEXT_WINDOW = 1_000_000

# @brief Normalized discovered-model payload type used by backend probes.
ModelDescriptorPayload = dict[str, object]

# @brief Normalized provider-probe result payload type returned to the UI layer.
ProviderProbeResultPayload = dict[str, object]


def _resolve_ollama_tags_url(base_url: str) -> str:
    """
    @brief      Resolve the Ollama model-tags endpoint from a base URL.
    @param[in]  base_url Operator-configured backend base URL.
    @return     Fully qualified Ollama tags URL.
    @exception  None
    """
    return join_endpoint_url(remove_trailing_endpoint(base_url, "/v1"), "/api/tags")


def _resolve_ollama_show_url(base_url: str) -> str:
    """
    @brief      Resolve the Ollama model-details endpoint from a base URL.
    @param[in]  base_url Operator-configured backend base URL.
    @return     Fully qualified Ollama show URL.
    @exception  None
    """
    return join_endpoint_url(remove_trailing_endpoint(base_url, "/v1"), "/api/show")


def _resolve_lm_studio_models_url(base_url: str) -> str:
    """
    @brief      Resolve the LM Studio native model-metadata endpoint.
    @param[in]  base_url Operator-configured backend base URL.
    @return     Fully qualified LM Studio native models URL.
    @exception  None
    """
    return join_endpoint_url(remove_trailing_endpoint(base_url, "/v1"), "/api/v1/models")


def _build_request_headers(profile_payload: dict[str, object]) -> dict[str, str]:
    """
    @brief      Build HTTP request headers for one profile probe.
    @param[in]  profile_payload Normalized profile payload.
    @return     HTTP header map.
    @exception  None
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
    """
    backend_kind = str(profile_payload.get("backend_kind", "")).strip()
    base_url = str(profile_payload.get("base_url", "")).strip()
    selected_model_name = str(profile_payload.get("model_name", "")).strip()
    timeout_seconds = config.DEFAULT_AI_CONNECT_TIMEOUT_SECONDS

    if backend_kind not in config.LLM_BACKEND_OPTIONS:
        return _build_probe_failure(f"Unsupported backend kind: {backend_kind or '<empty>'}.")
    if not base_url:
        return _build_probe_failure("Base URL is empty.")
    parsed_url = parse.urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return _build_probe_failure("Base URL is invalid.")

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
        return _build_probe_failure(f"Connection failed: HTTP {exception.code}.")
    except TimeoutError:
        return _build_probe_failure("Connection failed: request timed out.")
    except OSError:
        return _build_probe_failure("Connection failed: transport error.")
    except client.HTTPException:
        return _build_probe_failure("Connection failed: incomplete or invalid HTTP response.")
    except (UnicodeError, ValueError):
        return _build_probe_failure("Connection failed: invalid response data.")

    discovered_model_ids = {model["id"] for model in discovered_models}
    selected_model_valid = bool(selected_model_name) and selected_model_name in discovered_model_ids
    effective_model_name = _effective_model_name(
        selected_model_name,
        discovered_models,
        bool(profile_payload.get("user_overrode_model_name", False)),
    )
    discovered_context_window = _descriptor_context_window(
        discovered_models,
        effective_model_name,
    )
    if backend_kind == "lmstudio" and effective_model_name:
        native_context_window = _optional_lm_studio_context_window(
            profile_payload,
            timeout_seconds,
            effective_model_name,
        )
        if native_context_window is not None:
            discovered_context_window = native_context_window
    elif backend_kind == "ollama" and effective_model_name:
        ollama_context_window = _optional_ollama_context_window(
            profile_payload,
            timeout_seconds,
            effective_model_name,
        )
        if ollama_context_window is not None:
            discovered_context_window = ollama_context_window

    message = f"Connection successful. Discovered {len(discovered_models)} models."
    return _build_probe_result(
        success=True,
        message=message,
        discovered_models=discovered_models,
        discovered_context_window=discovered_context_window,
        discovered_context_model_name=(
            effective_model_name if discovered_context_window is not None else None
        ),
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
    """
    models_url = join_endpoint_url(
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
        model_descriptor: ModelDescriptorPayload = {"id": model_id, "label": model_id}
        context_window = _normalize_context_window(model_entry.get("context_length"))
        if context_window is None:
            context_window = _normalize_context_window(model_entry.get("max_context_length"))
        if context_window is not None:
            model_descriptor["context_window"] = context_window
        discovered_models.append(model_descriptor)
    return discovered_models


def _effective_model_name(
    selected_model_name: str,
    discovered_models: list[ModelDescriptorPayload],
    user_overrode_model_name: bool,
) -> str:
    """
    @brief      Resolve the model that the UI will keep or select after probing.
    @param[in]  selected_model_name Configured model identifier.
    @param[in]  discovered_models Normalized provider model descriptors.
    @param[in]  user_overrode_model_name Whether the configured name is operator-owned.
    @return     Exact effective model identifier or an empty string.
    @exception  None
    """
    discovered_ids = [str(model.get("id", "")) for model in discovered_models]
    if selected_model_name and selected_model_name in discovered_ids:
        return selected_model_name
    if not user_overrode_model_name and discovered_ids:
        return discovered_ids[0]
    return ""


def _descriptor_context_window(
    discovered_models: list[ModelDescriptorPayload],
    model_name: str,
) -> int | None:
    """
    @brief      Read normalized inline context metadata for one exact model.
    @param[in]  discovered_models Normalized model descriptors.
    @param[in]  model_name Exact effective model identifier.
    @return     Positive bounded context window or `None`.
    @exception  None
    """
    for model in discovered_models:
        if str(model.get("id", "")) == model_name:
            return _normalize_context_window(model.get("context_window"))
    return None


def _optional_lm_studio_context_window(
    profile_payload: dict[str, object],
    timeout_seconds: int,
    model_name: str,
) -> int | None:
    """
    @brief      Read optional LM Studio native context metadata without failing discovery.
    @param[in]  profile_payload Normalized profile payload.
    @param[in]  timeout_seconds HTTP request timeout.
    @param[in]  model_name Exact effective model identifier.
    @return     Matching runtime or supported context window, otherwise `None`.
    @exception  None
    """
    try:
        payload = _read_json(
            _resolve_lm_studio_models_url(str(profile_payload.get("base_url", ""))),
            _build_request_headers(profile_payload),
            timeout_seconds,
        )
        return _lm_studio_context_window(payload, model_name)
    except (error.HTTPError, OSError, client.HTTPException, UnicodeError, ValueError):
        return None


def _lm_studio_context_window(payload: dict[str, Any], model_name: str) -> int | None:
    """
    @brief      Extract context metadata for one exact LM Studio model or instance.
    @param[in]  payload LM Studio native model-list payload.
    @param[in]  model_name Exact effective model identifier.
    @return     Matching loaded context or supported model limit, otherwise `None`.
    @exception  ValueError When the native models container is invalid.
    """
    model_entries = payload.get("models")
    if not isinstance(model_entries, list):
        raise ValueError("backend returned invalid native model metadata")
    for model_entry in model_entries:
        if not isinstance(model_entry, dict):
            continue
        loaded_instances = model_entry.get("loaded_instances", [])
        if not isinstance(loaded_instances, list):
            loaded_instances = []
        matching_instances = [
            instance
            for instance in loaded_instances
            if isinstance(instance, dict) and str(instance.get("id", "")).strip() == model_name
        ]
        model_key_matches = str(model_entry.get("key", "")).strip() == model_name
        if not model_key_matches and not matching_instances:
            continue
        for instance in matching_instances:
            instance_config = instance.get("config")
            if not isinstance(instance_config, dict):
                continue
            context_window = _normalize_context_window(instance_config.get("context_length"))
            if context_window is not None:
                return context_window
        return _normalize_context_window(model_entry.get("max_context_length"))
    return None


def _optional_ollama_context_window(
    profile_payload: dict[str, object],
    timeout_seconds: int,
    model_name: str,
) -> int | None:
    """
    @brief      Read optional Ollama context metadata without failing model discovery.
    @param[in]  profile_payload Normalized profile payload.
    @param[in]  timeout_seconds HTTP request timeout.
    @param[in]  model_name Exact confirmed model identifier.
    @return     Positive bounded model context window or `None`.
    @exception  None
    """
    try:
        payload = _read_json(
            _resolve_ollama_show_url(str(profile_payload.get("base_url", ""))),
            _build_request_headers(profile_payload),
            timeout_seconds,
            method="POST",
            json_body={"model": model_name},
        )
    except (error.HTTPError, OSError, client.HTTPException, UnicodeError, ValueError):
        return None
    model_info = payload.get("model_info")
    if not isinstance(model_info, dict):
        return None
    for metadata_key, metadata_value in model_info.items():
        if str(metadata_key).split(".")[-1] == "context_length":
            context_window = _normalize_context_window(metadata_value)
            if context_window is not None:
                return context_window
    return None


def _normalize_context_window(value: object) -> int | None:
    """
    @brief      Normalize one provider context value to the supported UI range.
    @param[in]  value Provider metadata value.
    @return     Positive bounded integer or `None`.
    @exception  None
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0 or value > _MAX_DISCOVERED_CONTEXT_WINDOW:
        return None
    return value


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
    *,
    method: str = "GET",
    json_body: dict[str, object] | None = None,
) -> dict[str, Any]:
    """
    @brief      Execute one JSON request and decode the response.
    @param[in]  url Fully qualified target URL.
    @param[in]  headers HTTP header mapping.
    @param[in]  timeout_seconds HTTP request timeout.
    @param[in]  method HTTP method.
    @param[in]  json_body Optional JSON object request body.
    @return     Decoded JSON object payload.
    @exception  ValueError When decoding fails or the payload root is invalid.
    """
    request_headers = dict(headers)
    request_body = None
    if json_body is not None:
        request_headers["Content-Type"] = "application/json"
        request_body = json.dumps(json_body).encode("utf-8")
    http_request = request.Request(
        url=url,
        headers=request_headers,
        data=request_body,
        method=method,
    )
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
    discovered_context_model_name: str | None,
    selected_model_valid: bool,
) -> ProviderProbeResultPayload:
    """
    @brief      Build one normalized provider probe result payload.
    @param[in]  success True when the backend probe succeeded.
    @param[in]  message Operator-facing probe message.
    @param[in]  discovered_models Normalized discovered model payloads.
    @param[in]  discovered_context_window Optional discovered context window.
    @param[in]  discovered_context_model_name Exact model owning the context value.
    @param[in]  selected_model_valid True when the chosen model is valid.
    @return     Normalized probe result dictionary.
    @exception  None
    """
    return {
        "success": success,
        "message": message,
        "discovered_models": list(discovered_models),
        "discovered_model_count": len(discovered_models),
        "discovered_context_window": discovered_context_window,
        "discovered_context_model_name": discovered_context_model_name,
        "selected_model_valid": selected_model_valid,
    }


def _build_probe_failure(message: str) -> ProviderProbeResultPayload:
    """
    @brief      Build one normalized failed provider probe result.
    @param[in]  message Safe operator-facing failure message.
    @return     Normalized failed probe payload.
    @exception  None
    """
    return _build_probe_result(
        success=False,
        message=message,
        discovered_models=[],
        discovered_context_window=None,
        discovered_context_model_name=None,
        selected_model_valid=False,
    )


# END OF FILE
