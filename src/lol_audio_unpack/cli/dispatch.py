"""CLI 执行编排逻辑。

该模块负责 update / extract / wav / mapping 的执行分发与阶段日志输出。
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from ..app.facade import LolAudioUnpackApp
from ..app.targets import resolve_scope
from ..config import SettingKey
from .runtime import build_options, parse_int_ids, resolve_champion_ids


def _has_update(args: argparse.Namespace) -> bool:
    """返回是否包含 update 动作。"""
    return "update" in getattr(args, "actions", [])


def _has_extract(args: argparse.Namespace) -> bool:
    """返回是否包含 extract 动作。"""
    return "extract" in getattr(args, "actions", [])


def _has_mapping(args: argparse.Namespace) -> bool:
    """返回是否包含 mapping 动作。"""
    return "mapping" in getattr(args, "actions", [])


def _has_wav(args: argparse.Namespace) -> bool:
    """返回是否请求执行 WAV 转码 stage。"""
    return "wav" in getattr(args, "actions", [])


def _resolve_targets(
    args: argparse.Namespace,
    *,
    app: LolAudioUnpackApp,
) -> tuple[tuple[int, ...] | None, tuple[int, ...] | None]:
    """解析共享的 CLI 实体选择。"""
    champion_ids = resolve_champion_ids(args.champions, app=app, force_update=args.force)
    map_ids = parse_int_ids(args.maps)
    return champion_ids, map_ids


def _target_scope(
    *,
    champion_ids: tuple[int, ...] | None,
    map_ids: tuple[int, ...] | None,
) -> tuple[str, bool, bool]:
    """根据共享目标范围推导门面目标范围。"""
    return resolve_scope(
        champion_ids=champion_ids,
        map_ids=map_ids,
    )


def _target_detail(
    *,
    champion_ids: tuple[int, ...] | None,
    map_ids: tuple[int, ...] | None,
    all_detail: str,
    champion_detail: str,
    map_detail: str,
) -> str:
    """根据共享目标范围构建日志详情。"""
    if champion_ids is None and map_ids is None:
        return all_detail
    if champion_ids is not None and map_ids is not None:
        return f"指定英雄和地图: champions={list(champion_ids)}, maps={list(map_ids)}"
    if champion_ids is not None:
        return f"{champion_detail}: {list(champion_ids)}"
    return f"{map_detail}: {list(map_ids) if map_ids is not None else []}"


def _log_stage_start(stage: str, detail: str | None = None) -> None:
    """输出 CLI 阶段开始日志，并保持调用方归属。"""
    message = f"{stage}阶段开始"
    if detail:
        message = f"{message}: {detail}"
    logger.opt(depth=1).info(message)


def _log_stage_done(stage: str, detail: str | None = None) -> None:
    """输出 CLI 阶段完成日志，并保持调用方归属。"""
    message = f"{stage}阶段完成"
    if detail:
        message = f"{message}: {detail}"
    logger.opt(depth=1).success(message)


def _log_top_error(error: Exception, *, dev_mode: bool) -> None:
    """统一记录 CLI 顶层未处理异常。"""
    logger.opt(depth=1, exception=dev_mode).error(f"执行过程中发生错误: {error}")


def run_remote_workflow(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行 remote 模式下的单位驱动工作流。"""
    champion_ids, map_ids = _resolve_targets(args, app=app)
    update_target, extract_include_champions, extract_include_maps = _target_scope(
        champion_ids=champion_ids,
        map_ids=map_ids,
    )

    update_options = None
    if _has_update(args):
        update_options = build_options(args, champion_ids=champion_ids, map_ids=map_ids)

    extract_options = None
    if _has_extract(args):
        extract_options = build_options(args, champion_ids=champion_ids, map_ids=map_ids)

    mapping_options = None
    if _has_mapping(args):
        mapping_options = build_options(args, champion_ids=champion_ids, map_ids=map_ids)

    app.run_workflow(
        update_options=update_options,
        update_target=update_target,
        extract_options=extract_options,
        mapping_options=mapping_options,
        extract_include_champions=extract_include_champions,
        extract_include_maps=extract_include_maps,
        mapping_include_champions=extract_include_champions,
        mapping_include_maps=extract_include_maps,
    )


def run_update(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行数据更新操作。"""
    if not _has_update(args):
        return

    champion_ids, map_ids = _resolve_targets(args, app=app)
    target, _, _ = _target_scope(champion_ids=champion_ids, map_ids=map_ids)

    if args.skip_events:
        logger.info("已启用快速模式：跳过事件数据处理")
    if args.force:
        logger.warning("已启用强制更新模式，将忽略现有文件的版本检查。")

    detail = _target_detail(
        champion_ids=champion_ids,
        map_ids=map_ids,
        all_detail="所有数据（英雄和地图）",
        champion_detail="指定英雄数据",
        map_detail="指定地图数据",
    )
    _log_stage_start("数据更新", detail)
    app.update(build_options(args, champion_ids=champion_ids, map_ids=map_ids), target=target)
    _log_stage_done("数据更新", detail)


def run_extract(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行音频解包操作。"""
    if not _has_extract(args):
        return

    try:
        champion_ids, map_ids = _resolve_targets(args, app=app)
    except ValueError as exc:
        logger.error(f"解包目标失败: {exc}")
        return

    _, include_champions, include_maps = _target_scope(champion_ids=champion_ids, map_ids=map_ids)
    detail = _target_detail(
        champion_ids=champion_ids,
        map_ids=map_ids,
        all_detail="所有音频（英雄和地图）",
        champion_detail="指定英雄音频",
        map_detail="指定地图音频",
    )
    _log_stage_start("音频解包", detail)
    app.extract(
        build_options(args, champion_ids=champion_ids, map_ids=map_ids),
        include_champions=include_champions,
        include_maps=include_maps,
    )
    _log_stage_done("音频解包", detail)


def run_wav(args: argparse.Namespace, app: LolAudioUnpackApp) -> None:
    """执行独立的 WAV 转码 stage。"""
    if not _has_wav(args):
        return

    detail = "消费当前 audios 输出树"
    _log_stage_start("WAV 转码", detail)
    app.transcode_wav(build_options(args))
    _log_stage_done("WAV 转码", detail)


def _log_mapping_error(error: ValueError) -> None:
    """记录 mapping 运行时错误，并在 wwiser 配置错误时补充指引。"""
    message = str(error)
    logger.error(f"构建事件映射失败: {message}")

    if "Wwiser 工具路径" not in message and SettingKey.WWISER_PATH not in message:
        return

    logger.error(
        "如果需要使用 WwiserHIRC 回退路径，请通过 --wwiser-path 显式传入，或在 -c 指定的 INI 中配置 wwiser_path。"
    )
    logger.error(
        "WWISER_PATH 应指向 wwiser.pyz 或 wwiser.exe 文件；如果不需要 wwiser，请移除该配置并直接使用默认 NativeHIRC。"
    )


def run_mapping(
    args: argparse.Namespace,
    app: LolAudioUnpackApp,
) -> None:
    """执行事件映射操作。"""
    if not _has_mapping(args):
        return

    if build_options(args).integrate_data:
        logger.info("启用整合数据功能，将生成包含完整实体信息的整合文件")

    try:
        champion_ids, map_ids = _resolve_targets(args, app=app)
    except ValueError as exc:
        logger.error(f"构建映射目标失败: {exc}")
        return

    _, include_champions, include_maps = _target_scope(champion_ids=champion_ids, map_ids=map_ids)
    detail = _target_detail(
        champion_ids=champion_ids,
        map_ids=map_ids,
        all_detail="所有实体（英雄和地图）",
        champion_detail="指定英雄事件映射",
        map_detail="指定地图事件映射",
    )
    _log_stage_start("事件映射", detail)
    mapping_options = build_options(args, champion_ids=champion_ids, map_ids=map_ids)
    try:
        app.mapping(
            mapping_options,
            include_champions=include_champions,
            include_maps=include_maps,
        )
    except ValueError as exc:
        _log_mapping_error(exc)
        sys.exit(1)
    _log_stage_done("事件映射", detail)


__all__ = [
    "_has_extract",
    "_has_mapping",
    "_has_update",
    "_has_wav",
    "_log_stage_done",
    "_log_stage_start",
    "_log_top_error",
    "run_extract",
    "run_mapping",
    "run_remote_workflow",
    "run_update",
    "run_wav",
]
