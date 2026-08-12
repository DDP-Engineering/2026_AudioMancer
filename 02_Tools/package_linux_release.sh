#!/usr/bin/env bash
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

set -euo pipefail

# Run each release step with a visible label so packaging failures identify the
# stage that failed in the terminal output.
invoke_step() {
    local name="$1"
    shift

    echo "==> ${name}"
    "$@"
}

# Delete temporary packaging paths without failing when they are absent.
remove_path_if_exists() {
    local path="$1"

    if [[ -e "${path}" ]]; then
        rm -rf -- "${path}"
    fi
}

# Copy the runtime files expected beside the executable in the portable bundle.
copy_required_root_files() {
    local target_dir="$1"
    local required_files=(
        "LICENSE.txt"
        "LICENSE_NC.txt"
        "LICENSE_ro.txt"
        "LICENSE_NC_ro.txt"
    )

    for file_name in "${required_files[@]}"; do
        local source_path="${APP_ROOT}/${file_name}"

        if [[ ! -f "${source_path}" ]]; then
            echo "Required packaging file is missing: ${source_path}" >&2
            exit 1
        fi

        cp -- "${source_path}" "${target_dir}/${file_name}"
    done
}

# Copy settings into a delivery package without operator-local secrets or
# connection-discovery cache. The source settings.json in the app root is not
# modified.
copy_clean_settings_file() {
    local source_path="$1"
    local target_path="$2"

    if [[ ! -f "${source_path}" ]]; then
        echo "Required packaging file is missing: ${source_path}" >&2
        exit 1
    fi

    python3 - "${source_path}" "${target_path}" <<'PY'
import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
settings_payload = json.loads(source_path.read_text(encoding="utf-8"))

for profile in settings_payload.get("llm_profiles", []):
    if not isinstance(profile, dict):
        continue
    profile["api_key"] = ""
    if profile.get("backend_kind") == "lmstudio":
        profile["base_url"] = "http://127.0.0.1:1234/v1"
    profile["discovered_model_name"] = ""
    profile["discovered_context_window"] = None
    profile["discovery_succeeded"] = False
    profile["discovery_message"] = ""

settings_payload["tts_runtime_base_url"] = "http://127.0.0.1:8059"
settings_payload["tts_runtime_api_key"] = ""
settings_payload["tts_runtime_probe_succeeded"] = False
settings_payload["tts_runtime_probe_message"] = ""
settings_payload["tts_runtime_discovered_models"] = []
settings_payload["tts_runtime_active_model_id"] = None
settings_payload["tts_runtime_device_diagnostics"] = {}

target_path.write_text(json.dumps(settings_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

# Ship both offline help bundles under the language folders used by the app.
copy_user_guide() {
    local target_dir="$1"
    local english_source_path="${REPO_ROOT}/05_SoftwareDocu/UserGuide"
    local romanian_source_path="${REPO_ROOT}/05_SoftwareDocu/UserGuide_ro"
    local help_root="${target_dir}/help"

    if [[ ! -d "${english_source_path}" ]]; then
        echo "Required English user guide folder is missing: ${english_source_path}" >&2
        exit 1
    fi
    if [[ ! -d "${romanian_source_path}" ]]; then
        echo "Required Romanian user guide folder is missing: ${romanian_source_path}" >&2
        exit 1
    fi

    mkdir -p "${help_root}"
    cp -a "${english_source_path}" "${help_root}/en"
    cp -a "${romanian_source_path}" "${help_root}/ro"
}

# Keep prompt templates available in the extracted release folder.
copy_prompt_templates() {
    local target_dir="$1"
    local prompt_source_path="${APP_ROOT}/prompts"

    if [[ ! -d "${prompt_source_path}" ]]; then
        echo "Required prompt-template folder is missing: ${prompt_source_path}" >&2
        exit 1
    fi

    cp -a "${prompt_source_path}" "${target_dir}/prompts"
}

# Linux desktop launchers need an icon path outside the PyInstaller internals.
copy_app_icons() {
    local target_dir="$1"
    local icon_source_path="${APP_ROOT}/src/audiomancer/assets/icons/audiomancer_icon.png"
    local icon_target_dir="${target_dir}/assets/icons"

    if [[ ! -f "${icon_source_path}" ]]; then
        echo "Required app icon is missing: ${icon_source_path}" >&2
        exit 1
    fi

    mkdir -p "${icon_target_dir}"
    cp -- "${icon_source_path}" "${icon_target_dir}/audiomancer_icon.png"
}

# Use Python's zipfile module to avoid depending on a system zip executable.
create_zip_archive() {
    local source_dir="$1"
    local archive_path="$2"

    rm -f -- "${archive_path}"
    python3 - "${source_dir}" "${archive_path}" <<'PY'
import sys
import zipfile
from pathlib import Path

# Preserve the top-level portable folder inside the archive.
source_dir = Path(sys.argv[1]).resolve()
archive_path = Path(sys.argv[2]).resolve()
base_parent = source_dir.parent

with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source_dir.rglob("*")):
        archive.write(path, path.relative_to(base_parent))
PY
}

# Resolve repository paths from the script location so the script can be run
# from any current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_ROOT="${REPO_ROOT}/04_Software/AudioMancer"
DELIVERY_ROOT="${REPO_ROOT}/07_Delivery"
PYTHON_LAUNCHER_PATH="${SCRIPT_DIR}/audiomancer_windows_entry.py"
PYPROJECT_PATH="${APP_ROOT}/pyproject.toml"
CHANGELOG_PATH="${REPO_ROOT}/CHANGELOG.md"

if [[ ! -f "${PYPROJECT_PATH}" ]]; then
    echo "Could not locate pyproject.toml at ${PYPROJECT_PATH}" >&2
    exit 1
fi
if [[ ! -f "${CHANGELOG_PATH}" ]]; then
    echo "Could not locate CHANGELOG.md at ${CHANGELOG_PATH}" >&2
    exit 1
fi

# The archive filename is stable, but release notes still include the app
# version read from pyproject.toml.
APP_VERSION="$(sed -nE 's/^version = "([^"]+)"/\1/p' "${PYPROJECT_PATH}" | head -n 1)"
if [[ -z "${APP_VERSION}" ]]; then
    echo "Could not read project version from ${PYPROJECT_PATH}" >&2
    exit 1
fi

ARTIFACT_BASE_NAME="AudioMancer_Linux_x64"
ARCHIVE_PATH="${DELIVERY_ROOT}/${ARTIFACT_BASE_NAME}.zip"
STAGING_ROOT="${SCRIPT_DIR}/.packaging_tmp"
STAGING_PATH="${STAGING_ROOT}/${ARTIFACT_BASE_NAME}"
BUILD_PATH="${APP_ROOT}/build"
DIST_PATH="${APP_ROOT}/dist"
DIST_BUNDLE_PATH="${DIST_PATH}/AudioMancer"

# Build in a dedicated, isolated uv environment so a release build never touches
# the developer .venv (important when the repo lives on a Windows-shared mount).
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${HOME}/.cache/audiomancer/linux-build-venv}"

# Directory that caches downloaded build tools between runs (outside the repo).
TOOL_CACHE_DIR="${HOME}/.cache/audiomancer/tools"

# Resolved by ensure_prerequisites, consumed by build_appimage.
APPIMAGETOOL_BIN=""

# Detect the build prerequisites and install any that are missing. Everything is
# installed into the user's home directory, so no root/sudo is required.
ensure_prerequisites() {
    export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
    mkdir -p "${TOOL_CACHE_DIR}"

    local downloader=""
    if command -v curl >/dev/null 2>&1; then
        downloader="curl"
    elif command -v wget >/dev/null 2>&1; then
        downloader="wget"
    fi

    # uv: PyInstaller and the app environment are managed through uv.
    if ! command -v uv >/dev/null 2>&1; then
        if [[ -z "${downloader}" ]]; then
            echo "Missing 'uv' and neither curl nor wget is available to install it." >&2
            exit 1
        fi
        echo "Installing uv (official Astral installer, user-space)..."
        if [[ "${downloader}" == "curl" ]]; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
        else
            wget -qO- https://astral.sh/uv/install.sh | sh
        fi
        export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
    fi
    command -v uv >/dev/null 2>&1 || { echo "uv is still unavailable after installation." >&2; exit 1; }
    echo "uv: $(uv --version)"

    # appimagetool: cached AppImage executed without FUSE via extract-and-run.
    local cached_tool="${TOOL_CACHE_DIR}/appimagetool-x86_64.AppImage"
    if command -v appimagetool >/dev/null 2>&1; then
        APPIMAGETOOL_BIN="$(command -v appimagetool)"
    elif [[ -x "${cached_tool}" ]]; then
        APPIMAGETOOL_BIN="${cached_tool}"
    else
        if [[ -z "${downloader}" ]]; then
            echo "Missing appimagetool and neither curl nor wget is available to fetch it." >&2
            exit 1
        fi
        echo "Downloading appimagetool..."
        local url="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
        if [[ "${downloader}" == "curl" ]]; then
            curl -fL -o "${cached_tool}" "${url}"
        else
            wget -O "${cached_tool}" "${url}"
        fi
        chmod +x "${cached_tool}"
        APPIMAGETOOL_BIN="${cached_tool}"
    fi
    echo "appimagetool: ${APPIMAGETOOL_BIN}"
}

# Build a portable AppImage from the already-assembled staging bundle.
build_appimage() {
    local appdir="${STAGING_ROOT}/${ARTIFACT_BASE_NAME}.AppDir"
    local appimage_path="${DELIVERY_ROOT}/${ARTIFACT_BASE_NAME}.AppImage"

    remove_path_if_exists "${appdir}"
    mkdir -p "${appdir}"
    cp -a "${STAGING_PATH}/." "${appdir}/"

    # Top-level icon whose base name matches the desktop Icon key.
    cp -- "${APP_ROOT}/src/audiomancer/assets/icons/audiomancer_icon.png" "${appdir}/AudioMancer.png"

    # AppImage desktop entry: Exec and Icon are names, not paths.
    cat >"${appdir}/AudioMancer.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=AudioMancer
Comment=AudioMancer audiobook production application
Exec=AudioMancer
Icon=AudioMancer
Terminal=false
Categories=AudioVideo;Audio;Utility;
DESKTOP

    # AppRun launches the bundled PyInstaller executable.
    cat >"${appdir}/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "${HERE}/AudioMancer" "$@"
APPRUN
    chmod +x "${appdir}/AppRun"

    remove_path_if_exists "${appimage_path}"
    ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "${APPIMAGETOOL_BIN}" "${appdir}" "${appimage_path}"
    remove_path_if_exists "${appdir}"
}

invoke_step "Prepare packaging workspace" mkdir -p "${DELIVERY_ROOT}" "${STAGING_ROOT}"
remove_path_if_exists "${STAGING_PATH}"

invoke_step "Detect and install build prerequisites" ensure_prerequisites

pushd "${APP_ROOT}" >/dev/null
# PyInstaller runs inside the uv-managed app environment.
invoke_step "Sync uv environment" uv sync --extra dev

invoke_step "Clean previous PyInstaller output" remove_path_if_exists "${BUILD_PATH}"
remove_path_if_exists "${DIST_PATH}"

invoke_step "Build Ubuntu bundle with PyInstaller" \
    uv run --no-sync pyinstaller \
        --noconfirm \
        --clean \
        --name AudioMancer \
        --windowed \
        --paths "${APP_ROOT}/src" \
        --add-data "${APP_ROOT}/src/audiomancer/assets/icons:audiomancer/assets/icons" \
        --distpath "${DIST_PATH}" \
        --workpath "${BUILD_PATH}" \
        --specpath "${STAGING_ROOT}" \
        "${PYTHON_LAUNCHER_PATH}"
popd >/dev/null

if [[ ! -d "${DIST_BUNDLE_PATH}" ]]; then
    echo "PyInstaller output folder not found: ${DIST_BUNDLE_PATH}" >&2
    exit 1
fi

# PySide's optional TIFF image plugin targets the retired libtiff.so.5 ABI,
# which Ubuntu 24.04 does not provide. AudioMancer does not load TIFF assets;
# omit this unusable plugin instead of shipping one unresolved shared object.
remove_path_if_exists \
    "${DIST_BUNDLE_PATH}/_internal/PySide6/Qt/plugins/imageformats/libqtiff.so"

invoke_step "Assemble delivery staging folder" mkdir -p "${STAGING_PATH}"
# Start from PyInstaller output, then add project-controlled runtime assets.
cp -a "${DIST_BUNDLE_PATH}/." "${STAGING_PATH}/"
copy_required_root_files "${STAGING_PATH}"
cp -- "${CHANGELOG_PATH}" "${STAGING_PATH}/CHANGELOG.md"
copy_clean_settings_file "${APP_ROOT}/settings.json" "${STAGING_PATH}/settings.json"
copy_user_guide "${STAGING_PATH}"
copy_prompt_templates "${STAGING_PATH}"
copy_app_icons "${STAGING_PATH}"

# Keep a simple shell launcher for users who prefer a stable start file.
cat >"${STAGING_PATH}/start-audiomancer.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec "./AudioMancer" "$@"
SH
chmod +x "${STAGING_PATH}/start-audiomancer.sh"

# Provide a portable desktop-entry template for Linux file managers.
cat >"${STAGING_PATH}/AudioMancer.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=AudioMancer
Comment=AudioMancer audiobook production application
Exec=./start-audiomancer.sh
Icon=./assets/icons/audiomancer_icon.png
Terminal=false
Categories=AudioVideo;Audio;Utility;
DESKTOP

# Plain-text release notes remain readable in the extracted portable folder.
cat >"${STAGING_PATH}/README_RELEASE.txt" <<EOF
AudioMancer Ubuntu x64 v${APP_VERSION}

This folder is a portable AudioMancer release.

Start:
- Run ./AudioMancer, or
- Run ./start-audiomancer.sh.
- On Linux desktops that support portable launchers, use AudioMancer.desktop
  after marking it trusted/executable if required by the desktop environment.

Install:
- Extract the full zip folder before starting the app.
- Keep the files together; the executable depends on bundled runtime files.
- On a minimal Ubuntu desktop, install the standard Qt desktop libraries if
  the app reports missing system display dependencies.

Configuration and licenses are included next to the executable.
The project changelog is included as CHANGELOG.md.
The packaged settings.json is cleaned of operator API keys and runtime discovery cache.
Prompt templates are included in prompts/.
The app icon is included in assets/icons/.
Offline help is included in help/en/index.html and help/ro/index.html.
EOF

invoke_step "Create delivery archive" create_zip_archive "${STAGING_PATH}" "${ARCHIVE_PATH}"

invoke_step "Build AppImage" build_appimage

invoke_step "Clean build artifacts" remove_path_if_exists "${BUILD_PATH}"
# Do not leave PyInstaller or staging folders in the working tree.
remove_path_if_exists "${DIST_PATH}"
remove_path_if_exists "${STAGING_PATH}"
remove_path_if_exists "${STAGING_ROOT}/AudioMancer.spec"

if [[ -d "${STAGING_ROOT}" ]] && [[ -z "$(find "${STAGING_ROOT}" -mindepth 1 -print -quit)" ]]; then
    rmdir "${STAGING_ROOT}"
fi

echo "Ubuntu delivery archive created: ${ARCHIVE_PATH}"
echo "Ubuntu AppImage created: ${DELIVERY_ROOT}/${ARTIFACT_BASE_NAME}.AppImage"
