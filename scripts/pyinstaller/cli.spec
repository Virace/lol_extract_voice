"""独立控制台程序的 PyInstaller 构建配置。"""

# ruff: noqa: F821

import argparse
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=("onefile", "onedir"), default="onefile")
parser.add_argument("--runtime-version", required=True)
parser.add_argument("--version-quad", required=True)
args = parser.parse_args()

root = Path(SPECPATH).resolve().parents[1]
version_hook = Path(workpath) / "runtime_version.py"
version_hook.write_text(
    "import os\n" + f"os.environ['LOL_AUDIO_UNPACK_BUILD_VERSION'] = {args.runtime_version!r}\n",
    encoding="utf-8",
)
quad = tuple(int(value) for value in args.version_quad.split("."))
version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=quad, prodvers=quad, mask=0x3F, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "080404B0",
                    [
                        StringStruct("CompanyName", "Virace"),
                        StringStruct("FileDescription", "Lol Audio Unpack CLI"),
                        StringStruct("FileVersion", args.runtime_version),
                        StringStruct("InternalName", "LolAudioUnpack-CLI"),
                        StringStruct("OriginalFilename", "LolAudioUnpack-CLI.exe"),
                        StringStruct("ProductName", "lol-audio-unpack"),
                        StringStruct("ProductVersion", args.runtime_version),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [2052, 1200])]),
    ],
)
version_file = Path(workpath) / "windows_version.txt"
version_file.write_text(str(version), encoding="utf-8")

a = Analysis(
    [str(root / "scripts" / "pyinstaller" / "cli_entry.py")],
    pathex=[str(root / "src")],
    binaries=collect_dynamic_libs("pyvgmstream"),
    datas=[(str(root / "src/lol_audio_unpack/resources/preflight"), "lol_audio_unpack/resources/preflight")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(version_hook)],
    excludes=["PySide6", "shiboken6", "qfluentwidgets", "lol_audio_unpack.gui"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
options = dict(
    name="LolAudioUnpack-CLI",
    console=True,
    upx=False,
    strip=False,
    version=str(version_file),
    icon=str(root / "scripts/pyinstaller/assets/cli_icon.ico"),
)
if args.mode == "onefile":
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LolAudioUnpack-CLI")
