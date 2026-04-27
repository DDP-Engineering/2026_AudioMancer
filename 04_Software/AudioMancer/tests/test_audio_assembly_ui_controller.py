#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_assembly_ui_controller.py
@brief Audio Assembly UI controller tests for AudioMancer.
@details Verifies confirmation, settings persistence, threaded dispatch, and
         playback, and reset synchronization for the Audio Assembly controller.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.4.0
"""

# IMPORTS

import json
from types import SimpleNamespace

from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import audio_assembly_ui_controller


def test_audio_assembly_ui_controller_persists_settings_and_starts_threaded_operation(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Generate Audio confirms, persists settings, and dispatches a threaded operation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    window = _controller_window(tmp_path)
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        audio_assembly_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        lambda _window, operation_kind, operation_name, initial_message, worker_callable, **kwargs: observed.update(
            {
                "operation_kind": operation_kind,
                "operation_name": operation_name,
                "initial_message": initial_message,
                "worker_callable": worker_callable,
                "set_busy": kwargs["set_busy"],
            }
        ),
    )

    audio_assembly_ui_controller.handle_generate_requested(
        window,
        {
            "output_mode": "time_limit",
            "max_duration_minutes": 45,
            "output_format": "wav",
            "inter_block_silence_ms": 300,
            "inter_chunk_silence_ms": 900,
        },
    )

    manifest = project_workspace_service.load_manifest(window._current_project_root)
    assert observed["operation_kind"] == "audio_assembly"
    assert manifest["audio_assembly_settings"]["output_mode"] == "time_limit"
    assert manifest["audio_assembly_settings"]["max_duration_minutes"] == 45


def test_audio_assembly_ui_controller_reset_clears_artifacts_and_manifest_summary(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Reset Audio Assembly clears artifacts and refreshes the manifest summary.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    window = _controller_window(tmp_path)
    (window._current_project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME).mkdir()
    (window._current_project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / "audiobook.wav").write_bytes(b"RIFF")
    (window._current_project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME).write_text("{}\n", encoding="utf-8")
    (window._current_project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME).write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    audio_assembly_ui_controller.handle_reset_requested(window)

    manifest = project_workspace_service.load_manifest(window._current_project_root)
    assert not (window._current_project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / "audiobook.wav").exists()
    assert manifest["operations"]["audio_assembly"]["status"] == "not_started"


def test_audio_assembly_ui_controller_stops_active_playback_when_selected_output_changes(tmp_path) -> None:
    """
    @brief      Verify Stop halts active playback even when another output row is selected.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    window = _controller_window(tmp_path)
    _write_audio_assembly_report(window._current_project_root)
    window._audio_assembly_playback_output_key = "part-0001"

    audio_assembly_ui_controller.handle_playback_toggle_requested(window, "part-0002")

    assert window._audio_assembly_audio_player.stop_count == 1
    assert window._audio_assembly_audio_player.play_count == 0
    assert window._audio_assembly_audio_player.source.toString() == ""
    assert window._audio_assembly_page.playback_active is False
    assert window._audio_assembly_playback_output_key is None


def test_audio_assembly_ui_controller_starts_selected_output(tmp_path) -> None:
    """
    @brief      Verify playback starts from the selected generated Audio Assembly output.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    window = _controller_window(tmp_path)
    output_paths = _write_audio_assembly_report(window._current_project_root)

    audio_assembly_ui_controller.handle_playback_toggle_requested(window, "part-0002")

    assert window._audio_assembly_audio_player.play_count == 1
    assert window._audio_assembly_audio_player.source.toLocalFile() == output_paths["part-0002"].as_posix()
    assert window._audio_assembly_page.playback_active is True
    assert window._audio_assembly_page.playback_progress == (0, 1000)
    assert window._audio_assembly_playback_output_key == "part-0002"


def test_audio_assembly_ui_controller_restarts_clicked_output_from_beginning(tmp_path) -> None:
    """
    @brief      Verify double-click restart stops active playback and starts the clicked output.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    window = _controller_window(tmp_path)
    output_paths = _write_audio_assembly_report(window._current_project_root)
    window._audio_assembly_playback_output_key = "part-0001"
    window._audio_assembly_audio_player.position_ms = 30_000

    audio_assembly_ui_controller.handle_playback_restart_requested(window, "part-0002")

    assert window._audio_assembly_audio_player.stop_count == 1
    assert window._audio_assembly_audio_player.play_count == 1
    assert window._audio_assembly_audio_player.source.toLocalFile() == output_paths["part-0002"].as_posix()
    assert window._audio_assembly_audio_player.position_ms == 0
    assert window._audio_assembly_page.playback_active is True
    assert window._audio_assembly_page.playback_progress == (0, 1000)
    assert window._audio_assembly_playback_output_key == "part-0002"


def test_audio_assembly_ui_controller_updates_playback_progress(tmp_path) -> None:
    """
    @brief      Verify media position and duration callbacks refresh the page progress bar.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    window = _controller_window(tmp_path)
    window._audio_assembly_audio_player.duration_ms = 60_000
    window._audio_assembly_audio_player.position_ms = 12_000

    audio_assembly_ui_controller.handle_playback_position_changed(window, 14_000)
    assert window._audio_assembly_page.playback_progress == (14_000, 60_000)

    audio_assembly_ui_controller.handle_playback_duration_changed(window, 90_000)
    assert window._audio_assembly_page.playback_progress == (12_000, 90_000)


def test_audio_assembly_ui_controller_seeks_and_skips_with_clamping(tmp_path) -> None:
    """
    @brief      Verify seek and skip requests clamp to the current media duration.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    window = _controller_window(tmp_path)
    window._audio_assembly_audio_player.duration_ms = 60_000
    window._audio_assembly_audio_player.position_ms = 20_000

    audio_assembly_ui_controller.handle_playback_skip_requested(window, 10_000)
    assert window._audio_assembly_audio_player.position_ms == 30_000

    audio_assembly_ui_controller.handle_playback_skip_requested(window, -40_000)
    assert window._audio_assembly_audio_player.position_ms == 0

    audio_assembly_ui_controller.handle_playback_seek_requested(window, 70_000)
    assert window._audio_assembly_audio_player.position_ms == 60_000


def test_audio_assembly_ui_controller_ignores_startup_stopped_state(tmp_path) -> None:
    """
    @brief      Verify transient stopped-state during source loading does not clear playback state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    window = _controller_window(tmp_path)
    window._audio_assembly_playback_output_key = "part-0001"
    window._audio_assembly_playback_starting = True
    window._audio_assembly_page.set_playback_active(True)
    window._audio_assembly_audio_player.state = QMediaPlayer.PlaybackState.StoppedState

    audio_assembly_ui_controller.handle_playback_state_changed(window)

    assert window._audio_assembly_playback_output_key == "part-0001"
    assert window._audio_assembly_page.playback_active is True


def _controller_window(tmp_path):
    """
    @brief      Build a minimal main-window test double for controller tests.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     Controller-compatible window namespace.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project("AudioAssemblyController", tmp_path)
    return SimpleNamespace(
        _active_operation_kind=None,
        _current_project_root=project_root,
        _current_manifest=manifest,
        _settings_payload={"language": "en"},
        _audio_assembly_page=_AudioAssemblyPageDouble(),
        _audio_assembly_audio_player=_AudioAssemblyPlayerDouble(),
        _audio_assembly_playback_output_key=None,
        _audio_assembly_playback_starting=False,
        show_project_state=lambda project_root, manifest: _set_project_state,
    )


def _set_project_state(project_root, manifest) -> None:
    """
    @brief      Accept project-state refresh calls from controller test doubles.
    @param[in]  project_root Active project root.
    @param[in]  manifest Active manifest payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = project_root
    _ = manifest


def _write_audio_assembly_report(project_root) -> dict[str, object]:
    """
    @brief      Create generated Audio Assembly output records for playback tests.
    @param[in]  project_root Active project root.
    @return     Mapping from output key to generated output path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    output_root = project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME
    output_root.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "part-0001": output_root / "part-0001.wav",
        "part-0002": output_root / "part-0002.wav",
    }
    for output_path in output_paths.values():
        output_path.write_bytes(b"RIFF")
    report = {
        "outputs": [
            _output_record(project_root, "part-0001", output_paths["part-0001"]),
            _output_record(project_root, "part-0002", output_paths["part-0002"]),
        ]
    }
    (project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME).write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_paths


def _output_record(project_root, output_key: str, output_path) -> dict[str, object]:
    """
    @brief      Build one generated output record for Audio Assembly playback tests.
    @param[in]  project_root Active project root.
    @param[in]  output_key Generated output key.
    @param[in]  output_path Generated output path.
    @return     Generated output record.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return {
        "output_key": output_key,
        "file_name": output_path.name,
        "audio_relative_path": output_path.relative_to(project_root).as_posix(),
        "block_count": 1,
        "chunk_ids": [output_key],
        "duration_seconds": 1.0,
        "generated": True,
        "generated_at": "2026-04-25T00:00:00+00:00",
        "output_format": "wav",
    }


class _AudioAssemblyPageDouble:
    """
    @brief      Minimal Audio Assembly page test double.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """

    def __init__(self) -> None:
        """
        @brief      Initialize captured page state.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.2.0
        """
        self.busy = False
        self.playback_active = False
        self.playback_progress = (0, 0)

    def set_busy(self, is_busy: bool) -> None:
        """
        @brief      Capture busy state updates.
        @param[in]  is_busy Current busy state.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self.busy = is_busy

    def set_playback_active(self, is_active: bool) -> None:
        """
        @brief      Capture playback state updates.
        @param[in]  is_active Current playback-active state.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self.playback_active = is_active

    def set_playback_progress(self, position_ms: int, duration_ms: int) -> None:
        """
        @brief      Capture playback progress updates.
        @param[in]  position_ms Current playback position in milliseconds.
        @param[in]  duration_ms Current playback duration in milliseconds.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-27
        @version    0.1.0
        """
        self.playback_progress = (position_ms, duration_ms)


class _AudioAssemblyPlayerDouble:
    """
    @brief      Minimal QMediaPlayer-compatible test double.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """

    def __init__(self) -> None:
        """
        @brief      Initialize captured player state.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.2.0
        """
        self.state = QMediaPlayer.PlaybackState.StoppedState
        self.source = None
        self.stop_count = 0
        self.play_count = 0
        self.position_ms = 0
        self.duration_ms = 0

    def stop(self) -> None:
        """
        @brief      Capture stop requests.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self.stop_count += 1
        self.state = QMediaPlayer.PlaybackState.StoppedState

    def setSource(self, source) -> None:
        """
        @brief      Capture source changes.
        @param[in]  source Media source URL.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self.source = source

    def play(self) -> None:
        """
        @brief      Capture play requests.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        self.play_count += 1
        self.state = QMediaPlayer.PlaybackState.PlayingState

    def setPosition(self, position_ms: int) -> None:
        """
        @brief      Capture seek requests.
        @param[in]  position_ms New playback position in milliseconds.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-27
        @version    0.1.0
        """
        self.position_ms = int(position_ms)

    def position(self) -> int:
        """
        @brief      Return the captured playback position.
        @return     Current playback position in milliseconds.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-27
        @version    0.1.0
        """
        return self.position_ms

    def duration(self) -> int:
        """
        @brief      Return the captured playback duration.
        @return     Current playback duration in milliseconds.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-27
        @version    0.1.0
        """
        return self.duration_ms

    def playbackState(self):
        """
        @brief      Return the captured playback state.
        @return     Current playback state.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        return self.state


# END OF FILE
