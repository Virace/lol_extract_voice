"""实体总览左侧列表组件。"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractListModel, QItemSelectionModel, QModelIndex, QRect, QSize, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)
from qfluentwidgets import CustomStyleSheet, setCustomStyleSheet, setStyleSheet, themeColor
from qfluentwidgets.components.widgets.scroll_bar import SmoothScrollDelegate

from lol_audio_unpack.gui.common.styles import (
    build_fluent_list_shell_theme_pair,
    resolve_fluent_neutral_surface,
)
from lol_audio_unpack.gui.components.overview_status_badge import STATUS_BADGE_SIZE, paint_status_badge

EMPTY_MODEL_INDEX = QModelIndex()
OVERVIEW_ITEM_HEIGHT = 40
OVERVIEW_INTERACTION_RADIUS = 4
OVERVIEW_INTERACTION_HORIZONTAL_MARGIN = 4
OVERVIEW_INTERACTION_VERTICAL_MARGIN = 2
OVERVIEW_SELECTION_ACCENT_WIDTH = 3
OVERVIEW_SELECTION_ACCENT_TOP_MARGIN = 7
OVERVIEW_SELECTION_ACCENT_BOTTOM_MARGIN = 6
OVERVIEW_TEXT_LEFT_PADDING = 18
OVERVIEW_TEXT_RIGHT_PADDING = 12
OVERVIEW_ROW_ROLE = int(Qt.ItemDataRole.UserRole) + 11
OVERVIEW_ENTITY_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 12
OVERVIEW_ALIAS_ROLE = int(Qt.ItemDataRole.UserRole) + 13
OVERVIEW_AUDIO_STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 14
OVERVIEW_MAPPING_STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 15
OVERVIEW_TOOLTIP_ROLE = int(Qt.ItemDataRole.UserRole) + 16
OVERVIEW_SEARCH_TEXT_ROLE = int(Qt.ItemDataRole.UserRole) + 17


def should_display_overview_row(row: dict[str, Any]) -> bool:
    """判断该实体是否应显示在总览页中。

    Args:
        row: 实体数据行。

    Returns:
        只要存在基础 ID，即认为该行可用于总览展示。
    """
    return bool(str(row.get("id", "")).strip())


def build_overview_item_text(row: dict[str, Any]) -> str:
    """构造实体列表条目的主标题文本。

    Args:
        row: 实体列表行数据。

    Returns:
        当前实体的展示名称。
    """
    return str(row.get("name", "") or "")


def _build_overview_item_tooltip(row: dict[str, Any]) -> str:
    """构造总览页条目的提示信息。

    Args:
        row: 实体列表行数据。

    Returns:
        多行 tooltip 文本。
    """
    entity_id = str(row.get("id", "")).strip()
    alias = str(row.get("alias", "")).strip() or "无 alias"
    mapping_path = str(row.get("mapping_file", "") or "当前还没有 mapping 文件")
    audio_status = str(row.get("audio", "未存在"))
    mapping_status = str(row.get("mapping", "未存在"))
    return (
        f"ID: {entity_id}\n"
        f"Alias: {alias}\n"
        f"音频: {audio_status}\n"
        f"映射: {mapping_status}\n"
        f"文件: {mapping_path}"
    )


def _build_overview_list_styles() -> tuple[str, str]:
    """构造实体列表在亮暗主题下的统一样式。"""
    return build_fluent_list_shell_theme_pair(
        item_min_height=40,
        item_border_radius=8,
    )


def _build_overview_idle_background() -> QColor:
    """构造总览列表非选中斑马行的中性底色。"""
    return resolve_fluent_neutral_surface("subtle_idle")


def _build_overview_interaction_colors() -> tuple[QColor, QColor, QColor]:
    """构造总览列表 hover/selected 的中性底色与主题 accent。"""
    return (
        resolve_fluent_neutral_surface("subtle_hover"),
        resolve_fluent_neutral_surface("subtle_selected"),
        QColor(themeColor()),
    )


class OverviewEntityListModel(QAbstractListModel):
    """承载实体总览左侧列表数据的轻量模型。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def rowCount(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> int:
        """返回当前列表可展示的实体数量。"""
        if parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        """按角色返回当前实体行数据。"""
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None

        row = self._rows[index.row()]
        value: Any = None
        if role == Qt.ItemDataRole.DisplayRole:
            value = build_overview_item_text(row)
        elif role in (Qt.ItemDataRole.ToolTipRole, OVERVIEW_TOOLTIP_ROLE):
            value = _build_overview_item_tooltip(row)
        elif role == Qt.ItemDataRole.SizeHintRole:
            value = QSize(0, OVERVIEW_ITEM_HEIGHT)
        elif role in (Qt.ItemDataRole.UserRole, OVERVIEW_ROW_ROLE):
            value = dict(row)
        elif role == OVERVIEW_ENTITY_ID_ROLE:
            value = str(row.get("id", "")).strip()
        elif role == OVERVIEW_ALIAS_ROLE:
            value = str(row.get("alias", "")).strip()
        elif role == OVERVIEW_AUDIO_STATUS_ROLE:
            value = str(row.get("audio", "未存在"))
        elif role == OVERVIEW_MAPPING_STATUS_ROLE:
            value = str(row.get("mapping", "未存在"))
        elif role == OVERVIEW_SEARCH_TEXT_ROLE:
            value = " ".join(
                (
                    str(row.get("id", "")),
                    str(row.get("name", "")),
                    str(row.get("alias", "")),
                )
            ).lower()
        return value

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        """整体替换当前实体行数据。

        Args:
            rows: 原始实体行列表。
        """
        filtered_rows = [dict(row) for row in rows if should_display_overview_row(row)]
        self.beginResetModel()
        self._rows = filtered_rows
        self.endResetModel()

    def entity_ids(self) -> set[str]:
        """返回当前 source model 中存在的实体 ID 集合。"""
        return {str(row.get("id", "")).strip() for row in self._rows if str(row.get("id", "")).strip()}


class OverviewEntityFilterModel(QSortFilterProxyModel):
    """按搜索关键字过滤实体列表的代理模型。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._keyword = ""
        self.setDynamicSortFilter(True)

    def set_keyword(self, keyword: str) -> None:
        """更新当前过滤关键字。

        Args:
            keyword: 搜索关键字。
        """
        normalized = keyword.lower().strip()
        if normalized == self._keyword:
            return
        self._keyword = normalized
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """判断 source model 中的某一行是否应保留在当前结果里。"""
        if not self._keyword:
            return True

        model = self.sourceModel()
        if model is None:
            return False

        index = model.index(source_row, 0, source_parent)
        haystack = str(model.data(index, OVERVIEW_SEARCH_TEXT_ROLE) or "")
        return self._keyword in haystack


class OverviewEntityItemDelegate(QStyledItemDelegate):
    """直接绘制实体条目，避免为每一行创建独立 QWidget。"""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """返回稳定的总览行高。"""
        return QSize(0, OVERVIEW_ITEM_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """绘制实体标题与两枚状态徽章。"""
        painter.save()

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.text = ""
        style_option.features &= ~QStyleOptionViewItem.ViewItemFeature.Alternate
        if is_selected or is_hovered:
            style_option.state &= ~QStyle.StateFlag.State_Selected
            style_option.state &= ~QStyle.StateFlag.State_MouseOver
        style = style_option.widget.style() if style_option.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, style_option, painter, style_option.widget)

        interaction_rect = option.rect.adjusted(
            OVERVIEW_INTERACTION_HORIZONTAL_MARGIN,
            OVERVIEW_INTERACTION_VERTICAL_MARGIN,
            -OVERVIEW_INTERACTION_HORIZONTAL_MARGIN,
            -OVERVIEW_INTERACTION_VERTICAL_MARGIN,
        )
        content_rect = QRect(
            interaction_rect.left() + OVERVIEW_TEXT_LEFT_PADDING,
            interaction_rect.top(),
            max(0, interaction_rect.width() - OVERVIEW_TEXT_LEFT_PADDING - OVERVIEW_TEXT_RIGHT_PADDING),
            interaction_rect.height(),
        )
        if is_selected:
            hover_background, selection_background, selection_accent = _build_overview_interaction_colors()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(selection_background)
            painter.drawRoundedRect(interaction_rect, OVERVIEW_INTERACTION_RADIUS, OVERVIEW_INTERACTION_RADIUS)
            accent_rect = QRect(
                interaction_rect.left(),
                interaction_rect.top() + OVERVIEW_SELECTION_ACCENT_TOP_MARGIN,
                OVERVIEW_SELECTION_ACCENT_WIDTH,
                max(
                    0,
                    interaction_rect.height()
                    - OVERVIEW_SELECTION_ACCENT_TOP_MARGIN
                    - OVERVIEW_SELECTION_ACCENT_BOTTOM_MARGIN,
                ),
            )
            painter.setBrush(selection_accent)
            painter.drawRoundedRect(
                accent_rect,
                OVERVIEW_SELECTION_ACCENT_WIDTH / 2,
                OVERVIEW_SELECTION_ACCENT_WIDTH / 2,
            )
        elif is_hovered:
            hover_background, _selection_background, _selection_accent = _build_overview_interaction_colors()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hover_background)
            painter.drawRoundedRect(interaction_rect, OVERVIEW_INTERACTION_RADIUS, OVERVIEW_INTERACTION_RADIUS)
        elif index.row() % 2 == 1:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_build_overview_idle_background())
            painter.drawRoundedRect(interaction_rect, OVERVIEW_INTERACTION_RADIUS, OVERVIEW_INTERACTION_RADIUS)

        badge_spacing = 8
        badge_width = STATUS_BADGE_SIZE
        badge_count = 2
        badges_total_width = badge_count * badge_width + (badge_count - 1) * badge_spacing
        title_rect = QRect(
            content_rect.left(),
            content_rect.top(),
            max(
                0,
                content_rect.right() - badges_total_width - badge_spacing - content_rect.left(),
            ),
            content_rect.height(),
        )

        display_text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        metrics = QFontMetrics(style_option.font)
        elided_text = metrics.elidedText(display_text, Qt.TextElideMode.ElideRight, title_rect.width())
        painter.setPen(style_option.palette.color(QPalette.ColorRole.Text))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_text)

        badge_top = interaction_rect.center().y() - STATUS_BADGE_SIZE // 2
        badge_left = interaction_rect.right() - badges_total_width - OVERVIEW_TEXT_RIGHT_PADDING + 1
        badges = (
            ("A", str(index.data(OVERVIEW_AUDIO_STATUS_ROLE) or "未存在")),
            ("M", str(index.data(OVERVIEW_MAPPING_STATUS_ROLE) or "未存在")),
        )
        for badge_label, badge_status in badges:
            badge_rect = QRect(badge_left, badge_top, STATUS_BADGE_SIZE, STATUS_BADGE_SIZE)
            paint_status_badge(
                painter,
                badge_rect,
                badge_label,
                badge_status,
                palette=style_option.palette,
            )
            badge_left += badge_width + badge_spacing

        painter.restore()


class OverviewEntityListView(QListView):
    """封装实体总览左侧列表的模型、代理与主题接线。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(18)
        self.setSpacing(2)
        self.setItemDelegate(OverviewEntityItemDelegate(self))
        self.scrollDelegate = SmoothScrollDelegate(self, True)

        light_qss, dark_qss = _build_overview_list_styles()
        setCustomStyleSheet(self, light_qss, dark_qss)
        setStyleSheet(self, CustomStyleSheet(self))

        self._source_model = OverviewEntityListModel(self)
        self._proxy_model = OverviewEntityFilterModel(self)
        self._proxy_model.setSourceModel(self._source_model)
        self.setModel(self._proxy_model)

    def source_model(self) -> OverviewEntityListModel:
        """返回内部 source model。"""
        return self._source_model

    def proxy_model(self) -> OverviewEntityFilterModel:
        """返回内部 proxy model。"""
        return self._proxy_model

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        """整体替换当前列表数据。

        Args:
            rows: 原始实体行列表。
        """
        self._source_model.set_rows(rows)

    def entity_ids(self) -> set[str]:
        """返回当前 source model 中的实体 ID 集合。"""
        return self._source_model.entity_ids()

    def set_keyword(self, keyword: str) -> None:
        """更新当前关键字过滤。"""
        self._proxy_model.set_keyword(keyword)

    def visible_row_count(self) -> int:
        """返回当前代理模型中可见的行数。"""
        return self._proxy_model.rowCount()

    def iter_visible_rows(self) -> list[dict[str, Any]]:
        """返回当前过滤条件下仍可见的实体行。"""
        rows: list[dict[str, Any]] = []
        for row_index in range(self._proxy_model.rowCount()):
            index = self._proxy_model.index(row_index, 0)
            row = index.data(OVERVIEW_ROW_ROLE)
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def find_index_by_entity_id(self, entity_id: str | None) -> QModelIndex:
        """在代理模型里按实体 ID 查找对应索引。"""
        if not entity_id:
            return QModelIndex()

        for row_index in range(self._proxy_model.rowCount()):
            index = self._proxy_model.index(row_index, 0)
            if str(index.data(OVERVIEW_ENTITY_ID_ROLE) or "") == str(entity_id):
                return index
        return QModelIndex()

    def restore_state(self, selected_ids: set[str], current_entity_id: str | None) -> None:
        """将页面层维护的选择和当前项同步回代理视图。

        Args:
            selected_ids: 当前应恢复的实体 ID 集合。
            current_entity_id: 当前预览实体 ID。
        """
        selection_model = self.selectionModel()
        if selection_model is None:
            return

        selection_model.clearSelection()
        for entity_id in selected_ids:
            index = self.find_index_by_entity_id(entity_id)
            if index.isValid():
                selection_model.select(
                    index,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

        current_index = self.find_index_by_entity_id(current_entity_id)
        if current_index.isValid():
            selection_model.setCurrentIndex(
                current_index,
                QItemSelectionModel.SelectionFlag.Current,
            )
            self.scrollTo(current_index, QListView.ScrollHint.EnsureVisible)
        else:
            selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
            self.setCurrentIndex(QModelIndex())

    def selected_entity_ids(self) -> set[str]:
        """返回当前选择模型中的实体 ID 集合。"""
        selection_model = self.selectionModel()
        if selection_model is None:
            return set()
        return {
            str(index.data(OVERVIEW_ENTITY_ID_ROLE))
            for index in selection_model.selectedRows()
            if str(index.data(OVERVIEW_ENTITY_ID_ROLE) or "")
        }

    def refresh_theme(self) -> None:
        """在主题切换后刷新当前视口绘制。"""
        self.viewport().update()


__all__ = [
    "OVERVIEW_AUDIO_STATUS_ROLE",
    "OVERVIEW_ENTITY_ID_ROLE",
    "OVERVIEW_INTERACTION_RADIUS",
    "OVERVIEW_MAPPING_STATUS_ROLE",
    "OVERVIEW_ROW_ROLE",
    "OVERVIEW_SELECTION_ACCENT_BOTTOM_MARGIN",
    "OVERVIEW_SELECTION_ACCENT_TOP_MARGIN",
    "OVERVIEW_SELECTION_ACCENT_WIDTH",
    "OVERVIEW_TEXT_LEFT_PADDING",
    "OVERVIEW_TEXT_RIGHT_PADDING",
    "OverviewEntityFilterModel",
    "OverviewEntityItemDelegate",
    "OverviewEntityListModel",
    "OverviewEntityListView",
    "_build_overview_interaction_colors",
    "_build_overview_list_styles",
    "build_overview_item_text",
    "should_display_overview_row",
]
