"""WAV 转码协调器的定向单元测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pyvgmstream import SampleFormat

from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.runtime.wav import build_output_path, resolve_decode_config
from lol_audio_unpack.runtime.wav import job as wav_job
from lol_audio_unpack.runtime.wav._runtime import Job, run_worker

pytestmark = pytest.mark.unit


def _format_log(message: str, *args: Any) -> str:
    """展开测试中使用的 loguru 占位符消息。"""
    return message.format(*args)


def test_build_output_path_mirrors_audio_tree(tmp_path: Path) -> None:
    audio_root = tmp_path / "audios" / "15.8"
    wav_root = tmp_path / "wavs" / "15.8"
    wem_path = audio_root / "champions" / "1·annie" / "1000·base" / "VO" / "123456.wem"

    wav_path = build_output_path(wem_path, audio_root=audio_root, wav_root=wav_root)

    assert wav_path == wav_root / "champions" / "1·annie" / "1000·base" / "VO" / "123456.wav"


def test_resolve_decode_config_returns_none_for_auto() -> None:
    assert resolve_decode_config("auto") is None


@pytest.mark.parametrize(
    ("raw_format", "sample_format"),
    [
        ("pcm16", SampleFormat.PCM16),
        ("pcm24", SampleFormat.PCM24),
        ("pcm32", SampleFormat.PCM32),
        ("float", SampleFormat.FLOAT),
    ],
)
def test_resolve_decode_config_maps_known_formats(raw_format: str, sample_format: SampleFormat) -> None:
    config = resolve_decode_config(raw_format)

    assert config is not None
    assert config.sample_format is sample_format


def test_run_worker_passes_resolved_decode_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    class FakeDecodeResult:
        byte_count = 123

    def fake_decode_to_wav_file(in_path, out_path, *, config=None):
        captured["in_path"] = in_path
        captured["out_path"] = out_path
        captured["config"] = config
        return FakeDecodeResult()

    queue = SimpleQueueAdapter()
    monkeypatch.setattr("lol_audio_unpack.runtime.wav._runtime.decode_to_wav_file", fake_decode_to_wav_file)

    job = Job(
        wem_path=tmp_path / "sample.wem",
        wav_path=tmp_path / "sample.wav",
        wav_format="pcm24",
    )

    run_worker(job, queue)

    assert captured["config"] is not None
    assert captured["config"].sample_format is SampleFormat.PCM24


class SimpleQueueAdapter:
    """提供与进程队列兼容的最小 put 接口。"""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def put(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


def test_run_tree_uses_transcode_tree_for_version_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """独立 WAV stage 应直接消费当前版本的 audios 根目录。"""
    ctx = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        )
    )
    input_root = tmp_path / "audios" / "15.8"
    input_root.mkdir(parents=True, exist_ok=True)
    (input_root / "sample.wem").write_bytes(b"wem")
    calls: list[tuple[Path, Path]] = []

    def fake_transcode_tree(input_root_arg: Path, output_root_arg: Path, **kwargs):
        calls.append((Path(input_root_arg), Path(output_root_arg)))
        return SimpleNamespace(processed_count=1, failed_count=0, results=())

    monkeypatch.setattr(wav_job, "transcode_tree", fake_transcode_tree)

    payload = wav_job.run_tree(
        ctx=ctx,
        version="15.8",
        wav_output=WavOutputOptions(enabled=True, worker_count=2, timeout_seconds=5, max_retries=3, format="pcm16"),
        job_label="cli-test",
    )

    assert calls == [
        (
            tmp_path / "audios" / "15.8",
            tmp_path / "wavs" / "15.8",
        )
    ]
    assert payload["processed_file_count"] == 1
    assert payload["failed_file_count"] == 0


def test_run_tree_uses_selected_audio_roots_when_provided(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """定向 WAV stage 应只消费显式选中的实体音频目录。"""
    ctx = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        )
    )
    version_root = tmp_path / "audios" / "15.8"
    selected_root = version_root / "champions" / "1-annie"
    selected_root.mkdir(parents=True, exist_ok=True)
    (selected_root / "sample.wem").write_bytes(b"wem")
    ignored_root = version_root / "champions" / "2-olaf"
    ignored_root.mkdir(parents=True, exist_ok=True)
    (ignored_root / "sample.wem").write_bytes(b"wem")
    calls: list[tuple[Path, Path]] = []

    def fake_transcode_tree(input_root_arg: Path, output_root_arg: Path, **kwargs):
        calls.append((Path(input_root_arg), Path(output_root_arg)))
        return SimpleNamespace(processed_count=1, failed_count=0, results=())

    monkeypatch.setattr(wav_job, "transcode_tree", fake_transcode_tree)

    payload = wav_job.run_tree(
        ctx=ctx,
        version="15.8",
        wav_output=WavOutputOptions(enabled=True, worker_count=2, timeout_seconds=5, max_retries=3, format="pcm16"),
        audio_roots=(selected_root,),
    )

    assert calls == [
        (
            selected_root,
            tmp_path / "wavs" / "15.8" / "champions" / "1-annie",
        )
    ]
    assert payload["processed_file_count"] == 1
    assert payload["failed_file_count"] == 0


def test_run_tree_bridges_root_level_progress_to_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """独立 WAV stage 应只向统一回调暴露目标目录级进度。"""
    ctx = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        )
    )
    version_root = tmp_path / "audios" / "15.8"
    first_root = version_root / "champions" / "1-annie"
    second_root = version_root / "maps" / "0-common"
    first_root.mkdir(parents=True, exist_ok=True)
    second_root.mkdir(parents=True, exist_ok=True)
    (first_root / "sample-1.wem").write_bytes(b"wem")
    (second_root / "sample-2.wem").write_bytes(b"wem")
    progress_events: list[tuple[str, int, int, str]] = []

    def fake_transcode_tree(_input_root: Path, _output_root: Path, **kwargs):
        kwargs["progress_callback"](SimpleNamespace(completed_count=2, total_count=3, failed_count=1))
        return SimpleNamespace(processed_count=2, failed_count=1, results=())

    monkeypatch.setattr(wav_job, "transcode_tree", fake_transcode_tree)

    wav_job.run_tree(
        ctx=ctx,
        version="15.8",
        wav_output=WavOutputOptions(enabled=True, worker_count=2, timeout_seconds=5, max_retries=3, format="pcm16"),
        audio_roots=(first_root, second_root),
        progress_callback=lambda entity_type, current, total, message: progress_events.append(
            (entity_type, current, total, message)
        ),
    )

    assert progress_events == [
        (
            "wav",
            0,
            2,
            "正在处理: 1-annie",
        ),
        (
            "wav",
            1,
            2,
            "WAV 转码目录完成：1-annie",
        ),
        (
            "wav",
            1,
            2,
            "正在处理: 0-common",
        ),
        (
            "wav",
            2,
            2,
            "WAV 转码目录完成：0-common",
        ),
    ]


def test_run_tree_logs_internal_file_progress_at_debug_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """文件级 WAV 内部快照只应进入 DEBUG 日志。"""
    ctx = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        )
    )
    input_root = tmp_path / "audios" / "15.8"
    input_root.mkdir(parents=True, exist_ok=True)
    (input_root / "sample.wem").write_bytes(b"wem")
    info_messages: list[str] = []
    debug_messages: list[str] = []
    success_messages: list[str] = []

    def fake_transcode_tree(_input_root: Path, _output_root: Path, **kwargs):
        kwargs["progress_callback"](SimpleNamespace(completed_count=2, total_count=3, failed_count=1))
        return SimpleNamespace(processed_count=2, failed_count=1, results=())

    monkeypatch.setattr(wav_job, "transcode_tree", fake_transcode_tree)
    monkeypatch.setattr(
        wav_job,
        "logger",
        SimpleNamespace(
            info=lambda message, *args: info_messages.append(_format_log(message, *args)),
            debug=lambda message, *args: debug_messages.append(_format_log(message, *args)),
            warning=lambda message, *args: info_messages.append(_format_log(message, *args)),
            success=lambda message, *args: success_messages.append(_format_log(message, *args)),
        ),
    )

    wav_job.run_tree(
        ctx=ctx,
        version="15.8",
        wav_output=WavOutputOptions(enabled=True, worker_count=2, timeout_seconds=5, max_retries=3, format="pcm16"),
    )

    assert debug_messages == ["WAV 转码内部进度：文件 2/3 · 失败 1"]
    assert all("内部进度" not in message for message in info_messages)
    assert any("WAV 转码目录完成：当前版本音频" in message for message in info_messages)
    assert any("WAV 转码完成：成功 2 个，失败 1 个" in message for message in info_messages)
    assert success_messages == []
