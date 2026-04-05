"""`runtime.remote.game` 目标计划辅助测试。"""

from __future__ import annotations

from types import SimpleNamespace

from lol_audio_unpack.runtime.remote.game import build_bin_plan, build_extract_plan


def _champion(champion_id: int, alias: str, wad_root: str) -> dict:
    return {
        "id": champion_id,
        "alias": alias,
        "name": alias,
        "wad": {
            "root": wad_root,
            "zh_CN": wad_root.replace(".wad.client", ".zh_CN.wad.client"),
        },
        "skins": [
            {
                "binPath": f"data/characters/{alias}/skins/skin0.bin",
                "chromas": [],
            }
        ],
    }


def _map(map_id: int) -> dict:
    return {
        "id": map_id,
        "wad": {
            "root": f"Game/DATA/FINAL/Maps/Shipping/Map{map_id}/Map{map_id}.wad.client",
            "zh_CN": f"Game/DATA/FINAL/Maps/Shipping/Map{map_id}/Map{map_id}.zh_CN.wad.client",
        },
        "binPath": f"data/maps/shipping/map{map_id}/map{map_id}.bin",
    }


def _build_reader() -> SimpleNamespace:
    champions = {
        1: _champion(1, "Annie", "Game/DATA/FINAL/Champions/Annie.wad.client"),
        66600: _champion(66600, "Ruby_Urgot", "Game/DATA/FINAL/Champions/Ruby_Urgot.wad.client"),
    }
    maps = {
        11: _map(11),
        12: _map(12),
    }
    return SimpleNamespace(
        ctx=SimpleNamespace(
            config=SimpleNamespace(
                include_types=("VO", "SFX"),
                game_region="zh_CN",
            )
        ),
        get_audio_type=lambda category: "VO" if "VO" in category else "SFX",
        get_champions=lambda: list(champions.values()),
        get_maps=lambda: list(maps.values()),
        get_champion=lambda champion_id: champions[champion_id],
        get_map=lambda map_id: maps[map_id],
        get_champion_banks=lambda champion_id: (
            {
                "skins": {
                    "1000": {
                        "CHARACTER_VO": [["vo_path"]],
                        "SFX": [["sfx_path"]],
                    }
                }
            }
            if champion_id == 1
            else {
                "skins": {
                    "1000": {
                        "CHARACTER_VO": [["ruby_vo"]],
                    }
                }
            }
        ),
        get_map_banks=lambda map_id: {
            "banks": {
                "MAP_VO": [["map_vo"]],
                "MAP_SFX": [["map_sfx"]],
            }
        },
    )


def test_build_bin_plan_uses_default_visible_champions_only() -> None:
    """默认 BIN 计划应继续跳过隐藏英雄。"""
    reader = _build_reader()

    plan = build_bin_plan(
        reader=reader,
        target="all",
        champion_ids=None,
        map_ids=None,
    )

    assert plan == {
        "DATA/FINAL/Champions/Annie.wad.client": ["data/characters/Annie/skins/skin0.bin"],
        "DATA/FINAL/Maps/Shipping/Map11/Map11.wad.client": ["data/maps/shipping/map11/map11.bin"],
        "DATA/FINAL/Maps/Shipping/Map12/Map12.wad.client": ["data/maps/shipping/map12/map12.bin"],
    }


def test_build_extract_plan_respects_include_flags_with_explicit_targets() -> None:
    """显式目标与 include 开关组合后应只产出当前阶段允许的实体。"""
    reader = _build_reader()

    plan = build_extract_plan(
        reader=reader,
        champion_ids=(1,),
        map_ids=(11,),
        include_champions=False,
        include_maps=True,
    )

    assert plan == {
        "Game/DATA/FINAL/Maps/Shipping/Map11/Map11.wad.client",
        "Game/DATA/FINAL/Maps/Shipping/Map11/Map11.zh_CN.wad.client",
    }
