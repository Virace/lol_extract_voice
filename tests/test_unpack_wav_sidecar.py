"""解包阶段接入 WAV sidecar 的定向测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack import unpack
from lol_audio_unpack.utils.run_summary import get_or_create_run_summary

pytestmark = pytest.mark.unit


def test_persisted_wem_is_submitted_to_sidecar(tmp_path: Path) -> None:
    submitted: list[Path] = []

    class FakeCoordinator:
        def submit_persisted_wem(self, wem_path: Path, **_kwargs) -> None:
            submitted.append(wem_path)

    file = SimpleNamespace(save_file=lambda path: Path(path).write_bytes(b"wem-bytes"))
    destination = tmp_path / "audios" / "15.8" / "champions" / "1" / "VO" / "123.wem"

    unpack._persist_wem_and_maybe_submit(file, destination, wav_submitter=FakeCoordinator().submit_persisted_wem)

    assert submitted == [destination]


def test_failed_wem_write_is_not_submitted(tmp_path: Path) -> None:
    submitted: list[Path] = []

    def boom(_path: Path) -> None:
        raise OSError("disk full")

    file = SimpleNamespace(save_file=boom)
    destination = tmp_path / "audios" / "15.8" / "champions" / "1" / "VO" / "123.wem"

    with pytest.raises(OSError):
        unpack._persist_wem_and_maybe_submit(file, destination, wav_submitter=submitted.append)

    assert submitted == []


def test_execute_unpack_tasks_sidecar_submit_error_does_not_fail_main_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = {"unknown_categories": 0, "mark_finished": 0, "finalize": 0}

    class FakeCoordinator:
        def __init__(self, **_kwargs) -> None:
            return None

        def submit_persisted_wem(self, _wem_path: Path, **_kwargs) -> None:
            raise RuntimeError("submit boom")

        def mark_extract_finished(self) -> None:
            writes["mark_finished"] += 1

        def finalize(self) -> SimpleNamespace:
            writes["finalize"] += 1
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

    monkeypatch.setattr(unpack, "WavTranscodeCoordinator", FakeCoordinator)
    monkeypatch.setattr(unpack, "unpack_champion", fake_unpack_champion)

    reader = SimpleNamespace(
        version="15.8",
        write_unknown_categories_to_file=lambda: writes.__setitem__("unknown_categories", writes["unknown_categories"] + 1),
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
    wav_output = SimpleNamespace(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1)

    unpack.execute_unpack_tasks(
        [("champion", 1, "测试英雄")],
        reader,
        max_workers=1,
        ctx=ctx,
        wav_output=wav_output,
    )

    summary = get_or_create_run_summary(ctx.runtime_cache)
    assert writes == {"unknown_categories": 1, "mark_finished": 1, "finalize": 1}
    assert "extract" in summary.stages
    assert any("sidecar 内部异常" in note for note in summary.stages["extract"].notes)


def test_execute_unpack_tasks_sidecar_finalize_error_does_not_fail_main_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = {"unknown_categories": 0, "mark_finished": 0}

    class FakeCoordinator:
        def __init__(self, **_kwargs) -> None:
            return None

        def submit_persisted_wem(self, _wem_path: Path, **_kwargs) -> None:
            return None

        def mark_extract_finished(self) -> None:
            writes["mark_finished"] += 1

        def finalize(self) -> SimpleNamespace:
            raise RuntimeError("finalize boom")

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

    monkeypatch.setattr(unpack, "WavTranscodeCoordinator", FakeCoordinator)
    monkeypatch.setattr(unpack, "unpack_champion", fake_unpack_champion)

    reader = SimpleNamespace(
        version="15.8",
        write_unknown_categories_to_file=lambda: writes.__setitem__("unknown_categories", writes["unknown_categories"] + 1),
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
    wav_output = SimpleNamespace(enabled=True, worker_count=1, timeout_seconds=1, max_retries=1)

    unpack.execute_unpack_tasks(
        [("champion", 1, "测试英雄")],
        reader,
        max_workers=1,
        ctx=ctx,
        wav_output=wav_output,
    )

    summary = get_or_create_run_summary(ctx.runtime_cache)
    assert writes == {"unknown_categories": 1, "mark_finished": 1}
    assert "extract" in summary.stages
    assert any("sidecar 内部异常" in note for note in summary.stages["extract"].notes)
