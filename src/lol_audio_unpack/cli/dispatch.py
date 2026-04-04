"""CLI 执行编排逻辑。

该模块负责 update / extract / mapping 的执行分发、阶段日志输出，
以及 CLI 主线中的远端工作流与 WAV 后台进度轮询。
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

from loguru import logger

from ..app.facade import LolAudioUnpackApp
from ..app.targets import resolve_scope
from ..config import SettingKey
from ..runtime.wav import JobHandle
from .runtime import build_options, parse_int_ids, resolve_champion_ids


@dataclass(slots=True, frozen=True)
class WavJobProgress:
    """CLI 侧使用的 WAV 后台进度快照。"""

    status: str
    phase: str
    queued: int
    running: int
    completed: int
    failed: int
    skipped: int
    detail: str


def _has_update(args: argparse.Namespace) -> bool:
    """返回是否包含 update 动作。"""
    return "update" in getattr(args, "actions", [])


def _has_extract(args: argparse.Namespace) -> bool:
    """返回是否包含 extract 动作。"""
    return "extract" in getattr(args, "actions", [])


def _has_mapping(args: argparse.Namespace) -> bool:
    """返回是否包含 mapping 动作。"""
    return "mapping" in getattr(args, "actions", [])


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


def _extract_detail(base_detail: str, *, wav_enabled: bool) -> str:
    """拼接音频解包阶段摘要。"""
    if not wav_enabled:
        return base_detail
    return f"{base_detail} + WAV 转码"


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


def _wav_progress_from_snapshot(snapshot: dict[str, object]) -> WavJobProgress:
    """将后端原始快照转换为 CLI 侧进度对象。"""
    return WavJobProgress(
        status=str(snapshot.get("status", "running")),
        phase=str(snapshot.get("phase", "unknown")),
        queued=int(snapshot.get("submitted_wav_job_count", 0)),
        running=int(snapshot.get("running_wav_job_count", 0)),
        completed=int(snapshot.get("completed_wav_job_count", 0)),
        failed=int(snapshot.get("failed_wav_job_count", 0)),
        skipped=int(snapshot.get("skipped_wav_job_count", 0)),
        detail=str(snapshot.get("detail", "")).strip(),
    )


def _wav_progress_key(progress: WavJobProgress) -> tuple[object, ...]:
    """返回用于去重比较的进度签名。"""
    return (
        progress.status,
        progress.phase,
        progress.queued,
        progress.running,
        progress.completed,
        progress.failed,
        progress.skipped,
        progress.detail,
    )


def _format_wav_progress(progress: WavJobProgress) -> str:
    """将进度对象格式化为 CLI 文案。"""
    if progress.status != "running":
        return progress.detail or progress.status
    return (
        f"phase={progress.phase} · "
        f"已提交 {progress.queued} · "
        f"运行中 {progress.running} · "
        f"完成 {progress.completed} · "
        f"失败 {progress.failed} · "
        f"跳过 {progress.skipped}"
    )


def _report_wav_progress(
    handle: JobHandle | None,
    *,
    last_signature: tuple[object, ...] | None,
    force: bool = False,
) -> tuple[object, ...] | None:
    """轮询并按需输出后台 WAV 进度。"""
    if handle is None:
        return last_signature
    snapshot = handle.read_progress_snapshot()
    if snapshot is None:
        return last_signature

    progress = _wav_progress_from_snapshot(snapshot)
    signature = _wav_progress_key(progress)
    if not force and signature == last_signature:
        return last_signature

    message = _format_wav_progress(progress)
    if progress.status == "completed":
        logger.success(f"WAV 后台进度[{handle.job_label}]：{message}")
    elif progress.status == "failed":
        logger.warning(f"WAV 后台进度[{handle.job_label}]：{message}")
    else:
        logger.info(f"WAV 后台进度[{handle.job_label}]：{message}")
    return signature


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


def run_extract(args: argparse.Namespace, app: LolAudioUnpackApp) -> JobHandle | None:
    """执行音频解包操作。"""
    if not _has_extract(args):
        return None

    try:
        champion_ids, map_ids = _resolve_targets(args, app=app)
    except ValueError as exc:
        logger.error(f"解包目标失败: {exc}")
        return None

    _, include_champions, include_maps = _target_scope(champion_ids=champion_ids, map_ids=map_ids)
    detail = _extract_detail(
        _target_detail(
            champion_ids=champion_ids,
            map_ids=map_ids,
            all_detail="所有音频（英雄和地图）",
            champion_detail="指定英雄音频",
            map_detail="指定地图音频",
        ),
        wav_enabled=args.wav,
    )
    _log_stage_start("音频解包", detail)
    wav_handle = app.extract(
        build_options(args, champion_ids=champion_ids, map_ids=map_ids),
        include_champions=include_champions,
        include_maps=include_maps,
        detach_wav=args.wav,
        wav_job_label=f"cli-{int(time.time() * 1000)}",
    )
    _log_stage_done("音频解包", detail)
    return wav_handle


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
    *,
    wav_handle: JobHandle | None = None,
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
    mapping_kwargs = {
        "include_champions": include_champions,
        "include_maps": include_maps,
    }
    last_progress: tuple[object, ...] | None = None

    def emit_mapping_progress(_entity_type: str, _current: int, _total: int, _message: str) -> None:
        nonlocal last_progress
        last_progress = _report_wav_progress(
            wav_handle,
            last_signature=last_progress,
        )

    try:
        if wav_handle is None:
            app.mapping(mapping_options, **mapping_kwargs)
        else:
            app.mapping(mapping_options, progress_callback=emit_mapping_progress, **mapping_kwargs)
    except ValueError as exc:
        _log_mapping_error(exc)
        sys.exit(1)

    _report_wav_progress(
        wav_handle,
        last_signature=last_progress,
        force=True,
    )
    _log_stage_done("事件映射", detail)


__all__ = [
    "_has_extract",
    "_has_mapping",
    "_has_update",
    "_log_stage_done",
    "_log_stage_start",
    "_log_top_error",
    "_report_wav_progress",
    "run_extract",
    "run_mapping",
    "run_remote_workflow",
    "run_update",
]
