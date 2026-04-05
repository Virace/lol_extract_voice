"""WAV 转码 stage 的路径装配与批处理入口。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from pyvgmstream.transcode import BatchTranscodeItemResult, BatchTranscodeProgress, transcode_tree

from ...app.types import AppContext, WavOutputOptions
from ._runtime import resolve_decode_config


@dataclass(slots=True, frozen=True)
class TranscodePaths:
    """描述单个版本的 WAV 运行路径组合。"""

    audio_root: Path
    wav_root: Path
    report_root: Path


def build_transcode_paths(*, ctx: AppContext, version: str, job_label: str | None = None) -> TranscodePaths:
    """根据版本和可选标签构造 WAV 路径组合。

    Args:
        ctx: 运行时上下文。
        version: 当前数据版本号。
        job_label: 可选报告标签；提供时报告目录会追加该标签。

    Returns:
        TranscodePaths: 当前版本对应的音频、WAV 和报告目录。
    """
    report_root = Path(ctx.paths.report_path) / version / "transcode_wav"
    if job_label is not None:
        report_root = report_root / job_label
    return TranscodePaths(
        audio_root=Path(ctx.paths.audio_path) / version,
        wav_root=Path(ctx.paths.wav_path) / version,
        report_root=report_root,
    )


def _format_progress(progress: BatchTranscodeProgress) -> str:
    """将 `pyvgmstream` 的批处理进度格式化为日志文案。"""
    return f"WAV 转码进行中：文件 {progress.completed_count}/{max(progress.total_count, 1)} · 失败 {progress.failed_count}"


def _serialize_failure(result: BatchTranscodeItemResult) -> dict[str, Any]:
    """序列化单条失败结果。"""
    return {
        "source_path": str(result.source_path),
        "output_path": str(result.output_path),
        "frame_count": result.frame_count,
        "byte_count": result.byte_count,
        "error": result.error or "unknown error",
    }


def _write_reports(
    report_root: Path,
    *,
    payload: dict[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    """写出转码汇总与失败报告。"""
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_root / "failures.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in failures) + ("\n" if failures else ""),
        encoding="utf-8",
    )


def run_tree(  # noqa: PLR0913
    *,
    ctx: AppContext,
    version: str,
    wav_output: WavOutputOptions,
    audio_roots: tuple[Path, ...] | None = None,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    job_label: str | None = None,
) -> dict[str, Any]:
    """对当前版本的默认 audios 树执行一次完整 WAV 转码。

    Args:
        ctx: 运行时上下文。
        version: 当前数据版本号。
        wav_output: WAV 输出配置。
        audio_roots: 可选的音频根目录集合；为空时默认消费整个版本目录。
        progress_callback: 可选的统一进度回调。
        job_label: 可选报告标签。

    Returns:
        dict[str, Any]: 供上层汇总与日志消费的转码结果摘要。
    """
    paths = build_transcode_paths(ctx=ctx, version=version, job_label=job_label)
    decode_config = resolve_decode_config(wav_output.format)
    run_roots = (paths.audio_root,) if audio_roots is None else tuple(Path(root) for root in audio_roots)

    logger.info(
        "开始 WAV 转码：audio_root={}，wav_root={}，workers={}，format={}",
        paths.audio_root,
        paths.wav_root,
        wav_output.worker_count,
        wav_output.format,
    )

    def emit_progress(progress: BatchTranscodeProgress) -> None:
        message = _format_progress(progress)
        if progress_callback is not None:
            progress_callback("wav", progress.completed_count, max(progress.total_count, 1), message)
        logger.info(message)

    if not run_roots:
        logger.warning("WAV 转码未找到可处理的音频目录，已跳过本次执行。")
        payload = {
            "status": "success",
            "job_label": job_label,
            "audio_root": str(paths.audio_root),
            "wav_root": str(paths.wav_root),
            "worker_count": wav_output.worker_count,
            "wav_format": wav_output.format,
            "processed_file_count": 0,
            "failed_file_count": 0,
            "audio_roots": [],
        }
        _write_reports(paths.report_root, payload=payload, failures=[])
        return payload

    processed_count = 0
    failed_count = 0
    failures: list[dict[str, Any]] = []
    for input_root in run_roots:
        output_root = paths.wav_root / input_root.relative_to(paths.audio_root)
        summary = transcode_tree(
            input_root,
            output_root,
            workers=wav_output.worker_count,
            chunk_frames=65536,
            dispatch_chunksize=64,
            config=decode_config,
            progress_callback=emit_progress,
        )
        processed_count += summary.processed_count
        failed_count += summary.failed_count
        failures.extend(
            _serialize_failure(result)
            for result in summary.results
            if result.error
        )
    payload = {
        "status": "warning" if failed_count else "success",
        "job_label": job_label,
        "audio_root": str(paths.audio_root),
        "wav_root": str(paths.wav_root),
        "worker_count": wav_output.worker_count,
        "wav_format": wav_output.format,
        "processed_file_count": processed_count,
        "failed_file_count": failed_count,
        "audio_roots": [str(root) for root in run_roots],
    }
    _write_reports(paths.report_root, payload=payload, failures=failures)

    if failed_count:
        logger.warning(
            "WAV 转码完成：成功 {} 个，失败 {} 个",
            processed_count,
            failed_count,
        )
    else:
        logger.success("WAV 转码完成：成功 {} 个", processed_count)

    return payload


__all__ = [
    "TranscodePaths",
    "build_transcode_paths",
    "run_tree",
]
