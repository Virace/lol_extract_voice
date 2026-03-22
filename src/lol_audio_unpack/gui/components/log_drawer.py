"""全局日志抽屉组件与相关几何辅助逻辑。"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QWidget
from qfluentwidgets import HeaderCardWidget, PlainTextEdit, isDarkTheme, qconfig

LOG_PANEL_MIN_HEIGHT = 248
LOG_PANEL_MAX_HEIGHT = 360
LOG_PANEL_MIN_TOP_GAP = 72
LOG_PANEL_SIDE_MARGIN = 24
LOG_PANEL_TOP_MARGIN = 16
LOG_PANEL_ANIMATION_DURATION_MS = 240
LOG_PANEL_CARD_RADIUS = 0
LOG_PANEL_HANDLE_SIZE = 21
LOG_PANEL_COLLAPSED_VISIBLE_HEIGHT = 13
LOG_PANEL_HANDLE_RIGHT_INSET = 18
LOG_PANEL_HANDLE_HOVER_LIFT = 6
LOG_PANEL_ARROW_PROGRESS_EPSILON = 1e-6
LOG_PANEL_RESIZE_HANDLE_HEIGHT = 12
LOG_PANEL_OUTPUT_TEXT_LEFT_MARGIN = 2
LOG_PANEL_CHEVRON_HALF_WIDTH = 4.1
LOG_PANEL_CHEVRON_VERTICAL_OFFSET = 2.6
LOG_PANEL_CHEVRON_CENTER_X_SHIFT = 0.35
LOG_PANEL_CHEVRON_COLLAPSED_CENTER_Y_SHIFT = 0.3
LOG_PANEL_CHEVRON_EXPANDED_CENTER_Y_SHIFT = 0.7
LOG_PANEL_CHEVRON_PEN_WIDTH = 1.8


def _build_log_panel_host_rect(window_size: QSize, navigation_width: int) -> QRect:
    """根据主窗口尺寸与导航宽度推导页面内容区矩形。

    Args:
        window_size: 主窗口当前尺寸。
        navigation_width: 当前导航栏占用宽度。

    Returns:
        近似代表页面内容区的宿主矩形。
    """
    x = max(0, navigation_width)
    width = max(0, window_size.width() - x)
    return QRect(x, 0, width, window_size.height())


def _resolve_log_panel_height(
    host_rect: QRect,
    preferred_height: int | None = None,
) -> int:
    """解析日志抽屉的实际高度。

    Args:
        host_rect: 页面内容区矩形。
        preferred_height: 用户拖拽后的期望高度，未提供时使用默认高度。

    Returns:
        已根据当前窗口尺寸夹紧后的抽屉高度。
    """
    default_height = min(
        max(int(host_rect.height() * 0.34), LOG_PANEL_MIN_HEIGHT),
        LOG_PANEL_MAX_HEIGHT,
    )
    max_height = max(
        LOG_PANEL_MIN_HEIGHT,
        host_rect.height() - LOG_PANEL_TOP_MARGIN - LOG_PANEL_MIN_TOP_GAP,
    )
    if preferred_height is None:
        return min(default_height, max_height)
    return max(LOG_PANEL_MIN_HEIGHT, min(int(preferred_height), max_height))


def _build_log_panel_geometry(
    host_rect: QRect,
    expanded: bool,
    *,
    preferred_height: int | None = None,
) -> QRect:
    """根据页面内容区计算全局日志抽屉的位置与大小。

    Args:
        host_rect: 页面内容区矩形。
        expanded: 日志抽屉是否处于展开状态。
        preferred_height: 用户拖拽后的期望高度。

    Returns:
        日志抽屉对应的目标矩形区域。
    """
    width = max(0, host_rect.width())
    height = _resolve_log_panel_height(host_rect, preferred_height)
    x = host_rect.x()
    visible_y = max(
        host_rect.y() + LOG_PANEL_TOP_MARGIN,
        host_rect.bottom() + 1 - height,
    )
    y = visible_y if expanded else host_rect.bottom() + 1
    return QRect(x, y, width, height)


def _build_log_panel_toggle_rect(
    host_rect: QRect,
    panel_rect: QRect,
    *,
    expanded: bool,
    hovered: bool,
) -> QRect:
    """根据抽屉与宿主区计算浮动把手的位置。

    Args:
        host_rect: 页面内容区矩形。
        panel_rect: 当前日志抽屉矩形。
        expanded: 抽屉是否展开。
        hovered: 把手是否处于悬停状态。

    Returns:
        把手按钮对应的目标矩形区域。
    """
    hover_lift = LOG_PANEL_HANDLE_HOVER_LIFT if hovered and not expanded else 0
    x = host_rect.right() - LOG_PANEL_SIDE_MARGIN - LOG_PANEL_HANDLE_SIZE + 1
    if expanded:
        y = panel_rect.top() - LOG_PANEL_HANDLE_SIZE // 2
    else:
        y = panel_rect.top() - LOG_PANEL_COLLAPSED_VISIBLE_HEIGHT - hover_lift
    return QRect(x, y, LOG_PANEL_HANDLE_SIZE, LOG_PANEL_HANDLE_SIZE)


class _LogDrawerHandleButton(QAbstractButton):
    """绘制带动画尖号的浮动日志抽屉把手。"""

    hover_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._arrow_progress = 0.0
        self._background_color = QColor(255, 255, 255, 244)
        self._border_color = QColor(0, 0, 0, 30)
        self._icon_color = QColor(28, 28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(LOG_PANEL_HANDLE_SIZE, LOG_PANEL_HANDLE_SIZE)

    def set_arrow_progress(self, value: float) -> None:
        """设置当前尖号方向的插值进度。

        Args:
            value: 0 表示收起态，1 表示展开态。
        """
        clamped = max(0.0, min(1.0, float(value)))
        if abs(self._arrow_progress - clamped) < LOG_PANEL_ARROW_PROGRESS_EPSILON:
            return
        self._arrow_progress = clamped
        self.update()

    def set_palette_colors(
        self,
        *,
        background: QColor,
        border: QColor,
        icon: QColor,
    ) -> None:
        """刷新把手的绘制配色。

        Args:
            background: 背景色。
            border: 边框色。
            icon: 图标色。
        """
        self._background_color = QColor(background)
        self._border_color = QColor(border)
        self._icon_color = QColor(icon)
        self.update()

    def enterEvent(self, event) -> None:
        """在鼠标进入时通知主控组件更新悬停动画。"""
        self.hover_changed.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """在鼠标离开时通知主控组件恢复默认位置。"""
        self.hover_changed.emit(False)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        """绘制圆形把手与内部尖号。"""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)

        fill_color = QColor(self._background_color)
        if self.isDown():
            fill_color = fill_color.darker(108)

        painter.setBrush(fill_color)
        painter.setPen(QPen(self._border_color, 1.2))
        painter.drawEllipse(rect)

        center_x = rect.center().x() + LOG_PANEL_CHEVRON_CENTER_X_SHIFT
        center_y_shift = (
            LOG_PANEL_CHEVRON_COLLAPSED_CENTER_Y_SHIFT
            + (LOG_PANEL_CHEVRON_EXPANDED_CENTER_Y_SHIFT - LOG_PANEL_CHEVRON_COLLAPSED_CENTER_Y_SHIFT)
            * self._arrow_progress
        )
        center_y = rect.center().y() + center_y_shift
        outer_y = (
            center_y + LOG_PANEL_CHEVRON_VERTICAL_OFFSET - 2 * LOG_PANEL_CHEVRON_VERTICAL_OFFSET * self._arrow_progress
        )
        middle_y = (
            center_y - LOG_PANEL_CHEVRON_VERTICAL_OFFSET + 2 * LOG_PANEL_CHEVRON_VERTICAL_OFFSET * self._arrow_progress
        )
        chevron_path = QPainterPath()
        chevron_path.moveTo(center_x - LOG_PANEL_CHEVRON_HALF_WIDTH, outer_y)
        chevron_path.lineTo(center_x, middle_y)
        chevron_path.lineTo(center_x + LOG_PANEL_CHEVRON_HALF_WIDTH, outer_y)
        painter.setPen(
            QPen(
                self._icon_color,
                LOG_PANEL_CHEVRON_PEN_WIDTH,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            )
        )
        painter.drawPath(chevron_path)


class _LogPanelResizeHandle(QWidget):
    """提供日志抽屉顶部垂直拖拽改高的透明热区。"""

    drag_delta = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_active = False
        self._last_global_y = 0
        self.setCursor(Qt.SizeVerCursor)

    def mousePressEvent(self, event) -> None:
        """在按下时开始记录拖拽起点。"""
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._drag_active = True
        self._last_global_y = int(event.globalPosition().toPoint().y())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        """拖拽过程中持续发出垂直位移。"""
        if not self._drag_active:
            super().mouseMoveEvent(event)
            return
        current_y = int(event.globalPosition().toPoint().y())
        delta = current_y - self._last_global_y
        if delta != 0:
            self._last_global_y = current_y
            self.drag_delta.emit(delta)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        """在释放时结束拖拽。"""
        if event.button() == Qt.LeftButton and self._drag_active:
            self._drag_active = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class GlobalLogDrawer(QObject):
    """管理主窗口底部的全局日志抽屉组件。"""

    def __init__(self, parent: QWidget) -> None:
        """初始化日志抽屉及其内部控件。

        Args:
            parent: 宿主窗口。
        """
        super().__init__(parent)
        self._parent = parent
        self._expanded = False
        self._handle_hovered = False
        self._height_override: int | None = None
        self._host_rect = QRect(0, 0, parent.width(), parent.height())

        self._card = HeaderCardWidget(parent)
        self._card.setObjectName("GlobalLogPanel")
        self._card.setBorderRadius(LOG_PANEL_CARD_RADIUS)
        self._card.setTitle("日志详情")
        self._card.headerView.setObjectName("GlobalLogPanelHeader")
        self._card.view.setObjectName("GlobalLogPanelBody")
        self._card.headerLabel.setObjectName("GlobalLogPanelTitle")
        self._card.headerLayout.setContentsMargins(20, 16, 20, 12)
        self._card.headerView.setFixedHeight(56)
        self._card.viewLayout.setContentsMargins(5, 5, 5, 5)
        self._card.viewLayout.setSpacing(0)
        self._title = self._card.headerLabel

        self._output = PlainTextEdit(self._card.view)
        self._output.setPlaceholderText("这里会同步原本输出到 shell 的运行日志。")
        self._output.setReadOnly(True)
        self._output.setViewportMargins(LOG_PANEL_OUTPUT_TEXT_LEFT_MARGIN, 0, 0, 0)
        self._card.viewLayout.addWidget(self._output, 1)

        self._resize_handle = _LogPanelResizeHandle(self._card)
        self._resize_handle.drag_delta.connect(self._resize_by_drag)

        self._toggle_btn = _LogDrawerHandleButton(parent)
        self._toggle_btn.clicked.connect(self._toggle)
        self._toggle_btn.hover_changed.connect(self._set_handle_hovered)

        self._card_animation = QPropertyAnimation(self._card, b"geometry", self)
        self._card_animation.setDuration(LOG_PANEL_ANIMATION_DURATION_MS)
        self._card_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._card_animation.valueChanged.connect(self._sync_toggle_geometry)

        self._hover_animation = QPropertyAnimation(self._toggle_btn, b"geometry", self)
        self._hover_animation.setDuration(LOG_PANEL_ANIMATION_DURATION_MS)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        qconfig.themeChanged.connect(lambda _theme: self._refresh_surface_style())
        qconfig.themeColorChanged.connect(lambda _color: self._refresh_surface_style())

        self._refresh_surface_style()
        self.set_expanded(False, animate=False)

    @property
    def output_widget(self) -> PlainTextEdit:
        """返回内部日志输出控件。"""
        return self._output

    def set_log_text(self, text: str) -> None:
        """同步日志全文到抽屉中的输出框。

        Args:
            text: 当前累计日志文本。
        """
        self._output.setPlainText(text)
        self._output.verticalScrollBar().setValue(self._output.verticalScrollBar().maximum())

    def sync_host_rect(self, host_rect: QRect, *, animate: bool = False) -> None:
        """同步当前宿主内容区并重排抽屉。

        Args:
            host_rect: 当前页面内容区矩形。
            animate: 是否在重排时使用滑动动画。
        """
        self._host_rect = QRect(host_rect)
        self._apply_layout(expanded=self._expanded, animate=animate)

    def set_expanded(self, expanded: bool, *, animate: bool = True) -> None:
        """设置日志抽屉的展开状态。

        Args:
            expanded: 是否展开。
            animate: 是否播放抽屉滑动动画。
        """
        self._expanded = expanded
        self._handle_hovered = False
        self._update_toggle_button(expanded)
        self._apply_layout(expanded=expanded, animate=animate)

    def _current_panel_rect(self, *, expanded: bool | None = None) -> QRect:
        """返回给定状态下的日志抽屉矩形。"""
        current_expanded = self._expanded if expanded is None else expanded
        return _build_log_panel_geometry(
            self._host_rect,
            current_expanded,
            preferred_height=self._height_override,
        )

    def _current_toggle_rect(
        self,
        *,
        expanded: bool | None = None,
        hovered: bool | None = None,
        panel_rect: QRect | None = None,
    ) -> QRect:
        """返回给定状态下的浮动把手矩形。"""
        current_expanded = self._expanded if expanded is None else expanded
        current_hovered = self._handle_hovered if hovered is None else hovered
        current_panel_rect = self._current_panel_rect(expanded=current_expanded) if panel_rect is None else panel_rect
        return _build_log_panel_toggle_rect(
            self._host_rect,
            current_panel_rect,
            expanded=current_expanded,
            hovered=current_hovered,
        )

    def _sync_resize_handle_geometry(self) -> None:
        """让顶部拖拽热区始终贴住抽屉上边缘。"""
        self._resize_handle.setGeometry(
            0,
            0,
            self._card.width(),
            LOG_PANEL_RESIZE_HANDLE_HEIGHT,
        )

    def _sync_toggle_geometry(self, panel_rect: QRect | None = None) -> None:
        """根据当前抽屉矩形同步圆形按钮位置。"""
        current_panel_rect = self._card.geometry() if panel_rect is None else panel_rect
        self._sync_resize_handle_geometry()
        self._toggle_btn.setGeometry(self._current_toggle_rect(panel_rect=current_panel_rect))
        self._toggle_btn.raise_()

    def _update_toggle_button(self, expanded: bool) -> None:
        """刷新切换按钮提示文案。"""
        self._toggle_btn.setToolTip("收起终端日志" if expanded else "展开终端日志")

    def _apply_layout(self, *, expanded: bool, animate: bool) -> None:
        """应用日志抽屉布局，并在需要时触发上下滑动动画。"""
        target_panel_rect = self._current_panel_rect(expanded=expanded)
        target_arrow_progress = 1.0 if expanded else 0.0
        self._card_animation.stop()
        self._hover_animation.stop()
        self._toggle_btn.set_arrow_progress(target_arrow_progress)
        self._card.raise_()

        if not animate:
            self._card.setGeometry(target_panel_rect)
            self._sync_toggle_geometry(target_panel_rect)
            return

        self._sync_toggle_geometry(self._card.geometry())
        self._card_animation.setStartValue(self._card.geometry())
        self._card_animation.setEndValue(target_panel_rect)
        self._card_animation.start()

    def _resize_by_drag(self, delta_y: int) -> None:
        """按用户拖拽距离调整抽屉高度，并保持底边固定。"""
        if not self._expanded:
            return
        current_height = self._card.height()
        self._height_override = _resolve_log_panel_height(
            self._host_rect,
            current_height - delta_y,
        )
        self._apply_layout(expanded=True, animate=False)

    def _refresh_surface_style(self) -> None:
        """按当前主题刷新抽屉外壳、标题条和把手样式。"""
        if isDarkTheme():
            card_border = "rgba(255, 255, 255, 41)"
            card_background = "rgb(28, 31, 38)"
            title_color = "rgb(245, 245, 245)"
            editor_background = "rgb(28, 31, 38)"
            editor_border = "rgba(255, 255, 255, 28)"
            handle_background = QColor(34, 37, 44, 244)
            handle_border = QColor(255, 255, 255, 58)
            handle_icon = QColor(245, 245, 245)
        else:
            card_border = "rgba(0, 0, 0, 26)"
            card_background = "rgb(255, 255, 255)"
            title_color = "rgb(28, 28, 28)"
            editor_background = "rgb(255, 255, 255)"
            editor_border = "rgba(0, 0, 0, 20)"
            handle_background = QColor(255, 255, 255, 244)
            handle_border = QColor(0, 0, 0, 28)
            handle_icon = QColor(28, 28, 28)

        self._card.setStyleSheet(
            f"""
            HeaderCardWidget#GlobalLogPanel {{
                background-color: {card_background};
                border: 1px solid {card_border};
                border-radius: {LOG_PANEL_CARD_RADIUS}px;
            }}
            QWidget#GlobalLogPanelHeader {{
                background-color: transparent;
                border: none;
            }}
            QWidget#GlobalLogPanelBody {{
                background-color: transparent;
                border: none;
            }}
            """
        )
        self._title.setStyleSheet(
            f"""
            QLabel#GlobalLogPanelTitle {{
                border: none;
                background-color: transparent;
                color: {title_color};
                padding: 0;
            }}
            """
        )
        self._output.setStyleSheet(
            f"""
            PlainTextEdit {{
                background-color: {editor_background};
                border: 1px solid {editor_border};
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 12px;
                padding-left: {LOG_PANEL_OUTPUT_TEXT_LEFT_MARGIN}px;
            }}
            """
        )
        self._toggle_btn.set_palette_colors(
            background=handle_background,
            border=handle_border,
            icon=handle_icon,
        )

    def _toggle(self) -> None:
        """切换日志抽屉的展开状态。"""
        self.set_expanded(not self._expanded)

    def _set_handle_hovered(self, hovered: bool) -> None:
        """更新把手悬停状态并触发布局动画。"""
        if self._expanded or (self._card_animation.state() != QAbstractAnimation.State.Stopped):
            if self._handle_hovered:
                self._handle_hovered = False
            return
        if self._handle_hovered == hovered:
            return
        self._handle_hovered = hovered
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._toggle_btn.geometry())
        self._hover_animation.setEndValue(self._current_toggle_rect())
        self._hover_animation.start()


__all__ = [
    "GlobalLogDrawer",
    "LOG_PANEL_COLLAPSED_VISIBLE_HEIGHT",
    "LOG_PANEL_HANDLE_SIZE",
    "LOG_PANEL_MAX_HEIGHT",
    "LOG_PANEL_MIN_HEIGHT",
    "LOG_PANEL_MIN_TOP_GAP",
    "LOG_PANEL_SIDE_MARGIN",
    "LOG_PANEL_TOP_MARGIN",
    "_build_log_panel_geometry",
    "_build_log_panel_host_rect",
    "_build_log_panel_toggle_rect",
    "_resolve_log_panel_height",
]
