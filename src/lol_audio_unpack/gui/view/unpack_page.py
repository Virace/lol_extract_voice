"""音频解包页面。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CheckBox,
    ComboBox,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    ProgressBar,
    RoundMenu,
    SearchLineEdit,
    SegmentedWidget,
    SmoothMode,
    SubtitleLabel,
    TableWidget,
)

from lol_audio_unpack.app_context import OperationOptions, SourceMode, create_app_context
from lol_audio_unpack.facade import LolAudioUnpackApp
from lol_audio_unpack.gui.service.worker import DataLoadWorker
from lol_audio_unpack.gui.workers import TaskWorker, WorkerSignals

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext


class UnpackPage(QWidget):
    """展示实体状态并发起解包任务。"""

    refresh_requested = Signal()
    task_running_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("UnpackPage")
        self.setStyleSheet("QWidget#UnpackPage{background: transparent}")
        self.gui_config = None
        self._cached_data = {"champions": [], "maps": []}
        self._worker = None
        self._task_worker: TaskWorker | None = None
        self._is_unpack_running = False
        self._current_table_key: str | None = None
        self._build_ui()
        self._setup_connections()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        title_label = SubtitleLabel("音频解包", self)
        root_layout.addWidget(title_label)

        self.nav_pivot = SegmentedWidget(self)
        self.nav_pivot.addItem("champions", "英雄")
        self.nav_pivot.addItem("maps", "地图")
        self.nav_pivot.setCurrentItem("champions")
        root_layout.addWidget(self.nav_pivot)

        top_bar = QHBoxLayout()
        self.search_input = SearchLineEdit(self)
        self.search_input.setPlaceholderText("搜索实体 (支持中英)")
        self.search_input.setFixedWidth(240)

        self.vo_filter = SegmentedWidget(self)
        self.vo_filter.addItem("VO", "仅 VO")
        self.vo_filter.addItem("ALL", "全部类型")
        self.vo_filter.setCurrentItem("VO")

        top_bar.addWidget(self.search_input)
        top_bar.addStretch(1)
        top_bar.addWidget(self.vo_filter)
        root_layout.addLayout(top_bar)

        self.hero_table = TableWidget(self)
        self.hero_table.setBorderVisible(True)
        self.hero_table.setBorderRadius(8)
        self.hero_table.setWordWrap(False)
        self.hero_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.hero_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        if hasattr(self.hero_table, "scrollDelagate"):
            self.hero_table.scrollDelagate.verticalSmoothScroll.setSmoothMode(SmoothMode.NO_SMOOTH)

        self.hero_table.setColumnCount(4)
        self.hero_table.setHorizontalHeaderLabels(["ID", "实体", "音频", "映射"])
        self.hero_table.verticalHeader().hide()
        self.hero_table.setAlternatingRowColors(True)
        self.hero_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hero_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.hero_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hero_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.hero_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.hero_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.hero_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.hero_table.setColumnWidth(0, 85)
        self.hero_table.setColumnWidth(2, 85)
        self.hero_table.setColumnWidth(3, 85)
        self.hero_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.hero_table.customContextMenuRequested.connect(self._show_context_menu)
        root_layout.addWidget(self.hero_table, 1)

        bottom_bar_frame = QFrame(self)
        bottom_bar_frame.setObjectName("BottomBar")
        bottom_bar_frame.setStyleSheet(
            """
            QFrame#BottomBar {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
            """
        )
        bottom_layout = QVBoxLayout(bottom_bar_frame)

        actions_row = QHBoxLayout()
        self.bp_voice_cb = CheckBox("附加 BP 语音", self)
        self.bp_voice_cb.setChecked(True)
        self.max_workers_label = BodyLabel("并发数", self)
        self.max_workers_combo = ComboBox(self)
        self.max_workers_combo.addItems(["1", "2", "4", "8", "16"])
        self.max_workers_combo.setCurrentText("4")
        self.unpack_all_btn = PrimaryPushButton("全部解包", self)

        actions_row.addWidget(self.bp_voice_cb)
        actions_row.addSpacing(12)
        actions_row.addWidget(self.max_workers_label)
        actions_row.addWidget(self.max_workers_combo)
        actions_row.addStretch(1)
        actions_row.addWidget(self.unpack_all_btn)
        bottom_layout.addLayout(actions_row)

        self.progress_text = BodyLabel("等待任务开始。", self)
        self.progress_text.setVisible(False)
        bottom_layout.addWidget(self.progress_text)

        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        bottom_layout.addWidget(self.progress_bar)

        root_layout.addWidget(bottom_bar_frame)

    def _setup_connections(self):
        """设置信号连接。"""
        self.nav_pivot.currentItemChanged.connect(self._on_nav_changed)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.unpack_all_btn.clicked.connect(self._unpack_all_entities)

    def showEvent(self, event):
        """页面显示时渲染当前缓存的数据。"""
        super().showEvent(event)
        current_key = self._current_entity_type()

        if self._current_table_key == current_key:
            return

        logger.info(f"UnpackPage showEvent 触发，current_key={current_key}")
        logger.info(
            f"缓存数据: champions={len(self._cached_data.get('champions', []))}, maps={len(self._cached_data.get('maps', []))}"
        )

        if self._cached_data.get(current_key):
            logger.info(f"显示 {current_key} 数据，共 {len(self._cached_data[current_key])} 条")
            self._current_table_key = current_key
            self.add_preview_data(self._cached_data[current_key])
            return

        logger.warning(f"没有可显示的数据: current_key={current_key}，尝试加载...")
        if self.gui_config:
            self.load_data(current_key)

    def set_gui_config(self, cfg):
        """注入 GUI 配置。"""
        self.gui_config = cfg
        self._sync_runtime_controls_from_context()

    def _create_app_context(self, extra_overrides: dict[str, str | bool] | None = None) -> AppContext:
        """从 GUI 配置创建 ``AppContext``。"""
        cli_overrides = self.gui_config.to_app_context_overrides()
        if extra_overrides:
            cli_overrides.update(extra_overrides)
        return create_app_context(cli_overrides=cli_overrides)

    def load_data(self, entity_type: str, force_reload: bool = False):
        """异步加载实体数据，避免主线程卡顿。"""
        if not self.gui_config:
            return

        if not force_reload and self._cached_data[entity_type]:
            if self._current_table_key != entity_type:
                self._current_table_key = entity_type
                self.add_preview_data(self._cached_data[entity_type])
            return

        if self._worker and self._worker.isRunning():
            return

        try:
            app_context = self._create_app_context()
        except Exception as exc:  # noqa: BLE001
            InfoBar.error("初始化失败", str(exc), parent=self, position=InfoBarPosition.TOP)
            return

        self._show_status_progress("正在读取实体状态…")
        self._worker = DataLoadWorker(app_context, entity_type)
        self._worker.finished.connect(lambda data: self._on_data_loaded(entity_type, data))
        self._worker.error.connect(self._on_load_error)
        self._worker.start()

    def _on_data_loaded(self, entity_type: str, data: list):
        """处理数据加载完成事件。"""
        self._hide_status_progress()
        self._cached_data[entity_type] = data
        self._current_table_key = entity_type
        self.add_preview_data(data)

    def _on_load_error(self, error: str):
        """处理数据加载失败事件。"""
        self._hide_status_progress()
        InfoBar.error("加载失败", error, parent=self, position=InfoBarPosition.TOP)

    def _on_nav_changed(self, key: str):
        """在实体标签切换时加载对应数据。"""
        self.load_data(key)

    def _on_search_text_changed(self, text: str):
        """根据名称或别名过滤当前表格。"""
        text = text.lower().strip()
        current_type = self._current_entity_type()
        cached = self._cached_data.get(current_type, [])

        for row in range(self.hero_table.rowCount()):
            name_item = self.hero_table.item(row, 1)
            id_item = self.hero_table.item(row, 0)
            if not name_item or not id_item:
                continue

            entity_id = id_item.text()
            alias = next((data["alias"] for data in cached if data["id"] == entity_id), "")
            name_match = text in name_item.text().lower()
            alias_match = text in alias.lower()
            self.hero_table.setRowHidden(row, not (name_match or alias_match))

    def add_preview_data(self, data_list):
        """将实体状态填充到表格中。"""
        self.hero_table.setUpdatesEnabled(False)
        self.hero_table.setRowCount(len(data_list))
        for row_idx, data in enumerate(data_list):
            id_item = QTableWidgetItem(data["id"])
            name_item = QTableWidgetItem(data["name"])
            audio_item = QTableWidgetItem(data["audio"])
            mapping_item = QTableWidgetItem(data.get("mapping", "未存在"))

            id_item.setTextAlignment(Qt.AlignCenter)
            audio_item.setTextAlignment(Qt.AlignCenter)
            mapping_item.setTextAlignment(Qt.AlignCenter)

            if data["audio"] == "已存在":
                audio_item.setForeground(QColor(0, 200, 0))
            else:
                audio_item.setForeground(QColor(255, 165, 0))

            if data.get("mapping") == "已存在":
                mapping_item.setForeground(QColor(0, 200, 0))
            else:
                mapping_item.setForeground(QColor(255, 165, 0))

            self.hero_table.setItem(row_idx, 0, id_item)
            self.hero_table.setItem(row_idx, 1, name_item)
            self.hero_table.setItem(row_idx, 2, audio_item)
            self.hero_table.setItem(row_idx, 3, mapping_item)
            self.hero_table.setRowHeight(row_idx, 36)

        self.hero_table.setUpdatesEnabled(True)
        self._on_search_text_changed(self.search_input.text())

    def _show_context_menu(self, pos):
        """显示表格右键菜单。"""
        if self._is_unpack_running or not self.hero_table.selectedItems():
            return

        menu = RoundMenu(parent=self)
        unpack_selected_action = Action("解包选中", triggered=self._unpack_selected_entities)
        menu.addAction(unpack_selected_action)
        menu.exec(self.hero_table.mapToGlobal(pos))

    def is_task_running(self) -> bool:
        """返回当前是否存在正在执行的解包任务。"""
        return self._is_unpack_running

    def _current_entity_type(self) -> str:
        """返回当前实体类型键。"""
        return self.nav_pivot.currentRouteKey() or "champions"

    def _current_entity_label(self) -> str:
        """返回当前实体类型的中文名称。"""
        return "英雄" if self._current_entity_type() == "champions" else "地图"

    def _sync_runtime_controls_from_context(self) -> None:
        """使用当前上下文同步运行期控件默认值。"""
        if self.gui_config is None:
            return

        try:
            app_context = self._create_app_context()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"同步解包页运行参数失败: {exc}")
            return

        self.bp_voice_cb.setChecked(bool(app_context.config.with_bp_vo))
        self.vo_filter.setCurrentItem("VO" if tuple(app_context.config.include_types) == ("VO",) else "ALL")

    def _build_runtime_overrides(self) -> dict[str, str | bool]:
        """构建当前任务的临时上下文覆盖项。"""
        audio_filter = self.vo_filter.currentRouteKey() or "VO"
        exclude_type = "" if audio_filter == "ALL" else "SFX,MUSIC"
        return {
            "WITH_BP_VO": self.bp_voice_cb.isChecked(),
            "EXCLUDE_TYPE": exclude_type,
        }

    def _collect_target_entity_ids(self, only_selected: bool) -> tuple[int, ...]:
        """根据当前页面状态收集目标实体 ID。"""
        current_type = self._current_entity_type()
        cached_rows = self._cached_data.get(current_type, [])
        if not cached_rows:
            return ()

        if not only_selected:
            return tuple(int(row["id"]) for row in cached_rows)

        selection_model = self.hero_table.selectionModel()
        if selection_model is None:
            return ()

        selected_id_set = {
            int(index.data())
            for index in selection_model.selectedRows(0)
            if index.isValid()
        }
        return tuple(int(row["id"]) for row in cached_rows if int(row["id"]) in selected_id_set)

    def _build_operation_options(self, entity_ids: tuple[int, ...]) -> OperationOptions:
        """根据页面控件构建解包选项。"""
        current_type = self._current_entity_type()
        max_workers = int(self.max_workers_combo.currentText())
        return OperationOptions(
            max_workers=max_workers,
            champion_ids=entity_ids if current_type == "champions" else None,
            map_ids=entity_ids if current_type == "maps" else None,
        )

    def _build_unpack_task(
        self,
        app: LolAudioUnpackApp,
        opts: OperationOptions,
        *,
        entity_type: str,
    ):
        """构建后台解包任务函数。"""
        include_champions = entity_type == "champions"
        include_maps = entity_type == "maps"
        entity_count = len(opts.champion_ids or opts.map_ids or ())

        def _emit_progress(signals: WorkerSignals, completed: int, total: int, message: str) -> None:
            signals.progress.emit(completed, total, message)

        def _task(signals: WorkerSignals) -> dict[str, Any]:
            if app.ctx.config.source_mode is SourceMode.REMOTE_SNAPSHOT:
                app.run_remote_entity_workflow(
                    extract_options=opts,
                    extract_include_champions=include_champions,
                    extract_include_maps=include_maps,
                    mapping_include_champions=False,
                    mapping_include_maps=False,
                    progress_callback=lambda completed, total, message: _emit_progress(
                        signals,
                        completed,
                        total,
                        message,
                    ),
                )
            else:
                app.extract(
                    opts,
                    include_champions=include_champions,
                    include_maps=include_maps,
                    progress_callback=lambda completed, total, message: _emit_progress(
                        signals,
                        completed,
                        total,
                        message,
                    ),
                )
            return {
                "entity_type": entity_type,
                "entity_count": entity_count,
            }

        return _task

    def _start_unpack_task(self, *, only_selected: bool) -> None:
        """启动当前标签页的解包任务。"""
        if self._is_unpack_running:
            return
        if self.gui_config is None:
            InfoBar.warning("配置未就绪", "请先完成基础配置后再执行解包。", parent=self, position=InfoBarPosition.TOP)
            return

        entity_ids = self._collect_target_entity_ids(only_selected)
        if not entity_ids:
            content = "请先在表格中选择至少一个实体。" if only_selected else "当前列表暂无可解包的实体。"
            InfoBar.warning("没有可执行目标", content, parent=self, position=InfoBarPosition.TOP)
            return

        try:
            app_context = self._create_app_context(self._build_runtime_overrides())
        except Exception as exc:  # noqa: BLE001
            InfoBar.error("初始化失败", str(exc), parent=self, position=InfoBarPosition.TOP)
            return

        entity_type = self._current_entity_type()
        operation_label = "选中项" if only_selected else "全部实体"
        opts = self._build_operation_options(entity_ids)
        worker = TaskWorker(
            self._build_unpack_task(
                LolAudioUnpackApp(app_context),
                opts,
                entity_type=entity_type,
            ),
            pass_signals=True,
        )
        worker.signals.progress.connect(self._on_unpack_progress)
        worker.signals.finished.connect(self._on_unpack_finished)
        worker.signals.failed.connect(self._on_unpack_failed)

        self._task_worker = worker
        self._set_unpack_running(True)
        self._show_task_progress(
            0,
            len(entity_ids),
            f"准备开始解包 {len(entity_ids)} 个{self._current_entity_label()}（{operation_label}）…",
        )
        QThreadPool.globalInstance().start(worker)

    def _unpack_all_entities(self) -> None:
        """解包当前标签页的全部实体。"""
        self._start_unpack_task(only_selected=False)

    def _unpack_selected_entities(self) -> None:
        """解包当前表格中选中的实体。"""
        self._start_unpack_task(only_selected=True)

    def _set_unpack_running(self, running: bool) -> None:
        """切换页面运行态。"""
        self._is_unpack_running = running
        self.nav_pivot.setEnabled(not running)
        self.search_input.setEnabled(not running)
        self.vo_filter.setEnabled(not running)
        self.bp_voice_cb.setEnabled(not running)
        self.max_workers_combo.setEnabled(not running)
        self.unpack_all_btn.setEnabled(not running)
        self.hero_table.setEnabled(not running)
        self.unpack_all_btn.setText("解包中…" if running else "全部解包")
        self.task_running_changed.emit(running)

    def _show_status_progress(self, message: str) -> None:
        """显示通用状态进度提示。"""
        self.progress_text.setText(message)
        self.progress_text.setVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

    def _show_task_progress(self, completed: int, total: int, message: str) -> None:
        """显示实体级进度。"""
        normalized_total = max(total, 1)
        self.progress_text.setText(f"{completed}/{total} · {message}")
        self.progress_text.setVisible(True)
        self.progress_bar.setRange(0, normalized_total)
        self.progress_bar.setValue(min(completed, normalized_total))
        self.progress_bar.setVisible(True)

    def _hide_status_progress(self) -> None:
        """隐藏状态进度提示。"""
        if self._is_unpack_running:
            return
        self.progress_text.setVisible(False)
        self.progress_bar.setVisible(False)

    def _on_unpack_progress(self, completed: int, total: int, message: str) -> None:
        """响应后台解包进度更新。"""
        self._show_task_progress(completed, total, message)

    def _on_unpack_finished(self, result: dict[str, Any]) -> None:
        """响应后台解包任务完成。"""
        self._task_worker = None
        self._set_unpack_running(False)
        entity_count = int(result.get("entity_count", 0))
        entity_label = "英雄" if result.get("entity_type") == "champions" else "地图"
        logger.info(f"GUI 解包任务完成：{entity_count} 个{entity_label}")
        self.progress_text.setVisible(False)
        self.progress_bar.setVisible(False)
        self.refresh_requested.emit()

    def _on_unpack_failed(self, error: str) -> None:
        """响应后台解包任务失败。"""
        self._task_worker = None
        self._set_unpack_running(False)
        self.progress_text.setVisible(False)
        self.progress_bar.setVisible(False)
        InfoBar.error("解包失败", error, parent=self, position=InfoBarPosition.TOP)
