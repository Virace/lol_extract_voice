"""装备查询页的虚拟化宫格组件。"""

from __future__ import annotations

import urllib.request
from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QRect,
    QRectF,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget
from qfluentwidgets import CustomStyleSheet, isDarkTheme, setCustomStyleSheet, setStyleSheet
from qfluentwidgets.components.widgets.scroll_bar import SmoothScrollDelegate

from lol_audio_unpack.gui.common.styles import (
    build_fluent_list_shell_theme_pair,
    resolve_fluent_neutral_surface,
)
from lol_audio_unpack.gui.service.item_catalog import ItemRecord
from lol_audio_unpack.gui.theme import current_accent_preset_id, get_accent_preset
from lol_audio_unpack.gui.workers import TaskWorker

EMPTY_MODEL_INDEX = QModelIndex()
ITEM_TILE_WIDTH = 124
ITEM_TILE_HEIGHT = 134
ITEM_ICON_SIZE = 58
ITEM_ICON_RADIUS = 7
ITEM_TILE_RADIUS = 8
ITEM_TILE_MARGIN = 5
ITEM_CONTENT_HORIZONTAL_PADDING = 10
ITEM_ICON_TOP_MARGIN = 14
ITEM_NAME_TOP_SPACING = 8
ITEM_ID_TOP_SPACING = 7
ITEM_ID_WIDTH = 72
ITEM_ID_HEIGHT = 26
ITEM_ROW_ROLE = int(Qt.ItemDataRole.UserRole) + 31
ITEM_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 32
ITEM_NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 33
ITEM_ICON_URL_ROLE = int(Qt.ItemDataRole.UserRole) + 34
ITEM_SEARCH_TEXT_ROLE = int(Qt.ItemDataRole.UserRole) + 35
ICON_FETCH_TIMEOUT_SECONDS = 8
ITEM_MODE_ALL = "all"
ITEM_MODE_COMMON = "common"
ITEM_MODE_ARENA = "arena"
COMMON_MODE_MAPS = frozenset(("召唤师峡谷", "嚎哭深渊"))
ARENA_MAP_NAME = "斗魂竞技场"


def _fetch_icon_bytes(url: str) -> bytes:
    """在后台线程下载装备图标原始 bytes。"""
    request = urllib.request.Request(url, headers={"User-Agent": "lol-audio-unpack-gui"}, method="GET")
    with urllib.request.urlopen(request, timeout=ICON_FETCH_TIMEOUT_SECONDS) as response:
        return bytes(response.read())


def item_matches_mode(item: ItemRecord, mode: str) -> bool:
    """判断装备是否属于当前页面模式分类。

    Args:
        item: 装备资料。
        mode: 当前模式 key。

    Returns:
        bool: 装备应出现在当前 tab 时返回 ``True``。
    """
    if mode == ITEM_MODE_ALL:
        return True
    maps = set(item.maps)
    if mode == ITEM_MODE_COMMON:
        return bool(maps & COMMON_MODE_MAPS)
    if mode == ITEM_MODE_ARENA:
        return ARENA_MAP_NAME in maps
    return True


def _build_item_grid_styles() -> tuple[str, str]:
    """构造装备宫格在亮暗主题下的统一样式。"""
    return build_fluent_list_shell_theme_pair(
        item_min_height=ITEM_TILE_HEIGHT,
        item_border_radius=ITEM_TILE_RADIUS,
    )


def _build_item_idle_background() -> QColor:
    """构造装备 tile 的中性底色。"""
    return resolve_fluent_neutral_surface("subtle_idle")


def _build_item_interaction_colors() -> tuple[QColor, QColor, QColor]:
    """构造装备 tile hover/selected 背景与 ID 强调色。"""
    accent = get_accent_preset(current_accent_preset_id()).scale.color(300 if isDarkTheme() else 700)
    return (
        resolve_fluent_neutral_surface("subtle_hover"),
        resolve_fluent_neutral_surface("subtle_selected"),
        accent,
    )


class ItemListModel(QAbstractListModel):
    """承载装备查询宫格数据的轻量模型。"""

    def __init__(self, parent: QObject | None = None) -> None:
        """初始化装备宫格数据模型。

        Args:
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._items: list[ItemRecord] = []

    def rowCount(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> int:
        """返回当前装备行数。"""
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        """按角色返回装备行数据。"""
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None

        item = self._items[index.row()]
        value: Any = None
        if role == Qt.ItemDataRole.DisplayRole:
            value = item.name
        elif role == Qt.ItemDataRole.ToolTipRole:
            value = f"{item.name}\nID: {item.item_id}"
        elif role == Qt.ItemDataRole.SizeHintRole:
            value = QSize(ITEM_TILE_WIDTH, ITEM_TILE_HEIGHT)
        elif role in (Qt.ItemDataRole.UserRole, ITEM_ROW_ROLE):
            value = item
        elif role == ITEM_ID_ROLE:
            value = item.item_id
        elif role == ITEM_NAME_ROLE:
            value = item.name
        elif role == ITEM_ICON_URL_ROLE:
            value = item.icon_url
        elif role == ITEM_SEARCH_TEXT_ROLE:
            value = item.search_text()
        return value

    def set_items(self, items: Sequence[ItemRecord]) -> None:
        """整体替换装备宫格数据。

        Args:
            items: 已解析的装备行。
        """
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def total_count(self) -> int:
        """返回 source model 中的装备总数。"""
        return len(self._items)


class ItemFilterModel(QSortFilterProxyModel):
    """按名称、ID 和关键字过滤装备宫格。"""

    def __init__(self, parent: QObject | None = None) -> None:
        """初始化装备过滤模型。

        Args:
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._keyword = ""
        self._mode = ITEM_MODE_ALL
        self.setDynamicSortFilter(True)

    def set_keyword(self, keyword: str) -> None:
        """更新当前过滤关键字。

        Args:
            keyword: 用户输入的搜索文本。
        """
        normalized = keyword.lower().strip()
        if normalized == self._keyword:
            return
        self._keyword = normalized
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_mode(self, mode: str) -> None:
        """更新当前模式过滤。

        Args:
            mode: 模式 key。
        """
        normalized = mode or ITEM_MODE_ALL
        if normalized == self._mode:
            return
        self._mode = normalized
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """判断某个 source 行是否匹配当前模式与关键字。"""
        model = self.sourceModel()
        if model is None:
            return False
        index = model.index(source_row, 0, source_parent)
        item = model.data(index, ITEM_ROW_ROLE)
        if not isinstance(item, ItemRecord) or not item_matches_mode(item, self._mode):
            return False
        if not self._keyword:
            return True
        search_text = str(model.data(index, ITEM_SEARCH_TEXT_ROLE) or "")
        return self._keyword in search_text


class ItemIconCache(QObject):
    """为装备图标提供按需异步加载和进程内缓存。"""

    pixmap_changed = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        fetch_bytes_fn=_fetch_icon_bytes,
        start_worker_fn=None,
        worker_cls: type[TaskWorker] = TaskWorker,
    ) -> None:
        """初始化图标缓存。

        Args:
            parent: Qt 父对象。
            fetch_bytes_fn: 后台下载图标 bytes 的函数。
            start_worker_fn: worker 启动函数，测试可注入同步执行器。
            worker_cls: 后台 worker 类型。
        """
        super().__init__(parent)
        self._fetch_bytes_fn = fetch_bytes_fn
        self._start_worker = start_worker_fn or QThreadPool.globalInstance().start
        self._worker_cls = worker_cls
        self._pixmaps: dict[str, QPixmap] = {}
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        self._workers: dict[str, TaskWorker] = {}

    def pixmap(self, url: str, size: QSize) -> QPixmap | None:
        """返回缓存图标；未命中时安排异步加载。

        Args:
            url: 图标 URL。
            size: 目标绘制尺寸。

        Returns:
            已缓存图标；未加载完成或加载失败时返回 ``None``。
        """
        normalized_url = url.strip()
        if not normalized_url or normalized_url in self._failed:
            return None
        pixmap = self._pixmaps.get(normalized_url)
        if pixmap is not None and not pixmap.isNull():
            return pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if normalized_url not in self._pending:
            self._request_pixmap(normalized_url)
        return None

    def _request_pixmap(self, url: str) -> None:
        """发起后台图标下载请求。"""
        self._pending.add(url)
        worker = self._worker_cls(lambda url=url: self._fetch_bytes_fn(url))
        worker.signals.finished.connect(lambda payload, url=url: self._finish_request(url, payload))
        worker.signals.failed.connect(lambda _message, url=url: self._mark_failed(url))
        self._workers[url] = worker
        self._start_worker(worker)

    def _finish_request(self, url: str, payload: object) -> None:
        """处理图标请求结果并刷新视图。"""
        self._pending.discard(url)
        self._workers.pop(url, None)
        if isinstance(payload, bytes):
            image = QImage.fromData(payload)
            if not image.isNull():
                self._pixmaps[url] = QPixmap.fromImage(image)
                self.pixmap_changed.emit(url)
                return
        self._failed.add(url)

    def _mark_failed(self, url: str) -> None:
        """记录图标加载失败，避免同一 URL 反复重试。"""
        self._pending.discard(url)
        self._workers.pop(url, None)
        self._failed.add(url)


class ItemDelegate(QStyledItemDelegate):
    """直接绘制装备 tile，避免为每个装备创建独立 QWidget。"""

    def __init__(self, icon_cache: ItemIconCache, parent: QWidget | None = None) -> None:
        """初始化装备条目 delegate。

        Args:
            icon_cache: 装备图标缓存。
            parent: 父级控件。
        """
        super().__init__(parent)
        self._icon_cache = icon_cache

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """返回稳定装备 tile 尺寸。"""
        return QSize(ITEM_TILE_WIDTH, ITEM_TILE_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """绘制装备图标、名称与醒目的装备 ID。"""
        painter.save()

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        interaction_rect = option.rect.adjusted(ITEM_TILE_MARGIN, ITEM_TILE_MARGIN, -ITEM_TILE_MARGIN, -ITEM_TILE_MARGIN)
        if is_selected:
            _hover_background, selected_background, _accent = _build_item_interaction_colors()
            self._paint_background(painter, interaction_rect, selected_background)
        elif is_hovered:
            hover_background, _selected_background, _accent = _build_item_interaction_colors()
            self._paint_background(painter, interaction_rect, hover_background)
        else:
            self._paint_background(painter, interaction_rect, _build_item_idle_background())

        content_rect = interaction_rect.adjusted(
            ITEM_CONTENT_HORIZONTAL_PADDING,
            0,
            -ITEM_CONTENT_HORIZONTAL_PADDING,
            0,
        )
        icon_rect = QRect(
            content_rect.center().x() - ITEM_ICON_SIZE // 2,
            content_rect.top() + ITEM_ICON_TOP_MARGIN,
            ITEM_ICON_SIZE,
            ITEM_ICON_SIZE,
        )
        self._paint_icon(painter, icon_rect, str(index.data(ITEM_ICON_URL_ROLE) or ""))

        name_top = icon_rect.bottom() + ITEM_NAME_TOP_SPACING
        title_rect = QRect(
            content_rect.left(),
            name_top,
            content_rect.width(),
            20,
        )
        id_rect = QRect(
            content_rect.center().x() - ITEM_ID_WIDTH // 2,
            title_rect.bottom() + ITEM_ID_TOP_SPACING,
            ITEM_ID_WIDTH,
            ITEM_ID_HEIGHT,
        )

        metrics = QFontMetrics(option.font)
        name = str(index.data(ITEM_NAME_ROLE) or "")
        painter.setPen(option.palette.color(QPalette.ColorRole.Text))
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignCenter,
            metrics.elidedText(name, Qt.TextElideMode.ElideRight, title_rect.width()),
        )
        self._paint_id(painter, id_rect, str(index.data(ITEM_ID_ROLE) or ""), option.font)
        painter.restore()

    def _paint_background(self, painter: QPainter, rect: QRect, color: QColor) -> None:
        """绘制行交互背景。"""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(rect, ITEM_TILE_RADIUS, ITEM_TILE_RADIUS)

    def _paint_icon(self, painter: QPainter, rect: QRect, url: str) -> None:
        """绘制图标或稳定尺寸占位块。"""
        pixmap = self._icon_cache.pixmap(url, rect.size())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if pixmap is not None:
            target = QRect(
                rect.center().x() - pixmap.width() // 2,
                rect.center().y() - pixmap.height() // 2,
                pixmap.width(),
                pixmap.height(),
            )
            path = QPainterPath()
            path.addRoundedRect(QRectF(target), ITEM_ICON_RADIUS, ITEM_ICON_RADIUS)
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(target, pixmap)
            painter.restore()
            return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(resolve_fluent_neutral_surface("emphasis_hover"))
        painter.drawRoundedRect(rect, ITEM_ICON_RADIUS, ITEM_ICON_RADIUS)

    def _paint_id(self, painter: QPainter, rect: QRect, item_id: str, base_font: QFont) -> None:
        """绘制右侧固定宽度的装备 ID 区域。"""
        _hover_background, _selected_background, accent = _build_item_interaction_colors()
        id_background = QColor(accent)
        id_background.setAlpha(34 if not isDarkTheme() else 46)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(id_background)
        painter.drawRoundedRect(rect, ITEM_ID_HEIGHT // 2, ITEM_ID_HEIGHT // 2)

        font = QFont(base_font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(accent)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, item_id)


class ItemGridView(QListView):
    """封装装备查询宫格的模型、过滤、绘制与图标缓存。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化装备宫格视图。

        Args:
            parent: 父级控件。
        """
        super().__init__(parent)
        self.setAlternatingRowColors(False)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setGridSize(QSize(ITEM_TILE_WIDTH, ITEM_TILE_HEIGHT))
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(20)
        self.setSpacing(6)

        self._icon_cache = ItemIconCache(self)
        self._icon_cache.pixmap_changed.connect(lambda _url: self.viewport().update())
        self.setItemDelegate(ItemDelegate(self._icon_cache, self))
        self.scrollDelegate = SmoothScrollDelegate(self, True)

        light_qss, dark_qss = _build_item_grid_styles()
        setCustomStyleSheet(self, light_qss, dark_qss)
        setStyleSheet(self, CustomStyleSheet(self))

        self._source_model = ItemListModel(self)
        self._proxy_model = ItemFilterModel(self)
        self._proxy_model.setSourceModel(self._source_model)
        self.setModel(self._proxy_model)

    def set_items(self, items: Sequence[ItemRecord]) -> None:
        """整体替换装备数据。

        Args:
            items: 已解析装备行。
        """
        self._source_model.set_items(items)

    def set_keyword(self, keyword: str) -> None:
        """更新当前搜索过滤关键字。"""
        self._proxy_model.set_keyword(keyword)

    def set_mode(self, mode: str) -> None:
        """更新当前模式过滤。"""
        self._proxy_model.set_mode(mode)

    def total_count(self) -> int:
        """返回装备总数。"""
        return self._source_model.total_count()

    def visible_count(self) -> int:
        """返回过滤后的可见装备数。"""
        return self._proxy_model.rowCount()

    def visible_items(self) -> list[ItemRecord]:
        """返回当前过滤后仍可见的装备行。"""
        items: list[ItemRecord] = []
        for row_index in range(self._proxy_model.rowCount()):
            item = self._proxy_model.index(row_index, 0).data(ITEM_ROW_ROLE)
            if isinstance(item, ItemRecord):
                items.append(item)
        return items

    def item_from_index(self, index: QModelIndex) -> ItemRecord | None:
        """从代理索引提取装备行。"""
        if not index.isValid():
            return None
        item = index.data(ITEM_ROW_ROLE)
        return item if isinstance(item, ItemRecord) else None

    def find_index_by_item_id(self, item_id: str | None) -> QModelIndex:
        """在当前代理模型里按装备 ID 查找索引。"""
        if not item_id:
            return QModelIndex()
        for row_index in range(self._proxy_model.rowCount()):
            index = self._proxy_model.index(row_index, 0)
            if str(index.data(ITEM_ID_ROLE) or "") == str(item_id):
                return index
        return QModelIndex()

    def refresh_theme(self) -> None:
        """在主题切换后刷新当前视口绘制。"""
        self.viewport().update()


__all__ = [
    "ITEM_ID_ROLE",
    "ITEM_ICON_URL_ROLE",
    "ITEM_MODE_ALL",
    "ITEM_MODE_ARENA",
    "ITEM_MODE_COMMON",
    "ITEM_NAME_ROLE",
    "ITEM_ROW_ROLE",
    "ITEM_SEARCH_TEXT_ROLE",
    "ITEM_TILE_HEIGHT",
    "ITEM_TILE_WIDTH",
    "ItemDelegate",
    "ItemFilterModel",
    "ItemGridView",
    "ItemIconCache",
    "ItemListModel",
]
