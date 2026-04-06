"""全局日志抽屉控制器。"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QRect, QSize

from lol_audio_unpack.gui.components.log_drawer import (
    GlobalLogDrawer,
    _build_log_panel_host_rect,
)


class LogDrawerController:
    """负责全局日志抽屉的实例持有与壳层同步。"""

    def __init__(
        self,
        *,
        drawer_factory=GlobalLogDrawer,
        host_rect_builder: Callable[[QSize, int], QRect] = _build_log_panel_host_rect,
    ) -> None:
        """初始化日志抽屉控制器。"""
        self._drawer_factory = drawer_factory
        self._host_rect_builder = host_rect_builder
        self._drawer = None
        self._pending_dev_console_callback = None

    @property
    def drawer(self):
        """返回当前日志抽屉实例。"""
        return self._drawer

    @property
    def output_widget(self):
        """返回日志抽屉输出控件。"""
        return None if self._drawer is None else self._drawer.output_widget

    def ensure_drawer(
        self,
        *,
        host,
        current_log_text: str,
        window_size: QSize,
        navigation_width: int,
        on_dev_console_requested,
    ):
        """确保日志抽屉实例存在并完成首次初始化。"""
        if self._drawer is None:
            self._drawer = self._drawer_factory(host)
            self._pending_dev_console_callback = on_dev_console_requested
            self._drawer.set_log_text(current_log_text)
            self._drawer.dev_console_requested.connect(self._pending_dev_console_callback)
            self._drawer.sync_host_rect(
                self._host_rect_builder(window_size, navigation_width),
                animate=False,
            )
        return self._drawer

    def append_log_lines(self, lines: Sequence[str]) -> None:
        """向日志抽屉追加一批日志。"""
        if self._drawer is None:
            return
        self._drawer.append_log_lines(lines)

    def set_auto_collapse_enabled(self, enabled: bool) -> None:
        """应用日志抽屉点击外部自动收起设置。"""
        if self._drawer is None:
            return
        self._drawer.set_auto_collapse_enabled(enabled)

    def sync_host_rect(self, *, window_size: QSize, navigation_width: int) -> None:
        """按当前窗口尺寸与导航宽度刷新抽屉宿主区。"""
        if self._drawer is None:
            return
        self._drawer.sync_host_rect(
            self._host_rect_builder(window_size, navigation_width),
            animate=False,
        )
