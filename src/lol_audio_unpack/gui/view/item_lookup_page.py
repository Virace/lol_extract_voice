"""装备 ID 查询独立页面。"""

from __future__ import annotations

from collections.abc import Callable

from loguru import logger
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    InfoBar,
    InfoBarPosition,
    PushButton,
    SearchLineEdit,
    SegmentedWidget,
    SubtitleLabel,
)
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common.font_compat import apply_line_edit_safe_font
from lol_audio_unpack.gui.common.page_style import apply_page_content_margins
from lol_audio_unpack.gui.components.item_lookup_grid import (
    ITEM_MODE_ALL,
    ITEM_MODE_ARENA,
    ITEM_MODE_COMMON,
    ItemGridView,
)
from lol_audio_unpack.gui.service.item_catalog import ItemCatalogPayload, fetch_tencent_items
from lol_audio_unpack.gui.workers import TaskWorker

SOURCE_READY_TEMPLATE = "来源：腾讯官网装备数据 · 版本 {version} · 更新 {file_time}"
SOURCE_IDLE_TEXT = "来源：腾讯官网装备数据 · 尚未加载"
SOURCE_LOADING_TEXT = "来源：腾讯官网装备数据 · 正在加载"
SOURCE_FAILED_TEXT = "来源：腾讯官网装备数据 · 加载失败"
STATUS_IDLE_TEXT = "进入页面后加载装备数据"
STATUS_LOADING_TEXT = "正在加载装备数据..."
STATUS_FAILED_TEXT = "装备数据加载失败"


class ItemLookupPage(QWidget):
    """展示腾讯官网装备 ID 数据的独立查询页。

    页面不依赖 ``AppContext``，也不读取本地 WAD 或音频实体数据。
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        fetch_items_fn: Callable[[], ItemCatalogPayload] = fetch_tencent_items,
        start_worker_fn: Callable[[TaskWorker], None] | None = None,
        worker_cls: type[TaskWorker] = TaskWorker,
    ) -> None:
        """初始化装备查询页。

        Args:
            parent: 父级控件。
            fetch_items_fn: 下载并解析装备资料的函数。
            start_worker_fn: 后台 worker 启动函数，测试可注入同步执行器。
            worker_cls: 后台 worker 类型。
        """
        super().__init__(parent=parent)
        self.setObjectName("ItemLookupPage")
        self.setStyleSheet("QWidget#ItemLookupPage{background: transparent}")

        self._fetch_items_fn = fetch_items_fn
        self._start_worker = start_worker_fn or QThreadPool.globalInstance().start
        self._worker_cls = worker_cls
        self._active_worker: TaskWorker | None = None
        self._has_requested_load = False
        self._is_loading = False

        self._build_ui()
        self._setup_connections()

    def showEvent(self, event: QShowEvent) -> None:
        """首次显示页面时触发在线数据加载。"""
        super().showEvent(event)
        if not self._has_requested_load:
            QTimer.singleShot(0, self.load_items)

    def load_items(self) -> None:
        """异步加载腾讯官网装备数据。

        首次显示和手动刷新都会进入该路径；失败后不会自动重试。
        """
        if self._is_loading:
            return
        self._has_requested_load = True
        worker = self._worker_cls(self._fetch_items_fn)
        worker.signals.started.connect(self._on_load_started)
        worker.signals.finished.connect(self._on_load_finished)
        worker.signals.failed.connect(self._on_load_failed)
        self._active_worker = worker
        self._start_worker(worker)

    def set_catalog(self, payload: ItemCatalogPayload) -> None:
        """把已加载装备资料应用到页面。

        Args:
            payload: 已解析的装备资料。
        """
        self.item_grid.set_items(payload.items)
        self.source_label.setText(
            SOURCE_READY_TEMPLATE.format(
                version=payload.version or "未知",
                file_time=payload.file_time or "未知",
            )
        )
        self.source_label.setToolTip(self.source_label.text())
        self._update_count_status()

    def copy_item_id(self, item_id: str) -> bool:
        """复制纯装备 ID 到系统剪贴板。

        Args:
            item_id: 待复制装备 ID。

        Returns:
            bool: 成功写入剪贴板时返回 ``True``。
        """
        normalized = str(item_id).strip()
        if not normalized:
            return False
        clipboard = QApplication.clipboard()
        if clipboard is None:
            self.status_label.setText("剪贴板不可用")
            return False

        clipboard.setText(normalized)
        InfoBar.success(
            "已复制装备 ID",
            normalized,
            parent=self.window(),
            position=InfoBarPosition.TOP,
        )
        return True

    def _build_ui(self) -> None:
        """创建页面布局与控件。"""
        root_layout = QVBoxLayout(self)
        apply_page_content_margins(root_layout)
        root_layout.setSpacing(14)

        title = SubtitleLabel("装备查询", self)
        root_layout.addWidget(title)

        self.source_label = CaptionLabel(SOURCE_IDLE_TEXT, self)
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root_layout.addWidget(self.source_label)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(10)

        self.search_input = SearchLineEdit(self)
        self.search_input.setPlaceholderText("搜索名称、关键词或 ID")
        self.search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_line_edit_safe_font(self.search_input)
        toolbar.addWidget(self.search_input, 1)

        self.refresh_button = PushButton("刷新", self)
        self.refresh_button.setIcon(FIF.SYNC)
        toolbar.addWidget(self.refresh_button)
        root_layout.addLayout(toolbar)

        self.mode_tabs = SegmentedWidget(self)
        self.mode_tabs.addItem(ITEM_MODE_ALL, "全部")
        self.mode_tabs.addItem(ITEM_MODE_COMMON, "普通模式")
        self.mode_tabs.addItem(ITEM_MODE_ARENA, "斗魂竞技场")
        self.mode_tabs.setCurrentItem(ITEM_MODE_ALL)
        root_layout.addWidget(self.mode_tabs)

        self.status_label = BodyLabel(STATUS_IDLE_TEXT, self)
        root_layout.addWidget(self.status_label)

        self.item_grid = ItemGridView(self)
        root_layout.addWidget(self.item_grid, 1)

    def _setup_connections(self) -> None:
        """连接页面内部交互信号。"""
        self.refresh_button.clicked.connect(self.load_items)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.mode_tabs.currentItemChanged.connect(self._on_mode_changed)
        self.item_grid.clicked.connect(self._on_item_clicked)

    def _on_load_started(self) -> None:
        """进入加载态。"""
        self._is_loading = True
        self.refresh_button.setEnabled(False)
        self.source_label.setText(SOURCE_LOADING_TEXT)
        self.source_label.setToolTip("")
        self.status_label.setText(STATUS_LOADING_TEXT)
        self.status_label.setToolTip("")

    def _on_load_finished(self, payload: object) -> None:
        """处理后台加载成功结果。"""
        self._is_loading = False
        self._active_worker = None
        self.refresh_button.setEnabled(True)
        if not isinstance(payload, ItemCatalogPayload):
            self._on_load_failed("装备数据格式异常")
            return
        self.set_catalog(payload)

    def _on_load_failed(self, message: str) -> None:
        """显示加载失败状态，等待用户手动刷新。"""
        logger.error(f"装备数据加载失败: {message}")
        self._is_loading = False
        self._active_worker = None
        self.refresh_button.setEnabled(True)
        self.source_label.setText(SOURCE_FAILED_TEXT)
        self.status_label.setText(f"{STATUS_FAILED_TEXT}，请检查网络后点击刷新")
        self.status_label.setToolTip(message)

    def _on_search_text_changed(self, text: str) -> None:
        """按本地已加载装备数据更新过滤结果。"""
        self.item_grid.set_keyword(text)
        if not self._is_loading:
            self._update_count_status()

    def _on_mode_changed(self, mode: str) -> None:
        """按页面内模式 tab 更新过滤结果。"""
        self.item_grid.set_mode(mode)
        if not self._is_loading:
            self._update_count_status()

    def _on_item_clicked(self, index) -> None:
        """点击装备行后复制对应 ID。"""
        item = self.item_grid.item_from_index(index)
        if item is not None:
            self.copy_item_id(item.item_id)

    def _update_count_status(self) -> None:
        """刷新当前宫格计数文案。"""
        self.status_label.setText(f"显示 {self.item_grid.visible_count()}/{self.item_grid.total_count()} 件装备")
        self.status_label.setToolTip("")


__all__ = ["ItemLookupPage"]
