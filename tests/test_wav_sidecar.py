"""WAV sidecar 协调器的定向单元测试。"""

from __future__ import annotations

import json
import time
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any

import pytest
from pyvgmstream import SampleFormat

from lol_audio_unpack.app_context import WavOutputOptions
from lol_audio_unpack.runtime.wav import (
    WavSidecarProgressSnapshot,
    WavTranscodeCoordinator,
    build_wav_output_path,
    resolve_wav_decode_config,
)
from lol_audio_unpack.runtime.wav._runtime import WavJob, default_worker_entry

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


def instant_success_worker_entry(_job: Any, queue: Queue[Any]) -> None:
    """模拟立即成功的 worker。"""
    queue.put({"ok": True, "byte_count": 123})


def test_build_wav_output_path_mirrors_audio_tree(tmp_path: Path) -> None:
    audio_root = tmp_path / "audios" / "15.8"
    wav_root = tmp_path / "wavs" / "15.8"
    wem_path = audio_root / "champions" / "1·annie" / "1000·base" / "VO" / "123456.wem"

    wav_path = build_wav_output_path(wem_path, audio_root=audio_root, wav_root=wav_root)

    assert wav_path == wav_root / "champions" / "1·annie" / "1000·base" / "VO" / "123456.wav"


def test_resolve_wav_decode_config_returns_none_for_auto() -> None:
    assert resolve_wav_decode_config("auto") is None


@pytest.mark.parametrize(
    ("raw_format", "sample_format"),
    [
        ("pcm16", SampleFormat.PCM16),
        ("pcm24", SampleFormat.PCM24),
        ("pcm32", SampleFormat.PCM32),
        ("float", SampleFormat.FLOAT),
    ],
)
def test_resolve_wav_decode_config_maps_known_formats(raw_format: str, sample_format: SampleFormat) -> None:
    config = resolve_wav_decode_config(raw_format)

    assert config is not None
    assert config.sample_format is sample_format


def test_default_worker_entry_passes_resolved_decode_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    class FakeDecodeResult:
        byte_count = 123

    def fake_decode_to_wav_file(in_path, out_path, *, config=None):
        captured["in_path"] = in_path
        captured["out_path"] = out_path
        captured["config"] = config
        return FakeDecodeResult()

    queue: Queue[Any] = SimpleQueueAdapter()
    monkeypatch.setattr("lol_audio_unpack.runtime.wav._runtime.decode_to_wav_file", fake_decode_to_wav_file)

    job = WavJob(
        wem_path=tmp_path / "sample.wem",
        wav_path=tmp_path / "sample.wav",
        wav_format="pcm24",
    )

    default_worker_entry(job, queue)

    assert captured["config"] is not None
    assert captured["config"].sample_format is SampleFormat.PCM24


class SimpleQueueAdapter:
    """提供与进程队列兼容的最小 put 接口。"""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def put(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


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


def test_finalize_writes_summary_and_failures_reports(tmp_path: Path) -> None:
    options = WavOutputOptions(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1)
    report_root = tmp_path / "reports" / "15.8" / "transcode_wav"
    coordinator = WavTranscodeCoordinator(
        options=options,
        audio_root=tmp_path / "audios" / "15.8",
        wav_root=tmp_path / "wavs" / "15.8",
        report_root=report_root,
        worker_entry=always_fail_worker_entry,
    )

    for index in range(BREAKER_FAILURE_THRESHOLD + 1):
        coordinator.submit_persisted_wem(tmp_path / "audios" / "15.8" / f"{index}.wem")

    coordinator.mark_extract_finished()
    summary = coordinator.finalize()

    summary_path = report_root / "summary.json"
    failures_path = report_root / "failures.jsonl"

    assert summary_path.exists()
    assert failures_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["failed_wav_job_count"] == summary.failed_wav_job_count
    assert payload["skipped_wav_job_count"] == summary.skipped_wav_job_count
    assert len(failures_path.read_text(encoding="utf-8").strip().splitlines()) == summary.failed_wav_job_count


def test_progress_callback_receives_sidecar_lifecycle_snapshots(tmp_path: Path) -> None:
    """协调器应在关键生命周期节点发出结构化进度快照。"""
    snapshots: list[WavSidecarProgressSnapshot] = []
    options = WavOutputOptions(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1)
    coordinator = WavTranscodeCoordinator(
        options=options,
        audio_root=tmp_path / "audios" / "15.8",
        wav_root=tmp_path / "wavs" / "15.8",
        report_root=tmp_path / "reports" / "15.8" / "transcode_wav",
        worker_entry=instant_success_worker_entry,
        progress_callback=snapshots.append,
    )

    coordinator.submit_persisted_wem(tmp_path / "audios" / "15.8" / "sample.wem")
    coordinator.mark_extract_finished()
    summary = coordinator.finalize()

    assert any(snapshot.phase == "submitted" for snapshot in snapshots)
    assert any(snapshot.phase == "draining" and snapshot.extract_finished for snapshot in snapshots)
    assert snapshots[-1].phase == "finalized"
    assert snapshots[-1].completed_wav_job_count == summary.completed_wav_job_count
    assert snapshots[-1].running_wav_job_count == 0
