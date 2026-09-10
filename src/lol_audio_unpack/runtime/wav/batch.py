"""目录、所选音频和失败重试共用的上游批处理适配。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
from uuid import uuid4

from loguru import logger
from pyvgmstream.transcode import BatchTranscodeProgress, transcode_many

from ...app.audio_scope import AudioScope, MappingNode
from ...app.types import WavOutputOptions
from ._runtime import build_output_path, resolve_decode_config

_PROGRESS_INTERVAL = 0.1


@dataclass(frozen=True, slots=True)
class WavFailure:
    """保留可精确重试的输入输出身份和上游原始诊断。"""

    source_path: str
    output_path: str
    error: str


@dataclass(frozen=True, slots=True)
class WavBatchResult:
    """一轮 WAV 批处理的不可变事实，跳过不计为本轮转换成功。"""

    operation_id: str
    scope: AudioScope
    output_root: Path
    options: WavOutputOptions
    overwrite: bool
    success_count: int
    failed_count: int
    skipped_count: int
    failures: tuple[WavFailure, ...]
    duration_seconds: float
    report_path: Path
    output_file: Path | None = None
    parent_id: str | None = None
    error_message: str | None = None
    unconfirmed_count: int = 0
    report_error: str | None = None

    @property
    def status(self) -> str:
        """按成功与失败事实派生终态。"""
        if not self.failed_count and self.error_message is None:
            return "success"
        return "partial" if self.success_count or self.skipped_count else "failed"

    def retry_scope(self) -> AudioScope:
        """只构造本轮失败的精确文件集合，不重新枚举目录。"""
        root = self.scope.root.resolve()
        return AudioScope(
            root, files=tuple(Path(item.source_path).relative_to(root).as_posix() for item in self.failures)
        )


def _write_result(result: WavBatchResult) -> None:
    """以操作身份隔离报告，避免后续任务改写旧详情。"""
    result.report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    payload["status"] = result.status
    payload["scope"]["excluded"] = sorted(result.scope.excluded)
    result.report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    result.report_path.with_name("failures.jsonl").write_text(
        "".join(json.dumps(asdict(item), ensure_ascii=False) + "\n" for item in result.failures), encoding="utf-8"
    )


def run_batch(  # noqa: PLR0913
    scope: AudioScope,
    output_root: Path,
    *,
    options: WavOutputOptions,
    report_root: Path,
    overwrite: bool = False,
    progress: Callable[[BatchTranscodeProgress], None] | None = None,
    output_file: Path | None = None,
    parent_id: str | None = None,
) -> WavBatchResult:
    """在调用方后台执行范围扫描和一次上游批处理。

    Args:
        scope: 当前实体的紧凑范围。
        output_root: 镜像输出根目录。
        options: 与主任务共用的 WAV 配置。
        report_root: 现有 reports 体系中的父目录。
        overwrite: 是否替换本次范围内的输出，默认跳过既有文件。
        progress: 节流后的文件计数回调，应为异步 UI 信号或队列。
        output_file: 单文件另存为目标；使用临时目录避免覆盖同 ID 的其他文件。
        parent_id: 失败重试所关联的原操作身份。

    Returns:
        带有独立报告地址的批处理事实。
    """
    started = monotonic()
    operation_id = uuid4().hex
    output_root = Path(output_root).expanduser().resolve()
    output_file = Path(output_file).expanduser().resolve() if output_file is not None else None
    report_path = Path(report_root) / operation_id / "summary.json"
    root = scope.root.resolve()
    try:
        sources = scope.resolve_files()
    except (OSError, ValueError) as exc:
        logger.warning("WAV 范围复核失败：{}", exc)
        result = WavBatchResult(
            operation_id,
            scope,
            output_root,
            options,
            overwrite,
            0,
            0,
            0,
            (),
            monotonic() - started,
            report_path,
            output_file,
            parent_id,
            f"范围复核失败: {exc}",
        )
        return _persist_result(result)
    if output_file is not None and len(sources) != 1:
        raise ValueError("另存为文件只支持一个精确音频")
    skipped = 0
    pending: list[Path] = []
    failures: list[WavFailure] = []
    logger.info("开始 WAV 批处理：{}，扫描 {} 个文件，覆盖={}", operation_id, len(sources), overwrite)
    for source in sources:
        output = output_file or build_output_path(source, audio_root=root, wav_root=output_root)
        # 已确认的精确输入消失时，不能因旧输出存在而静默跳过。
        if not source.is_file():
            failures.append(WavFailure(str(source), str(output), "对应 WEM 文件不可用，请恢复输入后重试。"))
        elif output.exists() and not overwrite:
            skipped += 1
        else:
            pending.append(source)

    finished = Event()
    last_emit = 0.0

    def emit(snapshot: BatchTranscodeProgress) -> None:
        nonlocal last_emit
        now = monotonic()
        if not finished.is_set() and (
            snapshot.completed_count == snapshot.total_count or now - last_emit >= _PROGRESS_INTERVAL
        ):
            last_emit = now
            if progress is not None:
                progress(snapshot)

    def transcode(destination: Path):
        return transcode_many(
            pending,
            destination,
            input_root=root if output_file is None else None,
            workers=options.worker_count,
            chunk_frames=65536,
            dispatch_chunksize=64,
            config=resolve_decode_config(options.format),
            progress_callback=emit,
        )

    success_count = 0
    error_message = None
    unconfirmed_count = 0
    try:
        if pending:
            destination = output_file.parent if output_file is not None else output_root
            destination.mkdir(parents=True, exist_ok=True)
            # 暂存与最终输出位于同一卷；只有上游确认成功后才原子替换，失败残留不能被下次跳过。
            with TemporaryDirectory(prefix=".wav-export-", dir=destination) as scratch:
                summary = transcode(Path(scratch))
                for item in summary.results:
                    output = output_file or build_output_path(item.source_path, audio_root=root, wav_root=output_root)
                    if item.error is not None:
                        failures.append(WavFailure(str(item.source_path), str(output), item.error))
                        continue
                    try:
                        output.parent.mkdir(parents=True, exist_ok=True)
                        item.output_path.replace(output)
                    except OSError as exc:
                        failures.append(WavFailure(str(item.source_path), str(output), str(exc)))
                    else:
                        success_count += 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("WAV 批处理异常中止：{}", operation_id)
        # 没有上游终态快照时不猜测成功范围；精确输入仍保留供诊断和显式替换。
        error_message = f"{type(exc).__name__}: {exc}（未取得可靠完成结果）"
        unconfirmed_count = len(pending)
    finally:
        finished.set()
    result = WavBatchResult(
        operation_id,
        scope,
        output_root,
        options,
        overwrite,
        success_count,
        len(failures),
        skipped,
        tuple(failures),
        monotonic() - started,
        report_path,
        output_file,
        parent_id,
        error_message,
        unconfirmed_count,
    )
    result = _persist_result(result)
    if failures or error_message:
        logger.warning("WAV 批处理结束：成功 {}、失败 {}、跳过 {} 个文件", success_count, len(failures), skipped)
    else:
        logger.success("WAV 批处理结束：成功 {}、跳过 {} 个文件", success_count, skipped)
    return result


def _persist_result(result: WavBatchResult) -> WavBatchResult:
    """报告写入失败只补充诊断，不能丢弃已完成文件和精确失败身份。"""
    try:
        _write_result(result)
    except OSError as exc:
        logger.error("WAV 报告保存失败，保留内存结果：{}", exc)
        return replace(result, report_error=str(exc))
    return result


def retry_batch(
    result: WavBatchResult, *, progress: Callable[[BatchTranscodeProgress], None] | None = None
) -> WavBatchResult:
    """用原始格式和输出位置重试精确失败项，替换它们可能残留的输出。"""
    if not result.failures:
        raise ValueError("当前结果没有可重试的失败文件")
    return run_batch(
        result.retry_scope(),
        result.output_root,
        options=replace(result.options),
        report_root=result.report_path.parent.parent,
        overwrite=True,
        progress=progress,
        output_file=result.output_file,
        parent_id=result.operation_id,
    )


def read_batch_result(path: Path) -> WavBatchResult:
    """在任务后台恢复本轮报告中的精确结果，避免 UI 同步读取大清单。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    scope = payload["scope"]
    return WavBatchResult(
        operation_id=payload["operation_id"],
        scope=AudioScope(
            Path(scope["root"]),
            tuple(scope["directories"]),
            tuple(scope["files"]),
            frozenset(scope["excluded"]),
            tuple(
                MappingNode(
                    Path(node["mapping_path"]),
                    node["entity_type"],
                    node["entity_id"],
                    tuple(node["signature"]),
                    tuple(node["key"]),
                    node["prefix"],
                )
                for node in scope.get("nodes", ())
            ),
        ),
        output_root=Path(payload["output_root"]),
        options=WavOutputOptions(**payload["options"]),
        overwrite=payload["overwrite"],
        success_count=payload["success_count"],
        failed_count=payload["failed_count"],
        skipped_count=payload["skipped_count"],
        failures=tuple(WavFailure(**item) for item in payload["failures"]),
        duration_seconds=payload["duration_seconds"],
        report_path=path,
        output_file=Path(payload["output_file"]) if payload.get("output_file") else None,
        parent_id=payload.get("parent_id"),
        error_message=payload.get("error_message"),
        unconfirmed_count=payload.get("unconfirmed_count", 0),
        report_error=payload.get("report_error"),
    )
