"""unpack 目录包公开导出面的回归测试。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack import unpack as m_unpack
from lol_audio_unpack.app_context import AppConfig, AppContext, AppPaths
from lol_audio_unpack.model import AudioEntityData


def test_unpack_module_keeps_public_batch_entrypoints() -> None:
    assert callable(m_unpack.unpack_all)
    assert callable(m_unpack.unpack_champions)
    assert callable(m_unpack.unpack_maps)
    assert m_unpack.unpack_audio_all is m_unpack.unpack_all


def test_unpack_module_keeps_public_single_entity_entrypoints() -> None:
    assert callable(m_unpack.unpack_entity)
    assert callable(m_unpack.unpack_champion)
    assert callable(m_unpack.unpack_map)
    assert m_unpack.unpack_audio_entity is m_unpack.unpack_entity
    assert m_unpack.unpack_map_audio is m_unpack.unpack_map


def test_unpack_module_keeps_generate_output_path() -> None:
    assert callable(m_unpack.generate_output_path)


def test_generate_output_path_keeps_current_folder_layout(tmp_path: Path) -> None:
    entity = AudioEntityData(
        entity_id="1",
        entity_name="安妮",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
        sub_entities={"1000": {"name": "基础皮肤", "categories": {}}},
        wad_root="Game/root.wad.client",
        wad_language="Game/zh.wad.client",
    )
    ctx = AppContext(
        config=AppConfig(
            game_path=tmp_path / "game",
            output_path=tmp_path,
            group_by_type=False,
        ),
        paths=AppPaths(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            temp_path=tmp_path / "temps",
            log_path=tmp_path / "logs",
            cache_path=tmp_path / "cache",
            hash_path=tmp_path / "hashes",
            report_path=tmp_path / "reports",
            manifest_path=tmp_path / "manifest",
            local_version_file=tmp_path / "game_version",
            game_champion_path=tmp_path / "game" / "Game" / "DATA" / "FINAL" / "Champions",
            game_maps_path=tmp_path / "game" / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping",
            game_lcu_path=tmp_path / "game" / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data",
        ),
    )

    path = m_unpack.generate_output_path(entity, "1000", "VO", ctx=ctx)

    assert path == tmp_path / "audios" / "champions" / "1·annie·安妮·黑暗之女" / "1000·基础皮肤" / "VO"
