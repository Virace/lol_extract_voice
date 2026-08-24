"""验证全局进度条宿主的可观察状态切换。"""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from lol_audio_unpack.gui.components.global_progress_strip import (
    GlobalProgressStripCoordinator,
    GlobalProgressStripHost,
    GlobalProgressStripState,
    build_shared_data_progress_strip_state,
)
from lol_audio_unpack.gui.shared_data import SharedDataPhase, SharedDataProgress, SharedDataState

RESUMED_PROGRESS_CURRENT = 2100
HALF_PROGRESS = 0.5


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


def test_progress_host_previews_terminal_progress_before_delayed_hide(qtbot) -> None:
    """带摘要的隐藏态应先更新条带，再按既有延时自动隐藏。"""
    _parent, host = _show_host(qtbot)
    host.set_state(_running_state(), animate=False)
    terminal_state = GlobalProgressStripState(
        visible=False,
        title_text="任务已结束",
        detail_text="部分完成：成功 1，失败 1",
        progress_current=1,
        progress_total=2,
        status_text="1/2",
    )

    host.set_state(terminal_state, animate=False)
    qtbot.wait(100)

    assert host.current_state().visible is True
    assert host.strip_widget().target_progress_value() == HALF_PROGRESS
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


def test_shared_progress_uses_full_track_and_keeps_up_with_latest_count(qtbot) -> None:
    """隐藏操作区不能缩短轨道，高频进度也必须立即对齐最新计数。"""
    _parent, host = _show_host(qtbot)
    strip = host.strip_widget()
    for current in range(1, 116):
        host.set_state(
            GlobalProgressStripState(
                visible=True,
                progress_current=current,
                progress_total=173,
                cancellable=False,
            ),
            animate=True,
        )

    expected_ratio = 115 / 173
    assert strip.debug_action_rect().isNull()
    assert strip.target_progress_value() == pytest.approx(expected_ratio)
    assert strip.display_progress_value() == pytest.approx(expected_ratio)
    assert strip.debug_fill_rect().width() == pytest.approx(strip.debug_outer_rect().width() * expected_ratio)


def test_progress_strip_stop_button_emits_signal(qtbot) -> None:
    """运行态的停止按钮应向任务控制层发出停止请求。"""
    _parent, host = _show_host(qtbot)
    host.set_state(_running_state(), animate=False)
    strip = host.strip_widget()
    stop_events: list[bool] = []
    strip.stop_requested.connect(lambda: stop_events.append(True))

    qtbot.mouseClick(strip.stop_button(), Qt.MouseButton.LeftButton)

    assert stop_events == [True]


def test_progress_host_hides_strip_without_releasing_reserved_space(qtbot) -> None:
    """首页抑制共享条带时应保持宿主高度，避免切页期间触发布局重排。"""
    _parent, host = _show_host(qtbot)
    host.set_state(_running_state(), animate=False)
    visible_height = host.get_host_height()

    host.set_state(
        GlobalProgressStripState(cancellable=False, reserve_space=True),
        animate=True,
    )
    qtbot.wait(300)

    assert host.get_host_height() == visible_height
    assert host.strip_widget().isVisible() is False


def test_shared_data_progress_state_distinguishes_unknown_and_measured_work() -> None:
    """共享准备的未知阶段与可测阶段不能使用同一种伪百分比。"""
    unknown = build_shared_data_progress_strip_state(SharedDataState(SharedDataPhase.CHECKING, 1))
    measured = build_shared_data_progress_strip_state(
        SharedDataState(
            SharedDataPhase.PREPARING,
            1,
            progress=SharedDataProgress(
                1,
                "champion_banks",
                "advanced",
                current=42,
                total=173,
            ),
        )
    )

    assert unknown.indeterminate is True
    assert unknown.cancellable is False
    assert measured.indeterminate is False
    assert (measured.progress_current, measured.progress_total) == (42, 173)
    assert measured.status_text == "英雄数据 · 42/173"


def test_global_progress_coordinator_prioritizes_user_task_then_resumes_shared_state() -> None:
    """用户任务短暂重叠时优先展示，结束后恢复最新 generation 的共享状态。"""
    published = []
    coordinator = GlobalProgressStripCoordinator(published.append)
    task_state = _running_state()
    coordinator.set_task_state(task_state)
    coordinator.set_shared_data_state(SharedDataState(SharedDataPhase.CHECKING, 2))
    coordinator.set_shared_data_state(SharedDataState(SharedDataPhase.CHECKING, 1))

    assert coordinator.current_state() == task_state

    coordinator.set_task_state(GlobalProgressStripState(title_text="任务已完成"))

    assert coordinator.current_state().visible is True
    assert coordinator.current_state().title_text == "正在检查实体数据…"
    assert coordinator.current_state().indeterminate is True


def test_global_progress_coordinator_suppresses_only_shared_progress_on_home() -> None:
    """首页只隐藏同源共享进度，用户任务仍保持全局可见。"""
    published = []
    coordinator = GlobalProgressStripCoordinator(published.append)
    coordinator.set_shared_data_state(SharedDataState(SharedDataPhase.CHECKING, 2))

    coordinator.set_shared_data_progress_suppressed(True)

    assert coordinator.current_state().visible is False
    assert coordinator.current_state().reserve_space is True
    coordinator.set_task_state(_running_state())
    assert coordinator.current_state().visible is True
    assert coordinator.current_state().cancellable is True

    coordinator.set_task_state(GlobalProgressStripState(title_text="任务已完成"))
    assert coordinator.current_state().visible is False
    coordinator.set_shared_data_progress_suppressed(False)
    assert coordinator.current_state().visible is True
    assert coordinator.current_state().title_text == "正在检查实体数据…"
