"""全局底部进度条独立 demo。"""

from __future__ import annotations

import sys
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lol_audio_unpack.gui.components.global_progress_strip import (
    DEFAULT_PROGRESS_SWEEP_ANIMATION_MS,
    GlobalProgressStripHost,
    GlobalProgressStripState,
)

DEMO_WINDOW_WIDTH = 1160
DEMO_WINDOW_HEIGHT = 860
DEMO_PROGRESS_MIN = 0
DEMO_PROGRESS_MAX = 100
DEMO_SWEEP_DURATION_MIN = 800
DEMO_SWEEP_DURATION_MAX = 3600
DEMO_RADIUS_MIN = 0
DEMO_RADIUS_MAX = 18
DEFAULT_DEMO_STATE = GlobalProgressStripState(
    visible=False,
    title_text="stream.x64.x-none.dat (2/4)",
    detail_text="1.63 GB / 2.60 GB",
    progress_current=63,
    progress_total=100,
    rate_text="71.20 MB/s",
    status_text="下载中",
    paused=False,
    theme_mode="auto",
    sweep_duration_ms=DEFAULT_PROGRESS_SWEEP_ANIMATION_MS,
    outer_radius=5.0,
    inner_radius=0.0,
    button_radius=5.0,
)


def _build_demo_card(title: str, description: str, parent: QWidget) -> QFrame:
    """构造展示用占位卡片。"""
    card = QFrame(parent)
    card.setObjectName("ProgressStripDemoCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(6)
    title_label = QLabel(title, card)
    title_label.setObjectName("ProgressStripDemoCardTitle")
    description_label = QLabel(description, card)
    description_label.setObjectName("ProgressStripDemoCardDescription")
    description_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(description_label)
    return card


class GlobalProgressStripDemoWindow(QWidget):
    """用于人工调试全局底部进度条的独立窗口。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化 demo 窗口。"""
        super().__init__(parent)
        self._default_state = DEFAULT_DEMO_STATE
        self._current_state = DEFAULT_DEMO_STATE
        self.setWindowTitle("Global Progress Strip Demo")
        self.resize(DEMO_WINDOW_WIDTH, DEMO_WINDOW_HEIGHT)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        self.page = QWidget()
        self.page.setObjectName("GlobalProgressStripDemoPage")
        self.page_layout = QVBoxLayout(self.page)
        self.page_layout.setContentsMargins(24, 24, 24, 24)
        self.page_layout.setSpacing(16)

        self.page_layout.addWidget(
            _build_demo_card("全局底部进度条 Demo", "这个页面只用于调试底部壳层进度条，不接真实任务事件。", self.page)
        )
        self.page_layout.addWidget(
            _build_demo_card("观察点 1", "显示进度条后，页面内容本身高度不变，但可视 viewport 会缩小，滚动条应该随之出现。", self.page)
        )

        self.control_card = QFrame(self.page)
        self.control_card.setObjectName("GlobalProgressStripDemoControlCard")
        control_layout = QVBoxLayout(self.control_card)
        control_layout.setContentsMargins(20, 18, 20, 18)
        control_layout.setSpacing(14)

        control_title = QLabel("控制面板", self.control_card)
        control_title.setObjectName("GlobalProgressStripDemoSectionTitle")
        control_layout.addWidget(control_title)

        form_layout = QGridLayout()
        form_layout.setHorizontalSpacing(14)
        form_layout.setVerticalSpacing(10)

        self.title_input = QLineEdit(self.control_card)
        self.detail_input = QLineEdit(self.control_card)
        self.rate_input = QLineEdit(self.control_card)
        self.status_input = QLineEdit(self.control_card)
        self.progress_slider = QSlider(Qt.Orientation.Horizontal, self.control_card)
        self.progress_slider.setRange(DEMO_PROGRESS_MIN, DEMO_PROGRESS_MAX)
        self.progress_value_label = QLabel(self.control_card)
        self.pause_checkbox = QCheckBox("暂停态", self.control_card)
        self.theme_mode_combo = QComboBox(self.control_card)
        self.theme_mode_combo.addItem("跟随主题", "auto")
        self.theme_mode_combo.addItem("浅色", "light")
        self.theme_mode_combo.addItem("深色", "dark")
        self.sweep_duration_slider = QSlider(Qt.Orientation.Horizontal, self.control_card)
        self.sweep_duration_slider.setRange(DEMO_SWEEP_DURATION_MIN, DEMO_SWEEP_DURATION_MAX)
        self.sweep_duration_slider.setSingleStep(100)
        self.sweep_duration_slider.setPageStep(200)
        self.sweep_duration_value_label = QLabel(self.control_card)
        self.outer_radius_slider = QSlider(Qt.Orientation.Horizontal, self.control_card)
        self.outer_radius_slider.setRange(DEMO_RADIUS_MIN, DEMO_RADIUS_MAX)
        self.inner_radius_slider = QSlider(Qt.Orientation.Horizontal, self.control_card)
        self.inner_radius_slider.setRange(DEMO_RADIUS_MIN, DEMO_RADIUS_MAX)
        self.button_radius_slider = QSlider(Qt.Orientation.Horizontal, self.control_card)
        self.button_radius_slider.setRange(DEMO_RADIUS_MIN, DEMO_RADIUS_MAX)
        self.outer_radius_value_label = QLabel(self.control_card)
        self.inner_radius_value_label = QLabel(self.control_card)
        self.button_radius_value_label = QLabel(self.control_card)

        form_layout.addWidget(QLabel("标题", self.control_card), 0, 0)
        form_layout.addWidget(self.title_input, 0, 1, 1, 3)
        form_layout.addWidget(QLabel("说明", self.control_card), 1, 0)
        form_layout.addWidget(self.detail_input, 1, 1, 1, 3)
        form_layout.addWidget(QLabel("速率", self.control_card), 2, 0)
        form_layout.addWidget(self.rate_input, 2, 1)
        form_layout.addWidget(QLabel("状态", self.control_card), 2, 2)
        form_layout.addWidget(self.status_input, 2, 3)
        form_layout.addWidget(QLabel("进度", self.control_card), 3, 0)
        form_layout.addWidget(self.progress_slider, 3, 1, 1, 2)
        form_layout.addWidget(self.progress_value_label, 3, 3)
        form_layout.addWidget(self.pause_checkbox, 4, 0, 1, 2)
        form_layout.addWidget(QLabel("主题模式", self.control_card), 5, 0)
        form_layout.addWidget(self.theme_mode_combo, 5, 1)
        form_layout.addWidget(QLabel("Sweep", self.control_card), 5, 2)
        form_layout.addWidget(self.sweep_duration_value_label, 5, 3)
        form_layout.addWidget(self.sweep_duration_slider, 6, 0, 1, 4)
        form_layout.addWidget(QLabel("外层圆角", self.control_card), 7, 0)
        form_layout.addWidget(self.outer_radius_slider, 7, 1, 1, 2)
        form_layout.addWidget(self.outer_radius_value_label, 7, 3)
        form_layout.addWidget(QLabel("内层圆角", self.control_card), 8, 0)
        form_layout.addWidget(self.inner_radius_slider, 8, 1, 1, 2)
        form_layout.addWidget(self.inner_radius_value_label, 8, 3)
        form_layout.addWidget(QLabel("按钮圆角", self.control_card), 9, 0)
        form_layout.addWidget(self.button_radius_slider, 9, 1, 1, 2)
        form_layout.addWidget(self.button_radius_value_label, 9, 3)

        control_layout.addLayout(form_layout)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(10)

        self.show_button = QPushButton("显示", self.control_card)
        self.hide_button = QPushButton("隐藏", self.control_card)
        self.apply_button = QPushButton("应用状态", self.control_card)
        self.reset_button = QPushButton("重置默认", self.control_card)
        self.advance_button = QPushButton("+10%", self.control_card)
        self.rewind_button = QPushButton("-10%", self.control_card)

        for button in (
            self.show_button,
            self.hide_button,
            self.apply_button,
            self.reset_button,
            self.advance_button,
            self.rewind_button,
        ):
            button_row.addWidget(button)
        button_row.addStretch(1)
        control_layout.addLayout(button_row)

        self.page_layout.addWidget(self.control_card)
        self.page_layout.addWidget(
            _build_demo_card("观察点 2", "暂停态会降低填充条饱和度，但 sweep 光晕动画仍然保持运行。", self.page)
        )
        self.page_layout.addWidget(
            _build_demo_card("观察点 3", "把页面滚动到底部后再显示进度条，观察底部卡片会被整体顶上去，而不是被覆盖。", self.page)
        )
        self.page_layout.addStretch(1)
        self.page_layout.addWidget(
            _build_demo_card("底部参考卡片", "这是专门留在页面最底部的观察卡片，用来确认底部进度条出现时内容区和滚动条的表现。", self.page)
        )

        self.scroll_area.setWidget(self.page)

        self.progress_host = GlobalProgressStripHost(self)

        root_layout.addWidget(self.scroll_area, 1)
        root_layout.addWidget(self.progress_host, 0)

        self._apply_state_to_form(self._default_state)
        self._connect_signals()

    def _connect_signals(self) -> None:
        """绑定 demo 控件事件。"""
        self.show_button.clicked.connect(self._show_progress_strip)
        self.hide_button.clicked.connect(self._hide_progress_strip)
        self.apply_button.clicked.connect(self._apply_form_state)
        self.reset_button.clicked.connect(self._reset_form_state)
        self.advance_button.clicked.connect(lambda: self._adjust_progress(10))
        self.rewind_button.clicked.connect(lambda: self._adjust_progress(-10))
        self.progress_slider.valueChanged.connect(self._update_progress_label)
        self.sweep_duration_slider.valueChanged.connect(self._update_sweep_duration_label)
        self.outer_radius_slider.valueChanged.connect(self._update_outer_radius_label)
        self.inner_radius_slider.valueChanged.connect(self._update_inner_radius_label)
        self.button_radius_slider.valueChanged.connect(self._update_button_radius_label)
        self.progress_host.strip_widget().pause_requested.connect(self._toggle_pause_from_strip)
        self.progress_host.strip_widget().stop_requested.connect(self._stop_from_strip)

    def _build_state_from_form(self, *, visible: bool | None = None) -> GlobalProgressStripState:
        """根据当前表单内容构造进度条状态。"""
        return GlobalProgressStripState(
            visible=self._current_state.visible if visible is None else visible,
            title_text=self.title_input.text().strip(),
            detail_text=self.detail_input.text().strip(),
            progress_current=self.progress_slider.value(),
            progress_total=DEMO_PROGRESS_MAX,
            rate_text=self.rate_input.text().strip(),
            status_text=self.status_input.text().strip(),
            paused=self.pause_checkbox.isChecked(),
            accent_color=self._current_state.accent_color,
            theme_mode=str(self.theme_mode_combo.currentData()),
            sweep_duration_ms=self.sweep_duration_slider.value(),
            outer_radius=float(self.outer_radius_slider.value()),
            inner_radius=float(self.inner_radius_slider.value()),
            button_radius=float(self.button_radius_slider.value()),
        )

    def _apply_state_to_form(self, state: GlobalProgressStripState) -> None:
        """把状态对象写回到控件表单。"""
        self.title_input.setText(state.title_text)
        self.detail_input.setText(state.detail_text)
        self.rate_input.setText(state.rate_text)
        self.status_input.setText(state.status_text)
        self.progress_slider.setValue(state.progress_current)
        self.pause_checkbox.setChecked(state.paused)
        theme_index = self.theme_mode_combo.findData(state.theme_mode)
        self.theme_mode_combo.setCurrentIndex(max(theme_index, 0))
        self.sweep_duration_slider.setValue(state.sweep_duration_ms)
        self.outer_radius_slider.setValue(int(state.outer_radius))
        self.inner_radius_slider.setValue(int(state.inner_radius))
        self.button_radius_slider.setValue(int(state.button_radius))
        self._update_progress_label(state.progress_current)
        self._update_sweep_duration_label(state.sweep_duration_ms)
        self._update_outer_radius_label(int(state.outer_radius))
        self._update_inner_radius_label(int(state.inner_radius))
        self._update_button_radius_label(int(state.button_radius))

    def _update_progress_label(self, value: int) -> None:
        """同步显示当前百分比。"""
        self.progress_value_label.setText(f"{value}%")

    def _update_sweep_duration_label(self, value: int) -> None:
        """同步显示当前 sweep 时长。"""
        self.sweep_duration_value_label.setText(f"{value} ms")

    def _update_outer_radius_label(self, value: int) -> None:
        """同步显示当前外层圆角。"""
        self.outer_radius_value_label.setText(str(value))

    def _update_inner_radius_label(self, value: int) -> None:
        """同步显示当前内层圆角。"""
        self.inner_radius_value_label.setText(str(value))

    def _update_button_radius_label(self, value: int) -> None:
        """同步显示当前按钮圆角。"""
        self.button_radius_value_label.setText(str(value))

    def _apply_form_state(self) -> None:
        """将表单中的状态应用到底部进度条。"""
        self._current_state = self._build_state_from_form()
        self.progress_host.set_state(self._current_state, animate=False)

    def _show_progress_strip(self) -> None:
        """显示进度条，并保留当前表单内容。"""
        self._current_state = self._build_state_from_form(visible=True)
        self.progress_host.set_state(self._current_state, animate=False)

    def _hide_progress_strip(self) -> None:
        """隐藏进度条。"""
        self._current_state = replace(self._current_state, visible=False)
        self.progress_host.set_state(self._current_state, animate=False)

    def _adjust_progress(self, delta: int) -> None:
        """增减当前进度百分比。"""
        next_value = max(DEMO_PROGRESS_MIN, min(DEMO_PROGRESS_MAX, self.progress_slider.value() + delta))
        self.progress_slider.setValue(next_value)
        if self._current_state.visible:
            self._current_state = self._build_state_from_form()
            self.progress_host.set_state(self._current_state, animate=True)

    def _reset_form_state(self) -> None:
        """重置到默认状态并回写到进度条。"""
        self._current_state = self._default_state
        self._apply_state_to_form(self._default_state)
        self.progress_host.set_state(self._default_state, animate=False)

    def _toggle_pause_from_strip(self) -> None:
        """响应条内暂停/继续按钮。"""
        next_paused = not self.pause_checkbox.isChecked()
        self.pause_checkbox.setChecked(next_paused)
        self.status_input.setText("已暂停" if next_paused else "下载中")
        self._apply_form_state()

    def _stop_from_strip(self) -> None:
        """响应条内停止按钮。"""
        self._hide_progress_strip()


def main() -> int:
    """启动 demo 窗口。"""
    app = QApplication.instance() or QApplication(sys.argv)
    window = GlobalProgressStripDemoWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
