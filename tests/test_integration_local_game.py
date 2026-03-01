import os
import re
from pathlib import Path

import pytest
from league_tools.formats import WAD

from lol_audio_unpack.manager.utils import get_game_version

pytestmark = pytest.mark.local_game

DEFAULT_LOCAL_GAME_PATH = Path("/mnt/d/Games/Tencent/WeGameApps/英雄联盟/")
LOCAL_GAME_SKIP_PREFIX = "[需人工校对][local_game外部资源]"


def _skip_local_game(stage: str, reason: str, checklist: str) -> None:
    pytest.skip(
        f"{LOCAL_GAME_SKIP_PREFIX}[阶段:{stage}] {reason}；"
        f"人工校对建议: {checklist}"
    )


def _resolve_local_game_path() -> Path:
    env_path = os.environ.get("LOL_LOCAL_GAME_PATH", "").strip()
    target = Path(env_path) if env_path else DEFAULT_LOCAL_GAME_PATH

    if not target.exists():
        _skip_local_game(
            stage="环境准备",
            reason=f"本地游戏目录不存在: {target}",
            checklist="确认 LOL_LOCAL_GAME_PATH 或默认目录是否指向有效的英雄联盟客户端",
        )

    return target


@pytest.fixture(scope="session")
def local_game_path() -> Path:
    return _resolve_local_game_path()


def test_local_game_required_files_exist(local_game_path):
    required_files = [
        ("版本元数据", local_game_path / "Game" / "content-metadata.json"),
    ]

    for name, path in required_files:
        assert path.is_file(), f"{name}不存在: {path}"

    required_globs = [
        ("默认资源WAD分卷", "LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad"),
        ("中文资源WAD分卷", "LeagueClient/Plugins/rcp-be-lol-game-data/zh_CN-assets*.wad"),
        ("英雄WAD", "Game/DATA/FINAL/Champions/*.wad.client"),
        ("地图WAD", "Game/DATA/FINAL/Maps/Shipping/*.wad.client"),
    ]

    for name, pattern in required_globs:
        assert any(local_game_path.glob(pattern)), f"{name}不存在: {pattern}"


def test_local_game_version_is_parseable(local_game_path):
    version = get_game_version(local_game_path)
    assert re.match(r"^\d+\.\d+$", version), f"版本号格式异常: {version}"


def test_old_summary_hash_paths_not_found_in_rcp_wads(local_game_path):
    wad_dir = local_game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data"
    wad_files = sorted(wad_dir.glob("*.wad"))

    assert wad_files, f"未找到任何WAD文件: {wad_dir}"

    old_paths = [
        "plugins/rcp-be-lol-game-data/global/default/v1/champion-summary.json",
        "plugins/rcp-be-lol-game-data/global/zh_cn/v1/champion-summary.json",
    ]
    old_hashes = {WAD.get_hash(path) for path in old_paths}

    hits = []
    for wad_file in wad_files:
        wad = WAD(wad_file)
        hashes_in_wad = {entry.path_hash for entry in wad.files}
        if old_hashes & hashes_in_wad:
            hits.append(wad_file.name)

    assert not hits, f"旧路径哈希不应命中当前客户端WAD，命中列表: {hits}"
