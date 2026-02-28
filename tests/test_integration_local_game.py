import os
import re
from pathlib import Path

import pytest
from league_tools.formats import WAD

from lol_audio_unpack.data.manifest import GameData, GameDataReader, GameDataUpdater
from lol_audio_unpack.hashes import HashManager
from lol_audio_unpack.utils.common import Singleton

pytestmark = pytest.mark.local_game

_REQUIRED_FILES = (
    ("版本元数据", "Game/content-metadata.json"),
    ("LCU 中文资源包", "LeagueClient/Plugins/rcp-be-lol-game-data/zh_CN-assets.wad"),
)

_REQUIRED_GLOBS = (
    ("英雄 WAD", "Game/DATA/FINAL/Champions/*.wad.client"),
    ("地图 WAD", "Game/DATA/FINAL/Maps/Shipping/*.wad.client"),
    ("LCU 默认资源包", "LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad"),
)


def _resolve_local_game_path() -> Path:
    game_path = os.environ.get("LOL_LOCAL_GAME_PATH") or os.environ.get("LOL_GAME_PATH")
    if not game_path:
        pytest.skip("未设置 LOL_LOCAL_GAME_PATH 或 LOL_GAME_PATH，跳过本地完整功能测试")

    path = Path(game_path).expanduser()
    if not path.is_dir():
        pytest.skip(f"本地游戏目录不存在: {path}")

    return path


@pytest.fixture(scope="session")
def local_game_path() -> Path:
    return _resolve_local_game_path()


@pytest.fixture(scope="session")
def integration_workspace(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("local_game_integration")


@pytest.fixture(scope="session")
def extracted_game_data_if_available(local_game_path, integration_workspace) -> GameData:
    manifest_root = integration_workspace / "manifest_extract"
    game_data = GameData(out_dir=manifest_root, mode="local", game_path=local_game_path, region="zh_CN")
    game_data.get_data()

    if not game_data.get_summary():
        pytest.skip(
            "当前客户端未命中旧版 rcp-be-lol-game-data 路径（champion-summary.json 等），"
            "跳过依赖旧路径的完整链路测试"
        )

    return game_data


@pytest.fixture(autouse=True)
def reset_game_data_reader_singleton():
    Singleton._instances.pop(GameDataReader, None)
    yield
    Singleton._instances.pop(GameDataReader, None)


def test_local_game_required_files_exist(local_game_path):
    for desc, rel_path in _REQUIRED_FILES:
        assert (local_game_path / rel_path).is_file(), f"{desc}不存在: {rel_path}"

    for desc, glob_pattern in _REQUIRED_GLOBS:
        assert any(local_game_path.glob(glob_pattern)), f"{desc}不存在: {glob_pattern}"


def test_content_metadata_version_is_parseable(local_game_path):
    version = GameDataUpdater._get_game_version(local_game_path)
    assert re.fullmatch(r"\d+\.\d+", version)


def test_core_wad_archives_are_readable(local_game_path):
    champion_wad = next(local_game_path.glob("Game/DATA/FINAL/Champions/*.wad.client"), None)
    map_wad = next(local_game_path.glob("Game/DATA/FINAL/Maps/Shipping/*.wad.client"), None)
    default_assets_wad = next(
        local_game_path.glob("LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad"),
        None,
    )

    assert champion_wad is not None
    assert map_wad is not None
    assert default_assets_wad is not None

    assert len(WAD(champion_wad).files) > 0
    assert len(WAD(map_wad).files) > 0
    assert len(WAD(default_assets_wad).files) > 0


def test_game_data_can_extract_and_read_summary(extracted_game_data_if_available):
    summary = extracted_game_data_if_available.get_summary()
    assert summary

    sample = next((item for item in summary if item["id"] != -1), None)
    assert sample is not None

    detail = extracted_game_data_if_available.get_champion_detail_by_id(sample["id"])
    assert detail.get("id") == sample["id"]
    assert isinstance(detail.get("skins"), list)

    maps = extracted_game_data_if_available.get_maps()
    assert maps


def test_game_data_updater_builds_merged_manifest(local_game_path, integration_workspace, extracted_game_data_if_available):
    merged_root = integration_workspace / "manifest_merged"
    merged_file = GameDataUpdater.check_and_update(
        game_path=local_game_path,
        out_dir=merged_root,
        languages=["zh_CN"],
    )

    assert merged_file.exists()

    reader = GameDataReader(merged_file)
    champions = reader.get_champions_list()
    assert champions

    languages = set(reader.get_supported_languages())
    assert "default" in languages
    assert "zh_CN" in languages

    assert {"id", "alias"}.issubset(champions[0].keys())


def test_hash_manager_can_generate_bin_hashes(local_game_path, integration_workspace, extracted_game_data_if_available):
    manifest_root = integration_workspace / "manifest_extract"
    hash_root = integration_workspace / "hashes"
    log_root = integration_workspace / "logs"

    manager = HashManager(
        game_path=local_game_path,
        manifest_path=manifest_root,
        hash_path=hash_root,
        region="zh_CN",
        log_path=log_root,
    )

    bin_hashes = manager.get_bin_hashes(update=True)
    assert manager.bin_hash_file.exists()
    assert bin_hashes.get("characters")
    assert "map11" in bin_hashes.get("maps", {})
