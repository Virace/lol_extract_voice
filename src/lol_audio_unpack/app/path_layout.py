"""应用层共享的实体路径布局与命名规则。"""

from __future__ import annotations

from typing import Literal

ENTITY_TYPE_CHAMPION: Literal["champion"] = "champion"
ENTITY_TYPE_MAP: Literal["map"] = "map"

AUDIO_TYPE_VO: Literal["VO"] = "VO"
AUDIO_TYPE_SFX: Literal["SFX"] = "SFX"
AUDIO_TYPE_MUSIC: Literal["MUSIC"] = "MUSIC"

DIR_CHAMPIONS: Literal["champions"] = "champions"
DIR_MAPS: Literal["maps"] = "maps"

GAME_DIR_CHAMPIONS: Literal["Champions"] = "Champions"
GAME_DIR_MAPS: Literal["Maps"] = "Maps"

ENTITY_NAME_SEPARATOR: Literal["·"] = "·"


def get_output_dir_name(entity_type: str) -> str:
    """获取输出目录名称。

    Args:
        entity_type: 实体类型，支持 ``champion`` 或 ``map``。

    Returns:
        对应的小写复数目录名。

    Raises:
        ValueError: 当实体类型未知时抛出。
    """
    if entity_type == ENTITY_TYPE_CHAMPION:
        return DIR_CHAMPIONS
    if entity_type == ENTITY_TYPE_MAP:
        return DIR_MAPS
    raise ValueError(f"未知的实体类型: {entity_type}")


def get_game_dir_name(entity_type: str) -> str:
    """获取游戏原始目录名称。

    Args:
        entity_type: 实体类型，支持 ``champion`` 或 ``map``。

    Returns:
        游戏资源中的原始目录名。

    Raises:
        ValueError: 当实体类型未知时抛出。
    """
    if entity_type == ENTITY_TYPE_CHAMPION:
        return GAME_DIR_CHAMPIONS
    if entity_type == ENTITY_TYPE_MAP:
        return GAME_DIR_MAPS
    raise ValueError(f"未知的实体类型: {entity_type}")


def format_entity_folder_name(
    entity_id: str,
    entity_alias: str,
    entity_name: str,
    entity_title: str | None = None,
) -> str:
    """格式化实体文件夹名称。

    Args:
        entity_id: 实体 ID。
        entity_alias: 实体别名。
        entity_name: 实体显示名称。
        entity_title: 可选标题。

    Returns:
        以 `·` 连接的实体文件夹名称。
    """
    parts = [entity_id, entity_alias, entity_name]
    if entity_title:
        parts.append(entity_title)
    return ENTITY_NAME_SEPARATOR.join(parts)


def format_sub_entity_folder_name(sub_id: str, sub_name: str) -> str:
    """格式化子实体文件夹名称。

    Args:
        sub_id: 子实体 ID。
        sub_name: 子实体名称。

    Returns:
        以 `·` 连接的子实体文件夹名称。
    """
    return ENTITY_NAME_SEPARATOR.join([sub_id, sub_name])


__all__ = [
    "AUDIO_TYPE_MUSIC",
    "AUDIO_TYPE_SFX",
    "AUDIO_TYPE_VO",
    "DIR_CHAMPIONS",
    "DIR_MAPS",
    "ENTITY_NAME_SEPARATOR",
    "ENTITY_TYPE_CHAMPION",
    "ENTITY_TYPE_MAP",
    "GAME_DIR_CHAMPIONS",
    "GAME_DIR_MAPS",
    "format_entity_folder_name",
    "format_sub_entity_folder_name",
    "get_game_dir_name",
    "get_output_dir_name",
]
