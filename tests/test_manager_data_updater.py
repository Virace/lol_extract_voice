import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.manager import data_updater as m_data_updater

pytestmark = pytest.mark.integration


def _build_updater(game_path: Path, version: str = "16.3"):
    updater = m_data_updater.DataUpdater.__new__(m_data_updater.DataUpdater)
    updater.ctx = SimpleNamespace(
        config=SimpleNamespace(
            game_path=game_path,
            game_region="zh_CN",
            dev_mode=False,
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
