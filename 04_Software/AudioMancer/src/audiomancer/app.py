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
@date 2026-04-04
@version 0.1.4
@example
    uv run audiomancer
"""

# IMPORTS

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import config
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
    @date       2026-04-04
    @version    0.1.4
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
