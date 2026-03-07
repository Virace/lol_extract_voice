from pathlib import Path

import pytest
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
TARGET_CHAMPION_IDS = (1, 103, 555)


def _reset_data_reader_singleton() -> None:
    """重置 `DataReader` 单例。"""
    Singleton._instances.pop(DataReader, None)


def _build_remote_context(output_path: Path, *, version: str, lcu_manifest_url: str, game_manifest_url: str):
    """构建远端快照上下文。"""
    return create_app_context(
        cli_overrides={
            "OUTPUT_PATH": str(output_path),
            "GAME_REGION": GAME_REGION,
            "SOURCE_MODE": "remote_snapshot",
            "REMOTE_VERSION": version,
            "REMOTE_LCU_MANIFEST_URL": lcu_manifest_url,
            "REMOTE_GAME_MANIFEST_URL": game_manifest_url,
        },
    )


def _ensure_remote_update_ready(
    output_path: Path,
    *,
    version: str,
    lcu_manifest_url: str,
    game_manifest_url: str,
) -> None:
    """确保远端 update 产物已存在。"""
    data_file = find_data_file(output_path / "manifest" / version / "data", dev_mode=False)
    banks_root = output_path / "manifest" / version / "banks" / "champions"
    if data_file is not None and all((banks_root / f"{champion_id}.msgpack").exists() for champion_id in TARGET_CHAMPION_IDS):
        return

    _reset_data_reader_singleton()
    try:
        ctx = _build_remote_context(
            output_path,
            version=version,
            lcu_manifest_url=lcu_manifest_url,
            game_manifest_url=game_manifest_url,
        )
        app = LolAudioUnpackApp(ctx)
        app.update(OperationOptions(champion_ids=TARGET_CHAMPION_IDS), target="skin")
    finally:
        _reset_data_reader_singleton()


def test_remote_snapshot_extract_champions_live_latest_vo_only() -> None:
    """基于最新远端清单执行 `update -> extract`，验证 VO-only 远端解包链路。"""
    rgd = RiotGameData()
    pair = rgd.resolve_live_manifest_pair(LIVE_REGION, match_mode=VersionMatchMode.IGNORE_REVISION)
    version = str(pair.version)

    output_path = Path(".cache") / "remote_live_update_test" / LIVE_REGION.lower() / version / "update_champions_1_103_555"
    output_path.mkdir(parents=True, exist_ok=True)

    _ensure_remote_update_ready(
        output_path,
        version=version,
        lcu_manifest_url=pair.lcu.url,
        game_manifest_url=pair.game.url,
    )

    _reset_data_reader_singleton()
    try:
        ctx = _build_remote_context(
            output_path,
            version=version,
            lcu_manifest_url=pair.lcu.url,
            game_manifest_url=pair.game.url,
        )
        app = LolAudioUnpackApp(ctx)
        with monitor_directory_usage(output_path, label="remote_extract_champions_1_103_555_vo_only"):
            app.extract(OperationOptions(champion_ids=TARGET_CHAMPION_IDS))
    finally:
        _reset_data_reader_singleton()

    audio_root = output_path / "audios" / version / "champions"
    assert audio_root.exists()

    for champion_id in TARGET_CHAMPION_IDS:
        champion_dirs = [path for path in audio_root.iterdir() if path.is_dir() and path.name.startswith(f"{champion_id}·")]
        assert champion_dirs, f"未找到英雄 {champion_id} 的输出目录"
        champion_wems = list(champion_dirs[0].rglob("*.wem"))
        assert champion_wems, f"英雄 {champion_id} 未解包出任何 wem 文件"

    prepared_root = output_path / "_prepared_game" / "Game" / "DATA" / "FINAL" / "Champions"
    assert prepared_root.exists()
    language_wads = list(prepared_root.glob("*.zh_CN.wad.client"))
    assert language_wads, "VO-only 解包后未找到任何语言 WAD"
    assert (output_path / "space_usage_reports.json").exists()
