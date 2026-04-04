"""解包阶段接入 WAV 转码的定向测试。"""

from __future__ import annotations

import inspect
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.runtime.wav import TranscodeProgress
from lol_audio_unpack.runtime.wav import job as wav_job
from lol_audio_unpack.unpack import batch as unpack_batch
from lol_audio_unpack.unpack import entity as unpack_entity
from lol_audio_unpack.utils.run_summary import get_or_create_run_summary

pytestmark = pytest.mark.unit


def test_unpack_wav_bridge_module_is_removed() -> None:
    """解包侧旧 bridge 模块应在收口后被移除。"""
    assert find_spec("lol_audio_unpack.unpack.wav") is None


def test_build_transcode_paths_uses_version_and_optional_job_label(tmp_path: Path) -> None:
    """WAV 路径装配应由 runtime.wav.job 统一负责。"""
    ctx = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        )
    )

    paths = wav_job.build_transcode_paths(ctx=ctx, version="15.8")
    detached_paths = wav_job.build_transcode_paths(ctx=ctx, version="15.8", job_label="cli-test")

    assert paths.audio_root == tmp_path / "audios" / "15.8"
    assert paths.wav_root == tmp_path / "wavs" / "15.8"
    assert paths.report_root == tmp_path / "reports" / "15.8" / "transcode_wav"
    assert detached_paths.report_root == tmp_path / "reports" / "15.8" / "transcode_wav" / "cli-test"


def test_launch_detached_accepts_manifest_recorder_keyword() -> None:
    """launch_detached 的关键字参数应与调用侧保持一致。"""
    assert "manifest_recorder" in inspect.signature(wav_job.launch_detached).parameters


def test_persisted_wem_is_submitted_to_transcode(tmp_path: Path) -> None:
    submitted: list[Path] = []

    class FakeCoordinator:
        def submit(self, wem_path: Path, **_kwargs) -> None:
            submitted.append(wem_path)

    file = SimpleNamespace(save_file=lambda path: Path(path).write_bytes(b"wem-bytes"))
    destination = tmp_path / "audios" / "15.8" / "champions" / "1" / "VO" / "123.wem"

    unpack_entity._persist_wem(
        file,
        destination,
        wav_submitter=FakeCoordinator().submit,
    )

    assert submitted == [destination]


def test_failed_wem_write_is_not_submitted(tmp_path: Path) -> None:
    submitted: list[Path] = []

    def boom(_path: Path) -> None:
        raise OSError("disk full")

    file = SimpleNamespace(save_file=boom)
    destination = tmp_path / "audios" / "15.8" / "champions" / "1" / "VO" / "123.wem"

    with pytest.raises(OSError):
        unpack_entity._persist_wem(
            file,
            destination,
            wav_submitter=submitted.append,
        )

    assert submitted == []


def test_execute_tasks_transcode_submit_error_does_not_fail_main_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = {"unknown_categories": 0, "finish_extract": 0, "finish": 0}

    class FakeCoordinator:
        def __init__(self, **_kwargs) -> None:
            return None

        def submit(self, _wem_path: Path, **_kwargs) -> None:
            raise RuntimeError("submit boom")

        def finish_extract(self) -> None:
            writes["finish_extract"] += 1

        def finish(self) -> SimpleNamespace:
            writes["finish"] += 1
            return SimpleNamespace(
                breaker_open=False,
                breaker_reason=None,
                completed_wav_job_count=0,
                failed_wav_job_count=0,
                skipped_wav_job_count=0,
            )

    def fake_unpack_champion(
        _champion_id: int,
        _reader,
        wad_cache=None,
        cache_lock=None,
        *,
        ctx,
        wav_submitter=None,
    ) -> None:
        _ = (wad_cache, cache_lock, ctx)
        if wav_submitter is not None:
            wav_submitter(tmp_path / "audios" / "15.8" / "champion-1.wem")

    monkeypatch.setattr(unpack_batch, "TranscodeCoordinator", FakeCoordinator)
    monkeypatch.setattr(unpack_batch, "unpack_champion", fake_unpack_champion)

    reader = SimpleNamespace(
        version="15.8",
        write_unknown_categories=lambda: writes.__setitem__("unknown_categories", writes["unknown_categories"] + 1),
    )
    ctx = SimpleNamespace(
        config=SimpleNamespace(dev_mode=False),
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
    )
    wav_output = SimpleNamespace(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1, format="pcm16")

    unpack_batch.execute_tasks(
        [("champion", 1, "测试英雄")],
        reader,
        max_workers=1,
        ctx=ctx,
        wav_output=wav_output,
    )

    summary = get_or_create_run_summary(ctx.runtime_cache)
    assert writes == {"unknown_categories": 1, "finish_extract": 1, "finish": 1}
    assert "extract" in summary.stages
    assert any("内部异常" in note for note in summary.stages["extract"].notes)


def test_execute_tasks_transcode_finish_error_does_not_fail_main_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = {"unknown_categories": 0, "finish_extract": 0}

    class FakeCoordinator:
        def __init__(self, **_kwargs) -> None:
            return None

        def submit(self, _wem_path: Path, **_kwargs) -> None:
            return None

        def finish_extract(self) -> None:
            writes["finish_extract"] += 1

        def finish(self) -> SimpleNamespace:
            raise RuntimeError("finish boom")

    def fake_unpack_champion(
        _champion_id: int,
        _reader,
        wad_cache=None,
        cache_lock=None,
        *,
        ctx,
        wav_submitter=None,
    ) -> None:
        _ = (wad_cache, cache_lock, ctx)
        if wav_submitter is not None:
            wav_submitter(tmp_path / "audios" / "15.8" / "champion-1.wem")

    monkeypatch.setattr(unpack_batch, "TranscodeCoordinator", FakeCoordinator)
    monkeypatch.setattr(unpack_batch, "unpack_champion", fake_unpack_champion)

    reader = SimpleNamespace(
        version="15.8",
        write_unknown_categories=lambda: writes.__setitem__("unknown_categories", writes["unknown_categories"] + 1),
    )
    ctx = SimpleNamespace(
        config=SimpleNamespace(dev_mode=False),
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
    )
    wav_output = SimpleNamespace(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1, format="pcm16")

    unpack_batch.execute_tasks(
        [("champion", 1, "测试英雄")],
        reader,
        max_workers=1,
        ctx=ctx,
        wav_output=wav_output,
    )

    summary = get_or_create_run_summary(ctx.runtime_cache)
    assert writes == {"unknown_categories": 1, "finish_extract": 1}
    assert "extract" in summary.stages
    assert any("内部异常" in note for note in summary.stages["extract"].notes)


def test_execute_tasks_detaches_wav_transcode_into_background_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launches: list[object] = []

    class FakeHandle:
        def __init__(self) -> None:
            self.returncode = None

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 1

    def fake_unpack_champion(
        _champion_id: int,
        _reader,
        wad_cache=None,
        cache_lock=None,
        *,
        ctx,
        wav_submitter=None,
    ) -> None:
        _ = (wad_cache, cache_lock, ctx)
        if wav_submitter is not None:
            wav_submitter(tmp_path / "audios" / "15.8" / "champion-1.wem")

    monkeypatch.setattr(
        unpack_batch,
        "TranscodeCoordinator",
        lambda **_kwargs: pytest.fail("detached 模式不应创建阻塞 coordinator"),
    )
    monkeypatch.setattr(unpack_batch, "unpack_champion", fake_unpack_champion)
    monkeypatch.setattr(
        unpack_batch,
        "launch_detached",
        lambda **kwargs: launches.append(kwargs["manifest_recorder"]) or FakeHandle(),
    )

    reader = SimpleNamespace(
        version="15.8",
        write_unknown_categories=lambda: None,
    )
    ctx = SimpleNamespace(
        config=SimpleNamespace(dev_mode=False),
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
    )
    wav_output = SimpleNamespace(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1, format="pcm16")

    handle = unpack_batch.execute_tasks(
        [("champion", 1, "测试英雄")],
        reader,
        max_workers=1,
        ctx=ctx,
        wav_output=wav_output,
        detach_wav=True,
        wav_job_label="cli-test",
    )

    assert handle is not None
    assert launches
    assert launches[0].manifest_path.name == "cli-test.txt"
    assert launches[0].manifest_path.read_text(encoding="utf-8").strip().endswith("champion-1.wem")


def test_execute_tasks_bridges_wav_progress_to_logs_and_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """主线应把转码进度桥接成日志和结构化进度。"""
    infos: list[str] = []
    progress_events: list[tuple[str, int, int, str]] = []

    class FakeLogger:
        def info(self, message: str, *args) -> None:
            if args:
                message = message.format(*args)
            infos.append(message)

        def warning(self, message: str, *args) -> None:
            if args:
                message = message.format(*args)
            infos.append(message)

        def success(self, message: str, *args) -> None:
            if args:
                message = message.format(*args)
            infos.append(message)

        def error(self, message: str, *args) -> None:
            if args:
                message = message.format(*args)
            infos.append(message)

        def opt(self, **_kwargs):
            return self

        def debug(self, _message: str) -> None:
            return None

    class FakeCoordinator:
        def __init__(self, *, progress_callback=None, **_kwargs) -> None:
            self._progress_callback = progress_callback

        def submit(self, _wem_path: Path, **_kwargs) -> None:
            if self._progress_callback is not None:
                self._progress_callback(
                    TranscodeProgress(
                        phase="submitted",
                        extract_finished=False,
                        produced_wem_count=1,
                        submitted_wav_job_count=1,
                        running_wav_job_count=1,
                        completed_wav_job_count=0,
                        failed_wav_job_count=0,
                        skipped_wav_job_count=0,
                        retried_wav_job_count=0,
                        breaker_open=False,
                        breaker_reason=None,
                    )
                )

        def finish_extract(self) -> None:
            if self._progress_callback is not None:
                self._progress_callback(
                    TranscodeProgress(
                        phase="draining",
                        extract_finished=True,
                        produced_wem_count=1,
                        submitted_wav_job_count=1,
                        running_wav_job_count=1,
                        completed_wav_job_count=0,
                        failed_wav_job_count=0,
                        skipped_wav_job_count=0,
                        retried_wav_job_count=0,
                        breaker_open=False,
                        breaker_reason=None,
                    )
                )

        def finish(self) -> SimpleNamespace:
            if self._progress_callback is not None:
                self._progress_callback(
                    TranscodeProgress(
                        phase="done",
                        extract_finished=True,
                        produced_wem_count=1,
                        submitted_wav_job_count=1,
                        running_wav_job_count=0,
                        completed_wav_job_count=1,
                        failed_wav_job_count=0,
                        skipped_wav_job_count=0,
                        retried_wav_job_count=0,
                        breaker_open=False,
                        breaker_reason=None,
                    )
                )
            return SimpleNamespace(
                breaker_open=False,
                breaker_reason=None,
                completed_wav_job_count=1,
                failed_wav_job_count=0,
                skipped_wav_job_count=0,
            )

    def fake_unpack_champion(
        _champion_id: int,
        _reader,
        wad_cache=None,
        cache_lock=None,
        *,
        ctx,
        wav_submitter=None,
    ) -> None:
        _ = (wad_cache, cache_lock, ctx)
        if wav_submitter is not None:
            wav_submitter(tmp_path / "audios" / "15.8" / "champion-1.wem")

    monkeypatch.setattr(unpack_batch, "logger", FakeLogger())
    monkeypatch.setattr(unpack_batch, "TranscodeCoordinator", FakeCoordinator)
    monkeypatch.setattr(unpack_batch, "unpack_champion", fake_unpack_champion)

    reader = SimpleNamespace(
        version="15.8",
        write_unknown_categories=lambda: None,
    )
    ctx = SimpleNamespace(
        config=SimpleNamespace(dev_mode=False),
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
    )
    wav_output = SimpleNamespace(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1, format="pcm16")

    unpack_batch.execute_tasks(
        [("champion", 1, "测试英雄")],
        reader,
        max_workers=1,
        ctx=ctx,
        progress_callback=lambda entity_type, current, total, message: progress_events.append(
            (entity_type, current, total, message)
        ),
        wav_output=wav_output,
    )

    assert any("WAV 转码已启用" in message for message in infos)
    assert any("WAV 转码" in message for message in infos)
    assert any(entity_type == "wav" and "WAV 转码" in message for entity_type, _, _, message in progress_events)
