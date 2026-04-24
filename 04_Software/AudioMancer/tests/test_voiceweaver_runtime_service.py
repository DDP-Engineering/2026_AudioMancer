#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_voiceweaver_runtime_service.py
@brief Focused tests for the VoiceWeaver runtime probe service.
@details Verifies probe normalization, failure mapping, and capability-matrix
         derivation for the TTS Settings and Narrator runtime-awareness flow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.4.0
"""

# IMPORTS

from urllib import error

from audiomancer import config
from audiomancer.services import operation_runtime_service, voiceweaver_runtime_service


def test_probe_runtime_normalizes_models_and_capabilities(monkeypatch) -> None:
    """
    @brief      Verify one successful runtime probe normalizes models and capability data.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    1.1.0
    """

    def _fake_read_json(url, headers, timeout_seconds):
        assert timeout_seconds == config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS
        if url == "http://127.0.0.1:8059/v1/health":
            return {"service": "VoiceWeaver", "status": "ok"}
        if url == "http://127.0.0.1:8059/v1/models":
            return {
                "models": [
                    {
                        "model_id": "custom_model",
                        "backend_name": "qwen",
                        "status": "healthy",
                        "supported_generation_modes": ["custom_voice"],
                        "supported_languages": ["en", "ro"],
                        "supported_presets": ["vivian", "serena"],
                        "default_model_parameters": {"temperature": 0.8, "top_k": 42},
                    },
                    {
                        "model_id": "definition_model",
                        "backend_name": "qwen",
                        "status": "healthy",
                        "supported_generation_modes": ["voice_designer"],
                        "supported_presets": [],
                    },
                    {
                        "model_id": "clone_model",
                        "backend_name": "qwen",
                        "status": "healthy",
                        "supported_generation_modes": ["base"],
                        "supported_presets": [],
                    },
                ]
            }
        if url == "http://127.0.0.1:8059/v1/status":
            return {
                "active_model": {"model_id": "custom_model"},
                "device_diagnostics": {"status_message": "CUDA active.", "device_mode": "cuda"},
            }
        raise AssertionError(url)

    monkeypatch.setattr(voiceweaver_runtime_service, "_read_json", _fake_read_json)

    result = voiceweaver_runtime_service.probe_runtime("http://127.0.0.1:8059")

    assert result["success"] is True
    assert result["discovered_model_count"] == 3
    assert result["active_model_id"] == "custom_model"
    assert result["capability_matrix"]["preset_voice_available"] is True
    assert result["capability_matrix"]["generate_and_clone_available"] is True
    assert result["discovered_models"][0]["speaker_count"] == 2
    assert result["discovered_models"][0]["supported_generation_modes"] == ["custom_voice"]
    assert result["discovered_models"][1]["supported_generation_modes"] == ["definition"]
    assert result["discovered_models"][2]["supported_generation_modes"] == ["clone"]
    assert result["discovered_models"][0]["default_model_parameters"] == {"temperature": 0.8, "top_k": 42}


def test_probe_runtime_maps_auth_failures(monkeypatch) -> None:
    """
    @brief      Verify runtime auth failures are surfaced as failed probe results.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    1.1.0
    """

    def _fake_read_json(*_args, **_kwargs):
        raise error.HTTPError(url="", code=401, msg="Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr(voiceweaver_runtime_service, "_read_json", _fake_read_json)

    result = voiceweaver_runtime_service.probe_runtime("http://127.0.0.1:8059", "secret")

    assert result["success"] is False
    assert "credentials" in str(result["message"])


def test_probe_runtime_rejects_invalid_models_payload(monkeypatch) -> None:
    """
    @brief      Verify invalid runtime models payloads are surfaced as probe failures.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """

    def _fake_read_json(url, headers, timeout_seconds):
        _ = headers
        _ = timeout_seconds
        if url.endswith("/v1/health"):
            return {"status": "ok"}
        if url.endswith("/v1/models"):
            return {"models": "invalid"}
        return {"active_model": None, "device_diagnostics": {}}

    monkeypatch.setattr(voiceweaver_runtime_service, "_read_json", _fake_read_json)

    result = voiceweaver_runtime_service.probe_runtime("http://127.0.0.1:8059")

    assert result["success"] is False
    assert "invalid models payload" in str(result["message"])


def test_build_capability_matrix_ignores_unhealthy_models() -> None:
    """
    @brief      Verify unhealthy models do not count toward realizable capabilities.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-16
    @version    0.1.0
    """
    capability_matrix = voiceweaver_runtime_service.build_capability_matrix(
        [
            {
                "model_id": "custom_bad",
                "status": "unhealthy",
                "supported_generation_modes": ["custom_voice"],
                "supported_presets": ["vivian"],
            },
            {
                "model_id": "definition_good",
                "status": "healthy",
                "supported_generation_modes": ["definition"],
                "supported_presets": [],
            },
            {
                "model_id": "clone_good",
                "status": "healthy",
                "supported_generation_modes": ["clone"],
                "supported_presets": [],
            },
        ]
    )

    assert capability_matrix["preset_voice_available"] is False
    assert capability_matrix["generate_and_clone_available"] is True


def test_voiceweaver_runtime_service_generation_payloads_use_current_contract(monkeypatch) -> None:
    """
    @brief      Verify runtime generation helpers send language codes and optional model parameters using the current
                REST contract.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    observed_calls: list[tuple[str, str, dict[str, object] | None, int]] = []

    def _fake_post_json_endpoint(base_url, runtime_api_key, endpoint, payload, timeout_seconds):
        observed_calls.append((str(base_url), str(endpoint), payload, int(timeout_seconds)))
        _ = runtime_api_key
        return {"status": "completed"}

    monkeypatch.setattr(voiceweaver_runtime_service, "_post_json_endpoint", _fake_post_json_endpoint)

    voiceweaver_runtime_service.generate_custom_voice(
        "http://127.0.0.1:8059",
        "",
        "vivian",
        "en",
        "Hello",
        "Speak warmly.",
        {"temperature": 0.8},
        timeout_seconds=45,
    )
    voiceweaver_runtime_service.generate_voice_design(
        "http://127.0.0.1:8059",
        "",
        "ro",
        "Salut",
        "Warm narrator.",
        {"top_k": 33},
        timeout_seconds=90,
    )

    assert observed_calls == [
        (
            "http://127.0.0.1:8059",
            "/v1/voice/custom",
            {
                "speaker": "vivian",
                "language": "en",
                "text": "Hello",
                "instruct": "Speak warmly.",
                "model_parameters": {"temperature": 0.8},
            },
            45,
        ),
        (
            "http://127.0.0.1:8059",
            "/v1/voice/design",
            {
                "language": "ro",
                "text": "Salut",
                "voice_description": "Warm narrator.",
                "model_parameters": {"top_k": 33},
            },
            90,
        ),
    ]


def test_voiceweaver_runtime_service_clone_prompt_wrappers_use_documented_contract(monkeypatch) -> None:
    """
    @brief      Verify reusable clone-prompt helpers target the documented VoiceWeaver REST payloads.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    observed_multipart_calls: list[tuple[str, str, dict[str, object], str, str, bytes, int]] = []
    observed_json_calls: list[tuple[str, str, dict[str, object], int]] = []

    def _fake_send_multipart_request(
        method,
        url,
        headers,
        timeout_seconds,
        form_fields,
        file_field_name,
        file_name,
        file_bytes,
        file_content_type="audio/wav",
    ):
        observed_multipart_calls.append(
            (
                str(method),
                str(url),
                dict(form_fields),
                str(file_field_name),
                str(file_name),
                bytes(file_bytes),
                int(timeout_seconds),
            )
        )
        assert headers["Accept"] == "application/json"
        assert file_content_type == "audio/wav"
        return {"status": "running"}

    def _fake_post_json_endpoint(base_url, runtime_api_key, endpoint, payload, timeout_seconds):
        _ = runtime_api_key
        observed_json_calls.append((str(base_url), str(endpoint), dict(payload or {}), int(timeout_seconds)))
        return {"status": "running"}

    monkeypatch.setattr(voiceweaver_runtime_service, "_send_multipart_request", _fake_send_multipart_request)
    monkeypatch.setattr(voiceweaver_runtime_service, "_post_json_endpoint", _fake_post_json_endpoint)

    voiceweaver_runtime_service.create_voice_clone_prompt(
        "http://127.0.0.1:8059",
        "",
        b"sample-bytes",
        "Reference transcript.",
        "en",
        {"temperature": 0.8},
        timeout_seconds=33,
    )
    voiceweaver_runtime_service.generate_voice_clone_from_prompt(
        "http://127.0.0.1:8059",
        "",
        {"format": "qwen_voice_clone_prompt_v1", "prompt": {"ref_code": {"data": "..."}}},
        "ro",
        "Salut.",
        {"top_k": 22},
        timeout_seconds=44,
    )

    assert observed_multipart_calls == [
        (
            "POST",
            "http://127.0.0.1:8059/v1/voice/clone-prompt",
            {
                "sample_text": "Reference transcript.",
                "language": "en",
                "model_parameters_json": '{"temperature": 0.8}',
            },
            "voice_sample",
            "reference.wav",
            b"sample-bytes",
            33,
        )
    ]
    assert observed_json_calls == [
        (
            "http://127.0.0.1:8059",
            "/v1/voice/clone-from-prompt",
            {
                "voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "prompt": {"ref_code": {"data": "..."}}},
                "language": "ro",
                "text": "Salut.",
                "model_parameters": {"top_k": 22},
            },
            44,
        )
    ]


def test_voiceweaver_runtime_service_endpoint_wrappers_cover_extended_rest_surface(monkeypatch) -> None:
    """
    @brief      Verify VoiceWeaver endpoint wrappers target the updated REST paths for server, catalog, unload,
                rescan, download, and delete.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.0.0
    """
    observed_json_requests: list[tuple[str, str, str, int]] = []
    observed_no_content_requests: list[tuple[str, str, str, int]] = []

    def _fake_request_json_endpoint(base_url, runtime_api_key, endpoint, timeout_seconds):
        observed_json_requests.append((str(base_url), str(runtime_api_key), str(endpoint), int(timeout_seconds)))
        return {"endpoint": endpoint}

    def _fake_post_json_endpoint(base_url, runtime_api_key, endpoint, payload, timeout_seconds):
        observed_json_requests.append((str(base_url), str(runtime_api_key), str(endpoint), int(timeout_seconds)))
        _ = payload
        if endpoint == "/v1/models/unload":
            return None
        return {"endpoint": endpoint}

    def _fake_request_without_json_response(base_url, runtime_api_key, endpoint, method, timeout_seconds):
        observed_no_content_requests.append(
            (str(base_url), str(runtime_api_key), f"{method} {endpoint}", int(timeout_seconds))
        )

    monkeypatch.setattr(voiceweaver_runtime_service, "_request_json_endpoint", _fake_request_json_endpoint)
    monkeypatch.setattr(voiceweaver_runtime_service, "_post_json_endpoint", _fake_post_json_endpoint)
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "_request_without_json_response",
        _fake_request_without_json_response,
    )

    assert voiceweaver_runtime_service.read_server_info("http://runtime", "key", 10) == {"endpoint": "/v1/server"}
    assert voiceweaver_runtime_service.read_model_catalog("http://runtime", "key", 11) == {
        "endpoint": "/v1/model-catalog"
    }
    assert voiceweaver_runtime_service.unload_model("http://runtime", "key", 12) is None
    assert voiceweaver_runtime_service.rescan_models("http://runtime", "key", 13) == {"endpoint": "/v1/models/rescan"}
    assert voiceweaver_runtime_service.start_model_download("http://runtime", "key", "Qwen3", 14) == {
        "endpoint": "/v1/models/download"
    }
    assert voiceweaver_runtime_service.read_model_download_status("http://runtime", "key", 15) == {
        "endpoint": "/v1/models/download/status"
    }
    voiceweaver_runtime_service.delete_model("http://runtime", "key", "Qwen 3/TTS", 16)
    voiceweaver_runtime_service.cancel_model_download("http://runtime", "key", 17)

    assert observed_json_requests == [
        ("http://runtime", "key", "/v1/server", 10),
        ("http://runtime", "key", "/v1/model-catalog", 11),
        ("http://runtime", "key", "/v1/models/unload", 12),
        ("http://runtime", "key", "/v1/models/rescan", 13),
        ("http://runtime", "key", "/v1/models/download", 14),
        ("http://runtime", "key", "/v1/models/download/status", 15),
    ]
    assert observed_no_content_requests == [
        ("http://runtime", "key", "DELETE /v1/models/Qwen%203%2FTTS", 16),
        ("http://runtime", "key", "POST /v1/models/download/cancel", 17),
    ]


def test_endpoint_url_avoids_duplicate_v1_suffix() -> None:
    """
    @brief      Verify VoiceWeaver endpoint normalization avoids duplicate `/v1` path segments.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    assert (
        voiceweaver_runtime_service._endpoint_url("http://127.0.0.1:8059/v1", "/v1/status")  # noqa: SLF001
        == "http://127.0.0.1:8059/v1/status"
    )


def test_wait_for_terminal_operation_stops_before_status_read_when_cancelled(monkeypatch) -> None:
    """
    @brief      Verify VoiceWeaver polling raises immediately when cancellation is already requested.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    status_reads = {"count": 0}

    def _fake_read_status(*_args, **_kwargs):
        status_reads["count"] = int(status_reads["count"]) + 1
        return {"operation": {"status": "running"}}

    monkeypatch.setattr(voiceweaver_runtime_service, "read_status", _fake_read_status)

    try:
        voiceweaver_runtime_service.wait_for_terminal_operation(
            "http://127.0.0.1:8059",
            cancel_requested=lambda: True,
        )
    except operation_runtime_service.OperationCancelledError:
        pass
    else:
        raise AssertionError("Expected runtime polling to raise OperationCancelledError.")

    assert status_reads["count"] == 0


# END OF FILE
