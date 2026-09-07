"""开发控制台命令分发控制器。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint

from lol_audio_unpack.gui.components.dev_console import DevConsoleWindow
from lol_audio_unpack.gui.controllers.shared_data_demo import (
    DEFAULT_SHARED_DATA_DEMO_INTERVAL_MS,
    MAX_SHARED_DATA_DEMO_INTERVAL_MS,
    MIN_SHARED_DATA_DEMO_INTERVAL_MS,
)

DEV_CONSOLE_COMMAND_MIN_PARTS = 2
DEV_CONSOLE_QUEUE_FILL_PARTS = 3
DEV_CONSOLE_QUEUE_RESULT_PARTS = 3
DEV_CONSOLE_SHARED_PROGRESS_MAX_PARTS = 3


class DevConsoleController:
    """解析并执行开发控制台命令。"""

    def __init__(  # noqa: PLR0913
        self,
        *,
        queue_fill: Callable[[int], str],
        queue_clear: Callable[[], str],
        queue_inspect: Callable[[], str],
        queue_result: Callable[[str], str] | None = None,
        shared_progress: Callable[[int], str] | None = None,
        shared_stop: Callable[[], str] | None = None,
        shared_inspect: Callable[[], str] | None = None,
        console_factory=DevConsoleWindow,
    ) -> None:
        """初始化开发控制台命令控制器。

        Args:
            queue_fill: 填充 mock 队列的执行函数。
            queue_clear: 清空 mock 队列的执行函数。
            queue_inspect: 返回当前队列诊断文本的执行函数。
            queue_result: 注入受控 typed terminal result 的可选执行函数。
            shared_progress: 启动共享进度 mock 的可选执行函数。
            shared_stop: 停止共享进度 mock 的可选执行函数。
            shared_inspect: 返回共享进度 mock 状态的可选执行函数。
        """
        self._queue_fill = queue_fill
        self._queue_clear = queue_clear
        self._queue_inspect = queue_inspect
        self._queue_result = queue_result
        self._shared_progress = shared_progress
        self._shared_stop = shared_stop
        self._shared_inspect = shared_inspect
        self._console_factory = console_factory
        self._console = None

    def run_command(self, command: str) -> tuple[str, ...]:
        """解析并执行一条开发控制台命令。

        Args:
            command: 原始命令文本。

        Returns:
            tuple[str, ...]: 供控制台逐行追加的输出文本。

        Raises:
            ValueError: 当命令格式非法或关键字未知时抛出。
        """
        normalized = command.strip()
        if not normalized:
            raise ValueError("空命令，输入 help 查看可用命令。")

        parts = normalized.split()
        keyword = parts[0].lower()
        if keyword == "help":
            return (
                "可用命令:",
                "help",
                "queue fill <n>",
                "queue clear",
                "queue inspect",
                "queue result <success|partial|failed|cancelled>",
                "shared progress [interval_ms]",
                "shared stop",
                "shared inspect",
            )

        if len(parts) < DEV_CONSOLE_COMMAND_MIN_PARTS:
            raise ValueError("未知命令，输入 help 查看可用命令。")

        if keyword == "shared":
            return self._run_shared_command(parts)
        if keyword != "queue":
            raise ValueError("未知命令，输入 help 查看可用命令。")

        action = parts[1].lower()
        if action == "fill":
            if len(parts) != DEV_CONSOLE_QUEUE_FILL_PARTS or not parts[2].isdigit():
                raise ValueError("queue fill 需要一个正整数参数。")
            return (self._queue_fill(int(parts[2])),)
        if action == "clear":
            return (self._queue_clear(),)
        if action == "inspect":
            return tuple(self._queue_inspect().splitlines())
        if action == "result":
            if len(parts) != DEV_CONSOLE_QUEUE_RESULT_PARTS or self._queue_result is None:
                raise ValueError("queue result 需要一个可用的终态参数。")
            return (self._queue_result(parts[2].lower()),)

        raise ValueError("未知 queue 子命令，输入 help 查看可用命令。")

    def _run_shared_command(self, parts: list[str]) -> tuple[str, ...]:
        """解析并执行共享进度 mock 子命令。"""
        action = parts[1].lower()
        if action == "progress":
            if self._shared_progress is None or len(parts) > DEV_CONSOLE_SHARED_PROGRESS_MAX_PARTS:
                raise ValueError("shared progress 当前不可用或参数格式错误。")
            if len(parts) == DEV_CONSOLE_SHARED_PROGRESS_MAX_PARTS:
                if not parts[2].isdigit():
                    raise ValueError("shared progress 的间隔必须为正整数毫秒值。")
                interval_ms = int(parts[2])
            else:
                interval_ms = DEFAULT_SHARED_DATA_DEMO_INTERVAL_MS
            if not MIN_SHARED_DATA_DEMO_INTERVAL_MS <= interval_ms <= MAX_SHARED_DATA_DEMO_INTERVAL_MS:
                raise ValueError(
                    "shared progress 的间隔必须在 "
                    f"{MIN_SHARED_DATA_DEMO_INTERVAL_MS}-{MAX_SHARED_DATA_DEMO_INTERVAL_MS} ms 之间。"
                )
            return (self._shared_progress(interval_ms),)
        if action == "stop" and len(parts) == DEV_CONSOLE_COMMAND_MIN_PARTS and self._shared_stop is not None:
            return (self._shared_stop(),)
        if action == "inspect" and len(parts) == DEV_CONSOLE_COMMAND_MIN_PARTS and self._shared_inspect is not None:
            return tuple(self._shared_inspect().splitlines())
        raise ValueError("未知 shared 子命令，输入 help 查看可用命令。")

    def handle_submitted_command(self, console, command: str) -> None:
        """执行开发控制台命令并回写输出。

        Args:
            console: 当前开发控制台窗口，需要提供 ``append_output`` 方法。
            command: 原始命令文本。
        """
        console.append_output(f"> {command}")
        try:
            output_lines = self.run_command(command)
        except ValueError as exc:
            console.append_output(f"ERROR: {exc}")
            return

        for line in output_lines:
            console.append_output(line)

    def show_console(self, console, host) -> None:
        """定位并显示开发控制台窗口。"""
        if console.width() <= 0 or console.height() <= 0:
            console.resize(console.sizeHint())

        offset_x = max(host.width() - console.width() - 32, 0)
        offset_y = max(host.height() - console.height() - 48, 0)
        anchor = host.mapToGlobal(QPoint(offset_x, offset_y))
        console.move(anchor)
        console.show()
        console.raise_()
        console.activateWindow()
        console.focus_command_input()

    def ensure_console(self, host):
        """确保开发控制台窗口存在并完成命令回调绑定。"""
        if self._console is None:
            self._console = self._console_factory(host)
            self._console.command_submitted.connect(
                lambda command: self.handle_submitted_command(self._console, command)
            )
        return self._console

    def show_console_window(self, host) -> None:
        """确保开发控制台存在并显示到宿主窗口右下角。"""
        console = self.ensure_console(host)
        self.show_console(console, host)
