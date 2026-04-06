"""`AudioEntityData` 统一实体构造入口测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lol_audio_unpack.model import AudioEntityData


def test_from_entity_dispatches_to_champion_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def _fake_from_champion(cls, entity_id, reader, include_events=False, *, ctx):  # noqa: ANN001
        captured.update(
            entity_id=entity_id,
            reader=reader,
            include_events=include_events,
            ctx=ctx,
        )
        return sentinel

    monkeypatch.setattr(AudioEntityData, "from_champion", classmethod(_fake_from_champion))

    reader = object()
    ctx = object()
    result = AudioEntityData.from_entity(
        "champion",
        1,
        reader,
        include_events=True,
        ctx=ctx,
    )

    assert result is sentinel
    assert captured == {
        "entity_id": 1,
        "reader": reader,
        "include_events": True,
        "ctx": ctx,
    }


def test_from_entity_dispatches_to_map_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def _fake_from_map(cls, entity_id, reader, include_events=False, *, ctx):  # noqa: ANN001
        captured.update(
            entity_id=entity_id,
            reader=reader,
            include_events=include_events,
            ctx=ctx,
        )
        return sentinel

    monkeypatch.setattr(AudioEntityData, "from_map", classmethod(_fake_from_map))

    reader = object()
    ctx = object()
    result = AudioEntityData.from_entity(
        "map",
        11,
        reader,
        ctx=ctx,
    )

    assert result is sentinel
    assert captured == {
        "entity_id": 11,
        "reader": reader,
        "include_events": False,
        "ctx": ctx,
    }


def test_from_entity_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="未知的实体类型: npc"):
        AudioEntityData.from_entity(
            "npc",
            1,
            SimpleNamespace(),
            ctx=SimpleNamespace(game_region="zh_CN"),
        )
