"""执行中心页面，承接任务队列、参数配置与日志同步。"""

from __future__ import annotations

from typing import Any

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    ExpandLayout,
    InfoBar,
    InfoBarPosition,
    SmoothScrollArea,
    SubtitleLabel,
)
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common import (
    GUI_LOG_FORMAT,
    GUI_LOG_MAX_LINES,
    apply_smooth_scroll_enabled,
    get_app_context_block_reason,
    get_buffered_log_lines,
    show_feedback_infobar,
)
from lol_audio_unpack.gui.common.style import (
    apply_page_content_margins,
    configure_transparent_scroll_page,
)
from lol_audio_unpack.gui.controllers.contracts import OverviewSelectionSyncRequest
from lol_audio_unpack.gui.controllers.entity_data_store import EntityDataStore
from lol_audio_unpack.gui.controllers.execution_log_controller import ExecutionLogController
from lol_audio_unpack.gui.controllers.execution_queue_controller import (
    TASK_ITEM_ROLE,
    ExecutionQueueController,
)
from lol_audio_unpack.gui.controllers.execution_selection_controller import (
    ExecutionSelectionController,
)
from lol_audio_unpack.gui.task_models import (
    ExecutionTaskDraft,
    ExecutionTaskProgress,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.view.execution.advanced_input_panel import AdvancedInputPanel
from lol_audio_unpack.gui.view.execution.progress_panel import (
    ProgressPanel,
    build_progress_display_state,
)
from lol_audio_unpack.gui.view.execution.selection_conflict_dialog import (
    ask_selection_conflict_resolution,
)
from lol_audio_unpack.gui.view.execution.task_builder_panel import TaskBuilderPanel


class ExecutionPage(SmoothScrollArea):
    """执行中心页面。"""

    output_state_refresh_requested = Signal(object)
    task_running_changed = Signal(bool)
    task_queue_busy_changed = Signal(bool)
    log_lines_appended = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.view = configure_transparent_scroll_page(
            self,
            page_object_name="ExecutionPage",
            view_object_name="ExecutionPageView",
        )
        self.gui_config = None
        self._entity_data_store = EntityDataStore(entity_types=("champions", "maps"))
        self._is_task_running = False
        self._is_task_queue_busy = False
        self._selection_controller = ExecutionSelectionController()
        self._log_controller = ExecutionLogController(
            initial_lines=(
                "执行中心日志会同步到主窗口底部日志面板。",
                "执行中心已就绪，开始记录任务队列与界面操作。",
                *tuple(get_buffered_log_lines()),
            ),
            max_lines=GUI_LOG_MAX_LINES,
            log_format=GUI_LOG_FORMAT,
            parent=self,
        )
        self._log_controller.log_lines_appended.connect(self.log_lines_appended.emit)
        self.destroyed.connect(self._log_controller.detach_runtime_log_sink)
        self._build_ui()
        self._queue_controller = ExecutionQueueController(
            queue_panel=self.progressPanel.queue_panel,
            build_task_item_tooltip=self._build_task_item_tooltip,
            parent=self,
        )
        self._queue_controller.set_queue_placeholder()
        self._queue_controller.apply_queue_list_height()
        self.taskBuilderPanel.apply_defaults()
        self.taskBuilderPanel.sync_state_from_widgets()
        self._setup_connections()

    def _build_ui(self) -> None:
        self.expandLayout = ExpandLayout(self.view)
        apply_page_content_margins(self.expandLayout)
        self.expandLayout.setSpacing(16)

        header_widget = QWidget(self.view)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        title_label = SubtitleLabel("执行中心", header_widget)
        subtitle_label = CaptionLabel("在这里创建任务并查看进度。", header_widget)
        subtitle_label.setWordWrap(True)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        header_widget.resize(header_widget.width(), header_widget.sizeHint().height())
        self.expandLayout.addWidget(header_widget)

        top_widget = QWidget(self.view)
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(12)

        self.taskBuilderPanel = TaskBuilderPanel(self.view)
        self.task_builder_card = self.taskBuilderPanel
        self.target_title_label = self.taskBuilderPanel.target_title_label
        self.target_summary_value = self.taskBuilderPanel.target_summary_value
        self.task_kind_title_label = self.taskBuilderPanel.task_kind_title_label
        self.extract_task_cb = self.taskBuilderPanel.extract_task_cb
        self.mapping_task_cb = self.taskBuilderPanel.mapping_task_cb
        self.task_builder_summary_label = self.taskBuilderPanel.task_builder_summary_label
        self.create_task_btn = self.taskBuilderPanel.create_task_btn

        self.progressPanel = ProgressPanel(self.view)
        self.progress_card = self.progressPanel
        self.task_status_label = self.progressPanel.task_status_label
        self.task_progress_bar = self.progressPanel.task_progress_bar
        self.task_progress_note = self.progressPanel.task_progress_note
        self.queue_progress_label = self.progressPanel.queue_progress_label
        self.draft_list = self.progressPanel.draft_list

        top_layout.addWidget(self.progressPanel, 1)
        top_layout.addWidget(self.taskBuilderPanel, 1)
        top_widget.resize(top_widget.width(), top_widget.sizeHint().height())
        self.expandLayout.addWidget(top_widget)

        self.advancedPanel = AdvancedInputPanel(self.view)
        self.advanced_card = self.advancedPanel
        self.champion_ids_input = self.advancedPanel.champion_ids_input
        self.map_ids_input = self.advancedPanel.map_ids_input
        self.vo_filter = self.advancedPanel.vo_filter
        self.max_workers_combo = self.advancedPanel.max_workers_combo
        self.bp_voice_cb = self.advancedPanel.bp_voice_cb
        self.force_update_cb = self.advancedPanel.force_update_cb
        self.integrate_data_cb = self.advancedPanel.integrate_data_cb
        self.expandLayout.addWidget(self.advancedPanel)
        self.taskBuilderPanel.bind_advanced_panel(self.advancedPanel)
        self.bottom_spacing_widget = QWidget(self.view)
        self.bottom_spacing_widget.setFixedHeight(20)
        self.expandLayout.addWidget(self.bottom_spacing_widget)

    def _setup_connections(self) -> None:
        self._queue_controller.task_running_changed.connect(self._set_task_running_state)
        self._queue_controller.task_queue_busy_changed.connect(self._set_task_queue_busy_state)
        self._queue_controller.progress_display_requested.connect(
            lambda update: self._refresh_progress_panel(
                status_text=update.status_text,
                note_text=update.note_text,
                progress_current=update.progress_current,
                progress_total=update.progress_total,
            )
        )
        self._queue_controller.log_requested.connect(
            lambda event: self._log_gui_event(event.level, event.message)
        )
        self._queue_controller.output_state_refresh_requested.connect(self.output_state_refresh_requested.emit)
        self._queue_controller.feedback_requested.connect(
            lambda notice: show_feedback_infobar(
                title=notice.title,
                content=notice.content,
                parent=self._feedback_parent(),
                level=notice.level,
                position=InfoBarPosition.TOP,
            )
        )
        self.create_task_btn.clicked.connect(self._queue_task_draft)
        self.taskBuilderPanel.connect_form_signals(self.taskBuilderPanel.sync_state_from_widgets)
        self.draft_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.draft_list.customContextMenuRequested.connect(self._open_task_queue_context_menu)
        self.taskBuilderPanel.refresh_summary()
        self._refresh_progress_panel()

    def set_gui_config(self, cfg) -> None:
        """注入 GUI 配置并刷新默认值。"""
        self.gui_config = cfg
        self.taskBuilderPanel.apply_gui_config_defaults(cfg)
        self.taskBuilderPanel.apply_defaults()
        self.taskBuilderPanel.sync_state_from_widgets()
        self.taskBuilderPanel.refresh_summary()
        fallback_enabled = bool(getattr(cfg, "smooth_scroll_enabled", False))
        self.set_smooth_scroll_enabled(
            page_enabled=bool(getattr(cfg, "page_smooth_scroll_enabled", fallback_enabled)),
            widget_enabled=bool(getattr(cfg, "widget_smooth_scroll_enabled", fallback_enabled)),
        )

    def set_entity_data(self, entity_type: str, data: list[dict[str, Any]]) -> None:
        """更新当前已加载实体目录摘要。"""
        self._entity_data_store.set_rows(entity_type, data)

    def update_entity_rows(self, entity_type: str, rows: list[dict[str, Any]]) -> None:
        """按实体 ID 增量更新页面缓存中的摘要行。"""
        self._entity_data_store.update_rows(entity_type, rows)

    def clear_entity_data(self) -> None:
        """清空当前已加载实体目录摘要。"""
        self._entity_data_store.clear()

    def attach_runtime_log_sink(self, level: str = "INFO") -> None:
        """重新挂载 GUI 运行时日志 sink。"""
        self._log_controller.attach_runtime_log_sink(level)

    def _log_gui_event(self, level: str, message: str) -> None:
        """通过 loguru 记录执行中心的界面交互日志。

        Args:
            level: loguru 使用的日志级别名称。
            message: 需要写入统一日志链路的文本。
        """
        logger.log(level.upper(), message)

    def set_selected_entities(
        self,
        payload: OverviewSelectionSyncRequest | dict[str, Any],
        feedback_parent: QWidget | None = None,
    ) -> str | None:
        """接收来自实体总览的选择结果。"""
        if isinstance(payload, OverviewSelectionSyncRequest):
            champion_ids = tuple(str(entity_id) for entity_id in payload.champion_ids)
            map_ids = tuple(str(entity_id) for entity_id in payload.map_ids)
            source = payload.source
            summary = payload.summary
        else:
            champion_ids = tuple(str(entity_id) for entity_id in payload.get("champion_ids", ()))
            map_ids = tuple(str(entity_id) for entity_id in payload.get("map_ids", ()))
            source = str(payload.get("source", "overview_selection"))
            summary = str(payload.get("summary", "未提供摘要"))

        current_champion_ids, current_map_ids = self.taskBuilderPanel.current_target_ids()
        if self._selection_controller.has_conflict(
            current_champion_ids=current_champion_ids,
            current_map_ids=current_map_ids,
            incoming_champion_ids=champion_ids,
            incoming_map_ids=map_ids,
        ):
            choice = ask_selection_conflict_resolution(
                content=self._selection_controller.build_conflict_dialog_content(
                    current_champion_ids=current_champion_ids,
                    current_map_ids=current_map_ids,
                    incoming_champion_ids=champion_ids,
                    incoming_map_ids=map_ids,
                ),
                parent=self._feedback_parent(feedback_parent),
            )
        else:
            choice = None

        update = self._selection_controller.resolve_selection_update(
            current_champion_ids=current_champion_ids,
            current_map_ids=current_map_ids,
            incoming_champion_ids=champion_ids,
            incoming_map_ids=map_ids,
            source=source,
            summary=summary,
            resolution=choice,
        )
        if update is None:
            self._log_gui_event("info", "[同步] 已取消从实体总览同步选择。")
            return None

        self.taskBuilderPanel.apply_selected_entities(
            champion_ids=update.champion_ids,
            map_ids=update.map_ids,
            source=update.source,
            summary=update.summary,
        )
        self._log_gui_event("info", f"[同步] {update.summary}")
        return update.summary

    def is_task_running(self) -> bool:
        """返回当前是否存在正在执行的任务。"""
        return self._queue_controller.is_task_running()

    def has_active_background_task(self) -> bool:
        """返回执行中心是否仍持有运行中的后台任务。"""
        return self._queue_controller.has_active_background_work()

    def has_incomplete_tasks(self) -> bool:
        """返回队列中是否仍存在等待或运行中的任务。"""
        return self._queue_controller.has_incomplete_tasks()

    def _build_task_item_tooltip(self, task: QueuedExecutionTask) -> str:
        """构造任务列表项的悬停提示文本。"""
        lines = [task.summary]
        if task.result_summary:
            lines.append(task.result_summary)
        if task.error_message:
            lines.append(f"错误：{task.error_message}")
        return "\n".join(lines)

    def _set_task_running_state(self, running: bool) -> None:
        """同步内部运行态并向主窗口发出状态信号。"""
        if self._is_task_running == running:
            return
        self._is_task_running = running
        self.task_running_changed.emit(running)

    def _set_task_queue_busy_state(self, busy: bool) -> None:
        """同步任务队列忙碌状态并向主窗口发出状态信号。"""
        if self._is_task_queue_busy == busy:
            return
        self._is_task_queue_busy = busy
        self.task_queue_busy_changed.emit(busy)

    def _feedback_parent(self, feedback_parent: QWidget | None = None) -> QWidget:
        """返回全局通知应挂载的父级窗口。"""
        if feedback_parent is not None:
            return feedback_parent

        window = self.window()
        return window if isinstance(window, QWidget) else self

    def _open_task_queue_context_menu(self, pos) -> None:
        """打开任务队列右键菜单。"""
        self.progressPanel.queue_panel.open_context_menu(pos, queue_controller=self._queue_controller)

    def _refresh_progress_panel(
        self,
        *,
        status_text: str | None = None,
        note_text: str | None = None,
        progress_current: int | None = None,
        progress_total: int | None = None,
    ) -> None:
        """刷新右侧任务进度面板的摘要。"""
        draft_count = self._queue_controller.draft_queue_size()
        counts = self._queue_controller.queue_status_counts()
        running_item = self._queue_controller.find_running_task_item()
        running_task = running_item.data(TASK_ITEM_ROLE) if running_item is not None else None
        state = build_progress_display_state(
            draft_count=draft_count,
            counts=counts,
            running_task=running_task if isinstance(running_task, QueuedExecutionTask) else None,
            status_text=status_text,
            note_text=note_text,
            progress_current=progress_current,
            progress_total=progress_total,
        )
        self.progressPanel.apply_display_state(state)

    def _queue_task_draft(self) -> None:
        """将当前界面参数写入任务队列，并自动开始首个任务。"""
        task_scope_summary = self.taskBuilderPanel.selected_task_scope_summary()
        if task_scope_summary == "未选择执行内容":
            self._log_gui_event("warning", "[队列] 未勾选任何执行步骤，已阻止创建任务。")
            show_feedback_infobar(
                title="无法创建任务",
                content="请至少勾选音频解包或事件映射中的一个步骤。",
                parent=self._feedback_parent(),
                level="warning",
                position=InfoBarPosition.TOP,
            )
            return

        block_reason = get_app_context_block_reason(self.gui_config)
        if block_reason is not None:
            self._log_gui_event("warning", f"[队列] {block_reason}")
            show_feedback_infobar(
                title="无法创建任务",
                content=block_reason,
                parent=self._feedback_parent(),
                level="warning",
                position=InfoBarPosition.TOP,
            )
            return

        try:
            draft = self.taskBuilderPanel.build_task_draft(gui_config=self.gui_config)
        except ValueError as exc:
            self._log_gui_event("warning", f"[队列] {exc}")
            show_feedback_infobar(
                title="无法创建任务",
                content=str(exc),
                parent=self._feedback_parent(),
                level="warning",
                position=InfoBarPosition.TOP,
            )
            return

        summary = self.taskBuilderPanel.current_task_config_summary()
        self._queue_controller.enqueue_task(draft=draft, summary=summary)
        self.taskBuilderPanel.reset_custom_inputs_to_defaults()

    def _debug_fill_mock_queue(self, count: int) -> str:
        """填充指定数量的 mock 队列项，方便调试列表布局。"""
        return self._queue_controller.fill_mock_queue(count=count)

    def _debug_clear_mock_queue(self) -> str:
        """清空当前调试队列并恢复占位状态。"""
        return self._queue_controller.clear_mock_queue()

    def _debug_inspect_queue(self) -> str:
        """返回当前队列列表与卡片尺寸信息。"""
        return self._queue_controller.inspect_queue(
            progress_card_height=self.progress_card.height(),
            builder_card_height=self.task_builder_card.height(),
        )

    def shutdown_background_tasks(self) -> None:
        """在窗口关闭前清理执行中心后台任务引用。"""
        self._queue_controller.shutdown()

    def current_log_text(self) -> str:
        """返回执行中心当前累计日志文本。

        Returns:
            用换行拼接后的日志全文。
        """
        return self._log_controller.current_log_text()

    def set_smooth_scroll_enabled(
        self,
        page_enabled: bool,
        widget_enabled: bool | None = None,
    ) -> None:
        """根据设置分别应用页面与内部控件的滚动模式。"""
        if widget_enabled is None:
            widget_enabled = page_enabled

        apply_smooth_scroll_enabled(self, page_enabled)
        apply_smooth_scroll_enabled(self.advanced_card, widget_enabled)
        apply_smooth_scroll_enabled(self.draft_list, widget_enabled)
