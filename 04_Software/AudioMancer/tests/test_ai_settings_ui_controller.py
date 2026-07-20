"""Focused persistence coverage for the AI Settings dialog controller."""

from types import SimpleNamespace
from unittest.mock import Mock

from audiomancer.ui.controllers import ai_settings_ui_controller


def test_apply_ai_settings_persists_reloads_and_refreshes_window(monkeypatch) -> None:
    """REQ-FUNC-025: Apply persists merged settings while leaving the dialog open."""
    merged_settings = {"ui": {"language": "en"}, "ai_profiles": [{"id": "local"}]}
    persisted_settings = {**merged_settings, "persisted": True}
    page = SimpleNamespace(build_settings=Mock(return_value=merged_settings))
    window = SimpleNamespace(
        _ai_settings_page=page,
        _ai_settings_dialog=SimpleNamespace(close=Mock()),
        _settings_payload={"previous": True},
        _current_project_root="project-root",
        _current_manifest={"project_name": "Demo"},
        show_project_state=Mock(),
    )
    save_settings = Mock()
    apply_ui_settings = Mock()
    show_message = Mock()
    monkeypatch.setattr(ai_settings_ui_controller.settings_service, "save_settings", save_settings)
    monkeypatch.setattr(ai_settings_ui_controller.settings_service, "load_settings", lambda: persisted_settings)
    monkeypatch.setattr(ai_settings_ui_controller.settings_ui_controller, "apply_current_ui_settings", apply_ui_settings)
    monkeypatch.setattr(ai_settings_ui_controller.misc_ui_controller, "show_message", show_message)

    ai_settings_ui_controller.apply_ai_settings_from_dialog(window)

    save_settings.assert_called_once_with(merged_settings)
    assert window._settings_payload == persisted_settings
    apply_ui_settings.assert_called_once_with(window)
    window.show_project_state.assert_called_once_with("project-root", {"project_name": "Demo"})
    window._ai_settings_dialog.close.assert_not_called()
    show_message.assert_called_once()
