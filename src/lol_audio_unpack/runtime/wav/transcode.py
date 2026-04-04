"""WAV 转码协调器与报告写出。"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any

from loguru import logger

from ...app_context import WavOutputOptions
from ._runtime import (
    AttemptResult,
    Job,
    JobFailure,
    TranscodeSummary,
    _run_attempt,
    build_output_path,
    run_worker,
)

_BREAKER_CONSECUTIVE_FAILURES = 8
_BREAKER_RECENT_WINDOW = 16
_BREAKER_RECENT_FAILURE_THRESHOLD = 12
_POLL_INTERVAL_SECONDS = 0.05


@dataclass
class _QueuedJob:
    job: Job
    attempt_count: int = 0


@dataclass(frozen=True)
class TranscodeProgress:
    """描述 WAV 转码当前进度与生命周期状态。"""

    phase: str
    extract_finished: bool
    produced_wem_count: int
    submitted_wav_job_count: int
    running_wav_job_count: int
    completed_wav_job_count: int
    failed_wav_job_count: int
    skipped_wav_job_count: int
    retried_wav_job_count: int
    breaker_open: bool
    breaker_reason: str | None


class TranscodeCoordinator:
    """协调 WAV 转码生命周期。"""

    def __init__(  # noqa: PLR0913
        self,
        *,
        options: WavOutputOptions,
        audio_root: Path,
        wav_root: Path,
        report_root: Path,
        worker_entry: Callable[[Job, Queue[Any]], None] = run_worker,
        progress_callback: Callable[[TranscodeProgress], None] | None = None,
    ) -> None:
        """初始化协调器。

        Args:
            options: WAV 转码运行配置。
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
        self._progress_callback = progress_callback
        self._executor = ThreadPoolExecutor(max_workers=options.worker_count, thread_name_prefix="wav-transcode")
        self._pending_jobs: deque[_QueuedJob] = deque()
        self._running_jobs: dict[Future[AttemptResult], _QueuedJob] = {}
        self._final_failures: list[JobFailure] = []
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

    def submit(
        self,
        wem_path: Path,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        sub_id: str | None = None,
        audio_type: str | None = None,
    ) -> None:
        """接收已落盘的 ``.wem`` 并加入转码队列。

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

        job = Job(
            wem_path=wem_path,
            wav_path=build_output_path(wem_path, audio_root=self.audio_root, wav_root=self.wav_root),
            wav_format=self.options.format,
            entity_type=entity_type,
            entity_id=entity_id,
            sub_id=sub_id,
            audio_type=audio_type,
        )
        self.submitted_wav_job_count += 1
        self._pending_jobs.append(_QueuedJob(job=job))
        self._dispatch_available_jobs()
        self._emit("submitted")

    def finish_extract(self) -> None:
        """标记主 extraction 已结束。"""
        self._extract_finished = True
        self._poll_finished_attempts()
        self._dispatch_available_jobs()
        self._emit("draining")

    def finish(self) -> TranscodeSummary:
        """等待所有可执行任务结束并写出报告。

        Returns:
            当前整轮转码的汇总结果。
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

        summary = TranscodeSummary(
            produced_wem_count=self.produced_wem_count,
            submitted_wav_job_count=self.submitted_wav_job_count,
            completed_wav_job_count=self.completed_wav_job_count,
            failed_wav_job_count=self.failed_wav_job_count,
            skipped_wav_job_count=self.skipped_wav_job_count,
            retried_wav_job_count=self.retried_wav_job_count,
            breaker_open=self.breaker_open,
            breaker_reason=self.breaker_reason,
        )
        self._write_summary(summary)
        self._write_failures()
        self._emit("done")
        return summary

    def _dispatch_available_jobs(self) -> None:
        while not self.breaker_open and self._pending_jobs and len(self._running_jobs) < self.options.worker_count:
            queued_job = self._pending_jobs.popleft()
            queued_job.attempt_count += 1
            future = self._executor.submit(
                _run_attempt,
                queued_job.job,
                timeout_seconds=self.options.timeout_seconds,
                worker_entry=self._worker_entry,
            )
            self._running_jobs[future] = queued_job
            self._emit("started")

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
            self._emit("completed")
            return

        if queued_job.attempt_count < self.options.max_retries:
            if queued_job.job.wem_path not in self._retried_wem_paths:
                self._retried_wem_paths.add(queued_job.job.wem_path)
                self.retried_wav_job_count += 1
            self._pending_jobs.append(queued_job)
            self._emit("retrying")
            return

        self.failed_wav_job_count += 1
        self._final_failures.append(
            JobFailure(
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
        self._emit("failed")

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
        if self.breaker_open:
            self._emit("breaker_opened")

    def _snapshot(self, phase: str) -> TranscodeProgress:
        """构造当前转码进度快照。"""
        return TranscodeProgress(
            phase=phase,
            extract_finished=self._extract_finished,
            produced_wem_count=self.produced_wem_count,
            submitted_wav_job_count=self.submitted_wav_job_count,
            running_wav_job_count=len(self._running_jobs),
            completed_wav_job_count=self.completed_wav_job_count,
            failed_wav_job_count=self.failed_wav_job_count,
            skipped_wav_job_count=self.skipped_wav_job_count,
            retried_wav_job_count=self.retried_wav_job_count,
            breaker_open=self.breaker_open,
            breaker_reason=self.breaker_reason,
        )

    def _emit(self, phase: str) -> None:
        """将当前进度快照安全地发给主流程。"""
        if self._progress_callback is None:
            return
        snapshot = self._snapshot(phase)
        try:
            self._progress_callback(snapshot)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"WAV transcode progress callback failed: {exc}")

    def _write_summary(self, summary: TranscodeSummary) -> None:
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

    def _write_failures(self) -> None:
        self.report_root.mkdir(parents=True, exist_ok=True)
        target_path = self.report_root / "failures.jsonl"
        lines = [json.dumps(failure.to_payload(), ensure_ascii=False) for failure in self._final_failures]
        target_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


__all__ = [
    "TranscodeProgress",
    "TranscodeCoordinator",
]
