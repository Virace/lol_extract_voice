"""实体总览页试听树的 model、delegate 与 view 组件。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPalette, QPen, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QStyleOptionViewItem, QTreeView
from qfluentwidgets import CustomStyleSheet, setCustomStyleSheet, setStyleSheet
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.components.widgets.tree_view import TreeItemDelegate

NODE_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
AUDIO_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 2
AUDIO_AVAILABLE_ROLE = int(Qt.ItemDataRole.UserRole) + 3
NODE_PAYLOAD_ROLE = int(Qt.ItemDataRole.UserRole) + 4
NODE_LOADED_ROLE = int(Qt.ItemDataRole.UserRole) + 5
NODE_PLACEHOLDER_ROLE = int(Qt.ItemDataRole.UserRole) + 6


@dataclass(frozen=True, slots=True)
class AudioPreviewStats:
    """试听树摘要统计。"""

    skin_count: int = 0
    audio_type_count: int = 0
    event_count: int = 0
    audio_id_count: int = 0
    available_audio_id_count: int = 0


def collect_audio_preview_stats(
    mapping_data: dict[str, Any] | None,
    available_audio_ids: set[str],
) -> AudioPreviewStats:
    """统计完整试听树中的层级与可试听 ID 数量。

    Args:
        mapping_data: 当前实体的原始 mapping 数据。
        available_audio_ids: 当前实体本地已存在的 wem ID 集合。

    Returns:
        用于右侧摘要卡的统计数据。
    """
    skins = mapping_data.get("skins", {}) if isinstance(mapping_data, dict) else {}
    if not isinstance(skins, dict):
        return AudioPreviewStats()

    skin_count = 0
    audio_type_count = 0
    event_count = 0
    audio_id_count = 0
    available_audio_id_count = 0

    for skin_payload in skins.values():
        if not isinstance(skin_payload, dict):
            continue

        skin_count += 1
        events_payload = skin_payload.get("events", {})
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

    return AudioPreviewStats(
        skin_count=skin_count,
        audio_type_count=audio_type_count,
        event_count=event_count,
        audio_id_count=audio_id_count,
        available_audio_id_count=available_audio_id_count,
    )


def build_audio_preview_summary_text(stats: AudioPreviewStats) -> str:
    """构造试听视图顶部摘要文案。"""
    return (
        f"皮肤 {stats.skin_count} · 类型 {stats.audio_type_count} · "
        f"事件 {stats.event_count} · ID {stats.audio_id_count} · 可试听 {stats.available_audio_id_count}"
    )


def build_branch_indicator_center_x(depth: int, indentation: int, base_offset: int = 14) -> int:
    """根据层级计算展开箭头的水平中心位置。"""
    return base_offset + max(0, depth) * max(0, indentation)


def _build_audio_preview_tree_styles() -> tuple[str, str]:
    """构造试听树在亮暗主题下的轻量样式。"""
    light_qss = """
    QTreeView {
        background-color: rgba(255, 255, 255, 0.92);
        color: #202020;
        border: 1px solid rgba(0, 0, 0, 0.10);
        border-radius: 10px;
        outline: none;
        padding: 6px;
    }
    QTreeView::item {
        min-height: 28px;
        padding: 2px 6px;
        border-radius: 6px;
    }
    QTreeView::item:hover {
        background-color: rgba(0, 0, 0, 0.05);
    }
    QTreeView::item:selected {
        background-color: rgba(0, 0, 0, 0.08);
        color: #111111;
    }
    QTreeView::branch {
        background: transparent;
    }
    QTreeView::branch:hover {
        background-color: rgba(0, 0, 0, 0.05);
    }
    QTreeView::branch:selected {
        background-color: rgba(0, 0, 0, 0.08);
    }
    QHeaderView::section {
        background: transparent;
        border: none;
    }
    """
    dark_qss = """
    QTreeView {
        background-color: rgba(28, 28, 30, 0.94);
        color: #F5F5F5;
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 10px;
        outline: none;
        padding: 6px;
    }
    QTreeView::item {
        min-height: 28px;
        padding: 2px 6px;
        border-radius: 6px;
    }
    QTreeView::item:hover {
        background-color: rgba(255, 255, 255, 0.06);
    }
    QTreeView::item:selected {
        background-color: rgba(255, 255, 255, 0.10);
        color: #FFFFFF;
    }
    QTreeView::branch {
        background: transparent;
    }
    QTreeView::branch:hover {
        background-color: rgba(255, 255, 255, 0.06);
    }
    QTreeView::branch:selected {
        background-color: rgba(255, 255, 255, 0.10);
    }
    QHeaderView::section {
        background: transparent;
        border: none;
    }
    """
    return light_qss, dark_qss


class AudioPreviewTreeModel(QStandardItemModel):
    """按需展开的试听树数据模型。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._available_audio_ids: set[str] = set()
        self.clear_preview()

    def clear_preview(self) -> None:
        """清空当前试听树内容。"""
        self.clear()
        self.setColumnCount(1)
        self.setHorizontalHeaderLabels(["试听视图"])
        self._available_audio_ids = set()

    def set_preview_data(
        self,
        mapping_data: dict[str, Any] | None,
        available_audio_ids: set[str],
    ) -> None:
        """替换当前试听树数据。

        Args:
            mapping_data: 当前实体的原始 mapping 数据。
            available_audio_ids: 当前实体本地已存在的 wem ID 集合。
        """
        self.clear_preview()
        self._available_audio_ids = {str(audio_id) for audio_id in available_audio_ids}
        skins = mapping_data.get("skins", {}) if isinstance(mapping_data, dict) else {}
        if not isinstance(skins, dict):
            return

        for skin_id, skin_payload in skins.items():
            if not isinstance(skin_payload, dict):
                continue

            events_payload = skin_payload.get("events", {})
            item = self._create_branch_item(str(skin_id), "skin", events_payload)
            self.appendRow(item)

    def ensure_children_loaded(self, index) -> None:
        """在节点首次展开时填充下一层子节点。

        Args:
            index: 当前展开的模型索引。
        """
        if not index.isValid():
            return

        item = self.itemFromIndex(index)
        if item is None:
            return

        if item.data(NODE_KIND_ROLE) == "audio_id":
            return

        if bool(item.data(NODE_LOADED_ROLE)):
            return

        kind = item.data(NODE_KIND_ROLE)
        payload = item.data(NODE_PAYLOAD_ROLE)
        item.removeRows(0, item.rowCount())

        if kind == "skin":
            self._populate_skin_children(item, payload)
        elif kind == "audio_type":
            self._populate_event_children(item, payload)
        elif kind == "event":
            self._populate_audio_id_children(item, payload)

        item.setData(True, NODE_LOADED_ROLE)

    def _populate_skin_children(self, parent: QStandardItem, payload: Any) -> None:
        """填充皮肤节点下的类型分组。"""
        if not isinstance(payload, dict):
            return

        for audio_type_name, event_payload in payload.items():
            if not isinstance(event_payload, dict):
                continue

            parent.appendRow(self._create_branch_item(str(audio_type_name), "audio_type", event_payload))

    def _populate_event_children(self, parent: QStandardItem, payload: Any) -> None:
        """填充事件节点。"""
        if not isinstance(payload, dict):
            return

        for event_name, audio_ids in payload.items():
            if not isinstance(audio_ids, list | tuple):
                continue

            parent.appendRow(self._create_branch_item(str(event_name), "event", list(audio_ids)))

    def _populate_audio_id_children(self, parent: QStandardItem, payload: Any) -> None:
        """填充音频 ID 叶子节点。"""
        if not isinstance(payload, list | tuple):
            return

        for audio_id in payload:
            audio_id_text = str(audio_id).strip()
            if not audio_id_text:
                continue

            parent.appendRow(
                self._create_audio_id_item(
                    audio_id=audio_id_text,
                    is_available=audio_id_text in self._available_audio_ids,
                )
            )

    def _create_branch_item(self, label: str, kind: str, payload: Any) -> QStandardItem:
        """创建一个可按需展开的分支节点。"""
        item = QStandardItem(label)
        item.setEditable(False)
        item.setData(kind, NODE_KIND_ROLE)
        item.setData(payload, NODE_PAYLOAD_ROLE)
        item.setData(False, NODE_LOADED_ROLE)
        item.setToolTip(label)
        if self._node_has_children(kind, payload):
            item.appendRow(self._create_placeholder_item())
        else:
            item.setData(True, NODE_LOADED_ROLE)
        return item

    def _create_audio_id_item(self, audio_id: str, is_available: bool) -> QStandardItem:
        """创建音频 ID 叶子节点。"""
        item = QStandardItem(audio_id)
        item.setEditable(False)
        item.setIcon(FIF.PLAY.icon())
        item.setData("audio_id", NODE_KIND_ROLE)
        item.setData(audio_id, AUDIO_ID_ROLE)
        item.setData(is_available, AUDIO_AVAILABLE_ROLE)
        item.setData(True, NODE_LOADED_ROLE)
        item.setToolTip(audio_id)
        item.setSizeHint(QSize(0, 30))
        if not is_available:
            item.setEnabled(False)
        return item

    def _create_placeholder_item(self) -> QStandardItem:
        """创建用于保留展开箭头的占位节点。"""
        placeholder = QStandardItem("")
        placeholder.setEditable(False)
        placeholder.setEnabled(False)
        placeholder.setData(True, NODE_PLACEHOLDER_ROLE)
        return placeholder

    def _node_has_children(self, kind: str, payload: Any) -> bool:
        """判断一个分支节点是否还有下一层可展开内容。"""
        if kind == "skin":
            return isinstance(payload, dict) and bool(payload)
        if kind == "audio_type":
            return isinstance(payload, dict) and bool(payload)
        if kind == "event":
            return isinstance(payload, list | tuple) and any(str(item).strip() for item in payload)
        return False


class AudioPreviewTreeDelegate(TreeItemDelegate):
    """试听树代理，仅保留稳定的行高控制。"""

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        """为音频 ID 叶子节点提供更稳定的行高。"""
        hint = super().sizeHint(option, index)
        if index.data(AUDIO_ID_ROLE):
            hint.setHeight(max(hint.height(), 30))
        return hint


class AudioPreviewTreeView(QTreeView):
    """实体总览页右侧的试听树控件。"""

    audio_id_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.preview_model = AudioPreviewTreeModel(self)
        self.setModel(self.preview_model)
        self.setHeaderHidden(True)
        self.header().setHighlightSections(False)
        self.header().setDefaultAlignment(Qt.AlignCenter)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setUniformRowHeights(True)
        self.setIndentation(22)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(18)
        self.horizontalScrollBar().setSingleStep(18)
        self.setIconSize(QSize(16, 16))
        self.setMouseTracking(True)
        self.setItemDelegate(AudioPreviewTreeDelegate(self))
        light_qss, dark_qss = _build_audio_preview_tree_styles()
        setCustomStyleSheet(self, light_qss, dark_qss)
        setStyleSheet(self, CustomStyleSheet(self))

        self.expanded.connect(self.ensure_children_loaded)
        self.clicked.connect(self.try_emit_audio_request)

    def set_preview_data(self, mapping_data: dict[str, Any] | None, available_audio_ids: set[str]) -> None:
        """刷新当前试听树数据。"""
        self.setUpdatesEnabled(False)
        try:
            self.collapseAll()
            self.preview_model.set_preview_data(mapping_data, available_audio_ids)
        finally:
            self.setUpdatesEnabled(True)

    def clear_preview(self) -> None:
        """清空当前试听树。"""
        self.collapseAll()
        self.preview_model.clear_preview()

    def ensure_children_loaded(self, index) -> None:
        """确保指定索引的下一层子节点已经填充。"""
        self.preview_model.ensure_children_loaded(index)

    def try_emit_audio_request(self, index) -> bool:
        """尝试为当前叶子节点发出试听请求。

        Args:
            index: 当前点击的模型索引。

        Returns:
            成功发出请求时返回 ``True``，否则返回 ``False``。
        """
        if not index.isValid():
            return False

        audio_id = index.data(AUDIO_ID_ROLE)
        is_available = bool(index.data(AUDIO_AVAILABLE_ROLE))
        if not audio_id or not is_available:
            return False

        self.audio_id_requested.emit(str(audio_id))
        return True

    def drawBranches(self, painter: QPainter, rect, index) -> None:
        """绘制更清晰的展开/折叠箭头。"""
        if not index.isValid() or not self.model().hasChildren(index):
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color_group = QPalette.ColorGroup.Disabled if not self.isEnabled() else QPalette.ColorGroup.Active
        color = self.palette().color(color_group, QPalette.ColorRole.Text)
        painter.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        center_x = rect.center().x()
        center_y = rect.center().y()
        if self.isExpanded(index):
            painter.drawLine(center_x - 4, center_y - 2, center_x, center_y + 2)
            painter.drawLine(center_x, center_y + 2, center_x + 4, center_y - 2)
        else:
            painter.drawLine(center_x - 2, center_y - 4, center_x + 2, center_y)
            painter.drawLine(center_x + 2, center_y, center_x - 2, center_y + 4)

        painter.restore()
