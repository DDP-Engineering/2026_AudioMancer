#!/usr/bin/env bash
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

set -euo pipefail

# Run each validation step with a visible label so failures identify the stage
# that failed in the terminal output.
invoke_step() {
    local name="$1"
    shift

    echo "==> ${name}"
    "$@"
}

# Delete temporary validation paths without failing when they are absent.
remove_path_if_exists() {
    local path="$1"

    if [[ -e "${path}" ]]; then
        rm -rf -- "${path}"
    fi
}

# Require one command and print a clear setup message when it is absent.
require_command() {
    local command_name="$1"

    if ! command -v "${command_name}" >/dev/null 2>&1; then
        echo "Required command is missing: ${command_name}" >&2
        exit 1
    fi
}

# Extract the AppImage without requiring host FUSE support.
extract_appimage() {
    remove_path_if_exists "${APPIMAGE_EXTRACT_ROOT}"
    mkdir -p "${APPIMAGE_EXTRACT_ROOT}"

    pushd "${APPIMAGE_EXTRACT_ROOT}" >/dev/null
    APPIMAGE_EXTRACT_AND_RUN=1 "${APPIMAGE_PATH}" --appimage-extract >/dev/null
    popd >/dev/null

    if [[ ! -d "${EXTRACTED_APPDIR_PATH}" ]]; then
        echo "AppImage extraction did not create ${EXTRACTED_APPDIR_PATH}" >&2
        exit 1
    fi
}

# Fail when any extracted executable or library still points at a missing shared
# object. This catches gaps such as missing xcb platform dependencies.
check_extracted_dependencies() {
    local missing_count=0
    local library_path="${EXTRACTED_APPDIR_PATH}/usr/bin/_internal:${EXTRACTED_APPDIR_PATH}/usr/lib"

    while IFS= read -r -d '' candidate_path; do
        if ! file "${candidate_path}" | grep -q "ELF"; then
            continue
        fi

        local ldd_output
        ldd_output="$(LD_LIBRARY_PATH="${library_path}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" ldd "${candidate_path}" 2>&1 || true)"
        if grep -q "not found" <<<"${ldd_output}"; then
            echo "Missing dependencies for ${candidate_path}:" >&2
            grep "not found" <<<"${ldd_output}" >&2
            missing_count=$((missing_count + 1))
        fi
    done < <(
        find "${EXTRACTED_APPDIR_PATH}" -type f \
            \( -name "AudioMancer" -o -name "*.so" -o -name "*.so.*" \) \
            -print0
    )

    if (( missing_count > 0 )); then
        echo "Found ${missing_count} file(s) with unresolved shared-library dependencies." >&2
        exit 1
    fi
}

# Run the AppImage long enough to prove the app starts, loads settings, and
# reaches Qt theme initialization in headless mode.
smoke_test_appimage() {
    local smoke_output_path="${VALIDATION_ROOT}/appimage-smoke.log"
    local smoke_state_home_path="${VALIDATION_ROOT}/state"
    local smoke_exit_code=0

    mkdir -p "${smoke_state_home_path}"
    set +e
    APPIMAGE_EXTRACT_AND_RUN=1 XDG_STATE_HOME="${smoke_state_home_path}" QT_QPA_PLATFORM=offscreen timeout 15s "${APPIMAGE_PATH}" \
        >"${smoke_output_path}" 2>&1
    smoke_exit_code=$?
    set -e

    if [[ "${smoke_exit_code}" != "0" && "${smoke_exit_code}" != "124" ]]; then
        echo "AppImage smoke test failed with exit code ${smoke_exit_code}." >&2
        cat "${smoke_output_path}" >&2
        exit 1
    fi

    if ! grep -q "AudioMancer bootstrap started" "${smoke_output_path}"; then
        echo "AppImage smoke test did not reach application bootstrap." >&2
        cat "${smoke_output_path}" >&2
        exit 1
    fi
    if ! grep -q "Loaded settings" "${smoke_output_path}"; then
        echo "AppImage smoke test did not load packaged settings." >&2
        cat "${smoke_output_path}" >&2
        exit 1
    fi
    if ! grep -q "ui-theme-applied" "${smoke_output_path}"; then
        echo "AppImage smoke test did not reach Qt theme initialization." >&2
        cat "${smoke_output_path}" >&2
        exit 1
    fi
}

# Verify the portable zip still carries the expected operator resources.
check_zip_contents() {
    local zip_listing
    local required_entries=(
        "AudioMancer_Linux_x64/AudioMancer"
        "AudioMancer_Linux_x64/start-audiomancer.sh"
        "AudioMancer_Linux_x64/README_RELEASE.txt"
        "AudioMancer_Linux_x64/settings.json"
        "AudioMancer_Linux_x64/prompts/text_cleanup_adjudication_primary_system.txt"
        "AudioMancer_Linux_x64/prompts/text_cleanup_adjudication_verifier_system.txt"
        "AudioMancer_Linux_x64/help/en/index.html"
        "AudioMancer_Linux_x64/help/ro/index.html"
        "AudioMancer_Linux_x64/assets/icons/audiomancer_icon.png"
        "AudioMancer_Linux_x64/LICENSE.txt"
        "AudioMancer_Linux_x64/LICENSE_NC.txt"
        "AudioMancer_Linux_x64/LICENSE_ro.txt"
        "AudioMancer_Linux_x64/LICENSE_NC_ro.txt"
        "AudioMancer_Linux_x64/CHANGELOG.md"
    )

    unzip -t "${ARCHIVE_PATH}" >/dev/null
    zip_listing="$(unzip -Z1 "${ARCHIVE_PATH}")"
    for entry_name in "${required_entries[@]}"; do
        if ! grep -Fxq "${entry_name}" <<<"${zip_listing}"; then
            echo "Linux zip is missing required entry: ${entry_name}" >&2
            exit 1
        fi
    done
}

# Write checksums for the Linux delivery artifacts.
write_checksums() {
    local checksum_temp_path="${VALIDATION_ROOT}/SHA256SUMS.txt"

    pushd "${DELIVERY_ROOT}" >/dev/null
    if [[ -f "${CHECKSUM_PATH}" ]]; then
        grep -Ev '  AudioMancer_Linux_x64\.(zip|AppImage)$' "${CHECKSUM_PATH}" >"${checksum_temp_path}" || true
    fi
    sha256sum "$(basename "${ARCHIVE_PATH}")" "$(basename "${APPIMAGE_PATH}")" >>"${checksum_temp_path}"
    mv -- "${checksum_temp_path}" "${CHECKSUM_PATH}"
    popd >/dev/null
}

# Resolve repository paths from the script location so the script can be run
# from any current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DELIVERY_ROOT="${REPO_ROOT}/07_Delivery"
ARCHIVE_PATH="${DELIVERY_ROOT}/AudioMancer_Linux_x64.zip"
APPIMAGE_PATH="${DELIVERY_ROOT}/AudioMancer_Linux_x64.AppImage"
CHECKSUM_PATH="${DELIVERY_ROOT}/SHA256SUMS.txt"
VALIDATION_ROOT="${TMPDIR:-/tmp}/audiomancer-linux-delivery-validation"
APPIMAGE_EXTRACT_ROOT="${VALIDATION_ROOT}/appimage"
EXTRACTED_APPDIR_PATH="${APPIMAGE_EXTRACT_ROOT}/squashfs-root"

require_command file
require_command ldd
require_command sha256sum
require_command timeout
require_command unzip

if [[ ! -f "${ARCHIVE_PATH}" ]]; then
    echo "Missing Linux delivery archive: ${ARCHIVE_PATH}" >&2
    exit 1
fi
if [[ ! -f "${APPIMAGE_PATH}" ]]; then
    echo "Missing Linux AppImage: ${APPIMAGE_PATH}" >&2
    exit 1
fi
chmod +x "${APPIMAGE_PATH}"

remove_path_if_exists "${VALIDATION_ROOT}"
mkdir -p "${VALIDATION_ROOT}"
trap 'remove_path_if_exists "${VALIDATION_ROOT}"' EXIT

invoke_step "Validate Linux zip contents" check_zip_contents
invoke_step "Extract AppImage" extract_appimage
invoke_step "Check AppImage shared-library dependencies" check_extracted_dependencies
invoke_step "Smoke-test AppImage startup" smoke_test_appimage
invoke_step "Write Linux delivery checksums" write_checksums

echo "Linux delivery validation completed."
