"""共享音频实体模型与任务生成逻辑。"""

from __future__ import annotations

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.manager.data_reader import get_default_visible_champions

from .entity import AudioEntityData


def generate_champion_tasks(reader: DataReader, champion_ids: list[int] | None = None) -> list[tuple[str, int, str]]:
    """生成英雄任务集。

    Args:
        reader: 数据读取器。
        champion_ids: 指定的英雄 ID 列表；为 ``None`` 时表示所有默认可见英雄。

    Returns:
        list[tuple[str, int, str]]: 任务元组列表 ``[("champion", id, description), ...]``。

    Raises:
        ValueError: 指定的英雄 ID 不存在时抛出。
    """
    all_champions = reader.get_champions()
    available_ids = {champ.get("id") for champ in all_champions if champ.get("id") is not None}

    if champion_ids is None:
        return [
            ("champion", champ.get("id"), f"英雄ID {champ.get('id')}")
            for champ in get_default_visible_champions(reader)
            if champ.get("id") is not None
        ]

    invalid_ids = [cid for cid in champion_ids if cid not in available_ids]
    if invalid_ids:
        raise ValueError(f"无效的英雄ID: {invalid_ids}")

    return [("champion", cid, f"英雄ID {cid}") for cid in champion_ids]


def generate_map_tasks(reader: DataReader, map_ids: list[int] | None = None) -> list[tuple[str, int, str]]:
    """生成地图任务集。

    Args:
        reader: 数据读取器。
        map_ids: 指定的地图 ID 列表；为 ``None`` 时表示所有地图。

    Returns:
        list[tuple[str, int, str]]: 任务元组列表 ``[("map", id, description), ...]``。

    Raises:
        ValueError: 指定的地图 ID 不存在时抛出。
    """
    maps = reader.get_maps()
    available_ids = {map_data.get("id") for map_data in maps if map_data.get("id") is not None}

    if map_ids is None:
        return [
            ("map", map_data.get("id"), f"地图ID {map_data.get('id')}")
            for map_data in maps
            if map_data.get("id") is not None
        ]

    invalid_ids = [mid for mid in map_ids if mid not in available_ids]
    if invalid_ids:
        raise ValueError(f"无效的地图ID: {invalid_ids}")

    return [("map", mid, f"地图ID {mid}") for mid in map_ids]


__all__ = [
    "AudioEntityData",
    "generate_champion_tasks",
    "generate_map_tasks",
]
