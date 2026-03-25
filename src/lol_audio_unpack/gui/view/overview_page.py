"""实体总览页面，负责展示实体状态并预留右侧资源预览区。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    QSignalBlocker,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SegmentedWidget,
    StrongBodyLabel,
    SubtitleLabel,
    TransparentToolButton,
    qconfig,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.gui.common import apply_smooth_scroll_enabled
from lol_audio_unpack.gui.components.overview_entity_list import OVERVIEW_ROW_ROLE, OverviewEntityListView
from lol_audio_unpack.gui.components.preview_tree import (
    PreviewTreeModel,
    PreviewTreeView,
    build_tree_summary_text,
    collect_tree_stats,
)
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader


def build_preview_path_text(mapping_path: Path | None) -> str:
    """构造右侧预览区域顶部路径文本。

    Args:
        mapping_path: 当前选中的映射文件路径。

    Returns:
        存在映射文件时返回完整路径，否则返回空字符串。
    """
    if mapping_path is None:
        return ""
    return str(mapping_path)


def create_preview_path_edit(parent: QWidget | None = None) -> LineEdit:
    """创建跟随 Fluent 主题的预览路径输入框。"""
    line_edit = LineEdit(parent)
    line_edit.setReadOnly(True)
    line_edit.setClearButtonEnabled(False)
    line_edit.setPlaceholderText("请选择左侧实体以查看原始数据。")
    line_edit.setMinimumWidth(0)
    line_edit.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    return line_edit


class OverviewPage(QWidget):
    """实体总览页面。

    英雄与地图分别维护独立列表缓存，仅在数据刷新时重建；
    tab 切换与搜索只在现有列表项上切换或隐藏，不再 rebuild。
    """

    selection_sync_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("OverviewPage")
        self.setStyleSheet("QWidget#OverviewPage{background: transparent}")
        self.gui_config = None
        self._app_context = None
        self._loader = None
        self._cached_data: dict[str, list[dict[str, Any]]] = {"champions": [], "maps": []}
        self._selected_entity_ids: dict[str, set[str]] = {"champions": set(), "maps": set()}
        self._current_preview_ids: dict[str, str | None] = {"champions": None, "maps": None}
        self._current_mapping_path: Path | None = None
        self._entity_lists: dict[str, OverviewEntityListView] = {}
        self._audio_preview_placeholder = "请选择左侧实体以查看事件内容。"
        self._build_ui()
        self._setup_connections()

    def showEvent(self, event):
        """页面首次展示时同步当前缓存。"""
        super().showEvent(event)
        if self._current_preview_ids[self._current_entity_type()] is None:
            self._set_splitter_sizes_evenly()
        self._sync_current_list_view()

    def set_gui_config(self, cfg) -> None:
        """注入 GUI 配置。"""
        self.gui_config = cfg
        fallback_enabled = bool(getattr(cfg, "smooth_scroll_enabled", False))
        self.set_smooth_scroll_enabled(
            bool(getattr(cfg, "widget_smooth_scroll_enabled", fallback_enabled))
        )

    def set_app_context(self, app_context) -> None:
        """注入应用上下文。

        Args:
            app_context: 当前应用上下文；为 ``None`` 时仅保留占位提示。
        """
        self._app_context = app_context
        self._loader = None
        if app_context is None:
            self._show_placeholder("当前配置尚未完成初始化，暂时无法读取预览内容。")
            return

        current_index = self._current_entity_list().currentIndex()
        if current_index.isValid():
            self._load_preview_for_item(self._current_entity_type(), current_index)

    def set_entity_data(self, entity_type: str, data: list[dict[str, Any]]) -> None:
        """更新页面缓存的实体数据。"""
        if entity_type not in self._cached_data:
            return

        self._cached_data[entity_type] = data
        self._rebuild_entity_list(entity_type)
        if self._current_entity_type() == entity_type:
            self._sync_current_list_view()
        else:
            self._update_selection_summary()

    def clear_data(self) -> None:
        """清空页面缓存并恢复占位内容。"""
        self._cached_data = {"champions": [], "maps": []}
        self._selected_entity_ids = {"champions": set(), "maps": set()}
        self._current_preview_ids = {"champions": None, "maps": None}
        self._current_mapping_path = None
        for _entity_type, list_widget in self._entity_lists.items():
            selection_model = list_widget.selectionModel()
            blockers = [QSignalBlocker(list_widget)]
            if selection_model is not None:
                blockers.append(QSignalBlocker(selection_model))
                selection_model.clearSelection()
                selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
            list_widget.set_rows([])
            list_widget.setCurrentIndex(QModelIndex())
            del blockers
        self.list_summary_label.setText("等待实体数据加载…")
        self._update_selection_summary()
        self._show_placeholder("当前暂无可预览的内容。")

    def _setup_connections(self) -> None:
        self.nav_pivot.currentItemChanged.connect(self._on_nav_changed)
        self.preview_mode_pivot.currentItemChanged.connect(self._on_preview_mode_changed)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.sync_selection_btn.clicked.connect(self._sync_selected_entities)
        self.clear_selection_btn.clicked.connect(self._clear_selected_entities)
        self.reveal_file_btn.clicked.connect(self._reveal_selected_mapping_file)
        qconfig.themeChanged.connect(lambda _theme: self._refresh_entity_list_theme())
        qconfig.themeColorChanged.connect(lambda _color: self._refresh_entity_list_theme())

        for entity_type, list_widget in self._entity_lists.items():
            selection_model = list_widget.selectionModel()
            if selection_model is None:
                continue
            selection_model.currentChanged.connect(
                lambda current, previous, et=entity_type: self._on_current_item_changed(et, current, previous)
            )
            selection_model.selectionChanged.connect(
                lambda _selected, _deselected, et=entity_type: self._on_entity_selection_changed(et)
            )

    def _refresh_entity_list_theme(self) -> None:
        """在主题或主题色变化后刷新列表绘制。"""
        for list_widget in self._entity_lists.values():
            try:
                list_widget.refresh_theme()
            except RuntimeError:
                continue

    def _on_preview_mode_changed(self, mode_key: str) -> None:
        """切换右侧 Raw 与试听视图。"""
        is_audio_mode = mode_key == "audio"
        self.preview_stack.setCurrentWidget(self.audio_preview_tree if is_audio_mode else self.text_preview)
        self.audio_preview_summary_card.setVisible(is_audio_mode)

    def _current_entity_type(self) -> str:
        return self.nav_pivot.currentRouteKey() or "champions"

    def _current_entity_list(self) -> OverviewEntityListView:
        return self._entity_lists[self._current_entity_type()]

    def _ensure_loader(self) -> EntityDataLoader | None:
        if self._loader is None and self._app_context is not None:
            self._loader = EntityDataLoader(self._app_context)
        return self._loader

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        header_layout = QHBoxLayout()
        title_label = SubtitleLabel("实体总览", self)
        self.subtitle_label = CaptionLabel("统一查看实体状态、筛选与选择，并同步到执行中心。", self)
        self.subtitle_label.setWordWrap(False)

        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        title_column.addWidget(title_label)
        title_column.addWidget(self.subtitle_label)

        header_layout.addLayout(title_column)
        header_layout.addStretch(1)
        root_layout.addLayout(header_layout)

        self.nav_pivot = SegmentedWidget(self)
        self.nav_pivot.addItem("champions", "英雄")
        self.nav_pivot.addItem("maps", "地图")
        self.nav_pivot.setCurrentItem("champions")
        root_layout.addWidget(self.nav_pivot)

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setObjectName("OverviewSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(0)

        left_widget = QWidget(self.splitter)
        left_widget.setMinimumWidth(0)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 12, 0)
        left_layout.setSpacing(10)

        self.search_input = SearchLineEdit(left_widget)
        self.search_input.setPlaceholderText("搜索实体 / alias / ID")
        left_layout.addWidget(self.search_input)

        self.list_summary_label = BodyLabel("等待实体数据加载…", left_widget)
        left_layout.addWidget(self.list_summary_label)

        self.list_stack = QStackedWidget(left_widget)
        for entity_type in ("champions", "maps"):
            list_widget = OverviewEntityListView(self.list_stack)
            self._entity_lists[entity_type] = list_widget
            self.list_stack.addWidget(list_widget)
        left_layout.addWidget(self.list_stack, 1)

        selection_bar = QFrame(left_widget)
        selection_bar.setObjectName("OverviewSelectionBar")
        selection_bar.setStyleSheet(
            """
            QFrame#OverviewSelectionBar {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            """
        )
        selection_layout = QHBoxLayout(selection_bar)
        selection_layout.setContentsMargins(12, 10, 12, 10)
        selection_layout.setSpacing(10)

        self.selection_status_label = BodyLabel("尚未选中实体。", selection_bar)
        self.clear_selection_btn = PushButton("清空选择", selection_bar)
        self.sync_selection_btn = PrimaryPushButton("同步到执行中心", selection_bar)
        self.clear_selection_btn.setEnabled(False)
        self.sync_selection_btn.setEnabled(False)

        selection_layout.addWidget(self.selection_status_label, 1)
        selection_layout.addWidget(self.clear_selection_btn)
        selection_layout.addWidget(self.sync_selection_btn)
        left_layout.addWidget(selection_bar)

        right_widget = QWidget(self.splitter)
        right_widget.setMinimumWidth(0)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(8)

        preview_title = StrongBodyLabel("资源预览", right_widget)
        preview_hint = CaptionLabel("右侧支持事件树与原始数据预览；事件树当前仅展示基础层级。", right_widget)
        preview_hint.setWordWrap(True)
        right_layout.addWidget(preview_title)
        right_layout.addWidget(preview_hint)

        right_header = QHBoxLayout()
        self.preview_path_edit = create_preview_path_edit(right_widget)
        self.reveal_file_btn = TransparentToolButton(FIF.LINK, right_widget)
        self.reveal_file_btn.setToolTip("打开文件所在位置")
        self.reveal_file_btn.setFixedSize(32, 32)
        self.reveal_file_btn.setEnabled(False)

        right_header.addWidget(self.preview_path_edit, 1)
        right_header.addWidget(self.reveal_file_btn)
        right_layout.addLayout(right_header)

        self.preview_mode_pivot = SegmentedWidget(right_widget)
        self.preview_mode_pivot.addItem("audio", "事件")
        self.preview_mode_pivot.addItem("raw", "原始数据")
        self.preview_mode_pivot.setCurrentItem("audio")
        right_layout.addWidget(self.preview_mode_pivot)

        self.audio_preview_summary_card = QFrame(right_widget)
        self.audio_preview_summary_card.setObjectName("AudioPreviewSummaryCard")
        self.audio_preview_summary_card.setStyleSheet(
            """
            QFrame#AudioPreviewSummaryCard {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
            """
        )
        summary_layout = QVBoxLayout(self.audio_preview_summary_card)
        summary_layout.setContentsMargins(12, 10, 12, 10)
        summary_layout.setSpacing(4)
        self.audio_preview_summary_label = BodyLabel(
            "事件树会保留首层分组；英雄显示皮肤名，地图显示 map 子分组 ID。", self.audio_preview_summary_card
        )
        self.audio_preview_summary_label.setWordWrap(True)
        summary_layout.addWidget(self.audio_preview_summary_label)
        self.audio_preview_summary_card.setVisible(False)
        right_layout.addWidget(self.audio_preview_summary_card)

        self.preview_stack = QStackedWidget(right_widget)
        self.text_preview = PlainTextEdit(right_widget)
        self.text_preview.setReadOnly(True)
        self.text_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_preview.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.text_preview.setCenterOnScroll(False)
        self.text_preview.setUndoRedoEnabled(False)
        self.text_preview.verticalScrollBar().setSingleStep(18)
        self.text_preview.horizontalScrollBar().setSingleStep(18)
        self.text_preview.setPlainText("请选择左侧实体以查看原始数据。")
        self.preview_stack.addWidget(self.text_preview)

        self.audio_preview_tree = PreviewTreeView(right_widget)
        self.preview_stack.addWidget(self.audio_preview_tree)
        self.preview_stack.setCurrentWidget(self.audio_preview_tree)
        self.audio_preview_summary_card.setVisible(True)

        right_layout.addWidget(self.preview_stack, 1)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        splitter_handle = self.splitter.handle(1)
        splitter_handle.setEnabled(False)
        splitter_handle.hide()
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([1, 1])

        root_layout.addWidget(self.splitter, 1)
        self._update_selection_summary()
        self.set_smooth_scroll_enabled(False)

    def _rebuild_entity_list(self, entity_type: str) -> None:
        """刷新指定实体类型的 source model，并恢复选择状态。"""
        self._entity_lists[entity_type].set_rows(self._cached_data.get(entity_type, []))
        self._prune_entity_state(entity_type)
        self._restore_list_state(entity_type)

    def _apply_filter_to_current_list(self) -> int:
        """对当前列表应用代理过滤，并返回过滤后的可见行数。"""
        entity_type = self._current_entity_type()
        list_widget = self._entity_lists[entity_type]
        selection_model = list_widget.selectionModel()
        blockers = [QSignalBlocker(list_widget)]
        if selection_model is not None:
            blockers.append(QSignalBlocker(selection_model))
        list_widget.set_keyword(self.search_input.text())
        self._restore_list_state(entity_type)
        del blockers
        return list_widget.visible_row_count()

    def _prune_entity_state(self, entity_type: str) -> None:
        """移除已经不在当前 source model 中的选择与预览状态。"""
        available_ids = self._entity_lists[entity_type].entity_ids()
        self._selected_entity_ids[entity_type] &= available_ids
        current_preview_id = self._current_preview_ids.get(entity_type)
        if current_preview_id is not None and current_preview_id not in available_ids:
            self._current_preview_ids[entity_type] = None

    def _find_proxy_index_by_entity_id(self, entity_type: str, entity_id: str | None) -> QModelIndex:
        """在当前代理模型里按实体 ID 查找对应索引。"""
        return self._entity_lists[entity_type].find_index_by_entity_id(entity_id)

    def _restore_list_state(self, entity_type: str) -> None:
        """将页面层维护的选择和当前项同步回代理视图。"""
        list_widget = self._entity_lists[entity_type]
        selection_model = list_widget.selectionModel()
        if selection_model is None:
            return

        blockers = [QSignalBlocker(list_widget), QSignalBlocker(selection_model)]
        list_widget.restore_state(
            self._selected_entity_ids.get(entity_type, set()),
            self._current_preview_ids.get(entity_type),
        )
        del blockers

    def _sync_current_list_view(self) -> None:
        """同步当前 tab 的列表显示状态，不重建已有缓存。"""
        entity_type = self._current_entity_type()
        source_rows = self._cached_data.get(entity_type, [])
        visible_count = self._apply_filter_to_current_list()
        current_preview_id = self._current_preview_ids.get(entity_type)
        list_widget = self._current_entity_list()
        self.list_stack.setCurrentWidget(list_widget)

        if not source_rows:
            self.list_summary_label.setText("等待实体数据加载…")
            self._set_splitter_sizes_evenly()
            self._show_placeholder("当前实体数据尚未加载完成。")
            self._update_selection_summary()
            return

        if visible_count == 0:
            self.list_summary_label.setText("当前筛选结果为空。")
            self._set_splitter_sizes_evenly()
            self._show_placeholder("未找到匹配的实体，请调整筛选条件。")
            self._update_selection_summary()
            return

        self.list_summary_label.setText(f"共 {len(source_rows)} 个实体，当前显示 {visible_count} 个。")

        if current_preview_id is None:
            list_widget.setCurrentIndex(QModelIndex())
            self._set_splitter_sizes_evenly()
            self._show_placeholder("请选择左侧实体以查看原始数据。")
            self._update_selection_summary()
            return

        target_index = self._find_proxy_index_by_entity_id(entity_type, current_preview_id)
        if not target_index.isValid():
            self._show_placeholder("当前筛选结果中不包含已选实体。")
            self._update_selection_summary()
            return

        if list_widget.currentIndex() != target_index:
            list_widget.setCurrentIndex(target_index)
        else:
            self._load_preview_for_item(entity_type, target_index)
        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        champion_count = len(self._selected_entity_ids["champions"])
        map_count = len(self._selected_entity_ids["maps"])
        total_count = champion_count + map_count
        if total_count == 0:
            self.selection_status_label.setText("尚未选中实体，可使用 Ctrl / Shift 多选。")
        else:
            self.selection_status_label.setText(
                f"已选中 英雄 {champion_count} 个，地图 {map_count} 个。"
            )
        self.clear_selection_btn.setEnabled(total_count > 0)
        self.sync_selection_btn.setEnabled(total_count > 0)

    def _selected_payload(self) -> dict[str, Any]:
        champion_ids = tuple(int(entity_id) for entity_id in sorted(self._selected_entity_ids["champions"], key=int))
        map_ids = tuple(int(entity_id) for entity_id in sorted(self._selected_entity_ids["maps"], key=int))
        return {
            "source": "overview_selection",
            "champion_ids": champion_ids,
            "map_ids": map_ids,
            "summary": f"英雄 {len(champion_ids)} 个，地图 {len(map_ids)} 个",
        }

    def _sync_selected_entities(self) -> None:
        payload = self._selected_payload()
        total_count = len(payload["champion_ids"]) + len(payload["map_ids"])
        if total_count == 0:
            InfoBar.warning(
                "没有可同步的选择",
                "请先在左侧列表中选择至少一个实体。",
                parent=self.window(),
                position=InfoBarPosition.TOP,
            )
            return

        self.selection_sync_requested.emit(payload)

    def _clear_selected_entities(self) -> None:
        entity_type = self._current_entity_type()
        self._selected_entity_ids[entity_type] = set()
        self._current_preview_ids[entity_type] = None
        list_widget = self._current_entity_list()
        selection_model = list_widget.selectionModel()
        blockers = [QSignalBlocker(list_widget)]
        if selection_model is not None:
            blockers.append(QSignalBlocker(selection_model))
            selection_model.clearSelection()
            selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
        list_widget.setCurrentIndex(QModelIndex())
        del blockers
        self._sync_current_list_view()

    def _on_nav_changed(self, _key: str) -> None:
        self._sync_current_list_view()

    def _on_search_text_changed(self, _text: str) -> None:
        self._sync_current_list_view()

    def _on_current_item_changed(self, entity_type: str, current, _previous) -> None:
        if entity_type != self._current_entity_type():
            return
        self._load_preview_for_item(entity_type, current)

    def _on_entity_selection_changed(self, entity_type: str) -> None:
        list_widget = self._entity_lists[entity_type]
        self._selected_entity_ids[entity_type] = list_widget.selected_entity_ids()
        self._update_selection_summary()

    def _load_preview_for_item(self, entity_type: str, item) -> None:
        row = self._resolve_row_payload(item)
        if not row:
            self._current_preview_ids[entity_type] = None
            self._show_placeholder("请选择左侧实体以查看原始数据。")
            return

        self._current_preview_ids[entity_type] = str(row["id"])
        loader = self._ensure_loader()
        if loader is None:
            self._show_placeholder("当前配置尚未完成初始化，暂时无法读取预览内容。")
            return

        mapping_path, mapping_data, preview_content = loader.load_mapping_preview(entity_type, str(row["id"]))
        if mapping_path is None:
            self._show_placeholder(f"{row['name']} 当前还没有映射文件。")
            return

        available_audio_ids = loader.load_available_audio_ids(entity_type, str(row["id"]))
        group_label_map = self._build_preview_group_label_map(
            entity_type,
            str(row["id"]),
            mapping_data,
            loader,
        )
        self._current_mapping_path = mapping_path
        self.preview_path_edit.setText(build_preview_path_text(mapping_path))
        self.preview_path_edit.setCursorPosition(0)
        self.preview_path_edit.setToolTip(str(mapping_path))
        self.text_preview.setPlainText(preview_content or "{}")
        self._refresh_audio_preview(mapping_data, available_audio_ids, group_label_map)
        self.reveal_file_btn.setEnabled(True)

    def _resolve_row_payload(self, item_or_index: Any) -> dict[str, Any] | None:
        """从旧 item 或新模型索引中解析出统一的行数据。"""
        row: Any = None
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

    @staticmethod
    def _resolve_champion_skin_name(skin: dict[str, Any]) -> str | None:
        """从英雄皮肤结构中提取中文皮肤名。"""
        skin_names = skin.get("skinNames")
        if isinstance(skin_names, dict):
            zh_name = str(skin_names.get("zh_CN") or "").strip()
            if zh_name:
                return zh_name

        for key in ("name", "displayName"):
            value = str(skin.get(key) or "").strip()
            if value:
                return value

        return None

    def _build_preview_group_label_map(
        self,
        entity_type: str,
        entity_id: str,
        mapping_data: dict[str, Any] | None,
        loader: EntityDataLoader,
    ) -> dict[str, str]:
        """为右侧试听树构造首层分组展示文案映射。"""
        if entity_type != "champions":
            return {}
        if not isinstance(mapping_data, dict) or not isinstance(mapping_data.get("skins"), dict):
            return {}

        try:
            champion_id = int(entity_id)
        except (TypeError, ValueError):
            return {}

        champion = loader.data_reader.get_champion(champion_id)
        if not isinstance(champion, dict):
            return {}

        label_map: dict[str, str] = {}
        for skin in champion.get("skins", []):
            if not isinstance(skin, dict):
                continue

            skin_id = str(skin.get("id") or "").strip()
            if not skin_id:
                continue

            skin_name = self._resolve_champion_skin_name(skin)
            if skin_name:
                label_map[skin_id] = skin_name

        return label_map

    def _refresh_audio_preview(
        self,
        mapping_data: dict[str, Any] | None,
        available_audio_ids: set[str],
        group_label_map: dict[str, str] | None = None,
    ) -> None:
        """根据当前 mapping 数据刷新试听树。"""
        stats = collect_tree_stats(mapping_data, available_audio_ids)
        self.audio_preview_summary_label.setText(build_tree_summary_text(stats))
        model = self.audio_preview_tree.model()
        if isinstance(model, PreviewTreeModel):
            self.audio_preview_tree.collapseAll()
            model.set_preview_data(mapping_data, available_audio_ids, group_label_map)

    def _show_placeholder(self, message: str) -> None:
        self._current_mapping_path = None
        self.preview_path_edit.clear()
        self.preview_path_edit.setToolTip("")
        self.text_preview.setPlainText(message)
        model = self.audio_preview_tree.model()
        if isinstance(model, PreviewTreeModel):
            self.audio_preview_tree.collapseAll()
            model.clear_preview()
        self.audio_preview_summary_label.setText(self._audio_preview_placeholder)
        self.reveal_file_btn.setEnabled(False)

    def _set_splitter_sizes_evenly(self) -> None:
        """在页面宽度已知时将左右面板恢复到 50/50。"""
        total_width = self.splitter.width()
        if total_width <= 0:
            return

        half_width = total_width // 2
        self.splitter.setSizes([half_width, total_width - half_width])

    def _reveal_selected_mapping_file(self) -> None:
        if self._current_mapping_path is None:
            return

        target_path = self._current_mapping_path
        directory = target_path.parent

        try:
            if os.name == "nt" and target_path.exists():
                subprocess.Popen(["explorer.exe", "/select,", str(target_path)])
                return
        except OSError:
            pass

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        if not opened:
            InfoBar.warning(
                "打开目录失败",
                f"无法打开目录：{directory}",
                parent=self.window(),
                position=InfoBarPosition.TOP,
            )

    def set_smooth_scroll_enabled(self, enabled: bool) -> None:
        """根据设置应用总览页的滚动模式。"""
        for list_widget in self._entity_lists.values():
            apply_smooth_scroll_enabled(list_widget, enabled)
        apply_smooth_scroll_enabled(self.text_preview, enabled)
        apply_smooth_scroll_enabled(self.audio_preview_tree, enabled)
