"""主窗口壳层 helper 测试。"""

from __future__ import annotations

import re
from pathlib import Path

from qfluentwidgets import NavigationItemPosition

from lol_audio_unpack.gui.controllers.contracts import RuntimeLoggingConfig
from lol_audio_unpack.gui.controllers.window_shell_controller import (
    apply_task_queue_busy_state,
    bind_shared_data_controller_signals,
    forward_selection_sync_feedback,
    register_navigation_items,
)


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


def test_register_navigation_items_adds_expected_entries() -> None:
    events: list[tuple[str, object]] = []

    class _FakeWindow:
        homeInterface = "home"
        executionInterface = "execution"
        overviewInterface = "overview"
        settingInterface = "setting"
        aboutInterface = "about"
        navigationInterface = type(
            "Nav",
            (),
            {
                "addSeparator": lambda self: events.append(("separator", None)),
                "addItem": lambda self, **kwargs: events.append(("item", kwargs)),
                "setExpandWidth": lambda self, width: events.append(("expand", width)),
            },
        )()

        def addSubInterface(self, interface, icon, text, position=None):
            events.append(("sub", (interface, text, position)))

        def toggleTheme(self):
            pass

    class _FakeSharedController:
        def refresh_shared_output_state(self):
            pass

    register_navigation_items(_FakeWindow(), _FakeSharedController())

    assert ("sub", ("home", "主页", None)) in events
    assert ("sub", ("execution", "执行中心", None)) in events
    assert ("sub", ("overview", "实体总览", None)) in events
    assert ("sub", ("setting", "全局设置", NavigationItemPosition.BOTTOM)) in events
    assert ("sub", ("about", "关于", NavigationItemPosition.BOTTOM)) in events
    assert any(event[0] == "item" and event[1]["routeKey"] == "refreshSharedData" for event in events)
    assert any(event[0] == "item" and event[1]["routeKey"] == "themeSwitcher" for event in events)
    assert ("expand", 180) in events


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
    assert ("exec_replace", ("champions", ({"id": 1},))) in events
    assert ("overview_replace", ("champions", ({"id": 1},))) in events
    assert ("notice", ("ok", "done", "success")) in events


def test_main_window_initializes_log_drawer_controller_before_super_init() -> None:
    window_source = Path("src/lol_audio_unpack/gui/window.py").read_text(encoding="utf-8")
    init_match = re.search(
        r"def __init__\(self\):(?P<body>.*?)(?:\n    def |\Z)",
        window_source,
        re.DOTALL,
    )
    assert init_match is not None
    body = init_match.group("body")

    assert "self._log_drawer_controller = LogDrawerController()" in body
    assert "super().__init__()" in body
    assert body.index("self._log_drawer_controller = LogDrawerController()") < body.index("super().__init__()")


def test_main_window_resize_event_guards_missing_navigation_interface() -> None:
    window_source = Path("src/lol_audio_unpack/gui/window.py").read_text(encoding="utf-8")
    resize_match = re.search(
        r"def resizeEvent\(self, event: QResizeEvent\) -> None:(?P<body>.*?)(?:\n    def |\Z)",
        window_source,
        re.DOTALL,
    )
    assert resize_match is not None
    body = resize_match.group("body")

    assert "navigation_interface = getattr(self, \"navigationInterface\", None)" in body
