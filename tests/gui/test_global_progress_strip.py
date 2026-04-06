"""全局底部进度条组件回归测试。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QApplication, QFrame, QScrollArea, QVBoxLayout, QWidget
from qfluentwidgets import qconfig

from lol_audio_unpack.gui.components.global_progress_strip import (
    DEFAULT_PROGRESS_SWEEP_ANIMATION_MS,
    PROGRESS_ACTION_GAP,
    GlobalProgressStripHost,
    GlobalProgressStripState,
)
from lol_audio_unpack.gui.resources import assets
from lol_audio_unpack.gui.theme import apply_accent_preset, resolve_progress_palette

WINDOW_WIDTH = 1120
WINDOW_HEIGHT = 800
BOTTOM_CARD_HEIGHT = 120
EXPECTED_CUSTOM_SWEEP_DURATION_MS = 2600
EXPECTED_DEFAULT_SWEEP_DURATION_MS = 4600
EXPECTED_DEFAULT_SWEEP_IDLE_DELAY_MS = 800
EXPECTED_STRIP_HEIGHT = 44
EXPECTED_STATUS_RIGHT_PADDING = 10.0
EXPECTED_TITLE_DETAIL_MAX_GAP = 4
EXPECTED_TITLE_FONT_PIXEL_SIZE = 13


@contextmanager
def _restore_theme_color():
    """在测试结束后恢复 qconfig 主题色。"""
    previous_color = qconfig.themeColor.value
    try:
        yield
    finally:
        qconfig.set(qconfig.themeColor, previous_color)


class _ProgressStripShellDemo(QWidget):
    """用于测试底部进度条的简化壳层宿主。"""

    def __init__(self) -> None:
        super().__init__()
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        self.page = QWidget()
        page_layout = QVBoxLayout(self.page)
        page_layout.setContentsMargins(24, 24, 24, 24)
        page_layout.addStretch(1)

        self.bottom_card = QFrame(self.page)
        self.bottom_card.setFixedHeight(BOTTOM_CARD_HEIGHT)
        page_layout.addWidget(self.bottom_card)

        self.scroll_area.setWidget(self.page)

        self.progress_host = GlobalProgressStripHost(self)

        root_layout.addWidget(self.scroll_area, 1)
        root_layout.addWidget(self.progress_host, 0)

    def sync_content_height_to_viewport(self) -> None:
        """让页面内容高度与当前 viewport 等高。"""
        self.page.setFixedWidth(self.scroll_area.viewport().width())
        self.page.setFixedHeight(self.scroll_area.viewport().height())


def _wait_until_visible(qtbot, widget: QWidget) -> None:
    """等待控件进入可见状态。"""
    qtbot.waitUntil(widget.isVisible)


def _running_state() -> GlobalProgressStripState:
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


def test_progress_action_icons_exist_in_resource_catalog() -> None:
    """进度条动作图标应由统一资源入口提供。"""
    assert assets.icons.PAUSE.path().endswith("pause-solid-full.svg")
    assert assets.icons.PLAY.path().endswith("play-solid-full.svg")
    assert assets.icons.STOP.path().endswith("stop-solid-full.svg")


def test_global_progress_strip_does_not_keep_local_action_icon_enum() -> None:
    """全局进度条模块不应继续保留本地动作图标枚举。"""
    source = Path("src/lol_audio_unpack/gui/components/global_progress_strip.py").read_text(encoding="utf-8")

    assert "ProgressActionIcon" not in source


def test_progress_host_hidden_keeps_viewport_without_extra_scroll(qtbot, tmp_path: Path) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)
    shell.sync_content_height_to_viewport()

    screenshot_path = tmp_path / "progress-hidden.png"
    shell.grab().save(str(screenshot_path))

    assert screenshot_path.exists()
    assert shell.progress_host.height() == 0
    assert shell.scroll_area.verticalScrollBar().maximum() == 0


def test_progress_host_visible_reduces_viewport_but_keeps_content_height(qtbot, tmp_path: Path) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)
    shell.sync_content_height_to_viewport()
    initial_content_height = shell.page.height()
    initial_viewport_height = shell.scroll_area.viewport().height()

    shell.progress_host.set_state(_running_state(), animate=False)
    qtbot.waitUntil(
        lambda: shell.progress_host.height() > 0
        and shell.scroll_area.viewport().height() < initial_viewport_height
    )

    screenshot_path = tmp_path / "progress-visible.png"
    shell.grab().save(str(screenshot_path))

    assert screenshot_path.exists()
    assert shell.page.height() == initial_content_height
    assert shell.scroll_area.viewport().height() < initial_viewport_height
    assert shell.scroll_area.verticalScrollBar().maximum() > 0
    assert shell.progress_host.height() == shell.progress_host.strip_widget().height()


def test_progress_host_waits_before_hiding_after_completion(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    shell.progress_host.set_state(_running_state(), animate=False)
    qtbot.waitUntil(lambda: shell.progress_host.height() > 0)

    shell.progress_host.set_state(GlobalProgressStripState(), animate=False)

    qtbot.wait(300)

    assert shell.progress_host.height() > 0

    qtbot.waitUntil(lambda: shell.progress_host.height() == 0, timeout=2200)


def test_progress_host_cancels_pending_hide_when_new_progress_arrives(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    shell.progress_host.set_state(_running_state(), animate=False)
    qtbot.waitUntil(lambda: shell.progress_host.height() > 0)

    shell.progress_host.set_state(GlobalProgressStripState(), animate=False)
    qtbot.wait(300)

    shell.progress_host.set_state(replace(_running_state(), progress_current=2100), animate=False)
    qtbot.wait(1700)

    assert shell.progress_host.height() > 0
    assert shell.progress_host.current_state().visible is True


def test_progress_host_paused_state_desaturates_color_but_keeps_sweep_running(qtbot, tmp_path: Path) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    running_state = _running_state()
    shell.progress_host.set_state(running_state, animate=False)
    running_color = shell.progress_host.strip_widget().current_fill_color()

    paused_state = replace(running_state, paused=True, status_text="已暂停")
    shell.progress_host.set_state(paused_state, animate=False)
    qtbot.wait(80)
    paused_color = shell.progress_host.strip_widget().current_fill_color()

    screenshot_path = tmp_path / "progress-paused.png"
    shell.grab().save(str(screenshot_path))

    assert screenshot_path.exists()
    assert paused_color.hue() == running_color.hue()
    assert paused_color.saturation() < running_color.saturation()
    assert shell.progress_host.strip_widget().is_sweep_animating()


def test_progress_updates_do_not_stop_sweep_animation(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    running_state = _running_state()
    shell.progress_host.set_state(running_state, animate=False)
    qtbot.wait(120)
    phase_before = shell.progress_host.strip_widget().sweep_phase()

    shell.progress_host.set_state(replace(running_state, progress_current=2100), animate=False)
    qtbot.wait(120)
    phase_after = shell.progress_host.strip_widget().sweep_phase()

    assert shell.progress_host.strip_widget().is_sweep_animating()
    assert phase_before != phase_after


def test_progress_updates_do_not_restart_host_height_animation_when_visibility_is_unchanged(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    running_state = _running_state()
    shell.progress_host.set_state(running_state, animate=False)

    updated_state = replace(running_state, progress_current=2100)
    shell.progress_host.set_state(updated_state, animate=True)

    assert shell.progress_host._height_animation.state() == shell.progress_host._height_animation.State.Stopped


def test_progress_strip_uses_configurable_sweep_duration(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    custom_state = replace(_running_state(), sweep_duration_ms=EXPECTED_CUSTOM_SWEEP_DURATION_MS)
    shell.progress_host.set_state(custom_state, animate=False)

    assert shell.progress_host.strip_widget().current_sweep_duration_ms() == EXPECTED_CUSTOM_SWEEP_DURATION_MS
    assert DEFAULT_PROGRESS_SWEEP_ANIMATION_MS == EXPECTED_DEFAULT_SWEEP_DURATION_MS
    assert shell.progress_host.strip_widget().current_sweep_idle_delay_ms() == EXPECTED_DEFAULT_SWEEP_IDLE_DELAY_MS


def test_progress_strip_theme_mode_updates_text_contrast(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    dark_state = replace(_running_state(), theme_mode="dark")
    shell.progress_host.set_state(dark_state, animate=False)
    dark_meta = shell.progress_host.strip_widget().current_meta_text_color()
    dark_track = shell.progress_host.strip_widget().current_track_background_color()

    light_state = replace(_running_state(), theme_mode="light")
    shell.progress_host.set_state(light_state, animate=False)
    light_meta = shell.progress_host.strip_widget().current_meta_text_color()
    light_track = shell.progress_host.strip_widget().current_track_background_color()

    assert dark_meta.lightness() > dark_track.lightness()
    assert light_meta.lightness() < light_track.lightness()


def test_progress_strip_first_show_snaps_progress_to_target(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    shell.progress_host.set_state(_running_state(), animate=False)

    assert shell.progress_host.strip_widget().display_progress_value() == shell.progress_host.strip_widget().target_progress_value()


def test_progress_strip_sweep_travels_fully_across_fill_span(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    shell.progress_host.set_state(_running_state(), animate=False)
    strip = shell.progress_host.strip_widget()
    fill_rect = strip.debug_fill_rect()
    motion_ratio = EXPECTED_DEFAULT_SWEEP_DURATION_MS / (
        EXPECTED_DEFAULT_SWEEP_DURATION_MS + EXPECTED_DEFAULT_SWEEP_IDLE_DELAY_MS
    )
    start_rect = strip.debug_glow_rect(phase=0.0)
    end_rect = strip.debug_glow_rect(phase=motion_ratio - 1e-4)
    delay_rect = strip.debug_glow_rect(phase=1.0)

    assert start_rect.left() < fill_rect.left()
    assert end_rect.left() >= fill_rect.right() - 1.0
    assert delay_rect.isNull()


def test_progress_strip_compacts_height_and_reserves_action_area(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    shell.progress_host.set_state(_running_state(), animate=False)
    strip = shell.progress_host.strip_widget()
    fill_rect = strip.debug_fill_rect()
    action_rect = strip.debug_action_rect()

    assert shell.progress_host.height() == EXPECTED_STRIP_HEIGHT
    assert strip.height() == EXPECTED_STRIP_HEIGHT
    assert action_rect.width() > 0
    assert fill_rect.right() <= action_rect.left()


def test_progress_strip_hidden_meta_labels_do_not_shrink_progress_rect(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    state = replace(_running_state(), rate_text="", status_text="")
    shell.progress_host.set_state(state, animate=False)
    strip = shell.progress_host.strip_widget()
    progress_rect = strip._progress_rect()
    action_rect = strip.debug_action_rect()

    assert strip._rate_label.isVisible() is False
    assert strip._status_label.isVisible() is False
    assert progress_rect.right() >= action_rect.left() - PROGRESS_ACTION_GAP - 1.0


def test_progress_strip_light_theme_keeps_meta_text_stable_across_progress(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    low_progress = replace(_running_state(), theme_mode="light", progress_current=10, progress_total=100)
    shell.progress_host.set_state(low_progress, animate=False)
    QApplication.processEvents()
    low_rate = shell.progress_host.strip_widget().current_rate_text_color()

    high_progress = replace(_running_state(), theme_mode="light", progress_current=100, progress_total=100)
    shell.progress_host.set_state(high_progress, animate=False)
    QApplication.processEvents()
    high_rate = shell.progress_host.strip_widget().current_rate_text_color()

    assert low_rate == high_rate


def test_progress_strip_uses_progress_palette_fill_for_accent_preset(qtbot) -> None:
    with _restore_theme_color():
        apply_accent_preset("orange")
        shell = _ProgressStripShellDemo()
        qtbot.addWidget(shell)
        shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        shell.show()
        _wait_until_visible(qtbot, shell)

        state = replace(_running_state(), theme_mode="dark")
        shell.progress_host.set_state(state, animate=False)

        expected_fill = resolve_progress_palette(mode="Dark", preset_id="orange").fill_main
        actual_fill = shell.progress_host.strip_widget().current_fill_color()

        assert actual_fill == expected_fill


def test_progress_strip_buttons_exist_and_pause_button_toggles_icon_with_state(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    shell.progress_host.set_state(_running_state(), animate=False)
    strip = shell.progress_host.strip_widget()
    pause_button = strip.pause_button()
    stop_button = strip.stop_button()

    assert pause_button.isVisible()
    assert stop_button.isVisible()
    assert pause_button.toolTip() == "暂停"
    assert stop_button.toolTip() == "停止"

    shell.progress_host.set_state(replace(_running_state(), paused=True), animate=False)
    assert pause_button.toolTip() == "继续"
    assert pause_button.font().pointSizeF() > 0
    assert stop_button.font().pointSizeF() > 0


def test_progress_strip_buttons_are_flush_and_status_keeps_right_padding_at_full_progress(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    shell.progress_host.set_state(replace(_running_state(), progress_current=100, progress_total=100), animate=False)
    strip = shell.progress_host.strip_widget()
    action_rect = strip.debug_action_rect()
    outer_rect = strip.debug_outer_rect()
    status_rect = QRectF(strip._status_label.geometry())
    fill_rect = strip.debug_fill_rect()
    left_padding = strip._text_block.geometry().left()

    assert action_rect.right() >= outer_rect.right() - 1.0
    assert fill_rect.right() <= action_rect.left() - PROGRESS_ACTION_GAP + 1.0
    assert status_rect.right() <= action_rect.left() - 1.0
    assert fill_rect.right() >= status_rect.left() - left_padding


def test_progress_strip_outer_radius_clips_inner_fill_left_edge(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    state = replace(_running_state(), progress_current=100, progress_total=100, outer_radius=12, inner_radius=0)
    shell.progress_host.set_state(state, animate=False)
    strip = shell.progress_host.strip_widget()

    fill_rect = strip.debug_fill_rect()
    top_left_probe = QPointF(fill_rect.left() + 1, fill_rect.top() + 1)
    mid_left_probe = QPointF(fill_rect.left() + 1, fill_rect.center().y())

    assert fill_rect.left() == strip.debug_outer_rect().left()
    assert strip.debug_clipped_fill_contains(top_left_probe) is False
    assert strip.debug_clipped_fill_contains(mid_left_probe) is True


def test_progress_strip_pause_and_stop_icons_share_consistent_visual_scale(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    shell.progress_host.set_state(_running_state(), animate=False)
    strip = shell.progress_host.strip_widget()

    pause_bounds = strip.pause_button().debug_icon_bounds()
    stop_bounds = strip.stop_button().debug_icon_bounds()

    assert pause_bounds.height() <= stop_bounds.height()
    assert stop_bounds.width() >= pause_bounds.width()


def test_progress_strip_title_and_detail_are_visually_compact(qtbot) -> None:
    shell = _ProgressStripShellDemo()
    qtbot.addWidget(shell)
    shell.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    shell.show()
    _wait_until_visible(qtbot, shell)

    shell.progress_host.set_state(_running_state(), animate=False)
    strip = shell.progress_host.strip_widget()
    title_rect = strip._text_block.debug_title_rect().toRect()
    detail_rect = strip._text_block.debug_detail_rect().toRect()

    assert detail_rect.top() - title_rect.bottom() <= EXPECTED_TITLE_DETAIL_MAX_GAP
    assert strip._text_block._title_label.font().pixelSize() == EXPECTED_TITLE_FONT_PIXEL_SIZE
