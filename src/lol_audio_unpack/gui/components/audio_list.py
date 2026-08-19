"""实体总览全部音频模式使用的轻量路径级列表。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from lol_audio_unpack.app.artifacts import AudioRef

AUDIO_REF_ROLE = int(Qt.ItemDataRole.UserRole) + 1
EMPTY_MODEL_INDEX = QModelIndex()
_ITEM_HEIGHT = 48
_ROW_MARGIN = 6
_AUDIO_BUTTON_SIZE = 20


class AudioListModel(QAbstractListModel):
    """以稳定相对路径为身份的全部音频列表模型。"""

    def __init__(self, parent=None) -> None:
        """初始化列表模型。

        Args:
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._refs: tuple[AudioRef, ...] = ()

    def set_audio_refs(self, refs: tuple[AudioRef, ...]) -> None:
        """替换当前实体的全部路径级音频引用。

        Args:
            refs: 按稳定相对路径排序的音频引用。
        """
        self.beginResetModel()
        self._refs = tuple(sorted(refs, key=lambda ref: ref.relative_path))
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> int:
        """返回平铺列表行数。"""
        return 0 if parent.isValid() else len(self._refs)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        """按角色返回列表项的显示信息和稳定引用。"""
        if not index.isValid() or not 0 <= index.row() < len(self._refs):
            return None

        ref = self._refs[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return ref.wem_id
        if role == Qt.ItemDataRole.ToolTipRole:
            return ref.relative_path
        if role == AUDIO_REF_ROLE:
            return ref
        return None


class AudioListFilterModel(QSortFilterProxyModel):
    """在模型层按 WEM ID、相对路径和可靠类型筛选平铺音频。"""

    def __init__(self, parent=None) -> None:
        """初始化筛选代理。"""
        super().__init__(parent)
        self._keyword = ""
        self.setDynamicSortFilter(True)

    def set_keyword(self, keyword: str) -> None:
        """更新当前筛选关键字。

        Args:
            keyword: 用户输入的搜索文本。
        """
        normalized = keyword.strip().casefold()
        if normalized == self._keyword:
            return
        self._keyword = normalized
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """判断源模型行是否匹配当前音频搜索。"""
        if not self._keyword:
            return True

        source = self.sourceModel()
        if source is None:
            return False
        index = source.index(source_row, 0, source_parent)
        ref = source.data(index, AUDIO_REF_ROLE)
        if not isinstance(ref, AudioRef):
            return False

        parts = [ref.wem_id, ref.relative_path]
        if ref.audio_type:
            parts.append(ref.audio_type)
        return any(self._keyword in part.casefold() for part in parts)


class _AudioListDelegate(QStyledItemDelegate):
    """绘制两行文本与轻量播放按钮，不创建逐行 QWidget。"""

    def __init__(self, view: AudioListView) -> None:
        """初始化委托。

        Args:
            view: 承载当前委托的音频列表视图。
        """
        super().__init__(view)
        self._view = view

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        """返回稳定的两行列表项高度。"""
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), _ITEM_HEIGHT))
        return size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """绘制路径级 WEM 行的播放状态和可区分路径。"""
        ref = index.data(AUDIO_REF_ROLE)
        if not isinstance(ref, AudioRef):
            super().paint(painter, option, index)
            return

        row_rect = option.rect.adjusted(_ROW_MARGIN, 2, -_ROW_MARGIN, -2)
        is_active = self._view.is_active(ref)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if is_active or is_selected or is_hovered:
            color = QColor("#2563eb" if is_active else "#64748b")
            color.setAlpha(64 if is_active else 30)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(row_rect, 6, 6)

        button_rect = self._view.audio_control_rect(index)
        button_color = QColor("#2563eb")
        button_color.setAlpha(115 if is_active else 72)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(button_color)
        painter.drawRoundedRect(button_rect, 5, 5)

        text_rect = row_rect.adjusted(10, 4, -button_rect.width() - 16, -4)
        painter.setPen(option.palette.text().color())
        primary_font = option.font
        primary_font.setBold(True)
        painter.setFont(primary_font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, ref.wem_id)

        secondary = ref.relative_path
        if ref.audio_type:
            secondary = f"{ref.audio_type} · {secondary}"
        secondary_font = option.font
        secondary_font.setPointSize(max(7, secondary_font.pointSize() - 1))
        painter.setFont(secondary_font)
        secondary_color = option.palette.text().color()
        secondary_color.setAlpha(170)
        painter.setPen(secondary_color)
        painter.drawText(
            text_rect.adjusted(0, 20, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, secondary
        )

        icon_color = QColor("#ffffff")
        painter.setBrush(icon_color)
        if is_active and self._view.is_playing:
            side = max(6, button_rect.width() - 10)
            stop_rect = button_rect.adjusted(
                (button_rect.width() - side) // 2,
                (button_rect.height() - side) // 2,
                -((button_rect.width() - side) // 2),
                -((button_rect.height() - side) // 2),
            )
            painter.drawRoundedRect(stop_rect, 1, 1)
        else:
            painter.drawPolygon(
                QPolygonF(
                    [
                        button_rect.topLeft() + QPoint(8, 5),
                        button_rect.bottomLeft() + QPoint(8, -5),
                        button_rect.center() + QPoint(5, 0),
                    ]
                )
            )
        painter.restore()


class AudioListView(QListView):
    """按路径显示并交互全部 WEM 的轻量视图。"""

    audio_ref_toggle_requested = Signal(object)
    audio_context_menu_requested = Signal(object, QPoint)
    audio_ref_selected = Signal(object)

    def __init__(self, parent=None) -> None:
        """初始化音频列表视图与其源/筛选模型。"""
        super().__init__(parent)
        self._active_audio_path: Path | None = None
        self._is_playing = False
        self.source_model = AudioListModel(self)
        self.filter_model = AudioListFilterModel(self)
        self.filter_model.setSourceModel(self.source_model)
        self.setModel(self.filter_model)
        self.setItemDelegate(_AudioListDelegate(self))
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setSpacing(2)
        selection_model = self.selectionModel()
        if selection_model is not None:
            selection_model.currentChanged.connect(self._on_current_changed)

    @property
    def is_playing(self) -> bool:
        """返回当前精确条目是否正在播放。"""
        return self._is_playing

    def set_audio_refs(self, refs: tuple[AudioRef, ...]) -> None:
        """加载当前实体的所有路径级 WEM。"""
        self.source_model.set_audio_refs(refs)

    def set_keyword(self, keyword: str) -> None:
        """更新模型层筛选关键字。"""
        self.filter_model.set_keyword(keyword)

    def audio_ref_at(self, index: QModelIndex) -> AudioRef | None:
        """返回给定视图索引对应的稳定音频引用。"""
        if not index.isValid():
            return None
        ref = index.data(AUDIO_REF_ROLE)
        return ref if isinstance(ref, AudioRef) else None

    def audio_control_rect(self, index: QModelIndex):
        """返回指定列表行的播放按钮命中区域。"""
        rect = self.visualRect(index)
        side = min(_AUDIO_BUTTON_SIZE, max(14, rect.height() - 14))
        return rect.adjusted(rect.width() - side - 10, (rect.height() - side) // 2, -10, -((rect.height() - side) // 2))

    def is_active(self, ref: AudioRef) -> bool:
        """判断路径级引用是否为当前播放目标。"""
        return self._active_audio_path == ref.path

    def set_audio_playback_state(self, audio_path: Path | None, *, is_playing: bool) -> None:
        """按精确路径更新列表行的播放显示状态。"""
        self._active_audio_path = Path(audio_path) if audio_path is not None else None
        self._is_playing = bool(is_playing and self._active_audio_path)
        self.viewport().update()

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """在选择一条平铺音频时上报其精确引用。"""
        ref = self.audio_ref_at(current)
        if ref is not None:
            self.audio_ref_selected.emit(ref)

    def mouseReleaseEvent(self, event) -> None:
        """在播放按钮上发出精确音频引用，其他区域保持默认选择。"""
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            ref = self.audio_ref_at(index)
            if ref is not None and self.audio_control_rect(index).contains(event.position().toPoint()):
                self.audio_ref_toggle_requested.emit(ref)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        """为当前精确音频项请求与事件树一致的路径操作菜单。"""
        ref = self.audio_ref_at(self.indexAt(event.pos()))
        if ref is None:
            event.ignore()
            return
        self.audio_context_menu_requested.emit(ref, event.globalPos())
        event.accept()


__all__ = [
    "AUDIO_REF_ROLE",
    "AudioListFilterModel",
    "AudioListModel",
    "AudioListView",
]
