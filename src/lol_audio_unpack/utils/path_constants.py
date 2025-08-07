# 🐍 In the face of ambiguity, refuse the temptation to guess.
# 🐼 面对不确定性，拒绝妄加猜测
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/1/15 12:00
# @Update  : 2025/8/7 11:19
# @Detail  : 路径常量统一管理


"""路径常量管理模块

统一管理所有目录名称常量，确保跨平台一致性。
所有输出目录均使用小写，避免大小写敏感问题。
"""

from typing import Literal

# === 实体类型常量 ===
ENTITY_TYPE_CHAMPION: Literal["champion"] = "champion"
ENTITY_TYPE_MAP: Literal["map"] = "map"

# === 音频类型常量 ===
AUDIO_TYPE_VO: Literal["VO"] = "VO"
AUDIO_TYPE_SFX: Literal["SFX"] = "SFX"
AUDIO_TYPE_MUSIC: Literal["MUSIC"] = "MUSIC"

# === 输出目录名称常量（统一小写） ===
DIR_CHAMPIONS: Literal["champions"] = "champions"
DIR_MAPS: Literal["maps"] = "maps"

# === 游戏原始目录名称（保持游戏原始格式） ===
GAME_DIR_CHAMPIONS: Literal["Champions"] = "Champions"
GAME_DIR_MAPS: Literal["Maps"] = "Maps"

# === 命名分隔符常量 ===
ENTITY_NAME_SEPARATOR: Literal["·"] = "·"


def get_output_dir_name(entity_type: str) -> str:
    """获取输出目录名称（小写复数）

    :param entity_type: 实体类型 ("champion" 或 "map")
    :returns: 输出目录名称 ("champions" 或 "maps")
    :raises ValueError: 未知的实体类型
    """
    if entity_type == ENTITY_TYPE_CHAMPION:
        return DIR_CHAMPIONS
    elif entity_type == ENTITY_TYPE_MAP:
        return DIR_MAPS
    else:
        raise ValueError(f"未知的实体类型: {entity_type}")


def get_game_dir_name(entity_type: str) -> str:
    """获取游戏原始目录名称（保持游戏原始格式）

    :param entity_type: 实体类型 ("champion" 或 "map")
    :returns: 游戏目录名称 ("Champions" 或 "Maps")
    :raises ValueError: 未知的实体类型
    """
    if entity_type == ENTITY_TYPE_CHAMPION:
        return GAME_DIR_CHAMPIONS
    elif entity_type == ENTITY_TYPE_MAP:
        return GAME_DIR_MAPS
    else:
        raise ValueError(f"未知的实体类型: {entity_type}")


def format_entity_folder_name(
    entity_id: str, entity_alias: str, entity_name: str, entity_title: str | None = None
) -> str:
    """格式化实体文件夹名称

    生成格式：[ID]·[alias]·[name]·[title]（如果提供 title）
    或：[ID]·[alias]·[name]（如果不提供 title）

    :param entity_id: 实体ID
    :param entity_alias: 实体别名
    :param entity_name: 实体名称
    :param entity_title: 实体标题（可选）
    :returns: 格式化的文件夹名称
    """
    parts = [entity_id, entity_alias, entity_name]
    if entity_title:
        parts.append(entity_title)
    return ENTITY_NAME_SEPARATOR.join(parts)


def format_sub_entity_folder_name(sub_id: str, sub_name: str) -> str:
    """格式化子实体文件夹名称（如皮肤）

    生成格式：[sub_id]·[sub_name]

    :param sub_id: 子实体ID
    :param sub_name: 子实体名称
    :returns: 格式化的文件夹名称
    """
    return ENTITY_NAME_SEPARATOR.join([sub_id, sub_name])
