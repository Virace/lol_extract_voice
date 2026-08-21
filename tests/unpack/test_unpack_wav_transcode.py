"""解包阶段与独立 WAV stage 的定向测试。"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.app.results import ResultStatus, StageResult
from lol_audio_unpack.runtime.wav import job as wav_job
from lol_audio_unpack.unpack import batch as unpack_batch
from lol_audio_unpack.unpack import entity as unpack_entity
from lol_audio_unpack.unpack.stats import StageResult as UnpackStageResult

pytestmark = pytest.mark.unit


def _fake_stats(status: UnpackStageResult = UnpackStageResult.SUCCESS) -> SimpleNamespace:
    return SimpleNamespace(overall_result=status, get_simple_summary=lambda: f"解包状态: {status.value}")


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
    labeled_paths = wav_job.build_transcode_paths(ctx=ctx, version="15.8", job_label="cli-test")

    assert paths.audio_root == tmp_path / "audios" / "15.8"
    assert paths.wav_root == tmp_path / "wavs" / "15.8"
    assert paths.report_root == tmp_path / "reports" / "15.8" / "transcode_wav"
    assert labeled_paths.report_root == tmp_path / "reports" / "15.8" / "transcode_wav" / "cli-test"


def test_persisted_wem_callback_runs_after_successful_write(tmp_path: Path) -> None:
    """WEM 成功落盘后应只触发通用 persisted callback。"""
    persisted: list[Path] = []
    file = SimpleNamespace(save_file=lambda path: Path(path).write_bytes(b"wem-bytes"))
    destination = tmp_path / "audios" / "15.8" / "champions" / "1" / "VO" / "123.wem"

    unpack_entity._persist_wem(
        file,
        destination,
        persisted_wem_callback=persisted.append,
    )

    assert persisted == [destination]


def test_failed_wem_write_does_not_trigger_persisted_callback(tmp_path: Path) -> None:
    """WEM 写盘失败时不应提前记录 persisted callback。"""
    persisted: list[Path] = []

    def boom(_path: Path) -> None:
        raise OSError("disk full")

    file = SimpleNamespace(save_file=boom)
    destination = tmp_path / "audios" / "15.8" / "champions" / "1" / "VO" / "123.wem"

    with pytest.raises(OSError):
        unpack_entity._persist_wem(
            file,
            destination,
            persisted_wem_callback=persisted.append,
        )

    assert persisted == []


def test_execute_tasks_keeps_extract_flow_without_wav_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extract 批处理不应再在内部驱动 WAV sidecar。"""
    events: list[object] = []
    persisted: list[Path] = []

    def fake_unpack_champion(
        _champion_id: int,
        _reader,
        wad_cache=None,
        cache_lock=None,
        *,
        ctx,
        persisted_wem_callback=None,
        persisted_artifact_callback=None,
    ) -> SimpleNamespace:
        _ = (wad_cache, cache_lock, ctx)
        events.append("extract")
        if persisted_wem_callback is not None:
            destination = tmp_path / "audios" / "15.8" / "champions" / "1-annie" / "sample.wem"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"wem")
            persisted_wem_callback(destination)
        if persisted_artifact_callback is not None:
            lobby_path = tmp_path / "audios" / "15.8" / "champions" / "1-annie" / "lobby" / "ban.ogg"
            lobby_path.parent.mkdir(parents=True, exist_ok=True)
            lobby_path.write_bytes(b"ogg")
            persisted_artifact_callback(lobby_path)
        return _fake_stats()

    monkeypatch.setattr(unpack_batch, "unpack_champion", fake_unpack_champion)

    reader = SimpleNamespace(
        version="15.8",
        write_unknown_categories=lambda: events.append("write_unknown_categories"),
    )
    ctx = SimpleNamespace(
        config=SimpleNamespace(dev_mode=False),
        runtime_cache={},
    )

    result = unpack_batch.execute_tasks(
        [("champion", 1, "测试英雄")],
        reader,
        max_workers=1,
        ctx=ctx,
        persisted_wem_callback=persisted.append,
    )

    assert result.stage == "extract"
    assert result.status is ResultStatus.SUCCESS
    assert result.success_count == 1
    assert result.entities[0].artifacts == (
        str(persisted[0]),
        str(tmp_path / "audios" / "15.8" / "champions" / "1-annie" / "lobby" / "ban.ogg"),
    )
    assert events == ["extract", "write_unknown_categories"]
    assert persisted == [tmp_path / "audios" / "15.8" / "champions" / "1-annie" / "sample.wem"]


def test_execute_tasks_emits_running_entity_progress_before_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extract 批处理应先发出当前实体的运行中进度。"""
    progress_events: list[tuple[str, int, int, str]] = []

    monkeypatch.setattr(
        unpack_batch,
        "unpack_champion",
        lambda *_args, **_kwargs: _fake_stats(),
    )

    reader = SimpleNamespace(
        version="15.8",
        write_unknown_categories=lambda: None,
    )
    ctx = SimpleNamespace(
        config=SimpleNamespace(dev_mode=False),
        runtime_cache={},
    )

    unpack_batch.execute_tasks(
        [("champion", 1, "测试英雄")],
        reader,
        max_workers=1,
        ctx=ctx,
        progress_callback=lambda entity_type, current, total, message: progress_events.append(
            (entity_type, current, total, message)
        ),
    )

    assert progress_events == [
        ("champion", 0, 1, "正在处理: 测试英雄"),
        ("champion", 1, 1, "测试英雄 解包完成"),
    ]


def test_execute_tasks_reports_partial_stats_as_partial_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    """内部 warning 统计不得通过进度回调伪装成完整成功。"""
    progress_events: list[str] = []
    monkeypatch.setattr(
        unpack_batch,
        "unpack_champion",
        lambda *_args, **_kwargs: _fake_stats(UnpackStageResult.WARNING),
    )
    reader = SimpleNamespace(write_unknown_categories=lambda: None)
    ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={})

    result = unpack_batch.execute_tasks(
        [("champion", 1, "测试英雄")],
        reader,
        max_workers=1,
        ctx=ctx,
        progress_callback=lambda _entity_type, _current, _total, message: progress_events.append(message),
    )

    assert result.status is ResultStatus.PARTIAL
    assert progress_events[-1] == "测试英雄 解包部分完成"


def test_execute_tasks_returns_success_noop_for_empty_tasks() -> None:
    """空任务列表是合法 no-op，不应被误报为 warning 或失败。"""
    reader = SimpleNamespace(write_unknown_categories=lambda: pytest.fail("空任务不应写入未知分类"))
    ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={})

    result = unpack_batch.execute_tasks([], reader, ctx=ctx)

    assert result.status is ResultStatus.SUCCESS
    assert result.total_count == 0
    assert result.note == "没有任何任务需要执行"


def test_execute_tasks_propagates_unknown_category_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """批处理基础设施写入失败必须交给 facade，不能降级为实体 partial。"""
    monkeypatch.setattr(unpack_batch, "unpack_champion", lambda *_args, **_kwargs: _fake_stats())
    reader = SimpleNamespace(
        write_unknown_categories=lambda: (_ for _ in ()).throw(OSError("unknown categories write failed"))
    )
    ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={})

    with pytest.raises(OSError, match="unknown categories write failed"):
        unpack_batch.execute_tasks([("champion", 1, "测试英雄")], reader, max_workers=1, ctx=ctx)


def test_execute_tasks_propagates_keyboard_interrupt_without_starting_later_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取消必须跳出批处理，不能被转写为实体失败。"""
    started: list[int] = []

    def interrupt(champion_id: int, *_args, **_kwargs) -> None:
        started.append(champion_id)
        raise KeyboardInterrupt

    monkeypatch.setattr(unpack_batch, "unpack_champion", interrupt)
    reader = SimpleNamespace(write_unknown_categories=lambda: pytest.fail("取消后不应写入未知分类"))
    ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={})

    with pytest.raises(KeyboardInterrupt):
        unpack_batch.execute_tasks(
            [("champion", 1, "英雄 1"), ("champion", 2, "英雄 2")],
            reader,
            max_workers=1,
            ctx=ctx,
        )

    assert started == [1]


def test_execute_tasks_returns_input_ordered_results_for_mixed_entity_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """批处理应按输入顺序返回 success、failed 与 partial 实体结果。"""
    failed_id = 2
    delays = {1: 0.03, failed_id: 0.0, 3: 0.01}

    def fake_unpack_champion(champion_id: int, *_args, **kwargs):
        time.sleep(delays[champion_id])
        destination = tmp_path / f"{champion_id}.wem"
        destination.write_bytes(b"wem")
        kwargs["persisted_wem_callback"](destination)
        if champion_id == failed_id:
            raise OSError("disk full")
        status = UnpackStageResult.SUCCESS if champion_id == 1 else UnpackStageResult.WARNING
        return SimpleNamespace(
            overall_result=status,
            get_simple_summary=lambda: f"英雄 {champion_id} 的内部统计",
        )

    monkeypatch.setattr(unpack_batch, "unpack_champion", fake_unpack_champion)
    reader = SimpleNamespace(version="15.8", write_unknown_categories=lambda: None)
    ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={})

    result = unpack_batch.execute_tasks(
        [
            ("champion", 1, "英雄 1"),
            ("champion", 2, "英雄 2"),
            ("champion", 3, "英雄 3"),
        ],
        reader,
        max_workers=3,
        ctx=ctx,
    )

    assert result.status is ResultStatus.PARTIAL
    assert [entity.entity_id for entity in result.entities] == [1, 2, 3]
    assert [entity.status for entity in result.entities] == [
        ResultStatus.SUCCESS,
        ResultStatus.FAILED,
        ResultStatus.PARTIAL,
    ]
    assert [entity.artifacts for entity in result.entities] == [
        (str(tmp_path / "1.wem"),),
        (str(tmp_path / "2.wem"),),
        (str(tmp_path / "3.wem"),),
    ]
    assert result.entities[1].error_type == "OSError"


def test_execute_tasks_reports_unknown_entity_type_as_stage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未知实体类型必须在排队前成为 stage 失败，而非实体级部分失败。"""
    dispatched: list[int] = []
    monkeypatch.setattr(
        unpack_batch,
        "unpack_champion",
        lambda entity_id, *_args, **_kwargs: dispatched.append(entity_id),
    )
    reader = SimpleNamespace(version="15.8", write_unknown_categories=lambda: None)
    ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={})

    result = unpack_batch.execute_tasks(
        [("champion", 1, "英雄 1"), ("unknown", 2, "未知实体")],
        reader,
        max_workers=1,
        ctx=ctx,
    )

    assert result.status is ResultStatus.FAILED
    assert result.entities == ()
    assert result.error_type == "ValueError"
    assert dispatched == []


def test_unpack_all_uses_task_generators_without_ctx_keyword(monkeypatch: pytest.MonkeyPatch) -> None:
    """unpack_all 不应再向任务生成器传递旧的 ctx 关键字。"""
    calls: list[tuple[str, object]] = []

    def fake_generate_champion_tasks(reader, champion_ids=None):
        calls.append(("champion", champion_ids))
        return [("champion", 1, "英雄ID 1")]

    def fake_generate_map_tasks(reader, map_ids=None):
        calls.append(("map", map_ids))
        return [("map", 11, "地图ID 11")]

    monkeypatch.setattr(unpack_batch, "generate_champion_tasks", fake_generate_champion_tasks)
    monkeypatch.setattr(unpack_batch, "generate_map_tasks", fake_generate_map_tasks)

    captured: dict[str, object] = {}
    expected = StageResult.from_entities("extract", ())
    monkeypatch.setattr(
        unpack_batch,
        "execute_tasks",
        lambda tasks, reader, **kwargs: (captured.update(tasks=tasks, kwargs=kwargs), expected)[1],
    )

    result = unpack_batch.unpack_all(
        reader=SimpleNamespace(),
        ctx=SimpleNamespace(),
    )

    assert calls == [("champion", None), ("map", None)]
    assert captured["tasks"] == [("champion", 1, "英雄ID 1"), ("map", 11, "地图ID 11")]
    assert result is expected


def test_unpack_champions_uses_task_generator_without_ctx_keyword(monkeypatch: pytest.MonkeyPatch) -> None:
    """unpack_champions 不应再向英雄任务生成器传递旧的 ctx 关键字。"""
    calls: list[object] = []

    def fake_generate_champion_tasks(reader, champion_ids=None):
        calls.append(champion_ids)
        return [("champion", 1, "英雄ID 1")]

    expected = StageResult.from_entities("extract", ())
    monkeypatch.setattr(unpack_batch, "generate_champion_tasks", fake_generate_champion_tasks)
    monkeypatch.setattr(unpack_batch, "execute_tasks", lambda tasks, reader, **kwargs: expected)

    result = unpack_batch.unpack_champions(
        reader=SimpleNamespace(),
        champion_ids=[1],
        ctx=SimpleNamespace(),
    )

    assert calls == [[1]]
    assert result is expected


def test_unpack_maps_uses_task_generator_without_ctx_keyword(monkeypatch: pytest.MonkeyPatch) -> None:
    """unpack_maps 不应再向地图任务生成器传递旧的 ctx 关键字。"""
    calls: list[object] = []

    def fake_generate_map_tasks(reader, map_ids=None):
        calls.append(map_ids)
        return [("map", 11, "地图ID 11")]

    expected = StageResult.from_entities("extract", ())
    monkeypatch.setattr(unpack_batch, "generate_map_tasks", fake_generate_map_tasks)
    monkeypatch.setattr(unpack_batch, "execute_tasks", lambda tasks, reader, **kwargs: expected)

    result = unpack_batch.unpack_maps(
        reader=SimpleNamespace(),
        map_ids=[11],
        ctx=SimpleNamespace(),
    )

    assert calls == [[11]]
    assert result is expected
