"""音频树与列表共用的行末复选框绘制和命中区域。"""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QWidget
from qfluentwidgets import isDarkTheme, themeColor
from qfluentwidgets.components.widgets.check_box import CheckBoxIcon

CHECK_COLUMN_WIDTH = 36


class AudioCheckDelegate(QStyledItemDelegate):
    """保留原文本样式，行末复选框由视图绘制和处理。"""

    def initStyleOption(self, option, index) -> None:
        """阻止默认委托在文本左侧再绘制一份复选框。"""
        super().initStyleOption(option, index)
        option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator

    def editorEvent(self, event, model, option, index) -> bool:
        """复选框命中只由视图处理，文本点击仍用于浏览焦点。"""
        return False


def audio_check_rect(row: QRect, viewport_width: int) -> QRect:
    """返回固定在视口右端、不受树缩进影响的复选框区域。"""
    side = 18
    return QRect(viewport_width - CHECK_COLUMN_WIDTH, row.center().y() - side // 2, side, side)


def draw_audio_check(view: QWidget, painter: QPainter, rect: QRect, state: Qt.CheckState, *, enabled: bool) -> None:
    """复用 Fluent 的强调色与三态图标，绘制单个行末指示器。"""
    dark = isDarkTheme()
    checked = state != Qt.CheckState.Unchecked
    ink = 255 if dark else 0
    border = QColor(ink, ink, ink, (141 if dark else 122) if enabled else (41 if dark else 56))
    background = themeColor() if checked and enabled else QColor(0, 0, 0, 0)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(background if checked and enabled else border)
    painter.setBrush(background)
    painter.drawRoundedRect(rect, 4, 4)
    if checked:
        icon = CheckBoxIcon.ACCEPT if state == Qt.CheckState.Checked else CheckBoxIcon.PARTIAL_ACCEPT
        icon.render(painter, rect)
    painter.restore()
