import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from loguru import logger

from lol_audio_unpack.app.types import SourceMode
from lol_audio_unpack.manager import data_updater as m_data_updater

pytestmark = pytest.mark.integration


def _build_updater(game_path: Path, version: str = "16.3"):
    updater = m_data_updater.DataUpdater.__new__(m_data_updater.DataUpdater)
    updater.ctx = SimpleNamespace(
        config=SimpleNamespace(
            game_path=game_path,
            game_region="zh_CN",
            dev_mode=False,
            source_mode=SourceMode.LOCAL_PATH,
            with_bp_vo=False,
        ),
        paths=SimpleNamespace(
            game_maps_path=game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping",
            game_champion_path=game_path / "Game" / "DATA" / "FINAL" / "Champions",
            game_lcu_path=game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data",
        ),
    )
    updater.game_path = game_path
    updater.version = version
    return updater


def test_extract_wad_data_collects_all_default_asset_volumes(tmp_path, monkeypatch):
    wad_root = tmp_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    wad_root.mkdir(parents=True, exist_ok=True)
    (wad_root / "default-assets.wad").write_bytes(b"")
    (wad_root / "default-assets2.wad").write_bytes(b"")
    (wad_root / "description.json").write_text(
        json.dumps(
            {
                "riotMeta": {
                    "globalAssetBundles": ["default-assets.wad", "default-assets2.wad"],
                    "perLocaleAssetBundles": {"zh_CN": ["zh_CN-assets.wad"]},
                }
            }
        ),
        encoding="utf-8",
    )

    calls = []

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, hash_table, out_dir):
            calls.append((self.path.name, list(hash_table)))
            return []

    monkeypatch.setattr(m_data_updater, "WAD", FakeWAD)

    updater = _build_updater(tmp_path)
    updater._extract_wad_data(tmp_path / "out", "en_us")

    assert [name for name, _ in calls] == ["default-assets.wad", "default-assets2.wad"]
    for _, hash_table in calls:
        assert "plugins/rcp-be-lol-game-data/global/default/v1/champion-summary.json" in hash_table
        assert "plugins/rcp-be-lol-game-data/global/default/v1/maps.json" in hash_table


def test_extract_wad_data_collects_all_region_asset_volumes(tmp_path, monkeypatch):
    wad_root = tmp_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    wad_root.mkdir(parents=True, exist_ok=True)
    (wad_root / "zh_CN-assets.wad").write_bytes(b"")
    (wad_root / "zh_CN-assets2.wad").write_bytes(b"")
    (wad_root / "description.json").write_text(
        json.dumps(
            {
                "riotMeta": {
                    "globalAssetBundles": ["default-assets.wad"],
                    "perLocaleAssetBundles": {"zh_CN": ["zh_CN-assets.wad", "zh_CN-assets2.wad"]},
                }
            }
        ),
        encoding="utf-8",
    )

    calls = []

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, hash_table, out_dir):
            calls.append((self.path.name, list(hash_table)))
            return []

    monkeypatch.setattr(m_data_updater, "WAD", FakeWAD)

    updater = _build_updater(tmp_path)
    updater._extract_wad_data(tmp_path / "out", "zh_CN")

    assert [name for name, _ in calls] == ["zh_CN-assets.wad", "zh_CN-assets2.wad"]
    for _, hash_table in calls:
        assert "plugins/rcp-be-lol-game-data/global/zh_CN/v1/champion-summary.json" in hash_table
        assert "plugins/rcp-be-lol-game-data/global/zh_CN/v1/maps.json" in hash_table


def test_extract_wad_data_uses_description_global_bundle_list(tmp_path, monkeypatch):
    wad_root = tmp_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    wad_root.mkdir(parents=True, exist_ok=True)
    (wad_root / "base-assets-a.wad").write_bytes(b"")
    (wad_root / "base-assets-b.wad").write_bytes(b"")
    (wad_root / "description.json").write_text(
        json.dumps(
            {
                "riotMeta": {
                    "globalAssetBundles": ["base-assets-a.wad", "base-assets-b.wad"],
                    "perLocaleAssetBundles": {"zh_CN": ["zh_CN-assets.wad"]},
                }
            }
        ),
        encoding="utf-8",
    )

    calls = []

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, hash_table, out_dir):
            calls.append((self.path.name, list(hash_table)))
            return []

    monkeypatch.setattr(m_data_updater, "WAD", FakeWAD)

    updater = _build_updater(tmp_path)
    updater._extract_wad_data(tmp_path / "out", "en_us")

    assert [name for name, _ in calls] == ["base-assets-a.wad", "base-assets-b.wad"]


def test_extract_wad_data_uses_description_locale_bundle_list(tmp_path, monkeypatch):
    wad_root = tmp_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    wad_root.mkdir(parents=True, exist_ok=True)
    (wad_root / "zh_CN-pack-a.wad").write_bytes(b"")
    (wad_root / "zh_CN-pack-b.wad").write_bytes(b"")
    (wad_root / "description.json").write_text(
        json.dumps(
            {
                "riotMeta": {
                    "globalAssetBundles": ["default-assets.wad"],
                    "perLocaleAssetBundles": {"zh_CN": ["zh_CN-pack-a.wad", "zh_CN-pack-b.wad"]},
                }
            }
        ),
        encoding="utf-8",
    )

    calls = []

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, hash_table, out_dir):
            calls.append((self.path.name, list(hash_table)))
            return []

    monkeypatch.setattr(m_data_updater, "WAD", FakeWAD)

    updater = _build_updater(tmp_path)
    updater._extract_wad_data(tmp_path / "out", "zh_CN")

    assert [name for name, _ in calls] == ["zh_CN-pack-a.wad", "zh_CN-pack-b.wad"]


def test_extract_wad_data_tries_champion_details_after_summary(tmp_path, monkeypatch):
    wad_root = tmp_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    wad_root.mkdir(parents=True, exist_ok=True)
    (wad_root / "default-assets.wad").write_bytes(b"")
    (wad_root / "description.json").write_text(
        json.dumps(
            {
                "riotMeta": {
                    "globalAssetBundles": ["default-assets.wad"],
                    "perLocaleAssetBundles": {},
                }
            }
        ),
        encoding="utf-8",
    )

    calls = []

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, hash_table, out_dir):
            calls.append((self.path.name, list(hash_table)))

            # 第一轮提取基础文件时，伪造 champion-summary.json 供后续读取
            if any(path.endswith("champion-summary.json") for path in hash_table):
                summary_virtual_path = next(path for path in hash_table if path.endswith("champion-summary.json"))
                summary_output = out_dir(summary_virtual_path)
                summary_output.parent.mkdir(parents=True, exist_ok=True)
                summary_output.write_text(
                    json.dumps([{"id": 1, "alias": "Annie", "name": "安妮"}, {"id": -1, "alias": "None", "name": ""}]),
                    encoding="utf-8",
                )
            return []

    monkeypatch.setattr(m_data_updater, "WAD", FakeWAD)

    updater = _build_updater(tmp_path)
    updater._extract_wad_data(tmp_path / "out", "en_us")

    all_requested_paths = [path for _, hash_table in calls for path in hash_table]
    assert "plugins/rcp-be-lol-game-data/global/default/v1/champions/1.json" in all_requested_paths


def test_extract_wad_data_logs_bin_metadata_preparation(tmp_path, monkeypatch):
    wad_root = tmp_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    wad_root.mkdir(parents=True, exist_ok=True)
    (wad_root / "default-assets.wad").write_bytes(b"")
    (wad_root / "description.json").write_text(
        json.dumps(
            {
                "riotMeta": {
                    "globalAssetBundles": ["default-assets.wad"],
                    "perLocaleAssetBundles": {},
                }
            }
        ),
        encoding="utf-8",
    )

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, hash_table, out_dir):
            if any(path.endswith("champion-summary.json") for path in hash_table):
                summary_virtual_path = next(path for path in hash_table if path.endswith("champion-summary.json"))
                summary_output = out_dir(summary_virtual_path)
                summary_output.parent.mkdir(parents=True, exist_ok=True)
                summary_output.write_text(
                    json.dumps([{"id": 1, "alias": "Annie", "name": "安妮"}, {"id": -1, "alias": "None", "name": ""}]),
                    encoding="utf-8",
                )
            return []

    monkeypatch.setattr(m_data_updater, "WAD", FakeWAD)

    updater = _build_updater(tmp_path)
    log_lines: list[str] = []
    logger.enable("lol_audio_unpack")
    sink_id = logger.add(lambda message: log_lines.append(str(message).rstrip()), format="{level}|{message}")

    try:
        updater._extract_wad_data(tmp_path / "out", "en_us")
    finally:
        logger.remove(sink_id)

    assert any("DEBUG|准备提取 1 个英雄详细信息，用于后续 bin 元数据装配" in line for line in log_lines)
    assert any("SUCCESS|英雄信息提取完成，共 1 个英雄，将进入 bin 元数据装配" in line for line in log_lines)


def test_extract_wad_data_returns_when_region_wad_missing(tmp_path, monkeypatch):
    calls = []

    class FakeWAD:
        def __init__(self, path):
            self.path = path

        def extract(self, hash_table, out_dir):
            calls.append((self.path, hash_table))
            return []

    monkeypatch.setattr(m_data_updater, "WAD", FakeWAD)

    updater = _build_updater(tmp_path)
    updater._extract_wad_data(tmp_path / "out", "zh_CN")

    assert calls == []


def test_extract_wad_data_includes_bp_vo_when_enabled(tmp_path, monkeypatch):
    wad_root = tmp_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    wad_root.mkdir(parents=True, exist_ok=True)
    (wad_root / "zh_CN-assets.wad").write_bytes(b"")
    (wad_root / "description.json").write_text(
        json.dumps(
            {
                "riotMeta": {
                    "globalAssetBundles": ["default-assets.wad"],
                    "perLocaleAssetBundles": {"zh_CN": ["zh_CN-assets.wad"]},
                }
            }
        ),
        encoding="utf-8",
    )

    calls = []

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, hash_table, out_dir):
            calls.append((self.path.name, list(hash_table)))

            if any(path.endswith("champion-summary.json") for path in hash_table):
                summary_virtual_path = next(path for path in hash_table if path.endswith("champion-summary.json"))
                summary_output = out_dir(summary_virtual_path)
                summary_output.parent.mkdir(parents=True, exist_ok=True)
                summary_output.write_text(
                    json.dumps([{"id": 1, "alias": "Annie", "name": "安妮"}, {"id": -1, "alias": "None", "name": ""}]),
                    encoding="utf-8",
                )
            return []

    monkeypatch.setattr(m_data_updater, "WAD", FakeWAD)

    updater = _build_updater(tmp_path)
    updater.ctx.config.with_bp_vo = True
    updater._extract_wad_data(tmp_path / "out", "zh_CN")

    all_requested_paths = [path for _, hash_table in calls for path in hash_table]
    assert "plugins/rcp-be-lol-game-data/global/zh_CN/v1/champion-ban-vo/1.ogg" in all_requested_paths
    assert "plugins/rcp-be-lol-game-data/global/zh_CN/v1/champion-choose-vo/1.ogg" in all_requested_paths
    assert "plugins/rcp-be-lol-game-data/global/default/v1/champion-sfx-audios/1.ogg" in all_requested_paths


def test_extract_wad_data_writes_default_sfx_audio_into_region_output(tmp_path, monkeypatch):
    wad_root = tmp_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    wad_root.mkdir(parents=True, exist_ok=True)
    (wad_root / "zh_CN-assets.wad").write_bytes(b"")
    (wad_root / "description.json").write_text(
        json.dumps(
            {
                "riotMeta": {
                    "globalAssetBundles": ["default-assets.wad"],
                    "perLocaleAssetBundles": {"zh_CN": ["zh_CN-assets.wad"]},
                }
            }
        ),
        encoding="utf-8",
    )

    extracted_outputs: list[Path] = []

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, hash_table, out_dir):
            if any(path.endswith("champion-summary.json") for path in hash_table):
                summary_virtual_path = next(path for path in hash_table if path.endswith("champion-summary.json"))
                summary_output = out_dir(summary_virtual_path)
                summary_output.parent.mkdir(parents=True, exist_ok=True)
                summary_output.write_text(
                    json.dumps([{"id": 1, "alias": "Annie", "name": "安妮"}]),
                    encoding="utf-8",
                )

            for path in hash_table:
                if path.endswith("champion-sfx-audios/1.ogg"):
                    output = out_dir(path)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b"sfx")
                    extracted_outputs.append(output)

            return []

    monkeypatch.setattr(m_data_updater, "WAD", FakeWAD)

    updater = _build_updater(tmp_path)
    updater.ctx.config.with_bp_vo = True
    updater._extract_wad_data(tmp_path / "out", "zh_CN")

    assert extracted_outputs == [tmp_path / "out" / updater.version / "zh_CN" / "champion-sfx-audios" / "1.ogg"]
    assert extracted_outputs[0].read_bytes() == b"sfx"


def test_persist_bp_vo_files_copies_new_sfx_category(tmp_path):
    updater = _build_updater(tmp_path)
    updater.version_manifest_path = tmp_path / "manifest" / updater.version
    updater.process_languages = ["zh_CN"]

    temp_root = tmp_path / "temp"
    source_dir = temp_root / updater.version / "zh_CN" / "champion-sfx-audios"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "1.ogg").write_bytes(b"sfx")

    updater._persist_bp_vo_files(temp_root)

    target_file = updater.version_manifest_path / "lobby" / "zh_CN" / "champion-sfx-audios" / "1.ogg"
    assert target_file.read_bytes() == b"sfx"


def test_merge_and_build_data_keeps_remote_map_wad_info_without_local_files(tmp_path):
    updater = _build_updater(tmp_path)
    updater.ctx.config.source_mode = SourceMode.REMOTE_SNAPSHOT
    updater.process_languages = ["default"]
    updater._is_dev_mode = lambda: False

    base_path = tmp_path / updater.version / "default"
    base_path.mkdir(parents=True, exist_ok=True)
    (base_path / "champion-summary.json").write_text("[]", encoding="utf-8")
    (base_path / "maps.json").write_text(
        json.dumps([{"id": 11, "mapStringId": "SR", "name": "召唤师峡谷"}]),
        encoding="utf-8",
    )

    captured = {}

    def fake_write_data(data: dict, _base: Path, *, dev_mode: bool) -> None:
        captured["data"] = data
        captured["dev_mode"] = dev_mode

    original_write_data = m_data_updater.write_data
    m_data_updater.write_data = fake_write_data
    try:
        updater._merge_and_build_data(tmp_path)
    finally:
        m_data_updater.write_data = original_write_data

    result = captured["data"]
    assert captured["dev_mode"] is False
    assert result["maps"]["11"]["wad"]["root"] == "Game/DATA/FINAL/Maps/Shipping/Map11.wad.client"


def test_merge_and_build_data_logs_bin_metadata_summary(tmp_path):
    updater = _build_updater(tmp_path)
    updater.ctx.config.source_mode = SourceMode.LOCAL_PATH
    updater.process_languages = ["default"]
    updater._is_dev_mode = lambda: False

    base_path = tmp_path / updater.version / "default"
    champions_path = base_path / "champions"
    champions_path.mkdir(parents=True, exist_ok=True)
    (base_path / "champion-summary.json").write_text(
        json.dumps([{"id": 1, "alias": "Annie", "name": "安妮", "description": "desc"}]),
        encoding="utf-8",
    )
    (champions_path / "1.json").write_text(
        json.dumps(
            {
                "title": "黑暗之女",
                "skins": [
                    {
                        "id": "1000",
                        "name": "经典",
                        "isBase": True,
                        "chromas": [{"id": "1001", "name": "猩红"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (base_path / "maps.json").write_text(
        json.dumps([{"id": 11, "mapStringId": "SR", "name": "召唤师峡谷"}]),
        encoding="utf-8",
    )

    captured = {}
    log_lines: list[str] = []

    def fake_write_data(data: dict, _base: Path, *, dev_mode: bool) -> None:
        captured["data"] = data
        captured["dev_mode"] = dev_mode

    original_write_data = m_data_updater.write_data
    m_data_updater.write_data = fake_write_data
    logger.enable("lol_audio_unpack")
    sink_id = logger.add(lambda message: log_lines.append(str(message).rstrip()), format="{level}|{message}")
    try:
        updater._merge_and_build_data(tmp_path)
    finally:
        logger.remove(sink_id)
        m_data_updater.write_data = original_write_data

    assert captured["dev_mode"] is False
    assert any("INFO|合并英雄数据并装配 bin 元数据..." in line for line in log_lines)
    assert any("DEBUG|英雄 bin 元数据装配完成，共 1 个英雄，1 个皮肤 binPath，1 个炫彩 binPath" in line for line in log_lines)
    assert any("INFO|合并地图数据并装配 bin 元数据..." in line for line in log_lines)
    assert any("DEBUG|地图 bin 元数据装配完成，共 1 个地图 binPath" in line for line in log_lines)
