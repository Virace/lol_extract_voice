"""主窗口底部全局进度条组件。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, FluentIconBase, TransparentToolButton, isDarkTheme, qconfig, themeColor

from lol_audio_unpack.gui.common.font_compat import apply_tool_button_safe_font

ThemeMode = Literal["auto", "light", "dark"]
ActionIconKind = Literal["pause", "play", "stop"]

ICON_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "icon"
DEFAULT_PROGRESS_STRIP_ACCENT = QColor(themeColor())
PROGRESS_STRIP_HEIGHT = 44
PROGRESS_STRIP_HOST_TOP_MARGIN = 0
PROGRESS_STRIP_HOST_BOTTOM_MARGIN = 0
PROGRESS_STRIP_HOST_HORIZONTAL_MARGIN = 0
PROGRESS_STRIP_ANIMATION_MS = 220
DEFAULT_PROGRESS_SWEEP_ANIMATION_MS = 4600
DEFAULT_PROGRESS_SWEEP_IDLE_DELAY_MS = 800
PROGRESS_TRACK_RADIUS = 12.0
PROGRESS_FILL_PADDING = 0.0
PROGRESS_GLOW_WIDTH = 84.0
PROGRESS_ACTION_GAP = 8.0
PROGRESS_ACTION_BUTTON_WIDTH = 36
PROGRESS_CONTENT_HORIZONTAL_MARGIN = 10
PROGRESS_CONTENT_VERTICAL_MARGIN = 2
PROGRESS_TEXT_TOP_MARGIN = 3
PROGRESS_TEXT_STACK_GAP = 2
PROGRESS_STATUS_SAFE_GAP = 12.0
PAUSED_SATURATION_FACTOR = 0.42
PAUSED_VALUE_FACTOR = 1.08
DEFAULT_BUTTON_RADIUS = 5.0
ACTION_BUTTON_ICON_SIZE = QSize(18, 18)


@dataclass(slots=True, frozen=True)
class GlobalProgressStripState:
    """描述全局进度条当前展示状态。

    Args:
        visible: 当前是否显示进度条。
        title_text: 左侧主标题。
        detail_text: 左侧辅助说明。
        progress_current: 当前进度值。
        progress_total: 总进度值。
        rate_text: 右侧速率文案。
        status_text: 右侧状态文案。
        paused: 是否为暂停态。
        accent_color: 主色；为空时使用默认颜色。
    """

    visible: bool = False
    title_text: str = ""
    detail_text: str = ""
    progress_current: int = 0
    progress_total: int = 100
    rate_text: str = ""
    status_text: str = ""
    paused: bool = False
    accent_color: QColor | None = None
    theme_mode: ThemeMode = "auto"
    sweep_duration_ms: int = DEFAULT_PROGRESS_SWEEP_ANIMATION_MS
    outer_radius: float = 5.0
    inner_radius: float = 0.0
    button_radius: float = DEFAULT_BUTTON_RADIUS
    sweep_idle_delay_ms: int = DEFAULT_PROGRESS_SWEEP_IDLE_DELAY_MS


def _normalized_progress_ratio(current: int, total: int) -> float:
    """将整数进度转换为 0 到 1 的比值。"""
    if total <= 0:
        return 0.0
    return max(0.0, min(float(current) / float(total), 1.0))


def _desaturate_color(color: QColor) -> QColor:
    """基于原色生成低饱和度的暂停态颜色。"""
    hue, saturation, value, alpha = color.getHsv()
    if hue < 0:
        return QColor(color)

    paused = QColor.fromHsv(
        hue,
        max(0, min(255, int(saturation * PAUSED_SATURATION_FACTOR))),
        max(0, min(255, int(value * PAUSED_VALUE_FACTOR))),
        alpha,
    )
    return paused


def _qcolor_to_rgba_text(color: QColor) -> str:
    """将 QColor 转换为 QSS 可用的 rgba 文本。"""
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def _fill_text_color() -> QColor:
    """返回覆盖在填充区域上的文本颜色。"""
    return QColor(236, 244, 252)


def _with_alpha(color: QColor, alpha: int) -> QColor:
    """返回调整 alpha 后的新颜色。"""
    clone = QColor(color)
    clone.setAlpha(alpha)
    return clone


def _build_uniform_round_rect_path(rect: QRectF, radius: float) -> QPainterPath:
    """构造统一圆角矩形路径。"""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


class _ProgressStripTextBlock(QWidget):
    """使用原生 QLabel 顶/底对齐的双行文本块。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化文本块。"""
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._title_label = QLabel("", self)
        self._detail_label = QLabel("", self)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        title_font = QFont(self._title_label.font())
        title_font.setPixelSize(13)
        self._title_label.setFont(title_font)

        detail_font = QFont(self._detail_label.font())
        detail_font.setPixelSize(11)
        self._detail_label.setFont(detail_font)

    def set_content(self, *, title: str, detail: str) -> None:
        """更新文本内容。"""
        self._title_label.setText(title)
        self._detail_label.setText(detail)
        self._sync_layout()

    def set_colors(self, *, title_color: QColor, detail_color: QColor) -> None:
        """更新文本颜色。"""
        self._title_label.setStyleSheet(f"color: {_qcolor_to_rgba_text(QColor(title_color))};")
        self._detail_label.setStyleSheet(f"color: {_qcolor_to_rgba_text(QColor(detail_color))};")

    def _sync_layout(self) -> None:
        """按中心线将标题/说明分到上下两个区域。"""
        content_rect = self.rect()
        half_height = content_rect.height() // 2
        title_rect = content_rect.adjusted(0, 0, 0, -(content_rect.height() - half_height))
        detail_rect = content_rect.adjusted(0, half_height, 0, 0)
        self._title_label.setGeometry(title_rect)
        self._detail_label.setGeometry(detail_rect)

    def resizeEvent(self, event) -> None:
        """尺寸变化后同步文本块内部布局。"""
        super().resizeEvent(event)
        self._sync_layout()

    def debug_title_rect(self) -> QRectF:
        """测试辅助：返回标题文本矩形。"""
        return QRectF(self._title_label.geometry())

    def debug_detail_rect(self) -> QRectF:
        """测试辅助：返回说明文本矩形。"""
        return QRectF(self._detail_label.geometry())


class ProgressActionIcon(FluentIconBase, Enum):
    """全局进度条按钮使用的自定义 svg 图标。"""

    PAUSE = "pause-solid-full.svg"
    PLAY = "play-solid-full.svg"
    STOP = "stop-solid-full.svg"

    def path(self, theme=None) -> str:
        """返回对应 svg 图标路径。"""
        _ = theme
        return str(ICON_ASSET_DIR / self.value)


class _ProgressStripActionButton(TransparentToolButton):
    """进度条内部动作按钮。"""

    def __init__(self, icon_kind: ActionIconKind, parent: QWidget | None = None) -> None:
        """初始化动作按钮。"""
        super().__init__(parent)
        self._icon_kind: ActionIconKind = icon_kind
        self._icon_color = QColor(255, 255, 255)
        self._background_idle = QColor(0, 0, 0, 0)
        self._background_hover = QColor(255, 255, 255, 24)
        self._background_pressed = QColor(255, 255, 255, 40)
        self._corner_radius = DEFAULT_BUTTON_RADIUS
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setIconSize(ACTION_BUTTON_ICON_SIZE)
        apply_tool_button_safe_font(self)
        self._sync_icon()

    def set_icon_kind(self, icon_kind: ActionIconKind) -> None:
        """切换当前图标类型。"""
        self._icon_kind = icon_kind
        self._sync_icon()

    def set_visual_style(
        self,
        *,
        icon_color: QColor,
        idle_background: QColor,
        hover_background: QColor,
        pressed_background: QColor,
        corner_radius: float,
    ) -> None:
        """同步按钮视觉样式。"""
        self._icon_color = QColor(icon_color)
        self._background_idle = QColor(idle_background)
        self._background_hover = QColor(hover_background)
        self._background_pressed = QColor(pressed_background)
        self._corner_radius = corner_radius
        self._sync_icon()
        self.setStyleSheet(
            f"""
            TransparentToolButton {{
                background-color: {_qcolor_to_rgba_text(self._background_idle)};
                border: none;
                border-radius: {self._corner_radius}px;
                padding: 0;
            }}
            TransparentToolButton:hover {{
                background-color: {_qcolor_to_rgba_text(self._background_hover)};
            }}
            TransparentToolButton:pressed {{
                background-color: {_qcolor_to_rgba_text(self._background_pressed)};
            }}
            """
        )

    def _icon_rect(self, rect: QRectF) -> QRectF:
        """返回图标绘制安全区域。"""
        size = self.iconSize()
        left = rect.center().x() - size.width() / 2
        top = rect.center().y() - size.height() / 2
        return QRectF(left, top, size.width(), size.height())

    def debug_icon_bounds(self) -> QRectF:
        """测试辅助：返回图标安全区域。"""
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        return self._icon_rect(rect)

    def _sync_icon(self) -> None:
        """根据当前状态同步 qfluent svg 图标。"""
        icon_map: dict[ActionIconKind, ProgressActionIcon] = {
            "pause": ProgressActionIcon.PAUSE,
            "play": ProgressActionIcon.PLAY,
            "stop": ProgressActionIcon.STOP,
        }
        icon = icon_map[self._icon_kind].colored(self._icon_color, self._icon_color)
        self.setIcon(icon)


class GlobalProgressStrip(QWidget):
    """底部全局进度条本体。

    该组件只负责视觉呈现与动画，不直接参与主窗口内容区高度计算。
    """

    pause_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化底部进度条。"""
        super().__init__(parent)
        self._state = GlobalProgressStripState()
        self._display_progress = 0.0
        self._target_progress = 0.0
        self._sweep_phase_value = 0.0
        self._configured_sweep_duration_ms = DEFAULT_PROGRESS_SWEEP_ANIMATION_MS
        self._configured_sweep_idle_delay_ms = DEFAULT_PROGRESS_SWEEP_IDLE_DELAY_MS
        self._track_background_color = QColor(18, 18, 18, 232)
        self._track_border_color = QColor(255, 255, 255, 36)
        self._title_text_color = QColor(18, 18, 18)
        self._detail_text_color = QColor(18, 18, 18, 210)
        self._meta_text_color = QColor(255, 255, 255, 230)
        self._rate_text_color = QColor(255, 255, 255, 230)
        self._status_text_color = QColor(255, 255, 255, 230)

        self.setFixedHeight(PROGRESS_STRIP_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self._content_layout = QHBoxLayout(self)
        self._content_layout.setContentsMargins(
            PROGRESS_CONTENT_HORIZONTAL_MARGIN,
            PROGRESS_CONTENT_VERTICAL_MARGIN,
            0,
            PROGRESS_CONTENT_VERTICAL_MARGIN,
        )
        self._content_layout.setSpacing(PROGRESS_CONTENT_HORIZONTAL_MARGIN)

        self._text_block = _ProgressStripTextBlock(self)
        self._content_layout.addWidget(self._text_block, 1)

        right_row = QHBoxLayout()
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(12)
        right_row.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._rate_label = BodyLabel("", self)
        self._status_label = BodyLabel("", self)
        self._content_layout.addLayout(right_row, 0)

        right_row.addWidget(self._rate_label)
        right_row.addWidget(self._status_label)

        self._action_widget = QWidget(self)
        action_layout = QHBoxLayout(self._action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(0)

        self._pause_button = _ProgressStripActionButton("pause", self._action_widget)
        self._pause_button.setToolTip("暂停")
        self._pause_button.setFixedWidth(PROGRESS_ACTION_BUTTON_WIDTH)
        self._pause_button.setFixedHeight(PROGRESS_STRIP_HEIGHT - PROGRESS_CONTENT_VERTICAL_MARGIN * 2)
        self._pause_button.clicked.connect(self.pause_requested.emit)

        self._stop_button = _ProgressStripActionButton("stop", self._action_widget)
        self._stop_button.setToolTip("停止")
        self._stop_button.setFixedWidth(PROGRESS_ACTION_BUTTON_WIDTH)
        self._stop_button.setFixedHeight(PROGRESS_STRIP_HEIGHT - PROGRESS_CONTENT_VERTICAL_MARGIN * 2)
        self._stop_button.clicked.connect(self.stop_requested.emit)

        action_layout.addWidget(self._pause_button)
        action_layout.addWidget(self._stop_button)
        self._content_layout.addWidget(self._action_widget, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._progress_animation = QPropertyAnimation(self, b"displayProgress", self)
        self._progress_animation.setDuration(PROGRESS_STRIP_ANIMATION_MS)
        self._progress_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._sweep_animation = QPropertyAnimation(self, b"sweepPhase", self)
        self._sweep_animation.setDuration(
            DEFAULT_PROGRESS_SWEEP_ANIMATION_MS + DEFAULT_PROGRESS_SWEEP_IDLE_DELAY_MS
        )
        self._sweep_animation.setStartValue(0.0)
        self._sweep_animation.setEndValue(1.0)
        self._sweep_animation.setLoopCount(-1)
        self._sweep_animation.setEasingCurve(QEasingCurve.Type.Linear)

        self._theme_listener = lambda *_args: self._refresh_visuals_from_theme()
        qconfig.themeChanged.connect(self._theme_listener)
        qconfig.themeColorChanged.connect(self._theme_listener)
        self.destroyed.connect(self._disconnect_theme_listeners)

        self._apply_state()

    def _disconnect_theme_listeners(self) -> None:
        """断开主题监听，避免对象析构后残留信号连接。"""
        for signal in (qconfig.themeChanged, qconfig.themeColorChanged):
            try:
                signal.disconnect(self._theme_listener)
            except (RuntimeError, TypeError):
                continue

    def _resolved_theme_mode(self) -> ThemeMode:
        """返回当前实际生效的主题模式。"""
        if self._state.theme_mode != "auto":
            return self._state.theme_mode
        return "dark" if isDarkTheme() else "light"

    def current_fill_color(self) -> QColor:
        """返回当前用于填充进度的颜色。"""
        accent = QColor(self._state.accent_color) if self._state.accent_color is not None else QColor(themeColor())
        return _desaturate_color(accent) if self._state.paused else accent

    def current_track_background_color(self) -> QColor:
        """返回当前轨道背景色。"""
        return QColor(self._track_background_color)

    def current_meta_text_color(self) -> QColor:
        """返回右侧状态文案当前颜色。"""
        return QColor(self._meta_text_color)

    def current_rate_text_color(self) -> QColor:
        """返回速率文本当前颜色。"""
        return self._dynamic_meta_color_for_widget(self._rate_label, fallback=self._meta_text_color)

    def current_status_text_color(self) -> QColor:
        """返回状态文本当前颜色。"""
        return self._dynamic_meta_color_for_widget(self._status_label, fallback=self._meta_text_color)

    def current_sweep_duration_ms(self) -> int:
        """返回当前 sweep 动画时长。"""
        return self._configured_sweep_duration_ms

    def current_sweep_idle_delay_ms(self) -> int:
        """返回 sweep 停顿时长。"""
        return self._configured_sweep_idle_delay_ms

    def pause_button(self) -> _ProgressStripActionButton:
        """返回暂停/恢复按钮。"""
        return self._pause_button

    def stop_button(self) -> _ProgressStripActionButton:
        """返回停止按钮。"""
        return self._stop_button

    def display_progress_value(self) -> float:
        """返回当前显示中的进度值。"""
        return self._display_progress

    def target_progress_value(self) -> float:
        """返回当前目标进度值。"""
        return self._target_progress

    def is_sweep_animating(self) -> bool:
        """返回 sweep 动画当前是否仍在运行。"""
        return self._sweep_animation.state() == QPropertyAnimation.State.Running

    def sweep_phase(self) -> float:
        """返回当前 sweep 相位。"""
        return self._sweep_phase_value

    def set_animation_active(self, active: bool) -> None:
        """启用或停用内部 sweep 动画。"""
        if active:
            if not self.is_sweep_animating():
                self._sweep_animation.start()
        else:
            self._sweep_animation.stop()

    def set_state(self, state: GlobalProgressStripState, *, animate: bool = True) -> None:
        """应用新的进度条展示状态。

        Args:
            state: 最新展示状态。
            animate: 是否对进度增长启用动画。
        """
        was_visible = self._state.visible
        self._state = state
        self._target_progress = _normalized_progress_ratio(state.progress_current, state.progress_total)

        self._text_block.set_content(title=state.title_text, detail=state.detail_text)
        self._rate_label.setText(state.rate_text)
        self._status_label.setText(state.status_text)
        self._pause_button.set_icon_kind("play" if state.paused else "pause")
        self._pause_button.setToolTip("继续" if state.paused else "暂停")
        self._configured_sweep_duration_ms = max(800, state.sweep_duration_ms)
        self._configured_sweep_idle_delay_ms = max(0, state.sweep_idle_delay_ms)
        self._sweep_animation.setDuration(
            self._configured_sweep_duration_ms + self._configured_sweep_idle_delay_ms
        )

        self._progress_animation.stop()
        if not animate or (not was_visible and state.visible):
            self.set_display_progress(self._target_progress)
        else:
            self._progress_animation.setStartValue(self._display_progress)
            self._progress_animation.setEndValue(self._target_progress)
            self._progress_animation.start()

        self.set_animation_active(state.visible)
        self._apply_state()
        self.update()

    def _refresh_visuals_from_theme(self) -> None:
        """在主题变化后刷新组件视觉。"""
        self._apply_state()
        self.update()

    def _apply_state(self) -> None:
        """同步当前状态到标签显隐与颜色。"""
        fill_text_color = _fill_text_color()
        resolved_theme = self._resolved_theme_mode()

        if resolved_theme == "dark":
            self._track_background_color = QColor(20, 20, 20, 232)
            self._track_border_color = QColor(255, 255, 255, 48)
            self._meta_text_color = QColor(245, 245, 245, 230)
            button_hover = QColor(255, 255, 255, 22)
            button_pressed = QColor(255, 255, 255, 44)
        else:
            self._track_background_color = QColor(243, 243, 243, 240)
            self._track_border_color = QColor(0, 0, 0, 22)
            self._meta_text_color = QColor(32, 36, 42, 230)
            button_hover = QColor(0, 0, 0, 18)
            button_pressed = QColor(0, 0, 0, 34)

        self._title_text_color = fill_text_color
        self._detail_text_color = _with_alpha(fill_text_color, 214)
        self._content_layout.activate()
        self._refresh_dynamic_meta_text_colors()

        self._text_block.set_colors(
            title_color=self._title_text_color,
            detail_color=self._detail_text_color,
        )
        self._rate_label.setStyleSheet(f"color: {_qcolor_to_rgba_text(self._rate_text_color)};")
        self._status_label.setStyleSheet(f"color: {_qcolor_to_rgba_text(self._status_text_color)};")
        for button in (self._pause_button, self._stop_button):
            button.set_visual_style(
                icon_color=self._meta_text_color,
                idle_background=QColor(0, 0, 0, 0),
                hover_background=button_hover,
                pressed_background=button_pressed,
                corner_radius=self._state.button_radius,
            )

        self._rate_label.setVisible(bool(self._state.rate_text))
        self._status_label.setVisible(bool(self._state.status_text))

    def _refresh_dynamic_meta_text_colors(self) -> None:
        """根据当前填充覆盖范围刷新右侧文本颜色。"""
        self._rate_text_color = self.current_rate_text_color()
        self._status_text_color = self.current_status_text_color()

    def get_display_progress(self) -> float:
        """返回当前显示中的进度比值。"""
        return self._display_progress

    def set_display_progress(self, value: float) -> None:
        """设置当前显示中的进度比值。"""
        self._display_progress = max(0.0, min(value, 1.0))
        self._apply_state()
        self.update()

    def get_sweep_phase(self) -> float:
        """返回当前 glow sweep 相位。"""
        return self._sweep_phase_value

    def set_sweep_phase(self, value: float) -> None:
        """设置当前 glow sweep 相位。"""
        self._sweep_phase_value = max(0.0, min(value, 1.0))
        self.update()

    def paintEvent(self, event) -> None:
        """绘制整体底板、进度填充与 glow sweep。"""
        self._refresh_dynamic_meta_text_colors()
        self._rate_label.setStyleSheet(f"color: {_qcolor_to_rgba_text(self._rate_text_color)};")
        self._status_label.setStyleSheet(f"color: {_qcolor_to_rgba_text(self._status_text_color)};")
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        outer_rect = self._outer_rect()
        painter.setPen(QPen(self._track_border_color, 1))
        painter.setBrush(self._track_background_color)
        painter.drawPath(_build_uniform_round_rect_path(outer_rect, self._state.outer_radius))

        fill_rect = self._fill_rect()
        if fill_rect.width() <= 0:
            return

        fill_color = self.current_fill_color()
        clipped_fill_path = self._clipped_fill_path()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill_color)
        painter.drawPath(clipped_fill_path)

        fill_path = QPainterPath()
        fill_path.addPath(clipped_fill_path)
        glow_rect = self._glow_rect(fill_rect=fill_rect, phase=self._sweep_phase_value)
        gradient = QLinearGradient(glow_rect.left(), 0, glow_rect.right(), 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 92))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.save()
        painter.setClipPath(fill_path)
        painter.fillRect(glow_rect, gradient)
        painter.restore()

    def _outer_rect(self) -> QRectF:
        """返回去掉半像素描边偏移后的外轮廓矩形。"""
        full_rect = self.rect().adjusted(0, 0, -1, -1)
        return QRectF(full_rect).adjusted(0.5, 0.5, -0.5, -0.5)

    def _track_rect(self) -> QRectF:
        """返回实际轨道矩形。"""
        return self._outer_rect().adjusted(
            PROGRESS_FILL_PADDING,
            PROGRESS_FILL_PADDING,
            -PROGRESS_FILL_PADDING,
            -PROGRESS_FILL_PADDING,
        )

    def _fill_rect(self) -> QRectF:
        """返回当前已填充区域矩形。"""
        progress_rect = self._progress_rect()
        fill_width = progress_rect.width() * self._display_progress
        if fill_width <= 0:
            return QRectF()
        return QRectF(progress_rect.left(), progress_rect.top(), fill_width, progress_rect.height())

    def _clipped_fill_path(self) -> QPainterPath:
        """返回被外层圆角裁剪后的填充路径。"""
        fill_rect = self._fill_rect()
        if fill_rect.isNull():
            return QPainterPath()
        fill_path = _build_uniform_round_rect_path(fill_rect, self._state.inner_radius)
        outer_path = _build_uniform_round_rect_path(self._outer_rect(), self._state.outer_radius)
        return fill_path.intersected(outer_path)

    def _progress_rect(self) -> QRectF:
        """返回按钮区左侧的可填充区域。"""
        track_rect = self._track_rect()
        action_rect = self._action_rect()
        if action_rect.isNull():
            return track_rect
        progress_right = max(track_rect.left(), action_rect.left() - PROGRESS_ACTION_GAP)
        return QRectF(track_rect.left(), track_rect.top(), max(0.0, progress_right - track_rect.left()), track_rect.height())

    def _glow_rect(self, *, fill_rect: QRectF, phase: float) -> QRectF:
        """返回指定 phase 下的 glow sweep 矩形。"""
        if fill_rect.isNull():
            return QRectF()
        total_cycle = self._configured_sweep_duration_ms + self._configured_sweep_idle_delay_ms
        if total_cycle <= 0 or self._configured_sweep_duration_ms <= 0:
            return QRectF()
        motion_ratio = self._configured_sweep_duration_ms / total_cycle
        if phase >= motion_ratio:
            return QRectF()
        normalized_phase = phase / motion_ratio
        sweep_left = (fill_rect.left() - PROGRESS_GLOW_WIDTH) + (
            (fill_rect.right() - (fill_rect.left() - PROGRESS_GLOW_WIDTH)) * normalized_phase
        )
        return QRectF(sweep_left, fill_rect.top(), PROGRESS_GLOW_WIDTH, fill_rect.height())

    def debug_fill_rect(self) -> QRectF:
        """测试辅助：返回当前填充矩形。"""
        return self._fill_rect()

    def debug_clipped_fill_rect(self) -> QRectF:
        """测试辅助：返回外层裁剪后的填充包围盒。"""
        return self._clipped_fill_path().boundingRect()

    def debug_clipped_fill_contains(self, point: QPointF) -> bool:
        """测试辅助：返回裁剪后的填充路径是否包含指定点。"""
        return self._clipped_fill_path().contains(point)

    def debug_glow_rect(self, *, phase: float) -> QRectF:
        """测试辅助：返回指定相位下的 glow 矩形。"""
        return self._glow_rect(fill_rect=self._fill_rect(), phase=phase)

    def debug_action_rect(self) -> QRectF:
        """测试辅助：返回按钮区矩形。"""
        return self._action_rect()

    def debug_outer_rect(self) -> QRectF:
        """测试辅助：返回最外层轨道矩形。"""
        return self._outer_rect()

    def _action_rect(self) -> QRectF:
        """返回按钮区在组件坐标中的矩形。"""
        return QRectF(self._action_widget.geometry())

    def _dynamic_meta_color_for_widget(self, widget: QWidget, *, fallback: QColor) -> QColor:
        """按当前填充覆盖情况返回更易读的文案颜色。"""
        self._content_layout.activate()
        if widget.text() == "":
            return QColor(fallback)
        fill_rect = self._fill_rect()
        widget_rect = QRectF(widget.geometry())
        if fill_rect.isNull() or widget_rect.isNull():
            return QColor(fallback)

        overlap_rect = fill_rect.intersected(widget_rect)
        if overlap_rect.width() > 0:
            return _fill_text_color()
        return QColor(fallback)

    def resizeEvent(self, event) -> None:
        """尺寸变化后同步覆盖相关文本颜色。"""
        super().resizeEvent(event)
        self._apply_state()

    displayProgress = Property(float, get_display_progress, set_display_progress)
    sweepPhase = Property(float, get_sweep_phase, set_sweep_phase)


class GlobalProgressStripHost(QWidget):
    """负责在主窗口底部占位并承载全局进度条。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化底部占位容器。"""
        super().__init__(parent)
        self._state = GlobalProgressStripState()
        self._host_height = 0

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            PROGRESS_STRIP_HOST_HORIZONTAL_MARGIN,
            PROGRESS_STRIP_HOST_TOP_MARGIN,
            PROGRESS_STRIP_HOST_HORIZONTAL_MARGIN,
            PROGRESS_STRIP_HOST_BOTTOM_MARGIN,
        )
        layout.setSpacing(0)

        self._strip = GlobalProgressStrip(self)
        self._strip.hide()
        layout.addWidget(self._strip)

        self._height_animation = QPropertyAnimation(self, b"hostHeight", self)
        self._height_animation.setDuration(PROGRESS_STRIP_ANIMATION_MS)
        self._height_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._height_animation.finished.connect(self._sync_strip_visibility)

    def strip_widget(self) -> GlobalProgressStrip:
        """返回内部实际渲染的进度条组件。"""
        return self._strip

    def current_state(self) -> GlobalProgressStripState:
        """返回当前保存的展示状态。"""
        return self._state

    def set_state(self, state: GlobalProgressStripState, *, animate: bool = True) -> None:
        """更新当前底部进度条状态。

        Args:
            state: 新状态。
            animate: 是否对宿主高度变化启用动画。
        """
        previous_state = self._state
        self._state = state
        self._strip.set_state(state, animate=animate)
        self._sync_strip_visibility(force=True)
        target_height = self._target_host_height() if state.visible else 0
        visibility_changed = previous_state.visible != state.visible

        self._height_animation.stop()
        if animate and visibility_changed and target_height != self._host_height:
            self._height_animation.setStartValue(self._host_height)
            self._height_animation.setEndValue(target_height)
            self._height_animation.start()
        else:
            self.set_host_height(target_height)
            self._sync_strip_visibility()

    def _target_host_height(self) -> int:
        """返回显示态下宿主应占用的总高度。"""
        return (
            PROGRESS_STRIP_HOST_TOP_MARGIN
            + PROGRESS_STRIP_HEIGHT
            + PROGRESS_STRIP_HOST_BOTTOM_MARGIN
        )

    def _sync_strip_visibility(self, *, force: bool = False) -> None:
        """根据当前高度同步内部条带显隐。"""
        should_show = self._state.visible and (force or self._host_height > 0)
        self._strip.setVisible(should_show)

    def get_host_height(self) -> int:
        """返回当前宿主占位高度。"""
        return self._host_height

    def set_host_height(self, value: int) -> None:
        """设置当前宿主占位高度。"""
        self._host_height = max(0, value)
        self.setFixedHeight(self._host_height)
        self._sync_strip_visibility()

    hostHeight = Property(int, get_host_height, set_host_height)
