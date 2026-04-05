"""CLI 显式命令 helper 的语义测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lol_audio_unpack.cli.invocation import (
    DEFAULT_CLI_MAX_WORKERS,
    DEFAULT_WAV_FORMAT,
    DEFAULT_WAV_RETRIES,
    DEFAULT_WAV_TIMEOUT,
    DEFAULT_WAV_WORKERS,
    CliInvocationRequest,
    CliInvocationValidationError,
    build_argv,
)
from lol_audio_unpack.config import SettingKey
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths, get_default_output_root, get_default_wwiser_path

EXPECTED_WAV_FORMAT = "float"


def _build_runtime_paths(tmp_path: Path):
    """构造测试使用的独立 runtime paths。"""
    isolated_root = tmp_path / "isolated_env"
    isolated_root.mkdir(parents=True, exist_ok=True)
    return detect_runtime_paths(
        is_frozen=False,
        cwd=isolated_root,
        executable=isolated_root / "python.exe",
    )


def test_build_explicit_cli_argv_omits_defaults_but_keeps_required_and_changed_values(tmp_path: Path) -> None:
    """完整显式命令应保留必需项，同时省略默认值。"""
    runtime_paths = _build_runtime_paths(tmp_path)
    request = CliInvocationRequest(
        actions=("extract", "wav"),
        settings=(
            (SettingKey.SOURCE_MODE, "local_path"),
            (SettingKey.GAME_PATH, "game-root"),
            (SettingKey.OUTPUT_PATH, str(get_default_output_root(runtime_paths))),
            (SettingKey.GAME_REGION, "zh_CN"),
            (SettingKey.WITH_BP_VO, True),
            (SettingKey.EXCLUDE_TYPE, ""),
        ),
        max_workers=DEFAULT_CLI_MAX_WORKERS,
        wav_enabled=True,
        wav_workers=DEFAULT_WAV_WORKERS,
        wav_timeout=DEFAULT_WAV_TIMEOUT,
        wav_retries=DEFAULT_WAV_RETRIES,
        wav_format=DEFAULT_WAV_FORMAT,
    )

    argv = build_argv(request, runtime_paths=runtime_paths)

    assert argv[:5] == ["uv", "run", "unpack", "extract", "wav"]
    assert "--game-path" in argv
    assert argv[argv.index("--game-path") + 1] == "game-root"
    assert "--with-bp-vo" in argv
    assert "--exclude-type" in argv
    assert argv[argv.index("--exclude-type") + 1] == ""
    assert "--output-path" not in argv
    assert "--source-mode" not in argv
    assert "--game-region" not in argv
    assert "--max-workers" not in argv
    assert "--wav-workers" not in argv
    assert "--wav-timeout" not in argv
    assert "--wav-retries" not in argv
    assert "--wav-format" not in argv


def test_build_explicit_cli_argv_requires_game_path_in_local_mode(tmp_path: Path) -> None:
    """本地模式缺少游戏目录时应拒绝构造命令。"""
    runtime_paths = _build_runtime_paths(tmp_path)
    request = CliInvocationRequest(
        actions=("extract",),
        settings=((SettingKey.SOURCE_MODE, "local_path"),),
    )

    with pytest.raises(CliInvocationValidationError, match="game_path"):
        build_argv(request, runtime_paths=runtime_paths)


def test_build_explicit_cli_argv_does_not_require_wwiser_for_mapping_fallback(tmp_path: Path) -> None:
    """未提供 wwiser 路径时，mapping 命令仍可构造。"""
    runtime_paths = _build_runtime_paths(tmp_path)
    request = CliInvocationRequest(
        actions=("mapping",),
        settings=((SettingKey.GAME_PATH, "game-root"),),
    )

    argv = build_argv(request, runtime_paths=runtime_paths)

    assert argv[:4] == ["uv", "run", "unpack", "mapping"]
    assert "--wwiser-path" not in argv


def test_build_explicit_cli_argv_omits_gui_default_wwiser_path(tmp_path: Path) -> None:
    """GUI 默认 wwiser 路径不应被当作显式 CLI 参数展开。"""
    runtime_paths = _build_runtime_paths(tmp_path)
    request = CliInvocationRequest(
        actions=("mapping",),
        settings=(
            (SettingKey.GAME_PATH, "game-root"),
            (SettingKey.WWISER_PATH, str(get_default_wwiser_path(runtime_paths))),
        ),
    )

    argv = build_argv(request, runtime_paths=runtime_paths)

    assert "--wwiser-path" not in argv


def test_build_explicit_cli_argv_uses_negative_flag_for_non_default_mapping_option(tmp_path: Path) -> None:
    """mapping 非默认布尔项应输出对应的反向开关。"""
    runtime_paths = _build_runtime_paths(tmp_path)
    request = CliInvocationRequest(
        actions=("mapping",),
        settings=((SettingKey.GAME_PATH, "game-root"),),
        integrate_data=False,
    )

    argv = build_argv(request, runtime_paths=runtime_paths)

    assert "--no-integrate-data" in argv
    assert "--integrate-data" not in argv


def test_build_explicit_cli_argv_includes_non_default_wav_tuning(tmp_path: Path) -> None:
    """启用 WAV 且参数偏离默认值时，应展开对应显式参数。"""
    runtime_paths = _build_runtime_paths(tmp_path)
    request = CliInvocationRequest(
        actions=("extract", "wav"),
        settings=((SettingKey.GAME_PATH, "game-root"),),
        wav_enabled=True,
        wav_workers=8,
        wav_timeout=12,
        wav_retries=5,
        wav_format=EXPECTED_WAV_FORMAT,
    )

    argv = build_argv(request, runtime_paths=runtime_paths)

    assert argv[:5] == ["uv", "run", "unpack", "extract", "wav"]
    assert argv[argv.index("--wav-workers") + 1] == "8"
    assert argv[argv.index("--wav-timeout") + 1] == "12"
    assert argv[argv.index("--wav-retries") + 1] == "5"
    assert argv[argv.index("--wav-format") + 1] == EXPECTED_WAV_FORMAT
