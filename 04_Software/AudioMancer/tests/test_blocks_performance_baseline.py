#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_blocks_performance_baseline.py
@brief Opt-in performance harness for large Speech Blocks and Audio Blocks projects.
@details Times representative review operations on a synthetic 3,000-block
         project without making the default test suite depend on timing.
@author Eng. Dan Dumitru Pasare
@date 2026-06-10
@version 0.1.0
"""

# IMPORTS

import importlib.util
from pathlib import Path
import time

import pytest

from audiomancer.services import audio_blocks_state_service, project_workspace_service, speech_blocks_service
from audiomancer.services.speech_blocks_state_service import build_speech_blocks_state
from audiomancer.ui.pages.speech_blocks_page import SpeechBlocksPage

# CONSTANTS

pytestmark = pytest.mark.performance
_BLOCK_COUNT = 3000
_CHUNK_COUNT = 150
_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_large_block_review_performance_baseline(tmp_path, qtbot) -> None:
    """
    @brief      Time representative large-project Speech/Audio Blocks review operations.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    project_root = _build_synthetic_project(tmp_path / "LargeBook")
    manifest = project_workspace_service.load_manifest(project_root)

    approve_elapsed = _elapsed(lambda: speech_blocks_service.approve_speech_block(project_root, "0001-000001"))
    speech_state, speech_state_elapsed = _elapsed_with_result(
        lambda: build_speech_blocks_state(project_root, manifest, "en", {})
    )
    audio_state_elapsed = _elapsed(
        lambda: audio_blocks_state_service.build_audio_blocks_state(project_root, manifest, "en", {})
    )

    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    full_page_elapsed = _elapsed(lambda: page.set_speech_blocks_state(**speech_state))
    first_block = dict(speech_state["speech_blocks"][0])
    first_block["approved"] = not bool(first_block.get("approved", False))
    item_update_elapsed = _elapsed(lambda: page.update_speech_block_item(first_block))

    print(
        "\nlarge-block timings: "
        f"approve={approve_elapsed:.4f}s "
        f"speech_state={speech_state_elapsed:.4f}s "
        f"audio_state={audio_state_elapsed:.4f}s "
        f"page_full={full_page_elapsed:.4f}s "
        f"page_item={item_update_elapsed:.4f}s"
    )
    assert len(speech_state["speech_blocks"]) == _BLOCK_COUNT
    assert approve_elapsed < 10.0
    assert speech_state_elapsed < 10.0
    assert audio_state_elapsed < 10.0
    assert full_page_elapsed < 10.0
    assert item_update_elapsed < full_page_elapsed


def _build_synthetic_project(project_root: Path) -> Path:
    """
    @brief      Load the synthetic-project tool and create one large fixture.
    @param[in]  project_root Output project root folder.
    @return     Created project root.
    @exception  AssertionError Raised when the tool module cannot be loaded.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    module_path = _REPO_ROOT / "02_Tools" / "make_synthetic_project.py"
    spec = importlib.util.spec_from_file_location("make_synthetic_project", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.build_synthetic_project(project_root, blocks=_BLOCK_COUNT, chunks=_CHUNK_COUNT)


def _elapsed(callback) -> float:
    """
    @brief      Time one callback execution.
    @param[in]  callback Callable to execute.
    @return     Elapsed seconds.
    @exception  Any exception raised by the callback.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    started = time.perf_counter()
    callback()
    return time.perf_counter() - started


def _elapsed_with_result(callback):
    """
    @brief      Time one callback execution while preserving its result.
    @param[in]  callback Callable to execute.
    @return     Tuple of callback result and elapsed seconds.
    @exception  Any exception raised by the callback.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    started = time.perf_counter()
    result = callback()
    return result, time.perf_counter() - started
