"""执行中心页面，承接任务创建、队列执行与日志同步。"""

from __future__ import annotations

from typing import Any

from loguru import logger
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMessageBox, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, InfoBarPosition, SmoothScrollArea, SubtitleLabel, qconfig

from lol_audio_unpack.gui.common import (
    GUI_LOG_FORMAT,
    GUI_LOG_MAX_LINES,
    apply_smooth_scroll_enabled,
    get_block_reason,
    get_buffered_log_lines,
    show_feedback_infobar,
)
from lol_audio_unpack.gui.common.page_style import (
    apply_page_content_margins,
    configure_transparent_scroll_page,
)
from lol_audio_unpack.gui.components.global_progress_strip import GlobalProgressStripState
from lol_audio_unpack.gui.controllers import (
    ExecutionLogController,
    ExecutionQueueController,
    ExecutionSelectionController,
)
from lol_audio_unpack.gui.controllers.contracts import OverviewSelectionSyncRequest, SharedDataLoadingState
from lol_audio_unpack.gui.controllers.entity_data_store import EntityDataStore
from lol_audio_unpack.gui.task_models import ExecutionTaskResult, QueuedExecutionTask
from lol_audio_unpack.gui.theme import get_accent_text_color_pair
from lol_audio_unpack.gui.view.execution.progress_state import build_global_progress_strip_state
from lol_audio_unpack.gui.view.execution.selection_conflict_dialog import (
    ask_selection_conflict_resolution,
)
from lol_audio_unpack.gui.view.execution.task_creation_card import TaskCreationCard


class ExecutionPage(SmoothScrollArea):
    """执行中心页面。"""

    output_state_refresh_requested = Signal(object)
    task_running_changed = Signal(bool)
    task_queue_busy_changed = Signal(bool)
    log_lines_appended = Signal(object)
    global_progress_state_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.view = configure_transparent_scroll_page(
            self,
            page_object_name="ExecutionPage",
            view_object_name="ExecutionPageView",
        )
        self.gui_config = None
        self._entity_data_store = EntityDataStore(entity_types=("champions", "maps", "special"))
        self._is_task_running = False
        self._is_task_queue_busy = False
        self._shared_data_busy_message = ""
        self._shared_data_block_reason = ""
        self._current_global_progress_state = GlobalProgressStripState()
        self._selection_controller = ExecutionSelectionController()
        self._log_controller = ExecutionLogController(
            initial_lines=(
                "执行中心日志会同步到主窗口底部日志面板。",
                "执行中心已就绪，开始记录任务执行与界面操作。",
                *tuple(get_buffered_log_lines()),
            ),
            max_lines=GUI_LOG_MAX_LINES,
            log_format=GUI_LOG_FORMAT,
            parent=self,
        )
        self._log_controller.log_lines_appended.connect(self.log_lines_appended.emit)
        self.destroyed.connect(self._log_controller.detach_runtime_log_sink)
        self._build_ui()
        qconfig.themeChanged.connect(self._refresh_theme_styles)
        qconfig.themeColorChanged.connect(self._refresh_theme_styles)
        self.destroyed.connect(self._disconnect_theme_signals)
        self._refresh_theme_styles()
        self._queue_controller = ExecutionQueueController(
            build_task_item_tooltip=self._build_task_item_tooltip,
            single_task_mode=True,
            parent=self,
        )
        self.taskBuilderPanel.sync_state_from_widgets()
        self._setup_connections()

    def _build_ui(self) -> None:
        self.expandLayout = QVBoxLayout(self.view)
        apply_page_content_margins(self.expandLayout)
        self.expandLayout.setSpacing(16)

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        title_label = SubtitleLabel("执行中心", self.view)
        self.subtitle_label = CaptionLabel("在这里补充自定义参数并创建任务。", self.view)
        self.subtitle_label.setWordWrap(True)
        header_layout.addWidget(title_label)
        header_layout.addWidget(self.subtitle_label)
        self.expandLayout.addLayout(header_layout)

        self.taskBuilderPanel = TaskCreationCard(self.view)
        self.advancedPanel = self.taskBuilderPanel
        self.advanced_card = self.taskBuilderPanel
        self.champion_ids_input = self.taskBuilderPanel.champion_ids_input
        self.map_ids_input = self.taskBuilderPanel.map_ids_input
        self.vo_filter = self.taskBuilderPanel.vo_filter
        self.max_workers_combo = self.taskBuilderPanel.max_workers_combo
        self.bp_voice_cb = self.taskBuilderPanel.bp_voice_cb
        self.force_update_cb = self.taskBuilderPanel.force_update_cb
        self.integrate_data_cb = self.taskBuilderPanel.integrate_data_cb
        self.extract_task_cb = self.taskBuilderPanel.extract_task_cb
        self.wav_task_cb = self.taskBuilderPanel.wav_task_cb
        self.mapping_task_cb = self.taskBuilderPanel.mapping_task_cb
        self.create_task_btn = self.taskBuilderPanel.create_task_btn
        self.taskActionCard = self.taskBuilderPanel.create_action_card(self.view)
        self.expandLayout.addWidget(self.taskBuilderPanel, 0)
        self.expandLayout.addWidget(self.taskActionCard, 0)
        self.expandLayout.addStretch(1)

        self.bottom_spacing_widget = QWidget(self.view)
        self.bottom_spacing_widget.setFixedHeight(20)
        self.bottom_spacing_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.expandLayout.addWidget(self.bottom_spacing_widget, 0)

    def _refresh_theme_styles(self, *_args: object) -> None:
        """刷新页面引导副标题的强调色。"""
        light, dark = get_accent_text_color_pair()
        self.subtitle_label.setTextColor(light, dark)

    def _disconnect_theme_signals(self, *_args: object) -> None:
        """释放页面持有的全局主题信号连接。"""
        for signal in (qconfig.themeChanged, qconfig.themeColorChanged):
            try:
                signal.disconnect(self._refresh_theme_styles)
            except (RuntimeError, TypeError):
                pass

    def _setup_connections(self) -> None:
        self._queue_controller.task_running_changed.connect(self._set_task_running_state)
        self._queue_controller.task_queue_busy_changed.connect(self._set_task_queue_busy_state)
        self._queue_controller.progress_display_requested.connect(
            lambda update: self._refresh_progress_panel(
                note_text=update.note_text,
                progress_current=update.progress_current,
                progress_total=update.progress_total,
            )
        )
        self._queue_controller.log_requested.connect(lambda event: self._log_gui_event(event.level, event.message))
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
        self.create_task_btn.clicked.connect(self._handle_primary_task_action)
        self.taskBuilderPanel.connect_form_signals(self.taskBuilderPanel.sync_state_from_widgets)
        self.taskBuilderPanel.refresh_summary()
        self._sync_primary_action_button()
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

    def set_shared_data_loading_state(self, state: SharedDataLoadingState) -> None:
        """同步共享数据加载状态到任务创建门禁。"""
        message = str(state.message or "")
        if state.active:
            self._shared_data_busy_message = message
            self._shared_data_block_reason = ""
        else:
            self._shared_data_busy_message = ""
            self._shared_data_block_reason = (
                f"共享数据暂不可用：{message}" if message and message != "实体数据已就绪" else ""
            )
        self._sync_primary_action_button()

    def attach_runtime_log_sink(self, level: str = "INFO") -> None:
        """重新挂载 GUI 运行时日志 sink。"""
        self._log_controller.attach_runtime_log_sink(level)

    def _log_gui_event(self, level: str, message: str) -> None:
        """通过 loguru 记录执行中心的界面交互日志。"""
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
            special_targets = payload.special_targets
            special_target_names = payload.special_target_names
            resource_pack_wads = payload.resource_pack_wads
            source = payload.source
            summary = payload.summary
        else:
            champion_ids = tuple(str(entity_id) for entity_id in payload.get("champion_ids", ()))
            map_ids = tuple(str(entity_id) for entity_id in payload.get("map_ids", ()))
            special_targets = tuple(str(target) for target in payload.get("special_targets", ()))
            special_target_names = tuple(str(name) for name in payload.get("special_target_names", ()))
            resource_pack_wads = tuple(payload.get("resource_pack_wads", ()))
            source = str(payload.get("source", "overview_selection"))
            summary = str(payload.get("summary", "未提供摘要"))

        current_champion_ids, current_map_ids = self.taskBuilderPanel.current_target_ids()
        current_special_targets = self.taskBuilderPanel.current_special_targets()
        current_resource_pack_wads = self.taskBuilderPanel.current_resource_pack_wads()
        if self._selection_controller.has_conflict(
            current_champion_ids=current_champion_ids,
            current_map_ids=current_map_ids,
            incoming_champion_ids=champion_ids,
            incoming_map_ids=map_ids,
            current_special_targets=current_special_targets,
            incoming_special_targets=special_targets,
            current_resource_pack_wads=current_resource_pack_wads,
            incoming_resource_pack_wads=resource_pack_wads,
        ):
            choice = ask_selection_conflict_resolution(
                content=self._selection_controller.build_conflict_dialog_content(
                    current_champion_ids=current_champion_ids,
                    current_map_ids=current_map_ids,
                    incoming_champion_ids=champion_ids,
                    incoming_map_ids=map_ids,
                    current_special_targets=current_special_targets,
                    incoming_special_targets=special_targets,
                    current_resource_pack_wads=current_resource_pack_wads,
                    incoming_resource_pack_wads=resource_pack_wads,
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
            current_special_targets=current_special_targets,
            incoming_special_targets=special_targets,
            current_special_target_names=self.taskBuilderPanel.current_special_target_names(),
            incoming_special_target_names=special_target_names,
            current_resource_pack_wads=current_resource_pack_wads,
            incoming_resource_pack_wads=resource_pack_wads,
        )
        if update is None:
            self._log_gui_event("info", "[同步] 已取消从实体总览同步选择。")
            return None

        all_champion_ids = {str(row.get("id")) for row in self._entity_data_store.rows_for("champions")}
        all_map_ids = {str(row.get("id")) for row in self._entity_data_store.rows_for("maps")}
        select_all = (
            not update.special_targets
            and bool(all_champion_ids and all_map_ids)
            and (set(update.champion_ids) == all_champion_ids and set(update.map_ids) == all_map_ids)
        )
        self.taskBuilderPanel.apply_selected_entities(
            champion_ids=update.champion_ids,
            map_ids=update.map_ids,
            source=update.source,
            summary=update.summary,
            select_all=select_all,
            special_targets=update.special_targets,
            special_target_names=update.special_target_names,
            resource_pack_wads=update.resource_pack_wads,
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
        """返回队列中是否仍存在等待或运行任务。"""
        return self._queue_controller.has_incomplete_tasks()

    def _build_task_item_tooltip(self, task: QueuedExecutionTask) -> str:
        """构造任务悬停提示文本。"""
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
        self._sync_primary_action_button()
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

    def _refresh_progress_panel(
        self,
        *,
        note_text: str | None = None,
        progress_current: int | None = None,
        progress_total: int | None = None,
    ) -> None:
        """刷新主窗口底部全局进度条状态。"""
        counts = self._queue_controller.queue_status_counts()
        running_task = self._queue_controller.find_running_task()
        next_global_progress_state = build_global_progress_strip_state(
            counts=counts,
            running_task=running_task,
            note_text=note_text,
            progress_current=progress_current,
            progress_total=progress_total,
        )
        if next_global_progress_state == self._current_global_progress_state:
            return
        self._current_global_progress_state = next_global_progress_state
        self.global_progress_state_changed.emit(self._current_global_progress_state)

    def current_global_progress_state(self) -> GlobalProgressStripState:
        """返回当前应同步到主窗口底部的全局进度条状态。"""
        return self._current_global_progress_state

    def _sync_primary_action_button(self) -> None:
        """根据当前运行态切换主按钮文案。"""
        if self._is_task_running:
            self.create_task_btn.setText("取消")
            self.create_task_btn.setToolTip("取消当前运行中的任务。")
            return
        if self._shared_data_busy_message:
            self.create_task_btn.setText("准备数据中")
            self.create_task_btn.setToolTip(f"后台数据准备中：{self._shared_data_busy_message} 完成后才能创建任务。")
            return
        self.create_task_btn.setText("创建任务")
        self.create_task_btn.setToolTip(self._shared_data_block_reason)

    def _handle_primary_task_action(self) -> None:
        """根据当前运行态分派创建或取消行为。"""
        if self._is_task_running:
            self.request_cancel_task()
            return
        self._queue_task_draft()

    def request_cancel_task(self) -> bool:
        """请求取消当前运行中的任务。"""
        if not self._is_task_running:
            return False
        if not self._confirm_force_stop_task():
            return False
        return self._queue_controller.cancel_active_task()

    def _confirm_force_stop_task(self) -> bool:
        """弹出全局确认框，确认是否强制结束当前任务。"""
        dialog = QMessageBox(self._feedback_parent())
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("结束当前任务")
        dialog.setText("当前任务仍在执行。")
        dialog.setInformativeText("确认后会强制结束当前任务，未完成的执行过程会立即停止。")
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        dialog.button(QMessageBox.StandardButton.Yes).setText("结束任务")
        dialog.button(QMessageBox.StandardButton.Cancel).setText("取消")
        return dialog.exec() == int(QMessageBox.StandardButton.Yes)

    def _queue_task_draft(self) -> None:
        """将当前界面参数写入任务队列，并自动开始首个任务。"""
        if self._shared_data_busy_message:
            message = f"后台数据仍在准备：{self._shared_data_busy_message}，完成后再创建任务。"
            self._log_gui_event("warning", f"[队列] {message}")
            show_feedback_infobar(
                title="后台数据准备中",
                content=message,
                parent=self._feedback_parent(),
                level="warning",
                position=InfoBarPosition.TOP,
            )
            return

        if self._shared_data_block_reason:
            self._log_gui_event("warning", f"[队列] {self._shared_data_block_reason}")
            show_feedback_infobar(
                title="无法创建任务",
                content=self._shared_data_block_reason,
                parent=self._feedback_parent(),
                level="warning",
                position=InfoBarPosition.TOP,
            )
            return

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

        block_reason = get_block_reason(self.gui_config)
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
        """填充指定数量的 mock 队列项，方便调试全局进度状态。"""
        return self._queue_controller.fill_mock_queue(count=count)

    def _debug_clear_mock_queue(self) -> str:
        """清空当前调试队列并恢复空状态。"""
        return self._queue_controller.clear_mock_queue()

    def _debug_inspect_queue(self) -> str:
        """返回当前队列与卡片尺寸信息。"""
        return self._queue_controller.inspect_queue(
            builder_card_height=self.taskBuilderPanel.height(),
        )

    def _debug_simulate_terminal_result(self, status: str) -> str:
        """注入一个可人工验收的 typed terminal result。"""
        return self._queue_controller.simulate_terminal_result(status)

    def shutdown_background_tasks(self) -> None:
        """在窗口关闭前清理执行中心后台任务引用。"""
        self._queue_controller.shutdown()

    def current_log_text(self) -> str:
        """返回执行中心当前累计日志文本。"""
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
