"""Focused interaction coverage for the shared operation-progress dialog."""

from audiomancer.services import ui_state_service
from audiomancer.ui.operation_progress_dialog import OperationProgressDialog


def test_progress_dialog_localizes_title_cancel_and_token_usage(qtbot):
    """REQ-FUNC-019: render localized operation progress and usage totals."""
    dialog = OperationProgressDialog()
    qtbot.addWidget(dialog)

    dialog.apply_language("ro")
    dialog.start("Traducere", "Se pregătește", cancellable=True)
    dialog.update_progress(
        135,
        "În lucru",
        {"input_tokens": 1200, "output_tokens": 34, "total_tokens": 1234, "usage_available": True},
    )

    assert dialog.windowTitle() == ui_state_service.translate(
        "dialog.operation_progress_title", "ro"
    ).format(operation_name="Traducere")
    assert dialog._cancel_button.text() == ui_state_service.translate(
        "dialog.operation_progress_cancel", "ro"
    )
    assert dialog._progress_bar.value() == 100
    assert dialog.status_message() == "În lucru"
    assert dialog._token_usage_label.text() == ui_state_service.translate(
        "dialog.operation_progress_token_usage", "ro"
    ).format(input_tokens="1,200", output_tokens="34", total_tokens="1,234")
    assert dialog._token_usage_label.isVisible()
