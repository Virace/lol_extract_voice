from pathlib import Path

import pytest
from league_tools.utils.wwiser import Singleton as WwiserSingleton
from league_tools.utils.wwiser import WwiserManager
from riotmanifest import RiotGameData, VersionMatchMode

from lol_audio_unpack.app_context import OperationOptions, create_app_context
from lol_audio_unpack.facade import LolAudioUnpackApp
from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.manager.utils import find_data_file
from lol_audio_unpack.utils.common import Singleton
from tests.remote_disk_usage import monitor_directory_usage

pytestmark = [pytest.mark.integration, pytest.mark.remote_live]

LIVE_REGION = "EUW"
GAME_REGION = "zh_CN"
TARGET_MAP_ID = 11


def _reset_data_reader_singleton() -> None:
    """重置 `DataReader` 单例。"""
    Singleton._instances.pop(DataReader, None)


def _build_remote_context(
    output_path: Path,
    *,
    version: str,
    lcu_manifest_url: str,
    game_manifest_url: str,
    wwiser_path: Path,
):
    """构建远端快照上下文。"""
    return create_app_context(
        cli_overrides={
            "OUTPUT_PATH": str(output_path),
            "GAME_REGION": GAME_REGION,
            "SOURCE_MODE": "remote_snapshot",
            "REMOTE_VERSION": version,
            "REMOTE_LCU_MANIFEST_URL": lcu_manifest_url,
            "REMOTE_GAME_MANIFEST_URL": game_manifest_url,
            "WWISER_PATH": str(wwiser_path),
        },
    )


def _ensure_remote_map_update_ready(
    output_path: Path,
    *,
    version: str,
    lcu_manifest_url: str,
    game_manifest_url: str,
) -> None:
    """确保远端 map update 产物已存在。"""
    data_file = find_data_file(output_path / "manifest" / version / "data", dev_mode=False)
    banks_file = find_data_file(output_path / "manifest" / version / "banks" / "maps" / str(TARGET_MAP_ID), dev_mode=False)
    events_file = find_data_file(output_path / "manifest" / version / "events" / "maps" / str(TARGET_MAP_ID), dev_mode=False)
    if data_file is not None and banks_file is not None and events_file is not None:
        return

    _reset_data_reader_singleton()
    try:
        ctx = create_app_context(
            cli_overrides={
                "OUTPUT_PATH": str(output_path),
                "GAME_REGION": GAME_REGION,
                "SOURCE_MODE": "remote_snapshot",
                "REMOTE_VERSION": version,
                "REMOTE_LCU_MANIFEST_URL": lcu_manifest_url,
                "REMOTE_GAME_MANIFEST_URL": game_manifest_url,
            },
        )
        app = LolAudioUnpackApp(ctx)
        with monitor_directory_usage(output_path, label="remote_update_map11"):
            app.update(OperationOptions(map_ids=(TARGET_MAP_ID,)), target="map")
    finally:
        _reset_data_reader_singleton()


def _ensure_wwiser_ready() -> Path:
    """确保测试使用的 wwiser.pyz 已下载。"""
    tool_dir = Path(".cache") / "tools" / "wwiser"
    tool_dir.mkdir(parents=True, exist_ok=True)
    wwiser_path = tool_dir / "wwiser.pyz"
    if wwiser_path.exists():
        return wwiser_path

    manager = WwiserManager(wwiser_path=tool_dir, auto_download=False)
    downloaded_path = manager.download_wwiser(output_dir=tool_dir)
    WwiserSingleton._instances.pop(WwiserManager, None)
    if downloaded_path is None:
        raise RuntimeError("无法下载 wwiser.pyz，无法执行真实地图 mapping 链路测试。")
    return downloaded_path


def test_remote_snapshot_mapping_single_map_live_latest() -> None:
    """基于最新远端清单执行单地图 `update -> mapping`，验证地图远端链路。"""
    rgd = RiotGameData()
    pair = rgd.resolve_live_manifest_pair(LIVE_REGION, match_mode=VersionMatchMode.IGNORE_REVISION)
    version = str(pair.version)

    output_path = Path(".cache") / "remote_live_map_test" / LIVE_REGION.lower() / version / "update_map11_mapping"
    output_path.mkdir(parents=True, exist_ok=True)

    _ensure_remote_map_update_ready(
        output_path,
        version=version,
        lcu_manifest_url=pair.lcu.url,
        game_manifest_url=pair.game.url,
    )
    wwiser_path = _ensure_wwiser_ready()

    _reset_data_reader_singleton()
    try:
        ctx = _build_remote_context(
            output_path,
            version=version,
            lcu_manifest_url=pair.lcu.url,
            game_manifest_url=pair.game.url,
            wwiser_path=wwiser_path,
        )
        app = LolAudioUnpackApp(ctx)
        with monitor_directory_usage(output_path, label="remote_mapping_map11"):
            app.mapping(
                OperationOptions(max_workers=1, map_ids=(TARGET_MAP_ID,)),
                include_champions=False,
            )
    finally:
        _reset_data_reader_singleton()

    hash_root = output_path / "hashes" / version / "maps"
    mapping_file = find_data_file(hash_root / str(TARGET_MAP_ID), dev_mode=False)
    assert mapping_file is not None
    assert (output_path / "space_usage_reports.json").exists()
