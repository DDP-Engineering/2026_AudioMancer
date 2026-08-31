#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QPushButton

from audiomancer.ui.pages.book_analysis_page import BookAnalysisPage


def _report() -> dict[str, object]:
    return {
        "concise": {
            "book_type": "Novel",
            "genres": ["Mystery"],
            "subjects": ["Memory"],
            "setting_time": ["Bucharest, present day"],
            "summary": "Ana investigates an archive.",
            "main_characters": [{"name": "Ana", "role": "Protagonist"}],
            "themes": ["Identity"],
        },
        "details": {
            "detailed_summary": "Ana follows the archive's history.",
            "supporting_characters": [
                {"name": "Mihai", "role": "Archivist", "relationships": ["Ana's guide"]}
            ],
            "narrative_perspective": "Third-person limited",
            "narrative_structure": "Linear",
            "tone": ["Intimate", "Suspenseful"],
            "pacing": "Measured",
            "diction": "Literary and direct",
            "emotional_range": ["Curiosity", "Resolve"],
            "audiobook_guidance": {
                "narration_style": "Restrained suspense",
                "character_voice_notes": ["Keep Mihai reserved."],
            },
            "uncertainties": ["The visitor remains ambiguous."],
            "source_evidence": [
                {"chunk_ids": ["chunk-0001"], "note": "Introduces Ana."}
            ],
        },
    }


def _page(qtbot) -> BookAnalysisPage:
    page = BookAnalysisPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile A", "profile-a")], "profile-a")
    page.set_analysis_state(
        state="ready",
        notes=["Ready."],
        report=None,
        report_stale=False,
        can_analyze=True,
        can_reset=False,
    )
    return page


def test_book_analysis_page_has_exactly_two_actions_and_emits_signals(qtbot) -> None:
    page = _page(qtbot)
    analyze_requests: list[str] = []
    reset_requests: list[bool] = []
    page.analyze_requested.connect(analyze_requests.append)
    page.reset_requested.connect(lambda: reset_requests.append(True))

    assert len(page.findChildren(QPushButton)) == 2
    qtbot.mouseClick(page._analyze_button, Qt.MouseButton.LeftButton)
    page.set_analysis_state(
        state="completed",
        notes=["Completed."],
        report=_report(),
        report_stale=False,
        can_analyze=False,
        can_reset=True,
    )
    qtbot.mouseClick(page._reset_button, Qt.MouseButton.LeftButton)

    assert analyze_requests == ["profile-a"]
    assert reset_requests == [True]


def test_book_analysis_page_preserves_stale_report_and_expands_details(qtbot) -> None:
    page = _page(qtbot)
    page.set_analysis_state(
        state="stale_completed",
        notes=["This report is stale."],
        report=_report(),
        report_stale=True,
        can_analyze=True,
        can_reset=True,
    )

    assert page._analyze_button.isEnabled() is True
    assert page._concise_values["summary"].text() == "Ana investigates an archive."
    assert page._details_group.isChecked() is False
    assert page._details_content.isHidden() is True

    page._details_group.setChecked(True)

    assert page._details_content.isHidden() is False
    assert "Mihai" in page._detail_values["supporting_characters"].text()
    assert "chunk-0001" in page._detail_values["source_evidence"].text()


def test_book_analysis_page_localizes_actions_without_context_controls(qtbot) -> None:
    page = _page(qtbot)

    page.apply_language("ro")

    assert page._analyze_button.text() == "Analizează"
    assert page._reset_button.text() == "Resetează"
    widget_names = {widget.objectName() for widget in page.findChildren(object)}
    assert "context_window" not in widget_names
    assert "reasoning_mode" not in widget_names
    assert page.operation_status_text() == "Ready."


def test_book_analysis_header_keeps_profile_and_actions_on_title_row(qtbot) -> None:
    page = _page(qtbot)
    page.resize(1000, 700)
    page.show()
    qtbot.waitExposed(page)

    title_center_y = page._title_label.geometry().center().y()
    header_controls = (
        page._profile_label,
        page._profile_combo,
        page._analyze_button,
        page._reset_button,
    )

    assert all(
        abs(control.geometry().center().y() - title_center_y) <= 2
        for control in header_controls
    )
    assert page._title_label.geometry().right() < page._profile_label.geometry().left()


def test_detailed_analysis_aligns_with_summary_and_frames_only_when_expanded(qtbot) -> None:
    page = _page(qtbot)
    page.set_analysis_state(
        state="completed",
        notes=["Completed."],
        report=_report(),
        report_stale=False,
        can_analyze=False,
        can_reset=True,
    )
    page.resize(1000, 700)
    page.show()
    qtbot.waitExposed(page)

    assert page._details_group.isFlat() is True
    assert page._details_group.height() <= page._details_group.fontMetrics().height() + 10

    page._details_group.setChecked(True)
    qtbot.wait(1)

    concise_x = page._concise_labels["book_type"].mapTo(page, QPoint(0, 0)).x()
    details_x = page._detail_labels["detailed_summary"].mapTo(page, QPoint(0, 0)).x()
    assert page._details_group.isFlat() is False
    assert abs(details_x - concise_x) <= 2


def test_book_analysis_report_field_labels_are_bold(qtbot) -> None:
    page = _page(qtbot)

    report_labels = (*page._concise_labels.values(), *page._detail_labels.values())

    assert report_labels
    assert all(label.font().bold() for label in report_labels)


def test_detailed_analysis_group_uses_the_scoped_theme_indicator(qtbot) -> None:
    page = _page(qtbot)

    assert page._details_group.objectName() == "bookAnalysisDetails"
