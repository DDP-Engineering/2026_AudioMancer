#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file app.py
@brief Desktop application bootstrap for AudioMancer.
@details Creates the Qt application instance, opens the main window, and
         starts the event loop for the initial UI scaffold.
@author Eng. Dan Dumitru Pasare
@date 2026-05-23
@version 0.1.6
@example
    uv run audiomancer
"""

# IMPORTS

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import config
from .services import ui_scroll_service, ui_state_service, ui_theme_service
from .services.logging_service import get_component_logger, initialize_logging, shutdown_logging
from .services.settings_service import load_settings
from .ui.main_window import MainWindow

# CONSTANTS

APPLICATION_NAME = config.APP_NAME

# PUBLIC API


def main() -> int:
    """
    @brief      Start the AudioMancer desktop application.
    @return     Process exit code returned by QApplication.exec().
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-23
    @version    0.1.6
    """
    log_file_path = initialize_logging()
    logger = get_component_logger("app")
    logger.info(
        "AudioMancer bootstrap started",
        extra={"func_name": "main", "event": "startup"},
    )

    try:
        settings_payload = load_settings()
        application = QApplication(sys.argv)
        application.setApplicationName(APPLICATION_NAME)
        application.setWindowIcon(QIcon(str(config.APP_ICON_PATH)))
        ui_scroll_service.install_global_scroll_step_filter(
            application,
            int(
                settings_payload.get(
                    "ui_scroll_steps_per_wheel_notch",
                    config.DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH,
                )
            ),
        )

        # Apply the persisted UI theme to the QApplication BEFORE the main
        # window is constructed. QApplication.setFont() does not retroactively
        # re-layout widgets that were already built with the previous default
        # font, so applying the theme only after MainWindow creation leaves
        # the operator-chosen font and palette invisible at startup. Doing it
        # here means every widget built by MainWindow inherits the themed
        # font, palette and stylesheet from the moment of construction.
        startup_theme = ui_theme_service.theme_by_id(
            settings_payload.get("ui_theme_id", config.DEFAULT_UI_THEME_ID),
            settings_payload.get("ui_themes", []),
        )
        ui_state_service.apply_theme(application, startup_theme, None)

        window = MainWindow(settings_payload=settings_payload)
        window.show()

        exit_code = application.exec()
        logger.info(
            "AudioMancer bootstrap finished",
            extra={
                "func_name": "main",
                "event": "shutdown",
                "result": f"exit_code={exit_code}",
            },
        )
        return exit_code
    except Exception:
        logger.exception(
            f"AudioMancer bootstrap failed. Log file: {log_file_path}",
            extra={"func_name": "main", "event": "fatal-bootstrap-error"},
        )
        raise
    finally:
        shutdown_logging()


# END OF FILE
