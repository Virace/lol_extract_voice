"""全局进度条 demo 页交互测试。"""

from __future__ import annotations

from PySide6.QtCore import Qt

from scripts.demo_global_progress_strip import GlobalProgressStripDemoWindow

EXPECTED_INITIAL_TITLE = "stream.x64.x-none.dat (2/4)"
EXPECTED_UPDATED_TITLE = "champion_103_audio.wpk"
EXPECTED_UPDATED_PROGRESS = 73
EXPECTED_PROGRESS_TOTAL = 100
EXPECTED_RESET_PROGRESS = 63
EXPECTED_CUSTOM_SWEEP_DURATION_MS = 2600
EXPECTED_CUSTOM_OUTER_RADIUS = 0
EXPECTED_CUSTOM_INNER_RADIUS = 0
EXPECTED_CUSTOM_BUTTON_RADIUS = 0


def test_demo_window_show_and_hide_buttons_toggle_host_visibility(qtbot) -> None:
    window = GlobalProgressStripDemoWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    assert window.progress_host.height() == 0

    qtbot.mouseClick(window.show_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.progress_host.height() > 0)

    qtbot.mouseClick(window.hide_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.progress_host.height() == 0)


def test_demo_window_progress_controls_update_state(qtbot) -> None:
    window = GlobalProgressStripDemoWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    qtbot.mouseClick(window.show_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.progress_host.height() > 0)

    window.title_input.setText(EXPECTED_UPDATED_TITLE)
    window.progress_slider.setValue(EXPECTED_UPDATED_PROGRESS)
    window.pause_checkbox.setChecked(True)
    window.rate_input.setText("88.80 MB/s")
    window.status_input.setText("已暂停")
    qtbot.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)

    state = window.progress_host.current_state()
    assert state.title_text == EXPECTED_UPDATED_TITLE
    assert state.progress_current == EXPECTED_UPDATED_PROGRESS
    assert state.progress_total == EXPECTED_PROGRESS_TOTAL
    assert state.paused is True
    assert state.rate_text == "88.80 MB/s"
    assert state.status_text == "已暂停"


def test_demo_window_reset_restores_default_state(qtbot) -> None:
    window = GlobalProgressStripDemoWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    window.title_input.setText(EXPECTED_UPDATED_TITLE)
    window.progress_slider.setValue(42)
    window.pause_checkbox.setChecked(True)
    qtbot.mouseClick(window.reset_button, Qt.MouseButton.LeftButton)

    assert window.title_input.text() == EXPECTED_INITIAL_TITLE
    assert window.progress_slider.value() == EXPECTED_RESET_PROGRESS
    assert window.pause_checkbox.isChecked() is False


def test_demo_window_visual_controls_update_theme_and_sweep_duration(qtbot) -> None:
    window = GlobalProgressStripDemoWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    qtbot.mouseClick(window.show_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.progress_host.height() > 0)

    window.theme_mode_combo.setCurrentText("浅色")
    window.sweep_duration_slider.setValue(EXPECTED_CUSTOM_SWEEP_DURATION_MS)
    qtbot.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)

    state = window.progress_host.current_state()
    assert state.theme_mode == "light"
    assert state.sweep_duration_ms == EXPECTED_CUSTOM_SWEEP_DURATION_MS


def test_demo_window_radius_controls_update_state(qtbot) -> None:
    window = GlobalProgressStripDemoWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    window.outer_radius_slider.setValue(EXPECTED_CUSTOM_OUTER_RADIUS)
    window.inner_radius_slider.setValue(EXPECTED_CUSTOM_INNER_RADIUS)
    window.button_radius_slider.setValue(EXPECTED_CUSTOM_BUTTON_RADIUS)
    qtbot.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)

    state = window.progress_host.current_state()
    assert state.outer_radius == EXPECTED_CUSTOM_OUTER_RADIUS
    assert state.inner_radius == EXPECTED_CUSTOM_INNER_RADIUS
    assert state.button_radius == EXPECTED_CUSTOM_BUTTON_RADIUS


def test_demo_window_strip_buttons_toggle_pause_and_stop(qtbot) -> None:
    window = GlobalProgressStripDemoWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    qtbot.mouseClick(window.show_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.progress_host.height() > 0)

    qtbot.mouseClick(window.progress_host.strip_widget().pause_button(), Qt.MouseButton.LeftButton)
    assert window.pause_checkbox.isChecked() is True
    assert window.status_input.text() == "已暂停"

    qtbot.mouseClick(window.progress_host.strip_widget().stop_button(), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.progress_host.height() == 0)


def test_demo_window_progress_advance_uses_animation(qtbot) -> None:
    window = GlobalProgressStripDemoWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)

    qtbot.mouseClick(window.show_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.progress_host.height() > 0)

    before_display = window.progress_host.strip_widget().display_progress_value()
    qtbot.mouseClick(window.advance_button, Qt.MouseButton.LeftButton)

    after_target = window.progress_host.strip_widget().target_progress_value()
    after_display = window.progress_host.strip_widget().display_progress_value()

    assert after_target > before_display
    assert after_display < after_target
