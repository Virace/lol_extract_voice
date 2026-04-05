"""全局日志抽屉控制器测试。"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize

from lol_audio_unpack.gui.controllers.log_drawer import LogDrawerController


def test_log_drawer_controller_initializes_drawer_once() -> None:
    events: list[tuple[str, object]] = []

    class _FakeSignal:
        def connect(self, callback) -> None:
            events.append(("connect", callback))

    class _FakeDrawer:
        def __init__(self, host) -> None:
            events.append(("create", host))
            self.dev_console_requested = _FakeSignal()
            self.output_widget = object()

        def set_log_text(self, text: str) -> None:
            events.append(("set_log_text", text))

        def sync_host_rect(self, rect: QRect, *, animate: bool = False) -> None:
            events.append(("sync_host_rect", (rect, animate)))

    controller = LogDrawerController(
        drawer_factory=_FakeDrawer,
        host_rect_builder=lambda size, navigation_width: QRect(10, 0, size.width() - navigation_width, size.height()),
    )

    drawer = controller.ensure_drawer(
        host="window",
        current_log_text="boot",
        window_size=QSize(800, 600),
        navigation_width=120,
        on_dev_console_requested=lambda: None,
    )

    assert drawer is not None
    assert events == [
        ("create", "window"),
        ("set_log_text", "boot"),
        ("connect", controller._pending_dev_console_callback),
        ("sync_host_rect", (QRect(10, 0, 680, 600), False)),
    ]


def test_log_drawer_controller_updates_existing_drawer() -> None:
    events: list[tuple[str, object]] = []

    class _FakeSignal:
        def connect(self, _callback) -> None:
            pass

    class _FakeDrawer:
        def __init__(self, _host) -> None:
            self.dev_console_requested = _FakeSignal()
            self.output_widget = object()

        def set_log_text(self, text: str) -> None:
            events.append(("set_log_text", text))

        def append_log_lines(self, lines) -> None:
            events.append(("append_log_lines", tuple(lines)))

        def set_auto_collapse_enabled(self, enabled: bool) -> None:
            events.append(("set_auto_collapse", enabled))

        def sync_host_rect(self, rect: QRect, *, animate: bool = False) -> None:
            events.append(("sync_host_rect", (rect, animate)))

    controller = LogDrawerController(
        drawer_factory=_FakeDrawer,
        host_rect_builder=lambda size, navigation_width: QRect(0, 0, size.width() - navigation_width, size.height()),
    )
    controller.ensure_drawer(
        host="window",
        current_log_text="boot",
        window_size=QSize(800, 600),
        navigation_width=100,
        on_dev_console_requested=lambda: None,
    )
    events.clear()

    controller.append_log_lines(("a", "b"))
    controller.set_auto_collapse_enabled(True)
    controller.sync_host_rect(window_size=QSize(1024, 768), navigation_width=120)

    assert events == [
        ("append_log_lines", ("a", "b")),
        ("set_auto_collapse", True),
        ("sync_host_rect", (QRect(0, 0, 904, 768), False)),
    ]
