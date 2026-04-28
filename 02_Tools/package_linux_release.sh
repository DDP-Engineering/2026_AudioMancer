#!/usr/bin/env bash
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

set -euo pipefail

invoke_step() {
    local name="$1"
    shift

    echo "==> ${name}"
    "$@"
}

remove_path_if_exists() {
    local path="$1"

    if [[ -e "${path}" ]]; then
        rm -rf -- "${path}"
    fi
}

copy_required_root_files() {
    local target_dir="$1"
    local required_files=(
        "settings.json"
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

copy_prompt_templates() {
    local target_dir="$1"
    local prompt_source_path="${APP_ROOT}/prompts"

    if [[ ! -d "${prompt_source_path}" ]]; then
        echo "Required prompt-template folder is missing: ${prompt_source_path}" >&2
        exit 1
    fi

    cp -a "${prompt_source_path}" "${target_dir}/prompts"
}

create_zip_archive() {
    local source_dir="$1"
    local archive_path="$2"

    rm -f -- "${archive_path}"
    python3 - "${source_dir}" "${archive_path}" <<'PY'
import sys
import zipfile
from pathlib import Path

source_dir = Path(sys.argv[1]).resolve()
archive_path = Path(sys.argv[2]).resolve()
base_parent = source_dir.parent

with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source_dir.rglob("*")):
        archive.write(path, path.relative_to(base_parent))
PY
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_ROOT="${REPO_ROOT}/04_Software/AudioMancer"
DELIVERY_ROOT="${REPO_ROOT}/07_Delivery"
PYTHON_LAUNCHER_PATH="${SCRIPT_DIR}/audiomancer_windows_entry.py"
PYPROJECT_PATH="${APP_ROOT}/pyproject.toml"

if [[ ! -f "${PYPROJECT_PATH}" ]]; then
    echo "Could not locate pyproject.toml at ${PYPROJECT_PATH}" >&2
    exit 1
fi

APP_VERSION="$(sed -nE 's/^version = "([^"]+)"/\1/p' "${PYPROJECT_PATH}" | head -n 1)"
if [[ -z "${APP_VERSION}" ]]; then
    echo "Could not read project version from ${PYPROJECT_PATH}" >&2
    exit 1
fi

ARTIFACT_BASE_NAME="AudioMancer_Ubuntu_x64_v${APP_VERSION}"
ARCHIVE_PATH="${DELIVERY_ROOT}/${ARTIFACT_BASE_NAME}.zip"
STAGING_ROOT="${SCRIPT_DIR}/.packaging_tmp"
STAGING_PATH="${STAGING_ROOT}/${ARTIFACT_BASE_NAME}"
BUILD_PATH="${APP_ROOT}/build"
DIST_PATH="${APP_ROOT}/dist"
DIST_BUNDLE_PATH="${DIST_PATH}/AudioMancer"

invoke_step "Prepare packaging workspace" mkdir -p "${DELIVERY_ROOT}" "${STAGING_ROOT}"
remove_path_if_exists "${STAGING_PATH}"

pushd "${APP_ROOT}" >/dev/null
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
        --distpath "${DIST_PATH}" \
        --workpath "${BUILD_PATH}" \
        --specpath "${STAGING_ROOT}" \
        "${PYTHON_LAUNCHER_PATH}"
popd >/dev/null

if [[ ! -d "${DIST_BUNDLE_PATH}" ]]; then
    echo "PyInstaller output folder not found: ${DIST_BUNDLE_PATH}" >&2
    exit 1
fi

invoke_step "Assemble delivery staging folder" mkdir -p "${STAGING_PATH}"
cp -a "${DIST_BUNDLE_PATH}/." "${STAGING_PATH}/"
copy_required_root_files "${STAGING_PATH}"
copy_user_guide "${STAGING_PATH}"
copy_prompt_templates "${STAGING_PATH}"

cat >"${STAGING_PATH}/start-audiomancer.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec "./AudioMancer" "$@"
SH
chmod +x "${STAGING_PATH}/start-audiomancer.sh"

cat >"${STAGING_PATH}/README_RELEASE.txt" <<EOF
AudioMancer Ubuntu x64 v${APP_VERSION}

This folder is a portable AudioMancer release.

Start:
- Run ./AudioMancer, or
- Run ./start-audiomancer.sh.

Install:
- Extract the full zip folder before starting the app.
- Keep the files together; the executable depends on bundled runtime files.
- On a minimal Ubuntu desktop, install the standard Qt desktop libraries if
  the app reports missing system display dependencies.

Configuration and licenses are included next to the executable.
Prompt templates are included in prompts/.
Offline help is included in help/en/index.html and help/ro/index.html.
EOF

invoke_step "Create versioned delivery archive" create_zip_archive "${STAGING_PATH}" "${ARCHIVE_PATH}"

invoke_step "Clean build artifacts" remove_path_if_exists "${BUILD_PATH}"
remove_path_if_exists "${DIST_PATH}"
remove_path_if_exists "${STAGING_PATH}"
remove_path_if_exists "${STAGING_ROOT}/AudioMancer.spec"

if [[ -d "${STAGING_ROOT}" ]] && [[ -z "$(find "${STAGING_ROOT}" -mindepth 1 -print -quit)" ]]; then
    rmdir "${STAGING_ROOT}"
fi

echo "Ubuntu delivery archive created: ${ARCHIVE_PATH}"
