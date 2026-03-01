import os
from pathlib import Path

import pytest

from lol_audio_unpack.manager import BinUpdater, DataReader, DataUpdater
from lol_audio_unpack.manager.utils import read_data
from lol_audio_unpack.unpack import unpack_champions
from lol_audio_unpack.utils.config import config


pytestmark = [pytest.mark.local_game, pytest.mark.integration]

DEFAULT_LOCAL_GAME_PATH = Path("/mnt/d/Games/Tencent/WeGameApps/英雄联盟/")


def _resolve_local_game_path() -> Path:
    env_path = os.environ.get("LOL_LOCAL_GAME_PATH", "").strip()
    target = Path(env_path) if env_path else DEFAULT_LOCAL_GAME_PATH
    if not target.exists():
        pytest.skip(f"本地游戏目录不存在，跳过 local_game 流程测试: {target}")
    return target


def _pick_existing_champion_id(data: dict, game_path: Path) -> str | None:
    champions = data.get("champions", {})
    for cid, champion in champions.items():
        root = champion.get("wad", {}).get("root")
        if not root:
            continue
        if not (game_path / root).exists():
            continue
        if champion.get("skins"):
            return cid
    return None


def _prepare_manifest_data_or_skip() -> dict:
    data_file_base = DataUpdater(languages=["zh_CN"], force_update=False).check_and_update()
    if not data_file_base:
        pytest.skip("当前客户端未命中旧版数据路径，DataUpdater 未生成 data 文件")

    merged = read_data(data_file_base)
    if not merged:
        pytest.skip("DataUpdater 未产出可读取的合并数据，跳过完整链路测试")

    champions = merged.get("champions", {})
    if not champions:
        pytest.skip("当前客户端未提取到 champion-summary/champions 数据，完整链路暂不可执行")

    return merged


@pytest.fixture(scope="session")
def local_game_path() -> Path:
    return _resolve_local_game_path()


@pytest.fixture(scope="session")
def pipeline_output_root(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("local_pipeline_output")


@pytest.fixture
def configured_local_runtime(local_game_path: Path, pipeline_output_root: Path, monkeypatch) -> Path:
    monkeypatch.setenv("LOL_GAME_PATH", str(local_game_path))
    monkeypatch.setenv("LOL_OUTPUT_PATH", str(pipeline_output_root))
    monkeypatch.setenv("LOL_GAME_REGION", "zh_CN")
    # 空值表示不排除任何类型，增加解包命中概率
    monkeypatch.setenv("LOL_EXCLUDE_TYPE", "")
    # 减少测试过程中的日志噪音
    monkeypatch.setenv("LOL_DEBUG", "20")

    # 显式指定 env_path，避免加载项目根目录下的 .lol.env 覆盖测试环境变量
    config.initialize(env_path=pipeline_output_root, force_reload=True, dev_mode=False)
    return pipeline_output_root


def test_pipeline_data_updater_builds_manifest(configured_local_runtime, local_game_path):
    merged = _prepare_manifest_data_or_skip()

    assert "metadata" in merged
    assert merged["metadata"].get("gameVersion")

    cid = _pick_existing_champion_id(merged, local_game_path)
    assert cid is not None, "未找到可用的英雄WAD映射，无法进行后续链路测试"


def test_pipeline_bin_updater_generates_champion_banks(configured_local_runtime, local_game_path):
    merged = _prepare_manifest_data_or_skip()
    cid = _pick_existing_champion_id(merged, local_game_path)
    if cid is None:
        pytest.skip("当前客户端未提取到可用英雄数据，跳过 BinUpdater 链路测试")

    BinUpdater(force_update=False, process_events=False).update(target="skin", champion_ids=[cid])

    reader = DataReader()
    banks = reader.get_champion_banks(int(cid))
    assert banks, f"英雄 {cid} 的 banks 数据未生成"
    assert banks.get("skins"), f"英雄 {cid} 的 skins banks 为空"


def test_pipeline_unpack_generates_wem(configured_local_runtime, local_game_path):
    merged = _prepare_manifest_data_or_skip()
    cid = _pick_existing_champion_id(merged, local_game_path)
    if cid is None:
        pytest.skip("当前客户端未提取到可用英雄数据，跳过完整解包链路测试")

    BinUpdater(force_update=False, process_events=False).update(target="skin", champion_ids=[cid])

    reader = DataReader()
    banks = reader.get_champion_banks(int(cid))
    if not banks or not banks.get("skins"):
        pytest.skip("未生成可用 banks 数据，跳过 wem 解包验证")

    unpack_champions(reader, [int(cid)], max_workers=1)

    output_root = config.AUDIO_PATH / reader.version
    wem_files = list(output_root.rglob("*.wem"))
    assert wem_files, f"未在输出目录发现 wem 文件: {output_root}"
