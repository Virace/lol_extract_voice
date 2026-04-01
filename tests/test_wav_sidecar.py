"""WAV sidecar 协调器的定向单元测试。"""

from __future__ import annotations

import time
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any

import pytest

from lol_audio_unpack.app_context import WavOutputOptions
from lol_audio_unpack.wav_sidecar import WavTranscodeCoordinator, build_wav_output_path

pytestmark = pytest.mark.unit

BREAKER_FAILURE_THRESHOLD = 8


def slow_worker_entry(_job: Any, queue: Queue[Any]) -> None:
    """模拟超时的 worker。"""
    time.sleep(2)
    queue.put({"ok": True, "byte_count": 0})


def always_fail_worker_entry(_job: Any, queue: Queue[Any]) -> None:
    """模拟稳定失败的 worker。"""
    queue.put(
        {
            "ok": False,
            "error_type": "RuntimeError",
            "error_message": "decode failed",
        }
    )


def test_build_wav_output_path_mirrors_audio_tree(tmp_path: Path) -> None:
    audio_root = tmp_path / "audios" / "15.8"
    wav_root = tmp_path / "wavs" / "15.8"
    wem_path = audio_root / "champions" / "1·annie" / "1000·base" / "VO" / "123456.wem"

    wav_path = build_wav_output_path(wem_path, audio_root=audio_root, wav_root=wav_root)

    assert wav_path == wav_root / "champions" / "1·annie" / "1000·base" / "VO" / "123456.wav"


def test_timeout_attempt_is_retried_and_final_failure_is_recorded(tmp_path: Path) -> None:
    options = WavOutputOptions(enabled=True, worker_count=2, timeout_seconds=1, max_retries=3)
    coordinator = WavTranscodeCoordinator(
        options=options,
        audio_root=tmp_path / "audios" / "15.8",
        wav_root=tmp_path / "wavs" / "15.8",
        report_root=tmp_path / "reports" / "15.8" / "transcode_wav",
        worker_entry=slow_worker_entry,
    )

    coordinator.submit_persisted_wem(tmp_path / "audios" / "15.8" / "sample.wem")
    coordinator.mark_extract_finished()
    summary = coordinator.finalize()

    assert summary.failed_wav_job_count == 1
    assert summary.retried_wav_job_count == 1
    assert summary.breaker_open is False


def test_breaker_opens_after_repeated_final_failures(tmp_path: Path) -> None:
    options = WavOutputOptions(enabled=True, worker_count=2, timeout_seconds=1, max_retries=3)
    coordinator = WavTranscodeCoordinator(
        options=options,
        audio_root=tmp_path / "audios" / "15.8",
        wav_root=tmp_path / "wavs" / "15.8",
        report_root=tmp_path / "reports" / "15.8" / "transcode_wav",
        worker_entry=always_fail_worker_entry,
    )

    for index in range(BREAKER_FAILURE_THRESHOLD):
        coordinator.submit_persisted_wem(tmp_path / "audios" / "15.8" / f"{index}.wem")

    coordinator.mark_extract_finished()
    summary = coordinator.finalize()

    assert summary.breaker_open is True
    assert summary.failed_wav_job_count >= BREAKER_FAILURE_THRESHOLD
