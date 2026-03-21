"""资源映射页面，负责展示并预览已生成的 mapping 文件。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSignalBlocker, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    InfoBar,
    InfoBarPosition,
    ListWidget,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SegmentedWidget,
    SmoothMode,
    SubtitleLabel,
)

from lol_audio_unpack.gui.service.data_loader import EntityDataLoader

MAPPING_ITEM_HEIGHT = 60


def should_display_mapping_row(row: dict[str, Any]) -> bool:
    """判断该实体是否应出现在映射页列表中。

    Args:
        row: 解包页缓存下来的实体数据。

    Returns:
        当映射状态为 ``已存在`` 时返回 ``True``。
    """
    return str(row.get("mapping", "")) == "已存在"


def build_mapping_item_text(row: dict[str, Any]) -> str:
    """构造映射列表条目的显示文本。

    Args:
        row: 映射列表行数据。

    Returns:
        普通列表项展示文本，第二行包含完整文件名。
    """
    alias = str(row.get("alias", "") or "").strip()
    title = f"{row['name']}·{alias}" if alias else str(row["name"])
    file_name = Path(str(row.get("mapping_file", "") or "")).name
    return f"{title}\n{file_name or '未找到 mapping 文件'}"


class MappingPage(QWidget):
    """资源映射页面。

    负责展示当前输出目录里已生成的英雄或地图 mapping 文件，并在右侧
    预览序列化后的文件内容。
    """

    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("MappingPage")
        self.setStyleSheet("QWidget#MappingPage{background: transparent}")
        self.gui_config = None
        self._app_context = None
        self._loader = None
        self._cached_data: dict[str, list[dict[str, Any]]] = {"champions": [], "maps": []}
        self._selected_entity_ids: dict[str, str | None] = {"champions": None, "maps": None}
        self._current_mapping_path: Path | None = None
        self._build_ui()
        self._setup_connections()

    def showEvent(self, event):
        """页面首次展示时同步当前缓存。"""
        super().showEvent(event)
        if self.entity_list.count() == 0:
            self._render_current_list()

    def set_gui_config(self, cfg) -> None:
        """注入 GUI 配置。

        Args:
            cfg: 当前 GUI 配置对象。
        """
        self.gui_config = cfg

    def set_app_context(self, app_context) -> None:
        """注入应用上下文。

        Args:
            app_context: 当前应用上下文；为 ``None`` 表示暂不可读取文件。
        """
        self._app_context = app_context
        self._loader = None
        if app_context is None:
            self._show_placeholder("当前配置尚未完成初始化，暂时无法读取 mapping 文件。")
            return

        if self.entity_list.currentItem() is not None:
            self._load_preview_for_item(self.entity_list.currentItem())

    def set_entity_data(self, entity_type: str, data: list[dict[str, Any]]) -> None:
        """更新页面缓存的实体数据。

        Args:
            entity_type: 实体类型。
            data: 实体列表数据。
        """
        if entity_type not in self._cached_data:
            return

        self._cached_data[entity_type] = data
        if self._current_entity_type() == entity_type:
            self._render_current_list()

    def clear_data(self) -> None:
        """清空页面缓存并恢复占位内容。"""
        self._cached_data = {"champions": [], "maps": []}
        self._selected_entity_ids = {"champions": None, "maps": None}
        self._current_mapping_path = None
        self.entity_list.clear()
        self.list_summary_label.setText("等待实体数据加载…")
        self._show_placeholder("当前暂无可预览的 mapping 文件。")

    def _setup_connections(self) -> None:
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.refresh_btn.clicked.connect(self._render_current_list)
        self.nav_pivot.currentItemChanged.connect(self._on_nav_changed)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.entity_list.currentItemChanged.connect(self._on_current_item_changed)
        self.open_dir_btn.clicked.connect(self._open_selected_directory)

    def _current_entity_type(self) -> str:
        return self.nav_pivot.currentRouteKey() or "champions"

    def _ensure_loader(self) -> EntityDataLoader | None:
        if self._loader is None and self._app_context is not None:
            self._loader = EntityDataLoader(self._app_context)
        return self._loader

    def _iter_visible_rows(self, entity_type: str) -> list[dict[str, Any]]:
        keyword = self.search_input.text().lower().strip()
        rows: list[dict[str, Any]] = []
        for row in self._cached_data.get(entity_type, []):
            if not should_display_mapping_row(row):
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

    def _render_current_list(self) -> None:
        entity_type = self._current_entity_type()
        source_rows = self._cached_data.get(entity_type, [])
        visible_rows = self._iter_visible_rows(entity_type)
        selected_id = self._selected_entity_ids.get(entity_type)

        if not source_rows:
            summary = "等待实体数据加载…"
            empty_text = "当前实体数据尚未加载完成。"
        elif not visible_rows:
            summary = "当前筛选结果下没有可预览的 mapping 文件。"
            empty_text = "当前输出目录中没有找到可预览的 mapping 文件。"
        else:
            summary = f"共找到 {len(visible_rows)} 个可预览文件。"
            empty_text = ""

        self.list_summary_label.setText(summary)

        blocker = QSignalBlocker(self.entity_list)
        self.entity_list.clear()
        for row in visible_rows:
            item = QListWidgetItem(build_mapping_item_text(row))
            item.setData(Qt.UserRole, dict(row))
            item.setToolTip(
                str(row.get("mapping_file", "") or "未找到 mapping 文件")
            )
            item.setSizeHint(QSize(0, MAPPING_ITEM_HEIGHT))
            self.entity_list.addItem(item)
        del blocker

        if not visible_rows:
            placeholder_item = QListWidgetItem(empty_text)
            placeholder_item.setSizeHint(QSize(0, MAPPING_ITEM_HEIGHT))
            placeholder_item.setFlags(Qt.NoItemFlags)
            self.entity_list.addItem(placeholder_item)
            self._selected_entity_ids[entity_type] = None
            self._show_placeholder(empty_text)
            return

        target_index = next(
            (index for index, row in enumerate(visible_rows) if row["id"] == selected_id),
            0,
        )
        self.entity_list.setCurrentRow(target_index)
        self._selected_entity_ids[entity_type] = visible_rows[target_index]["id"]
        self._load_preview_for_item(self.entity_list.item(target_index))

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        # 头部标题
        header_layout = QHBoxLayout()
        title_label = SubtitleLabel("资源映射", self)
        self.refresh_btn = PrimaryPushButton("刷新数据", self)

        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.refresh_btn)
        root_layout.addLayout(header_layout)

        self.nav_pivot = SegmentedWidget(self)
        self.nav_pivot.addItem("champions", "英雄")
        self.nav_pivot.addItem("maps", "地图")
        self.nav_pivot.setCurrentItem("champions")
        root_layout.addWidget(self.nav_pivot)

        # 主体: Splitter
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setObjectName("MappingSplitter")
        self.splitter.setStyleSheet("""
            QSplitter#MappingSplitter::handle {
                background-color: rgba(255, 255, 255, 0.08);
                margin: 4px 2px;
                border-radius: 2px;
                width: 4px;
            }
            QSplitter#MappingSplitter::handle:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
            QSplitter#MappingSplitter::handle:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)

        # 左侧面板
        left_widget = QWidget(self.splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 6, 0)

        self.search_input = SearchLineEdit(left_widget)
        self.search_input.setPlaceholderText("搜索实体 / alias / ID")
        left_layout.addWidget(self.search_input)

        self.list_summary_label = BodyLabel("等待实体数据加载…", left_widget)
        left_layout.addWidget(self.list_summary_label)

        self.entity_list = ListWidget(left_widget)
        self.entity_list.setAlternatingRowColors(True)
        self.entity_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.entity_list.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        if hasattr(self.entity_list, "scrollDelegate"):
            self.entity_list.scrollDelegate.verticalSmoothScroll.setSmoothMode(SmoothMode.NO_SMOOTH)
            self.entity_list.scrollDelegate.horizonSmoothScroll.setSmoothMode(SmoothMode.NO_SMOOTH)
        self.entity_list.verticalScrollBar().setSingleStep(18)
        left_layout.addWidget(self.entity_list, 1)

        # 右侧面板
        right_widget = QWidget(self.splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(8)

        right_header = QHBoxLayout()
        self.preview_title = SubtitleLabel("选中项预览", right_widget)
        self.open_dir_btn = PushButton("打开所在目录", right_widget)
        self.open_dir_btn.setEnabled(False)

        right_header.addWidget(self.preview_title)
        right_header.addStretch(1)
        right_header.addWidget(self.open_dir_btn)
        right_layout.addLayout(right_header)

        self.preview_meta_label = BodyLabel("请选择左侧实体以预览 mapping 文件内容。", right_widget)
        self.preview_meta_label.setWordWrap(True)
        right_layout.addWidget(self.preview_meta_label)

        self.text_preview = PlainTextEdit(right_widget)
        self.text_preview.setReadOnly(True)
        self.text_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_preview.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.text_preview.setCenterOnScroll(False)
        self.text_preview.setUndoRedoEnabled(False)
        if hasattr(self.text_preview, "scrollDelegate"):
            self.text_preview.scrollDelegate.verticalSmoothScroll.setSmoothMode(SmoothMode.NO_SMOOTH)
            self.text_preview.scrollDelegate.horizonSmoothScroll.setSmoothMode(SmoothMode.NO_SMOOTH)
        self.text_preview.verticalScrollBar().setSingleStep(18)
        self.text_preview.horizontalScrollBar().setSingleStep(18)
        self.text_preview.setPlainText("请选择左侧实体以预览 mapping 文件内容。")
        right_layout.addWidget(self.text_preview)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([300, 700])

        root_layout.addWidget(self.splitter, 1)

    def _on_nav_changed(self, _key: str) -> None:
        self._render_current_list()

    def _on_search_text_changed(self, _text: str) -> None:
        self._render_current_list()

    def _on_current_item_changed(self, current, _previous) -> None:
        self._load_preview_for_item(current)

    def _load_preview_for_item(self, item) -> None:
        row = item.data(Qt.UserRole) if item is not None else None
        if not row:
            self._show_placeholder("请选择左侧实体以预览 mapping 文件内容。")
            return

        entity_type = self._current_entity_type()
        self._selected_entity_ids[entity_type] = str(row["id"])
        loader = self._ensure_loader()
        if loader is None:
            self._show_placeholder("当前配置尚未完成初始化，暂时无法读取 mapping 文件。")
            return

        mapping_path, preview_content = loader.load_mapping_preview(entity_type, str(row["id"]))
        if mapping_path is None:
            self._show_placeholder(f"{row['name']} 当前没有可预览的 mapping 文件。")
            return

        self._current_mapping_path = mapping_path
        self.preview_title.setText(f"{row['name']} · {mapping_path.stem}")
        self.preview_meta_label.setText(str(mapping_path))
        self.text_preview.setPlainText(preview_content or "{}")
        self.open_dir_btn.setEnabled(True)

    def _show_placeholder(self, message: str) -> None:
        self._current_mapping_path = None
        self.preview_title.setText("选中项预览")
        self.preview_meta_label.setText(message)
        self.text_preview.setPlainText(message)
        self.open_dir_btn.setEnabled(False)

    def _open_selected_directory(self) -> None:
        if self._current_mapping_path is None:
            return

        directory = self._current_mapping_path.parent
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        if not opened:
            InfoBar.warning(
                "打开目录失败",
                f"无法打开目录：{directory}",
                parent=self,
                position=InfoBarPosition.TOP,
            )
