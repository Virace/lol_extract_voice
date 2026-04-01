import subprocess

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
    assert "--wav" in result.stdout
    assert "--game-path" in result.stdout


def test_unpack_cli_requires_action_arg() -> None:
    result = _run_unpack_cli()

    assert result.returncode == 1
    output = f"{result.stdout}\n{result.stderr}"
    assert "usage: unpack" in output
    assert "ACTION" in output
