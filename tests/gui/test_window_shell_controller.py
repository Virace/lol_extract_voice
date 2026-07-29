"""主窗口壳层 helper 测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.controllers.window_shell import (
    apply_task_queue_busy_state,
    bind_shared_data_controller_signals,
    confirm_force_close_running_tasks,
    force_quit_application,
    forward_selection_sync_feedback,
)

FORCE_QUIT_DELAY_MS = 250


def test_apply_task_queue_busy_state_updates_setting_and_refresh_widget() -> None:
    events: list[tuple[str, object]] = []

    class _FakeSettingPage:
        def set_runtime_config_locked(self, busy: bool) -> None:
            events.append(("locked", busy))

    class _FakeRefreshWidget:
        def setEnabled(self, enabled: bool) -> None:
            events.append(("refresh_enabled", enabled))

    class _FakeNavigation:
        def widget(self, key: str):
            assert key == "refreshSharedData"
            return _FakeRefreshWidget()

    class _FakeSharedController:
        def set_queue_busy(self, busy: bool) -> None:
            events.append(("queue_busy", busy))

    apply_task_queue_busy_state(
        busy=True,
        setting_page=_FakeSettingPage(),
        navigation_interface=_FakeNavigation(),
        shared_data_controller=_FakeSharedController(),
    )

    assert events == [
        ("locked", True),
        ("refresh_enabled", False),
        ("queue_busy", True),
    ]


def test_forward_selection_sync_feedback_emits_success_only_when_summary_exists() -> None:
    calls: list[tuple[str, str]] = []

    class _FakeExecutionPage:
        def set_selected_entities(self, payload, feedback_parent=None):
            assert payload == {"a": 1}
            assert feedback_parent == "host"
            return "已同步"

    forward_selection_sync_feedback(
        payload={"a": 1},
        execution_page=_FakeExecutionPage(),
        feedback_parent="host",
        show_feedback=lambda **kwargs: calls.append((kwargs["title"], kwargs["content"])),
    )

    assert calls == [("已同步到执行中心", "已同步")]


def test_forward_selection_sync_feedback_skips_when_summary_is_none() -> None:
    calls: list[dict] = []

    class _FakeExecutionPage:
        def set_selected_entities(self, payload, feedback_parent=None):
            return None

    forward_selection_sync_feedback(
        payload={"a": 1},
        execution_page=_FakeExecutionPage(),
        feedback_parent="host",
        show_feedback=lambda **kwargs: calls.append(kwargs),
    )

    assert calls == []


def test_bind_shared_data_controller_signals_wires_payload_consumers() -> None:
    events: list[tuple[str, object]] = []

    class _FakeSignal:
        def __init__(self) -> None:
            self._callbacks = []

        def connect(self, callback) -> None:
            self._callbacks.append(callback)

        def emit(self, value) -> None:
            for callback in self._callbacks:
                callback(value)

    class _FakeController:
        loading_state_changed = _FakeSignal()
        shared_data_cleared = _FakeSignal()
        app_context_changed = _FakeSignal()
        entity_data_replaced = _FakeSignal()
        entity_rows_updated = _FakeSignal()
        notice_requested = _FakeSignal()
        reconfigure_runtime_logging_requested = _FakeSignal()

    class _FakeHome:
        def set_loading_state(self, message: str, *, active: bool) -> None:
            events.append(("loading", (message, active)))

    class _FakeExecution:
        def set_shared_data_loading_state(self, state) -> None:
            events.append(("exec_loading", (state.message, state.active)))

        def clear_entity_data(self) -> None:
            events.append(("exec_clear", None))

        def set_entity_data(self, entity_type: str, rows) -> None:
            events.append(("exec_replace", (entity_type, tuple(rows))))

        def update_entity_rows(self, entity_type: str, rows) -> None:
            events.append(("exec_update", (entity_type, tuple(rows))))

    class _FakeOverview:
        def clear_data(self) -> None:
            events.append(("overview_clear", None))

        def set_app_context(self, value) -> None:
            events.append(("app_context", value))

        def set_entity_data(self, entity_type: str, rows) -> None:
            events.append(("overview_replace", (entity_type, tuple(rows))))

        def update_entity_rows(self, entity_type: str, rows) -> None:
            events.append(("overview_update", (entity_type, tuple(rows))))

    controller = _FakeController()
    bind_shared_data_controller_signals(
        controller,
        home_page=_FakeHome(),
        execution_page=_FakeExecution(),
        overview_page=_FakeOverview(),
        feedback_parent="host",
        show_feedback=lambda **kwargs: events.append(("notice", (kwargs["title"], kwargs["content"], kwargs["level"]))),
        on_reconfigure_runtime_logging=lambda payload: events.append(("log", payload)),
    )

    controller.loading_state_changed.emit(type("State", (), {"message": "loading", "active": True})())
    controller.entity_data_replaced.emit(type("Payload", (), {"entity_type": "champions", "rows": ({"id": 1},)})())
    controller.notice_requested.emit(type("Notice", (), {"title": "ok", "content": "done", "level": "success"})())

    assert ("loading", ("loading", True)) in events
    assert ("exec_loading", ("loading", True)) in events
    assert ("exec_replace", ("champions", ({"id": 1},))) in events
    assert ("overview_replace", ("champions", ({"id": 1},))) in events
    assert ("notice", ("ok", "done", "success")) in events


def test_confirm_force_close_running_tasks_returns_true_for_close(monkeypatch) -> None:
    button_texts: list[tuple[int, str]] = []

    class _FakeButton:
        def __init__(self, which: int) -> None:
            self.which = which

        def setText(self, text: str) -> None:
            button_texts.append((self.which, text))

    class _FakeMessageBox:
        class StandardButton:
            Close = 1
            Cancel = 2

        class Icon:
            Warning = 1

        def __init__(self, parent=None) -> None:
            self.parent = parent

        def setIcon(self, _icon) -> None:
            pass

        def setWindowTitle(self, _title: str) -> None:
            pass

        def setText(self, _text: str) -> None:
            pass

        def setInformativeText(self, _text: str) -> None:
            pass

        def setStandardButtons(self, _buttons) -> None:
            pass

        def setDefaultButton(self, _button) -> None:
            pass

        def button(self, which: int):
            return _FakeButton(which)

        def exec(self) -> int:
            return int(self.StandardButton.Close)

    monkeypatch.setattr(
        "lol_audio_unpack.gui.controllers.window_shell.QMessageBox",
        _FakeMessageBox,
    )

    assert confirm_force_close_running_tasks(parent="host") is True
    assert button_texts == [
        (_FakeMessageBox.StandardButton.Close, "关闭"),
        (_FakeMessageBox.StandardButton.Cancel, "取消"),
    ]


def test_force_quit_application_quits_app_and_schedules_fallback_exit() -> None:
    events: list[object] = []

    class _FakeApp:
        def setQuitOnLastWindowClosed(self, enabled: bool) -> None:
            events.append(("quit_on_last_window_closed", enabled))

    scheduled = []

    def _single_shot(delay_ms: int, callback) -> None:
        scheduled.append((delay_ms, callback))

    force_quit_application(
        app=_FakeApp(),
        delay_ms=FORCE_QUIT_DELAY_MS,
        single_shot_fn=_single_shot,
        exit_fn=lambda code: events.append(("exit", code)),
    )

    assert events == [("quit_on_last_window_closed", False)]
    assert scheduled[0][0] == FORCE_QUIT_DELAY_MS
    scheduled[0][1]()
    assert events == [("quit_on_last_window_closed", False), ("exit", 0)]
