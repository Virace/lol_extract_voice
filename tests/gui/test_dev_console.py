"""测试隐藏开发控制台与执行中心调试命令。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from lol_audio_unpack.gui.window import MainWindow

MOCK_QUEUE_COUNT = 5


def test_main_window_ctrl_click_log_title_opens_dev_console(qtbot, monkeypatch) -> None:
    """按住 Ctrl 点击日志详情标题后应打开隐藏开发控制台。"""
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window._global_log_drawer.set_expanded(True, animate=False)
    app.processEvents()

    QTest.mouseClick(window._global_log_drawer._title, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()

    assert window._dev_console is not None
    assert window._dev_console.isVisible()


def test_dev_console_queue_commands_can_fill_and_inspect_execution_queue(qtbot, monkeypatch) -> None:
    """开发控制台命令应能填充 mock 队列并输出当前容器信息。"""
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window._show_dev_console()
    app.processEvents()

    console = window._dev_console
    assert console is not None

    console.command_input.setText(f"queue fill {MOCK_QUEUE_COUNT}")
    QTest.keyClick(console.command_input, Qt.Key.Key_Return)
    app.processEvents()

    assert window.executionInterface._draft_queue_size() == MOCK_QUEUE_COUNT

    console.command_input.setText("queue inspect")
    QTest.keyClick(console.command_input, Qt.Key.Key_Return)
    app.processEvents()

    output_text = console.output_text()
    assert f"queue_count={MOCK_QUEUE_COUNT}" in output_text
    assert "visible_rows=3" in output_text
    assert "queue_height=" in output_text
