#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""Qt tests for the unified Cleanup V2 page."""

from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage


def test_page_exposes_one_cleanup_action_with_optional_ai_profile(qtbot) -> None:
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Local Qwen", "qwen")], "qwen")
    page.set_processing_state("source", None, [], True, True)
    requested: list[object] = []
    page.cleanup_requested.connect(requested.append)

    page._cleanup_button.click()
    assert requested == ["qwen"]
    assert not hasattr(page, "_ai_clean_button")
    assert not hasattr(page, "_apply_spacing_button")

    page._ai_profile_combo.setCurrentIndex(0)
    page._cleanup_button.click()
    assert requested[-1] is None


def test_page_edit_save_and_cancel_are_optional(qtbot) -> None:
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state("source", "clean", [], True, True, True, "passed", 0)
    saved: list[str] = []
    page.save_cleaned_text_requested.connect(saved.append)

    page._edit_cleaned_button.click()
    page._cleaned_text_edit.setPlainText("changed")
    page._cancel_edit_button.click()
    assert page._cleaned_text_edit.toPlainText() == "clean"

    page._edit_cleaned_button.click()
    page._cleaned_text_edit.setPlainText("saved")
    page._save_cleaned_button.click()
    assert saved == ["saved"]
