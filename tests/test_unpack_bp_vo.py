from pathlib import Path
from types import SimpleNamespace

import pytest
from loguru import logger

from lol_audio_unpack.app_context import AppConfig, AppContext, AppPaths
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.unpack import bp_vo as unpack_bp_vo
from lol_audio_unpack.unpack import entity as unpack_entity
from lol_audio_unpack.utils.path_constants import format_entity_folder_name

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
            wav_path=output_root / "wavs",
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
    )
    monkeypatch.setattr(unpack_bp_vo.os, "link", lambda _src, _dst: (_ for _ in ()).throw(OSError("no link")))

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

    unpack_bp_vo.attach_bp_vo(entity_data, reader, ctx=ctx)

    entity_folder = format_entity_folder_name("1", "annie", "安妮", "黑暗之女")
    target_dir = audio_root / version / "champions" / entity_folder / "BP_VO"
    assert (target_dir / "ban.ogg").read_bytes() == b"ban"
    assert (target_dir / "choose.ogg").read_bytes() == b"choose"


def test_unpack_entity_uses_warning_summary_for_partial_parse_failures(tmp_path, monkeypatch):
    version = "16.3"
    manifest_root = tmp_path / "manifest"
    audio_root = tmp_path / "audios"
    game_root = tmp_path / "game"
    output_root = tmp_path / "output"

    wad_dir = game_root / "Game"
    wad_dir.mkdir(parents=True, exist_ok=True)
    (wad_dir / "zh_audio.wad.client").write_bytes(b"wad")

    ctx = AppContext(
        config=AppConfig(
            game_path=game_root,
            output_path=output_root,
            game_region="zh_CN",
            group_by_type=False,
            with_bp_vo=False,
        ),
        paths=AppPaths(
            audio_path=audio_root,
            wav_path=output_root / "wavs",
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
    )

    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="安妮",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
        sub_entities={
            "1000": {
                "name": "经典",
                "categories": {
                    "CHARACTER_VO": [["assets/test_audio.bnk", "assets/test_audio.wpk"]],
                },
            }
        },
        wad_root="Game/root.wad.client",
        wad_language="Game/zh_audio.wad.client",
    )

    reader = SimpleNamespace(version=version, get_audio_type=lambda _category: "VO")

    class _FakeWad:
        @staticmethod
        def extract(paths, raw=True):
            assert raw is True
            return [b"fake-bnk", b"fake-wpk"]

    class _FakeWpkFile:
        filename = "ok.wem"

        @staticmethod
        def save_file(target: Path) -> None:
            target.write_bytes(b"ok")

    class _FakeWPK:
        def __init__(self, _raw: bytes) -> None:
            pass

        @staticmethod
        def extract_files():
            return [_FakeWpkFile()]

    def _fail_bnk(_raw: bytes):
        raise RuntimeError("bnk boom")

    monkeypatch.setattr(unpack_entity, "_get_wad_instance", lambda *_args, **_kwargs: _FakeWad())
    monkeypatch.setattr(unpack_entity, "BNK", _fail_bnk)
    monkeypatch.setattr(unpack_entity, "WPK", _FakeWPK)

    log_lines: list[str] = []
    logger.enable("lol_audio_unpack")
    sink_id = logger.add(
        lambda message: log_lines.append(str(message).rstrip()),
        format="{level}|{message}",
    )

    try:
        unpack_entity.unpack_entity(entity_data, reader, ctx=ctx)
    finally:
        logger.remove(sink_id)

    assert any("WARNING|处理BNK文件失败: bnk boom | 文件路径: assets/test_audio.bnk" in line for line in log_lines)
    assert any("WARNING|⚠️ 安妮 解包完成 - 成功 1 个文件" in line and "失败 1" in line for line in log_lines)
    assert not any("ERROR|❌ 安妮 解包失败" in line for line in log_lines)
