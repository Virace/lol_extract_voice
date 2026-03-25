"""实体总览页面，负责展示实体状态并预留右侧资源预览区。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QItemSelectionModel,
    QModelIndex,
    QRect,
    QSignalBlocker,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor, QDesktopServices, QFontMetrics, QPainter, QPalette, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
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
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SegmentedWidget,
    StrongBodyLabel,
    SubtitleLabel,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
    setCustomStyleSheet,
    setStyleSheet,
    themeColor,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)
from qfluentwidgets.components.widgets.scroll_bar import SmoothScrollDelegate

from lol_audio_unpack.gui.common import apply_smooth_scroll_enabled
from lol_audio_unpack.gui.common.styles import build_item_view_theme_pair
from lol_audio_unpack.gui.components.preview_tree import (
    PreviewTreeModel,
    PreviewTreeView,
    build_tree_summary_text,
    collect_tree_stats,
)
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader

OVERVIEW_ITEM_HEIGHT = 40
STATUS_BADGE_SIZE = 24
DARK_THEME_LIGHTNESS_THRESHOLD = 128
EMPTY_MODEL_INDEX = QModelIndex()
OVERVIEW_INTERACTION_RADIUS = 4
OVERVIEW_IDLE_LIGHT_SURFACE_RGBA = (0, 0, 0, 8)
OVERVIEW_IDLE_DARK_SURFACE_RGBA = (255, 255, 255, 12)
OVERVIEW_HOVER_LIGHT_SURFACE_RGBA = (0, 0, 0, 10)
OVERVIEW_HOVER_DARK_SURFACE_RGBA = (255, 255, 255, 14)
OVERVIEW_SELECTION_LIGHT_SURFACE_RGBA = (0, 0, 0, 18)
OVERVIEW_SELECTION_DARK_SURFACE_RGBA = (255, 255, 255, 22)
OVERVIEW_INTERACTION_HORIZONTAL_MARGIN = 4
OVERVIEW_INTERACTION_VERTICAL_MARGIN = 2
OVERVIEW_SELECTION_ACCENT_WIDTH = 3
OVERVIEW_SELECTION_ACCENT_TOP_MARGIN = 7
OVERVIEW_SELECTION_ACCENT_BOTTOM_MARGIN = 6
OVERVIEW_TEXT_LEFT_PADDING = 18
OVERVIEW_TEXT_RIGHT_PADDING = 12
STATUS_AVAILABLE_LIGHT_BACKGROUND = "#0F7B0F"
STATUS_AVAILABLE_DARK_BACKGROUND = "#6CCB5F"
STATUS_MISSING_LIGHT_BACKGROUND = "#9D5D00"
STATUS_MISSING_DARK_BACKGROUND = "#FFF4CE"
STATUS_LIGHT_FOREGROUND = "#FFFFFF"
STATUS_DARK_FOREGROUND = "#111111"
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
    line_edit.setMinimumWidth(0)
    line_edit.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    return line_edit


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
            build_style(STATUS_AVAILABLE_LIGHT_BACKGROUND, STATUS_LIGHT_FOREGROUND),
            build_style(STATUS_AVAILABLE_DARK_BACKGROUND, STATUS_DARK_FOREGROUND),
        )

    return (
        build_style(STATUS_MISSING_LIGHT_BACKGROUND, STATUS_LIGHT_FOREGROUND),
        build_style(STATUS_MISSING_DARK_BACKGROUND, STATUS_DARK_FOREGROUND),
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
        """整体替换当前实体行数据。"""
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
        """更新当前过滤关键字。"""
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
            self._paint_status_badge(
                painter,
                badge_rect,
                badge_label,
                badge_status,
                palette=style_option.palette,
            )
            badge_left += badge_width + badge_spacing

        painter.restore()

    def _paint_status_badge(
        self,
        painter: QPainter,
        rect: QRect,
        badge_label: str,
        badge_status: str,
        *,
        palette,
    ) -> None:
        """绘制单个圆形状态徽章。"""
        is_dark = palette.color(QPalette.ColorRole.Base).lightness() < DARK_THEME_LIGHTNESS_THRESHOLD
        if badge_status == "已存在":
            background = QColor(STATUS_AVAILABLE_DARK_BACKGROUND if is_dark else STATUS_AVAILABLE_LIGHT_BACKGROUND)
            foreground = QColor(STATUS_DARK_FOREGROUND if is_dark else STATUS_LIGHT_FOREGROUND)
        else:
            background = QColor(STATUS_MISSING_DARK_BACKGROUND if is_dark else STATUS_MISSING_LIGHT_BACKGROUND)
            foreground = QColor(STATUS_DARK_FOREGROUND if is_dark else STATUS_LIGHT_FOREGROUND)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, STATUS_BADGE_SIZE / 2, STATUS_BADGE_SIZE / 2)
        painter.setPen(foreground)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, badge_label)


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


def _build_overview_list_styles() -> tuple[str, str]:
    """构造实体列表在亮暗主题下的统一样式。"""
    return build_item_view_theme_pair(
        view_type="QListView",
        light_background="rgba(255, 255, 255, 0.92)",
        dark_background="rgba(28, 28, 30, 0.94)",
        light_border="1px solid rgba(0, 0, 0, 0.10)",
        dark_border="1px solid rgba(255, 255, 255, 0.10)",
        border_radius="10px",
        item_min_height=40,
        item_border_radius=8,
    )


def _build_overview_idle_background() -> QColor:
    """构造总览列表非选中斑马行的中性底色。"""
    if isDarkTheme():
        return QColor(*OVERVIEW_IDLE_DARK_SURFACE_RGBA)
    return QColor(*OVERVIEW_IDLE_LIGHT_SURFACE_RGBA)


def _build_overview_interaction_colors() -> tuple[QColor, QColor, QColor]:
    """构造总览列表 hover/selected 的中性底色与主题 accent。"""
    if isDarkTheme():
        hover_background = QColor(*OVERVIEW_HOVER_DARK_SURFACE_RGBA)
        selection_background = QColor(*OVERVIEW_SELECTION_DARK_SURFACE_RGBA)
    else:
        hover_background = QColor(*OVERVIEW_HOVER_LIGHT_SURFACE_RGBA)
        selection_background = QColor(*OVERVIEW_SELECTION_LIGHT_SURFACE_RGBA)

    return hover_background, selection_background, QColor(themeColor())


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
        self._entity_lists: dict[str, QListView] = {}
        self._entity_models: dict[str, OverviewEntityListModel] = {}
        self._entity_proxies: dict[str, OverviewEntityFilterModel] = {}
        self._audio_preview_placeholder = "请选择左侧实体以查看当前试听视图。"
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
            self._show_placeholder("当前配置尚未完成初始化，暂时无法读取右侧预览内容。")
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
        for entity_type, list_widget in self._entity_lists.items():
            selection_model = list_widget.selectionModel()
            blockers = [QSignalBlocker(list_widget)]
            if selection_model is not None:
                blockers.append(QSignalBlocker(selection_model))
                selection_model.clearSelection()
                selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
            self._entity_models[entity_type].set_rows([])
            list_widget.setCurrentIndex(QModelIndex())
            del blockers
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
                list_widget.viewport().update()
            except RuntimeError:
                continue

    def _on_preview_mode_changed(self, mode_key: str) -> None:
        """切换右侧 Raw 与试听视图。"""
        is_audio_mode = mode_key == "audio"
        self.preview_stack.setCurrentWidget(self.audio_preview_tree if is_audio_mode else self.text_preview)
        self.audio_preview_summary_card.setVisible(is_audio_mode)

    def _current_entity_type(self) -> str:
        return self.nav_pivot.currentRouteKey() or "champions"

    def _current_entity_list(self) -> QListView:
        return self._entity_lists[self._current_entity_type()]

    def _ensure_loader(self) -> EntityDataLoader | None:
        if self._loader is None and self._app_context is not None:
            self._loader = EntityDataLoader(self._app_context)
        return self._loader

    def _iter_visible_rows(self, entity_type: str) -> list[dict[str, Any]]:
        """返回当前过滤条件下仍可见的实体行。"""
        proxy_model = self._entity_proxies[entity_type]
        rows: list[dict[str, Any]] = []
        for row_index in range(proxy_model.rowCount()):
            index = proxy_model.index(row_index, 0)
            row = index.data(OVERVIEW_ROW_ROLE)
            if isinstance(row, dict):
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
        self.splitter.setChildrenCollapsible(False)
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
            list_widget = QListView(self.list_stack)
            list_widget.setAlternatingRowColors(False)
            list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            list_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            list_widget.setUniformItemSizes(True)
            list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            list_widget.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            list_widget.verticalScrollBar().setSingleStep(18)
            list_widget.setSpacing(2)
            list_widget.setItemDelegate(OverviewEntityItemDelegate(list_widget))
            list_widget.scrollDelegate = SmoothScrollDelegate(list_widget, True)
            light_qss, dark_qss = _build_overview_list_styles()
            setCustomStyleSheet(list_widget, light_qss, dark_qss)
            setStyleSheet(list_widget, CustomStyleSheet(list_widget))

            source_model = OverviewEntityListModel(list_widget)
            proxy_model = OverviewEntityFilterModel(list_widget)
            proxy_model.setSourceModel(source_model)
            list_widget.setModel(proxy_model)

            self._entity_lists[entity_type] = list_widget
            self._entity_models[entity_type] = source_model
            self._entity_proxies[entity_type] = proxy_model
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
        preview_hint = CaptionLabel("右侧支持 Raw 与试听树预览；试听树仅展示基础层级结构。", right_widget)
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
            "当前试听视图会保留首层分组；英雄显示 skin_id，地图显示 map 子分组 ID。", self.audio_preview_summary_card
        )
        self.audio_preview_summary_label.setWordWrap(True)
        summary_hint = CaptionLabel("TODO: 首层分组的友好名称映射将在后续补充。", self.audio_preview_summary_card)
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

        self.audio_preview_tree = PreviewTreeView(right_widget)
        self.preview_stack.addWidget(self.audio_preview_tree)

        right_layout.addWidget(self.preview_stack, 1)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([1, 1])

        root_layout.addWidget(self.splitter, 1)
        self._update_selection_summary()
        self.set_smooth_scroll_enabled(False)

    def _rebuild_entity_list(self, entity_type: str) -> None:
        """刷新指定实体类型的 source model，并恢复选择状态。"""
        self._entity_models[entity_type].set_rows(self._cached_data.get(entity_type, []))
        self._prune_entity_state(entity_type)
        self._restore_list_state(entity_type)

    def _apply_filter_to_current_list(self) -> int:
        """对当前列表应用代理过滤，并返回过滤后的可见行数。"""
        entity_type = self._current_entity_type()
        list_widget = self._entity_lists[entity_type]
        proxy_model = self._entity_proxies[entity_type]
        selection_model = list_widget.selectionModel()
        blockers = [QSignalBlocker(list_widget)]
        if selection_model is not None:
            blockers.append(QSignalBlocker(selection_model))
        proxy_model.set_keyword(self.search_input.text())
        self._restore_list_state(entity_type)
        del blockers
        return proxy_model.rowCount()

    def _prune_entity_state(self, entity_type: str) -> None:
        """移除已经不在当前 source model 中的选择与预览状态。"""
        available_ids = self._entity_models[entity_type].entity_ids()
        self._selected_entity_ids[entity_type] &= available_ids
        current_preview_id = self._current_preview_ids.get(entity_type)
        if current_preview_id is not None and current_preview_id not in available_ids:
            self._current_preview_ids[entity_type] = None

    def _find_proxy_index_by_entity_id(self, entity_type: str, entity_id: str | None) -> QModelIndex:
        """在当前代理模型里按实体 ID 查找对应索引。"""
        if not entity_id:
            return QModelIndex()

        proxy_model = self._entity_proxies[entity_type]
        for row_index in range(proxy_model.rowCount()):
            index = proxy_model.index(row_index, 0)
            if str(index.data(OVERVIEW_ENTITY_ID_ROLE) or "") == str(entity_id):
                return index
        return QModelIndex()

    def _restore_list_state(self, entity_type: str) -> None:
        """将页面层维护的选择和当前项同步回代理视图。"""
        list_widget = self._entity_lists[entity_type]
        selection_model = list_widget.selectionModel()
        if selection_model is None:
            return

        blockers = [QSignalBlocker(list_widget), QSignalBlocker(selection_model)]
        selection_model.clearSelection()
        selected_ids = self._selected_entity_ids.get(entity_type, set())
        for entity_id in selected_ids:
            index = self._find_proxy_index_by_entity_id(entity_type, entity_id)
            if index.isValid():
                selection_model.select(
                    index,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

        current_index = self._find_proxy_index_by_entity_id(
            entity_type,
            self._current_preview_ids.get(entity_type),
        )
        if current_index.isValid():
            selection_model.setCurrentIndex(
                current_index,
                QItemSelectionModel.SelectionFlag.Current,
            )
            list_widget.scrollTo(current_index, QListView.ScrollHint.EnsureVisible)
        else:
            selection_model.setCurrentIndex(QModelIndex(), QItemSelectionModel.SelectionFlag.NoUpdate)
            list_widget.setCurrentIndex(QModelIndex())
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
            self._show_placeholder("请选择左侧实体以查看当前 Raw 预览占位内容。")
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
        selection_model = list_widget.selectionModel()
        if selection_model is None:
            return
        selected_ids = {
            str(index.data(OVERVIEW_ENTITY_ID_ROLE))
            for index in selection_model.selectedRows()
            if str(index.data(OVERVIEW_ENTITY_ID_ROLE) or "")
        }
        self._selected_entity_ids[entity_type] = selected_ids
        self._update_selection_summary()

    def _load_preview_for_item(self, entity_type: str, item) -> None:
        row = self._resolve_row_payload(item)
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

    def _refresh_audio_preview(
        self,
        mapping_data: dict[str, Any] | None,
        available_audio_ids: set[str],
    ) -> None:
        """根据当前 mapping 数据刷新试听树。"""
        stats = collect_tree_stats(mapping_data, available_audio_ids)
        self.audio_preview_summary_label.setText(build_tree_summary_text(stats))
        model = self.audio_preview_tree.model()
        if isinstance(model, PreviewTreeModel):
            self.audio_preview_tree.collapseAll()
            model.set_preview_data(mapping_data, available_audio_ids)

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
