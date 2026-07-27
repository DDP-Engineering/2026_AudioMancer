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
         Keeps the read-only packaged resource root separate from the resolved
         writable data root that owns settings and logs, and from the per-user
         documents folder offered by operator-facing folder pickers.
@author Eng. Dan Dumitru Pasare
@date 2026-07-25
@version 1.44.0
"""

# IMPORTS

import os
from pathlib import Path
import sys
import tempfile

# CONSTANTS
# Application Identity
# @brief Operator-facing desktop application name.
APP_NAME = "AudioMancer"

# @brief Internal Python package name.
PACKAGE_NAME = "audiomancer"

# @brief Environment variable that pins the writable application data root.
APP_DATA_DIR_ENVIRONMENT_VARIABLE = "AUDIOMANCER_DATA_DIR"

# @brief Prefix used by the transient probe file that tests directory writability.
_WRITE_PROBE_FILE_PREFIX = ".audiomancer_write_probe_"

# @brief On-disk name of the per-user documents folder; Windows localizes only its display name.
_USER_DOCUMENTS_DIRECTORY_NAME = "Documents"

# @brief freedesktop.org variable that relocates the per-user documents folder on POSIX.
_XDG_DOCUMENTS_DIR_ENVIRONMENT_VARIABLE = "XDG_DOCUMENTS_DIR"


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


def resolve_user_data_root(app_root: Path | None = None) -> Path:
    """
    @brief      Resolve the folder that owns writable application data.
    @details    Candidates are tried in order: the explicit
                `AUDIOMANCER_DATA_DIR` override, then the application root when a
                probe file proves it writable (portable and source layouts), then
                the per-user location standard for the running platform. The
                PyInstaller extraction folder is never accepted, because a
                onefile bootloader deletes it on exit.
    @param[in]  app_root Optional resolved application root reused by the caller.
    @return     Absolute writable data root; the folder may not exist yet.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    override_root = _explicit_data_root_override()
    if override_root is not None:
        return override_root
    candidate_app_root = resolve_app_runtime_root() if app_root is None else Path(app_root).resolve()
    if _is_portable_data_root(candidate_app_root):
        return candidate_app_root
    return _per_user_data_root()


def resolve_user_documents_root() -> Path:
    """
    @brief      Resolve the per-user documents folder that project dialogs start in.
    @details    Candidates are tried in order and the first existing directory
                wins: the `XDG_DOCUMENTS_DIR` override on POSIX platforms other
                than macOS, the home documents folder, and finally the home
                directory itself. Every candidate must already exist, because
                `QFileDialog` silently falls back to the process working
                directory when handed a missing path.
    @return     Absolute per-user documents root, independent of `APP_ROOT`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    for candidate_root in (_xdg_documents_root(), Path.home() / _USER_DOCUMENTS_DIRECTORY_NAME):
        if candidate_root is not None and candidate_root.is_dir():
            return candidate_root.resolve()
    return Path.home().resolve()


# LOCAL HELPERS


def _xdg_documents_root() -> Path | None:
    """
    @brief      Resolve the freedesktop.org documents override, when it applies.
    @details    The variable is meaningless on Windows and macOS, so any value
                found there is accidental and is ignored.
    @return     Override path, or `None` off POSIX or when the variable is blank.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return None
    override_value = str(os.environ.get(_XDG_DOCUMENTS_DIR_ENVIRONMENT_VARIABLE, "") or "").strip()
    if not override_value:
        return None
    return Path(override_value).expanduser()


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


def _explicit_data_root_override() -> Path | None:
    """
    @brief      Resolve the operator-pinned writable data root, when configured.
    @details    An explicit instruction is honoured without a writability probe:
                a bad value must surface as a normal settings or logging error
                rather than being silently ignored.
    @return     Override path or `None` when the variable is unset or blank.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    override_value = str(os.environ.get(APP_DATA_DIR_ENVIRONMENT_VARIABLE, "") or "").strip()
    if not override_value:
        return None
    return Path(override_value).expanduser().resolve()


def _is_portable_data_root(candidate_root: Path) -> bool:
    """
    @brief      Return whether one application root may also own writable data.
    @param[in]  candidate_root Resolved application root.
    @return     True for a writable root that is not the frozen extraction folder.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    if _is_frozen_extraction_root(candidate_root):
        return False
    return _directory_accepts_writes(candidate_root)


def _is_frozen_extraction_root(candidate_root: Path) -> bool:
    """
    @brief      Return whether one folder is the PyInstaller extraction folder.
    @param[in]  candidate_root Resolved candidate folder.
    @return     True when the candidate is `_MEIPASS` or lives inside it.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    extraction_root = _optional_meipass_root()
    if extraction_root is None:
        return False
    return candidate_root == extraction_root or extraction_root in candidate_root.parents


def _directory_accepts_writes(candidate_root: Path) -> bool:
    """
    @brief      Return whether one existing directory accepts a new file.
    @details    Writability is proven by creating and removing a probe file
                rather than by `os.access`, which on Windows only reflects the
                read-only attribute and reports `C:\\Program Files` as writable.
    @param[in]  candidate_root Candidate directory.
    @return     True when a probe file could be created and removed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    if not candidate_root.is_dir():
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=candidate_root, prefix=_WRITE_PROBE_FILE_PREFIX):
            return True
    except OSError:
        return False


def _per_user_data_root() -> Path:
    """
    @brief      Resolve the per-user application data folder for this platform.
    @return     Absolute per-user data root; the folder may not exist yet.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    if sys.platform.startswith("win"):
        return _windows_per_user_data_root()
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / APP_NAME).resolve()
    return _xdg_per_user_data_root()


def _windows_per_user_data_root() -> Path:
    """
    @brief      Resolve the Windows per-user application data folder.
    @return     `%LOCALAPPDATA%`, `%APPDATA%`, or the default local app-data path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    for variable_name in ("LOCALAPPDATA", "APPDATA"):
        base_value = str(os.environ.get(variable_name, "") or "").strip()
        if base_value:
            return (Path(base_value) / APP_NAME).resolve()
    return (Path.home() / "AppData" / "Local" / APP_NAME).resolve()


def _xdg_per_user_data_root() -> Path:
    """
    @brief      Resolve the XDG per-user application data folder.
    @return     `$XDG_DATA_HOME` based path or the `~/.local/share` default.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    base_value = str(os.environ.get("XDG_DATA_HOME", "") or "").strip()
    if base_value:
        return (Path(base_value) / APP_NAME).resolve()
    return (Path.home() / ".local" / "share" / APP_NAME).resolve()


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

# @brief Writable root owning per-user data; equals APP_ROOT for portable and source layouts.
APP_USER_DATA_ROOT = resolve_user_data_root(APP_ROOT)

# @brief Absolute path to the read-only packaged settings scaffold used to seed a fresh install.
APP_DEFAULT_SETTINGS_PATH = APP_ROOT / "settings.json"

# @brief Absolute path to the active, writable app-level settings file.
APP_SETTINGS_PATH = APP_USER_DATA_ROOT / "settings.json"

# @brief Absolute path to the application-owned prompt template folder.
APP_PROMPTS_PATH = APP_ROOT / "prompts"

# @brief Absolute path to the packaged application icon file.
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icons" / "audiomancer.ico"

# @brief Relative paths to packaged user-guide HTML entry points by UI language.
APP_HELP_INDEX_RELATIVE_PATHS = {
    "en": Path("help") / "en" / "index.html",
    "ro": Path("help") / "ro" / "index.html",
}

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

# @brief Canonical ordered workflow operation kinds shared by runtime, impact, and workspace layers.
WORKFLOW_OPERATION_ORDER = (
    "extraction",
    "cleanup",
    "chunking",
    "translation",
    "character_discovery",
    "narrator_definition",
    "character_voices",
    "speech_blocks",
    "audio_blocks",
    "audio_assembly",
)

# @brief Workflow stage milestone promoted by each completed operation.
OPERATION_STAGE_BY_KIND = {
    "cleanup": "text_cleanup_ready",
    "chunking": "text_chunking_ready",
    "translation": "translation_ready",
    "character_discovery": "character_discovery_ready",
    "narrator_definition": "narrator_definition_ready",
    "character_voices": "character_voices_ready",
    "speech_blocks": "speech_blocks_ready",
    "audio_blocks": "audio_blocks_ready",
    "audio_assembly": "audio_assembly_ready",
}

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

# @brief Canonical structural ledger paired with extracted_text.txt.
SOURCE_LEDGER_FILE_NAME = "source_ledger.json"

# @brief Authoritative deterministic text-extraction metadata file name.
EXTRACTION_METADATA_FILE_NAME = "extraction_metadata.json"

# @brief File name used for persisted cleaned text.
CLEANED_TEXT_FILE_NAME = "clean_text.txt"

# @brief Authoritative AI-assisted cleanup document file name.
CLEANUP_DOCUMENT_FILE_NAME = "cleanup.json"

# @brief File name used for persisted cleaned-text paragraph metadata.
CLEANED_TEXT_METADATA_FILE_NAME = "clean_text_metadata.json"

# @brief File name used for cleanup metadata.
CLEANUP_REPORT_FILE_NAME = "cleanup_report.json"

# @brief File name used for persisted cleanup runtime state.
CLEANUP_STATE_FILE_NAME = "cleanup_state.json"

# @brief File name used for the persisted chunk list artifact.
CHUNK_ARTIFACT_FILE_NAME = "chunks_text.json"

# @brief File name used for persisted translated chunk records.
TRANSLATED_CHUNKS_FILE_NAME = "translated_text.json"

# @brief File name used for the authoritative Character Discovery document.
CHARACTERS_DOCUMENT_FILE_NAME = "characters.json"

# @brief File name used for the authoritative Narrator Voice document.
NARRATOR_VOICE_FILE_NAME = "narrator_voice.json"

# @brief File name used for persisted character-voices target records.
CHARACTER_VOICES_TARGETS_FILE_NAME = "characters_voice.json"

# @brief File name used for the authoritative single Speech Blocks document.
SPEECH_BLOCKS_DOCUMENT_FILE_NAME = "speech_blocks.json"

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

# @brief File name used for the authoritative single Audio Blocks document.
AUDIO_BLOCKS_DOCUMENT_FILE_NAME = "audio_blocks.json"

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

# @brief Ordered, operator-selectable UI font-size steps (extra small -> huge).
UI_FONT_SIZE_STEPS = ("extra_small", "small", "medium", "normal", "large", "very_large", "huge")

# @brief Default control/interface font-size step.
DEFAULT_UI_FONT_SIZE_STEP = "normal"

# @brief Default text-window (editor) font-size step.
DEFAULT_TEXT_FONT_SIZE_STEP = "normal"

# @brief Default selected UI theme identifier.
DEFAULT_UI_THEME_ID = "audiomancer_dark"

# @brief Current persisted UI theme schema version.
UI_THEME_SCHEMA_VERSION = 1

# @brief Default flag controlling whether the app plays a completion beep.
DEFAULT_PLAY_COMPLETION_BEEP = False

# @brief Default mouse-wheel scroll steps per physical wheel notch.
DEFAULT_UI_SCROLL_STEPS_PER_WHEEL_NOTCH = 1

# @brief Minimum accepted mouse-wheel scroll steps per physical wheel notch.
MIN_UI_SCROLL_STEPS_PER_WHEEL_NOTCH = 1

# @brief Maximum accepted mouse-wheel scroll steps per physical wheel notch.
MAX_UI_SCROLL_STEPS_PER_WHEEL_NOTCH = 5

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

# @brief Backend kind treated as an online AI provider for request-window sizing.
ONLINE_AI_BACKEND_KIND = "openai_compatible"

# @brief Context-window fraction used as text budget for online AI providers.
DEFAULT_ONLINE_AI_TEXT_CONTEXT_FRACTION = 0.30

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

# @brief Default timeout in seconds for polling long-running TTS operations.
DEFAULT_TTS_OPERATION_TIMEOUT_SECONDS = DEFAULT_TTS_AUDIO_GENERATION_TIMEOUT_SECONDS

# @brief Default maximum narrator preview text length for TTS samples.
DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT = 512

# @brief Minimum estimated narrator preview audio duration required for useful Qwen TTS references.
DEFAULT_TTS_MIN_PREVIEW_AUDIO_SECONDS = 6.0

# @brief Minimum imported WAV sample duration required for Qwen TTS clone references.
DEFAULT_IMPORTED_VOICE_SAMPLE_MIN_SECONDS = 3.0

# @brief Default per-project narrator voice-assignment mode.
DEFAULT_TTS_VOICE_ASSIGNMENT_MODE = "narrator_and_characters"

# @brief Supported narrator voice-assignment modes for one project.
TTS_VOICE_ASSIGNMENT_MODE_OPTIONS = ("same_narrator", "narrator_and_characters")

# @brief Conservative fallback max_new_tokens budget used before the TTS model reports one.
# @details Matches the VoiceWeaver clone-model cap, so an unprobed runtime is never planned
#          for more audio than a clone model can actually generate.
DEFAULT_TTS_NARRATOR_ONLY_TOKEN_BUDGET = 512

# @brief Approximate generated-audio seconds represented by one VoiceWeaver max_new_tokens unit.
DEFAULT_TTS_APPROX_AUDIO_SECONDS_PER_TOKEN = 0.08

# @brief Safety factor applied when splitting narrator-only Speech Blocks.
# @details Kept below the VoiceWeaver clone duration warning ratio so a fully packed block
#          does not land on the runtime warning threshold.
DEFAULT_TTS_SPLIT_SAFETY_FACTOR = 0.80

# @brief Approximate spoken-word rate used to convert audio token budget into text guidance.
DEFAULT_TTS_WORDS_PER_AUDIO_SECOND = 2.5

# @brief Approximate spoken characters per audio second, per dominant writing script.
# @details Space-separated scripts are word-paced; CJK and Hangul are character-paced, so a
#          word count is meaningless there and the character rate decides the budget.
DEFAULT_TTS_CHARACTERS_PER_AUDIO_SECOND_BY_SCRIPT = {
    "latin": 14.0,
    "cyrillic": 14.0,
    "cjk": 6.0,
    "hangul": 7.0,
}

# @brief Character rate used when the dominant writing script cannot be classified.
DEFAULT_TTS_CHARACTERS_PER_AUDIO_SECOND_FALLBACK = 14.0

# @brief Operator target for one narration block, in generated audio seconds.
# @details Zero means "follow the TTS model budget", which produces the widest safe blocks.
#          Any positive value only ever shortens blocks; the model budget stays the hard cap.
DEFAULT_SPEECH_BLOCK_TARGET_AUDIO_SECONDS = 0.0

# @brief Shortest operator-selectable narration block duration, in generated audio seconds.
SPEECH_BLOCK_TARGET_AUDIO_SECONDS_MINIMUM = 5.0

# @brief Longest operator-selectable narration block duration, in generated audio seconds.
SPEECH_BLOCK_TARGET_AUDIO_SECONDS_MAXIMUM = 300.0

# @brief Default Scene Ambience Speech Blocks generation enablement.
DEFAULT_SCENE_AMBIENCE_GENERATION_ENABLED = False

# @brief Scene Ambience placement options used by Speech Blocks generation.
SCENE_AMBIENCE_PLACEMENT_OPTIONS = (
    "none",
    "openers_and_closers",
    "openers_closers_and_scene_changes",
)

# @brief Default Scene Ambience placement policy.
DEFAULT_SCENE_AMBIENCE_PLACEMENT = "none"

# @brief Default maximum generated Scene Ambience sequence duration in seconds.
DEFAULT_SCENE_AMBIENCE_DURATION_SECONDS = 10

# @brief Default maximum generated Scene Ambience blocks in one ambience sequence.
DEFAULT_SCENE_AMBIENCE_MAX_BLOCKS_PER_SEQUENCE = 6

# @brief Default Stable Audio guidance scale for Scene Ambience sound generation.
DEFAULT_SCENE_AMBIENCE_GUIDANCE_SCALE = 7.0

# @brief Default Stable Audio inference-step count for Scene Ambience sound generation.
DEFAULT_SCENE_AMBIENCE_NUM_INFERENCE_STEPS = 100

# @brief Default Stable Audio seed for Scene Ambience sound generation; None lets the runtime randomize.
DEFAULT_SCENE_AMBIENCE_SEED = None

# @brief Default semantic AI chunking strategy.
DEFAULT_AI_CHUNKING_STRATEGY = "paragraph"

# @brief Supported semantic AI chunking strategies.
AI_CHUNKING_STRATEGY_OPTIONS = ("paragraph", "meaning", "scene")

# @brief Balanced AI chunking context mode token.
AI_CHUNKING_CONTEXT_MODE_BALANCED = "balanced"

# @brief Wide-scene AI chunking context mode token.
AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE = "wide_scene"

# @brief Maximum AI chunking context mode token.
AI_CHUNKING_CONTEXT_MODE_MAXIMUM = "maximum"

# @brief Default AI chunking context mode.
DEFAULT_AI_CHUNKING_CONTEXT_MODE = AI_CHUNKING_CONTEXT_MODE_BALANCED

# @brief Supported AI chunking context modes.
AI_CHUNKING_CONTEXT_MODE_OPTIONS = (
    AI_CHUNKING_CONTEXT_MODE_BALANCED,
    AI_CHUNKING_CONTEXT_MODE_WIDE_SCENE,
    AI_CHUNKING_CONTEXT_MODE_MAXIMUM,
)

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

# @brief Wider strategy-specific paragraph caps used by the wide-scene AI chunking context mode.
AI_CHUNKING_WIDE_WINDOW_SIZE_BY_STRATEGY = {
    "paragraph": DEFAULT_AI_CHUNKING_PARAGRAPH_WINDOW_SIZE * 2,
    "meaning": DEFAULT_AI_CHUNKING_MEANING_WINDOW_SIZE * 2,
    "scene": DEFAULT_AI_CHUNKING_SCENE_WINDOW_SIZE * 2,
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

# @brief Default requested count for AI narrator profile generation.
DEFAULT_NARRATOR_PROFILE_GENERATION_COUNT = 6

# @brief Maximum requested count for one AI narrator profile generation run.
MAX_NARRATOR_PROFILE_GENERATION_COUNT = 20

# @brief Default text-unit cap per AI narrator style-analysis request for local providers.
DEFAULT_NARRATOR_PROFILE_STYLE_WINDOW_SIZE = 12

# @brief Minimum estimated source-text token budget required for one AI narrator style-analysis request.
DEFAULT_NARRATOR_PROFILE_MIN_TEXT_BUDGET_TOKENS = 512

# @brief Minimum estimated token safety margin reserved in each AI narrator profile request.
DEFAULT_NARRATOR_PROFILE_MIN_SAFETY_MARGIN_TOKENS = 256

# @brief Fraction of the context window reserved as safety margin for AI narrator profile generation.
DEFAULT_NARRATOR_PROFILE_SAFETY_MARGIN_CONTEXT_FRACTION = 0.10

# @brief Maximum context-window fraction used for AI narrator profile source text.
DEFAULT_NARRATOR_PROFILE_TEXT_CONTEXT_FRACTION = 0.60


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

# @brief Default inclusion policy for generated Scene Ambience audio during Audio Assembly.
DEFAULT_AUDIO_ASSEMBLY_INCLUDE_SCENE_AMBIENCE = True


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

# END OF FILE
