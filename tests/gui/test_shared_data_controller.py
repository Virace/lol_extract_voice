"""共享实体数据控制器测试。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.gui.window as window_module
from lol_audio_unpack.app.resource_pack import ResourcePackWadRef, build_resource_pack_key
from lol_audio_unpack.app.results import ResultStatus, StageResult
from lol_audio_unpack.gui.controllers.contracts import GuiNotice
from lol_audio_unpack.gui.controllers.shared_data import (
    SharedDataController,
    build_shared_context_loading_message,
    build_shared_entity_reader_signature,
)
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader
from lol_audio_unpack.gui.shared_data import (
    SharedDataFailure,
    SharedDataPhase,
    SharedDataPreparationResult,
    SharedDataPrepareTrigger,
    SharedDataProblem,
    SharedDataProblemCode,
    SharedDataProgress,
    SharedDataReadiness,
    SharedDataRepairScope,
    SharedDataScanResult,
    SharedDataSectionResult,
)
from lol_audio_unpack.gui.task_models import OutputStateRefreshRequest
from lol_audio_unpack.manager.files import write_data
from lol_audio_unpack.model.binding import RESOURCE_SCHEMA_VERSION
from lol_audio_unpack.model.progress import OperationProgress

EXPECTED_SCAN_COUNT_AFTER_VERIFICATION = 2
EXPECTED_FIXTURE_MAP_COUNT = 2
CURRENT_GENERATION = 2


class _FakeConfig:
    """最小可用的 GUI 配置替身。"""

    source_mode = "local_path"
    effective_source_mode = "local_path"
    remote_snapshot_strategy = "latest"
    output_path = "output"
    game_path = "game"
    game_region = "zh_CN"
    remote_live_region = "EUW"
    snapshot_version = ""
    snapshot_lcu_url = ""
    snapshot_game_url = ""
    group_by_type = False
    console_log_level = "INFO"
    file_log_level = "DEBUG"

    def to_app_context_settings(self) -> dict[str, str | bool]:
        return {
            "SOURCE_MODE": self.source_mode,
            "GAME_PATH": self.game_path,
            "GAME_REGION": self.game_region,
            "REMOTE_LIVE_REGION": self.remote_live_region,
            "REMOTE_VERSION": self.snapshot_version,
            "REMOTE_LCU_MANIFEST_URL": self.snapshot_lcu_url,
            "REMOTE_GAME_MANIFEST_URL": self.snapshot_game_url,
            "OUTPUT_PATH": self.output_path,
            "GROUP_BY_TYPE": self.group_by_type,
        }

    def resolve_log_dir(self) -> Path:
        return Path("logs/runtime")


class _FakeSignal:
    """最小信号替身。"""

    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self._callbacks):
            callback(*args)


class _FakeTaskWorkerSignals:
    """任务 worker 的最小信号集合。"""

    def __init__(self) -> None:
        self.started = _FakeSignal()
        self.finished = _FakeSignal()
        self.failed = _FakeSignal()
        self.progress = _FakeSignal()


class _FakeTaskWorker:
    """共享数据控制器测试使用的最小 worker。"""

    def __init__(self, func, *, pass_signals: bool = False) -> None:
        self.func = func
        self.pass_signals = pass_signals
        self.signals = _FakeTaskWorkerSignals()

    def run(self):
        """同步运行函数并发送与生产 TaskWorker 一致的信号。"""
        self.signals.started.emit()
        result = self.func(self.signals) if self.pass_signals else self.func()
        self.signals.finished.emit(result)
        return result


class _FakeScanWorker:
    """可由测试显式结算的完整目录扫描 worker。"""

    instances = []

    def __init__(self, app_context, generation: int) -> None:
        self.app_context = app_context
        self.generation = generation
        self.progress = _FakeSignal()
        self.finished = _FakeSignal()
        self.error = _FakeSignal()
        self.started = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        self.started = True

    def isRunning(self) -> bool:
        return self.started


def _scan_result(
    generation: int,
    *,
    champion_failures: tuple[SharedDataFailure, ...] = (),
    all_champions_failed: bool = False,
) -> SharedDataScanResult:
    """构造 controller 测试使用的完整或不完整目录快照。"""
    failures = champion_failures
    champion_rows = () if all_champions_failed else ({"id": "1", "name": "Annie"},)
    champion_ids = ("1", "2") if failures else ("1",)
    champions = SharedDataSectionResult(
        "champions",
        champion_ids,
        rows=champion_rows,
        failures=failures,
    )
    maps = SharedDataSectionResult(
        "maps",
        ("0", "11"),
        rows=({"id": "0", "name": "Common"}, {"id": "11", "name": "峡谷"}),
    )
    special = SharedDataSectionResult("special", (), required=False)
    problems = ()
    if failures:
        problems = (
            SharedDataProblem(
                failures[0].code,
                "champions",
                failures[0].message,
                tuple(failure.entity_id for failure in failures),
            ),
        )
    return SharedDataScanResult(
        generation,
        "local_path",
        "16.16",
        champions,
        maps,
        special,
        problems,
    )


def _build_controller(  # noqa: PLR0913
    *,
    has_incomplete_tasks=lambda: False,
    entity_data_loader_cls=object,
    create_app_context_fn=lambda **_kwargs: object(),
    task_worker_cls=object,
    data_load_worker_cls=object,
    start_worker_fn=lambda _worker: None,
    app_context_block_reason_fn=lambda _cfg: None,
    prepare_shared_entity_data_fn=lambda *_args, **_kwargs: None,
) -> SharedDataController:
    cfg = _FakeConfig()
    return SharedDataController(
        get_config=lambda: cfg,
        has_incomplete_tasks=has_incomplete_tasks,
        create_app_context_fn=create_app_context_fn,
        data_load_worker_cls=data_load_worker_cls,
        task_worker_cls=task_worker_cls,
        entity_data_loader_cls=entity_data_loader_cls,
        start_worker_fn=start_worker_fn,
        prepare_shared_entity_data_fn=prepare_shared_entity_data_fn,
        app_context_block_reason_fn=app_context_block_reason_fn,
    )


def test_shared_data_controller_refresh_shared_output_state_warns_when_queue_busy() -> None:
    controller = _build_controller(has_incomplete_tasks=lambda: True)
    notices = []
    reconfigure_payloads = []
    controller.notice_requested.connect(notices.append)
    controller.reconfigure_runtime_logging_requested.connect(reconfigure_payloads.append)

    controller.refresh_shared_output_state()

    assert reconfigure_payloads == []
    assert notices == [
        GuiNotice(
            title="队列未清空",
            content="请等待当前任务队列全部结束后再刷新列表数据。",
            level="warning",
        )
    ]


def test_shared_data_controller_refresh_shared_output_state_uses_incremental_loader() -> None:
    loader_calls = []

    class _FakeEntityDataLoader:
        def __init__(self, app_context) -> None:
            loader_calls.append(("init", app_context))

        def load_champion_rows_by_targets(
            self,
            *,
            champion_ids: tuple[str, ...],
            special_targets: tuple[str, ...],
        ):
            loader_calls.append(("champion_rows", champion_ids, special_targets))
            return {
                "champions": [{"id": champion_ids[0], "name": "champions"}],
                "special": [{"id": "66600", "key": special_targets[0], "name": "厄加特"}],
            }

        def load_entities_by_ids(self, entity_type: str, entity_ids: tuple[str, ...]):
            loader_calls.append((entity_type, tuple(entity_ids)))
            return [{"id": entity_ids[0], "name": entity_type}]

    controller = _build_controller(entity_data_loader_cls=_FakeEntityDataLoader)
    controller.app_context = object()
    controller.state = replace(controller.state, phase=SharedDataPhase.READY)
    updates = []
    notices = []
    reconfigure_payloads = []
    controller.entity_rows_updated.connect(updates.append)
    controller.notice_requested.connect(notices.append)
    controller.reconfigure_runtime_logging_requested.connect(reconfigure_payloads.append)

    controller.refresh_shared_output_state(
        OutputStateRefreshRequest(
            champion_ids=("1",),
            map_ids=("11",),
            special_targets=("champion:66600",),
        )
    )

    assert reconfigure_payloads == []
    assert loader_calls[1:] == [
        ("champion_rows", ("1",), ("champion:66600",)),
        ("maps", ("11",)),
    ]
    assert [payload.entity_type for payload in updates] == ["champions", "special", "maps"]
    assert notices == [
        GuiNotice(
            title="数据已刷新",
            content="列表内容已经更新，可以继续查看或创建任务。",
            level="success",
        )
    ]
    assert controller.state.phase is SharedDataPhase.READY


def test_shared_data_controller_refreshes_resource_pack_snapshot_without_champion_scan() -> None:
    """资源包 key 与 snapshot 的完成任务仍走特殊目录增量刷新。"""
    calls = []
    ref = ResourcePackWadRef("Game/DATA/FINAL/Legacy.wad.client", size=12, mtime_ns=34)
    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")

    class _FakeEntityDataLoader:
        def __init__(self, _app_context) -> None:
            calls.append("init")

        def load_champion_rows_by_targets(self, *, champion_ids, special_targets):
            calls.append((champion_ids, special_targets))
            return {"champions": [], "special": [{"id": key, "name": "Legacy"}]}

        def load_entities_by_ids(self, _entity_type, _entity_ids):
            pytest.fail("资源包增量刷新不应读取地图目录")

    controller = _build_controller(entity_data_loader_cls=_FakeEntityDataLoader)
    controller.app_context = object()
    updates = []
    controller.entity_rows_updated.connect(updates.append)

    controller.refresh_shared_output_state(OutputStateRefreshRequest(special_targets=(key,), resource_pack_wads=(ref,)))

    assert calls == ["init", ((), (key,))]
    assert [(payload.entity_type, payload.rows) for payload in updates] == [
        ("special", ({"id": key, "name": "Legacy"},))
    ]


def test_shared_data_controller_refresh_shared_output_state_warns_before_full_reload(
    monkeypatch,
) -> None:
    controller = _build_controller()
    warnings: list[str] = []
    reload_calls = []

    monkeypatch.setattr(
        "lol_audio_unpack.gui.controllers.shared_data.logger",
        SimpleNamespace(
            warning=warnings.append,
            info=lambda *_args, **_kwargs: None,
            debug=lambda *_args, **_kwargs: None,
            error=lambda *_args, **_kwargs: None,
        ),
    )
    controller.request_shared_data_reload = lambda **kwargs: reload_calls.append(kwargs)

    controller.refresh_shared_output_state()

    assert warnings == ["共享上下文尚未就绪，回退到完整共享数据刷新"]
    assert reload_calls == [{"show_notice": True, "allow_auto_prepare": True}]


def test_shared_data_controller_refresh_shared_output_state_emits_notice_when_reload_is_blocked() -> None:
    controller = _build_controller(app_context_block_reason_fn=lambda _cfg: "请先在「全局设置」中配置游戏目录。")
    notices = []
    states = []
    controller.notice_requested.connect(notices.append)
    controller.state_changed.connect(states.append)

    controller.refresh_shared_output_state()

    assert notices == [
        GuiNotice(
            title="无法刷新数据",
            content="请先在「全局设置」中配置游戏目录。",
            level="warning",
        )
    ]
    assert states[-1].phase is SharedDataPhase.BLOCKED
    assert states[-1].problem.message == "请先在「全局设置」中配置游戏目录。"
    assert controller.pending_refresh_notice is False


def test_shared_data_uses_effective_local_mode_when_packaged() -> None:
    cfg = _FakeConfig()
    cfg.source_mode = "remote_snapshot"
    cfg.effective_source_mode = "local_path"

    signature = build_shared_entity_reader_signature(cfg)

    assert signature[0] == "local_path"
    assert build_shared_context_loading_message(cfg) == "正在读取本地共享数据…"


def test_shared_data_controller_load_initial_data_starts_worker_and_emits_typed_state() -> None:
    started_workers = []
    create_calls = []
    states = []

    def _create_app_context(**kwargs):
        create_calls.append(kwargs)
        return object()

    controller = _build_controller(
        create_app_context_fn=_create_app_context,
        task_worker_cls=_FakeTaskWorker,
        start_worker_fn=started_workers.append,
    )
    controller.state_changed.connect(states.append)

    controller.load_initial_data()

    assert controller.is_loading_shared_data is True
    assert controller.build_request_id == 1
    assert len(started_workers) == 1
    worker = started_workers[0]
    assert worker is controller.build_worker
    assert states[-1].phase is SharedDataPhase.CHECKING
    assert states[-1].active is True
    assert create_calls == []

    worker.func()

    assert len(create_calls) == 1
    assert create_calls[0]["settings"]["SOURCE_MODE"] == "local_path"
    assert create_calls[0]["settings"]["OUTPUT_PATH"] == "output"


def test_shared_data_controller_load_initial_data_failed_callback_clears_state_and_notifies() -> None:
    started_workers = []
    states = []
    notices = []
    app_context_events = []
    cleared_events = []

    controller = _build_controller(
        task_worker_cls=_FakeTaskWorker,
        start_worker_fn=started_workers.append,
    )
    controller.state_changed.connect(states.append)
    controller.notice_requested.connect(notices.append)
    controller.app_context_changed.connect(app_context_events.append)
    controller.shared_data_cleared.connect(lambda: cleared_events.append(True))
    controller.pending_refresh_notice = True

    controller.load_initial_data()
    started_workers[0].signals.failed.emit("boom")

    assert controller.build_worker is None
    assert controller.build_config is None
    assert controller.is_loading_shared_data is False
    assert controller.app_context is None
    assert app_context_events == [None]
    assert cleared_events == [True]
    assert states[-1].phase is SharedDataPhase.FAILED
    assert states[-1].problem.message == "无法建立共享数据上下文；请检查设置后重试。"
    assert notices == [
        GuiNotice(
            title="实体数据准备失败",
            content="无法建立共享数据上下文；请检查设置后重试。",
            level="error",
        )
    ]
    assert controller.pending_refresh_notice is False


def test_shared_data_controller_on_shared_context_build_timeout_resets_state_and_emits_notice() -> None:
    started_workers = []
    states = []
    notices = []
    app_context_events = []
    cleared_events = []
    expected_request_id_after_timeout = 2

    controller = _build_controller(
        task_worker_cls=_FakeTaskWorker,
        start_worker_fn=started_workers.append,
    )
    controller.state_changed.connect(states.append)
    controller.notice_requested.connect(notices.append)
    controller.app_context_changed.connect(app_context_events.append)
    controller.shared_data_cleared.connect(lambda: cleared_events.append(True))

    controller.load_initial_data()
    assert controller.build_request_id == 1

    controller.on_shared_context_build_timeout()

    assert controller.build_request_id == expected_request_id_after_timeout
    assert controller.build_worker is None
    assert controller.build_config is None
    assert controller.is_loading_shared_data is False
    assert controller.app_context is None
    assert app_context_events == [None]
    assert cleared_events == [True]
    assert states[-1].phase is SharedDataPhase.FAILED
    assert states[-1].problem.message == "读取共享数据超时，请重试。"
    assert notices == [
        GuiNotice(
            title="共享数据加载超时",
            content="读取共享数据超时，请重试。",
            level="error",
        )
    ]


def test_stale_build_timeout_resumes_waiting_generation_without_failure() -> None:
    """旧 generation 的 build timeout 只释放 owner，不能覆盖新 waiting 状态。"""
    started_workers = []
    controller = _build_controller(
        task_worker_cls=_FakeTaskWorker,
        start_worker_fn=started_workers.append,
    )
    controller.generation = CURRENT_GENERATION
    controller.state = replace(controller.state, generation=CURRENT_GENERATION, phase=SharedDataPhase.WAITING)
    controller.build_worker = object()
    controller.build_config = _FakeConfig()
    controller._build_generation = 1
    controller.pending_runtime_entity_refresh = True
    controller.pending_refresh_allow_prepare = True

    controller.on_shared_context_build_timeout()

    assert len(started_workers) == 1
    assert controller.state.phase is SharedDataPhase.CHECKING
    assert controller.state.generation == CURRENT_GENERATION


def test_shared_data_controller_reloads_for_reader_and_scan_signature_changes() -> None:
    """读取上下文或输出配置变化都应启动新的 waiting generation。"""
    cfg = _FakeConfig()
    controller = _build_controller()
    controller.reader_signature = build_shared_entity_reader_signature(cfg)
    controller.scan_signature = (cfg.output_path, cfg.group_by_type)
    reconfigure_payloads = []
    reload_calls = []
    controller.reconfigure_runtime_logging_requested.connect(reconfigure_payloads.append)
    controller.load_initial_data = lambda config, **kwargs: reload_calls.append((config, kwargs))

    cfg.game_path = "new-game"
    controller.on_context_input_changed(cfg)
    controller.flush_pending_runtime_entity_refresh()

    cfg.output_path = "new-output"
    controller.on_context_input_changed(cfg)
    controller.flush_pending_runtime_entity_refresh()

    assert len(reconfigure_payloads) == 1
    assert reconfigure_payloads[0].log_dir == Path("logs/runtime")
    assert [call[1]["trigger"] for call in reload_calls] == [
        SharedDataPrepareTrigger.CONTEXT_CHANGE,
        SharedDataPrepareTrigger.CONTEXT_CHANGE,
    ]
    assert [call[1]["generation"] for call in reload_calls] == [1, 2]


def test_shared_data_controller_publishes_ready_only_from_complete_scan() -> None:
    """worker 生命周期结束不能替代当前 generation 的 complete scan。"""
    _FakeScanWorker.instances.clear()
    started_workers = []
    controller = _build_controller(
        task_worker_cls=_FakeTaskWorker,
        data_load_worker_cls=_FakeScanWorker,
        start_worker_fn=started_workers.append,
    )
    states = []
    rows = []
    notices = []
    controller.state_changed.connect(states.append)
    controller.entity_data_replaced.connect(rows.append)
    controller.notice_requested.connect(notices.append)

    controller.load_initial_data()
    started_workers[0].run()
    scan_worker = _FakeScanWorker.instances[-1]
    scan_worker.finished.emit(_scan_result(controller.generation))

    assert controller.state.phase is SharedDataPhase.READY
    assert controller.state.summary.champion_loaded == 1
    assert [payload.entity_type for payload in rows] == ["champions", "special", "maps"]
    assert notices == []
    assert states[-1].blocks_new_tasks is False


@pytest.mark.parametrize(
    ("stage_status", "expected_phase", "expects_verification"),
    [
        (ResultStatus.SUCCESS, SharedDataPhase.READY, True),
        (ResultStatus.PARTIAL, SharedDataPhase.PARTIAL, True),
        (ResultStatus.FAILED, SharedDataPhase.FAILED, False),
        (ResultStatus.CANCELLED, SharedDataPhase.CANCELLED, False),
    ],
)
def test_shared_data_controller_consumes_prepare_stage_result_four_states(
    stage_status: ResultStatus,
    expected_phase: SharedDataPhase,
    expects_verification: bool,
) -> None:
    """TaskWorker.finished 只传递结果，业务终态必须按 StageResult 四态决定。"""
    _FakeScanWorker.instances.clear()
    started_workers = []
    prepare_calls = []
    progress_event = SimpleNamespace(stage_key="champion_banks", current=1, total=2)

    def prepare(_settings, **kwargs) -> SharedDataPreparationResult:
        prepare_calls.append(kwargs)
        kwargs["progress_callback"](progress_event)
        stage = StageResult(
            "update",
            status=stage_status,
            error_type="UpdateFailed" if stage_status is ResultStatus.FAILED else None,
            error_message="更新失败" if stage_status is ResultStatus.FAILED else None,
            note="用户取消" if stage_status is ResultStatus.CANCELLED else None,
        )
        return SharedDataPreparationResult(kwargs["generation"], kwargs["scope"], stage)

    controller = _build_controller(
        task_worker_cls=_FakeTaskWorker,
        data_load_worker_cls=_FakeScanWorker,
        start_worker_fn=started_workers.append,
        prepare_shared_entity_data_fn=prepare,
    )
    notices = []
    states = []
    controller.notice_requested.connect(notices.append)
    controller.state_changed.connect(states.append)

    controller.load_initial_data()
    started_workers[0].run()
    failure = SharedDataFailure(
        "2",
        SharedDataProblemCode.RESOURCE_SCHEMA_MISMATCH,
        "共享 banks artifact 仍使用旧版资源结构。",
    )
    _FakeScanWorker.instances[-1].finished.emit(_scan_result(controller.generation, champion_failures=(failure,)))

    prepare_worker = started_workers[1]
    prepare_worker.signals.started.emit()
    prepare_worker.run()
    if expects_verification:
        assert controller.state.phase is SharedDataPhase.VERIFYING
        assert len(_FakeScanWorker.instances) == EXPECTED_SCAN_COUNT_AFTER_VERIFICATION
        _FakeScanWorker.instances[-1].finished.emit(_scan_result(controller.generation))

    assert controller.state.phase is expected_phase
    assert len(prepare_calls) == 1
    assert prepare_calls[0]["scope"] == SharedDataRepairScope(full=False, champion_ids=(2,))
    assert prepare_calls[0]["force_update"] is False
    assert any(state.progress is progress_event for state in states)
    assert notices[0].level == "info"
    assert sum(notice.title == "正在更新实体数据" for notice in notices) == 1
    if stage_status is ResultStatus.SUCCESS:
        assert notices[-1].level == "success"
    else:
        assert notices[-1].level in {"warning", "error"}


def test_shared_data_controller_does_not_auto_prepare_twice_after_failed_verification() -> None:
    """update success 后复检仍不完整时保持终态，不进入自动循环。"""
    _FakeScanWorker.instances.clear()
    started_workers = []
    prepare_count = 0

    def prepare(_settings, **kwargs) -> SharedDataPreparationResult:
        nonlocal prepare_count
        prepare_count += 1
        return SharedDataPreparationResult(
            kwargs["generation"],
            kwargs["scope"],
            StageResult("update", status=ResultStatus.SUCCESS),
        )

    controller = _build_controller(
        task_worker_cls=_FakeTaskWorker,
        data_load_worker_cls=_FakeScanWorker,
        start_worker_fn=started_workers.append,
        prepare_shared_entity_data_fn=prepare,
    )
    failure = SharedDataFailure(
        "2",
        SharedDataProblemCode.RESOURCE_SCHEMA_MISMATCH,
        "共享 banks artifact 仍使用旧版资源结构。",
    )
    controller.load_initial_data()
    started_workers[0].run()
    _FakeScanWorker.instances[-1].finished.emit(_scan_result(controller.generation, champion_failures=(failure,)))
    started_workers[1].run()
    _FakeScanWorker.instances[-1].finished.emit(_scan_result(controller.generation, champion_failures=(failure,)))

    assert prepare_count == 1
    assert controller.state.phase is SharedDataPhase.PARTIAL
    assert controller.state.prepare_attempted is True


def test_shared_data_controller_maps_stage_error_type_to_stable_problem() -> None:
    """准备失败按 typed error_type 分类，不解析或直接展示底层路径文案。"""
    result = StageResult(
        "update",
        status=ResultStatus.FAILED,
        error_type="ArtifactWriteError",
        error_message="artifact 写入失败（replace）: C:/private/output/data.msgpack",
    )

    problem = SharedDataController._problem_from_stage_result(result)

    assert problem.code is SharedDataProblemCode.OUTPUT_NOT_WRITABLE
    assert "C:/private" not in problem.message


def test_shared_data_repair_scope_uses_full_update_for_dataset_problem() -> None:
    """无法枚举可信失败 ID 的 dataset 问题必须回退完整 update。"""
    scan = replace(
        _scan_result(1),
        problems=(
            SharedDataProblem(
                SharedDataProblemCode.DATASET_MISSING,
                "dataset",
                "当前版本的实体基础数据不存在。",
            ),
        ),
    )

    assert SharedDataRepairScope.from_scan(scan) == SharedDataRepairScope(full=True)


def test_shared_data_manual_retry_forwards_explicit_force_only() -> None:
    """force rebuild 只由显式 manual retry 传给 prepare adapter。"""
    _FakeScanWorker.instances.clear()
    started_workers = []
    prepare_calls = []

    def prepare(_settings, **kwargs) -> SharedDataPreparationResult:
        prepare_calls.append(kwargs)
        return SharedDataPreparationResult(
            kwargs["generation"],
            kwargs["scope"],
            StageResult("update", status=ResultStatus.FAILED),
        )

    controller = _build_controller(
        task_worker_cls=_FakeTaskWorker,
        data_load_worker_cls=_FakeScanWorker,
        start_worker_fn=started_workers.append,
        prepare_shared_entity_data_fn=prepare,
    )
    controller.request_shared_data_retry(force_update=True)
    started_workers[0].run()
    failure = SharedDataFailure(
        "2",
        SharedDataProblemCode.RESOURCE_SCHEMA_MISMATCH,
        "共享 banks artifact 仍使用旧版资源结构。",
    )
    _FakeScanWorker.instances[-1].finished.emit(_scan_result(controller.generation, champion_failures=(failure,)))
    started_workers[1].run()

    assert prepare_calls[0]["force_update"] is True
    assert controller.state.prepare_trigger is SharedDataPrepareTrigger.MANUAL_RETRY


def test_shared_data_controller_rejects_stale_generation_callbacks() -> None:
    """旧 generation 的 scan、progress 与 prepare 结果都不能覆盖新状态。"""
    controller = _build_controller()
    controller.generation = CURRENT_GENERATION
    controller.state = replace(controller.state, generation=CURRENT_GENERATION, phase=SharedDataPhase.WAITING)
    stale_scan = _scan_result(1)

    controller.on_scan_progress(1, SimpleNamespace(generation=1, current=1, total=1))
    controller.on_prepare_progress(1, SimpleNamespace(current=1, total=1))
    controller.on_scan_finished(1, stale_scan)
    controller.on_prepare_finished(
        1,
        SharedDataPreparationResult(
            1,
            SharedDataRepairScope(full=True),
            StageResult("update", status=ResultStatus.SUCCESS),
        ),
    )

    assert controller.state.phase is SharedDataPhase.WAITING
    assert controller.state.generation == CURRENT_GENERATION
    assert controller.state.progress is None


def test_shared_data_controller_throttles_ordinary_progress_but_keeps_latest(qtbot) -> None:
    """高频普通进度只按窗口刷新，并在窗口结束时发布最后一份快照。"""
    controller = _build_controller()
    controller.generation = 1
    controller.state = replace(
        controller.state,
        generation=1,
        phase=SharedDataPhase.CHECKING,
    )
    first = SharedDataProgress(1, "champions", "advanced", current=1, total=3)
    latest = SharedDataProgress(1, "champions", "advanced", current=2, total=3)

    controller.on_scan_progress(1, first)
    controller.on_scan_progress(1, latest)

    assert controller.state.progress is first
    qtbot.waitUntil(lambda: controller.state.progress is latest, timeout=1000)


def test_legacy_schema_fixture_uses_normal_update_adapter_then_verifies_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """旧 schema 必须经非 force update adapter 和真实扫描复检后才进入 ready。"""
    _FakeScanWorker.instances.clear()
    started_workers = []
    update_options = []
    champion_banks_dir = tmp_path / "champion-banks"
    map_banks_dir = tmp_path / "map-banks"
    resource_pack_banks_dir = tmp_path / "resource-pack-banks"
    champion_banks_dir.mkdir()
    map_banks_dir.mkdir()
    resource_pack_banks_dir.mkdir()

    legacy_payload = {"metadata": {"gameVersion": "16.16"}}
    for base_path in (
        champion_banks_dir / "1",
        map_banks_dir / "0",
        map_banks_dir / "11",
    ):
        write_data(legacy_payload, base_path, dev_mode=True)

    context = SimpleNamespace(
        config=SimpleNamespace(
            source_mode="local_path",
            effective_source_mode="local_path",
            dev_mode=True,
            game_path=tmp_path / "game",
        ),
        game_region="zh_CN",
    )
    champions = [
        {
            "id": 1,
            "alias": "Annie",
            "names": {"zh_CN": "安妮"},
            "wad": {"root": "Champions/Annie.wad.client"},
        }
    ]
    maps = [
        {"id": entity_id, "names": {"zh_CN": name}, "wad": {"root": f"Maps/{entity_id}.wad.client"}}
        for entity_id, name in ((0, "Common"), (11, "召唤师峡谷"))
    ]

    def scan_fixture(generation: int) -> SharedDataScanResult:
        """使用真实 catalog 扫描逻辑读取当前 fixture artifact。"""
        loader = EntityDataLoader.__new__(EntityDataLoader)
        loader.ctx = context
        loader.data_reader = SimpleNamespace(
            version="16.16",
            champion_banks_dir=champion_banks_dir,
            map_banks_dir=map_banks_dir,
            resource_pack_banks_dir=resource_pack_banks_dir,
            _champion_banks_cache={},
            _map_banks_cache={},
            get_champions=lambda: champions,
            get_maps=lambda: maps,
        )
        loader._build_entity_row = lambda entity_type, entity, _version: {
            "id": str(entity["id"]),
            "name": str(entity.get("alias") or entity["names"]["zh_CN"]),
            "entity_type": entity_type,
        }
        loader.load_resource_pack_rows = lambda **_kwargs: []
        return loader.scan_catalog(generation)

    class _FixtureApp:
        """用原子写入模拟核心 update 完成 schema 迁移。"""

        def __init__(self, app_context) -> None:
            """绑定 adapter 创建的当前测试上下文。"""
            assert app_context is context

        def update(self, options, *, target: str, progress_callback) -> StageResult:
            """以普通更新参数把旧 artifact 原子替换为 v2。"""
            update_options.append(options)
            assert target == "all"
            assert options.force_update is False
            progress_callback(OperationProgress("update", "champion_banks", "started", 0, 1))
            ready_payload = {
                "resourceSchemaVersion": RESOURCE_SCHEMA_VERSION,
                "diagnostics": {"completeness": "complete"},
            }
            for base_path in (
                champion_banks_dir / "1",
                map_banks_dir / "0",
                map_banks_dir / "11",
            ):
                write_data(ready_payload, base_path, dev_mode=True)
            progress_callback(OperationProgress("update", "champion_banks", "finished", 1, 1))
            return StageResult("update", status=ResultStatus.SUCCESS)

    monkeypatch.setattr(window_module, "create_app_context", lambda **_kwargs: context)
    monkeypatch.setattr(window_module, "LolAudioUnpackApp", _FixtureApp)
    controller = _build_controller(
        create_app_context_fn=lambda **_kwargs: context,
        task_worker_cls=_FakeTaskWorker,
        data_load_worker_cls=_FakeScanWorker,
        start_worker_fn=started_workers.append,
        prepare_shared_entity_data_fn=window_module._prepare_shared_entity_data,
    )

    controller.load_initial_data()
    started_workers[0].run()
    initial_scan = scan_fixture(controller.generation)
    _FakeScanWorker.instances[-1].finished.emit(initial_scan)

    assert initial_scan.readiness is SharedDataReadiness.FAILED
    assert {problem.code for problem in initial_scan.problems} == {SharedDataProblemCode.RESOURCE_SCHEMA_MISMATCH}

    started_workers[1].run()
    verified_scan = scan_fixture(controller.generation)
    _FakeScanWorker.instances[-1].finished.emit(verified_scan)

    assert len(update_options) == 1
    assert verified_scan.readiness is SharedDataReadiness.COMPLETE
    assert controller.state.phase is SharedDataPhase.READY
    assert controller.state.summary.champion_loaded == 1
    assert controller.state.summary.map_loaded == EXPECTED_FIXTURE_MAP_COUNT


def test_shared_data_controller_waits_for_busy_queue_then_resumes_checking() -> None:
    """配置变化在队列忙时进入 waiting，清空后自动继续同一 generation。"""
    busy = True
    started_workers = []
    cfg = _FakeConfig()
    controller = _build_controller(
        has_incomplete_tasks=lambda: busy,
        task_worker_cls=_FakeTaskWorker,
        start_worker_fn=started_workers.append,
    )
    controller.reader_signature = build_shared_entity_reader_signature(cfg)
    controller.scan_signature = (cfg.output_path, cfg.group_by_type)

    cfg.game_path = "new-game"
    controller.on_context_input_changed(cfg)

    assert controller.state.phase is SharedDataPhase.WAITING
    assert started_workers == []

    busy = False
    controller.set_queue_busy(False)

    assert controller.state.phase is SharedDataPhase.CHECKING
    assert len(started_workers) == 1


def test_shared_data_controller_shutdown_background_work_stops_short_workers() -> None:
    controller = _build_controller()
    controller.build_worker = object()
    controller.shared_data_prepare_worker = object()
    controller.is_loading_shared_data = True
    controller.is_preparing_shared_data = True
    controller.runtime_entity_refresh_timer.start()

    class _FakeThread:
        def __init__(self) -> None:
            self.request_interruption_called = False
            self.quit_called = False
            self.wait_calls = []
            self.terminate_called = False

        def isRunning(self) -> bool:
            return True

        def requestInterruption(self) -> None:
            self.request_interruption_called = True

        def quit(self) -> None:
            self.quit_called = True

        def wait(self, timeout_ms: int) -> bool:
            self.wait_calls.append(timeout_ms)
            return True

        def terminate(self) -> None:
            self.terminate_called = True

    controller._champions_worker = _FakeThread()
    controller._maps_worker = _FakeThread()
    champions_worker = controller._champions_worker
    maps_worker = controller._maps_worker

    assert controller.has_active_background_work() is True

    controller.shutdown_background_work()

    assert controller.has_active_background_work() is False
    assert champions_worker.request_interruption_called is True
    assert champions_worker.quit_called is True
    assert maps_worker.request_interruption_called is True
    assert maps_worker.quit_called is True
