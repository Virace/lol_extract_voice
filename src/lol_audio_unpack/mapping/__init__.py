"""事件映射公开入口。"""

from __future__ import annotations

from loguru import logger

from lol_audio_unpack.manager import DataReader

from .batch import build_all, build_champions, build_maps, execute_tasks
from .entity import build_champion, build_entity, build_map, integrate_entity
from .session import RuntimeCache, describe_hirc_backend

__all__ = [
    "RuntimeCache",
    "build_all",
    "build_champion",
    "build_champions",
    "build_entity",
    "build_map",
    "build_maps",
    "describe_hirc_backend",
    "execute_tasks",
    "integrate_entity",
    "MappingRuntimeCache",
    "build_audio_event_mapping",
    "build_champion_mapping",
    "build_champions_mapping",
    "build_map_mapping",
    "build_maps_mapping",
    "build_mapping_all",
    "execute_mapping_tasks",
    "integrate_entity_data",
    "main",
]

# 兼容层：后续统一收口后再移除旧名。
MappingRuntimeCache = RuntimeCache
build_audio_event_mapping = build_entity
build_champion_mapping = build_champion
build_champions_mapping = build_champions
build_map_mapping = build_map
build_maps_mapping = build_maps
build_mapping_all = build_all
execute_mapping_tasks = execute_tasks
integrate_entity_data = integrate_entity


def main() -> None:
    """运行 mapping 示例入口。

    Args:
        无。
    """

    from lol_audio_unpack import setup_app  # noqa: PLC0415

    ctx = setup_app(dev_mode=True, log_level="INFO")
    logger.disable("league_tools")

    reader = DataReader(ctx=ctx)
    result = build_champion(1, reader, ctx=ctx)
    logger.info(f"映射结果: {len(result.get('skins', {}))} 个皮肤")
