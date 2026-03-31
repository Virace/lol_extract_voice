"""开发控制台命令控制器测试。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint

from lol_audio_unpack.gui.controllers.dev_console_controller import DevConsoleController


def test_dev_console_controller_help_lists_available_commands() -> None:
    controller = DevConsoleController(
        queue_fill=lambda count: f"fill {count}",
        queue_clear=lambda: "clear",
        queue_inspect=lambda: "inspect",
    )

    assert controller.run_command("help") == (
        "可用命令:",
        "help",
        "queue fill <n>",
        "queue clear",
        "queue inspect",
    )


def test_dev_console_controller_dispatches_queue_actions() -> None:
    controller = DevConsoleController(
        queue_fill=lambda count: f"fill {count}",
        queue_clear=lambda: "clear",
        queue_inspect=lambda: "first\nsecond",
    )

    assert controller.run_command("queue fill 3") == ("fill 3",)
    assert controller.run_command("queue clear") == ("clear",)
    assert controller.run_command("queue inspect") == ("first", "second")


def test_dev_console_controller_rejects_unknown_command() -> None:
    controller = DevConsoleController(
        queue_fill=lambda count: f"fill {count}",
        queue_clear=lambda: "clear",
        queue_inspect=lambda: "inspect",
    )

    with pytest.raises(ValueError, match="未知命令"):
        controller.run_command("noop")


def test_dev_console_controller_handle_submitted_command_appends_output_lines() -> None:
    outputs: list[str] = []

    class _FakeConsole:
        def append_output(self, text: str) -> None:
            outputs.append(text)

    controller = DevConsoleController(
        queue_fill=lambda count: f"fill {count}",
        queue_clear=lambda: "clear",
        queue_inspect=lambda: "inspect",
    )

    controller.handle_submitted_command(_FakeConsole(), "queue clear")

    assert outputs == ["> queue clear", "clear"]


def test_dev_console_controller_handle_submitted_command_reports_error() -> None:
    outputs: list[str] = []

    class _FakeConsole:
        def append_output(self, text: str) -> None:
            outputs.append(text)

    controller = DevConsoleController(
        queue_fill=lambda count: f"fill {count}",
        queue_clear=lambda: "clear",
        queue_inspect=lambda: "inspect",
    )

    controller.handle_submitted_command(_FakeConsole(), "oops")

    assert outputs == ["> oops", "ERROR: 未知命令，输入 help 查看可用命令。"]


def test_dev_console_controller_show_console_positions_and_focuses_window() -> None:
    events: list[tuple[str, object]] = []

    class _FakeConsole:
        def __init__(self) -> None:
            self._width = 0
            self._height = 0

        def width(self) -> int:
            return self._width

        def height(self) -> int:
            return self._height

        def sizeHint(self):
            return (320, 200)

        def resize(self, size) -> None:
            self._width, self._height = size
            events.append(("resize", size))

        def move(self, point) -> None:
            events.append(("move", point))

        def show(self) -> None:
            events.append(("show", None))

        def raise_(self) -> None:
            events.append(("raise", None))

        def activateWindow(self) -> None:
            events.append(("activate", None))

        def focus_command_input(self) -> None:
            events.append(("focus", None))

    class _FakeHost:
        def width(self) -> int:
            return 900

        def height(self) -> int:
            return 700

        def mapToGlobal(self, point: QPoint) -> QPoint:
            return point

    controller = DevConsoleController(
        queue_fill=lambda count: f"fill {count}",
        queue_clear=lambda: "clear",
        queue_inspect=lambda: "inspect",
    )
    console = _FakeConsole()

    controller.show_console(console, _FakeHost())

    assert ("resize", (320, 200)) in events
    assert ("move", QPoint(548, 452)) in events
    assert events[-4:] == [
        ("show", None),
        ("raise", None),
        ("activate", None),
        ("focus", None),
    ]


def test_dev_console_controller_show_console_window_creates_console_once() -> None:
    created: list[object] = []
    hosts: list[object] = []

    class _FakeConsole:
        def __init__(self, host) -> None:
            created.append(host)
            self._width = 100
            self._height = 100
            self.command_submitted = _FakeSignal()

        def width(self) -> int:
            return self._width

        def height(self) -> int:
            return self._height

        def sizeHint(self):
            return (100, 100)

        def resize(self, size) -> None:
            self._width, self._height = size

        def move(self, _point) -> None:
            pass

        def show(self) -> None:
            hosts.append("show")

        def raise_(self) -> None:
            pass

        def activateWindow(self) -> None:
            pass

        def focus_command_input(self) -> None:
            pass

        def append_output(self, _text: str) -> None:
            pass

    class _FakeSignal:
        def connect(self, _callback) -> None:
            pass

    class _FakeHost:
        def width(self) -> int:
            return 900

        def height(self) -> int:
            return 700

        def mapToGlobal(self, point: QPoint) -> QPoint:
            return point

    controller = DevConsoleController(
        queue_fill=lambda count: f"fill {count}",
        queue_clear=lambda: "clear",
        queue_inspect=lambda: "inspect",
        console_factory=_FakeConsole,
    )
    host = _FakeHost()

    controller.show_console_window(host)
    controller.show_console_window(host)

    assert created == [host]
    assert hosts == ["show", "show"]
