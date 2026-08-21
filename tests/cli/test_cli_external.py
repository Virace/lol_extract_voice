"""从真实子进程入口验证 CLI 的最小用户链路。"""

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
EXIT_INPUT = 2


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "unpack", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_unpack_cli_help_succeeds() -> None:
    result = _run_cli("--help")

    assert result.returncode == 0, result.stderr
    assert "update" in result.stdout
    assert "extract" in result.stdout
    assert "mapping" in result.stdout


def test_unpack_cli_config_mode_uses_enabled_actions_from_config(tmp_path: Path) -> None:
    config_file = tmp_path / "lol-audio-unpack.ini"
    config_file.write_text(
        (
            "[app]\n"
            f"game_path = {tmp_path / 'missing-game'}\n"
            f"output_path = {tmp_path / 'output'}\n"
            "\n"
            "[extract]\n"
            "enable = true\n"
        ),
        encoding="utf-8",
    )

    result = _run_cli("-c", str(config_file))

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == EXIT_INPUT
    assert "必须提供至少一个动作" not in output
    assert "未找到有效的游戏目录" in output
