#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file voiceweaver_runtime_service.py
@brief VoiceWeaver runtime probe helpers for AudioMancer.
@details Probes the local VoiceWeaver REST runtime, normalizes discovered
         models and current status data, and derives one capability matrix used
         by the TTS Settings dialog and Narrator workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 0.11.0
"""

# IMPORTS

from functools import partial
import json
import time
from typing import Any
from urllib import error, parse, request

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import raise_if_cancelled
from audiomancer.services.url_service import join_endpoint_url

# CONSTANTS

_VOICEWEAVER_RUNTIME_LOGGER = get_component_logger("voiceweaver_runtime")
_endpoint_url = partial(join_endpoint_url, collapse_duplicate_version=True)

VoiceWeaverModelPayload = dict[str, object]
VoiceWeaverCapabilityMatrix = dict[str, object]
VoiceWeaverProbeResult = dict[str, object]


def _build_request_headers(runtime_api_key: str) -> dict[str, str]:
    """
    @brief      Build one VoiceWeaver request-header mapping.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @return     HTTP header map.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    headers = {"Accept": "application/json"}
    normalized_api_key = str(runtime_api_key or "").strip()
    if normalized_api_key:
        headers["Authorization"] = f"Bearer {normalized_api_key}"
    return headers


def _read_json(url: str, headers: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    """
    @brief      Execute one JSON GET request and decode the response payload.
    @param[in]  url Fully qualified target URL.
    @param[in]  headers HTTP header mapping.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Decoded JSON object payload.
    @exception  ValueError Raised when the payload cannot be normalized.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    http_request = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("runtime returned a non-object JSON payload")
    return payload


def _send_json_request(
    method: str,
    url: str,
    headers: dict[str, str],
    timeout_seconds: int,
    payload: dict[str, object] | None = None,
) -> Any:
    """
    @brief      Execute one JSON request and decode the object response payload.
    @param[in]  method HTTP method token.
    @param[in]  url Fully qualified target URL.
    @param[in]  headers HTTP header mapping.
    @param[in]  timeout_seconds Request timeout in seconds.
    @param[in]  payload Optional JSON-serializable object request body.
    @return     Decoded JSON payload or `None` when the response body is empty.
    @exception  ValueError Raised when the response cannot be decoded as JSON.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    1.2.0
    """
    request_headers = dict(headers)
    request_body = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        request_body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(url=url, headers=request_headers, data=request_body, method=method)
    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        response_body = response.read().decode("utf-8")
    if not response_body.strip():
        return None
    return json.loads(response_body)


def _add_tts_language_field(
    payload: dict[str, object],
    language: str,
    supported_languages: list[str] | None = None,
) -> None:
    """
    @brief      Add the VoiceWeaver TTS language field when the selected language should be explicit.
    @param[in]  payload Mutable outbound TTS request payload.
    @param[in]  language Selected synthesis language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.3.0
    """
    normalized_language = str(language).strip()
    normalized_supported_languages = (
        {str(item).strip() for item in supported_languages if str(item).strip()}
        if supported_languages is not None
        else None
    )
    if normalized_language == "ro":
        return
    if normalized_supported_languages is not None and normalized_language not in normalized_supported_languages:
        return
    if normalized_language:
        payload["language"] = normalized_language


def _send_multipart_request(
    method: str,
    url: str,
    headers: dict[str, str],
    timeout_seconds: int,
    form_fields: dict[str, object],
    file_field_name: str,
    file_name: str,
    file_bytes: bytes,
    file_content_type: str = "audio/wav",
) -> Any:
    """
    @brief      Execute one multipart/form-data request and decode the optional JSON response payload.
    @param[in]  method HTTP method token.
    @param[in]  url Fully qualified target URL.
    @param[in]  headers HTTP header mapping.
    @param[in]  timeout_seconds Request timeout in seconds.
    @param[in]  form_fields Flat form-field mapping encoded as strings.
    @param[in]  file_field_name Multipart field name used for the binary file part.
    @param[in]  file_name Uploaded file name.
    @param[in]  file_bytes Raw uploaded file bytes.
    @param[in]  file_content_type Uploaded file content type.
    @return     Decoded JSON payload or `None` when the response body is empty.
    @exception  ValueError Raised when the response cannot be decoded as JSON.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    boundary = f"----AudioMancerVoiceWeaverBoundary{int(time.time() * 1000)}"
    request_headers = dict(headers)
    request_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    body_parts: list[bytes] = []
    for field_name, field_value in form_fields.items():
        if field_value in (None, ""):
            continue
        body_parts.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode(),
                str(field_value).encode("utf-8"),
                b"\r\n",
            )
        )
    body_parts.extend(
        (
            f"--{boundary}\r\n".encode(),
            (f'Content-Disposition: form-data; name="{file_field_name}"; filename="{file_name}"\r\n').encode(),
            f"Content-Type: {file_content_type}\r\n\r\n".encode(),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        )
    )
    http_request = request.Request(
        url=url,
        headers=request_headers,
        data=b"".join(body_parts),
        method=method,
    )
    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        response_body = response.read().decode("utf-8")
    if not response_body.strip():
        return None
    return json.loads(response_body)


def _read_bytes(url: str, headers: dict[str, str], timeout_seconds: int) -> bytes:
    """
    @brief      Execute one binary GET request and return the response bytes.
    @param[in]  url Fully qualified target URL.
    @param[in]  headers HTTP header mapping.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Raw response bytes.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    1.0.0
    """
    http_request = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        return response.read()


def _normalize_string_list(value: object) -> list[str]:
    """
    @brief      Normalize one list-like payload into a list of non-empty strings.
    @param[in]  value Candidate list payload.
    @return     Normalized string list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_generation_modes(value: object) -> list[str]:
    """
    @brief      Normalize one model generation-mode list and fold legacy aliases into the current REST contract.
    @param[in]  value Candidate generation-mode list payload.
    @return     Normalized generation-mode list using current REST mode identifiers.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    mode_aliases = {
        "base": "clone",
        "voice_designer": "definition",
    }
    normalized_modes: list[str] = []
    for mode in _normalize_string_list(value):
        normalized_mode = mode_aliases.get(mode, mode)
        if normalized_mode not in normalized_modes:
            normalized_modes.append(normalized_mode)
    return normalized_modes


def _normalize_model_parameters(value: object) -> dict[str, object] | None:
    """
    @brief      Normalize one flat model-parameter object from VoiceWeaver.
    @param[in]  value Candidate model-parameter payload.
    @return     Normalized flat parameter mapping or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    if not isinstance(value, dict):
        return None
    normalized_payload: dict[str, object] = {}
    for key, parameter_value in value.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        if parameter_value is None or isinstance(parameter_value, (bool, int, float, str)):
            normalized_payload[normalized_key] = parameter_value
    return normalized_payload


def _normalize_generation_parameter_ranges(value: object) -> dict[str, dict[str, object]]:
    """
    @brief      Normalize VoiceWeaver generation-parameter ranges by parameter name.
    @param[in]  value Candidate range payload from model or status data.
    @return     Mapping of parameter names to scalar range metadata.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if not isinstance(value, (dict, list)):
        return {}
    raw_items = value.items() if isinstance(value, dict) else enumerate(value)
    normalized_ranges: dict[str, dict[str, object]] = {}
    for fallback_name, range_payload in raw_items:
        if not isinstance(range_payload, dict):
            continue
        parameter_name = str(range_payload.get("name", fallback_name)).strip()
        if not parameter_name:
            continue
        normalized_payload: dict[str, object] = {}
        for key, parameter_value in range_payload.items():
            normalized_key = str(key).strip()
            if not normalized_key or normalized_key == "name":
                continue
            if parameter_value is None or isinstance(parameter_value, (bool, int, float, str)):
                normalized_payload[normalized_key] = parameter_value
        if normalized_payload:
            normalized_ranges[parameter_name] = normalized_payload
    return normalized_ranges


def _normalize_active_model_payload(value: object) -> object:
    """
    @brief      Normalize active-model status data while preserving runtime-reported effective parameters.
    @param[in]  value Candidate `/v1/status.active_model` payload.
    @return     Normalized active-model identifier string, object, or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return value
    normalized_payload = dict(value)
    for field_name in ("effective_model_parameters", "effective_parameters", "model_parameters"):
        normalized_parameters = _normalize_model_parameters(normalized_payload.get(field_name))
        if normalized_parameters is not None:
            normalized_payload[field_name] = normalized_parameters
    default_parameters = _normalize_model_parameters(normalized_payload.get("default_model_parameters"))
    if default_parameters is not None:
        normalized_payload["default_model_parameters"] = default_parameters
    parameter_ranges = _normalize_generation_parameter_ranges(normalized_payload.get("generation_parameter_ranges"))
    if parameter_ranges:
        normalized_payload["generation_parameter_ranges"] = parameter_ranges
    return normalized_payload


def _normalize_status_payload(payload: dict[str, object]) -> dict[str, object]:
    """
    @brief      Normalize expanded `/v1/status` data needed by AudioMancer.
    @param[in]  payload Raw VoiceWeaver status payload.
    @return     Status payload with normalized active/effective model parameter fields.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    normalized_payload = dict(payload)
    normalized_payload["active_model"] = _normalize_active_model_payload(payload.get("active_model"))
    for field_name in ("effective_model_parameters", "effective_parameters", "model_parameters"):
        normalized_parameters = _normalize_model_parameters(normalized_payload.get(field_name))
        if normalized_parameters is not None:
            normalized_payload[field_name] = normalized_parameters
    parameter_ranges = _normalize_generation_parameter_ranges(normalized_payload.get("generation_parameter_ranges"))
    if parameter_ranges:
        normalized_payload["generation_parameter_ranges"] = parameter_ranges
    return normalized_payload


def _normalize_device_diagnostics(candidate_payload: object) -> dict[str, object]:
    """
    @brief      Normalize one runtime device-diagnostics payload.
    @param[in]  candidate_payload Candidate diagnostics payload.
    @return     Normalized diagnostics dictionary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    if not isinstance(candidate_payload, dict):
        return {}
    normalized_payload: dict[str, object] = {}
    for key, value in candidate_payload.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        if value is None or isinstance(value, (bool, int, float, str)):
            normalized_payload[normalized_key] = value
    return normalized_payload


def _normalize_model(candidate_model: object) -> VoiceWeaverModelPayload | None:
    """
    @brief      Normalize one VoiceWeaver discovered-model payload.
    @param[in]  candidate_model Candidate model payload.
    @return     Normalized model payload or None when invalid.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    0.2.0
    """
    if not isinstance(candidate_model, dict):
        return None
    model_id = str(candidate_model.get("model_id", "")).strip()
    if not model_id:
        return None
    supported_generation_modes = _normalize_generation_modes(candidate_model.get("supported_generation_modes"))
    issues = candidate_model.get("issues")
    return {
        "model_id": model_id,
        "backend_name": str(candidate_model.get("backend_name", "")).strip(),
        "status": str(candidate_model.get("status", "unhealthy")).strip().lower() or "unhealthy",
        "supported_generation_modes": supported_generation_modes,
        "supported_languages": _normalize_string_list(candidate_model.get("supported_languages")),
        "default_model_parameters": _normalize_model_parameters(candidate_model.get("default_model_parameters")),
        "generation_parameter_ranges": _normalize_generation_parameter_ranges(
            candidate_model.get("generation_parameter_ranges")
        ),
        "device_mode": str(candidate_model.get("device_mode", "")).strip(),
        "issues": issues if isinstance(issues, (list, type(None))) else None,
    }


def build_capability_matrix(discovered_models: list[VoiceWeaverModelPayload]) -> VoiceWeaverCapabilityMatrix:
    """
    @brief      Derive one TTS capability matrix from normalized discovered models.
    @param[in]  discovered_models Normalized VoiceWeaver discovered-model list.
    @return     Capability matrix used by the UI and narrator state shaping.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.1.0
    """
    normalized_models = [_normalize_model(model) for model in discovered_models if isinstance(model, dict)]
    healthy_models = [
        model
        for model in normalized_models
        if model is not None and str(model.get("status", "")).strip().lower() in {"healthy", "ready"}
    ]
    definition_models = [
        model
        for model in healthy_models
        if "definition" in _normalize_generation_modes(model.get("supported_generation_modes"))
    ]
    clone_models = [
        model
        for model in healthy_models
        if "clone" in _normalize_generation_modes(model.get("supported_generation_modes"))
    ]
    voice_designer_models = list(definition_models)
    base_models = list(clone_models)
    qwen_voice_designer_models = [model for model in voice_designer_models if _is_qwen_model(model)]
    qwen_base_models = [model for model in base_models if _is_qwen_model(model)]
    missing_qwen_capabilities: list[str] = []
    if not qwen_base_models:
        missing_qwen_capabilities.append("base")
    if not qwen_voice_designer_models:
        missing_qwen_capabilities.append("voice_designer")
    return {
        "definition_models": definition_models,
        "clone_models": clone_models,
        "voice_designer_models": voice_designer_models,
        "base_models": base_models,
        "qwen_voice_designer_models": qwen_voice_designer_models,
        "qwen_base_models": qwen_base_models,
        "minimum_qwen_ready": not missing_qwen_capabilities,
        "missing_qwen_capabilities": missing_qwen_capabilities,
        "preset_voice_available": False,
        "generate_and_clone_available": bool(definition_models and clone_models),
    }


@trace_function(_VOICEWEAVER_RUNTIME_LOGGER)
def probe_runtime(
    base_url: str,
    runtime_api_key: str = "",
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> VoiceWeaverProbeResult:
    """
    @brief      Probe the VoiceWeaver runtime and normalize discovered capability data.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Normalized runtime probe payload with models and capability matrix.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.2.0
    """
    normalized_base_url = str(base_url or "").strip()
    if not normalized_base_url:
        return _build_probe_result(
            success=False,
            message="Connection failed: Base URL is empty.",
            discovered_models=[],
            active_model_id=None,
            device_diagnostics={},
        )

    headers = _build_request_headers(runtime_api_key)

    try:
        health_payload = _read_json(_endpoint_url(normalized_base_url, "/v1/health"), headers, timeout_seconds)
        _validate_health_payload(health_payload)
        models_payload = _read_json(_endpoint_url(normalized_base_url, "/v1/models"), headers, timeout_seconds)
        discovered_models = _normalize_models_payload(models_payload)
        status_payload = _read_json(_endpoint_url(normalized_base_url, "/v1/status"), headers, timeout_seconds)
        active_model_id = _resolve_active_model_id(status_payload.get("active_model"))
        device_diagnostics = _normalize_device_diagnostics(status_payload.get("device_diagnostics"))
    except error.HTTPError as exception:
        if exception.code == 401:
            return _build_probe_result(
                success=False,
                message="Connection failed: invalid or missing runtime credentials.",
                discovered_models=[],
                active_model_id=None,
                device_diagnostics={},
            )
        return _build_probe_result(
            success=False,
            message=f"Connection failed: HTTP {exception.code}.",
            discovered_models=[],
            active_model_id=None,
            device_diagnostics={},
        )
    except error.URLError as exception:
        reason = getattr(exception, "reason", exception)
        return _build_probe_result(
            success=False,
            message=f"Connection failed: {reason}.",
            discovered_models=[],
            active_model_id=None,
            device_diagnostics={},
        )
    except TimeoutError:
        return _build_probe_result(
            success=False,
            message="Connection failed: request timed out.",
            discovered_models=[],
            active_model_id=None,
            device_diagnostics={},
        )
    except ValueError as exception:
        return _build_probe_result(
            success=False,
            message=f"Connection failed: {exception}.",
            discovered_models=[],
            active_model_id=None,
            device_diagnostics={},
        )

    return _build_probe_result(
        success=True,
        message=f"Connection successful. Discovered {len(discovered_models)} models.",
        discovered_models=discovered_models,
        active_model_id=active_model_id,
        device_diagnostics=device_diagnostics,
    )


def read_status(
    base_url: str,
    runtime_api_key: str = "",
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Read the current normalized VoiceWeaver runtime status payload.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime status payload returned by `/v1/status`.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    1.0.0
    """
    return _normalize_status_payload(_request_json_endpoint(base_url, runtime_api_key, "/v1/status", timeout_seconds))


def read_server_info(
    base_url: str,
    runtime_api_key: str = "",
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Read the VoiceWeaver `/v1/server` identity payload.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime server payload returned by `/v1/server`.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    return _request_json_endpoint(base_url, runtime_api_key, "/v1/server", timeout_seconds)


def read_model_catalog(
    base_url: str,
    runtime_api_key: str = "",
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Read the static VoiceWeaver `/v1/model-catalog` payload.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime catalog payload returned by `/v1/model-catalog`.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    return _request_json_endpoint(base_url, runtime_api_key, "/v1/model-catalog", timeout_seconds)


def load_model(
    base_url: str,
    runtime_api_key: str,
    model_id: str,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Load one runtime model through `POST /v1/models/load`.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  model_id Target runtime model identifier.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by the load endpoint.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    1.1.0
    """
    response_payload = _post_json_endpoint(
        base_url,
        runtime_api_key,
        "/v1/models/load",
        {"model_id": str(model_id).strip()},
        timeout_seconds,
    )
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid load-model response payload.")
    return response_payload


def unload_model(
    base_url: str,
    runtime_api_key: str = "",
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object] | None:
    """
    @brief      Unload the active VoiceWeaver model through `POST /v1/models/unload`.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload or `None` when the runtime reports a no-op unload.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    response_payload = _post_json_endpoint(base_url, runtime_api_key, "/v1/models/unload", None, timeout_seconds)
    if response_payload is None:
        return None
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid unload-model response payload.")
    return response_payload


def rescan_models(
    base_url: str,
    runtime_api_key: str = "",
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Force one VoiceWeaver model rescan through `POST /v1/models/rescan`.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime payload returned by the rescan endpoint.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    response_payload = _post_json_endpoint(base_url, runtime_api_key, "/v1/models/rescan", None, timeout_seconds)
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid model-rescan response payload.")
    return response_payload


def delete_model(
    base_url: str,
    runtime_api_key: str,
    model_id: str,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> None:
    """
    @brief      Delete one installed VoiceWeaver model through `DELETE /v1/models/{model_id}`.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  model_id Target runtime model identifier.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     None.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    encoded_model_id = parse.quote(str(model_id).strip(), safe="")
    _request_without_json_response(
        base_url,
        runtime_api_key,
        f"/v1/models/{encoded_model_id}",
        "DELETE",
        timeout_seconds,
    )


def start_model_download(
    base_url: str,
    runtime_api_key: str,
    model_id: str,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one VoiceWeaver background model download through `POST /v1/models/download`.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  model_id Target catalog model identifier.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Download-status payload returned by the runtime.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    response_payload = _post_json_endpoint(
        base_url,
        runtime_api_key,
        "/v1/models/download",
        {"model_id": str(model_id).strip()},
        timeout_seconds,
    )
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid model-download response payload.")
    return response_payload


def read_model_download_status(
    base_url: str,
    runtime_api_key: str = "",
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Read the current VoiceWeaver model-download status payload.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Download-status payload returned by `/v1/models/download/status`.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    return _request_json_endpoint(base_url, runtime_api_key, "/v1/models/download/status", timeout_seconds)


def cancel_model_download(
    base_url: str,
    runtime_api_key: str = "",
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> None:
    """
    @brief      Cancel the active VoiceWeaver model download through `POST /v1/models/download/cancel`.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     None.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    _request_without_json_response(base_url, runtime_api_key, "/v1/models/download/cancel", "POST", timeout_seconds)


def generate_voice_design(
    base_url: str,
    runtime_api_key: str,
    language: str,
    text: str,
    voice_description: str,
    model_parameters: dict[str, object] | None = None,
    supported_languages: list[str] | None = None,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one Voice Designer generation request.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  language Synthesis language code.
    @param[in]  text Preview text to synthesize.
    @param[in]  voice_description Voice Designer prompt text.
    @param[in]  model_parameters Optional VoiceWeaver model-parameter overrides.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by `/v1/voice/design`.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    1.2.0
    """
    payload = {
        "text": str(text).strip(),
        "voice_description": str(voice_description).strip(),
    }
    _add_tts_language_field(payload, language, supported_languages)
    normalized_model_parameters = _normalize_model_parameters(model_parameters)
    if normalized_model_parameters:
        payload["model_parameters"] = normalized_model_parameters
    response_payload = _post_json_endpoint(
        base_url,
        runtime_api_key,
        "/v1/voice/design",
        payload,
        timeout_seconds,
    )
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid voice-design response payload.")
    return response_payload


def generate_voice_clone(
    base_url: str,
    runtime_api_key: str,
    sample_audio_bytes: bytes,
    sample_text: str,
    language: str,
    text: str,
    model_parameters: dict[str, object] | None = None,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one direct Qwen3 voice-clone request from a WAV sample.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  sample_audio_bytes WAV reference audio bytes uploaded for cloning.
    @param[in]  sample_text Transcript matching the reference audio sample.
    @param[in]  language Synthesis language code associated with the sample.
    @param[in]  text Speech-block text to synthesize in the cloned voice.
    @param[in]  model_parameters Optional VoiceWeaver model-parameter overrides.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by `/v1/voice/clone`.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    headers = _build_request_headers(runtime_api_key)
    form_fields: dict[str, object] = {
        "sample_text": str(sample_text).strip(),
        "text": str(text).strip(),
    }
    _add_tts_language_field(form_fields, language)
    normalized_model_parameters = _normalize_model_parameters(model_parameters)
    if normalized_model_parameters:
        form_fields["model_parameters_json"] = json.dumps(normalized_model_parameters)
    try:
        response_payload = _send_multipart_request(
            "POST",
            _endpoint_url(base_url, "/v1/voice/clone"),
            headers,
            timeout_seconds,
            form_fields,
            "voice_sample",
            "reference.wav",
            sample_audio_bytes,
        )
    except error.HTTPError as exception:
        raise RuntimeError(_runtime_error_message(exception)) from exception
    except error.URLError as exception:
        raise RuntimeError(f"Connection failed: {getattr(exception, 'reason', exception)}.") from exception
    except TimeoutError as exception:
        raise RuntimeError("Connection failed: request timed out.") from exception
    except ValueError as exception:
        raise RuntimeError(str(exception)) from exception
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid voice-clone response payload.")
    return response_payload


def create_voice_clone_prompt(
    base_url: str,
    runtime_api_key: str,
    sample_audio_bytes: bytes,
    sample_text: str,
    language: str,
    model_parameters: dict[str, object] | None = None,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one reusable Qwen3 voice clone-prompt creation request from a WAV sample.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  sample_audio_bytes WAV reference audio bytes uploaded for clone-prompt creation.
    @param[in]  sample_text Transcript matching the reference audio sample.
    @param[in]  language Synthesis language code associated with the sample.
    @param[in]  model_parameters Optional VoiceWeaver model-parameter overrides.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by `/v1/voice/clone-prompt`.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    headers = _build_request_headers(runtime_api_key)
    form_fields: dict[str, object] = {
        "sample_text": str(sample_text).strip(),
    }
    _add_tts_language_field(form_fields, language)
    normalized_model_parameters = _normalize_model_parameters(model_parameters)
    if normalized_model_parameters:
        form_fields["model_parameters_json"] = json.dumps(normalized_model_parameters)
    try:
        response_payload = _send_multipart_request(
            "POST",
            _endpoint_url(base_url, "/v1/voice/clone-prompt"),
            headers,
            timeout_seconds,
            form_fields,
            "voice_sample",
            "reference.wav",
            sample_audio_bytes,
        )
    except error.HTTPError as exception:
        raise RuntimeError(_runtime_error_message(exception)) from exception
    except error.URLError as exception:
        raise RuntimeError(f"Connection failed: {getattr(exception, 'reason', exception)}.") from exception
    except TimeoutError as exception:
        raise RuntimeError("Connection failed: request timed out.") from exception
    except ValueError as exception:
        raise RuntimeError(str(exception)) from exception
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid clone-prompt response payload.")
    return response_payload


def generate_voice_clone_from_prompt(
    base_url: str,
    runtime_api_key: str,
    voice_clone_prompt: dict[str, object] | str,
    language: str,
    text: str,
    model_parameters: dict[str, object] | None = None,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one reusable Qwen3 voice-clone generation request from one stored clone prompt.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  voice_clone_prompt Client-owned VoiceWeaver clone-prompt payload or serialized JSON string.
    @param[in]  language Synthesis language code associated with the target text.
    @param[in]  text Speech-block text to synthesize in the cloned voice.
    @param[in]  model_parameters Optional VoiceWeaver model-parameter overrides.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by `/v1/voice/clone-from-prompt`.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    payload: dict[str, object] = {
        "voice_clone_prompt": voice_clone_prompt,
        "text": str(text).strip(),
    }
    _add_tts_language_field(payload, language)
    normalized_model_parameters = _normalize_model_parameters(model_parameters)
    if normalized_model_parameters:
        payload["model_parameters"] = normalized_model_parameters
    response_payload = _post_json_endpoint(
        base_url,
        runtime_api_key,
        "/v1/voice/clone-from-prompt",
        payload,
        timeout_seconds,
    )
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid prompt-clone response payload.")
    return response_payload


def wait_for_terminal_operation(
    base_url: str,
    runtime_api_key: str = "",
    poll_interval_seconds: float = 0.5,
    timeout_seconds: int = config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    progress_callback=None,
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Poll `/v1/status` until the current runtime operation completes or fails.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  poll_interval_seconds Delay between status polls.
    @param[in]  timeout_seconds Maximum total polling duration.
    @param[in]  progress_callback Optional callback receiving each status payload.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Final runtime status payload.
    @exception  RuntimeError Raised when the poll times out.
    @exception  OperationCancelledError Raised when cancellation is requested.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    1.2.0
    """
    deadline = time.monotonic() + timeout_seconds
    last_status_payload: dict[str, object] | None = None
    while time.monotonic() <= deadline:
        raise_if_cancelled(cancel_requested)
        last_status_payload = read_status(
            base_url, runtime_api_key, timeout_seconds=config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS
        )
        raise_if_cancelled(cancel_requested)
        if callable(progress_callback):
            progress_callback(last_status_payload)
        operation_payload = last_status_payload.get("operation", {})
        operation_status = (
            str(
                operation_payload.get("status", operation_payload.get("kind", "idle"))
                if isinstance(operation_payload, dict)
                else ""
            )
            .strip()
            .lower()
        )
        if operation_status in {"completed", "failed", "idle"}:
            return last_status_payload
        _sleep_with_cancel(max(poll_interval_seconds, 0.05), cancel_requested)
    raise RuntimeError("Timed out while waiting for VoiceWeaver to finish the current operation.")


def _sleep_with_cancel(delay_seconds: float, cancel_requested) -> None:
    """
    @brief      Sleep in short slices so UI cancellation can interrupt polling quickly.
    @param[in]  delay_seconds Total requested sleep duration.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     None.
    @exception  OperationCancelledError Raised when cancellation is requested.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    deadline = time.monotonic() + max(float(delay_seconds), 0.0)
    while time.monotonic() < deadline:
        raise_if_cancelled(cancel_requested)
        time.sleep(min(0.05, max(deadline - time.monotonic(), 0.0)))
    raise_if_cancelled(cancel_requested)


def download_generated_voice(
    base_url: str,
    runtime_api_key: str = "",
    timeout_seconds: int = config.DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
) -> bytes:
    """
    @brief      Download the latest generated WAV bytes from VoiceWeaver.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  runtime_api_key Optional operator-configured bearer token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Downloaded WAV bytes.
    @exception  RuntimeError Raised when the runtime request fails.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    1.0.0
    """
    headers = _build_request_headers(runtime_api_key)
    try:
        return _read_bytes(_endpoint_url(base_url, "/v1/voice"), headers, timeout_seconds)
    except error.HTTPError as exception:
        raise RuntimeError(_runtime_error_message(exception)) from exception
    except error.URLError as exception:
        raise RuntimeError(f"Connection failed: {getattr(exception, 'reason', exception)}.") from exception


def operation_failed_message(status_payload: dict[str, object]) -> str:
    """
    @brief      Extract one operator-facing failure message from a terminal runtime status payload.
    @param[in]  status_payload Final runtime status payload.
    @return     Failure message or one fallback summary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    1.0.0
    """
    operation_payload = status_payload.get("operation", {})
    if isinstance(operation_payload, dict):
        error_payload = operation_payload.get("error")
        if isinstance(error_payload, dict):
            message = str(error_payload.get("message", "")).strip()
            if message:
                return message
        if isinstance(error_payload, str) and error_payload.strip():
            return error_payload.strip()
        stage_message = str(operation_payload.get("stage", "")).strip()
        if stage_message:
            return stage_message
    return "VoiceWeaver reported a failed operation."


def _validate_health_payload(health_payload: object) -> None:
    """
    @brief      Validate the minimal VoiceWeaver health payload shape.
    @param[in]  health_payload Candidate health payload.
    @return     None.
    @exception  ValueError Raised when the payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    if not isinstance(health_payload, dict):
        raise ValueError("runtime returned an invalid health payload")
    if str(health_payload.get("status", "")).strip().lower() != "ok":
        raise ValueError("runtime health check did not return status = ok")


def _normalize_models_payload(models_payload: object) -> list[VoiceWeaverModelPayload]:
    """
    @brief      Normalize the `/v1/models` payload into one discovered-model list.
    @param[in]  models_payload Candidate models payload.
    @return     Normalized discovered-model list.
    @exception  ValueError Raised when the payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    if not isinstance(models_payload, dict):
        raise ValueError("runtime returned an invalid models payload")
    model_entries = models_payload.get("models")
    if not isinstance(model_entries, list):
        raise ValueError("runtime returned an invalid models payload")
    normalized_models: list[VoiceWeaverModelPayload] = []
    for model_entry in model_entries:
        normalized_model = _normalize_model(model_entry)
        if normalized_model is not None:
            normalized_models.append(normalized_model)
    return normalized_models


def _resolve_active_model_id(active_model_payload: object) -> str | None:
    """
    @brief      Resolve one active-model identifier from the `/v1/status` payload.
    @param[in]  active_model_payload Candidate active-model payload.
    @return     Active model identifier or None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    if active_model_payload in (None, ""):
        return None
    if isinstance(active_model_payload, str):
        normalized_model_id = active_model_payload.strip()
        return normalized_model_id or None
    if isinstance(active_model_payload, dict):
        normalized_model_id = str(active_model_payload.get("model_id", "")).strip()
        return normalized_model_id or None
    return None


def _build_probe_result(
    success: bool,
    message: str,
    discovered_models: list[VoiceWeaverModelPayload],
    active_model_id: str | None,
    device_diagnostics: dict[str, object],
) -> VoiceWeaverProbeResult:
    """
    @brief      Build one normalized VoiceWeaver probe result payload.
    @param[in]  success True when the runtime probe succeeded.
    @param[in]  message Operator-facing probe message.
    @param[in]  discovered_models Normalized discovered-model list.
    @param[in]  active_model_id Active model identifier or None.
    @param[in]  device_diagnostics Normalized runtime device-diagnostics payload.
    @return     Normalized runtime probe result dictionary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    capability_matrix = build_capability_matrix(discovered_models)
    return {
        "success": success,
        "message": message,
        "discovered_models": list(discovered_models),
        "discovered_model_count": len(discovered_models),
        "active_model_id": active_model_id,
        "device_diagnostics": dict(device_diagnostics),
        "capability_matrix": capability_matrix,
    }


def _request_json_endpoint(
    base_url: str,
    runtime_api_key: str,
    endpoint: str,
    timeout_seconds: int,
) -> dict[str, object]:
    """
    @brief      Execute the request json endpoint helper.
    @param[in]  base_url Value for `base_url`.
    @param[in]  runtime_api_key Value for `runtime_api_key`.
    @param[in]  endpoint Value for `endpoint`.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    headers = _build_request_headers(runtime_api_key)
    try:
        payload = _read_json(_endpoint_url(base_url, endpoint), headers, timeout_seconds)
    except error.HTTPError as exception:
        raise RuntimeError(_runtime_error_message(exception)) from exception
    except error.URLError as exception:
        raise RuntimeError(f"Connection failed: {getattr(exception, 'reason', exception)}.") from exception
    except TimeoutError as exception:
        raise RuntimeError("Connection failed: request timed out.") from exception
    except ValueError as exception:
        raise RuntimeError(str(exception)) from exception
    return payload


def _post_json_endpoint(
    base_url: str,
    runtime_api_key: str,
    endpoint: str,
    payload: dict[str, object] | None,
    timeout_seconds: int,
) -> object:
    """
    @brief      Execute the post json endpoint helper.
    @param[in]  base_url Value for `base_url`.
    @param[in]  runtime_api_key Value for `runtime_api_key`.
    @param[in]  endpoint Value for `endpoint`.
    @param[in]  payload Optional payload processed by the helper.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    headers = _build_request_headers(runtime_api_key)
    try:
        response_payload = _send_json_request(
            "POST",
            _endpoint_url(base_url, endpoint),
            headers,
            timeout_seconds,
            payload,
        )
    except error.HTTPError as exception:
        raise RuntimeError(_runtime_error_message(exception)) from exception
    except error.URLError as exception:
        raise RuntimeError(f"Connection failed: {getattr(exception, 'reason', exception)}.") from exception
    except TimeoutError as exception:
        raise RuntimeError("Connection failed: request timed out.") from exception
    except ValueError as exception:
        raise RuntimeError(str(exception)) from exception
    return response_payload


def _request_without_json_response(
    base_url: str,
    runtime_api_key: str,
    endpoint: str,
    method: str,
    timeout_seconds: int,
) -> None:
    """
    @brief      Execute the request without json response helper.
    @param[in]  base_url Value for `base_url`.
    @param[in]  runtime_api_key Value for `runtime_api_key`.
    @param[in]  endpoint Value for `endpoint`.
    @param[in]  method HTTP method token.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    headers = _build_request_headers(runtime_api_key)
    http_request = request.Request(url=_endpoint_url(base_url, endpoint), headers=headers, method=method)
    try:
        with request.urlopen(http_request, timeout=timeout_seconds):
            return None
    except error.HTTPError as exception:
        raise RuntimeError(_runtime_error_message(exception)) from exception
    except error.URLError as exception:
        raise RuntimeError(f"Connection failed: {getattr(exception, 'reason', exception)}.") from exception
    except TimeoutError as exception:
        raise RuntimeError("Connection failed: request timed out.") from exception


def _runtime_error_message(http_exception: error.HTTPError) -> str:
    """
    @brief      Execute the runtime error message helper.
    @param[in]  http_exception Value for `http_exception`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if http_exception.code == 401:
        return "Connection failed: invalid or missing runtime credentials."
    error_body = ""
    if http_exception.fp is not None:
        try:
            error_body = http_exception.fp.read().decode("utf-8")
        except Exception:  # noqa: BLE001
            error_body = ""
    if error_body.strip():
        try:
            error_payload = json.loads(error_body)
        except json.JSONDecodeError:
            error_payload = None
        if isinstance(error_payload, dict):
            message = str(error_payload.get("message", "")).strip()
            if message:
                return message
    return f"Connection failed: HTTP {http_exception.code}."


def _is_qwen_model(model_payload: VoiceWeaverModelPayload) -> bool:
    """
    @brief      Return whether one normalized runtime model belongs to the Qwen TTS family.
    @param[in]  model_payload Normalized discovered-model payload.
    @return     True when the model id or backend name indicates Qwen support.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    search_blob = " ".join(
        (
            str(model_payload.get("model_id", "")).strip(),
            str(model_payload.get("backend_name", "")).strip(),
        )
    ).casefold()
    return "qwen" in search_blob


# END OF FILE
