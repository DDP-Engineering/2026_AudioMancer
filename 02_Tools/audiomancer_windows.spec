# -*- mode: python ; coding: utf-8 -*-
#
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.

from pathlib import Path

SPEC_ROOT = Path.cwd()
SOURCE_ROOT = SPEC_ROOT / "src"
TOOLS_ROOT = SPEC_ROOT.parents[1] / "02_Tools"
ENTRYPOINT_PATH = TOOLS_ROOT / "audiomancer_windows_entry.py"
ICON_PATH = SOURCE_ROOT / "audiomancer" / "assets" / "icons" / "audiomancer.ico"
ICON_ASSET_ROOT = SOURCE_ROOT / "audiomancer" / "assets" / "icons"

analysis = Analysis(
    [str(ENTRYPOINT_PATH)],
    pathex=[str(SOURCE_ROOT)],
    binaries=[],
    datas=[(str(ICON_ASSET_ROOT), "audiomancer/assets/icons")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AudioMancer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ICON_PATH),
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AudioMancer",
)
