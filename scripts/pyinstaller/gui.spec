# -*- mode: python ; coding: utf-8 -*-
"""Lol Audio Unpack GUI 的 PyInstaller 构建规范。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=("onefile", "onedir"), default="onefile")
options = parser.parse_args()

SPEC_ROOT = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_ROOT.parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
GUI_ENTRY = SRC_ROOT / "lol_audio_unpack" / "gui" / "__main__.py"
GUI_ASSET_ROOT = SRC_ROOT / "lol_audio_unpack" / "gui" / "assets"
APP_ICON = GUI_ASSET_ROOT / "app_icon.ico" if sys.platform.startswith("win") else None
RUNTIME_HOOK = PROJECT_ROOT / "scripts" / "pyinstaller" / "runtime_hook_chdir.py"

datas = collect_data_files("qfluentwidgets")
datas += [
    (str(path), "lol_audio_unpack/gui/assets")
    for path in GUI_ASSET_ROOT.iterdir()
    if path.is_file()
]

hiddenimports = collect_submodules("qfluentwidgets")

a = Analysis(
    [str(GUI_ENTRY)],
    pathex=[str(SRC_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(RUNTIME_HOOK)],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

if options.mode == "onefile":
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="LolAudioUnpack",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        icon=str(APP_ICON) if APP_ICON is not None and APP_ICON.is_file() else None,
    )
elif options.mode == "onedir":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="LolAudioUnpack",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        icon=str(APP_ICON) if APP_ICON is not None and APP_ICON.is_file() else None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="LolAudioUnpack",
    )
