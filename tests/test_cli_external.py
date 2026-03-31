import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _run_unpack_cli(*args: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    """通过 subprocess 调用外部 `unpack` CLI。"""
    repo_root = Path(__file__).resolve().parents[1]
    cmd = ["uv", "run", "unpack", *args]
    return subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_unpack_cli_help_succeeds():
    """`--help` 应成功并包含核心参数说明。"""
    result = _run_unpack_cli("--help")
    assert result.returncode == 0, result.stderr
    assert "--extract" in result.stdout
    assert "--mapping" in result.stdout


def test_unpack_cli_version_succeeds():
    """`--version` 应成功返回版本号。"""
    result = _run_unpack_cli("--version")
    assert result.returncode == 0, result.stderr
    assert "3." in result.stdout


def test_unpack_cli_requires_action_arg():
    """无动作参数时应返回错误。"""
    result = _run_unpack_cli()
    assert result.returncode == 1
    output = f"{result.stdout}\n{result.stderr}"
    assert "usage: unpack" in output


def test_unpack_cli_integrate_data_requires_mapping():
    """`--integrate-data` 必须与映射参数一起使用。"""
    result = _run_unpack_cli("--update", "--integrate-data")
    assert result.returncode == 1
