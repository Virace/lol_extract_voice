"""执行中心本地任务编排回归测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.gui.window as window_module
from lol_audio_unpack.app.resource_pack import ResourcePackWadRef, build_resource_pack_key
from lol_audio_unpack.app.results import EntityResult, ResultStatus, StageResult
from lol_audio_unpack.gui.service import task_runner
from lol_audio_unpack.gui.shared_data import SharedDataRepairScope
from lol_audio_unpack.gui.task_models import (
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.window import _prepare_shared_entity_data

EXPECTED_CONTEXT_COUNT_WITH_UPDATE = 2
PREPARE_GENERATION = 3


def _stage(stage: str) -> StageResult:
    if stage == "update":
        return StageResult(stage, status=ResultStatus.SUCCESS)
    return StageResult.from_entities(
        stage,
        (
            EntityResult(
                "champion" if stage != "wav" else "wav_batch",
                1,
                ResultStatus.SUCCESS,
                artifacts=(f"{stage}.artifact",),
            ),
        ),
    )


def _entity_stage(
    stage: str,
    *entities: tuple[str, int, ResultStatus, tuple[str, ...]],
) -> StageResult:
    """构造带明确实体落盘证据的阶段结果。"""
    return StageResult.from_entities(
        stage,
        (
            EntityResult(entity_type, entity_id, status, artifacts=artifacts)
            for entity_type, entity_id, status, artifacts in entities
        ),
    )


def _build_task(  # noqa: PLR0913
    *,
    run_update: bool = False,
    run_extract: bool = True,
    run_mapping: bool = True,
    wav_enabled: bool = False,
    champion_ids: tuple[int, ...] | None = None,
    special_targets: tuple[str, ...] = (),
    resource_pack_wads: tuple[ResourcePackWadRef, ...] = (),
) -> QueuedExecutionTask:
    return QueuedExecutionTask(
        task_id=1,
        summary="test",
        draft=ExecutionTaskDraft(
            source="manual_input",
            source_summary="manual",
            context_input=AppContextInputSnapshot(
                settings=(
                    ("GAME_PATH", "game"),
                    ("OUTPUT_PATH", "output"),
                    ("GAME_REGION", "zh_CN"),
                )
            ),
            task_params=ExecutionTaskParamsSnapshot(
                champion_ids=champion_ids,
                special_targets=special_targets,
                resource_pack_wads=resource_pack_wads,
                run_update=run_update,
                run_extract=run_extract,
                run_mapping=run_mapping,
                wav_enabled=wav_enabled,
            ),
        ),
    )


class _ReadyMapBanksReader:
    """提供已就绪地图 banks 的轻量测试读取器。"""

    def __init__(self) -> None:
        self.requested_map_ids: list[int] = []

    def get_maps(self) -> list[dict]:
        return [{"id": 11}]

    def get_map_banks(self, map_id: int) -> dict:
        self.requested_map_ids.append(map_id)
        return {"banks": {"VO": [["map.wpk"]]}}


def _install_fake_runtime(monkeypatch, tmp_path: Path, app_cls: type) -> None:
    """为结果状态测试安装最小运行时上下文与门面。"""
    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
        config=SimpleNamespace(),
    )
    monkeypatch.setattr(task_runner, "create_app_context", lambda *, settings: runtime_context)
    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", app_cls)


def test_prepare_shared_entity_data_passes_local_settings_to_app_context(monkeypatch) -> None:
    captured: dict[str, str | bool] = {}
    update_calls = []

    class _FakeApp:
        def __init__(self, _app_context) -> None:
            pass

        def update(self, options, *, target: str, progress_callback):
            update_calls.append((options, target, progress_callback))
            return StageResult("update", status=ResultStatus.SUCCESS)

    def _fake_create_app_context(*, settings):
        captured.update(settings)
        return object()

    monkeypatch.setattr(window_module, "create_app_context", _fake_create_app_context)
    monkeypatch.setattr(window_module, "LolAudioUnpackApp", _FakeApp)

    def progress_callback(_progress) -> None:
        pass

    result = _prepare_shared_entity_data(
        {"GAME_PATH": "game"},
        generation=PREPARE_GENERATION,
        scope=SharedDataRepairScope(full=False, champion_ids=(1,)),
        force_update=True,
        progress_callback=progress_callback,
    )

    assert captured == {"GAME_PATH": "game"}
    options, target, callback = update_calls[0]
    assert target == "all"
    assert options.champion_ids == (1,)
    assert options.map_ids is None
    assert options.force_update is True
    assert callback is progress_callback
    assert result.generation == PREPARE_GENERATION
    assert result.stage_result.status is ResultStatus.SUCCESS


def test_run_execution_task_runs_stages_in_order_and_reuses_runtime_context(monkeypatch, tmp_path: Path) -> None:
    """完整任务应隔离强制更新，并让后续阶段复用同一运行时上下文。"""
    task = _build_task(run_update=True, wav_enabled=True)
    events: list[object] = []
    context_settings: list[dict[str, object]] = []
    app_instances = []
    reader_owners = []
    reader = _ReadyMapBanksReader()

    def _fail_exception(message: str) -> None:
        pytest.fail(message)

    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
        config=SimpleNamespace(),
    )

    monkeypatch.setattr(
        task_runner,
        "logger",
        SimpleNamespace(
            info=lambda _message: None,
            debug=lambda _message: None,
            success=lambda _message: None,
            exception=_fail_exception,
        ),
    )

    def _create_app_context(*, settings):
        context_settings.append(settings)
        return runtime_context

    monkeypatch.setattr(task_runner, "create_app_context", _create_app_context)

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context
            app_instances.append(self)

        def _get_reader(self) -> _ReadyMapBanksReader:
            reader_owners.append(self)
            return reader

        def update(self, _options, *, target: str) -> StageResult:
            assert target == "all"
            events.append("update")
            return _stage("update")

        def extract(self, options, **_kwargs) -> StageResult:
            assert options.wav_output.enabled is True
            events.append("extract")
            return _stage("extract")

        def transcode_wav(self, options, **_kwargs) -> StageResult:
            assert options.wav_output.enabled is True
            events.append("wav")
            return _stage("wav")

        def mapping(self, _options, **_kwargs) -> StageResult:
            events.append("mapping")
            return _stage("mapping")

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert events == ["update", "extract", "wav", "mapping"]
    assert result.run_result is not None
    assert result.run_result.status is ResultStatus.SUCCESS
    assert [stage.stage for stage in result.run_result.stages] == ["update", "extract", "wav", "mapping"]
    assert reader_owners == [app_instances[-1]]
    assert reader.requested_map_ids == [11]
    assert len(context_settings) == EXPECTED_CONTEXT_COUNT_WITH_UPDATE
    assert all(settings["GAME_PATH"] == "game" for settings in context_settings)


def test_run_execution_task_reports_partial_and_only_completes_productive_stages(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """部分成功必须保留 warning 终态，且只记录有落盘证据的阶段。"""
    task = _build_task(
        run_mapping=False,
        champion_ids=(1, 2),
    )

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, _options, **_kwargs) -> StageResult:
            return _entity_stage(
                "extract",
                ("champion", 1, ResultStatus.SUCCESS, ("audios/1/101.wem",)),
                ("champion", 2, ResultStatus.FAILED, ()),
            )

    _install_fake_runtime(monkeypatch, tmp_path, FakeApp)
    progress_events = []
    signals = SimpleNamespace(progress=SimpleNamespace(emit=progress_events.append))

    result = task_runner.run_execution_task(task, signals)

    assert result.run_result.status is ResultStatus.PARTIAL
    assert result.completed_steps == ("音频解包",)
    assert result.summary.startswith("部分完成：")
    assert progress_events[-1].stage_finished is True
    assert progress_events[-1].current < progress_events[-1].total


def test_run_execution_task_summary_separates_stages_and_explains_issue(monkeypatch, tmp_path: Path) -> None:
    """一个英雄跨阶段执行时，通知必须保留阶段归属与实际错误原因。"""
    task = _build_task(champion_ids=(1,))

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, _options, **_kwargs) -> StageResult:
            return StageResult.from_entities(
                "extract",
                (
                    EntityResult(
                        "champion",
                        1,
                        ResultStatus.PARTIAL,
                        entity_name="安妮",
                        error_message="voice.wpk 读取失败",
                        artifacts=("audios/1/101.wem",),
                    ),
                ),
            )

        def mapping(self, _options, **_kwargs) -> StageResult:
            return _stage("mapping")

    _install_fake_runtime(monkeypatch, tmp_path, FakeApp)
    progress = []
    signals = SimpleNamespace(progress=SimpleNamespace(emit=progress.append))
    result = task_runner.run_execution_task(task, signals)

    assert result.run_result.status is ResultStatus.PARTIAL
    assert "音频解包部分完成（安妮：voice.wpk 读取失败）" in result.summary
    assert "事件映射完成" in result.summary
    extract_progress = next(item for item in progress if item.stage_key == "extract" and item.stage_finished)
    assert "voice.wpk 读取失败" in extract_progress.message


def test_run_execution_task_stops_dependencies_after_failed_update(monkeypatch, tmp_path: Path) -> None:
    """前置更新失败后不得再启动依赖的解包与映射阶段。"""
    task = _build_task(run_update=True, champion_ids=(1,))
    events: list[str] = []

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def update(self, _options, *, target: str) -> StageResult:
            assert target == "skin"
            events.append("update")
            return StageResult.from_error("update", RuntimeError("data update failed"))

        def extract(self, _options, **_kwargs) -> StageResult:
            pytest.fail("更新失败后不应执行 extract")

        def mapping(self, _options, **_kwargs) -> StageResult:
            pytest.fail("更新失败后不应执行 mapping")

    _install_fake_runtime(monkeypatch, tmp_path, FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert events == ["update"]
    assert [stage.stage for stage in result.run_result.stages] == ["update"]
    assert result.run_result.status is ResultStatus.FAILED
    assert result.completed_steps == ()
    assert result.summary.startswith("执行失败：")


def test_run_execution_task_does_not_complete_partial_update_without_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """强制更新只有 success 可免产物证据，partial 不能伪装为已完成步骤。"""
    task = _build_task(
        run_update=True,
        run_extract=False,
        run_mapping=False,
    )

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def update(self, _options, *, target: str) -> StageResult:
            assert target == "all"
            return StageResult("update", status=ResultStatus.PARTIAL)

    _install_fake_runtime(monkeypatch, tmp_path, FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert result.run_result.status is ResultStatus.PARTIAL
    assert result.completed_steps == ()
    assert "本轮没有确认的新产物" in result.summary


def test_run_execution_task_skips_wav_after_failed_extract_but_runs_mapping(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """解包全失败只阻止 WAV，独立 mapping 仍应继续并使整轮保持 partial。"""
    task = _build_task(
        wav_enabled=True,
        champion_ids=(1,),
    )
    events: list[str] = []

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, _options, **_kwargs) -> StageResult:
            events.append("extract")
            return _entity_stage("extract", ("champion", 1, ResultStatus.FAILED, ()))

        def transcode_wav(self, _options, **_kwargs) -> StageResult:
            pytest.fail("解包全失败后不应执行 WAV")

        def mapping(self, _options, **_kwargs) -> StageResult:
            events.append("mapping")
            return _entity_stage(
                "mapping",
                ("champion", 1, ResultStatus.SUCCESS, ("hashes/1.msgpack",)),
            )

    _install_fake_runtime(monkeypatch, tmp_path, FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert events == ["extract", "mapping"]
    assert [stage.stage for stage in result.run_result.stages] == ["extract", "mapping"]
    assert result.run_result.status is ResultStatus.PARTIAL
    assert result.completed_steps == ("事件映射",)


def test_run_execution_task_limits_wav_to_successful_extract_artifacts(monkeypatch, tmp_path: Path) -> None:
    """解包部分成功后，WAV 只消费有落盘证据的成功实体。"""
    task = _build_task(
        run_mapping=False,
        wav_enabled=True,
        champion_ids=(1, 2),
    )
    wav_targets: list[tuple[int, ...] | None] = []

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, _options, **_kwargs) -> StageResult:
            return _entity_stage(
                "extract",
                ("champion", 1, ResultStatus.SUCCESS, ("audios/1/101.wem",)),
                ("champion", 2, ResultStatus.FAILED, ()),
            )

        def transcode_wav(self, options, **_kwargs) -> StageResult:
            wav_targets.append(options.champion_ids)
            return _stage("wav")

    _install_fake_runtime(monkeypatch, tmp_path, FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert wav_targets == [(1,)]
    assert [stage.stage for stage in result.run_result.stages] == ["extract", "wav"]
    assert result.run_result.status is ResultStatus.PARTIAL
    assert result.completed_steps == ("音频解包", "音频转码")


def test_run_execution_task_successful_no_op_has_no_completed_product_stage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """合法 no-op 是 success，但不能伪造已产生产物的步骤。"""
    task = _build_task(run_mapping=False, champion_ids=(1,))

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, _options, **_kwargs) -> StageResult:
            return StageResult("extract", note="没有任何任务需要执行")

    _install_fake_runtime(monkeypatch, tmp_path, FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert result.run_result.status is ResultStatus.SUCCESS
    assert result.completed_steps == ()
    assert result.summary.startswith("执行完成：本轮没有产生新产物")


def test_later_exception_preserves_completed_extract(monkeypatch, tmp_path: Path) -> None:
    """映射步骤抛出异常仍须保留先前解包成功及其产物。"""

    class FakeApp:
        def __init__(self, context):
            self.ctx = context

        def extract(self, *_args, **_kwargs):
            return _entity_stage("extract", ("champion", 1, ResultStatus.SUCCESS, ("1.wem",)))

        def mapping(self, *_args, **_kwargs):
            raise OSError("disk full")

    _install_fake_runtime(monkeypatch, tmp_path, FakeApp)
    result = task_runner.run_execution_task(
        _build_task(champion_ids=(1,)), SimpleNamespace(progress=SimpleNamespace(emit=lambda _event: None))
    )
    assert result.run_result.status is ResultStatus.PARTIAL
    assert result.completed_steps == ("音频解包",)
    assert result.run_result.stages[0].entities[0].artifacts == ("1.wem",)
    assert result.run_result.stages[1].error_message == "disk full"


def test_run_execution_task_allows_wav_stage_without_extract(monkeypatch, tmp_path: Path) -> None:
    task = _build_task(run_extract=False, run_mapping=False, wav_enabled=True)
    events: list[str] = []

    def _fail_exception(message: str) -> None:
        pytest.fail(message)

    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
        config=SimpleNamespace(),
    )

    monkeypatch.setattr(
        task_runner,
        "logger",
        SimpleNamespace(
            info=lambda _message: None,
            debug=lambda _message: None,
            success=lambda _message: None,
            exception=_fail_exception,
        ),
    )
    monkeypatch.setattr(task_runner, "create_app_context", lambda *, settings: runtime_context)

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, _options, **_kwargs) -> None:
            pytest.fail("未勾选音频解包时不应执行 extract")

        def transcode_wav(self, options, **_kwargs) -> StageResult:
            assert options.wav_output.enabled is True
            events.append("wav")
            return _stage("wav")

        def mapping(self, _options, **_kwargs) -> None:
            pytest.fail("未勾选事件映射时不应执行 mapping")

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert events == ["wav"]
    assert result.completed_steps == ("音频转码",)


def test_run_execution_task_rejects_missing_map_banks_before_runtime_steps(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """地图 banks 尚未生成时，GUI 任务不应静默跳过地图输出。"""
    task = _build_task(run_mapping=False)
    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(
            manifest_path=tmp_path / "manifest",
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
        config=SimpleNamespace(dev_mode=False),
    )
    data_dir = runtime_context.paths.manifest_path / "16.5"
    data_dir.mkdir(parents=True)
    (data_dir / "data.msgpack").write_bytes(b"placeholder")

    class FakeReader:
        version = "16.5"

        def get_champions(self) -> list[dict]:
            return [{"id": 1}]

        def get_maps(self) -> list[dict]:
            return [{"id": 11}]

        def get_map_banks(self, _map_id: int):
            return None

    reader = FakeReader()

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def _get_reader(self) -> FakeReader:
            return reader

        def extract(self, _options, **_kwargs) -> None:
            pytest.fail("地图 banks 缺失时不应进入 extract")

    monkeypatch.setattr(task_runner, "create_app_context", lambda *, settings: runtime_context)
    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)
    assert result.run_result.status is ResultStatus.FAILED
    assert "地图基础数据仍未准备完成" in result.run_result.stages[-1].error_message


def test_run_execution_task_preserves_special_targets_for_app_facade(monkeypatch, tmp_path: Path) -> None:
    """GUI runner 不得把异构 special key 错当作普通英雄 ID。"""
    task = _build_task(
        run_mapping=False,
        champion_ids=(1, 66600),
        special_targets=("champion:66600", "champion:77702"),
    )
    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(audio_path=tmp_path / "audios", wav_path=tmp_path / "wavs"),
        runtime_cache={},
        config=SimpleNamespace(),
    )
    captured = []
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    monkeypatch.setattr(task_runner, "create_app_context", lambda **_kwargs: runtime_context)

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, options, **_kwargs) -> StageResult:
            captured.append(options)
            return _stage("extract")

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)

    task_runner.run_execution_task(task, signals)

    assert len(captured) == 1
    assert captured[0].champion_ids == (1, 66600)
    assert captured[0].special_targets == ("champion:66600", "champion:77702")


def test_resource_pack_only_task_excludes_champion_and_map_runtime_scope(monkeypatch, tmp_path: Path) -> None:
    """仅资源包任务不得退化为全量英雄/地图，也不能触发地图 banks 检查。"""
    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")
    task = _build_task(run_mapping=False, special_targets=(key,))
    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(audio_path=tmp_path / "audios", wav_path=tmp_path / "wavs"),
        runtime_cache={},
        config=SimpleNamespace(),
    )
    calls: list[tuple[bool, bool]] = []
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    monkeypatch.setattr(task_runner, "create_app_context", lambda **_kwargs: runtime_context)

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(
            self,
            _options,
            *,
            include_champions: bool,
            include_maps: bool,
            **_kwargs,
        ) -> StageResult:
            calls.append((include_champions, include_maps))
            return _stage("extract")

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)

    task_runner.run_execution_task(task, signals)

    assert calls == [(False, False)]


def test_resource_pack_wad_snapshot_is_rejected_before_app_context(
    monkeypatch,
) -> None:
    """直接构造的 WAD snapshot 必须在创建上下文前通过 WAV 边界。"""
    ref = ResourcePackWadRef("Game/DATA/FINAL/Legacy.wad.client", size=12, mtime_ns=34)
    task = _build_task(
        run_mapping=False,
        wav_enabled=True,
        resource_pack_wads=(ref,),
    )
    calls: list[str] = []
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))
    monkeypatch.setattr(
        task_runner,
        "create_app_context",
        lambda **_kwargs: calls.append("context") or pytest.fail("不应创建 AppContext"),
    )

    with pytest.raises(ValueError, match="resource pack 当前不支持 WAV 转码"):
        task_runner.run_execution_task(task, signals)

    assert calls == []
