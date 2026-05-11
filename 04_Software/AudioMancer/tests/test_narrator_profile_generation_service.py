#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_narrator_profile_generation_service.py
@brief Narrator profile generation service tests for AudioMancer.
@details Verifies AI-assisted text-only narrator profile generation source
         selection, validation, persistence, resume, and cancellation contracts.
@author Eng. Dan Dumitru Pasare
@date 2026-05-11
@version 0.2.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import narrator_definition_service, narrator_profile_generation_service
from audiomancer.services.operation_runtime_service import OperationCancelledError

# CONSTANTS

_MOCK_AI_PROFILE = {
    "id": "profile_1",
    "label": "Mock Profile",
    "backend_kind": "lmstudio",
    "base_url": "http://127.0.0.1:1234/v1",
    "api_key": "",
    "model_name": "qwen3-8b",
    "context_window": 8192,
    "max_output_tokens": 1024,
    "request_timeout_seconds": 90,
    "temperature": 0.2,
    "supports_structured_output": True,
    "enabled": True,
}


def test_narrator_profile_generation_prefers_approved_translation_for_voice_language(
    tmp_path,
    monkeypatch,
    mock_prompt_environment,
) -> None:
    """
    @brief      Verify approved translated text is analyzed when it matches the voice language.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  mock_prompt_environment Prompt-root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _write_narrator_prompts(mock_prompt_environment)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_chunks(project_root, "Original desert empire text.")
    _write_translation(project_root, "Text tradus despre un imperiu al desertului.", "ro")
    prompts: list[str] = []
    monkeypatch.setattr(
        narrator_profile_generation_service.llm_provider_service,
        "chat_json",
        _chat_json_factory(prompts, _profiles_payload(2)),
    )

    report_payload = narrator_profile_generation_service.generate_narrator_profiles(
        project_root,
        {},
        _MOCK_AI_PROFILE,
        2,
        "ro",
        220,
    )

    profiles = narrator_definition_service.load_profiles(project_root)
    assert report_payload["source"] == narrator_profile_generation_service.SOURCE_TRANSLATED_CHUNKS
    assert "Text tradus" in prompts[0]
    assert "Original desert" not in prompts[0]
    assert len(profiles) == 2
    assert all(profile["profile_origin"] == "ai_generated" for profile in profiles)
    assert all(profile.get("sample_audio_path") is None for profile in profiles)
    assert not (project_root / config.SELECTED_NARRATOR_AUDIO_FILE_NAME).exists()


def test_narrator_profile_generation_odd_allocation_appends_without_deleting_existing(
    tmp_path,
    monkeypatch,
    mock_prompt_environment,
) -> None:
    """
    @brief      Verify odd gender allocation and append-only profile persistence.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  mock_prompt_environment Prompt-root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _write_narrator_prompts(mock_prompt_environment)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_chunks(project_root, "A solemn chronicle moves through cities, memory, and political consequence.")
    existing_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Existing Narrator",
        "English",
        "Existing prompt text.",
        "Existing preview.",
    )
    monkeypatch.setattr(narrator_profile_generation_service.random, "choice", lambda _values: "female")
    monkeypatch.setattr(
        narrator_profile_generation_service.llm_provider_service,
        "chat_json",
        _chat_json_factory([], _profiles_payload(3, genders=("male", "female", "female"))),
    )

    report_payload = narrator_profile_generation_service.generate_narrator_profiles(
        project_root,
        {},
        _MOCK_AI_PROFILE,
        3,
        "en",
        220,
    )

    profiles = narrator_definition_service.load_profiles(project_root)
    assert profiles[0]["profile_id"] == existing_profile["profile_id"]
    assert report_payload["gender_allocation"] == {
        "male": 1,
        "female": 2,
        "random": 1,
        "random_gender": "female",
    }
    assert len(profiles) == 4
    assert len(report_payload["generated_profile_ids"]) == 3


def test_narrator_profile_generation_invalid_response_leaves_profiles_unchanged(
    tmp_path,
    monkeypatch,
    mock_prompt_environment,
) -> None:
    """
    @brief      Verify invalid AI output is rejected before profile writes occur.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  mock_prompt_environment Prompt-root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _write_narrator_prompts(mock_prompt_environment)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_chunks(project_root, "A reflective book with intimate narration and restrained tension.")
    narrator_definition_service.create_custom_profile(
        project_root,
        "Existing Narrator",
        "English",
        "Existing prompt text.",
        "Existing preview.",
    )
    before_payload = (project_root / config.NARRATOR_PROFILE_FILE_NAME).read_text(encoding="utf-8")
    monkeypatch.setattr(
        narrator_profile_generation_service.llm_provider_service,
        "chat_json",
        _chat_json_factory([], {"profiles": []}),
    )

    with pytest.raises(ValueError, match="exactly 2 profiles"):
        narrator_profile_generation_service.generate_narrator_profiles(
            project_root,
            {},
            _MOCK_AI_PROFILE,
            2,
            "en",
            220,
        )

    assert (project_root / config.NARRATOR_PROFILE_FILE_NAME).read_text(encoding="utf-8") == before_payload
    assert not (project_root / config.NARRATOR_PROFILE_GENERATION_REPORT_FILE_NAME).exists()


def test_narrator_profile_generation_merges_token_usage_into_report_and_state(
    tmp_path,
    monkeypatch,
    mock_prompt_environment,
) -> None:
    """
    @brief      Verify cumulative token usage is written to report and runtime state.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  mock_prompt_environment Prompt-root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _write_narrator_prompts(mock_prompt_environment)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_chunks(project_root, "A quiet but expansive science fiction story with ritual and politics.")
    monkeypatch.setattr(
        narrator_profile_generation_service.llm_provider_service,
        "chat_json",
        _chat_json_factory([], _profiles_payload(2)),
    )

    report_payload = narrator_profile_generation_service.generate_narrator_profiles(
        project_root,
        {},
        _MOCK_AI_PROFILE,
        2,
        "en",
        220,
    )
    state_payload = narrator_profile_generation_service.load_operation_state(project_root)

    assert report_payload["token_usage"] == {
        "input_tokens": 30,
        "output_tokens": 12,
        "total_tokens": 42,
        "usage_available": True,
    }
    assert state_payload is not None
    assert state_payload["metadata"]["token_usage"] == report_payload["token_usage"]


def test_narrator_profile_generation_cancellation_leaves_profiles_unchanged(
    tmp_path,
    monkeypatch,
    mock_prompt_environment,
) -> None:
    """
    @brief      Verify cancellation before AI generation does not append profiles.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  mock_prompt_environment Prompt-root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _write_narrator_prompts(mock_prompt_environment)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_chunks(project_root, "A short source text.")
    narrator_definition_service.ensure_narrator_definition_files(project_root)
    before_payload = (project_root / config.NARRATOR_PROFILE_FILE_NAME).read_text(encoding="utf-8")

    with pytest.raises(OperationCancelledError):
        narrator_profile_generation_service.generate_narrator_profiles(
            project_root,
            {},
            _MOCK_AI_PROFILE,
            2,
            "en",
            220,
            cancel_requested=lambda: True,
        )

    assert (project_root / config.NARRATOR_PROFILE_FILE_NAME).read_text(encoding="utf-8") == before_payload


def test_narrator_profile_generation_resumes_after_completed_style_window(
    tmp_path,
    monkeypatch,
    mock_prompt_environment,
) -> None:
    """
    @brief      Verify a restarted run skips style windows already stored in the checkpoint.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  mock_prompt_environment Prompt-root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _write_narrator_prompts(mock_prompt_environment)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_chunk_records(
        project_root,
        [
            "First style window with political ritual and restrained grief.",
            "Second style window with imperial memory and quiet tension.",
            "Third style window with prophecy, consequence, and solemn pacing.",
        ],
    )
    monkeypatch.setattr(narrator_profile_generation_service.config, "DEFAULT_NARRATOR_PROFILE_STYLE_WINDOW_SIZE", 1)
    first_calls: list[tuple[str, int]] = []

    def _cancel_after_first_window(_profile, _system_prompt, _user_prompt, **kwargs):
        """
        @brief      Cancel after the first completed style-window response.
        @return     Fake provider response.
        @exception  OperationCancelledError Raised after the first window.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-11
        @version    0.1.0
        """
        log_context = dict(kwargs.get("log_context") or {})
        stage_label = str(log_context.get("stage_label", ""))
        window_index = int(log_context.get("window_index", 0) or 0)
        first_calls.append((stage_label, window_index))
        if stage_label == "style_window" and window_index > 1:
            raise OperationCancelledError("cancelled")
        return {"payload": _style_observation_payload(), "usage": _style_usage_payload()}

    monkeypatch.setattr(
        narrator_profile_generation_service.llm_provider_service,
        "chat_json",
        _cancel_after_first_window,
    )
    with pytest.raises(OperationCancelledError):
        narrator_profile_generation_service.generate_narrator_profiles(
            project_root,
            {},
            _MOCK_AI_PROFILE,
            2,
            "en",
            220,
        )

    state_payload = narrator_profile_generation_service.load_operation_state(project_root)
    assert state_payload is not None
    assert state_payload["progress_current"] == 1
    assert len(state_payload["resume_checkpoint"]["style_observations"]) == 1
    assert not narrator_definition_service.load_profiles(project_root)

    resumed_calls: list[tuple[str, int]] = []

    def _resume_chat_json(_profile, _system_prompt, _user_prompt, **kwargs):
        """
        @brief      Return style responses only for unfinished windows, then profiles.
        @return     Fake provider response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-11
        @version    0.1.0
        """
        log_context = dict(kwargs.get("log_context") or {})
        stage_label = str(log_context.get("stage_label", ""))
        window_index = int(log_context.get("window_index", 0) or 0)
        resumed_calls.append((stage_label, window_index))
        if stage_label == "style_window":
            return {"payload": _style_observation_payload(), "usage": _style_usage_payload()}
        return {"payload": _profiles_payload(2), "usage": _generation_usage_payload()}

    monkeypatch.setattr(
        narrator_profile_generation_service.llm_provider_service,
        "chat_json",
        _resume_chat_json,
    )
    report_payload = narrator_profile_generation_service.generate_narrator_profiles(
        project_root,
        {},
        _MOCK_AI_PROFILE,
        2,
        "en",
        220,
    )

    assert ("style_window", 1) not in resumed_calls
    assert [window_index for stage_label, window_index in resumed_calls if stage_label == "style_window"] == [2, 3]
    assert resumed_calls[-1] == ("profile_generation", 0)
    assert len(narrator_definition_service.load_profiles(project_root)) == 2
    assert report_payload["token_usage"] == {
        "input_tokens": 50,
        "output_tokens": 20,
        "total_tokens": 70,
        "usage_available": True,
    }


def test_narrator_profile_generation_resumes_final_generation_without_reanalyzing_style(
    tmp_path,
    monkeypatch,
    mock_prompt_environment,
) -> None:
    """
    @brief      Verify cancellation during final generation preserves completed style observations.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  mock_prompt_environment Prompt-root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _write_narrator_prompts(mock_prompt_environment)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_chunk_records(
        project_root,
        [
            "First style window with ritual politics.",
            "Second style window with reflective tragedy.",
        ],
    )
    monkeypatch.setattr(narrator_profile_generation_service.config, "DEFAULT_NARRATOR_PROFILE_STYLE_WINDOW_SIZE", 1)

    def _cancel_final_generation(_profile, _system_prompt, _user_prompt, **kwargs):
        """
        @brief      Complete style analysis, then cancel the final generation request.
        @return     Fake provider response.
        @exception  OperationCancelledError Raised for final generation.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-11
        @version    0.1.0
        """
        stage_label = str(dict(kwargs.get("log_context") or {}).get("stage_label", ""))
        if stage_label == "profile_generation":
            raise OperationCancelledError("cancelled")
        return {"payload": _style_observation_payload(), "usage": _style_usage_payload()}

    monkeypatch.setattr(
        narrator_profile_generation_service.llm_provider_service,
        "chat_json",
        _cancel_final_generation,
    )
    with pytest.raises(OperationCancelledError):
        narrator_profile_generation_service.generate_narrator_profiles(
            project_root,
            {},
            _MOCK_AI_PROFILE,
            2,
            "en",
            220,
        )

    resumed_calls: list[str] = []

    def _resume_final_generation(_profile, _system_prompt, _user_prompt, **kwargs):
        """
        @brief      Verify only the final generation call is replayed.
        @return     Fake provider response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-11
        @version    0.1.0
        """
        stage_label = str(dict(kwargs.get("log_context") or {}).get("stage_label", ""))
        resumed_calls.append(stage_label)
        assert stage_label == "profile_generation"
        return {"payload": _profiles_payload(2), "usage": _generation_usage_payload()}

    monkeypatch.setattr(
        narrator_profile_generation_service.llm_provider_service,
        "chat_json",
        _resume_final_generation,
    )
    narrator_profile_generation_service.generate_narrator_profiles(
        project_root,
        {},
        _MOCK_AI_PROFILE,
        2,
        "en",
        220,
    )

    assert resumed_calls == ["profile_generation"]
    assert len(narrator_definition_service.load_profiles(project_root)) == 2


def test_narrator_profile_generation_falls_back_to_clean_text(
    tmp_path,
    monkeypatch,
    mock_prompt_environment,
) -> None:
    """
    @brief      Verify clean_text.txt is accepted when chunk and translation outputs do not exist.
    @param[in]  tmp_path Temporary path fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  mock_prompt_environment Prompt-root fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _write_narrator_prompts(mock_prompt_environment)
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(
        "First cleaned paragraph.\n\nSecond cleaned paragraph.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        narrator_profile_generation_service.llm_provider_service,
        "chat_json",
        _chat_json_factory([], _profiles_payload(2)),
    )

    report_payload = narrator_profile_generation_service.generate_narrator_profiles(
        project_root,
        {},
        _MOCK_AI_PROFILE,
        2,
        "en",
        220,
    )

    assert report_payload["source"] == narrator_profile_generation_service.SOURCE_CLEANED_TEXT
    assert len(narrator_definition_service.load_profiles(project_root)) == 2


def _write_narrator_prompts(prompt_root) -> None:
    """
    @brief      Write minimal narrator profile prompts into the test prompt root.
    @param[in]  prompt_root Prompt fixture root.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    (prompt_root / "narrator_profile_style_system.txt").write_text("System prompt.", encoding="utf-8")
    (prompt_root / "narrator_profile_style_window_user.txt").write_text("Analyze:\n{units_block}", encoding="utf-8")
    (prompt_root / "narrator_profile_generation_user.txt").write_text(
        "{voice_language}\n{profile_count}\n{male_count}\n{female_count}\n{random_gender_count}\n{style_observations}",
        encoding="utf-8",
    )


def _write_chunks(project_root, text: str) -> None:
    """
    @brief      Write one canonical chunk artifact.
    @param[in]  project_root Active test project root.
    @param[in]  text Chunk text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _write_chunk_records(project_root, [text])


def _write_chunk_records(project_root, texts: list[str]) -> None:
    """
    @brief      Write canonical chunk artifacts.
    @param[in]  project_root Active test project root.
    @param[in]  texts Ordered chunk texts.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": f"chunk-{index:04d}",
                    "sequence_index": index,
                    "text": text,
                }
                for index, text in enumerate(texts, start=1)
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_translation(project_root, text: str, target_language: str) -> None:
    """
    @brief      Write approved translation artifacts.
    @param[in]  project_root Active test project root.
    @param[in]  text Translated text.
    @param[in]  target_language Translation target language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "translated_text": text,
                    "approved": True,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.TRANSLATION_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": target_language,
                "total_chunk_count": 1,
                "approved_chunk_count": 1,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _chat_json_factory(observed_prompts: list[str], generation_payload: dict[str, object]):
    """
    @brief      Build a fake chat_json callable for service tests.
    @param[in]  observed_prompts Captured prompt list.
    @param[in]  generation_payload Final generation response payload.
    @return     Fake chat_json callable.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **kwargs):
        """
        @brief      Return deterministic style or profile-generation payloads.
        @return     Fake provider response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-11
        @version    0.1.0
        """
        observed_prompts.append(user_prompt)
        stage_label = dict(kwargs.get("log_context") or {}).get("stage_label")
        if stage_label == "style_window":
            payload = _style_observation_payload()
            usage = _style_usage_payload()
        else:
            payload = generation_payload
            usage = _generation_usage_payload()
        return {"payload": payload, "usage": usage}

    return _fake_chat_json


def _style_observation_payload() -> dict[str, object]:
    """
    @brief      Build a valid style-observation payload.
    @return     Fake style-observation payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    return {
        "genre": ["literary science fiction"],
        "tone": ["reflective"],
        "pacing": ["measured"],
        "narrator_distance": ["close third person"],
        "emotional_range": ["restrained"],
        "diction": ["polished"],
        "worldbuilding_cues": ["empire"],
        "themes": ["memory"],
        "narration_risks": ["overacting"],
    }


def _style_usage_payload() -> dict[str, object]:
    """
    @brief      Build token usage for one fake style request.
    @return     Token usage payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    return {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "usage_available": True}


def _generation_usage_payload() -> dict[str, object]:
    """
    @brief      Build token usage for one fake profile-generation request.
    @return     Token usage payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    return {"input_tokens": 20, "output_tokens": 8, "total_tokens": 28, "usage_available": True}


def _profiles_payload(count: int, genders: tuple[str, ...] | None = None) -> dict[str, object]:
    """
    @brief      Build a valid generated-profiles payload.
    @param[in]  count Profile count.
    @param[in]  genders Optional gender sequence.
    @return     AI payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    resolved_genders = genders or tuple("male" if index < count // 2 else "female" for index in range(count))
    profiles = []
    for index, gender in enumerate(resolved_genders, start=1):
        profiles.append(
            {
                "display_name": f"{gender.title()} Narrator {index}",
                "gender": gender,
                "style_label": "Reflective",
                "prompt_text": (
                    "A mature narrator voice with warm resonance, measured pacing, clear diction, restrained "
                    "emotion, immersive presence, and refined audiobook delivery."
                ),
                "preview_text": f"Original preview sentence number {index}.",
            }
        )
    return {"style_brief": "Reflective literary science fiction.", "profiles": profiles}


# END OF FILE
