"""在隔离的 uv 环境中构建 Windows x64 控制台程序。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import runpy
import shutil
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POINTER_BYTES = 8


def _read_version() -> tuple[str, str]:
    """直接加载无业务依赖的版本规则，避免构建入口导入运行时。"""
    source = PROJECT_ROOT / "src/lol_audio_unpack/utils/versioning.py"
    module = runpy.run_path(str(source))
    for line in (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            fallback = line.split("=", 1)[1].strip().strip('"')
            version = module["resolve_runtime_version"](PROJECT_ROOT, fallback)
            return version, ".".join(str(value) for value in module["format_windows_version_quad"](version))
    raise RuntimeError("pyproject.toml 缺少版本号")


def _run(command: list[str], *, env: dict[str, str], log_path: Path) -> None:
    """将构建诊断同时写入终端和任务日志，保留子进程失败状态。"""
    print("$", subprocess.list2cmdline(command), flush=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("$ " + subprocess.list2cmdline(command) + "\n")
        with subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        ) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
            if process.wait():
                raise subprocess.CalledProcessError(process.returncode, command)


def main() -> int:
    """创建独立构建目录，输出 EXE、校验文件及构建记录。

    Returns:
        构建成功返回 0；环境、路径或子命令失败时返回 1。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("onefile", "onedir"), default="onefile")
    parser.add_argument("--output-root", type=Path, help="新的任务专用目录；已存在时拒绝覆盖")
    parser.add_argument("--dry-run", action="store_true", help="只显示构建配置，不创建文件")
    args = parser.parse_args()

    if (
        sys.platform != "win32"
        or platform.machine().lower() not in {"amd64", "x86_64"}
        or struct.calcsize("P") != POINTER_BYTES
    ):
        parser.error("请使用原生 Windows x64 Python 构建")
    if shutil.which("uv") is None:
        parser.error("未找到 uv，请先安装并加入 PATH")

    run_id = datetime.now().strftime(".%Y%m%d-%H%M%S-") + uuid4().hex[:8]
    output = (args.output_root or PROJECT_ROOT / ".temp/cli-package" / run_id).resolve()
    if output.exists():
        parser.error(f"构建目录已存在，请指定新目录以保留已有产物：{output}")

    version, quad = _read_version()
    print(f"版本：{version}\n模式：{args.mode}\n构建目录：{output}\nPython：{sys.version}", flush=True)
    if args.dry_run:
        return 0

    output.mkdir(parents=True)
    env = os.environ.copy()
    env.update(
        UV_PROJECT_ENVIRONMENT=str(output / "env"),
        UV_CACHE_DIR=str(output / "uv-cache"),
        PYINSTALLER_CONFIG_DIR=str(output / "pyinstaller-cache"),
        PYTHONUTF8="1",
        PYTHONDONTWRITEBYTECODE="1",
        TEMP=str(output / "scratch"),
        TMP=str(output / "scratch"),
    )
    # 构建依赖只取锁文件；不继承外部包搜索路径或 GUI extra 环境配置。
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_EXTRA", "UV_ALL_EXTRAS", "UV_DEV", "UV_GROUP"):
        env.pop(key, None)
    (output / "scratch").mkdir()
    log_path = output / "build.log"
    python = output / "env/Scripts/python.exe"
    try:
        _run(
            [
                "uv",
                "sync",
                "--locked",
                "--no-default-groups",
                "--group",
                "build",
                "--no-install-project",
                "--no-editable",
                "--no-python-downloads",
                "--python",
                sys.executable,
            ],
            env=env,
            log_path=log_path,
        )
        _run(
            [
                str(python),
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--distpath",
                str(output / "dist"),
                "--workpath",
                str(output / "build"),
                str(PROJECT_ROOT / "scripts/pyinstaller/cli.spec"),
                "--",
                "--mode",
                args.mode,
                "--runtime-version",
                version,
                "--version-quad",
                quad,
            ],
            env=env,
            log_path=log_path,
        )
        executable = (
            output
            / "dist"
            / ("LolAudioUnpack-CLI.exe" if args.mode == "onefile" else "LolAudioUnpack-CLI/LolAudioUnpack-CLI.exe")
        )
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        executable.with_suffix(".exe.sha256").write_text(f"{digest} *{executable.name}\n", encoding="utf-8")
        shutil.copyfile(PROJECT_ROOT / "docs/cli-package.md", executable.parent / "CLI-README.md")
        packages = subprocess.check_output(
            ["uv", "pip", "list", "--python", str(python), "--format", "json"],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            encoding="utf-8",
        )
        record = {
            "version": version,
            "python": sys.version,
            "platform": platform.platform(),
            "mode": args.mode,
            "executable": str(executable.relative_to(output)),
            "size_bytes": executable.stat().st_size,
            "sha256": digest,
            "dependencies": json.loads(packages),
        }
        (output / "build.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"构建失败：{exc}\n诊断日志：{log_path}", file=sys.stderr)
        return 1
    print(f"构建完成：{executable}\n大小：{executable.stat().st_size / 1024**2:.2f} MiB\nSHA256：{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
