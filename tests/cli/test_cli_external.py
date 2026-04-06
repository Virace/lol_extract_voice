import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _run_unpack_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "unpack", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_unpack_cli_help_succeeds() -> None:
    result = _run_unpack_cli("--help")

    assert result.returncode == 0, result.stderr
    assert "update" in result.stdout
    assert "extract" in result.stdout
    assert "mapping" in result.stdout


def test_unpack_extract_help_succeeds() -> None:
    result = _run_unpack_cli("extract", "--help")

    assert result.returncode == 0, result.stderr
    assert "--wav-workers" in result.stdout
    assert "--game-path" in result.stdout


def test_unpack_cli_requires_action_arg() -> None:
    result = _run_unpack_cli()

    assert result.returncode == 1
    output = f"{result.stdout}\n{result.stderr}"
    assert "usage: unpack" in output
    assert "ACTION" in output


def test_unpack_cli_rejects_extra_args_in_config_mode() -> None:
    result = _run_unpack_cli("-c", "--champions", "Annie")

    assert result.returncode == 1


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

    result = _run_unpack_cli("-c", str(config_file))

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1
    assert "必须提供至少一个动作" not in output
    assert "未找到有效的游戏目录" in output
