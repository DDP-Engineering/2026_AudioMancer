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
         models and current status, and selects compatible models for speech
         and sound generation.
"""

# IMPORTS

import copy
import json
import time
from typing import Any
from urllib import error, request

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import OperationCancelledError, raise_if_cancelled
from audiomancer.services.url_service import join_endpoint_url

# CONSTANTS

_VOICEWEAVER_RUNTIME_LOGGER = get_component_logger("voiceweaver_runtime")
_endpoint_url = join_endpoint_url

# @brief Generation modes the current VoiceWeaver REST contract defines.
SUPPORTED_GENERATION_MODES = ("voice_design", "clone", "sound_prompt")

VoiceWeaverModelPayload = dict[str, object]
VoiceWeaverCapabilityMatrix = dict[str, object]
VoiceWeaverProbeResult = dict[str, object]


def _build_request_headers() -> dict[str, str]:
    """
    @brief      Build one VoiceWeaver request-header mapping.
    @return     HTTP header map.
    @exception  None
    """
    return {"Accept": "application/json"}


def _read_json(url: str, headers: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    """
    @brief      Execute one JSON GET request and decode the response payload.
    @param[in]  url Fully qualified target URL.
    @param[in]  headers HTTP header mapping.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Decoded JSON object payload.
    @exception  ValueError Raised when the payload cannot be normalized.
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
    """
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_generation_modes(value: object) -> list[str]:
    """
    @brief      Normalize one model generation-mode list without accepting legacy aliases.
    @param[in]  value Candidate generation-mode list payload.
    @return     Normalized generation-mode list using current REST mode identifiers.
    @exception  None
    """
    normalized_modes: list[str] = []
    for mode in _normalize_string_list(value):
        if mode not in normalized_modes:
            normalized_modes.append(mode)
    return normalized_modes


def declares_unknown_generation_modes(candidate_models: object) -> bool:
    """
    @brief      Report whether any candidate model declares a generation mode outside the REST contract.
    @param[in]  candidate_models Candidate discovered-model list payload.
    @return     True when at least one declared mode is not a current REST generation mode.
    @exception  None
    """
    if not isinstance(candidate_models, list):
        return False
    for candidate_model in candidate_models:
        if not isinstance(candidate_model, dict):
            continue
        declared_modes = _normalize_generation_modes(candidate_model.get("supported_generation_modes"))
        if any(mode not in SUPPORTED_GENERATION_MODES for mode in declared_modes):
            return True
    return False


def _normalize_model_parameters(value: object) -> dict[str, object] | None:
    """
    @brief      Normalize one flat model-parameter object from VoiceWeaver.
    @param[in]  value Candidate model-parameter payload.
    @return     Normalized flat parameter mapping or `None`.
    @exception  None
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
    @param[in]  value Candidate `/status.active_model` payload.
    @return     Normalized active-model identifier string, object, or `None`.
    @exception  None
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
    @brief      Normalize expanded `/status` data needed by AudioMancer.
    @param[in]  payload Raw VoiceWeaver status payload.
    @return     Status payload with normalized active/effective model parameter fields.
    @exception  None
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


def normalize_model(candidate_model: object) -> VoiceWeaverModelPayload | None:
    """
    @brief      Normalize one VoiceWeaver discovered-model payload.
    @param[in]  candidate_model Candidate model payload.
    @return     Normalized model payload or None when invalid.
    @exception  None
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
        "supported_languages": [code.casefold() for code in _normalize_string_list(
            candidate_model.get("supported_languages")
        )],
        "default_model_parameters": _normalize_model_parameters(candidate_model.get("default_model_parameters")),
        "generation_parameter_ranges": _normalize_generation_parameter_ranges(
            candidate_model.get("generation_parameter_ranges")
        ),
        "device_mode": str(candidate_model.get("device_mode", "")).strip(),
        "issues": copy.deepcopy(issues) if isinstance(issues, list) else None,
    }


def tts_language_for_model(language: str, model: VoiceWeaverModelPayload) -> str | None:
    """
    @brief      Resolve the language hint accepted by a selected VoiceWeaver model.
    @param[in]  language Canonical project or reference-sample language.
    @param[in]  model Normalized runtime model descriptor.
    @return     Requested or fallback language, or None for a known incompatibility.
    """
    requested = str(language).strip().casefold()
    supported = model.get("supported_languages", [])
    if requested in supported:
        return requested
    if requested == "ro" and is_qwen_model(model) and (not supported or "it" in supported):
        return "it"
    return requested if not supported else None


def resolve_tts_model(
    models: list[object],
    operation: str,
    language: str = "",
) -> VoiceWeaverModelPayload | None:
    """
    @brief      Choose a healthy model for one operation and language.
    @param[in]  models Discovered runtime model descriptors in discovery order.
    @param[in]  operation Required generation mode.
    @param[in]  language Desired speech language, ignored for sound generation.
    @return     Best compatible descriptor, or None when unavailable.
    """
    requested = str(language).strip().casefold()
    candidates = []
    for candidate in models:
        model = normalize_model(candidate)
        if model is None or model["status"] not in {"healthy", "ready"}:
            continue
        if operation not in model["supported_generation_modes"]:
            continue
        rank = 0
        if operation != "sound_prompt" and requested:
            effective = tts_language_for_model(requested, model)
            if effective is None:
                continue
            if requested not in model["supported_languages"]:
                rank = 1 if effective != requested else 2
        preferred = operation == "clone" and model["model_id"] == "Qwen3-TTS-12Hz-1.7B-Base"
        candidates.append(((rank, not preferred), model))
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate[0])[1]


def build_capability_matrix(discovered_models: list[VoiceWeaverModelPayload]) -> VoiceWeaverCapabilityMatrix:
    """
    @brief      Derive one TTS capability matrix from normalized discovered models.
    @param[in]  discovered_models Normalized VoiceWeaver discovered-model list.
    @return     Capability matrix used by the UI and narrator state shaping.
    @exception  None
    """
    normalized_models = [normalize_model(model) for model in discovered_models if isinstance(model, dict)]
    healthy_models = [
        model
        for model in normalized_models
        if model is not None and str(model.get("status", "")).strip().lower() in {"healthy", "ready"}
    ]
    voice_design_models = [
        model
        for model in healthy_models
        if "voice_design" in _normalize_generation_modes(model.get("supported_generation_modes"))
    ]
    clone_models = [
        model
        for model in healthy_models
        if "clone" in _normalize_generation_modes(model.get("supported_generation_modes"))
    ]
    sound_prompt_models = [
        model
        for model in healthy_models
        if "sound_prompt" in _normalize_generation_modes(model.get("supported_generation_modes"))
    ]
    return {
        "voice_design_models": voice_design_models,
        "clone_models": clone_models,
        "sound_prompt_models": sound_prompt_models,
        "sound_prompt_available": bool(sound_prompt_models),
        "generate_and_clone_available": bool(voice_design_models and clone_models),
    }


@trace_function(_VOICEWEAVER_RUNTIME_LOGGER)
def probe_runtime(
    base_url: str,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> VoiceWeaverProbeResult:
    """
    @brief      Probe the VoiceWeaver runtime and normalize discovered capability data.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Normalized runtime probe payload with models and capability matrix.
    @exception  None
    """
    normalized_base_url = str(base_url or "").strip()
    if not normalized_base_url:
        return _build_probe_result(
            success=False,
            message="Connection failed: Base URL is empty.",
            discovered_models=[],
            active_model_id=None,
        )

    headers = _build_request_headers()

    try:
        models_payload = _read_json(_endpoint_url(normalized_base_url, "/models"), headers, timeout_seconds)
        discovered_models = _normalize_models_payload(models_payload)
        status_payload = _read_json(_endpoint_url(normalized_base_url, "/status"), headers, timeout_seconds)
        active_model_id = _resolve_active_model_id(status_payload.get("active_model"))
        runtime_version = _resolve_runtime_version(status_payload, models_payload)
    except error.HTTPError as exception:
        return _build_probe_result(
            success=False,
            message=_runtime_error_message(exception),
            discovered_models=[],
            active_model_id=None,
        )
    except error.URLError as exception:
        reason = getattr(exception, "reason", exception)
        return _build_probe_result(
            success=False,
            message=f"Connection failed: {reason}.",
            discovered_models=[],
            active_model_id=None,
        )
    except TimeoutError:
        return _build_probe_result(
            success=False,
            message="Connection failed: request timed out.",
            discovered_models=[],
            active_model_id=None,
        )
    except ValueError as exception:
        return _build_probe_result(
            success=False,
            message=f"Connection failed: {exception}.",
            discovered_models=[],
            active_model_id=None,
        )

    _VOICEWEAVER_RUNTIME_LOGGER.info(
        "Probed VoiceWeaver runtime_version=%s discovered_models=%s",
        runtime_version or "unreported",
        len(discovered_models),
    )
    return _build_probe_result(
        success=True,
        message=f"Connection successful. Discovered {len(discovered_models)} models.",
        discovered_models=discovered_models,
        active_model_id=active_model_id,
        runtime_version=runtime_version,
    )


def read_status(
    base_url: str,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Read the current normalized VoiceWeaver runtime status payload.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime status payload returned by `/status`.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    return _normalize_status_payload(_request_json_endpoint(base_url, "/status", timeout_seconds))


def load_model(
    base_url: str,
    model_id: str,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Load one runtime model through `POST /models/load`.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  model_id Target runtime model identifier.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by the load endpoint.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    response_payload = _post_json_endpoint(
        base_url,
        "/models/load",
        {"model_id": str(model_id).strip(), "device_mode": "auto"},
        timeout_seconds,
    )
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid load-model response payload.")
    return response_payload


def unload_model(
    base_url: str,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object] | None:
    """
    @brief      Unload the active VoiceWeaver model through `POST /models/unload`.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload or `None` when the runtime reports a no-op unload.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    response_payload = _post_json_endpoint(base_url, "/models/unload", None, timeout_seconds)
    if response_payload is None:
        return None
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid unload-model response payload.")
    return response_payload


def cancel_operation(
    base_url: str,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Request cancellation of the current VoiceWeaver operation through `POST /cancel`.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Current runtime operation payload returned by the cancel endpoint.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    response_payload = _post_json_endpoint(base_url, "/cancel", None, timeout_seconds)
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid cancel response payload.")
    return response_payload


def generate_voice_design(
    base_url: str,
    language: str,
    text: str,
    voice_description: str,
    model_parameters: dict[str, object] | None = None,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one Voice Designer generation request.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  language Synthesis language code.
    @param[in]  text Preview text to synthesize.
    @param[in]  voice_description Voice Designer prompt text.
    @param[in]  model_parameters Optional VoiceWeaver model-parameter overrides.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by `/voice/design`.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    payload = {
        "text": str(text).strip(),
        "voice_description": str(voice_description).strip(),
    }
    payload["language"] = str(language).strip()
    normalized_model_parameters = _normalize_model_parameters(model_parameters)
    if normalized_model_parameters:
        payload["model_parameters"] = normalized_model_parameters
    response_payload = _post_json_endpoint(
        base_url,
        "/voice/design",
        payload,
        timeout_seconds,
    )
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid voice-design response payload.")
    return response_payload


def generate_voice_clone(
    base_url: str,
    sample_audio_bytes: bytes,
    sample_text: str,
    language: str,
    text: str,
    model_parameters: dict[str, object] | None = None,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one direct voice-clone request from a WAV sample.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  sample_audio_bytes WAV reference audio bytes uploaded for cloning.
    @param[in]  sample_text Transcript matching the reference audio sample.
    @param[in]  language Synthesis language code associated with the sample.
    @param[in]  text Speech-block text to synthesize in the cloned voice.
    @param[in]  model_parameters Optional VoiceWeaver model-parameter overrides.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by `/voice/clone`.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    headers = _build_request_headers()
    form_fields: dict[str, object] = {
        "sample_text": str(sample_text).strip(),
        "text": str(text).strip(),
    }
    form_fields["language"] = str(language).strip()
    normalized_model_parameters = _normalize_model_parameters(model_parameters)
    if normalized_model_parameters:
        form_fields["model_parameters_json"] = json.dumps(normalized_model_parameters)
    try:
        response_payload = _send_multipart_request(
            "POST",
            _endpoint_url(base_url, "/voice/clone"),
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
    sample_audio_bytes: bytes,
    sample_text: str,
    language: str,
    model_parameters: dict[str, object] | None = None,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one reusable Qwen3 voice clone-prompt creation request from a WAV sample.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  sample_audio_bytes WAV reference audio bytes uploaded for clone-prompt creation.
    @param[in]  sample_text Transcript matching the reference audio sample.
    @param[in]  language Synthesis language code associated with the sample.
    @param[in]  model_parameters Optional VoiceWeaver model-parameter overrides.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by `/voice/clone-prompt`.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    headers = _build_request_headers()
    form_fields: dict[str, object] = {
        "sample_text": str(sample_text).strip(),
    }
    form_fields["language"] = str(language).strip()
    normalized_model_parameters = _normalize_model_parameters(model_parameters)
    if normalized_model_parameters:
        form_fields["model_parameters_json"] = json.dumps(normalized_model_parameters)
    try:
        response_payload = _send_multipart_request(
            "POST",
            _endpoint_url(base_url, "/voice/clone-prompt"),
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
    voice_clone_prompt: dict[str, object] | str,
    language: str,
    text: str,
    model_parameters: dict[str, object] | None = None,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one reusable Qwen3 voice-clone generation request from one stored clone prompt.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  voice_clone_prompt Client-owned VoiceWeaver clone-prompt payload or serialized JSON string.
    @param[in]  language Synthesis language code associated with the target text.
    @param[in]  text Speech-block text to synthesize in the cloned voice.
    @param[in]  model_parameters Optional VoiceWeaver model-parameter overrides.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by `/voice/clone-from-prompt`.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    payload: dict[str, object] = {
        "voice_clone_prompt": voice_clone_prompt,
        "text": str(text).strip(),
    }
    payload["language"] = str(language).strip()
    normalized_model_parameters = _normalize_model_parameters(model_parameters)
    if normalized_model_parameters:
        payload["model_parameters"] = normalized_model_parameters
    response_payload = _post_json_endpoint(
        base_url,
        "/voice/clone-from-prompt",
        payload,
        timeout_seconds,
    )
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid prompt-clone response payload.")
    return response_payload


def generate_sound_prompt(
    base_url: str,
    prompt: str,
    negative_prompt: str = "",
    duration_seconds: float | int | None = None,
    guidance_scale: float | int | None = None,
    num_inference_steps: int | None = None,
    seed: int | None = None,
    timeout_seconds: int = config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """
    @brief      Start one VoiceWeaver prompt-based sound generation request.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  prompt Sound generation prompt.
    @param[in]  negative_prompt Optional sound generation negative prompt.
    @param[in]  duration_seconds Optional requested output duration in seconds.
    @param[in]  guidance_scale Optional model guidance scale.
    @param[in]  num_inference_steps Optional model step count.
    @param[in]  seed Optional deterministic model seed.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Runtime operation payload returned by `/sound/prompt`.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    normalized_prompt = str(prompt).strip()
    if not normalized_prompt:
        raise RuntimeError("VoiceWeaver sound generation requires a non-empty prompt.")
    payload: dict[str, object] = {"prompt": normalized_prompt}
    normalized_negative_prompt = str(negative_prompt).strip()
    if normalized_negative_prompt:
        payload["negative_prompt"] = normalized_negative_prompt
    if duration_seconds is not None:
        payload["duration_seconds"] = min(float(duration_seconds), config.MAX_SOUND_PROMPT_DURATION_SECONDS)
    if guidance_scale is not None:
        payload["guidance_scale"] = float(guidance_scale)
    if num_inference_steps is not None:
        payload["num_inference_steps"] = int(num_inference_steps)
    if seed is not None:
        payload["seed"] = int(seed)
    _VOICEWEAVER_RUNTIME_LOGGER.info(
        "Submitting sound-prompt generation request duration_seconds=%s guidance_scale=%s steps=%s seed_set=%s",
        payload.get("duration_seconds"),
        payload.get("guidance_scale"),
        payload.get("num_inference_steps"),
        seed is not None,
    )
    response_payload = _post_json_endpoint(
        base_url,
        "/sound/prompt",
        payload,
        timeout_seconds,
    )
    if not isinstance(response_payload, dict):
        raise RuntimeError("VoiceWeaver returned an invalid sound-prompt response payload.")
    _VOICEWEAVER_RUNTIME_LOGGER.info("VoiceWeaver accepted sound-prompt generation request.")
    return response_payload


def wait_for_terminal_operation(
    base_url: str,
    poll_interval_seconds: float = 0.5,
    timeout_seconds: int = config.DEFAULT_TTS_OPERATION_TIMEOUT_SECONDS,
    progress_callback=None,
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Poll `/status` until the current runtime operation reaches a terminal state.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  poll_interval_seconds Delay between status polls.
    @param[in]  timeout_seconds Maximum total polling duration.
    @param[in]  progress_callback Optional callback receiving each status payload.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     Final runtime status payload.
    @exception  RuntimeError Raised when the poll times out.
    @exception  OperationCancelledError Raised when cancellation is requested locally or reported by the runtime.
    """
    deadline = time.monotonic() + timeout_seconds
    last_status_payload: dict[str, object] | None = None
    observed_active_operation = False
    runtime_reported_cancellation = False
    while time.monotonic() <= deadline:
        try:
            raise_if_cancelled(cancel_requested)
            last_status_payload = read_status(base_url, timeout_seconds=config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS)
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
            if operation_status in {"completed", "failed"}:
                return last_status_payload
            if operation_status == "cancelled":
                runtime_reported_cancellation = True
                raise OperationCancelledError("VoiceWeaver reported the current operation as cancelled.")
            if operation_status == "idle" and observed_active_operation:
                return last_status_payload
            if operation_status != "idle":
                observed_active_operation = True
            _sleep_with_cancel(max(poll_interval_seconds, 0.05), cancel_requested)
        except OperationCancelledError:
            if not runtime_reported_cancellation:
                _cancel_last_observed_operation(base_url, last_status_payload)
            raise
    raise RuntimeError("Timed out while waiting for VoiceWeaver to finish the current operation.")


def _cancel_last_observed_operation(base_url: str, status_payload: dict[str, object] | None) -> None:
    """
    @brief      Ask VoiceWeaver to stop the last observed operation when it advertised cancellation support.
    @details    A cancellation requested before the first status poll has nothing observed yet, so the
                operation is read once here; without it the request submitted a moment earlier would
                keep running and refuse the next one as busy.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  status_payload Last normalized runtime status payload, if one was observed.
    @return     None.
    @exception  OperationCancelledError Raised when the cancel request itself reports a cancellation.
    """
    resolved_status_payload = status_payload if status_payload is not None else _read_status_for_cancellation(base_url)
    operation_payload = (
        resolved_status_payload.get("operation", {}) if isinstance(resolved_status_payload, dict) else {}
    )
    if not isinstance(operation_payload, dict) or not bool(operation_payload.get("cancellable", False)):
        return
    try:
        cancel_operation(base_url, config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS)
    except OperationCancelledError:
        raise
    except Exception as exception:  # noqa: BLE001
        _VOICEWEAVER_RUNTIME_LOGGER.warning(
            "VoiceWeaver remote cancellation failed after local cancellation: %s",
            exception,
        )


def _read_status_for_cancellation(base_url: str) -> dict[str, object] | None:
    """
    @brief      Read one runtime status while deciding whether an operation can still be cancelled remotely.
    @param[in]  base_url Operator-configured runtime base URL.
    @return     Normalized runtime status payload, or `None` when the runtime could not be read.
    @exception  None
    """
    try:
        return read_status(base_url, timeout_seconds=config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS)
    except Exception as exception:  # noqa: BLE001
        _VOICEWEAVER_RUNTIME_LOGGER.warning(
            "VoiceWeaver status could not be read while cancelling the current operation: %s",
            exception,
        )
        return None


def _sleep_with_cancel(delay_seconds: float, cancel_requested) -> None:
    """
    @brief      Sleep in short slices so UI cancellation can interrupt polling quickly.
    @param[in]  delay_seconds Total requested sleep duration.
    @param[in]  cancel_requested Optional zero-argument cancellation callback.
    @return     None.
    @exception  OperationCancelledError Raised when cancellation is requested.
    """
    deadline = time.monotonic() + max(float(delay_seconds), 0.0)
    while time.monotonic() < deadline:
        raise_if_cancelled(cancel_requested)
        time.sleep(min(0.05, max(deadline - time.monotonic(), 0.0)))
    raise_if_cancelled(cancel_requested)


def download_generated_audio(
    base_url: str,
    timeout_seconds: int = config.DEFAULT_TTS_OPERATION_TIMEOUT_SECONDS,
) -> bytes:
    """
    @brief      Download the latest generated voice or sound WAV bytes from VoiceWeaver.
    @param[in]  base_url Operator-configured runtime base URL.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Downloaded WAV bytes.
    @exception  RuntimeError Raised when the runtime request fails.
    """
    headers = _build_request_headers()
    try:
        return _read_bytes(_endpoint_url(base_url, "/audio"), headers, timeout_seconds)
    except error.HTTPError as exception:
        raise RuntimeError(_runtime_error_message(exception)) from exception
    except error.URLError as exception:
        raise RuntimeError(f"Connection failed: {getattr(exception, 'reason', exception)}.") from exception
    except TimeoutError as exception:
        raise RuntimeError("Connection failed: request timed out.") from exception


def operation_failed_message(status_payload: dict[str, object]) -> str:
    """
    @brief      Extract one operator-facing failure message from a terminal runtime status payload.
    @param[in]  status_payload Final runtime status payload.
    @return     Failure message or one fallback summary.
    @exception  None
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


def _normalize_models_payload(models_payload: object) -> list[VoiceWeaverModelPayload]:
    """
    @brief      Normalize the `/models` payload into one discovered-model list.
    @param[in]  models_payload Candidate models payload.
    @return     Normalized discovered-model list.
    @exception  ValueError Raised when the payload is invalid.
    """
    if not isinstance(models_payload, dict):
        raise ValueError("runtime returned an invalid models payload")
    model_entries = models_payload.get("models")
    if not isinstance(model_entries, list):
        raise ValueError("runtime returned an invalid models payload")
    normalized_models: list[VoiceWeaverModelPayload] = []
    for model_entry in model_entries:
        normalized_model = normalize_model(model_entry)
        if normalized_model is not None:
            normalized_models.append(normalized_model)
    return normalized_models


def _resolve_active_model_id(active_model_payload: object) -> str | None:
    """
    @brief      Resolve one active-model identifier from the `/status` payload.
    @param[in]  active_model_payload Candidate active-model payload.
    @return     Active model identifier or None.
    @exception  None
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
    runtime_version: str | None = None,
) -> VoiceWeaverProbeResult:
    """
    @brief      Build one normalized VoiceWeaver probe result payload.
    @param[in]  success True when the runtime probe succeeded.
    @param[in]  message Operator-facing probe message.
    @param[in]  discovered_models Normalized discovered-model list.
    @param[in]  active_model_id Active model identifier or None.
    @param[in]  runtime_version Runtime version reported by the probed runtime, or None.
    @return     Normalized runtime probe result dictionary.
    @exception  None
    """
    capability_matrix = build_capability_matrix(discovered_models)
    return {
        "success": success,
        "message": message,
        "discovered_models": list(discovered_models),
        "discovered_model_count": len(discovered_models),
        "active_model_id": active_model_id,
        "runtime_version": runtime_version,
        "capability_matrix": capability_matrix,
    }


def _resolve_runtime_version(*payloads: object) -> str | None:
    """
    @brief      Resolve the runtime version reported by the first payload that carries one.
    @param[in]  payloads Candidate runtime payloads in priority order.
    @return     Reported runtime version or None.
    @exception  None
    """
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        runtime_version = str(payload.get("runtime_version", "")).strip()
        if runtime_version:
            return runtime_version
    return None


def _request_json_endpoint(
    base_url: str,
    endpoint: str,
    timeout_seconds: int,
) -> dict[str, object]:
    """
    @brief      Execute the request json endpoint helper.
    @param[in]  base_url Value for `base_url`.
    @param[in]  endpoint Value for `endpoint`.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Helper result.
    """
    headers = _build_request_headers()
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
    endpoint: str,
    payload: dict[str, object] | None,
    timeout_seconds: int,
) -> object:
    """
    @brief      Execute the post json endpoint helper.
    @param[in]  base_url Value for `base_url`.
    @param[in]  endpoint Value for `endpoint`.
    @param[in]  payload Optional payload processed by the helper.
    @param[in]  timeout_seconds Request timeout in seconds.
    @return     Helper result.
    """
    headers = _build_request_headers()
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


def _runtime_error_message(http_exception: error.HTTPError) -> str:
    """
    @brief      Execute the runtime error message helper.
    @param[in]  http_exception Value for `http_exception`.
    @return     Helper result.
    """
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


def is_qwen_model(model_payload: VoiceWeaverModelPayload) -> bool:
    """
    @brief      Return whether one normalized runtime model belongs to the Qwen TTS family.
    @param[in]  model_payload Normalized discovered-model payload.
    @return     True for a declared Qwen backend or a legacy Qwen model ID without backend metadata.
    @exception  None
    """
    backend = str(model_payload.get("backend_name") or "").strip().casefold()
    if backend:
        return backend.startswith("qwen")
    return "qwen" in str(model_payload.get("model_id") or "").casefold()



# END OF FILE
