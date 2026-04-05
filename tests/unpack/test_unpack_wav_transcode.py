"""解包阶段与独立 WAV stage 的定向测试。"""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.runtime.wav import job as wav_job
from lol_audio_unpack.unpack import batch as unpack_batch
from lol_audio_unpack.unpack import entity as unpack_entity

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
    ) -> None:
        _ = (wad_cache, cache_lock, ctx)
        events.append("extract")
        if persisted_wem_callback is not None:
            destination = tmp_path / "audios" / "15.8" / "champions" / "1-annie" / "sample.wem"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"wem")
            persisted_wem_callback(destination)

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

    assert result is None
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
        lambda *_args, **_kwargs: None,
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
    monkeypatch.setattr(
        unpack_batch,
        "execute_tasks",
        lambda tasks, reader, **kwargs: captured.update(tasks=tasks, kwargs=kwargs),
    )

    unpack_batch.unpack_all(
        reader=SimpleNamespace(),
        ctx=SimpleNamespace(),
    )

    assert calls == [("champion", None), ("map", None)]
    assert captured["tasks"] == [("champion", 1, "英雄ID 1"), ("map", 11, "地图ID 11")]


def test_unpack_champions_uses_task_generator_without_ctx_keyword(monkeypatch: pytest.MonkeyPatch) -> None:
    """unpack_champions 不应再向英雄任务生成器传递旧的 ctx 关键字。"""
    calls: list[object] = []

    def fake_generate_champion_tasks(reader, champion_ids=None):
        calls.append(champion_ids)
        return [("champion", 1, "英雄ID 1")]

    monkeypatch.setattr(unpack_batch, "generate_champion_tasks", fake_generate_champion_tasks)
    monkeypatch.setattr(unpack_batch, "execute_tasks", lambda tasks, reader, **kwargs: None)

    unpack_batch.unpack_champions(
        reader=SimpleNamespace(),
        champion_ids=[1],
        ctx=SimpleNamespace(),
    )

    assert calls == [[1]]


def test_unpack_maps_uses_task_generator_without_ctx_keyword(monkeypatch: pytest.MonkeyPatch) -> None:
    """unpack_maps 不应再向地图任务生成器传递旧的 ctx 关键字。"""
    calls: list[object] = []

    def fake_generate_map_tasks(reader, map_ids=None):
        calls.append(map_ids)
        return [("map", 11, "地图ID 11")]

    monkeypatch.setattr(unpack_batch, "generate_map_tasks", fake_generate_map_tasks)
    monkeypatch.setattr(unpack_batch, "execute_tasks", lambda tasks, reader, **kwargs: None)

    unpack_batch.unpack_maps(
        reader=SimpleNamespace(),
        map_ids=[11],
        ctx=SimpleNamespace(),
    )

    assert calls == [[11]]
