"""验证失败重试的真实范围与解决证据。"""

from dataclasses import replace
from pathlib import Path

import pytest

from lol_audio_unpack.app.audio_scope import AudioScope
from lol_audio_unpack.app.failures import collect_failures, reconcile_failures
from lol_audio_unpack.app.results import EntityResult, FailureDetail, ResultStatus, RunResult, StageResult
from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.runtime.wav.batch import WavBatchResult, WavFailure

pytestmark = pytest.mark.unit


def test_wav_retry_resolves_only_attempted_files(tmp_path: Path) -> None:
    """精确重试只解决已尝试的文件；成功记录不会因其他失败项未重试而丢失。"""
    failed = tuple(
        WavFailure(str(tmp_path / f"{number}.wem"), str(tmp_path / f"{number}.wav"), "decode error")
        for number in (1, 2)
    )
    batch = WavBatchResult(
        "original",
        AudioScope(tmp_path, directories=(".",)),
        tmp_path,
        WavOutputOptions(),
        False,
        1,
        2,
        0,
        failed,
        1,
        tmp_path / "original/summary.json",
    )
    original = RunResult((StageResult("wav", status=ResultStatus.PARTIAL, wav_batches=(batch,)),))
    issues = collect_failures(original, (batch,))
    retried = replace(
        batch,
        operation_id="retry",
        parent_id="original",
        scope=AudioScope(tmp_path, files=("1.wem",)),
        failed_count=0,
        failures=(),
        success_count=1,
    )
    result = RunResult((StageResult("wav", wav_batches=(retried,)),))
    merged = reconcile_failures(issues, result, (retried,), frozenset({issues[0].key}))
    assert [issue.resolved for issue in merged] == [True, False]
    assert issues[0].resolved is False
    assert merged[1].retry_mode == "wav_files"


def test_container_retry_keeps_unknown_units_and_new_file_failure() -> None:
    """解析失败以容器为单位；重读后定位到写入失败时保留原记录并追加文件记录。"""
    detail = FailureDetail(
        "container", "bank.bnk", "unknown parse failure", "1000", "VO", "vo", "hero.wad", "hash", retryable=True
    )
    entity = EntityResult("champion", 1, ResultStatus.FAILED, failures=(detail,))
    issues = collect_failures(RunResult((StageResult.from_entities("extract", (entity,)),)))
    assert issues[0].unit == "container" and issues[0].retry_mode == "extract_bindings"
    file_failure = replace(detail, unit="file", output_path="1000/VO/1.wem", error_message="disk full")
    partial = replace(entity, status=ResultStatus.PARTIAL, failures=(file_failure,), artifacts=("1000/VO/2.wem",))
    merged = reconcile_failures(
        issues, RunResult((StageResult.from_entities("extract", (partial,)),)), (), frozenset({issues[0].key})
    )
    assert merged[0].resolved
    assert merged[1].unit == "file" and not merged[1].resolved
