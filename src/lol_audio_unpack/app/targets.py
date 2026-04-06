"""应用层共享的目标范围与任务构造辅助。"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

EntityRef = tuple[str, int]
EntityTask = tuple[str, int, str]


def get_default_hidden_champion_markers(champion: Mapping[str, Any]) -> tuple[str, ...]:
    """返回英雄默认隐藏命中的稳定特征。

    说明：
        英雄名会随地区本地化变化，因此默认隐藏规则只依赖稳定字段：
        alias、根 WAD 文件名和 ID 前缀。
    """
    markers: list[str] = []

    alias = str(champion.get("alias", "")).strip().casefold()
    if alias.startswith("ruby_"):
        markers.append("alias:ruby")

    wad_info = champion.get("wad", {})
    wad_root = str(wad_info.get("root", "")) if isinstance(wad_info, dict) else ""
    wad_filename = Path(wad_root).name.casefold()
    if wad_filename.startswith("ruby_"):
        markers.append("wad:ruby")

    champion_id = str(champion.get("id", "")).strip()
    if champion_id.startswith("666"):
        markers.append("id:666")

    return tuple(markers)


def should_hide_champion_by_default(champion: Mapping[str, Any]) -> bool:
    """判断英雄是否应在默认列表与默认全量任务中隐藏。"""
    return bool(get_default_hidden_champion_markers(champion))


def filter_default_visible_champions(champions: Iterable[dict]) -> list[dict]:
    """过滤默认可见的英雄集合。"""
    return [champion for champion in champions if not should_hide_champion_by_default(champion)]


def get_default_visible_champions(reader: Any) -> list[dict]:
    """从读取器中获取默认可见的英雄集合。"""
    return filter_default_visible_champions(reader.get_champions())


def resolve_scope(
    *,
    champion_ids: Sequence[int] | None,
    map_ids: Sequence[int] | None,
) -> tuple[str, bool, bool]:
    """根据实体选择推导后端目标范围。

    Args:
        champion_ids: 指定的英雄 ID 集合；为 ``None`` 表示未显式限定。
        map_ids: 指定的地图 ID 集合；为 ``None`` 表示未显式限定。

    Returns:
        tuple[str, bool, bool]:
            ``(target, include_champions, include_maps)`` 元组。
    """
    if champion_ids is None and map_ids is None:
        return "all", True, True
    if champion_ids is not None and map_ids is not None:
        return "all", True, True
    if champion_ids is not None:
        return "skin", True, False
    return "map", False, True


def iter_entity_refs(
    reader: Any,
    *,
    champion_ids: Sequence[int] | None = None,
    map_ids: Sequence[int] | None = None,
    include_champions: bool = True,
    include_maps: bool = True,
) -> Iterator[EntityRef]:
    """按统一规则枚举当前范围内的实体 ID。

    Args:
        reader: 数据读取器。
        champion_ids: 指定的英雄 ID 集合；为 ``None`` 时回退到默认可见英雄。
        map_ids: 指定的地图 ID 集合；为 ``None`` 时回退到全部地图。
        include_champions: 是否包含英雄。
        include_maps: 是否包含地图。

    Yields:
        tuple[str, int]: ``(entity_type, entity_id)`` 元组。
    """
    if champion_ids is not None:
        if include_champions:
            for champion_id in champion_ids:
                yield "champion", int(champion_id)
    elif include_champions:
        for champion in get_default_visible_champions(reader):
            champion_id = champion.get("id")
            if champion_id is None:
                continue
            yield "champion", int(champion_id)

    if map_ids is not None:
        if include_maps:
            for map_id in map_ids:
                yield "map", int(map_id)
    elif include_maps:
        for map_data in reader.get_maps():
            map_id = map_data.get("id")
            if map_id is None:
                continue
            yield "map", int(map_id)


def build_tasks(
    reader: Any,
    *,
    champion_ids: Sequence[int] | None = None,
    map_ids: Sequence[int] | None = None,
    include_champions: bool = True,
    include_maps: bool = True,
) -> list[EntityTask]:
    """构建带描述文案的实体任务元组列表。

    Args:
        reader: 数据读取器。
        champion_ids: 指定的英雄 ID 集合；为 ``None`` 时回退到默认可见英雄。
        map_ids: 指定的地图 ID 集合；为 ``None`` 时回退到全部地图。
        include_champions: 是否包含英雄。
        include_maps: 是否包含地图。

    Returns:
        list[EntityTask]: ``[(entity_type, entity_id, description), ...]``。

    Raises:
        ValueError: 显式指定的英雄或地图 ID 不存在时抛出。
    """
    if include_champions or champion_ids is not None:
        _validate_ids(
            label="英雄ID",
            ids=champion_ids,
            available_ids=_collect_ids(reader.get_champions()),
        )
    if include_maps or map_ids is not None:
        _validate_ids(
            label="地图ID",
            ids=map_ids,
            available_ids=_collect_ids(reader.get_maps()),
        )

    tasks: list[EntityTask] = []
    for entity_type, entity_id in iter_entity_refs(
        reader,
        champion_ids=champion_ids,
        map_ids=map_ids,
        include_champions=include_champions,
        include_maps=include_maps,
    ):
        label = "英雄ID" if entity_type == "champion" else "地图ID"
        tasks.append((entity_type, entity_id, f"{label} {entity_id}"))
    return tasks


def _collect_ids(items: Sequence[dict]) -> set[int]:
    """提取数据列表中的可用整数 ID。"""
    return {int(item_id) for item in items if (item_id := item.get("id")) is not None}


def _validate_ids(*, label: str, ids: Sequence[int] | None, available_ids: set[int]) -> None:
    """校验显式传入的实体 ID 是否存在。"""
    if ids is None:
        return

    invalid_ids = [int(item_id) for item_id in ids if int(item_id) not in available_ids]
    if invalid_ids:
        raise ValueError(f"无效的{label}: {invalid_ids}")


__all__ = [
    "EntityTask",
    "build_tasks",
    "filter_default_visible_champions",
    "get_default_hidden_champion_markers",
    "get_default_visible_champions",
    "iter_entity_refs",
    "resolve_scope",
    "should_hide_champion_by_default",
]
