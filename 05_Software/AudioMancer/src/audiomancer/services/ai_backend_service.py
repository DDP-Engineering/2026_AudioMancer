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
_MAX_DISCOVERED_CONTEXT_WINDOW = config.MAX_LLM_CONTEXT_WINDOW

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
    if backend_kind == config.CHATGPT_BACKEND_KIND:
        from audiomancer.services.chatgpt_model_service import verify_profile
        return verify_profile(profile_payload)
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
    server_context_window = None
    reasoning = {}
    if backend_kind == "lmstudio" and effective_model_name:
        native_context_window, server_context_window, reasoning = _optional_lm_studio_model_metadata(
            profile_payload,
            timeout_seconds,
            effective_model_name,
        )
        if native_context_window is not None:
            discovered_context_window = native_context_window
    elif backend_kind == "ollama" and effective_model_name:
        ollama_context_window, reasoning = _optional_ollama_model_metadata(
            profile_payload,
            timeout_seconds,
            effective_model_name,
        )
        if ollama_context_window is not None:
            discovered_context_window = ollama_context_window
        server_context_window = _optional_ollama_server_context(
            profile_payload, timeout_seconds, effective_model_name
        )

    message = f"Connection successful. Discovered {len(discovered_models)} models."
    return _build_probe_result(
        success=True,
        message=message,
        discovered_models=discovered_models,
        discovered_context_window=discovered_context_window,
        discovered_context_model_name=(
            effective_model_name if discovered_context_window is not None or server_context_window is not None else None
        ),
        selected_model_valid=selected_model_valid,
        server_context_window=server_context_window,
        reasoning=reasoning,
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
        "/v1/models",
        collapse_duplicate_version=True,
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


def _optional_lm_studio_model_metadata(
    profile_payload: dict[str, object],
    timeout_seconds: int,
    model_name: str,
) -> tuple[int | None, int | None, dict[str, object]]:
    """
    @brief      Read optional LM Studio context and reasoning metadata without failing discovery.
    @param[in]  profile_payload Normalized profile payload.
    @param[in]  timeout_seconds HTTP request timeout.
    @param[in]  model_name Exact effective model identifier.
    @return     Optional model and server limits plus public reasoning settings.
    @exception  None
    """
    try:
        payload = _read_json(
            _resolve_lm_studio_models_url(str(profile_payload.get("base_url", ""))),
            _build_request_headers(profile_payload),
            timeout_seconds,
        )
        return _lm_studio_model_metadata(payload, model_name)
    except (error.HTTPError, OSError, client.HTTPException, UnicodeError, ValueError):
        return None, None, {}


def _lm_studio_model_metadata(
    payload: dict[str, Any], model_name: str
) -> tuple[int | None, int | None, dict[str, object]]:
    """
    @brief      Extract context and reasoning metadata for one exact LM Studio model or instance.
    @param[in]  payload LM Studio native model-list payload.
    @param[in]  model_name Exact effective model identifier.
    @return     Optional model and server limits plus public reasoning settings.
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
        instances = [item for item in loaded_instances if isinstance(item, dict)]
        exact = next((instance for instance in instances if instance.get("id") == model_name), None)
        variants = model_entry.get("variants")
        model_matches = model_name == model_entry.get("key") or (
            isinstance(variants, list) and model_name in variants
        )
        if not model_matches and exact is None:
            continue
        if exact is None and len(instances) == 1 and model_name in (
            model_entry.get("key"), model_entry.get("selected_variant")
        ):
            exact = instances[0]
        loaded_config = exact.get("config") if exact is not None else None
        server_context = (
            _normalize_context_window(loaded_config.get("context_length"))
            if isinstance(loaded_config, dict)
            else None
        )
        capabilities = model_entry.get("capabilities")
        reasoning = capabilities.get("reasoning") if isinstance(capabilities, dict) else None
        return (
            _normalize_context_window(model_entry.get("max_context_length")),
            server_context,
            reasoning if isinstance(reasoning, dict) else {},
        )
    return None, None, {}


def _optional_ollama_model_metadata(
    profile_payload: dict[str, object],
    timeout_seconds: int,
    model_name: str,
) -> tuple[int | None, dict[str, object]]:
    """
    @brief      Read optional Ollama model limits and thinking controls without failing model discovery.
    @param[in]  profile_payload Normalized profile payload.
    @param[in]  timeout_seconds HTTP request timeout.
    @param[in]  model_name Exact confirmed model identifier.
    @return     Optional model context and normalized reasoning settings.
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
        return None, {}
    model_info = payload.get("model_info")
    context_window = next((
        context for key, value in model_info.items()
        if str(key).split(".")[-1] == "context_length"
        and (context := _normalize_context_window(value)) is not None
    ), None) if isinstance(model_info, dict) else None
    thinking = payload.get("thinking")
    if not isinstance(thinking, dict) or not isinstance(thinking.get("values"), list):
        return context_window, {}
    return context_window, {
        "allowed_options": [_ollama_reasoning_level(value) for value in thinking["values"]],
        "default": _ollama_reasoning_level(thinking.get("default")),
    }


def _ollama_reasoning_level(value: object) -> object:
    """@brief Convert Ollama's boolean thinking controls to stable editor options."""
    if type(value) is bool:
        return "on" if value else "off"
    return value


def _optional_ollama_server_context(
    profile_payload: dict[str, object], timeout_seconds: int, model_name: str
) -> int | None:
    """
    @brief      Read the loaded context of the exact Ollama model from /api/ps.
    @param[in]  profile_payload Normalized backend profile.
    @param[in]  timeout_seconds Metadata request timeout.
    @param[in]  model_name Effective selected model identifier.
    @return     Loaded context in tokens, or None if unknown.
    """
    base_url = remove_trailing_endpoint(str(profile_payload.get("base_url", "")), "/v1")
    try:
        payload = _read_json(
            join_endpoint_url(base_url, "/api/ps"), _build_request_headers(profile_payload), timeout_seconds
        )
    except (error.HTTPError, OSError, client.HTTPException, UnicodeError, ValueError):
        return None
    models = payload.get("models")
    if not isinstance(models, list):
        return None
    for model in models:
        if isinstance(model, dict) and model_name in (model.get("model"), model.get("name")):
            return _normalize_context_window(model.get("context_length"))
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
    server_context_window: int | None = None,
    reasoning: dict[str, object] | None = None,
) -> ProviderProbeResultPayload:
    """
    @brief      Build one normalized provider probe result payload.
    @param[in]  success True when the backend probe succeeded.
    @param[in]  message Operator-facing probe message.
    @param[in]  discovered_models Normalized discovered model payloads.
    @param[in]  discovered_context_window Optional discovered context window.
    @param[in]  discovered_context_model_name Exact model owning the context value.
    @param[in]  selected_model_valid True when the chosen model is valid.
    @param[in]  server_context_window Context reported for the loaded instance, if available.
    @param[in]  reasoning Public reasoning settings for the effective model.
    @return     Normalized probe result dictionary.
    @exception  None
    """
    return {
        "success": success,
        "message": message,
        "discovered_models": list(discovered_models),
        "discovered_model_count": len(discovered_models),
        "discovered_context_window": discovered_context_window,
        "server_context_window": server_context_window,
        "reasoning": reasoning or {},
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
