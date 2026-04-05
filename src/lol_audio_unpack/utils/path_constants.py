"""兼容导出历史路径常量与目录命名规则。"""

from __future__ import annotations

from lol_audio_unpack.app.path_layout import (
    AUDIO_TYPE_MUSIC,
    AUDIO_TYPE_SFX,
    AUDIO_TYPE_VO,
    DIR_CHAMPIONS,
    DIR_MAPS,
    ENTITY_NAME_SEPARATOR,
    ENTITY_TYPE_CHAMPION,
    ENTITY_TYPE_MAP,
    GAME_DIR_CHAMPIONS,
    GAME_DIR_MAPS,
    format_entity_folder_name,
    format_sub_entity_folder_name,
    get_game_dir_name,
    get_output_dir_name,
)

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
