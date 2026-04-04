"""`app.targets` 共享目标范围辅助测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lol_audio_unpack.app.targets import (
    build_tasks,
    filter_default_visible_champions,
    get_default_hidden_champion_markers,
    get_default_visible_champions,
    iter_entity_refs,
    resolve_scope,
    should_hide_champion_by_default,
)


def _champion(champion_id: int, alias: str, wad_root: str) -> dict:
    return {
        "id": champion_id,
        "alias": alias,
        "name": alias,
        "wad": {"root": wad_root},
    }


def _map(map_id: int) -> dict:
    return {
        "id": map_id,
        "name": f"Map {map_id}",
    }


def _build_reader() -> SimpleNamespace:
    champions = [
        _champion(1, "Annie", "Game/DATA/FINAL/Champions/Annie.wad.client"),
        _champion(66600, "Ruby_Urgot", "Game/DATA/FINAL/Champions/Ruby_Urgot.wad.client"),
    ]
    maps = [_map(11), _map(12)]
    return SimpleNamespace(
        get_champions=lambda: champions,
        get_maps=lambda: maps,
    )


@pytest.mark.parametrize(
    ("champion_ids", "map_ids", "expected"),
    [
        (None, None, ("all", True, True)),
        ((1,), None, ("skin", True, False)),
        (None, (11,), ("map", False, True)),
        ((1,), (11,), ("all", True, True)),
    ],
)
def test_resolve_scope_matches_existing_backend_contract(
    champion_ids: tuple[int, ...] | None,
    map_ids: tuple[int, ...] | None,
    expected: tuple[str, bool, bool],
) -> None:
    """统一范围解析应保持当前门面约定不变。"""
    assert resolve_scope(champion_ids=champion_ids, map_ids=map_ids) == expected


def test_iter_entity_refs_uses_default_visible_champions_and_all_maps() -> None:
    """默认枚举应沿用隐藏英雄过滤与全地图规则。"""
    reader = _build_reader()

    assert list(iter_entity_refs(reader)) == [
        ("champion", 1),
        ("map", 11),
        ("map", 12),
    ]


def test_default_visible_champion_policy_uses_stable_markers() -> None:
    """默认可见英雄策略应由 targets 模块直接维护。"""
    hidden = _champion(66600, "Ruby_Urgot", "Game/DATA/FINAL/Champions/Ruby_Urgot.wad.client")
    visible = _champion(1, "Annie", "Game/DATA/FINAL/Champions/Annie.wad.client")
    reader = _build_reader()

    assert get_default_hidden_champion_markers(hidden) == ("alias:ruby", "wad:ruby", "id:666")
    assert should_hide_champion_by_default(hidden) is True
    assert filter_default_visible_champions([visible, hidden]) == [visible]
    assert get_default_visible_champions(reader) == [visible]


def test_build_tasks_validates_explicit_ids_and_formats_labels() -> None:
    """任务构造应保留显式校验与描述文案。"""
    reader = _build_reader()

    assert build_tasks(reader, champion_ids=(1,), include_maps=False) == [
        ("champion", 1, "英雄ID 1"),
    ]
    assert build_tasks(reader, map_ids=(11,), include_champions=False) == [
        ("map", 11, "地图ID 11"),
    ]

    with pytest.raises(ValueError, match=r"无效的地图ID: \[999\]"):
        build_tasks(reader, map_ids=(999,), include_champions=False)
