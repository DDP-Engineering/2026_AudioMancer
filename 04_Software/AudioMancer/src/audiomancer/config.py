#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file config.py
@brief Shared configuration constants for AudioMancer.
@details Centralizes application names, paths, defaults, artifact names, and
         file support used by the current AudioMancer implementation scaffold.
@author Eng. Dan Dumitru Pasare
@date 2026-04-04
@version 0.1.3
"""

# IMPORTS

from pathlib import Path

# CONSTANTS
# Application Identity And Root Paths
# @brief Operator-facing desktop application name.
APP_NAME = "AudioMancer"

# @brief Internal Python package name.
PACKAGE_NAME = "audiomancer"

# @brief Application subtree root resolved from the installed source layout.
APP_ROOT = Path(__file__).resolve().parents[2]

# @brief Absolute path to the app-level settings file.
APP_SETTINGS_PATH = APP_ROOT / "settings.json"

# Project Workspace And Artifact Naming
# @brief Standard non-operation directories created for each project workspace.
PROJECT_SUBDIRECTORIES = ("temp",)

# @brief Stable operation-folder file name for persisted state.
OPERATION_STATE_FILE_NAME = "state_operation.json"

# @brief Stable prefix used for copied operation-local input snapshots.
OPERATION_INPUT_FILE_PREFIX = "input_"

# @brief Stable prefix used for primary operation outputs.
OPERATION_OUTPUT_FILE_PREFIX = "output_"

# @brief Stable prefix used for operation artifacts and reports.
OPERATION_ARTIFACT_FILE_PREFIX = "artifact_"


# Source Import And Processing Artifacts
# @brief Supported import suffixes mapped to persisted source-type ids.
SUPPORTED_SOURCE_SUFFIXES = {".txt": "txt", ".pdf": "pdf"}

# @brief File name used for persisted raw extracted text.
EXTRACTED_TEXT_FILE_NAME = "raw_text.txt"

# @brief File name used for the extraction metadata report.
EXTRACTION_REPORT_FILE_NAME = "extraction_report.json"

# @brief File name used for persisted cleaned text.
CLEANED_TEXT_FILE_NAME = "clean_text.txt"

# @brief File name used for cleanup and chunking metadata.
CLEANUP_REPORT_FILE_NAME = "cleanup_report.json"

# @brief File name used for the persisted chunk list artifact.
CHUNK_ARTIFACT_FILE_NAME = "chunks.json"

# @brief File name used for persisted chunking metadata.
CHUNKING_REPORT_FILE_NAME = "chunking_report.json"

# @brief File name used for persisted translated chunk records.
TRANSLATED_CHUNKS_FILE_NAME = "translated_chunks.json"

# @brief File name used for persisted translation session metadata.
TRANSLATION_REPORT_FILE_NAME = "translation_report.json"

# @brief File name used for persisted discovered character profiles.
CHARACTER_PROFILE_FILE_NAME = "character_profiles.json"

# @brief File name used for persisted character-discovery metadata.
CHARACTER_DISCOVERY_REPORT_FILE_NAME = "character_discovery_report.json"


# Workflow And UI Defaults
# @brief Default initial workflow stage for a newly created project.
DEFAULT_WORKFLOW_STAGE = "project_created"

# @brief Default UI and workflow language code.
DEFAULT_LANGUAGE = "en"

# @brief Supported operator-selectable UI language codes.
SUPPORTED_LANGUAGES = ("en", "ro")

# @brief Default UI text-scale preset.
DEFAULT_UI_TEXT_SCALE = "normal"

# @brief Supported operator-selectable UI text-scale presets.
UI_TEXT_SCALE_OPTIONS = ("very_small", "small",
                         "normal", "large", "very_large")

# @brief Default flag controlling whether the app plays a completion beep.
DEFAULT_PLAY_COMPLETION_BEEP = False

# @brief Default initial main-window width.
DEFAULT_MAIN_WINDOW_WIDTH = 1100

# @brief Default initial main-window height.
DEFAULT_MAIN_WINDOW_HEIGHT = 700

# @brief Default minimum main-window width.
DEFAULT_MAIN_WINDOW_MIN_WIDTH = 960

# @brief Default minimum main-window height.
DEFAULT_MAIN_WINDOW_MIN_HEIGHT = 620


# AI Provider Profiles
# @brief Supported AI backend kinds for OpenAI-compatible providers.
LLM_BACKEND_OPTIONS = ("lmstudio", "ollama", "openai_compatible")

# @brief Default configured context window for AI profiles.
DEFAULT_LLM_CONTEXT_WINDOW = 8192

# @brief Default configured maximum output tokens for AI profiles.
DEFAULT_LLM_MAX_OUTPUT_TOKENS = 1024

# @brief Default timeout in seconds for AI provider requests.
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 90

# @brief Default temperature for AI cleanup and chunking requests.
DEFAULT_LLM_TEMPERATURE = 0.2

# AI Workflow Defaults
# @brief Default semantic AI chunking strategy.
DEFAULT_AI_CHUNKING_STRATEGY = "paragraph"

# @brief Supported semantic AI chunking strategies.
AI_CHUNKING_STRATEGY_OPTIONS = ("paragraph", "meaning", "scene")

# @brief Default target language for AI translation.
DEFAULT_TRANSLATION_TARGET_LANGUAGE = "en"

# @brief Supported target languages for the AI translation page.
TRANSLATION_LANGUAGE_OPTIONS = (
    ("en", "English"),
    ("ro", "Romanian"),
    ("de", "German"),
    ("fr", "French"),
    ("es", "Spanish"),
)

# @brief Default chunk-window size used for AI character discovery.
DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE = 8

# @brief Default chunk-window overlap used for AI character discovery.
DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP = 1


# Export Defaults
# @brief Default final export format.
DEFAULT_EXPORT_FORMAT = "mp3"

# @brief Default export bitrate in kilobits per second.
DEFAULT_EXPORT_BITRATE_KBPS = 128

# @brief Default export channel layout.
DEFAULT_EXPORT_CHANNELS = "stereo"

# @brief Default export split strategy.
DEFAULT_EXPORT_SPLIT_MODE = "single_file"


# Logging Defaults
# @brief Shared app-log directory name under the application root.
APP_LOG_DIRECTORY_NAME = "Logs"

# @brief Default app execution log output format.
DEFAULT_LOG_FORMAT = "text"

# @brief Default app execution log severity.
DEFAULT_LOG_LEVEL = "DEBUG"

# @brief Default number of days that app execution logs are retained.
DEFAULT_LOG_RETENTION_DAYS = 14

# @brief Default per-component app execution log-level overrides.
DEFAULT_LOG_LEVEL_OVERRIDES: dict[str, str] = {}

# @brief Supported app-log serialization formats.
LOG_FORMAT_OPTIONS = ("text", "json")

# @brief Supported log level names accepted by the logging layer.
LOG_LEVEL_OPTIONS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET")

# @brief Stable component logger identifiers used for per-component overrides.
AVAILABLE_LOG_COMPONENTS = (
    "app",
    "main_window",
    "settings",
    "ui_state",
)

# @brief Default flag controlling project-local AI exchange logging.
DEFAULT_AI_EXCHANGE_LOG_ENABLED = False

# @brief Default project-local AI exchange log output format.
DEFAULT_AI_EXCHANGE_LOG_FORMAT = "json"

# END OF FILE
