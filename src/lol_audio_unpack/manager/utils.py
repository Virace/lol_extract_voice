"""兼容导出 manager 子域的历史共享辅助入口。"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as get_package_version

from loguru import logger

from lol_audio_unpack.app.game_version import (
    get_game_version,
    get_lcu_version,
    resolve_game_version,
    validate_install_version,
)
from lol_audio_unpack.manager.files import find_data_file, needs_update, read_data, write_data


def build_metadata_payload(game_version: str, languages: list[str]) -> dict:
    """创建包含标准化元数据的新对象。

    Args:
        game_version: 游戏客户端版本。
        languages: 包含的语言列表。

    Returns:
        一个包含所有元数据的字典。
    """
    try:
        script_version = get_package_version("lol-audio-unpack")
    except PackageNotFoundError:
        script_version = "0.0.0-dev"
        logger.warning("无法获取包版本，请使用 'pip install -e .' 在可编辑模式下安装。将版本设置为 '0.0.0-dev'。")

    metadata = {
        "gameVersion": game_version,
        "scriptName": "lol-audio-unpack",
        "scriptWebsite": "https://github.com/Virace/lol-audio-unpack",
        "scriptVersion": script_version,
        "schemaVersion": "1.0",
        "createdAt": datetime.now().isoformat(),
        "languages": languages,
        "platform": {
            "os": os.name,
            "pythonVersion": sys.version.split(" ")[0],
        },
    }
    return {"metadata": metadata}


create_metadata_object = build_metadata_payload
resolve_context_version = resolve_game_version
validate_local_path_version = validate_install_version
validate_local_version = validate_install_version


__all__ = [
    "build_metadata_payload",
    "create_metadata_object",
    "find_data_file",
    "get_game_version",
    "get_lcu_version",
    "needs_update",
    "read_data",
    "resolve_context_version",
    "resolve_game_version",
    "validate_install_version",
    "validate_local_version",
    "validate_local_path_version",
    "write_data",
]
