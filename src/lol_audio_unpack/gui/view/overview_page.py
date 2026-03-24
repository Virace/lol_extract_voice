"""实体总览页面，负责展示实体状态并预留右侧资源预览区。"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from PySide6.QtCore import QSignalBlocker, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CustomStyleSheet,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SegmentedWidget,
    StrongBodyLabel,
    SubtitleLabel,
    TransparentToolButton,
    TreeWidget,
    setCustomStyleSheet,
    setStyleSheet,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.gui.common import apply_smooth_scroll_enabled
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader

OVERVIEW_ITEM_HEIGHT = 40
STATUS_BADGE_SIZE = 24
AUDIO_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 1
AUDIO_AVAILABLE_ROLE = int(Qt.ItemDataRole.UserRole) + 2


@dataclass(frozen=True, slots=True)
class AudioPreviewNode:
    """试听树中的通用节点。"""

    label: str
    children: tuple[AudioPreviewNode, ...] = ()
    audio_id: str | None = None
    is_available: bool = False


@dataclass(frozen=True, slots=True)
class AudioPreviewStats:
    """试听树摘要统计。"""

    skin_count: int = 0
    audio_type_count: int = 0
    event_count: int = 0
    audio_id_count: int = 0
    available_audio_id_count: int = 0


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
    line_edit.setPlaceholderText("请选择左侧实体以查看当前 Raw 预览占位内容。")
    return line_edit


def collect_available_audio_ids(audio_paths: tuple[Path, ...]) -> set[str]:
    """递归收集实体输出目录下已存在的音频 ID。"""
    available_ids: set[str] = set()

    for audio_path in audio_paths:
        if not audio_path.exists():
            continue

        for wem_path in audio_path.rglob("*.wem"):
            available_ids.add(wem_path.stem)

    return available_ids


def build_audio_preview_nodes(
    mapping_data: dict[str, Any] | None,
    available_audio_ids: set[str],
) -> tuple[tuple[AudioPreviewNode, ...], AudioPreviewStats]:
    """按 mapping 原始层级构造试听树节点。

    Args:
        mapping_data: 当前实体的原始 mapping 数据。
        available_audio_ids: 当前实体本地已存在的 wem ID 集合。

    Returns:
        可直接渲染到试听树的节点序列与摘要统计。
    """
    skins = mapping_data.get("skins", {}) if isinstance(mapping_data, dict) else {}
    if not isinstance(skins, dict):
        return (), AudioPreviewStats()

    skin_nodes: list[AudioPreviewNode] = []
    skin_count = 0
    audio_type_count = 0
    event_count = 0
    audio_id_count = 0
    available_audio_id_count = 0

    for skin_id, skin_payload in skins.items():
        events_payload = skin_payload.get("events", {}) if isinstance(skin_payload, dict) else {}
        type_nodes: list[AudioPreviewNode] = []

        if isinstance(events_payload, dict):
            for audio_type_name, event_payload in events_payload.items():
                if not isinstance(event_payload, dict):
                    continue

                event_nodes: list[AudioPreviewNode] = []
                for event_name, audio_ids in event_payload.items():
                    if not isinstance(audio_ids, list | tuple):
                        continue

                    id_nodes: list[AudioPreviewNode] = []
                    for audio_id in audio_ids:
                        audio_id_text = str(audio_id).strip()
                        if not audio_id_text:
                            continue

                        is_available = audio_id_text in available_audio_ids
                        id_nodes.append(
                            AudioPreviewNode(
                                label=audio_id_text,
                                audio_id=audio_id_text,
                                is_available=is_available,
                            )
                        )
                        audio_id_count += 1
                        if is_available:
                            available_audio_id_count += 1

                    event_nodes.append(AudioPreviewNode(label=str(event_name), children=tuple(id_nodes)))
                    event_count += 1

                type_nodes.append(AudioPreviewNode(label=str(audio_type_name), children=tuple(event_nodes)))
                audio_type_count += 1

        skin_nodes.append(
            AudioPreviewNode(
                label=str(skin_id),
                children=(AudioPreviewNode(label="events", children=tuple(type_nodes)),),
            )
        )
        skin_count += 1

    return (
        tuple(skin_nodes),
        AudioPreviewStats(
            skin_count=skin_count,
            audio_type_count=audio_type_count,
            event_count=event_count,
            audio_id_count=audio_id_count,
            available_audio_id_count=available_audio_id_count,
        ),
    )


def build_audio_preview_summary_text(stats: AudioPreviewStats) -> str:
    """构造试听视图顶部摘要文案。"""
    return (
        f"皮肤 {stats.skin_count} · 类型 {stats.audio_type_count} · "
        f"事件 {stats.event_count} · ID {stats.audio_id_count} · 可试听 {stats.available_audio_id_count}"
    )


def _build_status_badge_styles(status: str) -> tuple[str, str]:
    """构造状态徽章在亮暗主题下的样式文本。

    Args:
        status: 当前状态文案。

    Returns:
        亮色主题与暗色主题对应的样式表文本。
    """

    def build_style(background: str, foreground: str) -> str:
        return f"""
        QLabel {{
            background-color: {background};
            color: {foreground};
            border-radius: {STATUS_BADGE_SIZE // 2}px;
            font-size: 13px;
            font-weight: 500;
        }}
        """

    if status == "已存在":
        return (
            build_style("#0F7B0F", "#FFFFFF"),
            build_style("#6CCB5F", "#111111"),
        )

    return (
        build_style("#9D5D00", "#FFFFFF"),
        build_style("#FFF4CE", "#111111"),
    )


def _create_status_badge(kind: str, status: str, parent: QWidget) -> QLabel:
    """创建实体列表中的轻量状态徽章。"""
    label = "A" if kind == "audio" else "M"
    display_name = "音频" if kind == "audio" else "映射"
    badge = QLabel(label, parent)
    badge.setAlignment(Qt.AlignCenter)
    badge.setFixedSize(STATUS_BADGE_SIZE, STATUS_BADGE_SIZE)
    badge.setContentsMargins(0, 0, 0, 0)
    light_qss, dark_qss = _build_status_badge_styles(status)
    setCustomStyleSheet(badge, light_qss, dark_qss)
    setStyleSheet(badge, CustomStyleSheet(badge))
    badge.setToolTip(f"{display_name}：{status}")
    return badge


class OverviewListItemWidget(QFrame):
    """实体总览列表项控件。"""

    def __init__(self, row: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OverviewListItem")
        self.setStyleSheet("QFrame#OverviewListItem { background: transparent; }")

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(8, 4, 8, 4)
        root_layout.setSpacing(8)

        title_label = BodyLabel(build_overview_item_text(row), self)
        title_label.setToolTip(title_label.text())
        title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        badge_container = QWidget(self)
        badge_layout = QHBoxLayout(badge_container)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setSpacing(8)
        badge_layout.addWidget(
            _create_status_badge("audio", str(row.get("audio", "未存在")), badge_container),
            0,
            Qt.AlignVCenter,
        )
        badge_layout.addWidget(
            _create_status_badge("mapping", str(row.get("mapping", "未存在")), badge_container),
            0,
            Qt.AlignVCenter,
        )

        root_layout.addWidget(title_label, 1, Qt.AlignVCenter)
        root_layout.addWidget(badge_container, 0, Qt.AlignVCenter)


def _build_overview_item_tooltip(row: dict[str, Any]) -> str:
    """构造总览页条目的提示信息。"""
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
        self._entity_lists: dict[str, ListWidget] = {}
        self._audio_preview_placeholder = "请选择左侧实体以查看当前试听视图。"
        self._build_ui()
        self._setup_connections()

    def showEvent(self, event):
        """页面首次展示时同步当前缓存。"""
        super().showEvent(event)
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
            self._show_placeholder("当前配置尚未完成初始化，暂时无法读取右侧预览内容。")
            return

        current_item = self._current_entity_list().currentItem()
        if current_item is not None:
            self._load_preview_for_item(self._current_entity_type(), current_item)

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
        for list_widget in self._entity_lists.values():
            blocker = QSignalBlocker(list_widget)
            list_widget.clear()
            list_widget.clearSelection()
            list_widget.setCurrentRow(-1)
            del blocker
        self.list_summary_label.setText("等待实体数据加载…")
        self._update_selection_summary()
        self._show_placeholder("当前暂无可预览的资源内容。")

    def _setup_connections(self) -> None:
        self.nav_pivot.currentItemChanged.connect(self._on_nav_changed)
        self.preview_mode_pivot.currentItemChanged.connect(self._on_preview_mode_changed)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.sync_selection_btn.clicked.connect(self._sync_selected_entities)
        self.clear_selection_btn.clicked.connect(self._clear_selected_entities)
        self.reveal_file_btn.clicked.connect(self._reveal_selected_mapping_file)
        self.audio_preview_tree.itemClicked.connect(self._on_audio_preview_item_clicked)

        for entity_type, list_widget in self._entity_lists.items():
            list_widget.currentItemChanged.connect(
                lambda current, previous, et=entity_type: self._on_current_item_changed(et, current, previous)
            )
            list_widget.itemSelectionChanged.connect(
                lambda et=entity_type: self._on_entity_selection_changed(et)
            )

    def _on_preview_mode_changed(self, mode_key: str) -> None:
        """切换右侧 Raw 与试听视图。"""
        is_audio_mode = mode_key == "audio"
        self.preview_stack.setCurrentWidget(self.audio_preview_tree if is_audio_mode else self.text_preview)
        self.audio_preview_summary_card.setVisible(is_audio_mode)

    def _on_audio_preview_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """处理试听树叶子节点的点击请求。"""
        if column not in (0, 1):
            return

        audio_id = item.data(0, AUDIO_ID_ROLE)
        is_available = bool(item.data(0, AUDIO_AVAILABLE_ROLE))
        if not audio_id or not is_available:
            return

        self._handle_audio_preview_request(str(audio_id))

    def _current_entity_type(self) -> str:
        return self.nav_pivot.currentRouteKey() or "champions"

    def _current_entity_list(self) -> ListWidget:
        return self._entity_lists[self._current_entity_type()]

    def _ensure_loader(self) -> EntityDataLoader | None:
        if self._loader is None and self._app_context is not None:
            self._loader = EntityDataLoader(self._app_context)
        return self._loader

    def _iter_visible_rows(self, entity_type: str) -> list[dict[str, Any]]:
        keyword = self.search_input.text().lower().strip()
        rows: list[dict[str, Any]] = []
        for row in self._cached_data.get(entity_type, []):
            if not should_display_overview_row(row):
                continue
            haystacks = (
                str(row.get("id", "")),
                str(row.get("name", "")),
                str(row.get("alias", "")),
            )
            if keyword and not any(keyword in value.lower() for value in haystacks):
                continue
            rows.append(row)
        return rows

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        header_layout = QHBoxLayout()
        title_label = SubtitleLabel("实体总览", self)
        subtitle_label = CaptionLabel("统一查看实体状态、筛选与选择，并把当前选择同步到执行中心。", self)
        subtitle_label.setWordWrap(True)

        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        title_column.addWidget(title_label)
        title_column.addWidget(subtitle_label)

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
        self.splitter.setStyleSheet(
            """
            QSplitter#OverviewSplitter::handle {
                background-color: rgba(255, 255, 255, 0.08);
                margin: 8px 4px;
                border-radius: 2px;
                width: 6px;
            }
            QSplitter#OverviewSplitter::handle:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
            QSplitter#OverviewSplitter::handle:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
            """
        )

        left_widget = QWidget(self.splitter)
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
            list_widget = ListWidget(self.list_stack)
            list_widget.setAlternatingRowColors(True)
            list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
            list_widget.setUniformItemSizes(True)
            list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            list_widget.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            list_widget.verticalScrollBar().setSingleStep(18)
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
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(8)

        preview_title = StrongBodyLabel("资源预览", right_widget)
        preview_hint = CaptionLabel("当前先保留 Raw 预览壳；Tree 视图与音频点击播放将在后续接入。", right_widget)
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
        self.preview_mode_pivot.addItem("raw", "Raw")
        self.preview_mode_pivot.addItem("audio", "试听视图")
        self.preview_mode_pivot.setCurrentItem("raw")
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
            "当前试听视图会保留 skins 层级；皮肤名映射后续补充。", self.audio_preview_summary_card
        )
        self.audio_preview_summary_label.setWordWrap(True)
        summary_hint = CaptionLabel("TODO: skin_id -> 皮肤名映射将在后续补充。", self.audio_preview_summary_card)
        summary_hint.setWordWrap(True)
        summary_layout.addWidget(self.audio_preview_summary_label)
        summary_layout.addWidget(summary_hint)
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
        self.text_preview.setPlainText("请选择左侧实体以查看当前 Raw 预览占位内容。")
        self.preview_stack.addWidget(self.text_preview)

        self.audio_preview_tree = TreeWidget(right_widget)
        self.audio_preview_tree.setHeaderHidden(True)
        self.audio_preview_tree.setColumnCount(2)
        self.audio_preview_tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.audio_preview_tree.setUniformRowHeights(True)
        self.audio_preview_tree.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.audio_preview_tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.audio_preview_tree.verticalScrollBar().setSingleStep(18)
        self.audio_preview_tree.horizontalScrollBar().setSingleStep(18)
        self.audio_preview_tree.setColumnWidth(0, 56)
        self.audio_preview_tree.header().setStretchLastSection(True)
        self.preview_stack.addWidget(self.audio_preview_tree)

        right_layout.addWidget(self.preview_stack, 1)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([360, 660])

        root_layout.addWidget(self.splitter, 1)
        self._update_selection_summary()
        self.set_smooth_scroll_enabled(False)

    def _rebuild_entity_list(self, entity_type: str) -> None:
        """仅在数据刷新时重建指定实体类型的列表。"""
        list_widget = self._entity_lists[entity_type]
        selected_ids = self._selected_entity_ids.get(entity_type, set())
        current_preview_id = self._current_preview_ids.get(entity_type)

        blocker = QSignalBlocker(list_widget)
        list_widget.clear()
        for row in self._cached_data.get(entity_type, []):
            if not should_display_overview_row(row):
                continue
            item = QListWidgetItem()
            item.setData(Qt.UserRole, dict(row))
            item.setToolTip(_build_overview_item_tooltip(row))
            item.setSizeHint(QSize(0, OVERVIEW_ITEM_HEIGHT))
            list_widget.addItem(item)
            list_widget.setItemWidget(item, OverviewListItemWidget(row, list_widget))
            if str(row["id"]) in selected_ids:
                item.setSelected(True)
            if current_preview_id is not None and str(row["id"]) == current_preview_id:
                list_widget.setCurrentItem(item)
        if current_preview_id is None:
            list_widget.setCurrentRow(-1)
        del blocker

    def _apply_filter_to_current_list(self) -> int:
        """对当前列表应用搜索过滤，仅隐藏或显示现有项。"""
        keyword = self.search_input.text().lower().strip()
        visible_count = 0
        list_widget = self._current_entity_list()
        for row_index in range(list_widget.count()):
            item = list_widget.item(row_index)
            row = item.data(Qt.UserRole)
            if not row:
                continue
            haystacks = (
                str(row.get("id", "")),
                str(row.get("name", "")),
                str(row.get("alias", "")),
            )
            is_visible = not keyword or any(keyword in value.lower() for value in haystacks)
            item.setHidden(not is_visible)
            if is_visible:
                visible_count += 1
        return visible_count

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
            self._show_placeholder("当前实体数据尚未加载完成。")
            self._update_selection_summary()
            return

        if visible_count == 0:
            self.list_summary_label.setText("当前筛选结果为空。")
            self._show_placeholder("未找到匹配的实体，请调整筛选条件。")
            self._update_selection_summary()
            return

        self.list_summary_label.setText(f"共 {len(source_rows)} 个实体，当前显示 {visible_count} 个。")

        if current_preview_id is None:
            list_widget.setCurrentRow(-1)
            self._show_placeholder("请选择左侧实体以查看当前 Raw 预览占位内容。")
            self._update_selection_summary()
            return

        target_item = None
        for row_index in range(list_widget.count()):
            item = list_widget.item(row_index)
            row = item.data(Qt.UserRole)
            if not row or item.isHidden():
                continue
            if str(row["id"]) == current_preview_id:
                target_item = item
                break

        if target_item is None:
            self._show_placeholder("当前筛选结果中不包含已选实体。")
            self._update_selection_summary()
            return

        if list_widget.currentItem() is not target_item:
            list_widget.setCurrentItem(target_item)
        else:
            self._load_preview_for_item(entity_type, target_item)
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
        blocker = QSignalBlocker(list_widget)
        list_widget.clearSelection()
        list_widget.setCurrentRow(-1)
        del blocker
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
        selected_ids = {
            str(item.data(Qt.UserRole)["id"])
            for item in list_widget.selectedItems()
            if item.data(Qt.UserRole)
        }
        self._selected_entity_ids[entity_type] = selected_ids
        self._update_selection_summary()

    def _load_preview_for_item(self, entity_type: str, item) -> None:
        row = item.data(Qt.UserRole) if item is not None else None
        if not row:
            self._current_preview_ids[entity_type] = None
            self._show_placeholder("请选择左侧实体以查看当前 Raw 预览占位内容。")
            return

        self._current_preview_ids[entity_type] = str(row["id"])
        loader = self._ensure_loader()
        if loader is None:
            self._show_placeholder("当前配置尚未完成初始化，暂时无法读取右侧预览内容。")
            return

        mapping_path, mapping_data, preview_content = loader.load_mapping_preview(entity_type, str(row["id"]))
        if mapping_path is None:
            self._show_placeholder(
                f"{row['name']} 当前还没有 mapping 文件。后续 Tree 视图会继续承接更多预览能力。"
            )
            return

        available_audio_ids = loader.load_available_audio_ids(entity_type, str(row["id"]))
        self._current_mapping_path = mapping_path
        self.preview_path_edit.setText(build_preview_path_text(mapping_path))
        self.preview_path_edit.setCursorPosition(0)
        self.preview_path_edit.setToolTip(str(mapping_path))
        self.text_preview.setPlainText(preview_content or "{}")
        self._refresh_audio_preview(mapping_data, available_audio_ids)
        self.reveal_file_btn.setEnabled(True)

    def _refresh_audio_preview(
        self,
        mapping_data: dict[str, Any] | None,
        available_audio_ids: set[str],
    ) -> None:
        """根据当前 mapping 数据刷新试听树。"""
        self.audio_preview_tree.setUpdatesEnabled(False)
        try:
            self.audio_preview_tree.clear()
            nodes, stats = build_audio_preview_nodes(mapping_data, available_audio_ids)
            self.audio_preview_summary_label.setText(build_audio_preview_summary_text(stats))

            for node in nodes:
                self._append_audio_preview_node(None, node)

            if nodes:
                self.audio_preview_tree.expandToDepth(1)
        finally:
            self.audio_preview_tree.setUpdatesEnabled(True)

    def _append_audio_preview_node(
        self,
        parent_item: QTreeWidgetItem | None,
        node: AudioPreviewNode,
    ) -> QTreeWidgetItem:
        """将试听树节点递归追加到 TreeWidget。"""
        if node.audio_id is not None:
            item = QTreeWidgetItem(["▶", node.audio_id])
            item.setData(0, AUDIO_ID_ROLE, node.audio_id)
            item.setData(0, AUDIO_AVAILABLE_ROLE, node.is_available)
            item.setTextAlignment(0, Qt.AlignCenter)
            item.setToolTip(0, "模拟播放当前音频 ID")
            item.setToolTip(1, node.audio_id)
            if not node.is_available:
                item.setDisabled(True)
        else:
            item = QTreeWidgetItem([node.label, ""])
            item.setFirstColumnSpanned(True)

        if parent_item is None:
            self.audio_preview_tree.addTopLevelItem(item)
        else:
            parent_item.addChild(item)

        if node.audio_id is not None:
            item.setSizeHint(0, QSize(0, 32))
            return item

        for child_node in node.children:
            self._append_audio_preview_node(item, child_node)

        return item

    def _handle_audio_preview_request(self, audio_id: str) -> None:
        """记录试听树中的模拟播放请求。"""
        logger.info(f"[试听] 模拟播放音频 ID {audio_id}")

    def _show_placeholder(self, message: str) -> None:
        self._current_mapping_path = None
        self.preview_path_edit.clear()
        self.preview_path_edit.setToolTip("")
        self.text_preview.setPlainText(message)
        self.audio_preview_tree.clear()
        self.audio_preview_summary_label.setText(self._audio_preview_placeholder)
        self.reveal_file_btn.setEnabled(False)

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
