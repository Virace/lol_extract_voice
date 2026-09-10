"""实体总览左侧列表面板。"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QSignalBlocker, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SearchLineEdit,
    SegmentedWidget,
    TransparentDropDownToolButton,
    isDarkTheme,
    qconfig,
)

from lol_audio_unpack.app.resource_pack import ResourcePackWadRef
from lol_audio_unpack.gui.common.font_compat import apply_line_edit_safe_font
from lol_audio_unpack.gui.common.styles import resolve_fluent_entity_badge_colors
from lol_audio_unpack.gui.components.overview_entity_list import OVERVIEW_ROW_ROLE, OverviewEntityListView
from lol_audio_unpack.gui.controllers.contracts import OverviewSelectionSyncRequest


class OverviewStatusLegend(QWidget):
    """解释实体列表中 A 音频与 M 映射状态的轻量图例。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化状态图例。"""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.audio_badge = QLabel("A", self)
        self.mapping_badge = QLabel("M", self)
        self.audio_label = CaptionLabel("音频", self)
        self.mapping_label = CaptionLabel("映射", self)
        for badge in (self.audio_badge, self.mapping_badge):
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(22, 22)
            badge_font = badge.font()
            badge_font.setPixelSize(14)
            badge_font.setWeight(badge_font.Weight.Medium)
            badge.setFont(badge_font)
        layout.addWidget(self.audio_badge)
        layout.addWidget(self.audio_label)
        layout.addSpacing(3)
        layout.addWidget(self.mapping_badge)
        layout.addWidget(self.mapping_label)
        self.setToolTip("A 表示音频产物，M 表示事件映射产物。")
        qconfig.themeChanged.connect(self.refresh_theme)
        qconfig.themeColorChanged.connect(self.refresh_theme)
        self.destroyed.connect(self._disconnect_theme_signals)
        self.refresh_theme()

    def refresh_theme(self, *_args: object) -> None:
        """刷新 A/M 胶囊的深浅主题与强调色。"""
        for badge, kind in (
            (self.audio_badge, "audio"),
            (self.mapping_badge, "mapping"),
        ):
            background, foreground = resolve_fluent_entity_badge_colors(
                kind,
                "已存在",
                self.palette(),
            )
            badge.setStyleSheet(
                "QLabel {"
                f"background-color: {background.name()};"
                f"color: {foreground.name()};"
                "border-radius: 11px;"
                "margin: 0;"
                "padding: 0 0 1px 0;"
                "}"
            )
        secondary = "#B3B3B3" if isDarkTheme() else "#616161"
        for label in (self.audio_label, self.mapping_label):
            label.setStyleSheet(f"color: {secondary};")

    def _disconnect_theme_signals(self, *_args: object) -> None:
        """释放图例持有的全局主题信号连接。"""
        for signal in (qconfig.themeChanged, qconfig.themeColorChanged):
            try:
                signal.disconnect(self.refresh_theme)
            except (RuntimeError, TypeError):
                pass


class OverviewEntityListPanel(QWidget):
    """承载总览页左侧导航、筛选与列表壳层。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化左侧列表面板。

        Args:
            parent: 父级控件。
        """
        super().__init__(parent)
        self.entity_lists: dict[str, OverviewEntityListView] = {}
        self._special_availability_message: str | None = None
        self._special_catalog_notice: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(8)

        self.nav_pivot = SegmentedWidget(self)
        self.nav_pivot.addItem("champions", "英雄")
        self.nav_pivot.addItem("maps", "地图")
        self.nav_pivot.addItem("special", "特殊内容")
        self.nav_pivot.setCurrentItem("champions")
        layout.addWidget(self.nav_pivot)

        self.search_input = SearchLineEdit(self)
        self.search_input.setPlaceholderText("搜索英雄、别名或 ID")
        apply_line_edit_safe_font(self.search_input)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self.search_input, 1)
        self.catalog_menu_btn = TransparentDropDownToolButton(FluentIcon.MORE, self)
        self.catalog_menu_btn.setToolTip("更多特殊内容操作")
        self.catalog_menu_btn.setAccessibleName("更多特殊内容操作")
        self.catalog_menu_btn.setVisible(False)
        catalog_menu = RoundMenu(parent=self.catalog_menu_btn)
        self.scan_resource_packs_action = Action("扫描本地 WAD…", catalog_menu)
        self.scan_resource_packs_action.setToolTip("从所选本地 WAD 发现额外音频内容；经典英雄无需此步骤。")
        self.scan_resource_packs_action.setEnabled(False)
        catalog_menu.addAction(self.scan_resource_packs_action)
        self.catalog_menu_btn.setMenu(catalog_menu)
        search_row.addWidget(self.catalog_menu_btn)
        layout.addLayout(search_row)

        self.special_availability_label = CaptionLabel("特殊内容需要可用的本地游戏数据。", self)
        self.special_availability_label.setWordWrap(True)
        self.special_availability_label.setVisible(False)
        layout.addWidget(self.special_availability_label)

        status_row = QWidget(self)
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        self.selection_status_label = BodyLabel("已选：0 英雄 · 0 地图 · 0 特殊内容", status_row)
        self.status_legend = OverviewStatusLegend(status_row)
        status_layout.addWidget(self.selection_status_label)
        status_layout.addStretch(1)
        status_layout.addWidget(self.status_legend)
        status_row.setMinimumHeight(32)
        layout.addWidget(status_row)

        self.list_stack = QStackedWidget(self)
        for entity_type in ("champions", "maps", "special"):
            list_widget = OverviewEntityListView(self.list_stack)
            self.entity_lists[entity_type] = list_widget
            self.list_stack.addWidget(list_widget)

        self.selection_bar = QFrame(self)
        self.selection_bar.setObjectName("OverviewSelectionBar")
        self.selection_bar.setFrameShape(QFrame.Shape.NoFrame)
        selection_layout = QVBoxLayout(self.selection_bar)
        selection_layout.setContentsMargins(0, 0, 0, 0)
        selection_layout.setSpacing(8)

        self.selection_separator = QFrame(self.selection_bar)
        self.selection_separator.setFrameShape(QFrame.Shape.HLine)
        self.selection_separator.setFrameShadow(QFrame.Shadow.Plain)
        self.selection_separator.setFixedHeight(1)
        selection_layout.addWidget(self.selection_separator)

        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)

        self.clear_selection_btn = PushButton("清空选择", self.selection_bar)
        self.sync_selection_btn = PrimaryPushButton("发送到执行中心", self.selection_bar)
        self.clear_selection_btn.setEnabled(False)
        self.sync_selection_btn.setEnabled(False)

        actions_layout.addStretch(1)
        actions_layout.addWidget(self.clear_selection_btn)
        actions_layout.addWidget(self.sync_selection_btn)
        selection_layout.addLayout(actions_layout)

        list_footer = QWidget(self)
        list_footer_layout = QVBoxLayout(list_footer)
        list_footer_layout.setContentsMargins(0, 0, 0, 0)
        list_footer_layout.setSpacing(0)
        list_footer_layout.addWidget(self.list_stack, 1)
        list_footer_layout.addWidget(self.selection_bar)
        layout.addWidget(list_footer, 1)

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
        self.catalog_menu_btn.setVisible(entity_type == "special")
        self._sync_special_availability_label()

    def set_selection_summary(self, text: str) -> None:
        """更新底部选择摘要文案。

        Args:
            text: 摘要文本。
        """
        self.selection_status_label.setText(text)

    def set_selection_counts(self, *, champion_count: int, map_count: int, special_count: int) -> None:
        """按三类实体数量刷新摘要与按钮可用性。

        Args:
            champion_count: 已选英雄数。
            map_count: 已选地图数。
            special_count: 已选特殊内容数。
        """
        total_count = champion_count + map_count + special_count
        self.set_selection_summary(f"已选：{champion_count} 英雄 · {map_count} 地图 · {special_count} 特殊内容")
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
                if row is None:
                    row = item_or_index.data(Qt.ItemDataRole.UserRole)
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
        selected_special_targets: set[str],
        special_target_names: Mapping[str, str],
        resource_pack_wads: Mapping[str, ResourcePackWadRef] | None = None,
    ) -> OverviewSelectionSyncRequest:
        """根据当前选择集合构造发送到执行中心的同步请求。"""
        champion_ids = tuple(int(entity_id) for entity_id in sorted(selected_champion_ids, key=int))
        map_ids = tuple(int(entity_id) for entity_id in sorted(selected_map_ids, key=int))
        resource_pack_wads = resource_pack_wads or {}
        special_targets = tuple(
            target
            for target in sorted(selected_special_targets)
            if not target.startswith("resource_pack:") or target in resource_pack_wads
        )
        special_names = tuple(special_target_names.get(target, "特殊内容") for target in special_targets)
        selected_wads = tuple(
            dict.fromkeys(resource_pack_wads[target] for target in special_targets if target in resource_pack_wads)
        )
        special_summary = f"、{len(special_targets)} 个特殊内容" if special_targets else ""
        return OverviewSelectionSyncRequest(
            source="overview_selection",
            champion_ids=champion_ids,
            map_ids=map_ids,
            summary=(
                f"已选择 {len(champion_ids)} 个英雄、{len(map_ids)} 张地图{special_summary}，"
                "请前往执行中心继续创建任务。"
            ),
            special_targets=special_targets,
            special_target_names=special_names,
            resource_pack_wads=selected_wads,
        )

    def set_resource_pack_scan_enabled(self, enabled: bool) -> None:
        """设置本地 WAD 扫描入口是否可执行。"""
        self.scan_resource_packs_action.setEnabled(enabled)

    def set_special_interaction_enabled(self, enabled: bool) -> None:
        """根据应用上下文就绪状态切换特殊内容目录的选择能力。"""
        special_list = self.entity_lists["special"]
        special_list.set_interaction_enabled(enabled)

    def set_special_availability_message(self, message: str | None) -> None:
        """设置特殊内容可用性边界说明。"""
        self._special_availability_message = str(message or "").strip() or None
        self._sync_special_availability_label()

    def set_special_catalog_notice(self, message: str | None) -> None:
        """设置特殊目录当前数据状态的诚实提示。"""
        self._special_catalog_notice = str(message or "").strip() or None
        self._sync_special_availability_label()

    def _sync_special_availability_label(self) -> None:
        """仅在特殊内容目录显示可用性或数据准备提示。"""
        message = self._special_availability_message or self._special_catalog_notice
        visible = self.current_entity_type() == "special" and message is not None
        self.special_availability_label.setText(message or "")
        self.special_availability_label.setVisible(visible)
