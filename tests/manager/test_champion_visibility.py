from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.app.facade as m_facade
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.targets import (
    filter_default_visible_champions,
    get_default_hidden_champion_markers,
    should_hide_champion_by_default,
)
from lol_audio_unpack.model import generate_champion_tasks


def _champion(champion_id: int, alias: str, wad_root: str, *, name: str = "") -> dict:
    return {
        "id": champion_id,
        "alias": alias,
        "name": name,
        "wad": {"root": wad_root},
    }


def _build_ctx(tmp_path: Path):
    return SimpleNamespace(
        config=SimpleNamespace(
            game_path=str(tmp_path / "game"),
            manifest_path=str(tmp_path / "manifest"),
            dev_mode=False,
            source_mode="local_path",
            include_types=("VO", "SFX", "MUSIC"),
            with_bp_vo=False,
            remote_live_region="",
            output_path=str(tmp_path / "output"),
            hash_path=str(tmp_path / "hashes"),
            cache_path=str(tmp_path / "cache"),
        ),
        paths=SimpleNamespace(
            manifest_path=tmp_path / "manifest",
            hash_path=tmp_path / "hashes",
            cache_path=tmp_path / "cache",
            audio_path=tmp_path / "audios",
            report_path=tmp_path / "reports",
            game_path=tmp_path / "game",
        ),
        runtime_cache={},
    )


def test_hidden_champion_markers_use_alias_wad_and_id() -> None:
    champion = _champion(
        66600,
        "Ruby_Urgot",
        "Game/DATA/FINAL/Champions/Ruby_Wukong.wad.client",
        name="Doom Bot Urgot",
    )

    assert get_default_hidden_champion_markers(champion) == ("alias:ruby", "wad:ruby", "id:666")
    assert should_hide_champion_by_default(champion) is True


def test_filter_default_visible_champions_hides_ruby_series() -> None:
    champions = [
        _champion(1, "Annie", "Game/DATA/FINAL/Champions/Annie.wad.client"),
        _champion(66600, "Ruby_Urgot", "Game/DATA/FINAL/Champions/Ruby_Urgot.wad.client"),
        _champion(666123, "TestAlias", "Game/DATA/FINAL/Champions/Garen.wad.client"),
    ]

    visible = filter_default_visible_champions(champions)

    assert [champion["id"] for champion in visible] == [1]


def test_generate_champion_tasks_skips_hidden_by_default_but_allows_explicit_ids() -> None:
    champions = [
        _champion(1, "Annie", "Game/DATA/FINAL/Champions/Annie.wad.client"),
        _champion(66600, "Ruby_Urgot", "Game/DATA/FINAL/Champions/Ruby_Urgot.wad.client"),
    ]
    reader = SimpleNamespace(get_champions=lambda: champions)

    all_tasks = generate_champion_tasks(reader, None)
    explicit_tasks = generate_champion_tasks(reader, [66600])

    assert all_tasks == [("champion", 1, "英雄ID 1")]
    assert explicit_tasks == [("champion", 66600, "英雄ID 66600")]


def test_resolve_champion_ids_keeps_hidden_alias_available_when_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = _build_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)

    fake_reader = SimpleNamespace(
        get_champions=lambda: [
            _champion(1, "Annie", "Game/DATA/FINAL/Champions/Annie.wad.client"),
            _champion(66600, "Ruby_Urgot", "Game/DATA/FINAL/Champions/Ruby_Urgot.wad.client"),
        ]
    )

    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: fake_reader)

    champion_ids = app.resolve_champion_ids(["Ruby_Urgot"])

    assert champion_ids == (66600,)
