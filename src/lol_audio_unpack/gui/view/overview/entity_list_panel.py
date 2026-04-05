"""实体总览左侧列表面板。"""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QSignalBlocker, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, PrimaryPushButton, PushButton, SearchLineEdit, SegmentedWidget

from lol_audio_unpack.gui.common.font_compat import apply_line_edit_safe_font
from lol_audio_unpack.gui.components.overview_entity_list import OVERVIEW_ROW_ROLE, OverviewEntityListView
from lol_audio_unpack.gui.controllers.contracts import OverviewSelectionSyncRequest


class OverviewEntityListPanel(QWidget):
    """承载总览页左侧导航、筛选与列表壳层。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化左侧列表面板。

        Args:
            parent: 父级控件。
        """
        super().__init__(parent)
        self.entity_lists: dict[str, OverviewEntityListView] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(10)

        self.nav_pivot = SegmentedWidget(self)
        self.nav_pivot.addItem("champions", "英雄")
        self.nav_pivot.addItem("maps", "地图")
        self.nav_pivot.setCurrentItem("champions")
        layout.addWidget(self.nav_pivot)

        self.search_input = SearchLineEdit(self)
        self.search_input.setPlaceholderText("搜索英雄、地图、别名或 ID")
        apply_line_edit_safe_font(self.search_input)
        layout.addWidget(self.search_input)

        self.selection_status_label = BodyLabel("已选 0 个英雄，0 张地图。", self)
        layout.addWidget(self.selection_status_label)

        self.list_stack = QStackedWidget(self)
        for entity_type in ("champions", "maps"):
            list_widget = OverviewEntityListView(self.list_stack)
            self.entity_lists[entity_type] = list_widget
            self.list_stack.addWidget(list_widget)
        layout.addWidget(self.list_stack, 1)

        self.selection_bar = QFrame(self)
        self.selection_bar.setObjectName("OverviewSelectionBar")
        selection_layout = QHBoxLayout(self.selection_bar)
        selection_layout.setContentsMargins(12, 10, 12, 10)
        selection_layout.setSpacing(10)

        self.clear_selection_btn = PushButton("清空选择", self.selection_bar)
        self.sync_selection_btn = PrimaryPushButton("发送到执行中心", self.selection_bar)
        self.clear_selection_btn.setEnabled(False)
        self.sync_selection_btn.setEnabled(False)

        selection_layout.addStretch(1)
        selection_layout.addWidget(self.clear_selection_btn)
        selection_layout.addWidget(self.sync_selection_btn)
        layout.addWidget(self.selection_bar)

    def current_entity_type(self) -> str:
        """返回当前展示的实体类型。"""
        current_widget = self.list_stack.currentWidget()
        for entity_type, widget in self.entity_lists.items():
            if widget is current_widget:
                return entity_type
        return "champions"

    def current_list(self) -> OverviewEntityListView:
        """返回当前可见的列表控件。"""
        return self.entity_lists[self.current_entity_type()]

    def set_current_entity_type(self, entity_type: str) -> None:
        """切换当前展示的实体列表。

        Args:
            entity_type: 目标实体类型。
        """
        widget = self.entity_lists.get(entity_type)
        if widget is not None:
            self.list_stack.setCurrentWidget(widget)

    def set_selection_summary(self, text: str) -> None:
        """更新底部选择摘要文案。

        Args:
            text: 摘要文本。
        """
        self.selection_status_label.setText(text)

    def set_selection_counts(self, *, champion_count: int, map_count: int) -> None:
        """按英雄/地图数量刷新摘要与按钮可用性。

        Args:
            champion_count: 已选英雄数。
            map_count: 已选地图数。
        """
        total_count = champion_count + map_count
        self.set_selection_summary(f"已选 {champion_count} 个英雄，{map_count} 张地图。")
        self.set_selection_actions_enabled(total_count > 0)

    def set_selection_actions_enabled(self, enabled: bool) -> None:
        """统一切换选择操作按钮可用性。

        Args:
            enabled: 是否启用清空/同步按钮。
        """
        self.clear_selection_btn.setEnabled(enabled)
        self.sync_selection_btn.setEnabled(enabled)

    def set_rows(self, entity_type: str, rows: list[dict]) -> None:
        """整体替换指定实体类型的列表数据。

        Args:
            entity_type: 目标实体类型。
            rows: 实体摘要行。
        """
        self.entity_lists[entity_type].set_rows(rows)

    def apply_keyword_and_restore(
        self,
        *,
        entity_type: str,
        keyword: str,
        selected_ids: set[str],
        current_entity_id: str | None,
    ) -> int:
        """对指定列表应用筛选并恢复当前选择态。

        Args:
            entity_type: 目标实体类型。
            keyword: 搜索关键字。
            selected_ids: 当前已选实体 ID 集合。
            current_entity_id: 当前预览实体 ID。

        Returns:
            int: 过滤后可见行数。
        """
        list_widget = self.entity_lists[entity_type]
        selection_model = list_widget.selectionModel()
        blockers = [QSignalBlocker(list_widget)]
        if selection_model is not None:
            blockers.append(QSignalBlocker(selection_model))
        list_widget.set_keyword(keyword)
        list_widget.restore_state(selected_ids, current_entity_id)
        del blockers
        return list_widget.visible_row_count()

    def find_index_by_entity_id(self, entity_type: str, entity_id: str | None):
        """按实体 ID 在指定列表中查找代理索引。"""
        return self.entity_lists[entity_type].find_index_by_entity_id(entity_id)

    def selected_entity_ids(self, entity_type: str) -> set[str]:
        """返回指定列表当前选择的实体 ID 集合。"""
        return self.entity_lists[entity_type].selected_entity_ids()

    def resolve_row_payload(self, item_or_index) -> dict | None:
        """从当前项或模型索引中提取统一行数据。"""
        row = None
        if item_or_index is None:
            return None
        if isinstance(item_or_index, QModelIndex):
            if item_or_index.isValid():
                row = item_or_index.data(OVERVIEW_ROW_ROLE)
        elif hasattr(item_or_index, "isValid") and callable(item_or_index.isValid):
            if item_or_index.isValid():
                row = item_or_index.data(OVERVIEW_ROW_ROLE)
        elif hasattr(item_or_index, "data"):
            row = item_or_index.data(Qt.ItemDataRole.UserRole)
        return dict(row) if isinstance(row, dict) else None

    def clear_selection(self, entity_type: str) -> None:
        """清空指定列表当前选择与 current index。"""
        list_widget = self.entity_lists[entity_type]
        selection_model = list_widget.selectionModel()
        blockers = [QSignalBlocker(list_widget)]
        if selection_model is not None:
            blockers.append(QSignalBlocker(selection_model))
            selection_model.clearSelection()
            selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
        list_widget.setCurrentIndex(QModelIndex())
        del blockers

    def build_selection_sync_request(
        self,
        *,
        selected_champion_ids: set[str],
        selected_map_ids: set[str],
    ) -> OverviewSelectionSyncRequest:
        """根据当前选择集合构造发送到执行中心的同步请求。"""
        champion_ids = tuple(int(entity_id) for entity_id in sorted(selected_champion_ids, key=int))
        map_ids = tuple(int(entity_id) for entity_id in sorted(selected_map_ids, key=int))
        return OverviewSelectionSyncRequest(
            source="overview_selection",
            champion_ids=champion_ids,
            map_ids=map_ids,
            summary=f"已选择 {len(champion_ids)} 个英雄、{len(map_ids)} 张地图，请前往执行中心继续创建任务。",
        )
