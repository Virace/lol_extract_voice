import json
from pathlib import Path

import pytest
from riotmanifest import RiotGameData, VersionMatchMode

from lol_audio_unpack.app_context import OperationOptions, create_app_context
from lol_audio_unpack.facade import LolAudioUnpackApp
from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.manager.utils import find_data_file, read_data
from lol_audio_unpack.utils.common import Singleton
from tests.remote_disk_usage import monitor_directory_usage

pytestmark = [pytest.mark.integration, pytest.mark.remote_live]

LIVE_REGION = "EUW"
GAME_REGION = "zh_CN"
TARGET_CHAMPION_IDS = (1, 103, 555)


def _reset_data_reader_singleton() -> None:
    """重置 `DataReader` 单例，避免跨测试污染。"""
    Singleton._instances.pop(DataReader, None)


def test_remote_snapshot_update_champions_live_latest() -> None:
    """基于最新远端清单执行 DataUpdater + BinUpdater 的最小闭环。"""
    rgd = RiotGameData()
    pair = rgd.resolve_live_manifest_pair(LIVE_REGION, match_mode=VersionMatchMode.IGNORE_REVISION)
    version = str(pair.version)

    output_path = Path(".cache") / "remote_live_update_test" / LIVE_REGION.lower() / version / "update_champions_1_103_555"
    output_path.mkdir(parents=True, exist_ok=True)

    snapshot_file = output_path / "remote_snapshot_context.json"
    snapshot_file.write_text(
        json.dumps(
            {
                "live_region": LIVE_REGION,
                "game_region": GAME_REGION,
                "version": version,
                "champion_ids": list(TARGET_CHAMPION_IDS),
                "lcu_manifest_url": pair.lcu.url,
                "game_manifest_url": pair.game.url,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    _reset_data_reader_singleton()
    try:
        ctx = create_app_context(
            cli_overrides={
                "OUTPUT_PATH": str(output_path),
                "GAME_REGION": GAME_REGION,
                "SOURCE_MODE": "remote_snapshot",
                "REMOTE_VERSION": version,
                "REMOTE_LCU_MANIFEST_URL": pair.lcu.url,
                "REMOTE_GAME_MANIFEST_URL": pair.game.url,
            },
        )

        app = LolAudioUnpackApp(ctx)
        with monitor_directory_usage(output_path, label="remote_update_champions_1_103_555"):
            app.update(
                OperationOptions(
                    champion_ids=TARGET_CHAMPION_IDS,
                ),
                target="skin",
            )

        data_file_base = output_path / "manifest" / version / "data"
        data_file = find_data_file(data_file_base, dev_mode=False)
        assert data_file is not None

        merged = read_data(data_file_base, dev_mode=False)
        assert merged
        for champion_id in TARGET_CHAMPION_IDS:
            champion_key = str(champion_id)
            assert champion_key in merged.get("champions", {})

            banks_file_base = output_path / "manifest" / version / "banks" / "champions" / champion_key
            banks_data = read_data(banks_file_base, dev_mode=False)
            assert banks_data
            assert banks_data.get("skins")

        use_local_bin_flag = output_path / "manifest" / version / ".use_local_bin"
        assert use_local_bin_flag.exists()
        assert (output_path / "space_usage_reports.json").exists()
    finally:
        _reset_data_reader_singleton()
