"""验证全局进度条宿主的可观察状态切换。"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from lol_audio_unpack.gui.components.global_progress_strip import (
    GlobalProgressStripHost,
    GlobalProgressStripState,
)

RESUMED_PROGRESS_CURRENT = 2100


def _running_state() -> GlobalProgressStripState:
    """返回代表下载中的全局进度状态。"""
    return GlobalProgressStripState(
        visible=True,
        title_text="stream.x64.x-none.dat (2/4)",
        detail_text="1.63 GB / 2.60 GB",
        progress_current=1630,
        progress_total=2600,
        rate_text="71.20 MB/s",
        status_text="下载中",
        paused=False,
    )


def _show_host(qtbot) -> tuple[QWidget, GlobalProgressStripHost]:
    """创建并显示独立的进度条宿主。"""
    parent = QWidget()
    host = GlobalProgressStripHost(parent)
    qtbot.addWidget(parent)
    parent.resize(1120, 120)
    host.setGeometry(parent.rect())
    parent.show()
    qtbot.waitUntil(parent.isVisible)
    return parent, host


def test_progress_host_waits_before_hiding_after_completion(qtbot) -> None:
    """完成态应短暂保留，随后自动隐藏。"""
    _parent, host = _show_host(qtbot)
    host.set_state(_running_state(), animate=False)
    qtbot.waitUntil(lambda: host.current_state().visible)

    host.set_state(GlobalProgressStripState(), animate=False)
    qtbot.wait(300)

    assert host.current_state().visible is True
    qtbot.waitUntil(lambda: not host.current_state().visible, timeout=2200)


def test_progress_host_cancels_pending_hide_when_new_progress_arrives(qtbot) -> None:
    """隐藏等待期间出现新进度时，应保持可见并采用新状态。"""
    _parent, host = _show_host(qtbot)
    host.set_state(_running_state(), animate=False)
    qtbot.waitUntil(lambda: host.current_state().visible)

    host.set_state(GlobalProgressStripState(), animate=False)
    qtbot.wait(300)
    host.set_state(replace(_running_state(), progress_current=RESUMED_PROGRESS_CURRENT), animate=False)
    qtbot.wait(1700)

    assert host.current_state().visible is True
    assert host.current_state().progress_current == RESUMED_PROGRESS_CURRENT


def test_progress_strip_first_show_snaps_progress_to_target(qtbot) -> None:
    """首次显示应直接落到真实进度，避免从零误导用户。"""
    _parent, host = _show_host(qtbot)

    host.set_state(_running_state(), animate=True)

    strip = host.strip_widget()
    assert strip.display_progress_value() == strip.target_progress_value()


def test_progress_strip_stop_button_emits_signal(qtbot) -> None:
    """运行态的停止按钮应向任务控制层发出停止请求。"""
    _parent, host = _show_host(qtbot)
    host.set_state(_running_state(), animate=False)
    strip = host.strip_widget()
    stop_events: list[bool] = []
    strip.stop_requested.connect(lambda: stop_events.append(True))

    qtbot.mouseClick(strip.stop_button(), Qt.MouseButton.LeftButton)

    assert stop_events == [True]
