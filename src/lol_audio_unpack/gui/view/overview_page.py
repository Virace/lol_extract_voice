"""实体总览页面，负责展示实体状态并预留右侧资源预览区。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger
from PySide6.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QSignalBlocker,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QTextOption
from PySide6.QtWidgets import (
    QFileDialog,
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
    Action,
    BodyLabel,
    CaptionLabel,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MenuAnimationType,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SearchLineEdit,
    SegmentedWidget,
    StrongBodyLabel,
    SubtitleLabel,
    Theme,
    TransparentToolButton,
    qconfig,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.app.special_content import is_special_content_supported
from lol_audio_unpack.gui.common import apply_smooth_scroll_enabled
from lol_audio_unpack.gui.common.page_style import apply_page_content_margins
from lol_audio_unpack.gui.common.styles import build_fluent_panel_frame_theme_pair
from lol_audio_unpack.gui.components.overview_entity_list import OVERVIEW_ROW_ROLE, OverviewEntityListView
from lol_audio_unpack.gui.components.preview_tree import (
    build_tree_summary_text,
    collect_tree_stats,
    extract_preview_modifiers,
    filter_preview_mapping_data,
)
from lol_audio_unpack.gui.components.special_content_tree import SpecialContentTreeView
from lol_audio_unpack.gui.controllers import (
    OverviewPreviewController,
    PreviewPlaybackController,
)
from lol_audio_unpack.gui.controllers.contracts import OverviewSelectionSyncRequest
from lol_audio_unpack.gui.controllers.entity_data_store import EntityDataStore
from lol_audio_unpack.gui.controllers.overview_preview import (
    ALL_AUDIO_PREVIEW_MODE,
    EVENT_PREVIEW_MODE,
    RAW_PREVIEW_MODE,
)
from lol_audio_unpack.gui.controllers.preview_playback import PreviewPlaybackState
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader
from lol_audio_unpack.gui.service.preview_export import resolve_wav_path, transcode_wav
from lol_audio_unpack.gui.theme import get_accent_text_color_pair
from lol_audio_unpack.gui.view.overview.audio_preview_panel import OverviewAudioPreviewPanel
from lol_audio_unpack.gui.view.overview.entity_list_panel import OverviewEntityListPanel
from lol_audio_unpack.gui.view.overview.preview_panel import (
    DEFAULT_PREVIEW_PLACEHOLDER_TEXT,
    OverviewPreviewPanel,
)

DEFAULT_PREVIEW_AUDIO_VOLUME_PERCENT = 10
DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY = "default"


def build_preview_path_text(resource_path: Path | None) -> str:
    """构造右侧预览区域顶部路径文本。

    Args:
        resource_path: 当前模式对应的资源路径。

    Returns:
        存在资源路径时返回完整路径，否则返回空字符串。
    """
    if resource_path is None:
        return ""
    return str(resource_path)


def create_preview_path_edit(parent: QWidget | None = None) -> LineEdit:
    """创建跟随 Fluent 主题的预览路径输入框。"""
    line_edit = LineEdit(parent)
    line_edit.setAccessibleName("预览资源路径")
    line_edit.setReadOnly(True)
    line_edit.setClearButtonEnabled(False)
    line_edit.setPlaceholderText(DEFAULT_PREVIEW_PLACEHOLDER_TEXT)
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
        self._entity_data_store = EntityDataStore(entity_types=("champions", "maps", "special"))
        self._preview_controller = OverviewPreviewController()
        self._selected_entity_ids: dict[str, set[str]] = {"champions": set(), "maps": set(), "special": set()}
        self._current_preview_ids: dict[str, str | None] = {"champions": None, "maps": None, "special": None}
        self._current_preview_entity_type: str | None = None
        self._current_preview_entity_id: str | None = None
        self._current_mapping_path: Path | None = None
        self._current_audio_preview_audio_id: str | None = None
        self._current_audio_preview_path: Path | None = None
        self._current_audio_preview_progress = 0.0
        self._current_audio_preview_is_playing = False
        self._current_audio_preview_is_paused = False
        self._current_preview_mapping_data: dict[str, Any] | None = None
        self._current_preview_group_label_map: dict[str, str] = {}
        self._current_audio_refs: tuple[AudioRef, ...] = ()
        self._current_audio_roots: tuple[Path, ...] = ()
        self._selected_audio_refs: dict[str, AudioRef | None] = {
            EVENT_PREVIEW_MODE: None,
            ALL_AUDIO_PREVIEW_MODE: None,
        }
        self._current_mapping_notice: str | None = None
        self._audio_preview_placeholder = DEFAULT_PREVIEW_PLACEHOLDER_TEXT
        self._active_preview_mode = EVENT_PREVIEW_MODE
        self._event_preview_summary = self._audio_preview_placeholder
        self._all_audio_preview_summary = self._audio_preview_placeholder
        self._preview_search_keywords = {
            EVENT_PREVIEW_MODE: "",
            ALL_AUDIO_PREVIEW_MODE: "",
        }
        self._preview_audio_volume_percent = DEFAULT_PREVIEW_AUDIO_VOLUME_PERCENT
        self._preview_audio_output_device_key = DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY
        self._entity_lists: dict[str, OverviewEntityListView | SpecialContentTreeView] = {}
        self._build_ui()
        self._preview_playback_controller = PreviewPlaybackController(parent=self)
        self._preview_playback_controller.playback_state_changed.connect(self._apply_audio_preview_playback_state)
        self._preview_playback_controller.playback_error.connect(self._show_audio_preview_playback_error)
        self._setup_connections()
        self.destroyed.connect(self._disconnect_theme_refresh_listeners)
        self.destroyed.connect(self._preview_playback_controller.shutdown)

    def showEvent(self, event):
        """页面首次展示时同步当前缓存。"""
        super().showEvent(event)
        if self._current_preview_ids[self._current_entity_type()] is None:
            self._set_splitter_sizes_evenly()
        self._sync_current_list_view()

    def resizeEvent(self, event) -> None:
        """窗口尺寸变化时，重新收敛左右面板宽度。"""
        super().resizeEvent(event)
        self._set_splitter_sizes_evenly()

    def set_gui_config(self, cfg) -> None:
        """注入 GUI 配置。"""
        self.gui_config = cfg
        fallback_enabled = bool(getattr(cfg, "smooth_scroll_enabled", False))
        self.set_smooth_scroll_enabled(bool(getattr(cfg, "widget_smooth_scroll_enabled", fallback_enabled)))
        self.set_preview_audio_volume(
            int(getattr(cfg, "preview_audio_volume_percent", DEFAULT_PREVIEW_AUDIO_VOLUME_PERCENT))
        )
        self.set_preview_audio_output_device(
            str(getattr(cfg, "preview_audio_output_device_key", DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY))
        )

    def set_preview_audio_volume(self, value: int) -> None:
        """缓存试听音量设置并同步到底层播放器。"""
        self._preview_audio_volume_percent = int(value)
        self._preview_playback_controller.set_volume_percent(self._preview_audio_volume_percent)

    def set_preview_audio_output_device(self, value: str) -> None:
        """缓存试听输出设备设置并同步到播放控制器。"""
        self._preview_audio_output_device_key = str(value or "").strip() or DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY
        self._preview_playback_controller.set_output_device_key(self._preview_audio_output_device_key)

    def set_app_context(self, app_context) -> None:
        """注入应用上下文。

        Args:
            app_context: 当前应用上下文；为 ``None`` 时仅保留占位提示。
        """
        self._app_context = app_context
        self._loader = None
        if app_context is None:
            self.entityListPanel.set_special_interaction_enabled(False)
            self.entityListPanel.set_special_availability_message(None)
            self._update_catalog_subtitle()
            self._show_placeholder("当前配置尚未完成初始化，暂时无法读取预览内容。")
            return

        special_supported = is_special_content_supported(app_context.config.source_mode)
        self.entityListPanel.set_special_interaction_enabled(special_supported)
        self.entityListPanel.set_special_availability_message(
            None if special_supported else "特殊内容仅支持本地客户端资源。"
        )
        if not special_supported:
            self._selected_entity_ids["special"] = set()
            self._current_preview_ids["special"] = None
        self._update_catalog_subtitle()

        current_index = self._current_entity_list().currentIndex()
        if current_index.isValid():
            self._load_preview_for_item(self._current_entity_type(), current_index)
        else:
            self._sync_current_list_view()

    def set_entity_data(self, entity_type: str, data: list[dict[str, Any]]) -> None:
        """更新页面缓存的实体数据。"""
        if not self._entity_data_store.set_rows(entity_type, data):
            return

        self._rebuild_entity_list(entity_type)
        if self._current_entity_type() == entity_type:
            self._sync_current_list_view()
        else:
            self._update_selection_summary()

    def update_entity_rows(self, entity_type: str, rows: list[dict[str, Any]]) -> None:
        """按实体 ID 增量更新页面缓存并刷新当前列表。"""
        merged_rows = self._entity_data_store.update_rows(entity_type, rows)
        if merged_rows is None:
            return

        self.set_entity_data(entity_type, merged_rows)

    def clear_data(self) -> None:
        """清空页面缓存并恢复占位内容。"""
        self._entity_data_store.clear()
        self.entityListPanel.set_special_catalog_notice(None)
        self._selected_entity_ids = {"champions": set(), "maps": set(), "special": set()}
        self._current_preview_ids = {"champions": None, "maps": None, "special": None}
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
        self._update_selection_summary()
        self._show_placeholder("当前暂无可预览的内容。")

    def _setup_connections(self) -> None:
        self.nav_pivot.currentItemChanged.connect(self._on_nav_changed)
        self.preview_mode_pivot.currentItemChanged.connect(self._on_preview_mode_changed)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.previewPanel.preview_search_input.textChanged.connect(self._on_preview_search_text_changed)
        self.sync_selection_btn.clicked.connect(self._sync_selected_entities)
        self.clear_selection_btn.clicked.connect(self._clear_selected_entities)
        self.reveal_file_btn.clicked.connect(self._reveal_current_preview_target)
        self.audio_preview_tree.audio_ref_toggle_requested.connect(self._on_audio_preview_toggle_requested)
        self.audio_preview_tree.audio_context_menu_requested.connect(self._show_audio_menu)
        self.audio_preview_tree.audio_ref_selected.connect(self._on_audio_ref_selected)
        self.audioPreviewPanel.audio_list.audio_ref_toggle_requested.connect(self._on_audio_preview_toggle_requested)
        self.audioPreviewPanel.audio_list.audio_context_menu_requested.connect(self._show_audio_menu)
        self.audioPreviewPanel.audio_list.audio_ref_selected.connect(self._on_audio_ref_selected)
        qconfig.themeChanged.connect(self._refresh_theme_styles)
        qconfig.themeColorChanged.connect(self._refresh_theme_styles)

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

    def _disconnect_theme_refresh_listeners(self, *_args: object) -> None:
        """断开实体总览页注册的全局主题监听。"""
        for signal, callback in (
            (qconfig.themeChanged, self._refresh_theme_styles),
            (qconfig.themeColorChanged, self._refresh_theme_styles),
        ):
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError):
                pass

    def _refresh_entity_list_theme(self) -> None:
        """在主题或主题色变化后刷新列表绘制。"""
        for list_widget in self._entity_lists.values():
            try:
                list_widget.refresh_theme()
            except RuntimeError:
                continue

    def _refresh_panel_shell_theme(self) -> None:
        """刷新总览页轻量信息壳层的主题样式。"""
        light_qss, dark_qss = build_fluent_panel_frame_theme_pair("QFrame#OverviewSelectionBar")
        self.selection_bar.setStyleSheet(dark_qss if qconfig.theme == Theme.DARK else light_qss)

        light_qss, dark_qss = build_fluent_panel_frame_theme_pair("QFrame#AudioPreviewSummaryCard")
        self.audio_preview_summary_card.setStyleSheet(dark_qss if qconfig.theme == Theme.DARK else light_qss)
        self.previewPanel.refresh_theme()

    def _refresh_theme_styles(self, *_args: object) -> None:
        """统一刷新总览页当前主题相关样式。"""
        accent_light, accent_dark = get_accent_text_color_pair()
        self.subtitle_label.setTextColor(accent_light, accent_dark)
        self._refresh_entity_list_theme()
        self._refresh_panel_shell_theme()

    def _on_preview_mode_changed(self, mode_key: str) -> None:
        """切换右侧事件、全部音频与原始数据视图。"""
        previous_mode = self._active_preview_mode
        if previous_mode in self._preview_search_keywords:
            self._preview_search_keywords[previous_mode] = self.previewPanel.preview_search_input.text()
        self._active_preview_mode = mode_key
        self._apply_preview_mode(mode_key)

    def _apply_preview_mode(self, mode_key: str) -> None:
        """应用模式壳层状态，不重建另一种预览的模型或滚动位置。"""
        self.previewPanel.set_preview_mode(mode_key)

        search = self.previewPanel.preview_search_input
        if mode_key == RAW_PREVIEW_MODE:
            blocker = QSignalBlocker(search)
            search.clear()
            del blocker
            search.setEnabled(False)
            search.setPlaceholderText("原始数据暂不支持搜索")
        else:
            search.setEnabled(True)
            search.setPlaceholderText(
                "搜索事件、类型或音频 ID" if mode_key == EVENT_PREVIEW_MODE else "搜索 WEM ID、相对路径或音频类型"
            )
            keyword = self._preview_search_keywords.get(mode_key, "")
            blocker = QSignalBlocker(search)
            search.setText(keyword)
            del blocker

        if mode_key == EVENT_PREVIEW_MODE:
            self.audioPreviewPanel.set_summary_text(self._event_preview_summary)
        elif mode_key == ALL_AUDIO_PREVIEW_MODE:
            self.audioPreviewPanel.set_summary_text(self._all_audio_preview_summary)
        self._sync_preview_path()

    def _current_entity_type(self) -> str:
        return self.nav_pivot.currentRouteKey() or "champions"

    def _current_entity_list(self) -> OverviewEntityListView | SpecialContentTreeView:
        return self._entity_lists[self._current_entity_type()]

    def _ensure_loader(self) -> EntityDataLoader | None:
        if self._loader is None and self._app_context is not None:
            self._loader = EntityDataLoader(self._app_context)
        return self._loader

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        apply_page_content_margins(root_layout)
        root_layout.setSpacing(16)

        header_layout = QHBoxLayout()
        title_label = SubtitleLabel("实体总览", self)
        self.subtitle_label = CaptionLabel("查看英雄、地图与特殊内容状态，选好后可直接发送到执行中心。", self)
        self.subtitle_label.setWordWrap(False)

        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        title_column.addWidget(title_label)
        title_column.addWidget(self.subtitle_label)

        header_layout.addLayout(title_column)
        header_layout.addStretch(1)
        root_layout.addLayout(header_layout)

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setObjectName("OverviewSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(0)

        self.entityListPanel = OverviewEntityListPanel(self.splitter)
        self.nav_pivot = self.entityListPanel.nav_pivot
        self.search_input = self.entityListPanel.search_input
        self.selection_status_label = self.entityListPanel.selection_status_label
        self.list_stack = self.entityListPanel.list_stack
        self.selection_bar = self.entityListPanel.selection_bar
        self.clear_selection_btn = self.entityListPanel.clear_selection_btn
        self.sync_selection_btn = self.entityListPanel.sync_selection_btn
        self._entity_lists = self.entityListPanel.entity_lists

        self.previewPanel = OverviewPreviewPanel(
            audio_summary_placeholder=self._audio_preview_placeholder,
            parent=self.splitter,
        )
        self.preview_path_edit = self.previewPanel.preview_path_edit
        self.reveal_file_btn = self.previewPanel.reveal_file_btn
        self.preview_mode_pivot = self.previewPanel.preview_mode_pivot
        self.preview_stack = self.previewPanel.preview_stack
        self.text_preview = self.previewPanel.text_preview
        self.audioPreviewPanel = self.previewPanel.audio_preview_panel
        self.audio_preview_summary_card = self.audioPreviewPanel.summary_card
        self.audio_preview_summary_label = self.audioPreviewPanel.summary_label
        self.audio_preview_tree = self.audioPreviewPanel.audio_preview_tree
        self.audio_list = self.audioPreviewPanel.audio_list
        QWidget.setTabOrder(self.nav_pivot, self.search_input)
        QWidget.setTabOrder(self.search_input, self.preview_mode_pivot)
        QWidget.setTabOrder(self.preview_mode_pivot, self.previewPanel.preview_search_input)

        self.splitter.addWidget(self.entityListPanel)
        self.splitter.addWidget(self.previewPanel)
        splitter_handle = self.splitter.handle(1)
        splitter_handle.setEnabled(False)
        splitter_handle.hide()
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([1, 1])

        root_layout.addWidget(self.splitter, 1)
        self._update_selection_summary()
        self.set_smooth_scroll_enabled(False)
        self._refresh_panel_shell_theme()

    def _rebuild_entity_list(self, entity_type: str) -> None:
        """刷新指定实体类型的 source model，并恢复选择状态。"""
        self.entityListPanel.set_rows(entity_type, self._entity_data_store.rows_for(entity_type))
        self._prune_entity_state(entity_type)
        self.entityListPanel.apply_keyword_and_restore(
            entity_type=entity_type,
            keyword=self.search_input.text(),
            selected_ids=self._selected_entity_ids.get(entity_type, set()),
            current_entity_id=self._current_preview_ids.get(entity_type),
        )

    def _apply_filter_to_current_list(self) -> int:
        """对当前列表应用代理过滤，并返回过滤后的可见行数。"""
        entity_type = self._current_entity_type()
        return self.entityListPanel.apply_keyword_and_restore(
            entity_type=entity_type,
            keyword=self.search_input.text(),
            selected_ids=self._selected_entity_ids.get(entity_type, set()),
            current_entity_id=self._current_preview_ids.get(entity_type),
        )

    def _prune_entity_state(self, entity_type: str) -> None:
        """移除已经不在当前 source model 中的选择与预览状态。"""
        available_ids = self._entity_lists[entity_type].entity_ids()
        self._selected_entity_ids[entity_type] &= available_ids
        current_preview_id = self._current_preview_ids.get(entity_type)
        if current_preview_id is not None and current_preview_id not in available_ids:
            self._current_preview_ids[entity_type] = None

    def _sync_current_list_view(self) -> None:
        """同步当前 tab 的列表显示状态，不重建已有缓存。"""
        entity_type = self._current_entity_type()
        source_rows = self._entity_data_store.rows_for(entity_type)
        visible_count = self._apply_filter_to_current_list()
        current_preview_id = self._current_preview_ids.get(entity_type)
        self.entityListPanel.set_current_entity_type(entity_type)
        list_widget = self._current_entity_list()

        if entity_type == "special" and self._special_content_is_remote_unsupported():
            self.entityListPanel.set_special_catalog_notice(None)
            self._set_splitter_sizes_evenly()
            self._show_placeholder("特殊内容仅支持本地客户端资源。")
            self._update_selection_summary()
            return

        if entity_type == "special" and self._app_context is None:
            self.entityListPanel.set_special_catalog_notice(None)
            self._set_splitter_sizes_evenly()
            self._show_placeholder("当前特殊内容数据尚未加载完成。")
            self._update_selection_summary()
            return

        if not source_rows:
            if entity_type == "special":
                self.entityListPanel.set_special_catalog_notice(None)
            self._set_splitter_sizes_evenly()
            placeholders = {
                "champions": "当前英雄数据尚未加载完成。",
                "maps": "当前地图数据尚未加载完成。",
                "special": "当前版本未发现特殊内容",
            }
            placeholder = placeholders.get(entity_type, "当前实体数据尚未加载完成。")
            self._show_placeholder(placeholder)
            self._update_selection_summary()
            return

        if entity_type == "special":
            self.entityListPanel.set_special_catalog_notice(
                "特殊内容资源尚未准备，需要更新实体数据后才能显示完整状态。"
                if all(
                    str(row.get("audio", "")) == "未准备" and str(row.get("mapping", "")) == "未准备"
                    for row in source_rows
                )
                else None
            )

        if visible_count == 0:
            self._set_splitter_sizes_evenly()
            self._show_placeholder("未找到匹配的实体，请调整筛选条件。")
            self._update_selection_summary()
            return

        if current_preview_id is None:
            list_widget.setCurrentIndex(QModelIndex())
            self._set_splitter_sizes_evenly()
            self._show_placeholder(DEFAULT_PREVIEW_PLACEHOLDER_TEXT)
            self._update_selection_summary()
            return

        target_index = self.entityListPanel.find_index_by_entity_id(entity_type, current_preview_id)
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
        special_count = len(self._selected_entity_ids["special"])
        self.entityListPanel.set_selection_counts(
            champion_count=champion_count,
            map_count=map_count,
            special_count=special_count,
        )

    def _sync_selected_entities(self) -> None:
        if self._selected_entity_ids["special"] and self._special_content_is_remote_unsupported():
            InfoBar.warning(
                "无法同步特殊内容",
                "特殊内容仅支持本地客户端资源。",
                parent=self.window(),
                position=InfoBarPosition.TOP,
            )
            return
        payload = self.entityListPanel.build_selection_sync_request(
            selected_champion_ids=self._selected_entity_ids["champions"],
            selected_map_ids=self._selected_entity_ids["maps"],
            selected_special_targets=self._selected_entity_ids["special"],
            special_target_names={
                str(row.get("key", "")): str(row.get("display_name", ""))
                for row in self._entity_data_store.rows_for("special")
            },
        )
        total_count = len(payload.champion_ids) + len(payload.map_ids) + len(payload.special_targets)
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
        for entity_type in self._selected_entity_ids:
            self._selected_entity_ids[entity_type] = set()
            self._current_preview_ids[entity_type] = None
            self.entityListPanel.clear_selection(entity_type)
        self._sync_current_list_view()

    def _on_nav_changed(self, _key: str) -> None:
        self._update_catalog_subtitle()
        self._update_catalog_search_placeholder()
        self._sync_current_list_view()

    def _on_search_text_changed(self, _text: str) -> None:
        self._sync_current_list_view()

    def _on_preview_search_text_changed(self, _text: str) -> None:
        mode_key = self.preview_mode_pivot.currentRouteKey() or EVENT_PREVIEW_MODE
        if mode_key not in self._preview_search_keywords:
            return
        self._preview_search_keywords[mode_key] = self.previewPanel.preview_search_input.text()
        self._refresh_current_preview_mode()

    def _on_current_item_changed(self, entity_type: str, current, _previous) -> None:
        if entity_type != self._current_entity_type():
            return
        self._load_preview_for_item(entity_type, current)

    def _on_entity_selection_changed(self, entity_type: str) -> None:
        self._selected_entity_ids[entity_type] = self.entityListPanel.selected_entity_ids(entity_type)
        self._update_selection_summary()

    def _load_preview_for_item(self, entity_type: str, item) -> None:
        row = self.entityListPanel.resolve_row_payload(item)
        if not row:
            self._current_preview_ids[entity_type] = None
            self._show_placeholder(DEFAULT_PREVIEW_PLACEHOLDER_TEXT)
            return

        preview_state_id = row.get("key", row["id"]) if entity_type == "special" else row["id"]
        self._current_preview_ids[entity_type] = str(preview_state_id)
        preview_entity_type = str(row.get("entity_type", entity_type))
        self._current_preview_entity_type = preview_entity_type
        self._current_preview_entity_id = str(row["id"])
        loader = self._ensure_loader()
        preview_result = self._preview_controller.load_preview(
            entity_type=preview_entity_type,
            entity_id=str(row["id"]),
            entity_name=str(row.get("display_name", row["name"])),
            loader=loader,
        )
        if preview_result.placeholder_message is not None:
            self._show_placeholder(preview_result.placeholder_message)
            return

        self._current_mapping_path = preview_result.mapping_path
        self.text_preview.setPlainText(preview_result.preview_content)
        self._clear_audio_preview_request()
        self._current_preview_mapping_data = preview_result.mapping_data
        self._current_preview_group_label_map = dict(preview_result.group_label_map)
        self._current_audio_refs = preview_result.audio_refs
        self._current_audio_roots = preview_result.audio_roots
        self._selected_audio_refs = {
            EVENT_PREVIEW_MODE: None,
            ALL_AUDIO_PREVIEW_MODE: None,
        }
        self._current_mapping_notice = preview_result.mapping_notice
        self._preview_search_keywords = {
            EVENT_PREVIEW_MODE: "",
            ALL_AUDIO_PREVIEW_MODE: "",
        }
        modifiers = extract_preview_modifiers(preview_result.mapping_data)
        logger.debug(
            "[总览预览] entity_type={} entity_id={} prefixes={} suffixes={} audio_types={}",
            entity_type,
            row["id"],
            list(modifiers.prefixes),
            list(modifiers.suffixes),
            list(modifiers.audio_types),
        )
        self._refresh_audio_preview_tree()
        self.audioPreviewPanel.set_audio_refs(self._current_audio_refs, summary_text="")
        self._refresh_all_audio_preview()
        self.previewPanel.show_current_preview()
        self._sync_audio_preview_playback_state()
        pivot_blocker = QSignalBlocker(self.preview_mode_pivot)
        self.preview_mode_pivot.setCurrentItem(preview_result.default_preview_mode)
        del pivot_blocker
        self._active_preview_mode = preview_result.default_preview_mode
        self._apply_preview_mode(preview_result.default_preview_mode)

    def _on_audio_preview_toggle_requested(self, audio_ref: AudioRef) -> None:
        """响应路径级试听项点击并触发精确 WEM 播放控制。"""
        self._set_selected_audio_ref(audio_ref)
        self._sync_preview_path()
        result = self._preview_controller.resolve_audio_preview_toggle(
            requested_audio=audio_ref,
            current_audio_path=self._current_audio_preview_path,
        )
        if result is None:
            return
        if result.warning_message is not None:
            InfoBar.warning(
                "找不到试听音频",
                result.warning_message,
                parent=self.window(),
                position=InfoBarPosition.TOP,
            )
            return

        if result.audio_id is None or result.audio_path is None:
            self._clear_audio_preview_request()
            return

        self._preview_playback_controller.play(
            audio_id=result.audio_id,
            audio_path=result.audio_path,
        )

    def _on_audio_ref_selected(self, audio_ref: AudioRef) -> None:
        """让全部音频模式路径栏跟随用户实际选中的 WEM。"""
        self._set_selected_audio_ref(audio_ref)
        self._sync_preview_path()

    def _set_selected_audio_ref(self, audio_ref: AudioRef) -> None:
        """按当前试听模式保存用户选中的精确路径引用。"""
        mode_key = self.preview_mode_pivot.currentRouteKey() or self._active_preview_mode
        if mode_key in self._selected_audio_refs:
            self._selected_audio_refs[mode_key] = audio_ref

    @staticmethod
    def _audio_menu_wem_path(audio_ref: AudioRef) -> Path:
        """返回右键菜单目标的已验证精确 WEM 路径。"""
        return audio_ref.path

    def _show_audio_menu(self, audio_ref: AudioRef, global_pos: QPoint) -> None:
        """显示事件树与全部音频共用的路径级操作菜单。"""
        self._set_selected_audio_ref(audio_ref)
        self._sync_preview_path()
        wem_path = self._audio_menu_wem_path(audio_ref)
        menu = RoundMenu(parent=self)

        save_action = Action("另存为 WAV...", menu)
        save_action.triggered.connect(lambda: self._save_audio_wav(audio_ref.wem_id, wem_path))
        menu.addAction(save_action)

        reveal_wem_action = Action("打开 WEM 所在位置", menu)
        reveal_wem_action.triggered.connect(lambda: self._reveal_wem(wem_path))
        menu.addAction(reveal_wem_action)

        reveal_wav_action = Action("转码并打开 WAV 所在位置", menu)
        reveal_wav_action.triggered.connect(lambda: self._reveal_wav(wem_path))
        menu.addAction(reveal_wav_action)

        menu.exec(global_pos, aniType=MenuAnimationType.DROP_DOWN)

    def _wav_format(self) -> str:
        """返回右键单文件转码使用的 WAV 格式。"""
        return str(getattr(self.gui_config, "wav_format", "pcm16") or "pcm16")

    def _save_audio_wav(self, audio_id: str, wem_path: Path) -> None:
        """把当前试听音频另存为用户选择的 WAV 文件。"""
        output_text, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "另存为 WAV",
            f"{audio_id}.wav",
            "WAV 音频 (*.wav);;所有文件 (*)",
        )
        if not output_text:
            return

        output = Path(output_text)
        if output.suffix.lower() != ".wav":
            output = output.with_suffix(".wav")

        try:
            transcode_wav(wem_path, output, wav_format=self._wav_format())
        except Exception as exc:  # noqa: BLE001
            InfoBar.warning(
                "另存 WAV 失败",
                f"{type(exc).__name__}: {exc}",
                parent=self.window(),
                position=InfoBarPosition.TOP,
            )
            return

        InfoBar.success(
            "已保存 WAV",
            str(output),
            parent=self.window(),
            position=InfoBarPosition.TOP,
        )

    def _reveal_wem(self, wem_path: Path) -> None:
        """打开当前试听 WEM 所在位置。"""
        if self._reveal_file_path(wem_path):
            return
        InfoBar.warning(
            "打开目录失败",
            f"无法打开目录：{wem_path.parent}",
            parent=self.window(),
            position=InfoBarPosition.TOP,
        )

    def _reveal_wav(self, wem_path: Path) -> None:
        """转码当前试听音频到默认 WAV 镜像路径并定位文件。"""
        loader = self._ensure_loader()
        if self._app_context is None or loader is None:
            return

        version = loader.data_reader.version
        audio_root = Path(self._app_context.paths.audio_path) / version
        wav_root = Path(self._app_context.paths.wav_path) / version
        try:
            wav_path = resolve_wav_path(wem_path, audio_root=audio_root, wav_root=wav_root)
            if not wav_path.exists():
                transcode_wav(wem_path, wav_path, wav_format=self._wav_format())
        except Exception as exc:  # noqa: BLE001
            InfoBar.warning(
                "转码 WAV 失败",
                f"{type(exc).__name__}: {exc}",
                parent=self.window(),
                position=InfoBarPosition.TOP,
            )
            return

        if not self._reveal_file_path(wav_path):
            InfoBar.warning(
                "打开目录失败",
                f"无法打开目录：{wav_path.parent}",
                parent=self.window(),
                position=InfoBarPosition.TOP,
            )

    def _apply_audio_preview_playback_state(self, state: PreviewPlaybackState) -> None:
        """同步播放控制器发出的最新试听状态。"""
        self._current_audio_preview_audio_id = state.audio_id
        self._current_audio_preview_path = state.audio_path
        self._current_audio_preview_progress = state.progress
        self._current_audio_preview_is_playing = state.is_playing
        self._current_audio_preview_is_paused = state.is_paused
        self._sync_audio_preview_playback_state()

    def _show_audio_preview_playback_error(self, message: str) -> None:
        """显示试听播放链路的用户可见错误。"""
        InfoBar.warning(
            "试听播放失败",
            message,
            parent=self.window(),
            position=InfoBarPosition.TOP,
        )

    def _sync_audio_preview_playback_state(self) -> None:
        """把当前缓存的试听状态同步到两种路径级试听视图。"""
        self.audioPreviewPanel.set_playback_state(
            self._current_audio_preview_path,
            progress=self._current_audio_preview_progress,
            is_playing=self._current_audio_preview_is_playing,
            is_paused=self._current_audio_preview_is_paused,
        )

    def _clear_audio_preview_request(self) -> None:
        """清空当前试听请求并停止活跃中的播放器。"""
        self._preview_playback_controller.stop()
        self._apply_audio_preview_playback_state(
            PreviewPlaybackState(
                audio_id=None,
                audio_path=None,
                progress=0.0,
                is_playing=False,
                is_paused=False,
            )
        )

    def _show_placeholder(self, message: str) -> None:
        self._current_mapping_path = None
        self._current_preview_entity_type = None
        self._current_preview_entity_id = None
        self._current_preview_mapping_data = None
        self._current_preview_group_label_map = {}
        self._current_audio_refs = ()
        self._current_audio_roots = ()
        self._selected_audio_refs = {
            EVENT_PREVIEW_MODE: None,
            ALL_AUDIO_PREVIEW_MODE: None,
        }
        self._current_mapping_notice = None
        self._event_preview_summary = self._audio_preview_placeholder
        self._all_audio_preview_summary = self._audio_preview_placeholder
        self.previewPanel.show_placeholder(message)
        self._clear_audio_preview_request()
        self._sync_audio_preview_playback_state()

    def _refresh_audio_preview_tree(self) -> None:
        """根据当前搜索状态刷新右侧事件树。"""
        keyword = self._preview_search_keywords[EVENT_PREVIEW_MODE]
        filter_result = filter_preview_mapping_data(self._current_preview_mapping_data, keyword)
        stats = collect_tree_stats(filter_result.mapping_data, self._current_audio_refs)
        summary_text = build_tree_summary_text(stats)
        if self._current_mapping_notice:
            summary_text = f"{self._current_mapping_notice} · {summary_text}"
        if filter_result.is_active:
            summary_text = (
                f"{summary_text} · 匹配事件 {filter_result.matched_event_count} · "
                f"匹配 ID {filter_result.matched_audio_id_count}"
            )
        self._event_preview_summary = summary_text

        self.audioPreviewPanel.set_preview_data(
            mapping_data=filter_result.mapping_data,
            audio_refs=self._current_audio_refs,
            group_label_map=self._current_preview_group_label_map,
            summary_text=summary_text,
        )
        if filter_result.is_active:
            self.audio_preview_tree.expandAll()

    def _refresh_all_audio_preview(self) -> None:
        """根据当前搜索状态刷新全部音频模型与摘要。"""
        keyword = self._preview_search_keywords[ALL_AUDIO_PREVIEW_MODE]
        self.audioPreviewPanel.set_audio_keyword(keyword)
        matched_count = self.audio_list.model().rowCount()
        total_count = len(self._current_audio_refs)
        summary_text = f"全部音频 {total_count} 个 WEM"
        if keyword:
            summary_text = f"{summary_text} · 匹配 {matched_count} 个"
        if total_count == 0:
            summary_text = "暂无已解包音频"
        if self._current_mapping_notice:
            summary_text = f"{self._current_mapping_notice} · {summary_text}"
        self._all_audio_preview_summary = summary_text
        self.audioPreviewPanel.set_summary_text(summary_text)

    def _refresh_current_preview_mode(self) -> None:
        """只刷新当前模式所需的筛选模型，避免切换时重置另一视图。"""
        mode_key = self.preview_mode_pivot.currentRouteKey() or EVENT_PREVIEW_MODE
        if mode_key == EVENT_PREVIEW_MODE:
            self._refresh_audio_preview_tree()
        elif mode_key == ALL_AUDIO_PREVIEW_MODE:
            self._refresh_all_audio_preview()

    def _set_splitter_sizes_evenly(self) -> None:
        """在页面宽度已知时将左右面板收敛到更适合缩放的宽度比例。"""
        total_width = self.splitter.width()
        if total_width <= 0:
            return

        left_min_width = 280
        right_min_width = 190
        left_preferred_width = min(max(total_width // 2, left_min_width), 580)
        max_left_width = max(total_width - right_min_width, left_min_width)
        left_width = min(left_preferred_width, max_left_width)
        left_width = max(left_width, min(left_min_width, total_width))
        right_width = max(total_width - left_width, 0)
        self.splitter.setSizes([left_width, right_width])

    def _special_content_supported(self) -> bool:
        """返回当前上下文是否允许选择并执行特殊内容。"""
        return self._app_context is not None and is_special_content_supported(self._app_context.config.source_mode)

    def _special_content_is_remote_unsupported(self) -> bool:
        """判断当前已初始化上下文是否明确禁止特殊内容。"""
        return self._app_context is not None and not self._special_content_supported()

    def _update_catalog_subtitle(self) -> None:
        """按当前一级目录更新总览说明，避免隐藏特殊内容可用性边界。"""
        entity_type = self._current_entity_type()
        if entity_type == "special" and self._special_content_is_remote_unsupported():
            self.subtitle_label.setText("特殊内容仅支持本地客户端资源。")
            return
        if entity_type == "special" and self._app_context is None:
            self.subtitle_label.setText("正在准备特殊内容数据。")
            return
        labels = {
            "champions": "查看英雄状态，选好后可直接发送到执行中心。",
            "maps": "查看地图状态，选好后可直接发送到执行中心。",
            "special": "查看本地客户端支持的特殊内容，选好后可直接发送到执行中心。",
        }
        self.subtitle_label.setText(labels.get(entity_type, "查看实体状态，选好后可直接发送到执行中心。"))

    def _update_catalog_search_placeholder(self) -> None:
        """按当前目录收窄搜索提示，说明各目录实际可检索字段。"""
        placeholders = {
            "champions": "搜索英雄、别名或 ID",
            "maps": "搜索地图、别名或 ID",
            "special": "搜索模式、英雄、别名或资源包",
        }
        self.search_input.setPlaceholderText(placeholders.get(self._current_entity_type(), "搜索实体名称或 ID"))

    def _resolve_preview_target(self) -> Path | None:
        """按当前预览方式返回可安全打开的单一资源目标。"""
        mode_key = self.preview_mode_pivot.currentRouteKey() or EVENT_PREVIEW_MODE
        if mode_key in {EVENT_PREVIEW_MODE, RAW_PREVIEW_MODE}:
            return self._current_mapping_path
        selected_ref = self._selected_audio_refs[ALL_AUDIO_PREVIEW_MODE]
        if selected_ref is not None:
            return selected_ref.path
        if len(self._current_audio_roots) == 1:
            return self._current_audio_roots[0]
        return None

    def _sync_preview_path(self) -> None:
        """按当前模式更新路径栏、打开目标与工具提示。"""
        mode_key = self.preview_mode_pivot.currentRouteKey() or EVENT_PREVIEW_MODE
        target_path = self._resolve_preview_target()
        if target_path is not None:
            self.previewPanel.set_preview_path(build_preview_path_text(target_path))
            self.preview_path_edit.setCursorPosition(0)
            if mode_key == ALL_AUDIO_PREVIEW_MODE:
                self.reveal_file_btn.setToolTip("打开当前 WEM 所在位置" if target_path.is_file() else "打开音频目录")
            else:
                self.reveal_file_btn.setToolTip("打开映射文件位置")
            self.reveal_file_btn.setEnabled(True)
            return

        if mode_key == ALL_AUDIO_PREVIEW_MODE and self._current_audio_roots:
            paths_text = "；".join(str(path) for path in self._current_audio_roots)
            self.previewPanel.set_preview_path(f"多个音频目录：{paths_text}")
            self.reveal_file_btn.setToolTip("当前实体包含多个音频目录，请先选择一条音频。")
        else:
            self.previewPanel.set_preview_path("")
            self.reveal_file_btn.setToolTip("当前模式没有可打开的资源。")
        self.reveal_file_btn.setEnabled(False)

    def _reveal_current_preview_target(self) -> None:
        """打开当前预览模式对应的精确文件或音频目录。"""
        target_path = self._resolve_preview_target()
        if target_path is None:
            return
        if self._reveal_file_path(target_path):
            return

        directory = target_path if target_path.is_dir() else target_path.parent
        InfoBar.warning(
            "打开目录失败",
            f"无法打开目录：{directory}",
            parent=self.window(),
            position=InfoBarPosition.TOP,
        )

    def _reveal_file_path(self, target_path: Path) -> bool:
        """在系统文件管理器中定位指定文件。"""
        if target_path.is_dir():
            return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_path)))

        directory = target_path.parent
        try:
            if os.name == "nt" and target_path.exists():
                subprocess.Popen(["explorer.exe", "/select,", str(target_path)])
                return True
        except OSError:
            pass

        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def set_smooth_scroll_enabled(self, enabled: bool) -> None:
        """根据设置应用总览页的滚动模式。"""
        for list_widget in self._entity_lists.values():
            apply_smooth_scroll_enabled(list_widget, enabled)
        apply_smooth_scroll_enabled(self.text_preview, enabled)
        apply_smooth_scroll_enabled(self.audio_preview_tree, enabled)
        apply_smooth_scroll_enabled(self.audio_list, enabled)
