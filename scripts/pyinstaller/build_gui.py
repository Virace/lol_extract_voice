"""跨平台 GUI 打包入口。"""

from __future__ import annotations

import argparse
import platform
import shutil
import struct
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "scripts" / "pyinstaller" / "gui.spec"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / ".temp" / "pyinstaller"
REQUIRED_PYTHON_BITS = 64


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="构建 Lol Audio Unpack GUI 的 PyInstaller 包。")
    parser.add_argument(
        "--mode",
        choices=("onefile", "onedir"),
        default="onefile",
        help="打包模式，默认使用 onefile。",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="PyInstaller 构建输出根目录，默认写入 .temp/pyinstaller。",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="跳过 uv sync，只使用当前环境直接构建。",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="构建前清理旧的输出目录。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印将要执行的命令，不实际构建。",
    )
    return parser


def _ensure_supported_host() -> None:
    if struct.calcsize("P") * 8 != REQUIRED_PYTHON_BITS:
        raise SystemExit("当前构建脚本仅支持 64 位 Python 运行时。")

    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise SystemExit(
            f"当前主机架构为 {platform.machine()}，本构建入口目前仅面向 x64/amd64 本机构建。"
        )


def _run_command(command: list[str], *, dry_run: bool) -> None:
    print("$", " ".join(command))
    if dry_run:
        return

    subprocess.run(command, check=True, cwd=PROJECT_ROOT)


def main() -> int:
    args = _build_parser().parse_args()
    _ensure_supported_host()

    output_root = Path(args.output_root).expanduser().resolve()
    dist_path = output_root / "dist"
    work_path = output_root / "build"

    print(f"RepoRoot   : {PROJECT_ROOT}")
    print(f"SpecPath   : {SPEC_PATH}")
    print(f"Mode       : {args.mode}")
    print(f"OutputRoot : {output_root}")
    print(f"DistPath   : {dist_path}")
    print(f"WorkPath   : {work_path}")

    if args.clean and output_root.exists():
        print(f"清理旧的 PyInstaller 输出目录: {output_root}")
        if not args.dry_run:
            shutil.rmtree(output_root)

    if not args.skip_sync:
        _run_command(["uv", "sync", "--extra", "gui", "--group", "build"], dry_run=args.dry_run)

    build_command = [
        "uv",
        "run",
        "--extra",
        "gui",
        "--group",
        "build",
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_path),
        "--workpath",
        str(work_path),
        str(SPEC_PATH),
        "--",
        "--mode",
        args.mode,
    ]
    _run_command(build_command, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
