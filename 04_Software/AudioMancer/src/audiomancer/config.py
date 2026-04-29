#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
@date 2026-04-21
@version 1.36.0
"""

# IMPORTS

from pathlib import Path
import sys

# CONSTANTS
# Application Identity
# @brief Operator-facing desktop application name.
APP_NAME = "AudioMancer"

# @brief Internal Python package name.
PACKAGE_NAME = "audiomancer"


# PUBLIC API


def resolve_app_runtime_root() -> Path:
    """
    @brief      Resolve the root folder that owns runtime resource files.
    @return     Runtime resource root for source, installed, or PyInstaller layouts.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    package_root = Path(__file__).resolve().parent
    if bool(getattr(sys, "frozen", False)):
        return _resolve_frozen_runtime_root()
    source_root = _source_tree_root_from_package(package_root)
    if source_root is not None:
        return source_root
    installed_resource_root = _installed_resource_root_from_package(package_root)
    if installed_resource_root is not None:
        return installed_resource_root
    return package_root


# LOCAL HELPERS


def _resolve_frozen_runtime_root() -> Path:
    """
    @brief      Resolve runtime resources in a PyInstaller execution layout.
    @return     Folder containing packaged runtime resources.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    executable_root = Path(sys.executable).resolve().parent
    meipass_root = _optional_meipass_root()
    for candidate_root in _unique_paths([executable_root, meipass_root]):
        if _has_runtime_resource_markers(candidate_root):
            return candidate_root
    return executable_root


def _optional_meipass_root() -> Path | None:
    """
    @brief      Resolve the optional PyInstaller extraction folder.
    @return     `_MEIPASS` path when provided by the bootloader, otherwise `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    meipass_value = str(getattr(sys, "_MEIPASS", "") or "").strip()
    if not meipass_value:
        return None
    return Path(meipass_value).resolve()


def _source_tree_root_from_package(package_root: Path) -> Path | None:
    """
    @brief      Resolve the application root when running from a source tree.
    @param[in]  package_root Imported Python package folder.
    @return     Source application root or `None` when not in a source checkout.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    for candidate_root in package_root.parents:
        if (candidate_root / "pyproject.toml").is_file() and (candidate_root / "src" / PACKAGE_NAME).is_dir():
            return candidate_root
    return None


def _installed_resource_root_from_package(package_root: Path) -> Path | None:
    """
    @brief      Resolve package-adjacent resources for installed wheel layouts.
    @param[in]  package_root Imported Python package folder.
    @return     Installed resource root or `None` when no marker files are present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    for candidate_root in _unique_paths([package_root, package_root.parent]):
        if _has_runtime_resource_markers(candidate_root):
            return candidate_root
    return None


def _has_runtime_resource_markers(candidate_root: Path | None) -> bool:
    """
    @brief      Return whether one folder looks like an AudioMancer runtime root.
    @param[in]  candidate_root Candidate resource folder.
    @return     True when expected resource markers are present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if candidate_root is None:
        return False
    return (
        (candidate_root / "settings.json").is_file()
        or (candidate_root / "prompts").is_dir()
        or (candidate_root / "help").is_dir()
        or (candidate_root / "LICENSE.txt").is_file()
    )


def _unique_paths(paths: list[Path | None]) -> list[Path]:
    """
    @brief      Return unique existing path objects while preserving order.
    @param[in]  paths Candidate paths.
    @return     De-duplicated path list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    unique_values: list[Path] = []
    seen_values: set[str] = set()
    for path in paths:
        if path is None:
            continue
        resolved_path = Path(path).resolve()
        path_key = str(resolved_path).casefold()
        if path_key in seen_values:
            continue
        unique_values.append(resolved_path)
        seen_values.add(path_key)
    return unique_values


# CONSTANTS
# Application Root Paths
# @brief Imported Python package root.
APP_PACKAGE_ROOT = Path(__file__).resolve().parent

# @brief Source-tree root when available; falls back to the runtime root outside source checkouts.
APP_SOURCE_ROOT = _source_tree_root_from_package(APP_PACKAGE_ROOT) or resolve_app_runtime_root()

# @brief Application runtime root containing settings, prompts, help, and license resources.
APP_ROOT = resolve_app_runtime_root()

# @brief Absolute path to the app-level settings file.
APP_SETTINGS_PATH = APP_ROOT / "settings.json"

# @brief Absolute path to the application-owned prompt template folder.
APP_PROMPTS_PATH = APP_ROOT / "prompts"

# @brief Absolute path to the packaged application icon file.
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icons" / "audiomancer.ico"

# @brief Relative paths to packaged user-guide HTML entry points by UI language.
APP_HELP_INDEX_RELATIVE_PATHS = {
    "en": Path("help") / "en" / "index.html",
    "ro": Path("help") / "ro" / "index.html",
}

# @brief Relative path to the packaged English user-guide HTML entry point.
APP_HELP_INDEX_RELATIVE_PATH = Path("help") / "en" / "index.html"

# @brief Source-tree user-guide HTML entry points used during development.
APP_HELP_SOURCE_INDEX_PATHS = {
    "en": APP_SOURCE_ROOT.parents[1] / "05_SoftwareDocu" / "UserGuide" / "index.html",
    "ro": APP_SOURCE_ROOT.parents[1] / "05_SoftwareDocu" / "UserGuide_ro" / "index.html",
}

# @brief Source-tree English user-guide HTML entry point used during development.
APP_HELP_SOURCE_INDEX_PATH = APP_SOURCE_ROOT.parents[1] / "05_SoftwareDocu" / "UserGuide" / "index.html"

# Project Workspace And Artifact Naming
# @brief Stable manifest file name stored at the project root.
PROJECT_MANIFEST_FILE_NAME = "project.json"

# @brief Stable relative path used by root-level runtime operation artifacts.
PROJECT_ROOT_ARTIFACT_RELATIVE_PATH = "."

# @brief Stable ordered workflow stage identifiers used by the current project shell.
PROJECT_WORKFLOW_STAGES = (
    "project_created",
    "source_selected",
    "text_cleanup_ready",
    "text_chunking_ready",
    "translation_ready",
    "character_discovery_ready",
    "narrator_definition_ready",
    "character_voices_ready",
    "speech_blocks_ready",
    "audio_blocks_ready",
    "audio_assembly_ready",
)

# @brief Characters rejected for exact project folder names across Windows and Linux.
INVALID_PROJECT_NAME_CHARACTERS = '<>:"/\\|?*\x00'

# @brief Reserved Linux directory names that cannot be used as project roots.
LINUX_RESERVED_DIRECTORY_NAMES = (".", "..")

# @brief Reserved Windows device names that cannot be used as project roots.
WINDOWS_RESERVED_DIRECTORY_NAMES = (
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
)

# @brief Stable prefix used for project-local AI transaction logs.
AI_TRANSACTION_LOG_FILE_PREFIX = "log_ai_"

# @brief Stable extension used for project-local AI transaction logs.
AI_TRANSACTION_LOG_FILE_EXTENSION = ".log"


# Source Import And Processing Artifacts
# @brief Supported import suffixes mapped to persisted source-type ids.
SUPPORTED_SOURCE_SUFFIXES = {
    ".txt": "txt",
    ".pdf": "pdf",
    ".rtf": "rtf",
    ".docx": "docx",
    ".odt": "odt",
    ".md": "md",
    ".epub": "epub",
}

# @brief File name used for persisted raw extracted text.
EXTRACTED_TEXT_FILE_NAME = "extracted_text.txt"

# @brief File name used for the extraction metadata report.
EXTRACTION_REPORT_FILE_NAME = "extraction_report.json"

# @brief File name used for persisted extraction runtime state.
EXTRACTION_STATE_FILE_NAME = "extraction_state.json"

# @brief File name used for persisted cleaned text.
CLEANED_TEXT_FILE_NAME = "clean_text.txt"

# @brief File name used for persisted cleaned-text paragraph metadata.
CLEANED_TEXT_METADATA_FILE_NAME = "clean_text_metadata.json"

# @brief File name used for cleanup metadata.
CLEANUP_REPORT_FILE_NAME = "cleanup_report.json"

# @brief File name used for persisted cleanup runtime state.
CLEANUP_STATE_FILE_NAME = "cleanup_state.json"

# @brief File name used for the persisted chunk list artifact.
CHUNK_ARTIFACT_FILE_NAME = "chunks_text.json"

# @brief File name used for persisted chunking metadata.
CHUNKING_REPORT_FILE_NAME = "chunking_report.json"

# @brief File name used for persisted chunking runtime state.
CHUNKING_STATE_FILE_NAME = "chunking_state.json"

# @brief File name used for persisted translated chunk records.
TRANSLATED_CHUNKS_FILE_NAME = "translated_text.json"

# @brief File name used for persisted translation session metadata.
TRANSLATION_REPORT_FILE_NAME = "translation_report.json"

# @brief File name used for persisted translation runtime state.
TRANSLATION_STATE_FILE_NAME = "translation_state.json"

# @brief File name used for persisted discovered character profiles.
CHARACTER_PROFILE_FILE_NAME = "characters_profile.json"

# @brief File name used for persisted character-discovery metadata.
CHARACTER_DISCOVERY_REPORT_FILE_NAME = "characters_report.json"

# @brief File name used for persisted character-discovery runtime state.
CHARACTER_DISCOVERY_STATE_FILE_NAME = "characters_state.json"

# @brief File name used for persisted narrator-definition profile records.
NARRATOR_PROFILE_FILE_NAME = "audio_profiles.json"

# @brief File name used for persisted narrator-definition selection state.
NARRATOR_SELECTION_FILE_NAME = "narator.json"

# @brief File name used for persisted character-voices target records.
CHARACTER_VOICES_TARGETS_FILE_NAME = "characters_voice.json"

# @brief File name used for the selected narrator sample at the project root.
SELECTED_NARRATOR_AUDIO_FILE_NAME = "narator.wav"

# @brief File name used for the selected narrator sample metadata at the project root.
SELECTED_NARRATOR_METADATA_FILE_NAME = "narator_sample.json"

# @brief File name used for persisted Speech Blocks output.
SPEECH_BLOCKS_OUTPUT_FILE_NAME = "speech_blocks.json"

# @brief File name used for persisted Speech Blocks report metadata.
SPEECH_BLOCKS_REPORT_FILE_NAME = "speech_blocks_report.json"

# @brief File name used for persisted Speech Blocks runtime state.
SPEECH_BLOCKS_STATE_FILE_NAME = "speech_blocks_state.json"

# @brief Default pause duration used when a pause Speech Block has no valid duration.
DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS = 1000

# @brief Minimum estimated source-text token budget required for one AI Speech Blocks request.
DEFAULT_SPEECH_BLOCKS_MIN_TEXT_BUDGET_TOKENS = 512

# @brief Minimum estimated token safety margin reserved in each AI Speech Blocks request.
DEFAULT_SPEECH_BLOCKS_MIN_SAFETY_MARGIN_TOKENS = 256

# @brief Fraction of the context window reserved as safety margin for AI Speech Blocks.
DEFAULT_SPEECH_BLOCKS_SAFETY_MARGIN_CONTEXT_FRACTION = 0.10

# @brief Maximum context-window fraction used for AI Speech Blocks source text.
DEFAULT_SPEECH_BLOCKS_TEXT_CONTEXT_FRACTION = 0.60

# @brief File name used for persisted Audio Blocks output.
AUDIO_BLOCKS_OUTPUT_FILE_NAME = "audio_blocks.json"

# @brief File name used for persisted Audio Blocks report metadata.
AUDIO_BLOCKS_REPORT_FILE_NAME = "audio_blocks_report.json"

# @brief File name used for persisted Audio Blocks runtime state.
AUDIO_BLOCKS_STATE_FILE_NAME = "audio_blocks_state.json"

# @brief File name used for persisted Audio Blocks voice-clone profile metadata.
AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME = "voice_clone_profiles.json"

# @brief Folder name used for generated per-speech-block audio artifacts.
AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME = "audio_blocks"

# @brief File name used for persisted Audio Assembly report metadata.
AUDIO_ASSEMBLY_REPORT_FILE_NAME = "audio_assembly_report.json"

# @brief File name used for persisted Audio Assembly runtime state.
AUDIO_ASSEMBLY_STATE_FILE_NAME = "audio_assembly_state.json"

# @brief Folder name used for generated final audiobook deliverables.
AUDIOBOOK_OUTPUT_FOLDER_NAME = "audiobook"


def ai_transaction_log_file_name(operation_kind: str, timestamp_token: str) -> str:
    """
    @brief      Compose one project-local AI transaction log file name.
    @param[in]  operation_kind Stable AI operation token.
    @param[in]  timestamp_token Filesystem-safe date/time token.
    @return     AI log file name.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    normalized_operation = str(operation_kind).strip().replace("-", "_")
    normalized_timestamp = str(timestamp_token).strip()
    return (
        f"{AI_TRANSACTION_LOG_FILE_PREFIX}{normalized_operation}_{normalized_timestamp}"
        f"{AI_TRANSACTION_LOG_FILE_EXTENSION}"
    )


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
UI_TEXT_SCALE_OPTIONS = ("very_small", "small", "normal", "large", "very_large")

# @brief Default flag controlling whether the app plays a completion beep.
DEFAULT_PLAY_COMPLETION_BEEP = False

# @brief Default initial main-window width.
DEFAULT_MAIN_WINDOW_WIDTH = 1040

# @brief Default initial main-window height.
DEFAULT_MAIN_WINDOW_HEIGHT = 660

# @brief Default minimum main-window width.
DEFAULT_MAIN_WINDOW_MIN_WIDTH = 900

# @brief Default minimum main-window height.
DEFAULT_MAIN_WINDOW_MIN_HEIGHT = 560


# AI Provider Profiles
# @brief Supported AI backend kinds for OpenAI-compatible providers.
LLM_BACKEND_OPTIONS = ("lmstudio", "ollama", "openai_compatible")

# @brief Default configured context window for AI profiles.
DEFAULT_LLM_CONTEXT_WINDOW = 16384

# @brief Default configured maximum output tokens for AI profiles.
DEFAULT_LLM_MAX_OUTPUT_TOKENS = 8192

# @brief Default timeout in seconds for AI provider requests.
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 300

# @brief Default retry count for transient AI provider request failures.
DEFAULT_LLM_REQUEST_RETRY_COUNT = 2

# @brief Default timeout in seconds for AI backend connect/probe requests.
DEFAULT_AI_CONNECT_TIMEOUT_SECONDS = 3

# @brief Default temperature for AI cleanup and chunking requests.
DEFAULT_LLM_TEMPERATURE = 0.2


# TTS Runtime Defaults
# @brief Default base URL used for the local VoiceWeaver runtime.
DEFAULT_TTS_RUNTIME_BASE_URL = "http://127.0.0.1:8059"

# @brief Default bearer token used when the runtime requires authentication.
DEFAULT_TTS_RUNTIME_API_KEY = ""

# @brief Default connection timeout in seconds for VoiceWeaver probe requests.
DEFAULT_TTS_CONNECT_TIMEOUT_SECONDS = 5

# @brief Default timeout in seconds for narrator preview-sample generation requests.
DEFAULT_TTS_AUDIO_PREVIEW_TIMEOUT_SECONDS = 60

# @brief Default timeout in seconds for long-form audio generation requests.
DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS = 300

# @brief Default maximum narrator preview text length for TTS samples.
DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT = 512

# @brief Default per-project narrator voice-assignment mode.
DEFAULT_TTS_VOICE_ASSIGNMENT_MODE = "narrator_and_characters"

# @brief Supported narrator voice-assignment modes for one project.
TTS_VOICE_ASSIGNMENT_MODE_OPTIONS = ("same_narrator", "narrator_and_characters")

# @brief Conservative fallback max_new_tokens budget used before the TTS model reports one.
DEFAULT_TTS_NARRATOR_ONLY_TOKEN_BUDGET = 2048

# @brief Approximate generated-audio seconds represented by one VoiceWeaver max_new_tokens unit.
DEFAULT_TTS_APPROX_AUDIO_SECONDS_PER_TOKEN = 0.08

# @brief Safety factor applied when asking AI to split narrator-only Speech Blocks.
DEFAULT_TTS_SPLIT_SAFETY_FACTOR = 0.85

# @brief Approximate spoken-word rate used to convert audio token budget into text guidance.
DEFAULT_TTS_WORDS_PER_AUDIO_SECOND = 2.5

# AI Workflow Defaults
# @brief Default maximum cleanup-unit count sent in one AI cleanup request window.
DEFAULT_AI_CLEANUP_MAX_WINDOW_UNITS = 24

# @brief Minimum estimated text-token budget required for one AI cleanup request.
DEFAULT_AI_CLEANUP_MIN_TEXT_BUDGET_TOKENS = 512

# @brief Minimum estimated token safety margin reserved in each AI cleanup request.
DEFAULT_AI_CLEANUP_MIN_SAFETY_MARGIN_TOKENS = 256

# @brief Fraction of the context window reserved as safety margin for AI cleanup.
DEFAULT_AI_CLEANUP_SAFETY_MARGIN_CONTEXT_FRACTION = 0.10

# @brief Maximum context-window fraction used for AI cleanup unit text.
DEFAULT_AI_CLEANUP_TEXT_CONTEXT_FRACTION = 0.60

# @brief Default semantic AI chunking strategy.
DEFAULT_AI_CHUNKING_STRATEGY = "paragraph"

# @brief Supported semantic AI chunking strategies.
AI_CHUNKING_STRATEGY_OPTIONS = ("paragraph", "meaning", "scene")

# @brief Default paragraph cap per AI chunk-boundary request for paragraph strategy.
DEFAULT_AI_CHUNKING_PARAGRAPH_WINDOW_SIZE = 64

# @brief Default paragraph cap per AI chunk-boundary request for meaning strategy.
DEFAULT_AI_CHUNKING_MEANING_WINDOW_SIZE = 96

# @brief Default paragraph cap per AI chunk-boundary request for scene strategy.
DEFAULT_AI_CHUNKING_SCENE_WINDOW_SIZE = 128

# @brief Strategy-specific paragraph caps used by AI chunking requests.
AI_CHUNKING_WINDOW_SIZE_BY_STRATEGY = {
    "paragraph": DEFAULT_AI_CHUNKING_PARAGRAPH_WINDOW_SIZE,
    "meaning": DEFAULT_AI_CHUNKING_MEANING_WINDOW_SIZE,
    "scene": DEFAULT_AI_CHUNKING_SCENE_WINDOW_SIZE,
}

# @brief Minimum estimated text-token budget required for one AI chunking request.
DEFAULT_AI_CHUNKING_MIN_TEXT_BUDGET_TOKENS = 512

# @brief Minimum estimated token safety margin reserved in each AI chunking request.
DEFAULT_AI_CHUNKING_MIN_SAFETY_MARGIN_TOKENS = 256

# @brief Fraction of the context window reserved as safety margin for AI chunking.
DEFAULT_AI_CHUNKING_SAFETY_MARGIN_CONTEXT_FRACTION = 0.10

# @brief Maximum context-window fraction used for AI chunking paragraph text.
DEFAULT_AI_CHUNKING_TEXT_CONTEXT_FRACTION = 0.60

# @brief Default target language for AI translation.
DEFAULT_TRANSLATION_TARGET_LANGUAGE = "en"

# @brief Minimum estimated source-text token budget required for one AI translation request.
DEFAULT_AI_TRANSLATION_MIN_TEXT_BUDGET_TOKENS = 512

# @brief Minimum estimated token safety margin reserved in each AI translation request.
DEFAULT_AI_TRANSLATION_MIN_SAFETY_MARGIN_TOKENS = 256

# @brief Fraction of the context window reserved as safety margin for AI translation.
DEFAULT_AI_TRANSLATION_SAFETY_MARGIN_CONTEXT_FRACTION = 0.10

# @brief Maximum context-window fraction used for AI translation source text.
DEFAULT_AI_TRANSLATION_TEXT_CONTEXT_FRACTION = 0.60

# @brief Supported target languages for the AI translation page.
TRANSLATION_LANGUAGE_OPTIONS = (
    ("en", "English"),
    ("ro", "Romanian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh", "Chinese"),
    ("de", "German"),
    ("fr", "French"),
    ("ru", "Russian"),
    ("pt", "Portuguese"),
    ("es", "Spanish"),
    ("it", "Italian"),
)

# @brief Default chunk-window size used for AI character discovery.
DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE = 8

# @brief Default chunk-window overlap used for AI character discovery.
DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP = 1

# @brief Minimum estimated source-text token budget required for one AI character-discovery request.
DEFAULT_CHARACTER_DISCOVERY_MIN_TEXT_BUDGET_TOKENS = 512

# @brief Minimum estimated token safety margin reserved in each AI character-discovery request.
DEFAULT_CHARACTER_DISCOVERY_MIN_SAFETY_MARGIN_TOKENS = 256

# @brief Fraction of the context window reserved as safety margin for AI character discovery.
DEFAULT_CHARACTER_DISCOVERY_SAFETY_MARGIN_CONTEXT_FRACTION = 0.10

# @brief Maximum context-window fraction used for AI character-discovery input text.
DEFAULT_CHARACTER_DISCOVERY_TEXT_CONTEXT_FRACTION = 0.60

# @brief Default maximum evidence item count retained in one character synthesis payload.
DEFAULT_CHARACTER_DISCOVERY_SYNTHESIS_MAX_EVIDENCE_ITEMS = 20


# Export Defaults
# @brief Default final export format.
DEFAULT_EXPORT_FORMAT = "mp3"

# @brief Default export bitrate in kilobits per second.
DEFAULT_EXPORT_BITRATE_KBPS = 128

# @brief Default export channel layout.
DEFAULT_EXPORT_CHANNELS = "stereo"

# @brief Default export split strategy.
DEFAULT_EXPORT_SPLIT_MODE = "single_file"

# @brief Supported output modes for Audio Assembly.
AUDIO_ASSEMBLY_OUTPUT_MODE_OPTIONS = ("per_chunk", "time_limit", "whole_book")

# @brief Supported output formats for Audio Assembly.
AUDIO_ASSEMBLY_OUTPUT_FORMAT_OPTIONS = ("wav",)

# @brief Default Audio Assembly output mode.
DEFAULT_AUDIO_ASSEMBLY_OUTPUT_MODE = "whole_book"

# @brief Default Audio Assembly time-limit split length in minutes.
DEFAULT_AUDIO_ASSEMBLY_MAX_DURATION_MINUTES = 30

# @brief Default Audio Assembly output format.
DEFAULT_AUDIO_ASSEMBLY_OUTPUT_FORMAT = "wav"

# @brief Default silence between adjacent speech audio blocks.
DEFAULT_AUDIO_ASSEMBLY_INTER_BLOCK_SILENCE_MS = 250

# @brief Default silence between adjacent source chunks in the same output.
DEFAULT_AUDIO_ASSEMBLY_INTER_CHUNK_SILENCE_MS = 1000


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
    "ai_backend",
    "ai_cleanup",
    "ai_chunking",
    "ai_translation",
    "audio_assembly",
    "audio_blocks",
    "character_discovery",
    "deterministic_cleanup",
    "deterministic_chunking",
    "llm_provider",
    "main_window",
    "operation_runtime",
    "prompt_template",
    "settings",
    "project_workspace",
    "text_extraction",
    "ui_state",
    "voiceweaver_runtime",
)

# @brief Default flag controlling project-local AI exchange logging.
DEFAULT_AI_EXCHANGE_LOG_ENABLED = False

# @brief Default project-local AI exchange log output format.
DEFAULT_AI_EXCHANGE_LOG_FORMAT = "json"

# END OF FILE
