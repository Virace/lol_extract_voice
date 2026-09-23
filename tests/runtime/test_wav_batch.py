"""验证项目的范围、冲突、计数与失败重试，不重复验证上游解码算法。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyvgmstream.transcode import BatchTranscodeItemResult, BatchTranscodeSummary

from lol_audio_unpack.app.audio_scope import AudioScope
from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.runtime.wav import batch
from tests.factories import make_wav

pytestmark = pytest.mark.unit


def test_batch_keeps_paths_counts_and_retry_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """重复引用去重、同 ID 不合并；重试只替换失败文件且不覆盖旧报告。"""
    root = tmp_path / "hero"
    output = tmp_path / "wavs"
    keys = ("base/VO/1.wem", "skin/VO/1.wem", "base/VO/2.wem", "base/VO/3.wem")
    for key in keys:
        source = root / key
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(key.encode())
    existing = output / "base/VO/2.wav"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"existing")
    calls: list[tuple[Path, ...]] = []

    def transcode(sources, output_root, *, input_root, **_kwargs):
        calls.append(tuple(sources))
        results = []
        for source in sources:
            target = (output_root / source.relative_to(input_root)).with_suffix(".wav")
            target.parent.mkdir(parents=True, exist_ok=True)
            failed = len(calls) <= options.max_retries and source == root / "skin/VO/1.wem"
            target.write_bytes(b"failed-remnant" if failed else make_wav())
            results.append(BatchTranscodeItemResult(source, target, 0, 0, "unknown format" if failed else None))
        return BatchTranscodeSummary(
            input_root, output_root, len(results), sum(not item.success for item in results), tuple(results)
        )

    monkeypatch.setattr(batch, "transcode_many", transcode)
    options = WavOutputOptions()
    scope = AudioScope(root, directories=(".", "base"), files=(keys[0],), excluded=frozenset({keys[-1]}))
    result = batch.run_batch(scope, output, options=options, report_root=tmp_path / "reports")
    assert (result.success_count, result.failed_count, result.skipped_count) == (1, 1, 1)
    assert set(calls[0]) == {root / keys[0], root / keys[1]}
    assert calls[1:] == [(root / keys[1],)] * (options.max_retries - 1)
    assert result.status == "partial"
    assert not (output / "skin/VO/1.wav").exists()
    assert result.failures[0].output_path == str(output / "skin/VO/1.wav")
    original = result.report_path.read_bytes()
    retried = batch.retry_batch(result)
    assert calls[options.max_retries] == (root / keys[1],)
    assert retried.status == "success"
    assert retried.parent_id == result.operation_id
    assert retried.report_path != result.report_path
    assert result.report_path.read_bytes() == original
    assert existing.read_bytes() == b"existing"
    assert (output / "skin/VO/1.wav").read_bytes() == make_wav()
    assert not (output / "base/VO/3.wav").exists()
    assert json.loads(original)["failed_count"] == 1
    completed_calls = len(calls)
    repeated = batch.run_batch(scope, output, options=WavOutputOptions(), report_root=tmp_path / "reports")
    assert (repeated.success_count, repeated.skipped_count) == (0, 3)
    assert len(calls) == completed_calls


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("failure", ["read", "decode", "validate", "publish"])
def test_file_task_recovers_without_switching_backend(tmp_path, monkeypatch, external, failure):
    """偶发失败重置完整文件任务，已成功文件、后端、预检与最终报告保持稳定。"""
    root = tmp_path / "audio"
    root.mkdir()
    sources = [root / "1.wem", root / "2.wem"]
    for source in sources:
        source.write_bytes(source.name.encode())
    calls, probes, snapshots = [], [], []
    failed = False

    def fail_once(stage):
        nonlocal failed
        if failure == stage and not failed:
            failed = True
            raise PermissionError("temporarily occupied")

    identify = batch.WavCache.identify
    publish = batch.replace_file

    def read(cache, source):
        if source == sources[1]:
            fail_once("read")
        return identify(cache, source)

    def deliver(output, writer, **kwargs):
        if output.name == "2.wav":
            fail_once("publish")
        return publish(output, writer, **kwargs)

    def convert(pending, destination, *, input_root, **kwargs):
        calls.append(tuple(pending))
        items = []
        for source in pending:
            output = destination / source.relative_to(input_root).with_suffix(".wav")
            output.parent.mkdir(parents=True, exist_ok=True)
            error = None
            try:
                if source == sources[1]:
                    fail_once("decode")
                    fail_once("validate")
            except PermissionError as exc:
                output.write_bytes(b"partial")
                error = str(exc) if failure == "decode" else None
            else:
                output.write_bytes(make_wav())
            items.append(BatchTranscodeItemResult(source, output, 0, output.stat().st_size, error))
        callback = kwargs["progress" if external else "progress_callback"]
        failed_count = sum(not item.success for item in items)
        callback(batch.BatchTranscodeProgress(len(items), len(items), failed_count))
        return BatchTranscodeSummary(input_root, destination, len(items), failed_count, tuple(items))

    def wrong_backend(*args, **kwargs):
        pytest.fail("任务重试不得切换后端")

    monkeypatch.setattr(batch.WavCache, "identify", read)
    monkeypatch.setattr(batch, "replace_file", deliver)
    monkeypatch.setattr(batch, "require_tool", lambda *args, **kwargs: probes.append(kwargs))
    monkeypatch.setattr(batch, "transcode_external", convert if external else wrong_backend)
    monkeypatch.setattr(batch, "transcode_many", wrong_backend if external else convert)
    options = WavOutputOptions(backend_path="vgmstream-cli.exe" if external else None)
    result = batch.run_batch(
        AudioScope(root, directories=(".",)),
        tmp_path / "out",
        options=options,
        report_root=tmp_path / "reports",
        progress=snapshots.append,
    )

    assert failed
    assert result.status == "success"
    assert (result.success_count, result.failed_count, result.skipped_count) == (2, 0, 0)
    assert result.failures == ()
    assert len(probes) == 1 and probes[0]["path"] == options.backend_path
    assert sum(sources[0] in call for call in calls) == 1
    assert calls[-1] == (sources[1],)
    assert all((tmp_path / "out" / source.with_suffix(".wav").name).read_bytes() == make_wav() for source in sources)
    assert snapshots[-1] == batch.BatchTranscodeProgress(2, 2, 0)
    assert all(snapshot.total_count == len(sources) for snapshot in snapshots)
    assert [item.completed_count for item in snapshots] == sorted(item.completed_count for item in snapshots)
    assert all(item.completed_count < len(sources) for item in snapshots[:-1])
    assert list((tmp_path / "reports").glob("*/summary.json")) == [result.report_path]
    assert json.loads(result.report_path.read_text(encoding="utf-8"))["success_count"] == len(sources)


@pytest.mark.parametrize("crash", [False, True])
def test_failed_overwrite_preserves_previous_wav(tmp_path: Path, monkeypatch, crash: bool) -> None:
    """失败或中断都不发布半成品，也不能损坏用户之前成功生成的 WAV。"""
    source = tmp_path / "audio/1.wem"
    source.parent.mkdir()
    source.write_bytes(b"wem")
    destination = tmp_path / "wavs/1.wav"
    destination.parent.mkdir()
    destination.write_bytes(b"previous wav")

    def transcode(sources, output_root, **_kwargs):
        """模拟写入部分数据后失败，覆盖正式文件的责任仍由本项目承担。"""
        output = output_root / "1.wav"
        output.write_bytes(b"partial")
        if crash:
            raise RuntimeError("interrupted")
        failed = BatchTranscodeItemResult(sources[0], output, 0, 0, "write failed")
        return BatchTranscodeSummary(source.parent, output_root, 1, 1, (failed,))

    monkeypatch.setattr(batch, "transcode_many", transcode)
    result = batch.run_batch(
        AudioScope(source.parent, files=("1.wem",)),
        destination.parent,
        options=WavOutputOptions(),
        report_root=tmp_path / "reports",
        overwrite=True,
    )

    assert result.status == "failed"
    assert destination.read_bytes() == b"previous wav"
    assert set(destination.parent.iterdir()) == {destination}


def test_missing_selected_source_is_failure_even_with_old_output(tmp_path: Path) -> None:
    """精确输入消失不能被旧输出的默认跳过吞掉。"""
    (tmp_path / "1.wav").write_bytes(b"old")
    result = batch.run_batch(
        AudioScope(tmp_path, files=("1.wem",)),
        tmp_path,
        options=WavOutputOptions(),
        report_root=tmp_path / "reports",
    )
    assert (result.success_count, result.failed_count, result.skipped_count) == (0, 1, 0)
    assert result.status == "failed"
    assert result.retry_scope().files == ("1.wem",)


def test_batch_failure_does_not_invent_exact_failed_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """上游异常没有可靠终态时，只记录未确认范围，不伪造逐项失败。"""
    (tmp_path / "1.wem").write_bytes(b"wem")

    def fail(*_args, **_kwargs):
        raise RuntimeError("worker disappeared")

    monkeypatch.setattr(batch, "transcode_many", fail)
    result = batch.run_batch(
        AudioScope(tmp_path, files=("1.wem",)),
        tmp_path / "out",
        options=WavOutputOptions(),
        report_root=tmp_path / "reports",
    )
    assert result.status == "failed"
    assert result.unconfirmed_count == 1
    assert result.failures == ()
    with pytest.raises(ValueError, match="没有可重试"):
        batch.retry_batch(result)


@pytest.mark.parametrize("key", ["../other/1.wem", "/other/1.wem", "C:/other/1.wem"])
def test_scope_rejects_paths_outside_entity(tmp_path: Path, key: str) -> None:
    """选择合同拒绝跨实体路径。"""
    with pytest.raises(ValueError):
        AudioScope(tmp_path, files=(key,))


def test_report_failure_preserves_success_and_exact_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """报告目录不可写时，已处理结果仍能用于详情和精确重试。"""
    source = tmp_path / "1.wem"
    source.write_bytes(b"wem")

    def transcode(sources, output_root, **_kwargs):
        item = BatchTranscodeItemResult(source, output_root / "1.wav", 0, 0, "decode error")
        return BatchTranscodeSummary(tmp_path, output_root, 1, 1, (item,))

    def fail_report(_result):
        raise PermissionError("report directory denied")

    monkeypatch.setattr(batch, "transcode_many", transcode)
    monkeypatch.setattr(batch, "_write_result", fail_report)
    result = batch.run_batch(
        AudioScope(tmp_path, files=("1.wem",)),
        tmp_path / "out",
        options=WavOutputOptions(),
        report_root=tmp_path / "reports",
    )
    assert result.failed_count == 1 and result.report_error
    assert result.retry_scope().files == ("1.wem",)
