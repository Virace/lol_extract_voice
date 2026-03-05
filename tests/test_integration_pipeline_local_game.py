import os
import shutil
import sys
from pathlib import Path

import pytest
from loguru import logger

from lol_audio_unpack.app_context import AppContext, create_app_context
from lol_audio_unpack.manager import BinUpdater, DataReader, DataUpdater
from lol_audio_unpack.manager.utils import read_data
from lol_audio_unpack.unpack import unpack_champions, unpack_maps
from lol_audio_unpack.utils.common import Singleton

pytestmark = [pytest.mark.local_game, pytest.mark.integration]

DEFAULT_LOCAL_GAME_PATHS = [
    Path("/mnt/d/Games/Tencent/WeGameApps/英雄联盟"),
    Path("D:/Games/Tencent/WeGameApps/英雄联盟"),
]
LOCAL_GAME_PREFIX = "[local_game外部资源]"


def _configure_pipeline_logging() -> None:
    level = os.environ.get("LOL_LOCAL_GAME_TEST_LOG_LEVEL", "DEBUG").upper()
    warning_level_no = logger.level("WARNING").no
    error_level_no = logger.level("ERROR").no
    logger.enable("lol_audio_unpack")
    logger.remove()

    def _pipeline_log_filter(record: dict) -> bool:
        name = record["name"]
        if name.startswith("lol_audio_unpack"):
            return True
        if name.startswith("league_tools"):
            # 保留外部库的关键告警，压制大量 DEBUG 日志
            return record["level"].no >= warning_level_no
        if name == __name__:
            # 仅保留本测试文件中的错误级别日志
            return record["level"].no >= error_level_no
        return False

    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> | "
            "<level>{message}</level>"
        ),
        backtrace=False,
        diagnose=False,
        colorize=True,
        enqueue=False,
        filter=_pipeline_log_filter,
    )


def _skip_local_game(stage: str, reason: str, checklist: str) -> None:
    pytest.skip(
        f"{LOCAL_GAME_PREFIX}[阶段:{stage}][跳过] {reason}；"
        f"人工校对建议: {checklist}"
    )


def _fail_local_game(stage: str, reason: str, checklist: str) -> None:
    pytest.fail(
        f"{LOCAL_GAME_PREFIX}[阶段:{stage}][失败] {reason}；"
        f"人工校对建议: {checklist}",
        pytrace=False,
    )


def _resolve_local_game_path() -> Path:
    env_path = os.environ.get("LOL_LOCAL_GAME_PATH", "").strip()
    if env_path:
        target = Path(env_path)
    else:
        target = next((path for path in DEFAULT_LOCAL_GAME_PATHS if path.exists()), DEFAULT_LOCAL_GAME_PATHS[0])
    if not target.exists():
        _skip_local_game(
            stage="环境准备",
            reason=f"本地游戏目录不存在: {target}",
            checklist="确认 LOL_LOCAL_GAME_PATH 或默认目录是否指向有效的英雄联盟客户端",
        )
    return target


def _find_existing_data_file(file_base: Path) -> Path | None:
    for suffix in (".msgpack", ".yml", ".json"):
        candidate = file_base.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def _pick_existing_champion_id(merged: dict, game_path: Path) -> str | None:
    champions = merged.get("champions", {})
    for champion_id, champion in champions.items():
        wad_root = champion.get("wad", {}).get("root")
        if not wad_root or not (game_path / wad_root).exists():
            continue
        if champion.get("skins"):
            return champion_id
    return None


def _pick_existing_map_id(merged: dict, game_path: Path) -> str | None:
    maps = merged.get("maps", {})
    candidate_ids = sorted(maps.keys(), key=int)
    prioritized_ids = [mid for mid in candidate_ids if mid != "0"] + [mid for mid in candidate_ids if mid == "0"]

    for map_id in prioritized_ids:
        map_data = maps.get(map_id, {})
        wad_root = map_data.get("wad", {}).get("root")
        bin_path = map_data.get("binPath")
        if not wad_root or not bin_path:
            continue
        if (game_path / wad_root).exists():
            return map_id
    return None


def _reset_data_reader_singleton() -> None:
    Singleton._instances.pop(DataReader, None)


def _run_data_updater_or_fail(local_game_path: Path, ctx: AppContext) -> dict:
    data_file_base = DataUpdater(ctx=ctx, languages=["zh_CN"], force_update=False).check_and_update()
    if not data_file_base:
        _fail_local_game(
            stage="2-DataUpdater",
            reason="DataUpdater 未返回 data 文件基础路径",
            checklist="检查客户端 rcp-be-lol-game-data 资源路径是否变更，确认 champion-summary/maps 路径提取策略",
        )

    data_file = _find_existing_data_file(data_file_base)
    if data_file is None:
        _fail_local_game(
            stage="2-DataUpdater",
            reason=f"DataUpdater 完成后仍未找到 data 文件: {data_file_base}",
            checklist="检查 manifest 输出目录写入权限、格式后缀（msgpack/yml/json）与日志错误信息",
        )

    merged = read_data(data_file_base, dev_mode=ctx.config.dev_mode)
    if not merged:
        _fail_local_game(
            stage="2-DataUpdater",
            reason="DataUpdater 产出的 data 文件不可读取或内容为空",
            checklist="检查 data 文件是否损坏，并人工核对客户端版本号与提取日志",
        )

    metadata = merged.get("metadata", {})
    game_version = metadata.get("gameVersion")
    if not game_version:
        _fail_local_game(
            stage="2-DataUpdater",
            reason="合并数据缺少 metadata.gameVersion",
            checklist="人工核对 content-metadata.json 与 data 文件中的 metadata 字段",
        )

    champion_id = _pick_existing_champion_id(merged, local_game_path)
    if champion_id is None:
        _fail_local_game(
            stage="2-DataUpdater",
            reason="未找到可用英雄映射（缺少可访问WAD或皮肤数据）",
            checklist="人工核对 champions[*].wad.root 对应文件是否存在，及 skins 是否非空",
        )

    map_id = _pick_existing_map_id(merged, local_game_path)
    if map_id is None:
        _fail_local_game(
            stage="2-DataUpdater",
            reason="未找到可用地图映射（缺少可访问WAD或binPath）",
            checklist="人工核对 maps[*].wad.root 与 maps[*].binPath 是否存在且可读",
        )

    return {
        "data_file_base": data_file_base,
        "data_file": data_file,
        "merged": merged,
        "game_version": game_version,
        "champion_id": champion_id,
        "map_id": map_id,
    }


def _run_bin_updater_or_fail(
    champion_id: str,
    map_id: str,
    ctx: AppContext,
    process_events: bool = False,
    force_update: bool = False,
) -> DataReader:
    BinUpdater(force_update=force_update, process_events=process_events, ctx=ctx).update(
        champion_ids=[champion_id], map_ids=[map_id]
    )

    _reset_data_reader_singleton()
    reader = DataReader(ctx=ctx)

    champion_banks_file = _find_existing_data_file(ctx.paths.manifest_path / reader.version / "banks" / "champions" / champion_id)
    if champion_banks_file is None:
        _fail_local_game(
            stage="3-BinUpdater",
            reason=f"未找到英雄 banks 文件: {champion_id}",
            checklist="人工核对英雄WAD是否可读、binPath是否有效，以及 BinUpdater 日志中的解析错误",
        )

    champion_banks = reader.get_champion_banks(int(champion_id))
    if not champion_banks or not champion_banks.get("skins"):
        _fail_local_game(
            stage="3-BinUpdater",
            reason=f"英雄 {champion_id} 的 banks 内容为空",
            checklist="人工核对 BIN 是否包含 bank_path，确认 process_events 与筛选参数是否影响产出",
        )

    map_banks_file = _find_existing_data_file(ctx.paths.manifest_path / reader.version / "banks" / "maps" / map_id)
    if map_banks_file is None:
        _fail_local_game(
            stage="3-BinUpdater",
            reason=f"未找到地图 banks 文件: {map_id}",
            checklist="人工核对 map wad/bin 是否可读，以及 BinUpdater 地图处理日志中的解析错误",
        )

    map_banks = reader.get_map_banks(int(map_id))
    if not map_banks or not map_banks.get("banks"):
        _fail_local_game(
            stage="3-BinUpdater",
            reason=f"地图 {map_id} 的 banks 内容为空",
            checklist="人工核对地图 BIN 是否包含 bank_path，确认地图去重后是否仍有独有数据",
        )

    return reader


def _assert_events_or_fail(reader: DataReader, champion_id: str, map_id: str, ctx: AppContext) -> None:
    champion_events_base = ctx.paths.manifest_path / reader.version / "events" / "champions" / champion_id
    champion_events_file = _find_existing_data_file(champion_events_base)
    if champion_events_file is None:
        _fail_local_game(
            stage="3-BinUpdater(events)",
            reason=f"未找到英雄 events 文件: {champion_id}",
            checklist="确认 BinUpdater 运行时 process_events=True，检查英雄 BIN 事件解析日志",
        )
    champion_events = read_data(champion_events_base, dev_mode=ctx.config.dev_mode)
    if not champion_events or not champion_events.get("skins"):
        _fail_local_game(
            stage="3-BinUpdater(events)",
            reason=f"英雄 {champion_id} 的 events 内容为空",
            checklist="人工核对英雄 BIN 中 event 数据是否存在，并检查事件过滤逻辑",
        )

    map_events_base = ctx.paths.manifest_path / reader.version / "events" / "maps" / map_id
    map_events_file = _find_existing_data_file(map_events_base)
    if map_events_file is None:
        _fail_local_game(
            stage="3-BinUpdater(events)",
            reason=f"未找到地图 events 文件: {map_id}",
            checklist="确认地图 BIN 中事件是否存在，检查 map 事件提取与去重流程",
        )
    map_events = read_data(map_events_base, dev_mode=ctx.config.dev_mode)
    if not map_events or not map_events.get("map"):
        _fail_local_game(
            stage="3-BinUpdater(events)",
            reason=f"地图 {map_id} 的 events 内容为空",
            checklist="人工核对地图事件是否被全部去重移除，并检查 map 事件写入逻辑",
        )


def _clear_unpack_outputs(version: str, ctx: AppContext) -> None:
    output_root = ctx.paths.audio_path / version
    report_root = ctx.paths.report_path / version
    if output_root.exists():
        shutil.rmtree(output_root)
    if report_root.exists():
        shutil.rmtree(report_root)


def _unpack_champion_or_fail(reader: DataReader, champion_id: str, ctx: AppContext, max_workers: int = 1) -> set[str]:
    output_root = ctx.paths.audio_path / reader.version
    before_files = {str(path) for path in output_root.rglob("*.wem")}

    unpack_champions(reader, [int(champion_id)], max_workers=max_workers, ctx=ctx)

    after_files = {str(path) for path in output_root.rglob("*.wem")}
    new_files = after_files - before_files
    if not new_files:
        _fail_local_game(
            stage="4-Unpack(champion)",
            reason=f"英雄 {champion_id} 解包后未新增 wem 文件",
            checklist="人工核对 banks 中的 bnk/wpk 路径是否可提取，并检查 unpack 日志中的异常",
        )

    report_file = ctx.paths.report_path / reader.version / "champions" / f"_{champion_id}_metadata.yaml"
    if not report_file.is_file():
        _fail_local_game(
            stage="4-Unpack(champion)",
            reason=f"未生成英雄解包报告: {report_file}",
            checklist="人工核对输出目录权限，并检查报告写入日志",
        )

    return after_files


def _unpack_map_or_fail(
    reader: DataReader,
    map_id: str,
    before_files: set[str],
    ctx: AppContext,
    max_workers: int = 1,
) -> None:
    unpack_maps(reader, [int(map_id)], max_workers=max_workers, ctx=ctx)

    output_root = ctx.paths.audio_path / reader.version
    after_files = {str(path) for path in output_root.rglob("*.wem")}
    new_files = after_files - before_files
    if not new_files:
        _fail_local_game(
            stage="5-Unpack(map)",
            reason=f"地图 {map_id} 解包后未新增 wem 文件",
            checklist="人工核对地图 banks 指向的 bnk/wpk 是否可提取，检查 unpack 地图日志中的异常",
        )

    report_file = ctx.paths.report_path / reader.version / "maps" / f"_{map_id}_metadata.yaml"
    if not report_file.is_file():
        _fail_local_game(
            stage="5-Unpack(map)",
            reason=f"未生成地图解包报告: {report_file}",
            checklist="人工核对报告目录权限，并检查地图报告写入日志",
        )


@pytest.fixture(scope="session")
def local_game_path() -> Path:
    return _resolve_local_game_path()


@pytest.fixture(scope="session")
def pipeline_output_root(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("local_pipeline_output")


@pytest.fixture
def app_context(local_game_path: Path, pipeline_output_root: Path, monkeypatch) -> AppContext:
    monkeypatch.setenv("LOL_GAME_PATH", str(local_game_path))
    monkeypatch.setenv("LOL_OUTPUT_PATH", str(pipeline_output_root))
    monkeypatch.setenv("LOL_GAME_REGION", "zh_CN")
    monkeypatch.setenv("LOL_EXCLUDE_TYPE", "")
    monkeypatch.setenv("LOL_LOCAL_GAME_TEST_LOG_LEVEL", os.environ.get("LOL_LOCAL_GAME_TEST_LOG_LEVEL", "DEBUG"))
    _configure_pipeline_logging()

    return create_app_context(
        env_path=pipeline_output_root,
        force_reload=True,
        dev_mode=False,
    )


def test_pipeline_stage_1_runtime_config_ready(app_context: AppContext, local_game_path: Path) -> None:
    assert Path(app_context.config.game_path) == local_game_path
    assert app_context.paths.manifest_path == app_context.config.output_path / "manifest"
    assert app_context.paths.audio_path == app_context.config.output_path / "audios"
    assert not app_context.paths.manifest_path.exists()
    assert not app_context.paths.audio_path.exists()


def test_pipeline_linear_workflow_with_stage_assertions(app_context: AppContext, local_game_path: Path) -> None:
    # 阶段2：DataUpdater 产出 data
    context = _run_data_updater_or_fail(local_game_path, app_context)
    assert context["data_file"].is_file(), f"data 文件不存在: {context['data_file']}"

    # 阶段3：BinUpdater 产出 banks -> DataReader 加载
    reader = _run_bin_updater_or_fail(context["champion_id"], context["map_id"], app_context)
    assert reader.version == context["game_version"], (
        f"DataReader 版本与 data 版本不一致: reader={reader.version}, data={context['game_version']}"
    )

    _clear_unpack_outputs(reader.version, app_context)

    # 阶段4：先解包英雄
    after_champion_files = _unpack_champion_or_fail(reader, context["champion_id"], app_context)

    # 阶段5：再解包地图（依赖同一 reader 与前置产物）
    _unpack_map_or_fail(reader, context["map_id"], after_champion_files, app_context)


def test_pipeline_with_events_enabled_outputs_events(app_context: AppContext, local_game_path: Path) -> None:
    context = _run_data_updater_or_fail(local_game_path, app_context)
    reader = _run_bin_updater_or_fail(
        context["champion_id"],
        context["map_id"],
        app_context,
        process_events=True,
        force_update=True,
    )
    _assert_events_or_fail(reader, context["champion_id"], context["map_id"], app_context)


def test_pipeline_linear_workflow_multithread_unpack(app_context: AppContext, local_game_path: Path) -> None:
    context = _run_data_updater_or_fail(local_game_path, app_context)
    reader = _run_bin_updater_or_fail(
        context["champion_id"],
        context["map_id"],
        app_context,
        process_events=False,
        force_update=True,
    )
    assert reader.version == context["game_version"], (
        f"DataReader 版本与 data 版本不一致: reader={reader.version}, data={context['game_version']}"
    )

    _clear_unpack_outputs(reader.version, app_context)

    after_champion_files = _unpack_champion_or_fail(reader, context["champion_id"], app_context, max_workers=2)
    _unpack_map_or_fail(reader, context["map_id"], after_champion_files, app_context, max_workers=2)
