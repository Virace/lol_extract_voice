"""实体总览列表中可复用的状态徽章能力。"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QLabel, QWidget
from qfluentwidgets import CustomStyleSheet, setCustomStyleSheet, setStyleSheet

STATUS_BADGE_SIZE = 24
DARK_THEME_LIGHTNESS_THRESHOLD = 128
STATUS_AVAILABLE_LIGHT_BACKGROUND = "#0F7B0F"
STATUS_AVAILABLE_DARK_BACKGROUND = "#6CCB5F"
STATUS_MISSING_LIGHT_BACKGROUND = "#9D5D00"
STATUS_MISSING_DARK_BACKGROUND = "#FFF4CE"
STATUS_LIGHT_FOREGROUND = "#FFFFFF"
STATUS_DARK_FOREGROUND = "#111111"


def _build_status_badge_styles(status: str) -> tuple[str, str]:
    """构造状态徽章在亮暗主题下的样式文本。

    Args:
        status: 当前状态文案。

    Returns:
        亮色主题与暗色主题对应的样式表文本。
    """

    def build_style(background: str, foreground: str) -> str:
        return f"""
        QLabel {{
            background-color: {background};
            color: {foreground};
            border-radius: {STATUS_BADGE_SIZE // 2}px;
            font-size: 13px;
            font-weight: 500;
        }}
        """

    if status == "已存在":
        return (
            build_style(STATUS_AVAILABLE_LIGHT_BACKGROUND, STATUS_LIGHT_FOREGROUND),
            build_style(STATUS_AVAILABLE_DARK_BACKGROUND, STATUS_DARK_FOREGROUND),
        )

    return (
        build_style(STATUS_MISSING_LIGHT_BACKGROUND, STATUS_LIGHT_FOREGROUND),
        build_style(STATUS_MISSING_DARK_BACKGROUND, STATUS_DARK_FOREGROUND),
    )


def _create_status_badge(kind: str, status: str, parent: QWidget) -> QLabel:
    """创建实体列表中的轻量状态徽章。

    Args:
        kind: 徽章类型，目前支持 ``audio`` 与 ``mapping``。
        status: 当前状态文案。
        parent: 徽章父控件。

    Returns:
        已注册到 QFluentWidgets 主题系统的圆形徽章标签。
    """
    label = "A" if kind == "audio" else "M"
    display_name = "音频" if kind == "audio" else "映射"
    badge = QLabel(label, parent)
    badge.setAlignment(Qt.AlignCenter)
    badge.setFixedSize(STATUS_BADGE_SIZE, STATUS_BADGE_SIZE)
    badge.setContentsMargins(0, 0, 0, 0)
    light_qss, dark_qss = _build_status_badge_styles(status)
    setCustomStyleSheet(badge, light_qss, dark_qss)
    setStyleSheet(badge, CustomStyleSheet(badge))
    badge.setToolTip(f"{display_name}：{status}")
    return badge


def resolve_status_badge_colors(status: str, palette: QPalette) -> tuple[QColor, QColor]:
    """根据主题与状态返回徽章底色和前景色。

    Args:
        status: 当前状态文案。
        palette: 当前绘制使用的调色板。

    Returns:
        ``(background, foreground)`` 颜色对。
    """
    is_dark = palette.color(QPalette.ColorRole.Base).lightness() < DARK_THEME_LIGHTNESS_THRESHOLD
    if status == "已存在":
        background = QColor(STATUS_AVAILABLE_DARK_BACKGROUND if is_dark else STATUS_AVAILABLE_LIGHT_BACKGROUND)
        foreground = QColor(STATUS_DARK_FOREGROUND if is_dark else STATUS_LIGHT_FOREGROUND)
    else:
        background = QColor(STATUS_MISSING_DARK_BACKGROUND if is_dark else STATUS_MISSING_LIGHT_BACKGROUND)
        foreground = QColor(STATUS_DARK_FOREGROUND if is_dark else STATUS_LIGHT_FOREGROUND)
    return background, foreground


def paint_status_badge(
    painter: QPainter,
    rect: QRect,
    badge_label: str,
    badge_status: str,
    *,
    palette: QPalette,
) -> None:
    """按当前主题直接绘制圆形状态徽章。

    Args:
        painter: 当前行绘制使用的 painter。
        rect: 徽章矩形区域。
        badge_label: 徽章中间显示的单字符文案。
        badge_status: 当前状态文案。
        palette: 当前绘制使用的调色板。
    """
    background, foreground = resolve_status_badge_colors(badge_status, palette)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(rect, STATUS_BADGE_SIZE / 2, STATUS_BADGE_SIZE / 2)
    painter.setPen(foreground)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, badge_label)


__all__ = [
    "STATUS_BADGE_SIZE",
    "_build_status_badge_styles",
    "_create_status_badge",
    "paint_status_badge",
    "resolve_status_badge_colors",
]
