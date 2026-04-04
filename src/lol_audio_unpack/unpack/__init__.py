"""音频解包公开入口。"""

from .batch import unpack_all, unpack_champions, unpack_maps
from .entity import generate_output_path, unpack_champion, unpack_entity, unpack_map

# 兼容层：等全项目统一收口后再移除旧名。
unpack_audio_all = unpack_all
unpack_audio_entity = unpack_entity
unpack_map_audio = unpack_map

__all__ = [
    "generate_output_path",
    "unpack_all",
    "unpack_audio_all",
    "unpack_entity",
    "unpack_audio_entity",
    "unpack_champion",
    "unpack_champions",
    "unpack_map",
    "unpack_map_audio",
    "unpack_maps",
]
