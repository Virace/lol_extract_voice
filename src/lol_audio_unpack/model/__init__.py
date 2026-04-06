"""共享音频实体模型与兼容任务辅助入口。"""

from __future__ import annotations

from collections.abc import Sequence

from lol_audio_unpack.app.targets import build_tasks
from lol_audio_unpack.manager import DataReader

from .entity import AudioEntityData


def generate_champion_tasks(
    reader: DataReader,
    champion_ids: Sequence[int] | None = None,
) -> list[tuple[str, int, str]]:
    """生成英雄任务集。

    Args:
        reader: 数据读取器。
        champion_ids: 指定的英雄 ID 列表；为 ``None`` 时表示所有默认可见英雄。

    Returns:
        list[tuple[str, int, str]]: 任务元组列表 ``[("champion", id, description), ...]``。

    Raises:
        ValueError: 指定的英雄 ID 不存在时抛出。
    """
    return build_tasks(
        reader,
        champion_ids=champion_ids,
        include_maps=False,
    )


def generate_map_tasks(
    reader: DataReader,
    map_ids: Sequence[int] | None = None,
) -> list[tuple[str, int, str]]:
    """生成地图任务集。

    Args:
        reader: 数据读取器。
        map_ids: 指定的地图 ID 列表；为 ``None`` 时表示所有地图。

    Returns:
        list[tuple[str, int, str]]: 任务元组列表 ``[("map", id, description), ...]``。

    Raises:
        ValueError: 指定的地图 ID 不存在时抛出。
    """
    return build_tasks(
        reader,
        map_ids=map_ids,
        include_champions=False,
    )


__all__ = [
    "AudioEntityData",
    "generate_champion_tasks",
    "generate_map_tasks",
]
