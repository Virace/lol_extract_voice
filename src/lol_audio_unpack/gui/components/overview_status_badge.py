"""实体总览列表中可复用的状态徽章能力。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QLabel, QWidget
from qfluentwidgets import CustomStyleSheet, isDarkTheme, setCustomStyleSheet, setStyleSheet

from lol_audio_unpack.gui.common.styles import (
    get_fluent_status_badge_color_pair,
    resolve_fluent_entity_badge_colors,
    resolve_fluent_status_badge_colors,
)

STATUS_BADGE_SIZE = 24
STATUS_PILL_HORIZONTAL_PADDING = 9
STATUS_PILL_DIAGONAL_OFFSET = 6


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

    background_pair, foreground_pair = get_fluent_status_badge_color_pair(status)
    return (
        build_style(background_pair[0], foreground_pair[0]),
        build_style(background_pair[1], foreground_pair[1]),
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
    _ = palette
    return resolve_fluent_status_badge_colors(status)


def resolve_status_pill_segment_colors(
    badge_label: str,
    badge_status: str,
    palette: QPalette,
) -> tuple[QColor, QColor]:
    """根据段标签与状态返回分段胶囊的配色。

    A/M 两段固定表达资源类型；存在态跟随当前主题 preset，
    缺失态统一退回透明底与弱化文字，避免用户再额外记忆颜色语义。
    """
    normalized_label = badge_label.upper().strip()
    normalized_status = badge_status.strip()

    if normalized_label == "A":
        return resolve_fluent_entity_badge_colors("audio", normalized_status, palette)

    if normalized_label == "M":
        return resolve_fluent_entity_badge_colors("mapping", normalized_status, palette)

    return resolve_status_badge_colors(badge_status, palette)


def measure_status_pill_width(segment_labels: Sequence[str], font_metrics: QFontMetrics) -> int:
    """根据段标签和字体度量计算分段胶囊宽度。"""
    widths = _measure_status_pill_segment_widths(segment_labels, font_metrics)
    if not widths:
        return 0
    return sum(widths)


def _measure_status_pill_segment_widths(
    segment_labels: Sequence[str],
    font_metrics: QFontMetrics,
) -> tuple[int, ...]:
    """计算每一段在当前字体下的理想宽度。"""
    if not segment_labels:
        return ()

    segment_width = max(
        STATUS_BADGE_SIZE,
        max(font_metrics.horizontalAdvance(label) for label in segment_labels) + STATUS_PILL_HORIZONTAL_PADDING * 2,
    )
    return tuple(segment_width for _label in segment_labels)


def _build_status_pill_segment_polygons(
    rect: QRect,
    segment_widths: Sequence[int],
    *,
    diagonal_offset: int = STATUS_PILL_DIAGONAL_OFFSET,
) -> tuple[QPolygonF, ...]:
    """构造分段胶囊每一段的多边形。"""
    if not segment_widths:
        return ()

    bounds = QRectF(rect)
    top = bounds.top()
    bottom = bounds.top() + bounds.height()
    current_left = bounds.left()
    boundaries = [current_left]
    for width in segment_widths:
        current_left += width
        boundaries.append(current_left)

    diagonal_half = diagonal_offset / 2
    polygons: list[QPolygonF] = []

    for index, _width in enumerate(segment_widths):
        is_first = index == 0
        is_last = index == len(segment_widths) - 1
        segment_left = boundaries[index]
        segment_right = boundaries[index + 1]
        polygons.append(
            QPolygonF(
                [
                    QPointF(segment_left if is_first else segment_left + diagonal_half, top),
                    QPointF(segment_right if is_last else segment_right + diagonal_half, top),
                    QPointF(segment_right if is_last else segment_right - diagonal_half, bottom),
                    QPointF(segment_left if is_first else segment_left - diagonal_half, bottom),
                ]
            )
        )

    return tuple(polygons)


def _build_status_pill_seam_lines(
    rect: QRect,
    segment_widths: Sequence[int],
    *,
    diagonal_offset: int = STATUS_PILL_DIAGONAL_OFFSET,
) -> tuple[tuple[QPointF, QPointF], ...]:
    """根据段宽生成与接缝重合的斜切分隔线。"""
    if len(segment_widths) <= 1:
        return ()

    outline_bounds = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    current_left = float(outline_bounds.left())
    seam_lines: list[tuple[QPointF, QPointF]] = []
    diagonal_half = diagonal_offset / 2
    top = float(outline_bounds.top())
    bottom = float(outline_bounds.bottom())

    for width in segment_widths[:-1]:
        current_left += width
        seam_lines.append(
            (
                QPointF(current_left + diagonal_half, top),
                QPointF(current_left - diagonal_half, bottom),
            )
        )

    return tuple(seam_lines)


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


def resolve_status_pill_chrome_colors(palette: QPalette) -> tuple[QColor, QColor]:
    """按当前主题返回胶囊接缝线与外轮廓颜色。"""
    if palette is None:
        raise ValueError("palette must not be None")

    if isDarkTheme():
        seam = QColor(palette.color(QPalette.ColorRole.Midlight))
        seam.setAlpha(186)
        outline = QColor(palette.color(QPalette.ColorRole.Light))
        outline.setAlpha(148)
        return seam, outline

    seam = QColor(palette.color(QPalette.ColorRole.Mid))
    seam.setAlpha(136)
    outline = QColor(palette.color(QPalette.ColorRole.Mid))
    outline.setAlpha(92)
    return seam, outline


def paint_status_pill(
    painter: QPainter,
    rect: QRect,
    segments: Sequence[tuple[str, str]],
    *,
    palette: QPalette,
) -> None:
    """按当前主题绘制支持斜切分段的胶囊徽章。"""
    if not segments:
        return

    segment_labels = tuple(label for label, _status in segments)
    segment_widths = _measure_status_pill_segment_widths(segment_labels, painter.fontMetrics())
    segment_polygons = _build_status_pill_segment_polygons(rect, segment_widths)
    bounds = QRectF(rect)
    radius = bounds.height() / 2
    segment_rects: list[QRectF] = []
    segment_left = bounds.left()
    for width in segment_widths:
        segment_rects.append(QRectF(segment_left, bounds.top(), width, bounds.height()))
        segment_left += width
    clip_path = QPainterPath()
    clip_path.addRoundedRect(bounds, radius, radius)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setClipPath(clip_path)
    painter.setPen(Qt.PenStyle.NoPen)

    for polygon, segment_rect, (label, status) in zip(segment_polygons, segment_rects, segments, strict=False):
        background, foreground = resolve_status_pill_segment_colors(label, status, palette)
        painter.setBrush(background)
        painter.drawPolygon(polygon)
        painter.setPen(foreground)
        painter.drawText(segment_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(Qt.PenStyle.NoPen)

    if len(segment_rects) > 1:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        seam_color, outline = resolve_status_pill_chrome_colors(palette)
        seam_pen = QPen(seam_color)
        seam_pen.setWidthF(1.2)
        seam_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(seam_pen)
        for start, end in _build_status_pill_seam_lines(rect, segment_widths):
            painter.drawLine(start, end)
    else:
        _seam_color, outline = resolve_status_pill_chrome_colors(palette)

    painter.setClipping(False)
    outline_pen = QPen(outline)
    outline_pen.setWidthF(1.0)
    outline_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(outline_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(bounds.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    painter.restore()


__all__ = [
    "STATUS_BADGE_SIZE",
    "STATUS_PILL_DIAGONAL_OFFSET",
    "STATUS_PILL_HORIZONTAL_PADDING",
    "_build_status_badge_styles",
    "_build_status_pill_segment_polygons",
    "_build_status_pill_seam_lines",
    "_create_status_badge",
    "measure_status_pill_width",
    "paint_status_pill",
    "paint_status_badge",
    "resolve_status_badge_colors",
    "resolve_status_pill_chrome_colors",
    "resolve_status_pill_segment_colors",
]
