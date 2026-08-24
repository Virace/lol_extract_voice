"""本地客户端数据源结构预检。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .types import AppContextValidationError


def _require_directory(path: Path, label: str) -> None:
    """确认必需目录存在且可枚举。

    Args:
        path: 待检查目录。
        label: 面向用户的目录说明。

    Raises:
        AppContextValidationError: 目录缺失、类型错误或不可读取时抛出。
    """
    if not path.exists():
        raise AppContextValidationError(f"本地数据源缺少{label}: {path}")
    if not path.is_dir():
        raise AppContextValidationError(f"本地数据源的{label}不是目录: {path}")
    try:
        next(path.iterdir(), None)
    except OSError as exc:
        raise AppContextValidationError(f"本地数据源的{label}无法读取: {path} | {exc}") from exc


def _read_json_object(path: Path, label: str) -> Mapping[str, Any]:
    """读取必需 JSON 文件并确认顶层为对象。

    Args:
        path: JSON 文件路径。
        label: 面向用户的文件说明。

    Returns:
        解析后的 JSON 对象。

    Raises:
        AppContextValidationError: 文件缺失、不可读或结构无效时抛出。
    """
    if not path.exists():
        raise AppContextValidationError(f"本地数据源缺少{label}: {path}")
    if not path.is_file():
        raise AppContextValidationError(f"本地数据源的{label}不是文件: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AppContextValidationError(f"本地数据源的{label}无法解析: {path} | {exc}") from exc
    if not isinstance(payload, Mapping):
        raise AppContextValidationError(f"本地数据源的{label}顶层必须是 JSON 对象: {path}")
    return payload


def validate_local_source(game_path: Path) -> None:
    """在输出初始化前验证本地客户端或外部准备目录的基础结构。

    本预检只验证所有工作流共享的结构，不提前推断目标实体所需的
    WAD、BIN 或 bank。后者继续由 local resource schema v2 流程按目标校验。

    Args:
        game_path: 本地客户端根目录或外部工具准备出的等价目录。

    Raises:
        AppContextValidationError: 数据源不满足本地基础合同时抛出。
    """
    _require_directory(game_path, "根目录")

    game_root = game_path / "Game"
    final_root = game_root / "DATA" / "FINAL"
    lcu_root = game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    _require_directory(final_root, "GAME FINAL 目录")
    _require_directory(lcu_root, "LCU game-data 目录")

    metadata_path = game_root / "content-metadata.json"
    metadata = _read_json_object(metadata_path, "GAME content-metadata.json")
    version = metadata.get("version")
    if not isinstance(version, str) or not version.strip():
        raise AppContextValidationError(f"本地数据源的 GAME 元数据缺少有效 version: {metadata_path}")

    description_path = lcu_root / "description.json"
    description = _read_json_object(description_path, "LCU description.json")
    if not isinstance(description.get("riotMeta"), Mapping):
        raise AppContextValidationError(f"本地数据源的 LCU description.json 缺少有效 riotMeta: {description_path}")


__all__ = ["validate_local_source"]
