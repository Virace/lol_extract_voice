"""共享实体数据控制器测试。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.gui.controllers.contracts import GuiNotice
from lol_audio_unpack.gui.controllers.shared_data_controller import SharedDataController
from lol_audio_unpack.gui.task_models import OutputStateRefreshRequest


class _FakeConfig:
    """最小可用的 GUI 配置替身。"""

    source_mode = "local_path"
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

    def to_app_context_overrides(self) -> dict[str, str | bool]:
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


class _FakeTaskWorker:
    """共享数据控制器测试使用的最小 worker。"""

    def __init__(self, func) -> None:
        self.func = func
        self.signals = _FakeTaskWorkerSignals()


def _build_controller(
    *,
    has_incomplete_tasks=lambda: False,
    entity_data_loader_cls=object,
    create_app_context_fn=lambda **_kwargs: object(),
    task_worker_cls=object,
    start_worker_fn=lambda _worker: None,
) -> SharedDataController:
    cfg = _FakeConfig()
    return SharedDataController(
        get_config=lambda: cfg,
        has_incomplete_tasks=has_incomplete_tasks,
        create_app_context_fn=create_app_context_fn,
        data_load_worker_cls=object,
        task_worker_cls=task_worker_cls,
        entity_data_loader_cls=entity_data_loader_cls,
        start_worker_fn=start_worker_fn,
        prepare_shared_entity_data_fn=lambda _overrides: None,
        reset_data_reader_singleton_fn=lambda: None,
        app_context_block_reason_fn=lambda _cfg: None,
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

        def load_entities_by_ids(self, entity_type: str, entity_ids: tuple[str, ...]):
            loader_calls.append((entity_type, tuple(entity_ids)))
            return [{"id": entity_ids[0], "name": entity_type}]

    controller = _build_controller(entity_data_loader_cls=_FakeEntityDataLoader)
    controller.data_app_context = object()
    updates = []
    notices = []
    reconfigure_payloads = []
    controller.entity_rows_updated.connect(updates.append)
    controller.notice_requested.connect(notices.append)
    controller.reconfigure_runtime_logging_requested.connect(reconfigure_payloads.append)

    controller.refresh_shared_output_state(
        OutputStateRefreshRequest(champion_ids=("1",), map_ids=("11",))
    )

    assert reconfigure_payloads == []
    assert loader_calls[1:] == [("champions", ("1",)), ("maps", ("11",))]
    assert [payload.entity_type for payload in updates] == ["champions", "maps"]
    assert notices == [
        GuiNotice(
            title="数据已刷新",
            content="列表内容已经更新，可以继续查看或创建任务。",
            level="success",
        )
    ]


def test_shared_data_controller_load_initial_data_starts_worker_and_emits_loading_state() -> None:
    started_workers = []
    create_calls = []
    loading_states = []

    def _create_app_context(**kwargs):
        create_calls.append(kwargs)
        return object()

    controller = _build_controller(
        create_app_context_fn=_create_app_context,
        task_worker_cls=_FakeTaskWorker,
        start_worker_fn=started_workers.append,
    )
    controller.loading_state_changed.connect(loading_states.append)

    controller.load_initial_data()

    assert controller.is_loading_shared_data is True
    assert controller.shared_context_build_request_id == 1
    assert len(started_workers) == 1
    worker = started_workers[0]
    assert worker is controller.shared_context_build_worker
    assert loading_states[-1].message == "正在读取本地共享数据…"
    assert loading_states[-1].active is True
    assert create_calls == []

    worker.func()

    assert len(create_calls) == 1
    assert create_calls[0]["cli_overrides"]["SOURCE_MODE"] == "local_path"
    assert create_calls[0]["cli_overrides"]["OUTPUT_PATH"] == "output"


def test_shared_data_controller_load_initial_data_failed_callback_clears_state_and_notifies() -> None:
    started_workers = []
    loading_states = []
    notices = []
    app_context_events = []
    cleared_events = []

    controller = _build_controller(
        task_worker_cls=_FakeTaskWorker,
        start_worker_fn=started_workers.append,
    )
    controller.loading_state_changed.connect(loading_states.append)
    controller.notice_requested.connect(notices.append)
    controller.app_context_changed.connect(app_context_events.append)
    controller.shared_data_cleared.connect(lambda: cleared_events.append(True))
    controller.pending_refresh_notice = True

    controller.load_initial_data()
    started_workers[0].signals.failed.emit("boom")

    assert controller.shared_context_build_worker is None
    assert controller.shared_context_build_cfg is None
    assert controller.is_loading_shared_data is False
    assert controller.data_app_context is None
    assert app_context_events == [None]
    assert cleared_events == [True]
    assert loading_states[-1].message == "加载失败: boom"
    assert loading_states[-1].active is False
    assert notices == [GuiNotice(title="刷新失败", content="boom", level="error")]
    assert controller.pending_refresh_notice is False


def test_shared_data_controller_on_shared_context_build_timeout_resets_state_and_emits_notice() -> None:
    started_workers = []
    loading_states = []
    notices = []
    app_context_events = []
    cleared_events = []
    expected_request_id_after_timeout = 2

    controller = _build_controller(
        task_worker_cls=_FakeTaskWorker,
        start_worker_fn=started_workers.append,
    )
    controller.loading_state_changed.connect(loading_states.append)
    controller.notice_requested.connect(notices.append)
    controller.app_context_changed.connect(app_context_events.append)
    controller.shared_data_cleared.connect(lambda: cleared_events.append(True))

    controller.load_initial_data()
    assert controller.shared_context_build_request_id == 1

    controller.on_shared_context_build_timeout()

    assert controller.shared_context_build_request_id == expected_request_id_after_timeout
    assert controller.shared_context_build_worker is None
    assert controller.shared_context_build_cfg is None
    assert controller.is_loading_shared_data is False
    assert controller.data_app_context is None
    assert app_context_events == [None]
    assert cleared_events == [True]
    assert loading_states[-1].message == "加载失败: 读取共享数据超时，请重试。"
    assert loading_states[-1].active is False
    assert notices == [
        GuiNotice(
            title="共享数据加载超时",
            content="读取共享数据超时，请重试。",
            level="error",
        )
    ]


def test_shared_data_controller_reconfigures_logging_only_when_scan_signature_changes() -> None:
    cfg = _FakeConfig()
    controller = SharedDataController(
        get_config=lambda: cfg,
        has_incomplete_tasks=lambda: False,
        create_app_context_fn=lambda **_kwargs: object(),
        data_load_worker_cls=object,
        task_worker_cls=object,
        entity_data_loader_cls=object,
        start_worker_fn=lambda _worker: None,
        prepare_shared_entity_data_fn=lambda _overrides: None,
        reset_data_reader_singleton_fn=lambda: None,
        app_context_block_reason_fn=lambda _cfg: None,
    )
    controller.shared_entity_reader_signature = (
        cfg.to_app_context_overrides()["SOURCE_MODE"],
        cfg.to_app_context_overrides()["GAME_PATH"],
        cfg.to_app_context_overrides()["GAME_REGION"],
        cfg.to_app_context_overrides()["REMOTE_LIVE_REGION"],
        cfg.to_app_context_overrides()["REMOTE_VERSION"],
        cfg.to_app_context_overrides()["REMOTE_LCU_MANIFEST_URL"],
        cfg.to_app_context_overrides()["REMOTE_GAME_MANIFEST_URL"],
    )
    controller.shared_entity_scan_signature = (
        cfg.to_app_context_overrides()["OUTPUT_PATH"],
        cfg.to_app_context_overrides()["GROUP_BY_TYPE"],
    )
    reconfigure_payloads = []
    controller.reconfigure_runtime_logging_requested.connect(reconfigure_payloads.append)

    controller.on_shared_context_input_changed()
    assert reconfigure_payloads == []

    cfg.output_path = "new-output"
    controller.on_shared_context_input_changed()

    assert len(reconfigure_payloads) == 1
    assert reconfigure_payloads[0].log_dir == Path("logs/runtime")


def test_shared_data_controller_shutdown_background_work_stops_short_workers() -> None:
    controller = _build_controller()
    controller.shared_context_build_worker = object()
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
