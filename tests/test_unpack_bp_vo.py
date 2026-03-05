from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack import unpack as m_unpack
from lol_audio_unpack.app_context import AppConfig, AppContext, AppPaths
from lol_audio_unpack.model import AudioEntityData

pytestmark = pytest.mark.unit


def test_attach_bp_vo_to_champion_fallback_copy_when_link_fails(tmp_path, monkeypatch):
    version = "16.3"
    manifest_root = tmp_path / "manifest"
    audio_root = tmp_path / "audios"

    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-ban-vo").mkdir(parents=True, exist_ok=True)
    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-choose-vo").mkdir(parents=True, exist_ok=True)

    ban_source = manifest_root / version / "lobby_vo" / "zh_CN" / "champion-ban-vo" / "1.ogg"
    choose_source = manifest_root / version / "lobby_vo" / "zh_CN" / "champion-choose-vo" / "1.ogg"
    ban_source.write_bytes(b"ban")
    choose_source.write_bytes(b"choose")

    game_root = tmp_path / "game"
    output_root = tmp_path / "output"
    ctx = AppContext(
        config=AppConfig(
            game_path=game_root,
            output_path=output_root,
            game_region="zh_CN",
            group_by_type=False,
            with_bp_vo=True,
        ),
        paths=AppPaths(
            audio_path=audio_root,
            temp_path=output_root / "temps",
            log_path=output_root / "logs",
            cache_path=output_root / "cache",
            hash_path=output_root / "hashes",
            report_path=output_root / "reports",
            manifest_path=manifest_root,
            local_version_file=output_root / "game_version",
            game_champion_path=game_root / "Game" / "DATA" / "FINAL" / "Champions",
            game_maps_path=game_root / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping",
            game_lcu_path=game_root / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data",
        ),
        logger=None,
    )
    monkeypatch.setattr(m_unpack.os, "link", lambda _src, _dst: (_ for _ in ()).throw(OSError("no link")))

    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="安妮",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
        sub_entities={},
        wad_root="Game/DATA/FINAL/Champions/Annie.wad.client",
        wad_language=None,
    )
    reader = SimpleNamespace(version=version)

    m_unpack._attach_bp_vo_to_champion(entity_data, reader, ctx=ctx)

    entity_folder = m_unpack.format_entity_folder_name("1", "annie", "安妮", "黑暗之女")
    target_dir = audio_root / version / "champions" / entity_folder / "BP_VO"
    assert (target_dir / "ban.ogg").read_bytes() == b"ban"
    assert (target_dir / "choose.ogg").read_bytes() == b"choose"
