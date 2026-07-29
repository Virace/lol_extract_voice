"""验证旧 WAV 协调器的真实多进程与报告边界。"""

from __future__ import annotations

import json
import time
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any

import pytest

from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.runtime.wav import TranscodeCoordinator, TranscodeProgress

pytestmark = pytest.mark.system

BREAKER_FAILURE_THRESHOLD = 8


def slow_worker(_job: Any, queue: Queue[Any]) -> None:
    """模拟超过单次尝试期限的 worker。"""
    time.sleep(2)
    queue.put({"ok": True, "byte_count": 0})


def failing_worker(_job: Any, queue: Queue[Any]) -> None:
    """模拟稳定失败的 worker。"""
    queue.put(
        {
            "ok": False,
            "error_type": "RuntimeError",
            "error_message": "decode failed",
        }
    )


def successful_worker(_job: Any, queue: Queue[Any]) -> None:
    """模拟立即成功的 worker。"""
    queue.put({"ok": True, "byte_count": 123})


def test_timeout_is_retried_then_recorded(tmp_path: Path) -> None:
    """超时任务应重试，并在达到上限后记为失败。"""
    coordinator = TranscodeCoordinator(
        options=WavOutputOptions(enabled=True, worker_count=2, timeout_seconds=1, max_retries=3),
        audio_root=tmp_path / "audios" / "15.8",
        wav_root=tmp_path / "wavs" / "15.8",
        report_root=tmp_path / "reports" / "15.8" / "transcode_wav",
        worker_entry=slow_worker,
    )

    coordinator.submit(tmp_path / "audios" / "15.8" / "sample.wem")
    coordinator.finish_extract()
    summary = coordinator.finish()

    assert summary.failed_wav_job_count == 1
    assert summary.retried_wav_job_count == 1
    assert summary.breaker_open is False


def test_repeated_failures_open_breaker_and_write_reports(tmp_path: Path) -> None:
    """连续失败应打开熔断器，并留下与汇总一致的报告。"""
    report_root = tmp_path / "reports" / "15.8" / "transcode_wav"
    coordinator = TranscodeCoordinator(
        options=WavOutputOptions(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1),
        audio_root=tmp_path / "audios" / "15.8",
        wav_root=tmp_path / "wavs" / "15.8",
        report_root=report_root,
        worker_entry=failing_worker,
    )

    for index in range(BREAKER_FAILURE_THRESHOLD + 1):
        coordinator.submit(tmp_path / "audios" / "15.8" / f"{index}.wem")

    coordinator.finish_extract()
    summary = coordinator.finish()

    summary_path = report_root / "summary.json"
    failures_path = report_root / "failures.jsonl"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary.breaker_open is True
    assert summary.failed_wav_job_count >= BREAKER_FAILURE_THRESHOLD
    assert payload["failed_wav_job_count"] == summary.failed_wav_job_count
    assert payload["skipped_wav_job_count"] == summary.skipped_wav_job_count
    assert len(failures_path.read_text(encoding="utf-8").strip().splitlines()) == summary.failed_wav_job_count


def test_progress_callback_receives_lifecycle(tmp_path: Path) -> None:
    """协调器应在关键生命周期节点发出结构化进度。"""
    snapshots: list[TranscodeProgress] = []
    coordinator = TranscodeCoordinator(
        options=WavOutputOptions(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1),
        audio_root=tmp_path / "audios" / "15.8",
        wav_root=tmp_path / "wavs" / "15.8",
        report_root=tmp_path / "reports" / "15.8" / "transcode_wav",
        worker_entry=successful_worker,
        progress_callback=snapshots.append,
    )

    coordinator.submit(tmp_path / "audios" / "15.8" / "sample.wem")
    coordinator.finish_extract()
    summary = coordinator.finish()

    assert any(snapshot.phase == "submitted" for snapshot in snapshots)
    assert any(snapshot.phase == "draining" and snapshot.extract_finished for snapshot in snapshots)
    assert snapshots[-1].phase == "done"
    assert snapshots[-1].completed_wav_job_count == summary.completed_wav_job_count
    assert snapshots[-1].running_wav_job_count == 0
