# 🐍 In the face of ambiguity, refuse the temptation to guess.
# 🐼 面对不确定性，拒绝妄加猜测
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/1/15 12:00
# @Update  : 2025/8/7 6:48
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
