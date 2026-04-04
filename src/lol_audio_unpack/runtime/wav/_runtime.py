"""WAV 转码的低层数据结构与尝试执行器。"""

from __future__ import annotations

import multiprocessing
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from multiprocessing.queues import Queue
from pathlib import Path
from queue import Empty
from typing import Any

from pyvgmstream import DecodeConfig, SampleFormat, decode_to_wav_file


@dataclass(frozen=True)
class Job:
    """描述单个待转码任务。"""

    wem_path: Path
    wav_path: Path
    wav_format: str = "pcm16"
    entity_type: str | None = None
    entity_id: str | None = None
    sub_id: str | None = None
    audio_type: str | None = None


@dataclass(frozen=True)
class JobFailure:
    """描述最终失败的 WAV 转码任务。"""

    wem_path: Path
    wav_path: Path
    attempt_count: int
    timed_out: bool
    error_type: str
    error_message: str
    elapsed_ms: int
    entity_type: str | None = None
    entity_id: str | None = None
    sub_id: str | None = None
    audio_type: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """转换为 JSON 可序列化字典。

        Returns:
            适合写入 ``failures.jsonl`` 的字典。
        """
        payload = asdict(self)
        payload["wem_path"] = str(self.wem_path)
        payload["wav_path"] = str(self.wav_path)
        return payload


@dataclass(frozen=True)
class TranscodeSummary:
    """描述整轮 WAV 转码的汇总结果。"""

    produced_wem_count: int
    submitted_wav_job_count: int
    completed_wav_job_count: int
    failed_wav_job_count: int
    skipped_wav_job_count: int
    retried_wav_job_count: int
    breaker_open: bool
    breaker_reason: str | None


@dataclass(frozen=True)
class AttemptResult:
    """描述单次转码尝试的结果。"""

    ok: bool = False
    byte_count: int = 0
    timeout: bool = False
    error_type: str | None = None
    error_message: str | None = None
    elapsed_seconds: float = 0.0

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, elapsed_seconds: float) -> AttemptResult:
        """根据 worker 返回值构建尝试结果。

        Args:
            payload: 子进程通过队列写回的结构化结果。
            elapsed_seconds: 本次尝试耗时。

        Returns:
            标准化后的尝试结果对象。
        """
        if payload.get("ok"):
            return cls(ok=True, byte_count=int(payload.get("byte_count", 0)), elapsed_seconds=elapsed_seconds)
        return cls(
            ok=False,
            timeout=False,
            error_type=str(payload.get("error_type", "RuntimeError")),
            error_message=str(payload.get("error_message", "wav transcode failed")),
            elapsed_seconds=elapsed_seconds,
        )


def build_output_path(wem_path: Path, *, audio_root: Path, wav_root: Path) -> Path:
    """根据镜像规则构造 WAV 输出路径。

    Args:
        wem_path: 已落盘的 ``.wem`` 路径。
        audio_root: 权威 ``audios/<version>`` 根目录。
        wav_root: 镜像 ``wavs/<version>`` 根目录。

    Returns:
        镜像后的 ``.wav`` 输出路径。
    """
    relative_path = wem_path.relative_to(audio_root)
    return (wav_root / relative_path).with_suffix(".wav")


def resolve_decode_config(raw_format: str) -> DecodeConfig | None:
    """将 CLI 格式名映射为 `pyvgmstream` 解码配置。

    Args:
        raw_format: 用户传入的 WAV 输出格式名。

    Returns:
        对应的 `DecodeConfig`；当格式为 `auto` 时返回 `None`。

    Raises:
        ValueError: 当格式名不受支持时抛出。
    """
    normalized = raw_format.strip().lower()
    if normalized == "auto":
        return None

    sample_format_map = {
        "pcm16": SampleFormat.PCM16,
        "pcm24": SampleFormat.PCM24,
        "pcm32": SampleFormat.PCM32,
        "float": SampleFormat.FLOAT,
    }
    try:
        sample_format = sample_format_map[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported wav format: {raw_format}") from exc
    return DecodeConfig(sample_format=sample_format)


def run_worker(job: Job, queue: Queue[Any]) -> None:
    """执行单个 WAV 转码任务。

    Args:
        job: 当前转码任务。
        queue: 用于回传结构化结果的进程队列。
    """
    try:
        job.wav_path.parent.mkdir(parents=True, exist_ok=True)
        result = decode_to_wav_file(job.wem_path, job.wav_path, config=resolve_decode_config(job.wav_format))
        queue.put({"ok": True, "byte_count": result.byte_count})
    except Exception as exc:  # noqa: BLE001
        queue.put(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )


def _run_attempt(
    job: Job,
    *,
    timeout_seconds: int,
    worker_entry: Callable[[Job, Queue[Any]], None],
) -> AttemptResult:
    """在独立子进程中运行单次转码并施加硬超时。

    Args:
        job: 当前转码任务。
        timeout_seconds: 单次尝试超时时间。
        worker_entry: 真正的子进程入口。

    Returns:
        本次尝试的结果对象。
    """
    ctx = multiprocessing.get_context("spawn")
    queue: Queue[Any] = ctx.Queue()
    process = ctx.Process(target=worker_entry, args=(job, queue))
    started = time.monotonic()
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        queue.close()
        queue.join_thread()
        return AttemptResult(
            ok=False,
            timeout=True,
            error_type="TimeoutError",
            error_message="wav transcode timed out",
            elapsed_seconds=time.monotonic() - started,
        )

    elapsed_seconds = time.monotonic() - started
    try:
        payload = queue.get(timeout=0.1)
    except Empty:
        exit_code = process.exitcode
        message = "wav transcode worker exited without payload"
        if exit_code not in (0, None):
            message = f"wav transcode worker exited with code {exit_code}"
        result = AttemptResult(
            ok=False,
            timeout=False,
            error_type="RuntimeError",
            error_message=message,
            elapsed_seconds=elapsed_seconds,
        )
    else:
        result = AttemptResult.from_payload(payload, elapsed_seconds=elapsed_seconds)
    finally:
        queue.close()
        queue.join_thread()
    return result


__all__ = [
    "AttemptResult",
    "Job",
    "JobFailure",
    "TranscodeSummary",
    "build_output_path",
    "run_worker",
    "resolve_decode_config",
]
