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
        assert headers["Accept"] == "application/json"
        if url == "http://127.0.0.1:8059/models":
            return {
                "models": [
                    {
                        "model_id": "voice_design_model",
                        "backend_name": "qwen",
                        "status": "healthy",
                        "supported_generation_modes": ["voice_design"],
                        "supported_languages": ["en", "fr", "de", "it", "es", "pt", "ru"],
                        "default_model_parameters": {"temperature": 0.8, "top_k": 42},
                    },
                    {
                        "model_id": "clone_model",
                        "backend_name": "qwen",
                        "status": "healthy",
                        "supported_generation_modes": ["clone"],
                    },
                ]
            }
        if url == "http://127.0.0.1:8059/status":
            return {
                "active_model": {"model_id": "voice_design_model"},
            }
        raise AssertionError(url)

    monkeypatch.setattr(voiceweaver_runtime_service, "_read_json", _fake_read_json)

    result = voiceweaver_runtime_service.probe_runtime("http://127.0.0.1:8059")

    assert result["success"] is True
    assert result["discovered_model_count"] == 2
    assert result["active_model_id"] == "voice_design_model"
    assert result["capability_matrix"]["generate_and_clone_available"] is True
    assert result["discovered_models"][0]["supported_generation_modes"] == ["voice_design"]
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


def test_probe_runtime_maps_http_failures(monkeypatch) -> None:
    """
    @brief      Verify runtime HTTP failures are surfaced as failed probe results.
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
        raise error.HTTPError(url="", code=500, msg="Server Error", hdrs=None, fp=None)

    monkeypatch.setattr(voiceweaver_runtime_service, "_read_json", _fake_read_json)

    result = voiceweaver_runtime_service.probe_runtime("http://127.0.0.1:8059")

    assert result["success"] is False
    assert result["message"] == "Connection failed: HTTP 500."


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
        if url.endswith("/models"):
            return {"models": "invalid"}
        return {"active_model": None}

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
                "supported_generation_modes": ["voice_design"],
            },
            {
                "model_id": "definition_good",
                "status": "healthy",
                "supported_generation_modes": ["voice_design"],
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

    assert capability_matrix["generate_and_clone_available"] is True
    assert capability_matrix["sound_prompt_available"] is True
    assert [model["model_id"] for model in capability_matrix["sound_prompt_models"]] == ["sound_good"]
    assert [model["model_id"] for model in capability_matrix["voice_design_models"]] == ["definition_good"]
    assert [model["model_id"] for model in capability_matrix["clone_models"]] == ["clone_good"]


def test_voiceweaver_runtime_service_generation_payloads_use_current_contract(monkeypatch) -> None:
    """
    @brief      Verify voice-design generation sends the exact simplified REST request and omits unoffered languages.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_calls: list[tuple[str, str, dict[str, object] | None, int]] = []

    def _fake_post_json_endpoint(base_url, endpoint, payload, timeout_seconds):
        """
        @brief      Provide the fake post json endpoint test helper.
        @return     None.
        @exception  None
        """
        observed_calls.append((str(base_url), str(endpoint), payload, int(timeout_seconds)))
        return {"status": "completed"}

    monkeypatch.setattr(voiceweaver_runtime_service, "_post_json_endpoint", _fake_post_json_endpoint)

    voiceweaver_runtime_service.generate_voice_design(
        "http://127.0.0.1:8059",
        "en",
        "Hello",
        "Warm narrator.",
        {"top_k": 33},
        timeout_seconds=90,
    )
    voiceweaver_runtime_service.generate_voice_design(
        "http://127.0.0.1:8059",
        "ro",
        "Salut",
        "Warm narrator.",
        {"top_k": 33},
        timeout_seconds=90,
    )
    voiceweaver_runtime_service.generate_voice_design(
        "http://127.0.0.1:8059",
        "de",
        "Hallo",
        "Warm narrator.",
        {"top_k": 33},
        supported_languages=["en", "fr"],
        timeout_seconds=90,
    )

    assert observed_calls == [
        (
            "http://127.0.0.1:8059",
            "/voice/design",
            {
                "text": "Hello",
                "language": "en",
                "voice_description": "Warm narrator.",
                "model_parameters": {"top_k": 33},
            },
            90,
        ),
        (
            "http://127.0.0.1:8059",
            "/voice/design",
            {
                "text": "Salut",
                "voice_description": "Warm narrator.",
                "model_parameters": {"top_k": 33},
            },
            90,
        ),
        (
            "http://127.0.0.1:8059",
            "/voice/design",
            {
                "text": "Hallo",
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

    def _fake_post_json_endpoint(base_url, endpoint, payload, timeout_seconds):
        """
        @brief      Provide the fake post json endpoint test helper.
        @return     None.
        @exception  None
        """
        observed_json_calls.append((str(base_url), str(endpoint), dict(payload or {}), int(timeout_seconds)))
        return {"status": "running"}

    monkeypatch.setattr(voiceweaver_runtime_service, "_send_multipart_request", _fake_send_multipart_request)
    monkeypatch.setattr(voiceweaver_runtime_service, "_post_json_endpoint", _fake_post_json_endpoint)

    voiceweaver_runtime_service.create_voice_clone_prompt(
        "http://127.0.0.1:8059",
        b"sample-bytes",
        "Reference transcript.",
        "en",
        {"temperature": 0.8},
        timeout_seconds=33,
    )
    voiceweaver_runtime_service.generate_voice_clone_from_prompt(
        "http://127.0.0.1:8059",
        {"format": "qwen_voice_clone_prompt_v1", "prompt": {"ref_code": {"data": "..."}}},
        "ro",
        "Salut.",
        {"top_k": 22},
        timeout_seconds=44,
    )

    assert observed_multipart_calls == [
        (
            "POST",
            "http://127.0.0.1:8059/voice/clone-prompt",
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
            "/voice/clone-from-prompt",
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

    def _fake_post_json_endpoint(base_url, endpoint, payload, timeout_seconds):
        """
        @brief      Provide the fake post json endpoint test helper.
        @return     None.
        @exception  None
        """
        observed_json_calls.append((str(base_url), str(endpoint), dict(payload or {}), int(timeout_seconds)))
        return {"status": "running"}

    monkeypatch.setattr(voiceweaver_runtime_service, "_post_json_endpoint", _fake_post_json_endpoint)

    voiceweaver_runtime_service.generate_sound_prompt(
        "http://127.0.0.1:8059",
        "Rain in trenches",
        negative_prompt="speech",
        duration_seconds=5,
        guidance_scale=7,
        num_inference_steps=50,
        seed=123,
        timeout_seconds=66,
    )

    assert observed_json_calls == [
        (
            "http://127.0.0.1:8059",
            "/sound/prompt",
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


def test_generated_wav_downloads_translate_direct_timeouts(monkeypatch) -> None:
    """
    @brief      Verify the generated-audio download translates and chains direct timeouts.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
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
        assert http_request.full_url == "http://127.0.0.1:8059/audio"
        assert timeout == 37
        return _TimedOutResponse()

    monkeypatch.setattr(voiceweaver_runtime_service.request, "urlopen", _fake_urlopen)

    with pytest.raises(RuntimeError) as error_info:
        voiceweaver_runtime_service.download_generated_audio("http://127.0.0.1:8059", timeout_seconds=37)

    assert str(error_info.value) == "Connection failed: request timed out."
    assert error_info.value.__cause__ is timeout


def test_generated_wav_downloads_preserve_success_http_and_url_contracts(monkeypatch) -> None:
    """
    @brief      Verify timeout work does not alter successful, HTTP, or URL download behavior.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """

    def _return_wav(url, headers, timeout_seconds):
        """
        @brief      Return stable WAV bytes after verifying forwarded request values.
        @return     Fake WAV bytes.
        """
        assert url == "http://127.0.0.1:8059/audio"
        assert headers == {"Accept": "application/json"}
        assert timeout_seconds == 41
        return b"RIFF....WAVE"

    monkeypatch.setattr(voiceweaver_runtime_service, "_read_bytes", _return_wav)
    assert voiceweaver_runtime_service.download_generated_audio(
        "http://127.0.0.1:8059", timeout_seconds=41
    ) == b"RIFF....WAVE"

    http_failure = error.HTTPError(url="", code=401, msg="Unauthorized", hdrs=None, fp=None)
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "_read_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(http_failure),
    )
    with pytest.raises(RuntimeError) as http_error_info:
        voiceweaver_runtime_service.download_generated_audio("http://127.0.0.1:8059")
    assert str(http_error_info.value) == "Connection failed: HTTP 401."
    assert http_error_info.value.__cause__ is http_failure

    url_failure = error.URLError(TimeoutError("wrapped timeout"))
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "_read_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(url_failure),
    )
    with pytest.raises(RuntimeError) as url_error_info:
        voiceweaver_runtime_service.download_generated_audio("http://127.0.0.1:8059")
    assert str(url_error_info.value) == "Connection failed: wrapped timeout."
    assert url_error_info.value.__cause__ is url_failure


def test_voiceweaver_runtime_service_direct_clone_omits_unoffered_language(monkeypatch) -> None:
    """
    @brief      Verify direct clone requests send an offered language and omit an unoffered one.
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
        b"sample-bytes",
        "Reference transcript.",
        "fr",
        "Bonjour.",
        timeout_seconds=44,
    )
    voiceweaver_runtime_service.generate_voice_clone(
        "http://127.0.0.1:8059",
        b"sample-bytes",
        "Text de referinta.",
        "ro",
        "Salut.",
        timeout_seconds=44,
    )

    assert observed_form_fields == [
        {"sample_text": "Reference transcript.", "language": "fr", "text": "Bonjour."},
        {"sample_text": "Text de referinta.", "text": "Salut."},
    ]


def test_voiceweaver_runtime_service_uses_simplified_status_and_model_routes(monkeypatch) -> None:
    """
    @brief      Verify model-management helpers use the simplified VoiceWeaver routes.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_requests: list[tuple[str, str, object, int]] = []

    def _fake_request_json_endpoint(base_url, endpoint, timeout_seconds):
        """
        @brief      Provide the fake request json endpoint test helper.
        @return     None.
        @exception  None
        """
        observed_requests.append((str(base_url), str(endpoint), None, int(timeout_seconds)))
        return {"endpoint": endpoint}

    def _fake_post_json_endpoint(base_url, endpoint, payload, timeout_seconds):
        """
        @brief      Provide the fake post json endpoint test helper.
        @return     None.
        @exception  None
        """
        observed_requests.append((str(base_url), str(endpoint), payload, int(timeout_seconds)))
        if endpoint == "/models/unload":
            return None
        return {"endpoint": endpoint}

    monkeypatch.setattr(voiceweaver_runtime_service, "_request_json_endpoint", _fake_request_json_endpoint)
    monkeypatch.setattr(voiceweaver_runtime_service, "_post_json_endpoint", _fake_post_json_endpoint)

    assert voiceweaver_runtime_service.read_status("http://runtime", 10) == {
        "endpoint": "/status",
        "active_model": None,
    }
    assert voiceweaver_runtime_service.load_model("http://runtime", "Qwen3", 11) == {"endpoint": "/models/load"}
    assert voiceweaver_runtime_service.unload_model("http://runtime", 12) is None
    assert voiceweaver_runtime_service.cancel_operation("http://runtime", 13) == {"endpoint": "/cancel"}

    assert observed_requests == [
        ("http://runtime", "/status", None, 10),
        ("http://runtime", "/models/load", {"model_id": "Qwen3", "device_mode": "auto"}, 11),
        ("http://runtime", "/models/unload", None, 12),
        ("http://runtime", "/cancel", None, 13),
    ]


def test_wait_for_terminal_operation_cancels_remotely_when_cancelled_before_the_first_poll(monkeypatch) -> None:
    """
    @brief      Verify a cancellation that beats the first status poll still stops the runtime operation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    status_reads = {"count": 0}
    observed_cancel_calls: list[tuple[str, int]] = []

    def _fake_read_status(*_args, **_kwargs):
        """
        @brief      Provide the fake read status test helper.
        @return     None.
        @exception  None
        """
        status_reads["count"] = int(status_reads["count"]) + 1
        return {"operation": {"status": "running", "cancellable": True}}

    monkeypatch.setattr(voiceweaver_runtime_service, "read_status", _fake_read_status)
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "cancel_operation",
        lambda base_url, timeout_seconds: observed_cancel_calls.append((base_url, timeout_seconds)),
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        voiceweaver_runtime_service.wait_for_terminal_operation(
            "http://127.0.0.1:8059",
            cancel_requested=lambda: True,
        )

    assert status_reads["count"] == 1
    assert observed_cancel_calls == [("http://127.0.0.1:8059", config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS)]


def test_wait_for_terminal_operation_raises_cancellation_for_runtime_reported_cancel(monkeypatch) -> None:
    """
    @brief      Verify a terminal runtime-reported cancel ends the wait as a cancellation, not a payload.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_cancel_calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {
            "operation": {"status": "cancelled", "cancellable": True, "stage": "Cancellation requested."},
        },
    )
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "cancel_operation",
        lambda base_url, timeout_seconds: observed_cancel_calls.append((base_url, timeout_seconds)),
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        voiceweaver_runtime_service.wait_for_terminal_operation(
            "http://runtime",
            timeout_seconds=90,
        )

    assert observed_cancel_calls == []


def test_wait_for_terminal_operation_keeps_cancellation_when_remote_cancel_drops_the_connection(monkeypatch) -> None:
    """
    @brief      Verify a torn-down runtime during remote cancellation does not turn a cancel into a failure.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"operation": {"status": "running", "cancellable": True}},
    )
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "_sleep_with_cancel",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            operation_runtime_service.OperationCancelledError("cancelled")
        ),
    )
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "cancel_operation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionResetError("runtime closed the connection")),
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        voiceweaver_runtime_service.wait_for_terminal_operation(
            "http://runtime",
            timeout_seconds=90,
            cancel_requested=lambda: False,
        )


def test_wait_for_terminal_operation_posts_cancel_for_cancellable_runtime_operation(monkeypatch) -> None:
    """
    @brief      Verify local cancellation requests remote cancellation for a cancellable operation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    observed_cancel_calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {
            "operation": {"status": "running", "cancellable": True},
        },
    )
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "_sleep_with_cancel",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            operation_runtime_service.OperationCancelledError("cancelled")
        ),
    )
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "cancel_operation",
        lambda base_url, timeout_seconds: observed_cancel_calls.append((base_url, timeout_seconds)),
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        voiceweaver_runtime_service.wait_for_terminal_operation(
            "http://runtime",
            timeout_seconds=90,
            cancel_requested=lambda: False,
        )

    assert observed_cancel_calls == [("http://runtime", config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS)]


def test_wait_for_terminal_operation_posts_cancel_when_requested_after_status_read(monkeypatch) -> None:
    """@brief Verify cancellation after a status read uses that cancellable operation snapshot."""
    cancellation_checks = {"count": 0}
    observed_cancel_calls: list[tuple[str, int]] = []

    def _cancel_requested() -> bool:
        """@brief Request cancellation only after the first status read begins."""
        cancellation_checks["count"] += 1
        return cancellation_checks["count"] >= 2

    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {
            "operation": {"status": "running", "cancellable": True},
        },
    )
    monkeypatch.setattr(
        voiceweaver_runtime_service,
        "cancel_operation",
        lambda base_url, timeout_seconds: observed_cancel_calls.append((base_url, timeout_seconds)),
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        voiceweaver_runtime_service.wait_for_terminal_operation(
            "http://runtime",
            timeout_seconds=90,
            cancel_requested=_cancel_requested,
        )

    assert observed_cancel_calls == [("http://runtime", config.DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS)]


def test_wait_for_terminal_operation_ignores_idle_before_running(monkeypatch) -> None:
    """@brief Verify registration-lag idle status does not become a false terminal failure."""
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
