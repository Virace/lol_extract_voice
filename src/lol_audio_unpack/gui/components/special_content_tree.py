"""特殊内容目录使用的一层分组轻量树模型与视图。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QAbstractItemModel, QItemSelectionModel, QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QWidget,
)
from qfluentwidgets import CustomStyleSheet, isDarkTheme, setCustomStyleSheet, setStyleSheet
from qfluentwidgets.components.widgets.scroll_bar import SmoothScrollDelegate

from lol_audio_unpack.app.special_content import SPECIAL_CONTENT_GROUPS
from lol_audio_unpack.gui.common.styles import (
    build_fluent_list_shell_theme_pair,
    resolve_fluent_neutral_surface,
)
from lol_audio_unpack.gui.components.overview_entity_list import (
    OVERVIEW_AUDIO_STATUS_ROLE,
    OVERVIEW_MAPPING_STATUS_ROLE,
)
from lol_audio_unpack.gui.components.overview_status_badge import (
    STATUS_BADGE_SIZE,
    measure_status_pill_width,
    paint_status_pill,
)
from lol_audio_unpack.gui.theme import current_accent_preset_id, get_accent_preset

EMPTY_MODEL_INDEX = QModelIndex()
SPECIAL_ROW_ROLE = int(Qt.ItemDataRole.UserRole) + 41
SPECIAL_TARGET_ROLE = int(Qt.ItemDataRole.UserRole) + 42
SPECIAL_GROUP_ROLE = int(Qt.ItemDataRole.UserRole) + 43
SPECIAL_SEARCH_TEXT_ROLE = int(Qt.ItemDataRole.UserRole) + 44
SPECIAL_ITEM_HEIGHT = 40
SPECIAL_GROUP_HEIGHT = 34


@dataclass(slots=True)
class _SpecialGroup:
    """树模型中的一个不可选展示分组。"""

    mode_key: str
    display_name: str
    english_name: str
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _SpecialNode:
    """树模型索引使用的轻量节点引用。"""

    group: _SpecialGroup
    row: dict[str, Any] | None = None


def _build_tree_styles() -> tuple[str, str]:
    """构造特殊内容树在深浅主题下复用的列表壳层样式。"""
    return build_fluent_list_shell_theme_pair(item_min_height=SPECIAL_ITEM_HEIGHT, item_border_radius=8)


def _interaction_colors():
    """返回当前主题的 hover、selection 与 accent 色。"""
    accent = get_accent_preset(current_accent_preset_id()).scale.color(300 if isDarkTheme() else 700)
    return (
        resolve_fluent_neutral_surface("subtle_hover"),
        resolve_fluent_neutral_surface("subtle_selected"),
        accent,
    )


class SpecialContentTreeModel(QAbstractItemModel):
    """以一层 group → item 结构承载结构化特殊内容。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._groups: list[_SpecialGroup] = []
        self._all_groups: list[_SpecialGroup] = []
        self._group_nodes: list[_SpecialNode] = []
        self._item_nodes_by_group_id: dict[int, list[_SpecialNode]] = {}
        self._keyword = ""
        self._interactive = True

    def columnCount(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> int:
        """返回树模型的单列结构。"""
        return 1

    def rowCount(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> int:
        """返回根分组数或指定分组下的项目数。"""
        if not parent.isValid():
            return len(self._groups)
        node = parent.internalPointer()
        return len(node.group.rows) if isinstance(node, _SpecialNode) and node.row is None else 0

    def index(self, row: int, column: int, parent: QModelIndex = EMPTY_MODEL_INDEX) -> QModelIndex:
        """创建对应根分组或子项目的模型索引。"""
        if column != 0 or row < 0:
            return QModelIndex()
        if not parent.isValid():
            if row >= len(self._groups):
                return QModelIndex()
            return self.createIndex(row, column, self._group_nodes[row])
        parent_node = parent.internalPointer()
        if (
            not isinstance(parent_node, _SpecialNode)
            or parent_node.row is not None
            or row >= len(parent_node.group.rows)
        ):
            return QModelIndex()
        item_nodes = self._item_nodes_by_group_id.get(id(parent_node.group), [])
        return self.createIndex(row, column, item_nodes[row])

    def parent(self, index: QModelIndex) -> QModelIndex:
        """返回子项目所属分组；根分组没有父级。"""
        node = index.internalPointer() if index.isValid() else None
        if not isinstance(node, _SpecialNode) or node.row is None:
            return QModelIndex()
        for row, group in enumerate(self._groups):
            if group is node.group:
                return self.createIndex(row, 0, self._group_nodes[row])
        return QModelIndex()

    def data(  # noqa: PLR0911
        self,
        index: QModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        """按角色返回分组或特殊内容项目的展示数据。"""
        if not index.isValid():
            return None
        node = index.internalPointer()
        if not isinstance(node, _SpecialNode):
            return None
        if node.row is None:
            if role == Qt.ItemDataRole.DisplayRole:
                return f"{node.group.display_name} ({len(node.group.rows)})"
            if role == Qt.ItemDataRole.ToolTipRole:
                return f"{node.group.display_name} / {node.group.english_name}"
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return f"{node.group.display_name}，{len(node.group.rows)} 项"
            if role == Qt.ItemDataRole.AccessibleDescriptionRole:
                return f"可展开或折叠的特殊内容分组，包含 {len(node.group.rows)} 项。"
            if role == Qt.ItemDataRole.SizeHintRole:
                return QSize(0, SPECIAL_GROUP_HEIGHT)
            if role == SPECIAL_GROUP_ROLE:
                return True
            return None

        row = node.row
        if role == Qt.ItemDataRole.DisplayRole:
            return str(row.get("name", ""))
        if role in (Qt.ItemDataRole.UserRole, SPECIAL_ROW_ROLE):
            return dict(row)
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(row.get("tooltip", ""))
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(0, SPECIAL_ITEM_HEIGHT)
        if role == SPECIAL_TARGET_ROLE:
            return str(row.get("key", ""))
        if role == SPECIAL_SEARCH_TEXT_ROLE:
            return str(row.get("search_text", ""))
        if role == OVERVIEW_AUDIO_STATUS_ROLE:
            return str(row.get("audio", "未准备"))
        if role == OVERVIEW_MAPPING_STATUS_ROLE:
            return str(row.get("mapping", "未准备"))
        if role == SPECIAL_GROUP_ROLE:
            return False
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """限制分组不可选，并在 remote 时禁用特殊项目选择。"""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        node = index.internalPointer()
        if not isinstance(node, _SpecialNode):
            return Qt.ItemFlag.NoItemFlags
        if node.row is None:
            return Qt.ItemFlag.ItemIsEnabled
        if not self._interactive or not bool(node.row.get("selectable", True)):
            return Qt.ItemFlag.ItemIsEnabled
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        """替换特殊内容行，并按固定分组顺序重建一层分组。"""
        groups = self._build_groups(rows)
        self.beginResetModel()
        self._all_groups = groups
        self._groups = self._filter_groups(groups, self._keyword)
        self._rebuild_nodes()
        self.endResetModel()

    def set_keyword(self, keyword: str) -> None:
        """更新特殊目录搜索结果。"""
        normalized = keyword.casefold().strip()
        if normalized == self._keyword:
            return
        self._keyword = normalized
        self.beginResetModel()
        self._groups = self._filter_groups(self._all_groups, normalized)
        self._rebuild_nodes()
        self.endResetModel()

    def set_interactive(self, interactive: bool) -> None:
        """切换子项目是否允许被选择。"""
        if self._interactive == interactive:
            return
        self._interactive = interactive
        self.beginResetModel()
        self.endResetModel()

    def item_count(self) -> int:
        """返回当前搜索结果中的子项目数量。"""
        return sum(len(group.rows) for group in self._groups)

    def all_target_keys(self) -> set[str]:
        """返回未受当前搜索条件影响的完整 stable special key 集合。"""
        return {str(row.get("key", "")) for group in self._all_groups for row in group.rows if str(row.get("key", ""))}

    def _build_groups(self, rows: list[dict[str, Any]]) -> list[_SpecialGroup]:
        """按固定分组顺序组织给定原始行。"""
        rows_by_mode: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            rows_by_mode.setdefault(str(row.get("mode_key", "")), []).append(dict(row))
        return [
            _SpecialGroup(
                mode_key=profile.mode_key,
                display_name=profile.display_name,
                english_name=profile.english_name,
                rows=sorted(
                    rows_by_mode.get(profile.mode_key, []), key=lambda item: str(item.get("name", "")).casefold()
                ),
            )
            for profile in SPECIAL_CONTENT_GROUPS
            if rows_by_mode.get(profile.mode_key)
        ]

    @staticmethod
    def _filter_groups(groups: list[_SpecialGroup], keyword: str) -> list[_SpecialGroup]:
        """按分组中英文或项目预构建搜索字段筛选树数据。"""
        if not keyword:
            return groups
        result: list[_SpecialGroup] = []
        for group in groups:
            group_search = f"{group.display_name} {group.english_name}".casefold()
            rows = (
                group.rows
                if keyword in group_search
                else [row for row in group.rows if keyword in str(row.get("search_text", "")).casefold()]
            )
            if rows:
                result.append(
                    _SpecialGroup(
                        mode_key=group.mode_key,
                        display_name=group.display_name,
                        english_name=group.english_name,
                        rows=rows,
                    )
                )
        return result

    def _rebuild_nodes(self) -> None:
        """缓存 QModelIndex 使用的节点，避免 Qt 持有短生命周期 Python 指针。"""
        self._group_nodes = [_SpecialNode(group) for group in self._groups]
        self._item_nodes_by_group_id = {
            id(group): [_SpecialNode(group, row) for row in group.rows] for group in self._groups
        }


class SpecialContentItemDelegate(QStyledItemDelegate):
    """绘制一层分组标题和带 A/M 状态的特殊内容子项目。"""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """返回分组与子项目各自的稳定行高。"""
        height = SPECIAL_GROUP_HEIGHT if bool(index.data(SPECIAL_GROUP_ROLE)) else SPECIAL_ITEM_HEIGHT
        return QSize(0, height)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """直接绘制文字与状态胶囊，避免逐行创建 QWidget。"""
        painter.save()
        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.text = ""
        style = style_option.widget.style() if style_option.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, style_option, painter, style_option.widget)

        is_group = bool(index.data(SPECIAL_GROUP_ROLE))
        metrics = QFontMetrics(style_option.font)
        content = option.rect.adjusted(8, 2, -10, -2)
        if is_group:
            group_font = style_option.font
            group_font.setBold(True)
            painter.setFont(group_font)
            painter.setPen(style_option.palette.color(QPalette.ColorRole.Text))
            painter.drawText(
                content, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(index.data() or "")
            )
            painter.restore()
            return

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        interaction = option.rect.adjusted(4, 2, -4, -2)
        if is_selected or is_hovered:
            hover, selection, accent = _interaction_colors()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(selection if is_selected else hover)
            painter.drawRoundedRect(interaction, 4, 4)
            if is_selected:
                painter.setBrush(accent)
                painter.drawRoundedRect(
                    QRect(interaction.left(), interaction.top() + 6, 3, interaction.height() - 12), 1, 1
                )

        badges = (
            ("A", str(index.data(OVERVIEW_AUDIO_STATUS_ROLE) or "未准备")),
            ("M", str(index.data(OVERVIEW_MAPPING_STATUS_ROLE) or "未准备")),
        )
        badge_width = measure_status_pill_width(tuple(label for label, _status in badges), metrics)
        title_rect = QRect(
            content.left() + 10, content.top(), max(0, content.width() - badge_width - 18), content.height()
        )
        painter.setPen(style_option.palette.color(QPalette.ColorRole.Text))
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            metrics.elidedText(str(index.data() or ""), Qt.TextElideMode.ElideRight, title_rect.width()),
        )
        badge_rect = QRect(
            interaction.right() - badge_width - 8,
            interaction.center().y() - STATUS_BADGE_SIZE // 2,
            badge_width,
            STATUS_BADGE_SIZE,
        )
        paint_status_pill(painter, badge_rect, badges, palette=style_option.palette)
        painter.restore()


class SpecialContentTreeView(QTreeView):
    """封装特殊内容树的选择、搜索与展开状态恢复。"""

    _default_expanded_modes = {"doom_bots", "swarm"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setUniformRowHeights(False)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setIndentation(18)
        self.verticalScrollBar().setSingleStep(18)
        self.setItemDelegate(SpecialContentItemDelegate(self))
        self.setAccessibleName("特殊内容目录")
        self._expanded_modes = set(self._default_expanded_modes)
        self._search_restore_expanded_modes: set[str] | None = None
        self._search_active = False
        self._interactive = True
        self.scrollDelegate = SmoothScrollDelegate(self, True)

        light_qss, dark_qss = _build_tree_styles()
        setCustomStyleSheet(self, light_qss, dark_qss)
        setStyleSheet(self, CustomStyleSheet(self))

        self._source_model = SpecialContentTreeModel(self)
        self.setModel(self._source_model)

    def source_model(self) -> SpecialContentTreeModel:
        """返回内部特殊内容树模型。"""
        return self._source_model

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        """整体替换目录数据，并恢复当前会话的分组展开状态。"""
        if not rows:
            self._source_model.set_rows([])
            self._expanded_modes = set(self._default_expanded_modes)
            self._search_restore_expanded_modes = None
            return
        if self._source_model.all_target_keys() and not self._search_active:
            self._expanded_modes = self.expanded_mode_keys()
        self._source_model.set_rows(rows)
        if self._search_active:
            self.expandAll()
        else:
            self._apply_expanded_modes(self._expanded_modes)

    def set_keyword(self, keyword: str) -> None:
        """应用搜索；搜索期间临时展开命中分组，清空后恢复。"""
        is_active = bool(keyword.strip())
        if is_active and not self._search_active:
            self._search_restore_expanded_modes = self.expanded_mode_keys()
        self._source_model.set_keyword(keyword)
        self._search_active = is_active
        if is_active:
            self.expandAll()
            return
        if self._search_restore_expanded_modes is not None:
            self._expanded_modes = self._search_restore_expanded_modes
            self._search_restore_expanded_modes = None
        self._apply_expanded_modes(self._expanded_modes)

    def set_interaction_enabled(self, enabled: bool) -> None:
        """切换特殊项目是否允许选择与发送。"""
        expanded_modes = self.expanded_mode_keys()
        self._interactive = enabled
        self._source_model.set_interactive(enabled)
        if not enabled and self.selectionModel() is not None:
            self.selectionModel().clearSelection()
        self.setToolTip("特殊内容仅支持本地客户端资源。" if not enabled else "")
        if self._search_active:
            self.expandAll()
        else:
            self._apply_expanded_modes(expanded_modes)

    def entity_ids(self) -> set[str]:
        """返回未受当前搜索条件影响的完整 stable special key。"""
        return self._source_model.all_target_keys()

    def visible_row_count(self) -> int:
        """返回当前搜索结果中的子项目数。"""
        return self._source_model.item_count()

    def find_index_by_entity_id(self, target: str | None) -> QModelIndex:
        """按 stable key 查找当前可见 special 项。"""
        if not target:
            return QModelIndex()
        for group_row in range(self.model().rowCount()):
            for index in self._iter_group_items(group_row):
                if str(index.data(SPECIAL_TARGET_ROLE) or "") == str(target):
                    return index
        return QModelIndex()

    def restore_state(self, selected_ids: set[str], current_entity_id: str | None) -> None:
        """恢复多选、当前项与滚动位置。"""
        selection_model = self.selectionModel()
        if selection_model is None:
            return
        selection_model.clearSelection()
        for target in selected_ids:
            index = self.find_index_by_entity_id(target)
            if index.isValid() and self._interactive:
                selection_model.select(
                    index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
                )
        current_index = self.find_index_by_entity_id(current_entity_id)
        if current_index.isValid():
            selection_model.setCurrentIndex(current_index, QItemSelectionModel.SelectionFlag.Current)
            self.scrollTo(current_index, QTreeView.ScrollHint.EnsureVisible)
        else:
            selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
            self.setCurrentIndex(QModelIndex())

    def selected_entity_ids(self) -> set[str]:
        """返回当前选中的 stable special key 集合。"""
        selection_model = self.selectionModel()
        if selection_model is None:
            return set()
        return {
            str(index.data(SPECIAL_TARGET_ROLE))
            for index in selection_model.selectedRows()
            if str(index.data(SPECIAL_TARGET_ROLE) or "")
        }

    def expanded_mode_keys(self) -> set[str]:
        """返回当前展开的一层分组 key。"""
        keys: set[str] = set()
        for row in range(self.model().rowCount()):
            index = self.model().index(row, 0)
            node = index.internalPointer() if index.isValid() else None
            if isinstance(node, _SpecialNode) and self.isExpanded(index):
                keys.add(node.group.mode_key)
        return keys

    def refresh_theme(self) -> None:
        """主题切换后重绘树项目。"""
        self.viewport().update()

    def _iter_group_items(self, group_row: int):
        """遍历指定根分组下当前可见的子项目索引。"""
        group_index = self.model().index(group_row, 0)
        for child_row in range(self.model().rowCount(group_index)):
            yield self.model().index(child_row, 0, group_index)

    def _apply_expanded_modes(self, expanded_modes: set[str]) -> None:
        """根据保存的 mode key 恢复一层分组的展开状态。"""
        for row in range(self.model().rowCount()):
            index = self.model().index(row, 0)
            node = index.internalPointer() if index.isValid() else None
            if isinstance(node, _SpecialNode):
                self.setExpanded(index, node.group.mode_key in expanded_modes)


__all__ = [
    "SPECIAL_GROUP_ROLE",
    "SPECIAL_ROW_ROLE",
    "SPECIAL_TARGET_ROLE",
    "SpecialContentItemDelegate",
    "SpecialContentTreeModel",
    "SpecialContentTreeView",
]
