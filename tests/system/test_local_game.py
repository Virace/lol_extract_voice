"""使用真实本地客户端验证核心音频处理系统链路。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lol_audio_unpack.app import LolAudioUnpackApp, OperationOptions, create_app_context
from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.manager.files import find_data_file
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.model.binding import BindingRole, Completeness

if TYPE_CHECKING:
    from lol_audio_unpack.app import AppContext

pytestmark = [pytest.mark.system, pytest.mark.local_game]

CHAMPION_ID = 1
JADE_CHAMPION_ID = 60009
COMMON_MAP_ID = 0
MAP_ID = 11
TFT_MAP_ID = 22
DEFAULT_GAME_DRIVES = ("D",)
DEFAULT_GAME_PARTS = ("Games", "Tencent", "WeGameApps", "英雄联盟")


def _game_candidates() -> tuple[Path, ...]:
    """返回当前支持的默认客户端候选目录。"""
    windows = tuple(Path(f"{drive}:/").joinpath(*DEFAULT_GAME_PARTS) for drive in DEFAULT_GAME_DRIVES)
    wsl = tuple(Path("/mnt", drive.lower(), *DEFAULT_GAME_PARTS) for drive in DEFAULT_GAME_DRIVES)
    return windows + wsl


def _resolve_game_path() -> Path:
    """解析真实客户端目录，缺失时让显式系统门禁失败。"""
    configured = os.environ.get("LOL_LOCAL_GAME_PATH", "").strip()
    if configured:
        game_path = Path(configured)
    else:
        candidates = _game_candidates()
        game_path = next((path for path in candidates if path.is_dir()), candidates[0])

    if not game_path.is_dir():
        pytest.fail(
            f"未找到本地游戏目录: {game_path}。请通过 LOL_LOCAL_GAME_PATH 指定客户端根目录。",
            pytrace=False,
        )
    return game_path


def _verify_game_inputs(game_path: Path) -> None:
    """验证系统链路依赖的客户端资源存在。"""
    metadata = game_path / "Game" / "content-metadata.json"
    assert metadata.is_file(), f"缺少版本元数据: {metadata}"

    required_globs = {
        "默认 LCU WAD": "LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad",
        "中文 LCU WAD": "LeagueClient/Plugins/rcp-be-lol-game-data/zh_CN-assets*.wad",
        "英雄 WAD": "Game/DATA/FINAL/Champions/*.wad.client",
        "地图 WAD": "Game/DATA/FINAL/Maps/Shipping/*.wad.client",
    }
    for label, pattern in required_globs.items():
        assert any(game_path.glob(pattern)), f"缺少{label}: {pattern}"


def _verify_manifest(reader: DataReader, *, ctx: AppContext) -> None:
    """验证 banks、events 与本地 binding 已覆盖代表实体。"""
    champion_banks = reader.get_champion_banks(CHAMPION_ID)
    map_banks = reader.get_map_banks(MAP_ID)
    champion_events = reader.get_champion_events(CHAMPION_ID)
    map_events = reader.get_map_events(MAP_ID)

    assert champion_banks and champion_banks.get("skins"), "英雄 banks 为空"
    assert map_banks and map_banks.get("banks"), "地图 banks 为空"
    assert champion_events and champion_events.get("skins"), "英雄 events 为空"
    assert map_events, "地图 events 为空"

    jade_bindings = reader.get_champion_resource_bindings(JADE_CHAMPION_ID)
    assert jade_bindings is not None, "Jade_Fiddlesticks 缺少 resource bindings"
    assert jade_bindings.diagnostics.completeness is Completeness.COMPLETE
    assert jade_bindings.bin_bindings, "Jade_Fiddlesticks 缺少 BIN binding"
    assert all(
        binding.wad and binding.wad.casefold().endswith("/champions/fiddlesticks.wad.client")
        for binding in jade_bindings.bin_bindings
    ), "Jade_Fiddlesticks BIN 未绑定到 Fiddlesticks root WAD"

    jade_entity = AudioEntityData.from_entity("champion", JADE_CHAMPION_ID, reader, ctx=ctx)
    jade_vo_banks = [bank.binding for bank in jade_entity.resource_banks if bank.audio_type == "VO"]
    assert jade_vo_banks, "Jade_Fiddlesticks 缺少 VO binding"
    assert all(
        binding.role is BindingRole.LOCALIZED
        and binding.wad
        and binding.wad.casefold().endswith("/champions/fiddlesticks.zh_cn.wad.client")
        for binding in jade_vo_banks
    ), "Jade_Fiddlesticks VO 未绑定到当前语言 WAD"

    tft_bindings = reader.get_map_resource_bindings(TFT_MAP_ID)
    assert tft_bindings is not None, "Map 22 缺少 resource bindings"
    assert tft_bindings.diagnostics.completeness is Completeness.COMPLETE
    categories = {binding.category for binding in tft_bindings.bank_bindings}
    assert "MODE_TFT_Global_SFX" in categories
    assert any(category.startswith("MODE_TFT_ArenaSkin_") for category in categories)
    assert any(category.startswith("MODE_TFT_NPC_") for category in categories)
    assert any("_Champs_" in category for category in categories)
    assert any(category.startswith(("MUS_Map22", "Music_Map22")) for category in categories)


def _extract_new_wems(
    app: LolAudioUnpackApp,
    options: OperationOptions,
    audio_root: Path,
    *,
    include_champions: bool = True,
) -> set[Path]:
    """执行一次解包并返回该范围新增的 WEM 路径。"""
    before_wems = set(audio_root.rglob("*.wem"))
    app.extract(options, include_champions=include_champions)
    return set(audio_root.rglob("*.wem")) - before_wems


def _verify_mapping(output_path: Path, version: str) -> None:
    """验证普通英雄、旧版英雄和地图均生成原始 mapping 产物。"""
    hash_root = output_path / "hashes" / version
    champion_mapping = find_data_file(hash_root / "champions" / str(CHAMPION_ID), dev_mode=False)
    jade_mapping = find_data_file(hash_root / "champions" / str(JADE_CHAMPION_ID), dev_mode=False)
    map_mapping = find_data_file(hash_root / "maps" / str(MAP_ID), dev_mode=False)

    assert champion_mapping is not None, "未生成英雄 mapping"
    assert jade_mapping is not None, "未生成 Jade_Fiddlesticks mapping"
    assert map_mapping is not None, "未生成地图 mapping"


def test_local_pipeline_updates_extracts_and_maps(tmp_path: Path) -> None:
    """一次完成真实 update、解包与 NativeHIRC mapping 链路。"""
    game_path = _resolve_game_path()
    _verify_game_inputs(game_path)

    output_path = tmp_path / "output"
    ctx = create_app_context(
        settings={
            "GAME_PATH": str(game_path),
            "OUTPUT_PATH": str(output_path),
            "GAME_REGION": "zh_CN",
            "EXCLUDE_TYPE": "",
        },
        force_reload=True,
        dev_mode=False,
    )
    app = LolAudioUnpackApp(ctx)

    app.update(
        OperationOptions(
            champion_ids=(CHAMPION_ID, JADE_CHAMPION_ID),
            map_ids=(COMMON_MAP_ID, MAP_ID, TFT_MAP_ID),
            max_workers=2,
            process_events=True,
        ),
        target="all",
    )

    reader = DataReader(ctx=ctx)
    data_file = find_data_file(ctx.paths.manifest_path / reader.version / "data", dev_mode=False)
    assert data_file is not None, "未生成聚合 data 文件"
    _verify_manifest(reader, ctx=ctx)

    audio_root = ctx.paths.audio_path / reader.version
    champion_wems = _extract_new_wems(
        app,
        OperationOptions(champion_ids=(CHAMPION_ID,), max_workers=2),
        audio_root,
    )
    assert champion_wems, "英雄解包未生成 WEM"

    jade_wems = _extract_new_wems(
        app,
        OperationOptions(champion_ids=(JADE_CHAMPION_ID,), max_workers=2),
        audio_root,
    )
    assert jade_wems, "Jade_Fiddlesticks 解包未生成 WEM"

    map_wems = _extract_new_wems(
        app,
        OperationOptions(map_ids=(MAP_ID,), max_workers=2),
        audio_root,
        include_champions=False,
    )
    assert map_wems, "地图解包未生成 WEM"

    tft_wems = _extract_new_wems(
        app,
        OperationOptions(map_ids=(TFT_MAP_ID,), max_workers=2),
        audio_root,
        include_champions=False,
    )
    assert tft_wems, "Map 22 解包未生成 WEM"

    report_root = ctx.paths.report_path / reader.version
    assert (report_root / "champions" / f"_{CHAMPION_ID}_metadata.yaml").is_file()
    assert (report_root / "champions" / f"_{JADE_CHAMPION_ID}_metadata.yaml").is_file()
    assert (report_root / "maps" / f"_{MAP_ID}_metadata.yaml").is_file()
    assert (report_root / "maps" / f"_{TFT_MAP_ID}_metadata.yaml").is_file()

    app.mapping(OperationOptions(champion_ids=(CHAMPION_ID, JADE_CHAMPION_ID), max_workers=2))
    app.mapping(
        OperationOptions(map_ids=(MAP_ID,), max_workers=2),
        include_champions=False,
    )
    _verify_mapping(output_path, reader.version)
