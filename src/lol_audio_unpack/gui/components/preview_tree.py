"""基础试听树组件。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QTreeView
from qfluentwidgets import (
    CustomStyleSheet,
    setCustomStyleSheet,
    setStyleSheet,
    themeColor,
)

from lol_audio_unpack.gui.common.styles import (
    build_fluent_tree_shell_theme_pair,
    resolve_fluent_neutral_surface,
    resolve_fluent_text_primary_color,
)

NODE_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
AUDIO_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 2
AUDIO_AVAILABLE_ROLE = int(Qt.ItemDataRole.UserRole) + 3
NODE_PAYLOAD_ROLE = int(Qt.ItemDataRole.UserRole) + 4
NODE_LOADED_ROLE = int(Qt.ItemDataRole.UserRole) + 5
EMPTY_MODEL_INDEX = QModelIndex()
PREVIEW_TREE_ITEM_MIN_HEIGHT = 20
PREVIEW_TREE_ROW_HORIZONTAL_MARGIN = 10
PREVIEW_TREE_BRANCH_SLOT_WIDTH = 28
PREVIEW_TREE_BRANCH_ICON_SIZE = 12
PREVIEW_TREE_BRANCH_ICON_STROKE_WIDTH = 2
PREVIEW_TREE_TEXT_GAP = 4
PREVIEW_TREE_SELECTED_BAR_WIDTH = 3
PREVIEW_TREE_SELECTED_BAR_MARGIN = 0
PREVIEW_TREE_INDENTATION = 10


def _build_preview_tree_branch_styles() -> str:
    """构造 branch 区域样式。"""
    return """
    QTreeView::branch,
    QTreeView::branch:hover,
    QTreeView::branch:selected,
    QTreeView::branch:selected:hover,
    QTreeView::branch:has-siblings:!adjoins-item,
    QTreeView::branch:has-siblings:!adjoins-item:hover,
    QTreeView::branch:has-siblings:!adjoins-item:selected,
    QTreeView::branch:has-siblings:!adjoins-item:selected:hover,
    QTreeView::branch:adjoins-item,
    QTreeView::branch:adjoins-item:hover,
    QTreeView::branch:adjoins-item:selected,
    QTreeView::branch:adjoins-item:selected:hover,
    QTreeView::branch:has-siblings:adjoins-item,
    QTreeView::branch:!has-children:!has-siblings:adjoins-item,
    QTreeView::branch:closed:has-children:has-siblings,
    QTreeView::branch:closed:has-children:!has-siblings,
    QTreeView::branch:open:has-children:has-siblings,
    QTreeView::branch:open:has-children:!has-siblings {{
        background: transparent;
        border: none;
        margin: 0;
        padding: 0;
    }}
    """


def _build_preview_tree_styles() -> tuple[str, str]:
    """构造试听树的亮暗主题样式。"""
    branch_qss = _build_preview_tree_branch_styles()
    item_rules = """
        padding: 4px 8px 4px 0;
        margin: 2px 0;
        padding-left: 0;
    """
    return build_fluent_tree_shell_theme_pair(
        light_background="transparent",
        dark_background="transparent",
        is_border_visible=True,
        border_radius="10px",
        padding="8px 6px",
        item_min_height=PREVIEW_TREE_ITEM_MIN_HEIGHT,
        item_border_radius=0,
        extra_item_rules=item_rules,
        extra_rules=branch_qss,
    )


def inject_preview_tree_style(tree_view: QTreeView) -> None:
    """为当前试听树注入局部 QSS。

    默认使用接近 Fluent 的自定义亮暗主题，并在其基础上提高树节点行高。
    若后续需要为试听树补充更多局部样式，继续只在这个函数内部追加，
    并仍然只挂载到当前 ``PreviewTreeView`` 实例。

    Args:
        tree_view: 当前要挂载局部样式的试听树实例。
    """
    light_qss, dark_qss = _build_preview_tree_styles()
    setCustomStyleSheet(tree_view, light_qss, dark_qss)
    setStyleSheet(tree_view, CustomStyleSheet(tree_view))


@dataclass(frozen=True, slots=True)
class TreeStats:
    """树形预览摘要统计。"""

    skin_count: int = 0
    audio_type_count: int = 0
    event_count: int = 0
    audio_id_count: int = 0
    available_audio_id_count: int = 0


@dataclass(slots=True)
class _PreviewTreeNode:
    """树形预览中的轻量节点。"""

    label: str
    kind: str
    payload: Any
    parent: _PreviewTreeNode | None = None
    audio_id: str | None = None
    is_available: bool = False
    children: list[_PreviewTreeNode] | None = None
    children_loaded: bool = False

    def row_in_parent(self) -> int:
        """返回当前节点在父节点中的行号。"""
        if self.parent is None or not self.parent.children:
            return 0
        return self.parent.children.index(self)


def extract_tree_groups(mapping_data: dict[str, Any] | None) -> dict[str, Any]:
    """从英雄或地图 mapping 中提取统一的首层分组。

    Args:
        mapping_data: 当前实体的原始 mapping 数据。

    Returns:
        根分组字典；若数据缺失则返回空字典。
    """
    if not isinstance(mapping_data, dict):
        return {}

    for key in ("skins", "map"):
        payload = mapping_data.get(key)
        if key in mapping_data and isinstance(payload, dict):
            return payload
    return {}


def collect_tree_stats(
    mapping_data: dict[str, Any] | None,
    available_audio_ids: set[str],
) -> TreeStats:
    """统计完整预览树中的层级与可用音频 ID 数量。

    Args:
        mapping_data: 当前实体的原始 mapping 数据。
        available_audio_ids: 当前实体本地已存在的 wem ID 集合。

    Returns:
        用于右侧摘要卡的统计数据。
    """
    groups = extract_tree_groups(mapping_data)
    if not isinstance(groups, dict):
        return TreeStats()

    group_count = 0
    audio_type_count = 0
    event_count = 0
    audio_id_count = 0
    available_audio_id_count = 0

    for group_payload in groups.values():
        if not isinstance(group_payload, dict):
            continue

        group_count += 1
        events_payload = group_payload.get("events", {})
        if not isinstance(events_payload, dict):
            continue

        for event_group in events_payload.values():
            if not isinstance(event_group, dict):
                continue

            audio_type_count += 1
            for audio_ids in event_group.values():
                if not isinstance(audio_ids, list | tuple):
                    continue

                event_count += 1
                for audio_id in audio_ids:
                    audio_id_text = str(audio_id).strip()
                    if not audio_id_text:
                        continue

                    audio_id_count += 1
                    if audio_id_text in available_audio_ids:
                        available_audio_id_count += 1

    return TreeStats(
        skin_count=group_count,
        audio_type_count=audio_type_count,
        event_count=event_count,
        audio_id_count=audio_id_count,
        available_audio_id_count=available_audio_id_count,
    )


def build_tree_summary_text(stats: TreeStats) -> str:
    """构造预览树顶部摘要文案。

    Args:
        stats: 当前预览树的统计结果。

    Returns:
        供总览页摘要卡直接展示的文本。
    """
    return (
        f"分组 {stats.skin_count} · 类型 {stats.audio_type_count} · "
        f"事件 {stats.event_count} · ID {stats.audio_id_count} · 可试听 {stats.available_audio_id_count}"
    )


class PreviewTreeModel(QAbstractItemModel):
    """基础试听树数据模型。"""

    def __init__(self, parent=None) -> None:
        """初始化树模型。

        Args:
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._available_audio_ids: set[str] = set()
        self._root_nodes: list[_PreviewTreeNode] = []

    def clear_preview(self) -> None:
        """清空当前预览树内容。"""
        self.beginResetModel()
        self._available_audio_ids = set()
        self._root_nodes = []
        self.endResetModel()

    def set_preview_data(
        self,
        mapping_data: dict[str, Any] | None,
        available_audio_ids: set[str],
    ) -> None:
        """替换当前预览树数据。

        Args:
            mapping_data: 当前实体的原始 mapping 数据。
            available_audio_ids: 当前实体本地已存在的 wem ID 集合。
        """
        groups = extract_tree_groups(mapping_data)
        root_nodes: list[_PreviewTreeNode] = []

        for group_id, group_payload in groups.items():
            if not isinstance(group_payload, dict):
                continue
            root_nodes.append(
                _PreviewTreeNode(
                    label=str(group_id),
                    kind="group",
                    payload=group_payload.get("events", {}),
                )
            )

        self.beginResetModel()
        self._available_audio_ids = {str(audio_id) for audio_id in available_audio_ids}
        self._root_nodes = root_nodes
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> int:
        """返回指定父节点下的子节点数量。

        Args:
            parent: 父节点索引。

        Returns:
            当前父节点下已加载的子节点数量。
        """
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            return len(self._root_nodes)

        node = self._node_from_index(parent)
        if node is None or not node.children_loaded or node.children is None:
            return 0
        return len(node.children)

    def columnCount(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> int:
        """返回模型列数。

        Args:
            parent: 父节点索引。

        Returns:
            固定为单列。
        """
        return 1

    def index(
        self,
        row: int,
        column: int,
        parent: QModelIndex = EMPTY_MODEL_INDEX,
    ) -> QModelIndex:
        """根据父节点和行号创建子节点索引。

        Args:
            row: 目标行号。
            column: 目标列号。
            parent: 父节点索引。

        Returns:
            对应的模型索引；若越界则返回空索引。
        """
        if column != 0 or row < 0:
            return QModelIndex()

        children = self._root_nodes if not parent.isValid() else self._children_for_parent(parent)
        if children is None or row >= len(children):
            return QModelIndex()

        return self.createIndex(row, column, children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:
        """返回当前索引的父节点索引。

        Args:
            index: 当前节点索引。

        Returns:
            父节点索引；若当前为根节点则返回空索引。
        """
        if not index.isValid():
            return QModelIndex()

        node = self._node_from_index(index)
        if node is None or node.parent is None:
            return QModelIndex()

        parent_node = node.parent
        if parent_node.parent is None:
            row = self._root_nodes.index(parent_node)
        else:
            row = parent_node.row_in_parent()
        return self.createIndex(row, 0, parent_node)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        """按角色返回预览树节点信息。

        Args:
            index: 当前节点索引。
            role: 目标数据角色。

        Returns:
            对应角色的数据；若索引无效则返回 ``None``。
        """
        node = self._node_from_index(index)
        if node is None:
            return None

        value: Any = None
        if role == Qt.ItemDataRole.DisplayRole:
            value = node.label
        elif role == NODE_KIND_ROLE:
            value = node.kind
        elif role == AUDIO_ID_ROLE:
            value = node.audio_id
        elif role == AUDIO_AVAILABLE_ROLE:
            value = node.is_available
        elif role == NODE_PAYLOAD_ROLE:
            value = node.payload
        elif role == NODE_LOADED_ROLE:
            value = node.children_loaded
        return value

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """返回当前节点的基础交互标记。

        Args:
            index: 当前节点索引。

        Returns:
            有效节点统一允许启用与选择。
        """
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def hasChildren(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> bool:
        """判断某个节点是否还拥有下一层子节点。

        Args:
            parent: 父节点索引。

        Returns:
            是否还有下一层可展开内容。
        """
        if not parent.isValid():
            return bool(self._root_nodes)

        node = self._node_from_index(parent)
        if node is None:
            return False
        return self._node_has_children(node.kind, node.payload)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        """提供树视图列标题。

        Args:
            section: 列号。
            orientation: 表头方向。
            role: 目标数据角色。

        Returns:
            首列标题文本；其余场景返回 ``None``。
        """
        if orientation == Qt.Orientation.Horizontal and section == 0 and role == Qt.ItemDataRole.DisplayRole:
            return "试听视图"
        return None

    def ensure_children_loaded(self, index: QModelIndex) -> None:
        """在节点首次展开时填充下一层子节点。

        Args:
            index: 需要加载子节点的父索引。
        """
        node = self._node_from_index(index)
        if node is None or node.kind == "audio_id" or node.children_loaded:
            return

        children = self._build_children(node)
        if children:
            self.beginInsertRows(index, 0, len(children) - 1)
            node.children = children
            node.children_loaded = True
            self.endInsertRows()
            return

        node.children = []
        node.children_loaded = True

    def _children_for_parent(self, parent: QModelIndex) -> list[_PreviewTreeNode] | None:
        """返回父节点当前已加载的子节点列表。"""
        node = self._node_from_index(parent)
        if node is None or not node.children_loaded:
            return None
        return node.children or []

    def _node_from_index(self, index: QModelIndex) -> _PreviewTreeNode | None:
        """从模型索引中取回内部节点。"""
        if not index.isValid():
            return None
        node = index.internalPointer()
        return node if isinstance(node, _PreviewTreeNode) else None

    def _build_children(self, node: _PreviewTreeNode) -> list[_PreviewTreeNode]:
        """根据当前节点类别构造下一层子节点。"""
        if node.kind == "group":
            return self._build_audio_type_children(node)
        if node.kind == "audio_type":
            return self._build_event_children(node)
        if node.kind == "event":
            return self._build_audio_id_children(node)
        return []

    def _build_audio_type_children(self, node: _PreviewTreeNode) -> list[_PreviewTreeNode]:
        """构造分组节点下的音频类别子节点。"""
        payload = node.payload
        if not isinstance(payload, dict):
            return []

        children: list[_PreviewTreeNode] = []
        for audio_type_name, event_payload in payload.items():
            if not isinstance(event_payload, dict):
                continue
            children.append(
                _PreviewTreeNode(
                    label=str(audio_type_name),
                    kind="audio_type",
                    payload=event_payload,
                    parent=node,
                )
            )
        return children

    def _build_event_children(self, node: _PreviewTreeNode) -> list[_PreviewTreeNode]:
        """构造音频类别节点下的事件子节点。"""
        payload = node.payload
        if not isinstance(payload, dict):
            return []

        children: list[_PreviewTreeNode] = []
        for event_name, audio_ids in payload.items():
            if not isinstance(audio_ids, list | tuple):
                continue
            children.append(
                _PreviewTreeNode(
                    label=str(event_name),
                    kind="event",
                    payload=[str(audio_id).strip() for audio_id in audio_ids if str(audio_id).strip()],
                    parent=node,
                )
            )
        return children

    def _build_audio_id_children(self, node: _PreviewTreeNode) -> list[_PreviewTreeNode]:
        """构造事件节点下的音频 ID 叶子节点。"""
        payload = node.payload
        if not isinstance(payload, list | tuple):
            return []

        children: list[_PreviewTreeNode] = []
        for audio_id in payload:
            audio_id_text = str(audio_id).strip()
            if not audio_id_text:
                continue
            children.append(
                _PreviewTreeNode(
                    label=audio_id_text,
                    kind="audio_id",
                    payload=None,
                    parent=node,
                    audio_id=audio_id_text,
                    is_available=audio_id_text in self._available_audio_ids,
                    children=[],
                    children_loaded=True,
                )
            )
        return children

    def _node_has_children(self, kind: str, payload: Any) -> bool:
        """判断一个节点是否还有下一层可展开内容。"""
        if kind in {"group", "audio_type"}:
            return isinstance(payload, dict) and bool(payload)
        if kind == "event":
            return isinstance(payload, list | tuple) and any(str(item).strip() for item in payload)
        return False


class PreviewTreeView(QTreeView):
    """最基础的试听树视图。"""

    def _index_depth(self, index: QModelIndex) -> int:
        """返回当前节点深度。"""
        depth = 0
        current = index.parent()
        while current.isValid():
            depth += 1
            current = current.parent()
        return depth

    def _row_rect(self, option) -> QRect:
        """返回整行背景矩形。"""
        return QRect(
            PREVIEW_TREE_ROW_HORIZONTAL_MARGIN,
            option.rect.top() + 2,
            max(0, self.viewport().width() - PREVIEW_TREE_ROW_HORIZONTAL_MARGIN * 2),
            max(0, option.rect.height() - 4),
        )

    def _content_rect(self, option, index: QModelIndex) -> QRect:
        """返回文本内容绘制区域。"""
        row_rect = self._row_rect(option)
        depth = self._index_depth(index)
        icon_span = max(PREVIEW_TREE_BRANCH_SLOT_WIDTH, PREVIEW_TREE_BRANCH_ICON_SIZE)
        content_left = (
            row_rect.left()
            + depth * self.indentation()
            + icon_span
            + PREVIEW_TREE_TEXT_GAP
        )
        return QRect(
            content_left,
            option.rect.top(),
            max(0, row_rect.right() - content_left - 8),
            option.rect.height(),
        )

    def _draw_selected_bar(self, painter: QPainter, row_rect: QRect, index: QModelIndex) -> None:
        """绘制选中竖条。"""
        selection_model = self.selectionModel()
        is_selected = selection_model.isSelected(index) if selection_model is not None else False
        if not is_selected:
            return

        bar_rect = QRect(
            row_rect.left() + PREVIEW_TREE_SELECTED_BAR_MARGIN,
            row_rect.top() + 7,
            PREVIEW_TREE_SELECTED_BAR_WIDTH,
            max(0, row_rect.height() - 14),
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(themeColor()))
        painter.drawRoundedRect(bar_rect, 2, 2)
        painter.restore()

    def _draw_branch_icon(self, painter: QPainter, row_rect: QRect, index: QModelIndex) -> None:
        """按当前层级绘制展开/收缩图标。"""
        if not self._has_expand_icon(index):
            return

        depth = self._index_depth(index)
        slot_left = row_rect.left() + depth * self.indentation()
        icon_size = PREVIEW_TREE_BRANCH_ICON_SIZE
        icon_rect = QRect(
            slot_left + (PREVIEW_TREE_BRANCH_SLOT_WIDTH - icon_size) // 2,
            row_rect.center().y() - icon_size // 2 + 1,
            icon_size,
            icon_size,
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(resolve_fluent_text_primary_color(), PREVIEW_TREE_BRANCH_ICON_STROKE_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        center = icon_rect.center()
        half_w = icon_rect.width() / 2
        half_h = icon_rect.height() / 2
        if self.isExpanded(index):
            points = (
                QPointF(center.x() - half_w * 0.55, center.y() - half_h * 0.2),
                QPointF(center.x(), center.y() + half_h * 0.35),
                QPointF(center.x() + half_w * 0.55, center.y() - half_h * 0.2),
            )
        else:
            points = (
                QPointF(center.x() - half_w * 0.2, center.y() - half_h * 0.55),
                QPointF(center.x() + half_w * 0.35, center.y()),
                QPointF(center.x() - half_w * 0.2, center.y() + half_h * 0.55),
            )
        painter.drawLine(points[0], points[1])
        painter.drawLine(points[1], points[2])
        painter.restore()

    def _hovered_index_at_y(self, pos_y: int) -> QModelIndex:
        """按行命中 hover 索引，避免受 branch 子控件分块影响。"""
        probe_xs = (
            max(1, self.viewport().width() - 8),
            max(1, self.viewport().width() // 2),
            min(max(1, self.indentation() + 24), max(1, self.viewport().width() - 1)),
        )
        for probe_x in probe_xs:
            index = self.indexAt(QPoint(probe_x, pos_y))
            if index.isValid():
                return index
        return QModelIndex()

    def _has_expand_icon(self, index: QModelIndex) -> bool:
        """返回当前节点是否应显示展开/收缩尖号。"""
        model = self.model()
        return model is not None and model.hasChildren(index)

    def _current_row_color(self, index: QModelIndex) -> QColor | None:
        """返回当前行的自定义背景色。"""
        selection_model = self.selectionModel()
        is_selected = selection_model.isSelected(index) if selection_model is not None else False
        is_hovered = index == self._hovered_index
        if not is_selected and not is_hovered:
            return None

        return resolve_fluent_neutral_surface(
            "emphasis_selected" if is_selected else "emphasis_hover"
        )

    def __init__(self, parent=None) -> None:
        """初始化树视图。

        Args:
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._hovered_index = QModelIndex()
        model = PreviewTreeModel(self)
        self.setModel(model)
        self.setHeaderHidden(True)
        self.setIndentation(PREVIEW_TREE_INDENTATION)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        inject_preview_tree_style(self)
        self.expanded.connect(model.ensure_children_loaded)

    def viewportEvent(self, event) -> bool:
        """跟踪 hover 行并触发重绘。"""
        if event.type() == QEvent.Type.HoverMove:
            hovered_index = self._hovered_index_at_y(event.position().toPoint().y())
            if hovered_index != self._hovered_index:
                self._hovered_index = hovered_index
                self.viewport().update()
        elif event.type() in {QEvent.Type.HoverLeave, QEvent.Type.Leave}:
            if self._hovered_index.isValid():
                self._hovered_index = QModelIndex()
                self.viewport().update()
        return super().viewportEvent(event)

    def drawBranches(self, painter: QPainter, rect: QRect, index: QModelIndex) -> None:
        """只绘制展开/收缩图标，避免默认 branch 连接线与背景叠加。"""
        return

    def drawRow(self, painter: QPainter, option, index: QModelIndex) -> None:
        """绘制统一的整行 hover/selected 背景。"""
        row_color = self._current_row_color(index)
        row_rect = self._row_rect(option)
        if row_color is not None:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setClipping(False)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(row_color)
            painter.drawRoundedRect(row_rect, 6, 6)
            painter.restore()

        self._draw_selected_bar(painter, row_rect, index)
        self._draw_branch_icon(painter, row_rect, index)

        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.StateFlag.State_Selected
        clean_option.state &= ~QStyle.StateFlag.State_MouseOver
        clean_option.state &= ~QStyle.StateFlag.State_HasFocus
        clean_option.showDecorationSelected = False
        clean_option.features &= ~QStyleOptionViewItem.ViewItemFeature.Alternate
        clean_option.rect = self._content_rect(option, index)
        delegate = self.itemDelegateForIndex(index) or self.itemDelegate()
        if delegate is not None:
            delegate.paint(painter, clean_option, index)


__all__ = [
    "AUDIO_AVAILABLE_ROLE",
    "AUDIO_ID_ROLE",
    "EMPTY_MODEL_INDEX",
    "NODE_KIND_ROLE",
    "NODE_LOADED_ROLE",
    "NODE_PAYLOAD_ROLE",
    "PreviewTreeModel",
    "PreviewTreeView",
    "TreeStats",
    "build_tree_summary_text",
    "collect_tree_stats",
]
