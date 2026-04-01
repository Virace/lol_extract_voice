"""WAV sidecar 转码协调器与报告写出。"""

from __future__ import annotations

import json
import multiprocessing
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib import import_module
from multiprocessing.queues import Queue
from pathlib import Path
from queue import Empty
from typing import Any

from .app_context import WavOutputOptions

_BREAKER_CONSECUTIVE_FAILURES = 8
_BREAKER_RECENT_WINDOW = 16
_BREAKER_RECENT_FAILURE_THRESHOLD = 12
_POLL_INTERVAL_SECONDS = 0.05


@dataclass(frozen=True)
class WavJob:
    """描述单个待转码的 WAV 任务。"""

    wem_path: Path
    wav_path: Path
    entity_type: str | None = None
    entity_id: str | None = None
    sub_id: str | None = None
    audio_type: str | None = None


@dataclass(frozen=True)
class WavJobFailure:
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
class WavSidecarSummary:
    """描述整轮 WAV sidecar 的汇总结果。"""

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


@dataclass
class _QueuedJob:
    job: WavJob
    attempt_count: int = 0


def build_wav_output_path(wem_path: Path, *, audio_root: Path, wav_root: Path) -> Path:
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


def default_worker_entry(job: WavJob, queue: Queue[Any]) -> None:
    """执行单个 WAV 转码任务。

    Args:
        job: 当前转码任务。
        queue: 用于回传结构化结果的进程队列。
    """
    try:
        decode_to_wav_file = import_module("pyvgmstream").decode_to_wav_file
        job.wav_path.parent.mkdir(parents=True, exist_ok=True)
        result = decode_to_wav_file(job.wem_path, job.wav_path)
        queue.put({"ok": True, "byte_count": result.byte_count})
    except Exception as exc:  # noqa: BLE001
        queue.put(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )


def _run_attempt_with_timeout(
    job: WavJob,
    *,
    timeout_seconds: int,
    worker_entry: Callable[[WavJob, Queue[Any]], None],
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


class WavTranscodeCoordinator:
    """协调 WAV sidecar 转码生命周期。"""

    def __init__(
        self,
        *,
        options: WavOutputOptions,
        audio_root: Path,
        wav_root: Path,
        report_root: Path,
        worker_entry: Callable[[WavJob, Queue[Any]], None] = default_worker_entry,
    ) -> None:
        """初始化协调器。

        Args:
            options: WAV sidecar 运行配置。
            audio_root: 权威音频根目录。
            wav_root: 镜像 WAV 根目录。
            report_root: 报告输出目录。
            worker_entry: 单次转码子进程入口。
        """
        if options.worker_count < 1:
            raise ValueError("worker_count must be positive")
        if options.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        if options.max_retries < 1:
            raise ValueError("max_retries must be positive")

        self.options = options
        self.audio_root = audio_root
        self.wav_root = wav_root
        self.report_root = report_root
        self._worker_entry = worker_entry
        self._executor = ThreadPoolExecutor(max_workers=options.worker_count, thread_name_prefix="wav-sidecar")
        self._pending_jobs: deque[_QueuedJob] = deque()
        self._running_jobs: dict[Future[AttemptResult], _QueuedJob] = {}
        self._final_failures: list[WavJobFailure] = []
        self._retried_wem_paths: set[Path] = set()
        self._recent_final_outcomes: deque[bool] = deque(maxlen=_BREAKER_RECENT_WINDOW)
        self._consecutive_final_failures = 0
        self._extract_finished = False
        self._finalized = False
        self._started_at = datetime.now(UTC)
        self._finished_at: datetime | None = None

        self.produced_wem_count = 0
        self.submitted_wav_job_count = 0
        self.completed_wav_job_count = 0
        self.failed_wav_job_count = 0
        self.skipped_wav_job_count = 0
        self.retried_wav_job_count = 0
        self.breaker_open = False
        self.breaker_reason: str | None = None

    def submit_persisted_wem(
        self,
        wem_path: Path,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        sub_id: str | None = None,
        audio_type: str | None = None,
    ) -> None:
        """接收已落盘的 ``.wem`` 并加入 sidecar 队列。

        Args:
            wem_path: 成功落盘的 ``.wem`` 路径。
            entity_type: 可选实体类型。
            entity_id: 可选实体 ID。
            sub_id: 可选子资源 ID。
            audio_type: 可选音频类型。
        """
        self.produced_wem_count += 1
        self._poll_finished_attempts()
        if self.breaker_open:
            self.skipped_wav_job_count += 1
            return

        job = WavJob(
            wem_path=wem_path,
            wav_path=build_wav_output_path(wem_path, audio_root=self.audio_root, wav_root=self.wav_root),
            entity_type=entity_type,
            entity_id=entity_id,
            sub_id=sub_id,
            audio_type=audio_type,
        )
        self.submitted_wav_job_count += 1
        self._pending_jobs.append(_QueuedJob(job=job))
        self._dispatch_available_jobs()

    def mark_extract_finished(self) -> None:
        """标记主 extraction 已结束。"""
        self._extract_finished = True
        self._poll_finished_attempts()
        self._dispatch_available_jobs()

    def finalize(self) -> WavSidecarSummary:
        """等待所有可执行任务结束并写出报告。

        Returns:
            当前整轮 sidecar 的汇总结果。
        """
        while self._pending_jobs or self._running_jobs or not self._extract_finished:
            self._dispatch_available_jobs()
            self._poll_finished_attempts(block=bool(self._running_jobs))
            if self._extract_finished and not self._pending_jobs and not self._running_jobs:
                break

        self._finished_at = datetime.now(UTC)
        if not self._finalized:
            self._executor.shutdown(wait=True)
            self._finalized = True

        summary = WavSidecarSummary(
            produced_wem_count=self.produced_wem_count,
            submitted_wav_job_count=self.submitted_wav_job_count,
            completed_wav_job_count=self.completed_wav_job_count,
            failed_wav_job_count=self.failed_wav_job_count,
            skipped_wav_job_count=self.skipped_wav_job_count,
            retried_wav_job_count=self.retried_wav_job_count,
            breaker_open=self.breaker_open,
            breaker_reason=self.breaker_reason,
        )
        self._write_summary_json(summary)
        self._write_failures_jsonl()
        return summary

    def _dispatch_available_jobs(self) -> None:
        while not self.breaker_open and self._pending_jobs and len(self._running_jobs) < self.options.worker_count:
            queued_job = self._pending_jobs.popleft()
            queued_job.attempt_count += 1
            future = self._executor.submit(
                _run_attempt_with_timeout,
                queued_job.job,
                timeout_seconds=self.options.timeout_seconds,
                worker_entry=self._worker_entry,
            )
            self._running_jobs[future] = queued_job

    def _poll_finished_attempts(self, *, block: bool = False) -> None:
        if not self._running_jobs:
            return

        done_futures = [future for future in self._running_jobs if future.done()]
        if not done_futures and block:
            done_futures, _ = wait(
                tuple(self._running_jobs),
                timeout=_POLL_INTERVAL_SECONDS,
                return_when=FIRST_COMPLETED,
            )

        for future in list(done_futures):
            queued_job = self._running_jobs.pop(future)
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = AttemptResult(
                    ok=False,
                    timeout=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            self._handle_attempt_result(queued_job, result)

    def _handle_attempt_result(self, queued_job: _QueuedJob, result: AttemptResult) -> None:
        if result.ok:
            self.completed_wav_job_count += 1
            self._record_final_outcome(False)
            return

        if queued_job.attempt_count < self.options.max_retries:
            if queued_job.job.wem_path not in self._retried_wem_paths:
                self._retried_wem_paths.add(queued_job.job.wem_path)
                self.retried_wav_job_count += 1
            self._pending_jobs.append(queued_job)
            return

        self.failed_wav_job_count += 1
        self._final_failures.append(
            WavJobFailure(
                wem_path=queued_job.job.wem_path,
                wav_path=queued_job.job.wav_path,
                attempt_count=queued_job.attempt_count,
                timed_out=result.timeout,
                error_type=result.error_type or "RuntimeError",
                error_message=result.error_message or "wav transcode failed",
                elapsed_ms=int(round(result.elapsed_seconds * 1000)),
                entity_type=queued_job.job.entity_type,
                entity_id=queued_job.job.entity_id,
                sub_id=queued_job.job.sub_id,
                audio_type=queued_job.job.audio_type,
            )
        )
        self._record_final_outcome(True)
        self._maybe_open_breaker()

    def _record_final_outcome(self, failed: bool) -> None:
        self._recent_final_outcomes.append(failed)
        self._consecutive_final_failures = self._consecutive_final_failures + 1 if failed else 0

    def _maybe_open_breaker(self) -> None:
        if self.breaker_open:
            return
        if self._consecutive_final_failures >= _BREAKER_CONSECUTIVE_FAILURES:
            self.breaker_open = True
            self.breaker_reason = "consecutive_failures"
        elif (
            len(self._recent_final_outcomes) == _BREAKER_RECENT_WINDOW
            and sum(self._recent_final_outcomes) >= _BREAKER_RECENT_FAILURE_THRESHOLD
        ):
            self.breaker_open = True
            self.breaker_reason = "recent_failures"

        if self.breaker_open and self._pending_jobs:
            self.skipped_wav_job_count += len(self._pending_jobs)
            self._pending_jobs.clear()

    def _write_summary_json(self, summary: WavSidecarSummary) -> None:
        self.report_root.mkdir(parents=True, exist_ok=True)
        finished_at = self._finished_at or datetime.now(UTC)
        payload = {
            "status": "warning" if (summary.failed_wav_job_count or summary.skipped_wav_job_count) else "success",
            "transcode_requested": self.options.enabled,
            "extract_finished": self._extract_finished,
            "breaker_open": summary.breaker_open,
            "breaker_reason": summary.breaker_reason,
            "worker_count": self.options.worker_count,
            "timeout_seconds": self.options.timeout_seconds,
            "max_retries": self.options.max_retries,
            **asdict(summary),
            "audio_root": str(self.audio_root),
            "wav_root": str(self.wav_root),
            "started_at": self._started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "elapsed_seconds": round((finished_at - self._started_at).total_seconds(), 3),
        }
        (self.report_root / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_failures_jsonl(self) -> None:
        self.report_root.mkdir(parents=True, exist_ok=True)
        target_path = self.report_root / "failures.jsonl"
        lines = [json.dumps(failure.to_payload(), ensure_ascii=False) for failure in self._final_failures]
        target_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


__all__ = [
    "WavJob",
    "WavJobFailure",
    "WavSidecarSummary",
    "WavTranscodeCoordinator",
    "build_wav_output_path",
    "default_worker_entry",
]
