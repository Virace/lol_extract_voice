"""解包阶段的 WAV bridge。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from lol_audio_unpack.utils.run_summary import record_runtime_note
from lol_audio_unpack.wav_background_job import (
    WavBackgroundProcessHandle,
    WavManifestRecorder,
    build_wav_background_job_spec_from_paths,
    launch_wav_background_process,
)
from lol_audio_unpack.wav_sidecar import WavSidecarProgressSnapshot

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext, WavOutputOptions

INTERNAL_ERROR_NOTE = "已启用 WAV 转码，但 sidecar 内部异常，已自动降级为仅保留 WEM。"
_SUBMITTED_LOG_INTERVAL = 25
_PROCESSED_LOG_INTERVAL = 10


def record_internal_error(
    ctx: AppContext,
    error: Exception,
    *,
    phase: str,
    show_exception: bool,
) -> str:
    """记录 WAV sidecar 内部异常并返回调试详情。

    Args:
        ctx: 运行时上下文。
        error: 捕获到的异常对象。
        phase: 异常发生阶段。
        show_exception: 是否在日志中附带 traceback。

    Returns:
        写入运行时总结的 detail 文本。
    """
    detail = f"phase={phase}, error_type={type(error).__name__}, error={error}"
    logger.opt(exception=show_exception).warning(f"WAV sidecar {phase} 失败，已自动降级为仅保留 WEM: {error}")
    record_runtime_note(
        ctx.runtime_cache,
        "extract",
        INTERNAL_ERROR_NOTE,
        label="音频解包",
        detail=detail,
    )
    return detail


def processed_count(snapshot: WavSidecarProgressSnapshot) -> int:
    """返回当前已处理完成的 WAV 任务数。"""
    return snapshot.completed_wav_job_count + snapshot.failed_wav_job_count + snapshot.skipped_wav_job_count


def format_progress(snapshot: WavSidecarProgressSnapshot) -> str:
    """将 WAV sidecar 快照格式化为可读文案。"""
    counters = [
        f"已提交 {snapshot.submitted_wav_job_count}",
        f"运行中 {snapshot.running_wav_job_count}",
        f"完成 {snapshot.completed_wav_job_count}",
        f"失败 {snapshot.failed_wav_job_count}",
    ]
    if snapshot.retried_wav_job_count:
        counters.append(f"重试 {snapshot.retried_wav_job_count}")
    if snapshot.skipped_wav_job_count:
        counters.append(f"跳过 {snapshot.skipped_wav_job_count}")

    if snapshot.phase == "draining":
        prefix = "音频解包已完成，正在等待 WAV 转码收尾"
    elif snapshot.phase == "finalized":
        prefix = "WAV 转码已完成"
    elif snapshot.phase == "breaker_opened":
        prefix = "WAV 转码已触发熔断，后续任务将跳过"
    elif snapshot.phase == "retrying":
        prefix = "WAV 转码失败，准备重试"
    else:
        prefix = "WAV 转码进行中"
    return f"{prefix}：{'，'.join(counters)}"


def emit_degraded_progress(
    *,
    progress_callback: Callable[[str, int, int, str], None] | None,
) -> None:
    """向上游发出 WAV sidecar 已降级的进度提示。"""
    if progress_callback is None:
        return
    progress_callback("wav", 1, 1, "WAV 转码不可用，已自动降级为仅保留 WEM。")


def build_manifest_recorder(*, ctx: AppContext, job_label: str) -> WavManifestRecorder:
    """为 detached WAV sidecar 构造清单记录器。

    Args:
        ctx: 运行时上下文。
        job_label: 后台任务标签。

    Returns:
        对应任务的清单记录器。
    """
    manifest_path = Path(ctx.paths.report_path) / "_wav_manifests" / f"{job_label}.txt"
    if manifest_path.exists():
        manifest_path.unlink(missing_ok=True)
    return WavManifestRecorder(manifest_path)


def launch_detached_wav(
    *,
    ctx: AppContext,
    wav_output: WavOutputOptions,
    manifest_recorder: WavManifestRecorder,
    job_label: str,
) -> WavBackgroundProcessHandle | None:
    """根据已记录的 WEM 清单启动后台 WAV 进程。

    Args:
        ctx: 运行时上下文。
        wav_output: WAV 输出配置。
        manifest_recorder: 已写入的 WEM 清单记录器。
        job_label: 后台任务标签。

    Returns:
        启动成功时返回后台进程句柄；没有可处理任务时返回 ``None``。
    """
    if not manifest_recorder.has_records() or not manifest_recorder.manifest_path.exists():
        return None

    manifest_lines = [
        line.strip()
        for line in manifest_recorder.manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not manifest_lines:
        return None

    first_wem_path = Path(manifest_lines[0])
    audio_root = Path(ctx.paths.audio_path)
    relative_parts = first_wem_path.relative_to(audio_root).parts
    if not relative_parts:
        return None

    version = relative_parts[0]
    spec = build_wav_background_job_spec_from_paths(
        job_label=job_label,
        manifest_path=manifest_recorder.manifest_path,
        audio_root=audio_root / version,
        wav_root=Path(ctx.paths.wav_path) / version,
        report_root=Path(ctx.paths.report_path) / version / "transcode_wav" / job_label,
        worker_count=wav_output.worker_count,
        timeout_seconds=wav_output.timeout_seconds,
        max_retries=wav_output.max_retries,
        wav_format=wav_output.format,
    )
    return launch_wav_background_process(spec)


def build_progress_handler(
    *,
    progress_callback: Callable[[str, int, int, str], None] | None,
) -> Callable[[WavSidecarProgressSnapshot], None]:
    """构造 WAV sidecar 到日志/GUI 进度的桥接回调。

    Args:
        progress_callback: 上游结构化进度回调。

    Returns:
        可传给 sidecar 协调器的快照回调。
    """
    last_logged_submitted = 0
    last_logged_processed = 0

    def handle(snapshot: WavSidecarProgressSnapshot) -> None:
        nonlocal last_logged_processed, last_logged_submitted

        processed = processed_count(snapshot)
        total = max(snapshot.submitted_wav_job_count, 1)
        message = format_progress(snapshot)

        if progress_callback is not None:
            progress_callback("wav", processed, total, message)

        should_log = False
        log_fn = logger.info
        if snapshot.phase in {"draining", "finalized"}:
            should_log = True
        elif snapshot.phase == "breaker_opened":
            should_log = True
            log_fn = logger.warning
        elif snapshot.phase == "retrying":
            should_log = True
            log_fn = logger.warning
        elif snapshot.phase == "submitted":
            submitted = snapshot.submitted_wav_job_count
            if submitted == 1 or submitted - last_logged_submitted >= _SUBMITTED_LOG_INTERVAL:
                should_log = True
                last_logged_submitted = submitted
        elif snapshot.phase in {"completed", "failed"}:
            if processed in {1, snapshot.submitted_wav_job_count}:
                should_log = True
            elif processed - last_logged_processed >= _PROCESSED_LOG_INTERVAL:
                should_log = True
            if should_log:
                last_logged_processed = processed

        if should_log:
            log_fn(message)

    return handle
