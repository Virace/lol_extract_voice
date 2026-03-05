from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack import mapping as m_mapping
from lol_audio_unpack import unpack as m_unpack
from lol_audio_unpack.app_context import AppConfig, AppContext, AppPaths
from lol_audio_unpack.model import AudioEntityData

pytestmark = pytest.mark.unit


def _build_ctx(
    tmp_path: Path,
    *,
    game_region: str = "zh_CN",
    group_by_type: bool = False,
    with_bp_vo: bool = False,
    wwiser_path: Path | None = None,
) -> AppContext:
    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    app_config = AppConfig(
        game_path=game_path,
        output_path=output_path,
        game_region=game_region,
        group_by_type=group_by_type,
        with_bp_vo=with_bp_vo,
        wwiser_path=wwiser_path,
    )
    app_paths = AppPaths(
        audio_path=output_path / "audios",
        temp_path=output_path / "temps",
        log_path=output_path / "logs",
        cache_path=output_path / "cache",
        hash_path=output_path / "hashes",
        report_path=output_path / "reports",
        manifest_path=output_path / "manifest",
        local_version_file=output_path / "game_version",
        game_champion_path=game_path / "Game" / "DATA" / "FINAL" / "Champions",
        game_maps_path=game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping",
        game_lcu_path=game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data",
    )
    return AppContext(config=app_config, paths=app_paths, logger=None)


def test_audio_entity_from_champion_uses_ctx_region_and_game_path(tmp_path: Path) -> None:
    ctx = _build_ctx(tmp_path, game_region="en_US")
    wad_file = ctx.config.game_path / "Game" / "en.wad.client"
    wad_file.parent.mkdir(parents=True, exist_ok=True)
    wad_file.write_bytes(b"wad")

    reader = SimpleNamespace(
        get_champion=lambda _id: {
            "id": 1,
            "alias": "Annie",
            "names": {"zh_CN": "安妮", "en_US": "Annie"},
            "titles": {"zh_CN": "黑暗之女", "en_US": "The Dark Child"},
            "skins": [{"id": 1000, "isBase": True, "skinNames": {"zh_CN": "基础皮肤", "en_US": "Base Skin"}}],
            "wad": {"root": "Game/root.wad.client", "en_US": "Game/en.wad.client"},
        },
        get_champion_banks=lambda _id: {"skins": {"1000": {"CHARACTER_VO": [["Game/en_events.bnk"]]}}},
        get_champion_events=lambda _id: {"skins": {"1000": {"events": {}}}},
    )

    entity_data = AudioEntityData.from_champion(1, reader, ctx=ctx)

    assert entity_data.entity_name == "Annie"
    assert entity_data.wad_language == "Game/en.wad.client"
    assert entity_data.get_wad_path("VO", ctx=ctx) == wad_file


def test_generate_output_path_supports_ctx_grouping(tmp_path: Path) -> None:
    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="安妮",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
        sub_entities={"1000": {"name": "基础皮肤", "categories": {}}},
        wad_root="Game/root.wad.client",
        wad_language="Game/zh.wad.client",
    )

    by_type_ctx = _build_ctx(tmp_path, group_by_type=True)
    by_entity_ctx = _build_ctx(tmp_path, group_by_type=False)

    path_by_type = m_unpack.generate_output_path(entity_data, "1000", "VO", ctx=by_type_ctx)
    path_by_entity = m_unpack.generate_output_path(entity_data, "1000", "VO", ctx=by_entity_ctx)
    relative_path = m_unpack._generate_relative_path(entity_data, "1000")

    assert path_by_type == by_type_ctx.paths.audio_path / "VO" / relative_path
    assert path_by_entity == by_entity_ctx.paths.audio_path / relative_path / "VO"


def test_attach_bp_vo_to_champion_uses_ctx_without_global_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    version = "16.3"
    ctx = _build_ctx(tmp_path, game_region="zh_CN", with_bp_vo=True)

    manifest_root = ctx.paths.manifest_path
    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-ban-vo").mkdir(parents=True, exist_ok=True)
    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-choose-vo").mkdir(parents=True, exist_ok=True)

    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-ban-vo" / "1.ogg").write_bytes(b"ban")
    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-choose-vo" / "1.ogg").write_bytes(b"choose")

    monkeypatch.setattr(m_unpack.os, "link", lambda _src, _dst: (_ for _ in ()).throw(OSError("no link")))

    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="安妮",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
        sub_entities={},
        wad_root="Game/root.wad.client",
        wad_language=None,
    )
    reader = SimpleNamespace(version=version)

    m_unpack._attach_bp_vo_to_champion(entity_data, reader, ctx=ctx)

    entity_folder = m_unpack.format_entity_folder_name("1", "annie", "安妮", "黑暗之女")
    target_dir = ctx.paths.audio_path / version / "champions" / entity_folder / "BP_VO"
    assert (target_dir / "ban.ogg").read_bytes() == b"ban"
    assert (target_dir / "choose.ogg").read_bytes() == b"choose"


def test_execute_mapping_tasks_passes_ctx_to_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wwiser_file = tmp_path / "wwiser.pyz"
    wwiser_file.write_bytes(b"dummy")
    ctx = _build_ctx(tmp_path, wwiser_path=wwiser_file)

    captured: dict[str, object] = {}

    def fake_wwiser_manager(path: Path | str | None) -> object:
        captured["wwiser_path"] = path
        return object()

    def fake_build_champion_mapping(*args, **kwargs) -> dict[str, object]:
        captured["ctx"] = kwargs.get("ctx")
        return {}

    monkeypatch.setattr(m_mapping, "WwiserManager", fake_wwiser_manager)
    monkeypatch.setattr(m_mapping, "build_champion_mapping", fake_build_champion_mapping)

    reader = SimpleNamespace()
    m_mapping.execute_mapping_tasks([("champion", 1, "英雄ID 1")], reader, max_workers=1, ctx=ctx)

    assert captured["wwiser_path"] == wwiser_file
    assert captured["ctx"] == ctx
