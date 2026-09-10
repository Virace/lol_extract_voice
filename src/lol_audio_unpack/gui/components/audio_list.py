"""实体总览全部音频模式使用的轻量路径级列表。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QPointF,
    QRect,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QPainter, QPolygonF
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem
from qfluentwidgets import CustomStyleSheet, isDarkTheme, setCustomStyleSheet, setStyleSheet

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.app.audio_selection import AudioSelection
from lol_audio_unpack.gui.common.styles import (
    build_fluent_list_shell_theme_pair,
    resolve_fluent_neutral_surface,
    resolve_fluent_text_primary_color,
)
from lol_audio_unpack.gui.components.audio_check import (
    CHECK_COLUMN_WIDTH,
    AudioCheckDelegate,
    audio_check_rect,
    draw_audio_check,
)
from lol_audio_unpack.gui.components.audio_row_style import (
    AUDIO_ROW_BUTTON_GAP,
    AUDIO_ROW_BUTTON_LEADING_INSET,
    AUDIO_ROW_BUTTON_SIZE,
    AUDIO_ROW_HORIZONTAL_MARGIN,
    AUDIO_ROW_SELECTED_BAR_MARGIN,
    AUDIO_ROW_SELECTED_BAR_WIDTH,
    active_audio_row_color,
    audio_control_colors,
    audio_progress_color,
    audio_selection_bar_color,
)

AUDIO_REF_ROLE = int(Qt.ItemDataRole.UserRole) + 1
EMPTY_MODEL_INDEX = QModelIndex()
_ITEM_HEIGHT = 32
_LAYOUT_BATCH_SIZE = 512


def _build_styles() -> tuple[str, str]:
    """构造全部音频列表的透明亮暗主题样式。"""
    # 顶部 2px 对齐英雄列表首项留白，水平内收统一由行绘制负责。
    return build_fluent_list_shell_theme_pair(
        light_background="transparent",
        dark_background="transparent",
        light_border="none",
        dark_border="none",
        border_radius="0",
        padding="2px 0 0 0",
        item_min_height=_ITEM_HEIGHT,
        item_border_radius=0,
        extra_item_rules="""
        padding-left: 0;
        padding-right: 0;
        """,
    )


def inject_audio_list_style(list_view: QListView) -> None:
    """为全部音频列表挂载透明壳层样式。"""
    light_qss, dark_qss = _build_styles()
    setCustomStyleSheet(list_view, light_qss, dark_qss)
    setStyleSheet(list_view, CustomStyleSheet(list_view))


class AudioListModel(QAbstractListModel):
    """以稳定相对路径为身份的全部音频列表模型。"""

    selection_changed = Signal()

    def __init__(self, parent=None) -> None:
        """初始化列表模型。

        Args:
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._refs: tuple[AudioRef, ...] = ()
        self.audio_selection: AudioSelection | None = None
        self.selection_mode = False

    def set_audio_refs(self, refs: tuple[AudioRef, ...]) -> None:
        """替换当前实体的全部路径级音频引用。

        Args:
            refs: 按稳定相对路径排序的音频引用。
        """
        self.beginResetModel()
        self._refs = tuple(refs)
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
        if role == Qt.ItemDataRole.CheckStateRole and self.selection_mode:
            return (
                Qt.CheckState.Checked
                if self.audio_selection is not None and self.audio_selection.contains(ref.path)
                else Qt.CheckState.Unchecked
            )
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """选择模式提供可访问的勾选语义，不改变浏览单选。"""
        flags = super().flags(index)
        if self.selection_mode and index.isValid():
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index: QModelIndex, value: Any, role: int = int(Qt.ItemDataRole.EditRole)) -> bool:
        """修改当前精确路径的导出选择。"""
        ref = self.data(index, AUDIO_REF_ROLE)
        if (
            role != Qt.ItemDataRole.CheckStateRole
            or not self.selection_mode
            or self.audio_selection is None
            or ref is None
        ):
            return False
        self.audio_selection.set_paths((ref.path,), value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value))
        self.selection_changed.emit()
        return True


class AudioListFilterModel(QSortFilterProxyModel):
    """在模型层按 WEM ID、相对路径和可靠类型筛选平铺音频。"""

    def __init__(self, parent=None) -> None:
        """初始化筛选代理。"""
        super().__init__(parent)
        self._keyword = ""
        self.only_selected = False
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
        source = self.sourceModel()
        if source is None:
            return False
        index = source.index(source_row, 0, source_parent)
        ref = source.data(index, AUDIO_REF_ROLE)
        if not isinstance(ref, AudioRef):
            return False
        if self.only_selected and (source.audio_selection is None or not source.audio_selection.contains(ref.path)):
            return False
        if not self._keyword:
            return True

        parts = [ref.wem_id, ref.relative_path]
        if ref.audio_type:
            parts.append(ref.audio_type)
        return any(self._keyword in part.casefold() for part in parts)


class _AudioListDelegate(AudioCheckDelegate):
    """按事件树叶子风格绘制紧凑单行试听项。"""

    def __init__(self, view: AudioListView) -> None:
        """初始化委托。

        Args:
            view: 承载当前委托的音频列表视图。
        """
        super().__init__(view)
        self._view = view

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        """返回与事件树叶子一致的紧凑行高。"""
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), _ITEM_HEIGHT))
        return size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """绘制路径级 WEM 行的统一背景、进度与播放控件。"""
        ref = index.data(AUDIO_REF_ROLE)
        if not isinstance(ref, AudioRef):
            super().paint(painter, option, index)
            return

        row_rect = self._view.row_rect(option.rect)
        is_active = self._view.is_active(ref)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if is_active or is_selected or is_hovered:
            if is_active and not is_selected and not is_hovered:
                color = active_audio_row_color(is_dark=isDarkTheme())
            else:
                color = resolve_fluent_neutral_surface("emphasis_selected" if is_selected else "emphasis_hover")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(row_rect, 6, 6)

        progress = self._view.playback_progress(ref)
        if progress > 0:
            progress_width = max(0, min(row_rect.width(), int(round(row_rect.width() * progress))))
            painter.save()
            painter.setClipRect(QRect(row_rect.left(), row_rect.top(), progress_width, row_rect.height()))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(audio_progress_color(is_dark=isDarkTheme(), is_playing=self._view.is_playing))
            painter.drawRoundedRect(row_rect, 6, 6)
            painter.restore()

        if is_selected:
            bar_rect = QRect(
                row_rect.left() + AUDIO_ROW_SELECTED_BAR_MARGIN,
                row_rect.top() + 7,
                AUDIO_ROW_SELECTED_BAR_WIDTH,
                max(0, row_rect.height() - 14),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(audio_selection_bar_color(is_dark=isDarkTheme()))
            painter.drawRoundedRect(bar_rect, 2, 2)

        button_rect = self._view.audio_control_rect(index)
        if is_active:
            button_color, icon_color = audio_control_colors(is_dark=isDarkTheme())
        else:
            button_color = resolve_fluent_neutral_surface("emphasis_hover")
            button_color.setAlpha(20)
            icon_color = resolve_fluent_text_primary_color()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(button_color)
        painter.drawRoundedRect(button_rect, 5, 5)

        text_left = button_rect.right() + AUDIO_ROW_BUTTON_GAP + 1
        text_rect = QRect(text_left, option.rect.top(), max(0, row_rect.right() - text_left - 8), option.rect.height())
        if self._view.source_model.selection_mode:
            text_rect.adjust(0, 0, -CHECK_COLUMN_WIDTH, 0)
            draw_audio_check(
                self._view,
                painter,
                audio_check_rect(row_rect, self._view.viewport().width()),
                index.data(Qt.ItemDataRole.CheckStateRole),
                enabled=True,
            )
        painter.setPen(option.palette.text().color())
        painter.setFont(option.font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, ref.wem_id)

        painter.setBrush(icon_color)
        if is_active and self._view.is_playing:
            side = max(6, min(button_rect.width(), button_rect.height()) - 10)
            stop_rect = QRect(0, 0, side, side)
            stop_rect.moveCenter(button_rect.center())
            painter.drawRoundedRect(stop_rect, 1, 1)
        else:
            painter.drawPolygon(
                QPolygonF(
                    (
                        QPointF(
                            button_rect.left() + button_rect.width() * 0.36,
                            button_rect.top() + button_rect.height() * 0.26,
                        ),
                        QPointF(
                            button_rect.left() + button_rect.width() * 0.36,
                            button_rect.bottom() - button_rect.height() * 0.26,
                        ),
                        QPointF(button_rect.right() - button_rect.width() * 0.24, button_rect.center().y()),
                    )
                )
            )
        painter.restore()


class AudioListView(QListView):
    """按路径显示并交互全部 WEM 的轻量视图。"""

    audio_ref_toggle_requested = Signal(object)
    audio_context_menu_requested = Signal(object, QPoint)
    audio_ref_selected = Signal(object)
    export_selection_requested = Signal(QModelIndex, QModelIndex)

    def __init__(self, parent=None) -> None:
        """初始化音频列表视图与其源/筛选模型。"""
        super().__init__(parent)
        self._active_audio_path: Path | None = None
        self._ctrl_export_click = False
        self._export_anchor = QPersistentModelIndex()
        self._active_audio_progress = 0.0
        self._is_playing = False
        self._is_paused = False
        self.source_model = AudioListModel(self)
        self.filter_model = AudioListFilterModel(self)
        self.filter_model.setSourceModel(self.source_model)
        self.setModel(self.filter_model)
        self.setItemDelegate(_AudioListDelegate(self))
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(_LAYOUT_BATCH_SIZE)
        self.setMouseTracking(True)
        self.setSpacing(0)
        inject_audio_list_style(self)
        selection_model = self.selectionModel()
        if selection_model is not None:
            selection_model.currentChanged.connect(self._on_current_changed)

    @property
    def is_playing(self) -> bool:
        """返回当前精确条目是否正在播放。"""
        return self._is_playing

    @property
    def is_paused(self) -> bool:
        """返回当前精确条目是否处于暂停状态。"""
        return self._is_paused

    @property
    def active_progress(self) -> float:
        """返回当前精确条目的归一化播放进度。"""
        return self._active_audio_progress

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

    @staticmethod
    def row_rect(rect: QRect) -> QRect:
        """返回列表项在视口内的整行背景矩形。"""
        return QRect(
            AUDIO_ROW_HORIZONTAL_MARGIN,
            rect.top() + 2,
            max(0, rect.width() - AUDIO_ROW_HORIZONTAL_MARGIN * 2),
            max(0, rect.height() - 4),
        )

    def audio_control_rect(self, index: QModelIndex) -> QRect:
        """返回指定列表行左侧播放按钮的命中区域。"""
        row_rect = self.row_rect(self.visualRect(index))
        side = max(12, min(AUDIO_ROW_BUTTON_SIZE, row_rect.height() - 8))
        left = row_rect.left() + AUDIO_ROW_BUTTON_LEADING_INSET
        return QRect(left, row_rect.center().y() - side // 2, side, side)

    def is_active(self, ref: AudioRef) -> bool:
        """判断路径级引用是否为当前播放目标。"""
        return self._active_audio_path == ref.path

    def playback_progress(self, ref: AudioRef) -> float:
        """返回给定路径级引用的试听进度。"""
        if not self.is_active(ref):
            return 0.0
        return self._active_audio_progress

    def set_audio_playback_state(
        self,
        audio_path: Path | None,
        *,
        progress: float,
        is_playing: bool,
        is_paused: bool,
    ) -> None:
        """按精确路径更新列表行的播放按钮与进度状态。"""
        self._active_audio_path = Path(audio_path) if audio_path is not None else None
        self._active_audio_progress = max(0.0, min(1.0, float(progress)))
        self._is_playing = bool(is_playing and self._active_audio_path)
        self._is_paused = bool(is_paused and self._active_audio_path)
        self.viewport().update()

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """在选择一条平铺音频时上报其精确引用。"""
        self._export_anchor = QPersistentModelIndex()
        ref = self.audio_ref_at(current)
        if ref is not None:
            self.audio_ref_selected.emit(ref)

    def mousePressEvent(self, event) -> None:
        """Ctrl 点击正文时把前后浏览项交给共享导出选择。"""
        position = event.position().toPoint()
        index = self.indexAt(position)
        previous = QModelIndex(self._export_anchor)
        body_click = (
            event.button() == Qt.MouseButton.LeftButton
            and index.isValid()
            and position.x() > self.audio_control_rect(index).right()
            and not (
                self.source_model.selection_mode
                and audio_check_rect(self.visualRect(index), self.viewport().width()).contains(position)
            )
        )
        ctrl_select = body_click and bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._ctrl_export_click = ctrl_select
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._export_anchor = QPersistentModelIndex(index) if body_click else QPersistentModelIndex()
        if ctrl_select:
            self.export_selection_requested.emit(index, previous)

    def mouseReleaseEvent(self, event) -> None:
        """在播放按钮上发出精确音频引用，其他区域保持默认选择。"""
        if event.button() == Qt.MouseButton.LeftButton and self._ctrl_export_click:
            self._ctrl_export_click = False
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if self.source_model.selection_mode and audio_check_rect(
                self.visualRect(index), self.viewport().width()
            ).contains(event.position().toPoint()):
                self._toggle_export_check(index)
                event.accept()
                return
            ref = self.audio_ref_at(index)
            if ref is not None and self.audio_control_rect(index).contains(event.position().toPoint()):
                self.audio_ref_toggle_requested.emit(ref)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def _toggle_export_check(self, index: QModelIndex) -> None:
        state = index.data(Qt.ItemDataRole.CheckStateRole)
        self.model().setData(
            index,
            Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked,
            Qt.ItemDataRole.CheckStateRole,
        )

    def keyPressEvent(self, event) -> None:
        """选择模式用空格切换导出复选框。"""
        if event.key() == Qt.Key.Key_Space and self.source_model.selection_mode:
            self._toggle_export_check(self.currentIndex())
            event.accept()
            return
        super().keyPressEvent(event)

    def refresh_export_selection(self, *, only_selected: bool = False) -> None:
        """刷新模型筛选与行末选择，保留当前路径索引。"""
        was_filtered = self.filter_model.only_selected
        self.filter_model.only_selected = only_selected
        if was_filtered or only_selected:
            self.filter_model.beginFilterChange()
            self.filter_model.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        self.viewport().update()

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
