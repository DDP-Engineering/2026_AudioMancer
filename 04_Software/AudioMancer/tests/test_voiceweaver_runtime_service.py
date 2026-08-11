#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
"""

# IMPORTS

import copy
from urllib import error

import pytest

from audiomancer import config
from audiomancer.services import operation_runtime_service, voiceweaver_runtime_service


def test_probe_runtime_normalizes_models_and_capabilities(monkeypatch) -> None:
    """
    @brief      Verify one successful runtime probe normalizes models and capability data.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_read_json(url, headers, timeout_seconds):
        """
        @brief      Provide the fake read json test helper.
        @return     None.
        @exception  None
        """
        assert timeout_seconds == config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS
        if url == "http://127.0.0.1:8059/v1/health":
            return {"service": "VoiceWeaver", "status": "ok"}
        if url == "http://127.0.0.1:8059/v1/models":
            return {
                "models": [
                    {
                        "model_id": "definition_model",
                        "backend_name": "qwen",
                        "status": "healthy",
                        "supported_generation_modes": ["voice_designer"],
                        "supported_languages": ["en", "ro"],
                        "default_model_parameters": {"temperature": 0.8, "top_k": 42},
                    },
                    {
                        "model_id": "clone_model",
                        "backend_name": "qwen",
                        "status": "healthy",
                        "supported_generation_modes": ["base"],
                    },
                ]
            }
        if url == "http://127.0.0.1:8059/v1/status":
            return {
                "active_model": {"model_id": "definition_model"},
                "device_diagnostics": {"status_message": "CUDA active.", "device_mode": "cuda"},
            }
        raise AssertionError(url)

    monkeypatch.setattr(voiceweaver_runtime_service, "_read_json", _fake_read_json)

    result = voiceweaver_runtime_service.probe_runtime("http://127.0.0.1:8059")

    assert result["success"] is True
    assert result["discovered_model_count"] == 2
    assert result["active_model_id"] == "definition_model"
    assert result["capability_matrix"]["preset_voice_available"] is False
    assert result["capability_matrix"]["generate_and_clone_available"] is True
    assert result["discovered_models"][0]["supported_generation_modes"] == ["definition"]
    assert result["discovered_models"][1]["supported_generation_modes"] == ["clone"]
    assert result["discovered_models"][0]["default_model_parameters"] == {"temperature": 0.8, "top_k": 42}


def test_read_status_filters_non_scalar_effective_parameters_without_mutating_input(monkeypatch) -> None:
    """
    @brief      Verify runtime status keeps only scalar model parameters without input mutation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    status_payload = {
        "active_model": {
            "model_id": "qwen-base",
            "effective_model_parameters": {
                "max_new_tokens": 2048,
                "nested": {"drop": True},
                "sequence": [1, 2],
            },
            "default_model_parameters": {
                "temperature": 0.8,
                "nested": {"drop": True},
            },
        },
        "effective_model_parameters": {
            "max_new_tokens": 2048,
            "nested": {"drop": True},
        },
    }
    original_payload = copy.deepcopy(status_payload)
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "_request_json_endpoint",
        lambda *_args, **_kwargs: status_payload,
    )

    normalized_status = voiceweaver_runtime_service.read_status("http://runtime")

    assert normalized_status["active_model"]["effective_model_parameters"] == {"max_new_tokens": 2048}
    assert normalized_status["active_model"]["default_model_parameters"] == {"temperature": 0.8}
    assert normalized_status["effective_model_parameters"] == {"max_new_tokens": 2048}
    assert status_payload == original_payload


def test_probe_runtime_maps_auth_failures(monkeypatch) -> None:
    """
    @brief      Verify runtime auth failures are surfaced as failed probe results.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _fake_read_json(*_args, **_kwargs):
        """
        @brief      Provide the fake read json test helper.
        @return     None.
        @exception  None
        """
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
    """

    def _fake_read_json(url, headers, timeout_seconds):
        """
        @brief      Provide the fake read json test helper.
        @return     None.
        @exception  None
        """
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
    """
    capability_matrix = voiceweaver_runtime_service.build_capability_matrix(
        [
            {
                "model_id": "custom_bad",
                "status": "unhealthy",
                "supported_generation_modes": ["definition"],
            },
            {
                "model_id": "definition_good",
                "status": "healthy",
                "supported_generation_modes": ["definition"],
            },
            {
                "model_id": "clone_good",
                "status": "healthy",
                "supported_generation_modes": ["clone"],
            },
            {
                "model_id": "sound_good",
                "status": "healthy",
                "supported_generation_modes": ["sound_prompt"],
            },
        ]
    )

    assert capability_matrix["preset_voice_available"] is False
    assert capability_matrix["generate_and_clone_available"] is True
    assert capability_matrix["sound_prompt_available"] is True
    assert [model["model_id"] for model in capability_matrix["sound_prompt_models"]] == ["sound_good"]
    assert {"definition_models", "clone_models"}.isdisjoint(capability_matrix)


def test_voiceweaver_runtime_service_generation_payloads_use_current_contract(monkeypatch) -> None:
    """
    @brief      Verify runtime generation helpers send explicit language fields only when required by the current
                REST contract.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_calls: list[tuple[str, str, dict[str, object] | None, int]] = []

    def _fake_post_json_endpoint(base_url, runtime_api_key, endpoint, payload, timeout_seconds):
        """
        @brief      Provide the fake post json endpoint test helper.
        @return     None.
        @exception  None
        """
        observed_calls.append((str(base_url), str(endpoint), payload, int(timeout_seconds)))
        _ = runtime_api_key
        return {"status": "completed"}

    monkeypatch.setattr(voiceweaver_runtime_service, "_post_json_endpoint", _fake_post_json_endpoint)

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
            "/v1/voice/design",
            {
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
        """
        @brief      Provide the fake send multipart request test helper.
        @return     None.
        @exception  None
        """
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
        """
        @brief      Provide the fake post json endpoint test helper.
        @return     None.
        @exception  None
        """
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
                "text": "Salut.",
                "model_parameters": {"top_k": 22},
            },
            44,
        )
    ]


def test_voiceweaver_runtime_service_sound_prompt_wrappers_use_documented_contract(monkeypatch) -> None:
    """
    @brief      Verify sound prompt helpers target the documented VoiceWeaver REST payloads.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_json_calls: list[tuple[str, str, dict[str, object], int]] = []
    observed_byte_urls: list[str] = []

    def _fake_post_json_endpoint(base_url, runtime_api_key, endpoint, payload, timeout_seconds):
        """
        @brief      Provide the fake post json endpoint test helper.
        @return     None.
        @exception  None
        """
        _ = runtime_api_key
        observed_json_calls.append((str(base_url), str(endpoint), dict(payload or {}), int(timeout_seconds)))
        return {"status": "running"}

    def _fake_read_bytes(url, headers, timeout_seconds):
        """
        @brief      Provide the fake read bytes test helper.
        @return     Fake WAV bytes.
        @exception  None
        """
        _ = headers
        _ = timeout_seconds
        observed_byte_urls.append(str(url))
        return b"RIFF....WAVE"

    monkeypatch.setattr(voiceweaver_runtime_service, "_post_json_endpoint", _fake_post_json_endpoint)
    monkeypatch.setattr(voiceweaver_runtime_service, "_read_bytes", _fake_read_bytes)

    voiceweaver_runtime_service.generate_sound_prompt(
        "http://127.0.0.1:8059",
        "",
        "Rain in trenches",
        negative_prompt="speech",
        duration_seconds=5,
        guidance_scale=7,
        num_inference_steps=50,
        seed=123,
        timeout_seconds=66,
    )
    audio_bytes = voiceweaver_runtime_service.download_generated_audio("http://127.0.0.1:8059")

    assert observed_json_calls == [
        (
            "http://127.0.0.1:8059",
            "/v1/sound/prompt",
            {
                "prompt": "Rain in trenches",
                "negative_prompt": "speech",
                "duration_seconds": 5.0,
                "guidance_scale": 7.0,
                "num_inference_steps": 50,
                "seed": 123,
            },
            66,
        )
    ]
    assert observed_byte_urls == ["http://127.0.0.1:8059/v1/audio"]
    assert audio_bytes == b"RIFF....WAVE"


@pytest.mark.parametrize(
    ("download_helper", "endpoint"),
    [
        (voiceweaver_runtime_service.download_generated_voice, "/v1/voice"),
        (voiceweaver_runtime_service.download_generated_audio, "/v1/audio"),
    ],
)
def test_generated_wav_downloads_translate_direct_timeouts(
    monkeypatch,
    download_helper,
    endpoint,
) -> None:
    """
    @brief      Verify both generated-WAV downloads translate and chain direct timeouts.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  download_helper Generated-WAV download function under test.
    @param[in]  endpoint Expected VoiceWeaver endpoint suffix.
    @return     None.
    @exception  None
    """
    timeout = TimeoutError("socket read stalled")

    class _TimedOutResponse:
        """
        @brief      Provide a response whose body read raises the direct timeout.
        @exception  None
        """

        def __enter__(self):
            """@brief Return the fake opened response."""
            return self

        def __exit__(self, *_args):
            """@brief Leave the fake response context without suppressing failures."""
            return False

        def read(self):
            """
            @brief      Raise the simulated socket timeout during response reading.
            @exception  TimeoutError Always raised for this regression seam.
            """
            raise timeout

    def _fake_urlopen(http_request, timeout):
        """
        @brief      Verify request construction and return the timed-out response.
        @return     Fake response context manager.
        """
        assert http_request.full_url == f"http://127.0.0.1:8059{endpoint}"
        assert http_request.get_header("Authorization") == "Bearer secret"
        assert timeout == 37
        return _TimedOutResponse()

    monkeypatch.setattr(voiceweaver_runtime_service.request, "urlopen", _fake_urlopen)

    with pytest.raises(RuntimeError) as error_info:
        download_helper(
            "http://127.0.0.1:8059",
            runtime_api_key="secret",
            timeout_seconds=37,
        )

    assert str(error_info.value) == "Connection failed: request timed out."
    assert error_info.value.__cause__ is timeout


@pytest.mark.parametrize(
    ("download_helper", "endpoint"),
    [
        (voiceweaver_runtime_service.download_generated_voice, "/v1/voice"),
        (voiceweaver_runtime_service.download_generated_audio, "/v1/audio"),
    ],
)
def test_generated_wav_downloads_preserve_success_http_and_url_contracts(
    monkeypatch,
    download_helper,
    endpoint,
) -> None:
    """
    @brief      Verify timeout work does not alter successful, HTTP, or URL download behavior.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  download_helper Generated-WAV download function under test.
    @param[in]  endpoint Expected VoiceWeaver endpoint suffix.
    @return     None.
    @exception  None
    """

    def _return_wav(url, headers, timeout_seconds):
        """
        @brief      Return stable WAV bytes after verifying forwarded request values.
        @return     Fake WAV bytes.
        """
        assert url == f"http://127.0.0.1:8059{endpoint}"
        assert headers == {"Accept": "application/json"}
        assert timeout_seconds == 41
        return b"RIFF....WAVE"

    monkeypatch.setattr(voiceweaver_runtime_service, "_read_bytes", _return_wav)
    assert download_helper("http://127.0.0.1:8059", timeout_seconds=41) == b"RIFF....WAVE"

    http_failure = error.HTTPError(url="", code=401, msg="Unauthorized", hdrs=None, fp=None)
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "_read_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(http_failure),
    )
    with pytest.raises(RuntimeError) as http_error_info:
        download_helper("http://127.0.0.1:8059")
    assert str(http_error_info.value) == "Connection failed: invalid or missing runtime credentials."
    assert http_error_info.value.__cause__ is http_failure

    url_failure = error.URLError(TimeoutError("wrapped timeout"))
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "_read_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(url_failure),
    )
    with pytest.raises(RuntimeError) as url_error_info:
        download_helper("http://127.0.0.1:8059")
    assert str(url_error_info.value) == "Connection failed: wrapped timeout."
    assert url_error_info.value.__cause__ is url_failure


def test_voiceweaver_runtime_service_direct_clone_omits_romanian_language(monkeypatch) -> None:
    """
    @brief      Verify direct clone requests omit the VoiceWeaver language field for Romanian synthesis.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_form_fields: list[dict[str, object]] = []

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
        """
        @brief      Provide the fake send multipart request test helper.
        @return     None.
        @exception  None
        """
        _ = method
        _ = url
        _ = headers
        _ = timeout_seconds
        _ = file_field_name
        _ = file_name
        _ = file_bytes
        _ = file_content_type
        observed_form_fields.append(dict(form_fields))
        return {"status": "running"}

    monkeypatch.setattr(voiceweaver_runtime_service, "_send_multipart_request", _fake_send_multipart_request)

    voiceweaver_runtime_service.generate_voice_clone(
        "http://127.0.0.1:8059",
        "",
        b"sample-bytes",
        "Text de referinta.",
        "ro",
        "Salut.",
        timeout_seconds=44,
    )

    assert observed_form_fields == [{"sample_text": "Text de referinta.", "text": "Salut."}]


def test_voiceweaver_runtime_service_endpoint_wrappers_cover_extended_rest_surface(monkeypatch) -> None:
    """
    @brief      Verify VoiceWeaver endpoint wrappers target the updated REST paths for server, catalog, unload,
                rescan, download, and delete.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_json_requests: list[tuple[str, str, str, int]] = []
    observed_no_content_requests: list[tuple[str, str, str, int]] = []

    def _fake_request_json_endpoint(base_url, runtime_api_key, endpoint, timeout_seconds):
        """
        @brief      Provide the fake request json endpoint test helper.
        @return     None.
        @exception  None
        """
        observed_json_requests.append((str(base_url), str(runtime_api_key), str(endpoint), int(timeout_seconds)))
        return {"endpoint": endpoint}

    def _fake_post_json_endpoint(base_url, runtime_api_key, endpoint, payload, timeout_seconds):
        """
        @brief      Provide the fake post json endpoint test helper.
        @return     None.
        @exception  None
        """
        observed_json_requests.append((str(base_url), str(runtime_api_key), str(endpoint), int(timeout_seconds)))
        _ = payload
        if endpoint == "/v1/models/unload":
            return None
        return {"endpoint": endpoint}

    def _fake_request_without_json_response(base_url, runtime_api_key, endpoint, method, timeout_seconds):
        """
        @brief      Provide the fake request without json response test helper.
        @return     None.
        @exception  None
        """
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
    """
    status_reads = {"count": 0}

    def _fake_read_status(*_args, **_kwargs):
        """
        @brief      Provide the fake read status test helper.
        @return     None.
        @exception  None
        """
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


def test_wait_for_terminal_operation_ignores_idle_before_running(monkeypatch) -> None:
    """Verify registration-lag idle status does not become a false terminal failure."""
    statuses = iter(("idle", "running", "completed"))
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"operation": {"status": next(statuses)}},
    )
    monkeypatch.setattr(voiceweaver_runtime_service, "_sleep_with_cancel", lambda *_args: None)

    result = voiceweaver_runtime_service.wait_for_terminal_operation(
        "http://127.0.0.1:8059", poll_interval_seconds=0.0, timeout_seconds=1.0
    )

    assert result["operation"]["status"] == "completed"


# END OF FILE
