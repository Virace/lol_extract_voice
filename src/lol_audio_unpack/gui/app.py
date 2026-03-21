"""Fluent GUI 的启动入口。"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from .window import MainWindow


def start_gui_app(argv: Sequence[str] | None = None) -> int:
    """启动 Fluent GUI 应用。

    Args:
        argv: 可选的命令行参数列表。

    Returns:
        Qt 应用的退出码。
    """
    args = list(argv) if argv is not None else sys.argv
    app = QApplication(args)
    app.setApplicationName("lol_audio_unpack GUI")
    app.setOrganizationName("Virace")
    setTheme(Theme.DARK)

    window = MainWindow()
    window.show()
    return app.exec()
