# -*- mode: python ; coding: utf-8 -*-
"""Lol Audio Unpack GUI 的 PyInstaller 构建规范。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=("onefile", "onedir"), default="onefile")
parser.add_argument("--runtime-version", default="")
parser.add_argument("--version-file", default="")
options = parser.parse_args()

SPEC_ROOT = Path(SPECPATH).resolve()
PROJECT_ROOT = SPEC_ROOT.parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
GUI_ENTRY = SRC_ROOT / "lol_audio_unpack" / "gui" / "__main__.py"
GUI_ASSET_ROOT = SRC_ROOT / "lol_audio_unpack" / "gui" / "assets"
APP_ICON = GUI_ASSET_ROOT / "app_icon.ico" if sys.platform.startswith("win") else None
RUNTIME_HOOK = PROJECT_ROOT / "scripts" / "pyinstaller" / "runtime_hook_chdir.py"
BUILD_VERSION_HOOK = Path(workpath) / "runtime_hook_build_version.py"
version_file = Path(options.version_file).resolve() if options.version_file else None

if options.runtime_version:
    BUILD_VERSION_HOOK.write_text(
        "import os\n"
        f"os.environ['LOL_AUDIO_UNPACK_BUILD_VERSION'] = {options.runtime_version!r}\n",
        encoding="utf-8",
    )

runtime_hooks = []
if options.runtime_version:
    runtime_hooks.append(str(BUILD_VERSION_HOOK))
runtime_hooks.append(str(RUNTIME_HOOK))

datas = collect_data_files("qfluentwidgets")
datas += [
    (
        str(path),
        (
            f"lol_audio_unpack/gui/assets/{path.relative_to(GUI_ASSET_ROOT).parent.as_posix()}"
            if path.relative_to(GUI_ASSET_ROOT).parent.as_posix() != "."
            else "lol_audio_unpack/gui/assets"
        ),
    )
    for path in GUI_ASSET_ROOT.rglob("*")
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
    runtime_hooks=runtime_hooks,
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
        version=str(version_file) if sys.platform.startswith("win") and version_file is not None else None,
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
        version=str(version_file) if sys.platform.startswith("win") and version_file is not None else None,
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
