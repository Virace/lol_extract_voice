"""远端 CLI 烟测。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from lol_audio_unpack.manager.utils import find_data_file

pytestmark = [pytest.mark.integration, pytest.mark.remote_live]

LIVE_REGION = os.environ.get("LOL_REMOTE_SMOKE_REGION", "EUW")
GAME_REGION = os.environ.get("LOL_REMOTE_SMOKE_GAME_REGION", "zh_CN")
CHAMPION_ID = os.environ.get("LOL_REMOTE_SMOKE_CHAMPION_ID", "1")
TIMEOUT_SECONDS = int(os.environ.get("LOL_REMOTE_SMOKE_TIMEOUT", "900"))


def _run_cli(output_path: Path) -> subprocess.CompletedProcess[str]:
    """运行最小远端 CLI 链路。

    Args:
        output_path: 本次烟测的独立输出根目录。

    Returns:
        CLI 子进程结果。
    """
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "lol_audio_unpack",
            "update",
            "extract",
            "--champions",
            CHAMPION_ID,
            "--source-mode",
            "remote_snapshot",
            "--remote-live-region",
            LIVE_REGION,
            "--game-region",
            GAME_REGION,
            "--output-path",
            str(output_path),
            "--exclude-type",
            "SFX,MUSIC",
            "--skip-events",
            "--max-workers",
            "1",
            "--log-level",
            "INFO",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )


def _version_root(output_path: Path) -> Path:
    """返回远端 smoke 生成的版本目录。

    Args:
        output_path: CLI 输出根目录。

    Returns:
        manifest 下唯一的版本目录。
    """
    manifest_root = output_path / "manifest"
    version_roots = sorted(path for path in manifest_root.iterdir() if path.is_dir())
    assert len(version_roots) == 1, f"应只生成一个版本目录: {version_roots}"
    return version_roots[0]


def test_remote_snapshot_cli_smoke_extracts_champion_vo(tmp_path: Path) -> None:
    """CLI 应能从远端 live 快照解包一个英雄 VO。"""
    output_path = tmp_path / "remote_cli_smoke"

    result = _run_cli(output_path)

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, output

    version_root = _version_root(output_path)
    data_file = find_data_file(version_root / "data", dev_mode=False)
    assert data_file is not None

    champion_root = output_path / "audios" / version_root.name / "champions"
    champion_dirs = [
        path
        for path in champion_root.iterdir()
        if path.is_dir() and path.name.startswith(f"{CHAMPION_ID}·")
    ]
    assert champion_dirs, f"未找到英雄 {CHAMPION_ID} 的输出目录"

    wem_files = list(champion_dirs[0].rglob("*.wem"))
    assert wem_files, f"英雄 {CHAMPION_ID} 未解包出任何 wem 文件"

    report_file = output_path / "reports" / version_root.name / "champions" / f"_{CHAMPION_ID}_metadata.yaml"
    assert report_file.is_file()
