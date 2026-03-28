"""执行中心页面，承接任务队列、参数配置与日志同步。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from loguru import logger
from PySide6.QtCore import QObject, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    ExpandLayout,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SegmentedWidget,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
)
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common import (
    GUI_LOG_FORMAT,
    GUI_LOG_MAX_LINES,
    apply_smooth_scroll_enabled,
    get_buffered_log_lines,
    show_feedback_infobar,
)
from lol_audio_unpack.gui.common.style import apply_page_content_margins
from lol_audio_unpack.gui.components.accordion_setting_card import FormAccordionCard
from lol_audio_unpack.gui.service.task_runner import run_execution_task
from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    ExecutionTaskProgress,
    ExecutionTaskResult,
    OutputStateRefreshRequest,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.workers import TaskWorker


def _parse_csv_ids(text: str) -> tuple[str, ...]:
    """将逗号分隔的 ID 输入解析为字符串元组。"""
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _parse_csv_int_ids(text: str, *, label: str) -> tuple[int, ...] | None:
    """将逗号分隔的数字 ID 输入解析为整数元组。

    Args:
        text: 输入框中的原始文本。
        label: 用于错误提示的人类可读标签。

    Returns:
        解析成功后的整数元组；为空时返回 ``None``。

    Raises:
        ValueError: 当存在非数字 ID 时抛出。
    """
    raw_ids = _parse_csv_ids(text)
    if not raw_ids:
        return None

    try:
        return tuple(int(entity_id) for entity_id in raw_ids)
    except ValueError as exc:  # pragma: no cover - 由下层错误文本补充即可
        raise ValueError(f"{label} 仅支持逗号分隔的数字 ID。") from exc


def _build_target_summary(champion_ids: tuple[str, ...], map_ids: tuple[str, ...]) -> str:
    """构造当前目标范围摘要。"""
    if not champion_ids and not map_ids:
        return "全部英雄+地图"
    return f"目标：英雄 {len(champion_ids)} 个，地图 {len(map_ids)} 个"


def _build_task_scope_summary(*, include_extract: bool, include_mapping: bool) -> str:
    """构造当前任务包含的执行步骤摘要。"""
    parts: list[str] = []
    if include_extract:
        parts.append("音频解包")
    if include_mapping:
        parts.append("事件映射")
    return " + ".join(parts) if parts else "未选择执行内容"

TASK_ITEM_ROLE = int(Qt.ItemDataRole.UserRole)
QUEUE_VISIBLE_ROW_COUNT = 3


@dataclass(slots=True, frozen=True)
class _ExecutionTaskFormDefaults:
    """执行页内部维护的任务表单默认值。"""

    vo_filter_key: str = "VO"
    max_workers_text: str = "4"
    with_bp_vo: bool = True
    force_update: bool = False
    integrate_data: bool = True


@dataclass(slots=True, frozen=True)
class _ExecutionTaskFormState:
    """执行页当前任务表单的统一状态快照。"""

    champion_ids: tuple[str, ...] = ()
    map_ids: tuple[str, ...] = ()
    include_extract: bool = True
    include_mapping: bool = True
    vo_filter_key: str = "VO"
    max_workers_text: str = "4"
    with_bp_vo: bool = True
    force_update: bool = False
    integrate_data: bool = True

    def target_summary(self) -> str:
        """返回当前目标范围摘要。"""
        return _build_target_summary(self.champion_ids, self.map_ids)

    def task_scope_summary(self) -> str:
        """返回当前勾选的任务步骤摘要。"""
        return _build_task_scope_summary(
            include_extract=self.include_extract,
            include_mapping=self.include_mapping,
        )


def _build_queue_item_text(*, task_id: int, status: str, summary: str) -> str:
    """构造任务队列项文本。"""
    return f"#{task_id} · [{status}] {summary}"


def _quote_cli_arg(arg: str) -> str:
    """按 PowerShell 习惯格式化单个命令行参数。"""
    if not arg:
        return "''"

    safe_chars = "-_./,:=\\"
    if all(char.isalnum() or char in safe_chars for char in arg):
        return arg
    return "'" + arg.replace("'", "''") + "'"


def _merge_unique_ids(base_ids: tuple[str, ...], incoming_ids: tuple[str, ...]) -> tuple[str, ...]:
    """合并两组 ID，并保持原有顺序去重。"""
    merged = list(base_ids)
    seen = set(base_ids)
    for entity_id in incoming_ids:
        if entity_id not in seen:
            seen.add(entity_id)
            merged.append(entity_id)
    return tuple(merged)


class _GuiLogTextRelay(QObject):
    """将 loguru 文本 sink 转发为 Qt 信号。"""

    message_received = Signal(str)

    def write(self, message: str) -> None:
        """接收 loguru 已格式化文本并转发。

        Args:
            message: loguru 已格式化后的单条日志文本。
        """
        normalized = message.rstrip()
        if normalized:
            self.message_received.emit(normalized)

    def flush(self) -> None:
        """兼容 file-like sink 所需的空刷新接口。"""


class AdvancedInputCard(FormAccordionCard):
    """执行中心的高级输入折叠卡。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            FIF.SETTING,
            "自定义输入",
            "需要精细调整时，可以在这里补充范围和任务选项。",
            parent,
        )
        self.setExpand(True)

        self.champion_ids_input = LineEdit()
        self.champion_ids_input.setPlaceholderText("英雄 ID，如 1,103,555")
        self.champion_ids_input.setMinimumWidth(260)
        self.champion_ids_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.champion_ids_input.setClearButtonEnabled(True)

        self.map_ids_input = LineEdit()
        self.map_ids_input.setPlaceholderText("地图 ID，如 0,11,12")
        self.map_ids_input.setMinimumWidth(260)
        self.map_ids_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.map_ids_input.setClearButtonEnabled(True)

        self.vo_filter = SegmentedWidget()
        self.vo_filter.addItem("VO", "仅 VO")
        self.vo_filter.addItem("ALL", "全部类型")
        self.vo_filter.setCurrentItem("VO")
        self.vo_filter.setMinimumWidth(220)
        self.vo_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.max_workers_combo = ComboBox()
        self.max_workers_combo.addItems(["1", "2", "4", "8", "16", "32", "64"])
        self.max_workers_combo.setCurrentText("4")
        self.max_workers_combo.setMinimumWidth(120)
        self.max_workers_combo.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)

        self.bp_voice_cb = CheckBox("启用")
        self.bp_voice_cb.setChecked(True)
        self.force_update_cb = CheckBox("启用")
        self.integrate_data_cb = CheckBox("启用")

        self.add_form_row("英雄 ID", "多个英雄 ID 用逗号分隔，如 1,103,555", self.champion_ids_input)
        self.add_form_row("地图 ID", "多个地图 ID 用逗号分隔，如 0,11,12", self.map_ids_input)
        self.add_form_row("音频范围", "默认只处理 VO，需要时可切换为全部类型", self.vo_filter)
        self.add_form_row("并发数", "设置任务并发数；一般不建议超过 CPU 线程数", self.max_workers_combo)
        self.add_form_row("附加 BP 语音", "默认同时处理 BP 语音", self.bp_voice_cb)
        self.add_form_row("强制刷新缓存", "执行前重新刷新当前任务需要的缓存", self.force_update_cb)
        self.add_form_row(
            "整合数据文件",
            "映射任务时额外生成整合数据，便于后续整理和查看",
            self.integrate_data_cb,
        )


class ExecutionPage(SmoothScrollArea):
    """执行中心页面。"""

    output_state_refresh_requested = Signal(object)
    task_running_changed = Signal(bool)
    task_queue_busy_changed = Signal(bool)
    log_lines_appended = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("ExecutionPage")
        self.view = QWidget(self)
        self.view.setObjectName("ExecutionPageView")
        self.view.setStyleSheet("QWidget#ExecutionPageView{background: transparent}")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea {border: none; background: transparent;}")
        self.gui_config = None
        self._task_form_defaults = _ExecutionTaskFormDefaults()
        self._task_form_state = _ExecutionTaskFormState()
        self._cached_data: dict[str, list[dict[str, Any]]] = {"champions": [], "maps": []}
        self._draft_count = 0
        self._is_task_running = False
        self._is_task_queue_busy = False
        self._log_lines: deque[str] = deque(
            [
                "执行中心日志会同步到主窗口底部日志面板。",
                "执行中心已就绪，开始记录任务队列与界面操作。",
            ],
            maxlen=GUI_LOG_MAX_LINES,
        )
        self._log_lines.extend(get_buffered_log_lines())
        self._pending_log_lines: list[str] = []
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setSingleShot(True)
        self._log_flush_timer.setInterval(0)
        self._log_flush_timer.timeout.connect(self._flush_pending_log_lines)
        self._runtime_log_relay = _GuiLogTextRelay(self)
        self._runtime_log_relay.message_received.connect(self._queue_runtime_log_line)
        self._runtime_log_sink_id: int | None = None
        self._synced_selection: dict[str, Any] = self._build_empty_synced_selection()
        self._active_task_id: int | None = None
        self._active_worker: TaskWorker | None = None
        self._stage_completion_notifications: set[tuple[int, str]] = set()
        self.destroyed.connect(self._detach_runtime_log_sink)
        self._build_ui()
        self._apply_task_form_defaults()
        self._sync_task_form_state_from_widgets()
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
        subtitle_label = CaptionLabel("在这里创建任务、查看进度，也可以复制当前任务命令。", header_widget)
        subtitle_label.setWordWrap(True)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        header_widget.resize(header_widget.width(), header_widget.sizeHint().height())
        self.expandLayout.addWidget(header_widget)

        top_widget = QWidget(self.view)
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(12)

        # Keep task creation in one compact card so the page stays focused on queue management.
        self.task_builder_card = CardWidget(self.view)
        builder_layout = QVBoxLayout(self.task_builder_card)
        builder_layout.setContentsMargins(18, 16, 18, 18)
        builder_layout.setSpacing(12)
        builder_title = StrongBodyLabel("创建任务", self.task_builder_card)
        builder_hint = CaptionLabel("确认当前目标后就能创建任务；如果想在命令行执行，也可以先复制命令。", self.task_builder_card)
        builder_hint.setWordWrap(True)
        builder_layout.addWidget(builder_title)
        builder_layout.addWidget(builder_hint)

        target_widget = QWidget(self.task_builder_card)
        target_layout = QVBoxLayout(target_widget)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(6)
        self.target_title_label = BodyLabel("当前目标", target_widget)
        self.target_summary_value = StrongBodyLabel("全部英雄+地图", target_widget)
        self.target_summary_value.setWordWrap(True)
        target_layout.addWidget(self.target_title_label)
        target_layout.addWidget(self.target_summary_value)

        action_widget = QWidget(self.task_builder_card)
        action_layout = QVBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(10)

        task_kind_widget = QWidget(action_widget)
        task_kind_layout = QVBoxLayout(task_kind_widget)
        task_kind_layout.setContentsMargins(0, 0, 0, 0)
        task_kind_layout.setSpacing(6)
        self.task_kind_title_label = BodyLabel("执行内容", task_kind_widget)
        task_kind_row = QHBoxLayout()
        task_kind_row.setContentsMargins(0, 0, 0, 0)
        task_kind_row.setSpacing(12)
        self.extract_task_cb = CheckBox("音频解包")
        self.extract_task_cb.setChecked(True)
        self.mapping_task_cb = CheckBox("事件映射")
        self.mapping_task_cb.setChecked(True)
        task_kind_row.addWidget(self.extract_task_cb)
        task_kind_row.addWidget(self.mapping_task_cb)
        task_kind_row.addStretch(1)
        self.task_builder_summary_label = StrongBodyLabel("将创建：音频解包和事件映射。", task_kind_widget)
        self.task_builder_summary_label.setWordWrap(True)
        task_kind_layout.addWidget(self.task_kind_title_label)
        task_kind_layout.addLayout(task_kind_row)
        task_kind_layout.addWidget(self.task_builder_summary_label)

        builder_layout.addWidget(target_widget)
        action_layout.addWidget(task_kind_widget)

        builder_button_row = QHBoxLayout()
        builder_button_row.setContentsMargins(0, 0, 0, 0)
        builder_button_row.setSpacing(8)
        self.create_task_btn = PrimaryPushButton("创建任务", self.task_builder_card)
        self.copy_cli_btn = PushButton("复制 CLI 命令", self.task_builder_card)
        builder_button_row.addStretch(1)
        builder_button_row.addWidget(self.create_task_btn)
        builder_button_row.addWidget(self.copy_cli_btn)
        action_layout.addLayout(builder_button_row)

        builder_layout.addWidget(action_widget)

        self.progress_card = CardWidget(self.view)
        progress_layout = QVBoxLayout(self.progress_card)
        progress_layout.setContentsMargins(18, 16, 18, 16)
        progress_layout.setSpacing(10)
        progress_title = StrongBodyLabel("任务进度", self.progress_card)
        self.task_status_label = CaptionLabel("状态：界面已就绪，等待创建第一条任务。", self.progress_card)
        self.task_status_label.hide()
        self.task_progress_bar = ProgressBar(self.progress_card)
        self.task_progress_bar.setRange(0, 1)
        self.task_progress_bar.setValue(0)
        self.task_progress_note = BodyLabel("当前进度：暂无运行中的任务。", self.progress_card)
        self.queue_progress_label = CaptionLabel("任务队列：0 条", self.progress_card)
        self.draft_list = ListWidget(self.progress_card)
        self.draft_list.setAlternatingRowColors(True)
        progress_layout.addWidget(progress_title)
        progress_layout.addWidget(self.task_progress_bar)
        progress_layout.addWidget(self.task_progress_note)
        progress_layout.addWidget(self.queue_progress_label)
        progress_layout.addWidget(self.draft_list)
        top_layout.addWidget(self.progress_card, 1)
        top_layout.addWidget(self.task_builder_card, 1)
        top_widget.resize(top_widget.width(), top_widget.sizeHint().height())
        self.expandLayout.addWidget(top_widget)

        self.advanced_card = AdvancedInputCard(self.view)
        self.champion_ids_input = self.advanced_card.champion_ids_input
        self.map_ids_input = self.advanced_card.map_ids_input
        self.vo_filter = self.advanced_card.vo_filter
        self.max_workers_combo = self.advanced_card.max_workers_combo
        self.bp_voice_cb = self.advanced_card.bp_voice_cb
        self.force_update_cb = self.advanced_card.force_update_cb
        self.integrate_data_cb = self.advanced_card.integrate_data_cb
        self.expandLayout.addWidget(self.advanced_card)
        self.bottom_spacing_widget = QWidget(self.view)
        self.bottom_spacing_widget.setFixedHeight(20)
        self.expandLayout.addWidget(self.bottom_spacing_widget)
        self._set_queue_placeholder()
        self._apply_queue_list_height()

    def _setup_connections(self) -> None:
        self.create_task_btn.clicked.connect(self._queue_task_draft)
        self.copy_cli_btn.clicked.connect(self._copy_cli_command)
        self.champion_ids_input.textChanged.connect(self._sync_task_form_state_from_widgets)
        self.map_ids_input.textChanged.connect(self._sync_task_form_state_from_widgets)
        self.extract_task_cb.stateChanged.connect(self._sync_task_form_state_from_widgets)
        self.mapping_task_cb.stateChanged.connect(self._sync_task_form_state_from_widgets)
        self.vo_filter.currentItemChanged.connect(self._sync_task_form_state_from_widgets)
        self.max_workers_combo.currentTextChanged.connect(self._sync_task_form_state_from_widgets)
        self.bp_voice_cb.stateChanged.connect(self._sync_task_form_state_from_widgets)
        self.force_update_cb.stateChanged.connect(self._sync_task_form_state_from_widgets)
        self.integrate_data_cb.stateChanged.connect(self._sync_task_form_state_from_widgets)
        self.draft_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.draft_list.customContextMenuRequested.connect(self._open_task_queue_context_menu)
        self._refresh_task_builder_state()
        self._refresh_progress_panel()

    def set_gui_config(self, cfg) -> None:
        """注入 GUI 配置并刷新默认值。"""
        self.gui_config = cfg
        self._sync_task_form_state_from_widgets()
        self._refresh_task_builder_state()
        fallback_enabled = bool(getattr(cfg, "smooth_scroll_enabled", False))
        self.set_smooth_scroll_enabled(
            page_enabled=bool(getattr(cfg, "page_smooth_scroll_enabled", fallback_enabled)),
            widget_enabled=bool(getattr(cfg, "widget_smooth_scroll_enabled", fallback_enabled)),
        )

    def set_entity_data(self, entity_type: str, data: list[dict[str, Any]]) -> None:
        """更新当前已加载实体目录摘要。"""
        if entity_type not in self._cached_data:
            return
        self._cached_data[entity_type] = data

    def update_entity_rows(self, entity_type: str, rows: list[dict[str, Any]]) -> None:
        """按实体 ID 增量更新页面缓存中的摘要行。"""
        if entity_type not in self._cached_data or not rows:
            return

        row_by_id = {str(row["id"]): row for row in rows}
        merged_rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for row in self._cached_data[entity_type]:
            entity_id = str(row.get("id", ""))
            if entity_id in row_by_id:
                merged_rows.append(row_by_id[entity_id])
                seen_ids.add(entity_id)
            else:
                merged_rows.append(row)

        for row in rows:
            entity_id = str(row["id"])
            if entity_id not in seen_ids:
                merged_rows.append(row)

        self._cached_data[entity_type] = merged_rows

    def clear_entity_data(self) -> None:
        """清空当前已加载实体目录摘要。"""
        self._cached_data = {"champions": [], "maps": []}

    def attach_runtime_log_sink(self, level: str = "INFO") -> None:
        """重新挂载 GUI 运行时日志 sink。"""
        self._detach_runtime_log_sink()
        # 独立实例化执行中心时，也要确保项目命名空间日志不会被静默丢弃。
        logger.enable("lol_audio_unpack")
        self._runtime_log_sink_id = logger.add(
            self._runtime_log_relay,
            level=level.upper(),
            colorize=False,
            enqueue=False,
            format=GUI_LOG_FORMAT,
        )

    def _log_gui_event(self, level: str, message: str) -> None:
        """通过 loguru 记录执行中心的界面交互日志。

        Args:
            level: loguru 使用的日志级别名称。
            message: 需要写入统一日志链路的文本。
        """
        logger.log(level.upper(), message)

    def set_selected_entities(
        self,
        payload: dict[str, Any],
        feedback_parent: QWidget | None = None,
    ) -> str | None:
        """接收来自实体总览的选择结果。"""
        champion_ids = tuple(str(entity_id) for entity_id in payload.get("champion_ids", ()))
        map_ids = tuple(str(entity_id) for entity_id in payload.get("map_ids", ()))
        source = str(payload.get("source", "overview_selection"))
        summary = str(payload.get("summary", "未提供摘要"))

        current_champion_ids, current_map_ids = self._current_target_ids()
        if (current_champion_ids or current_map_ids) and (
            current_champion_ids != champion_ids or current_map_ids != map_ids
        ):
            choice = self._ask_sync_conflict_resolution(
                current_champion_ids=current_champion_ids,
                current_map_ids=current_map_ids,
                incoming_champion_ids=champion_ids,
                incoming_map_ids=map_ids,
                feedback_parent=feedback_parent,
            )
            if choice == "cancel":
                self._log_gui_event("info", "[同步] 已取消从实体总览同步选择。")
                return None
            if choice == "merge":
                champion_ids = _merge_unique_ids(current_champion_ids, champion_ids)
                map_ids = _merge_unique_ids(current_map_ids, map_ids)
                summary = (
                    f"已合并到当前任务：{len(champion_ids)} 个英雄、{len(map_ids)} 张地图。"
                    "请前往执行中心继续创建任务。"
                )
            else:
                summary = (
                    f"已同步 {len(champion_ids)} 个英雄、{len(map_ids)} 张地图，"
                    "请前往执行中心继续创建任务。"
                )
        elif summary == "未提供摘要":
            summary = (
                f"已同步 {len(champion_ids)} 个英雄、{len(map_ids)} 张地图，"
                "请前往执行中心继续创建任务。"
            )

        self._apply_selected_entities(
            champion_ids=champion_ids,
            map_ids=map_ids,
            source=source,
            summary=summary,
        )
        return summary

    def is_task_running(self) -> bool:
        """返回当前是否存在正在执行的任务。"""
        return self._is_task_running

    def has_incomplete_tasks(self) -> bool:
        """返回队列中是否仍存在等待或运行中的任务。"""
        for index in range(self.draft_list.count()):
            item = self.draft_list.item(index)
            payload = item.data(TASK_ITEM_ROLE)
            if not isinstance(payload, QueuedExecutionTask):
                continue
            if payload.status in {TASK_STATUS_WAITING, TASK_STATUS_RUNNING}:
                return True
        return False

    def _build_empty_synced_selection(self) -> dict[str, Any]:
        """返回空的总览同步状态。"""
        return {
            "source": "未同步",
            "champion_ids": (),
            "map_ids": (),
            "summary": "尚未从实体总览同步选择。",
        }

    def _build_output_state_refresh_request(
        self,
        task: QueuedExecutionTask,
        task_result: ExecutionTaskResult,
    ) -> OutputStateRefreshRequest:
        """根据任务快照和执行结果推导输出状态刷新范围。"""
        completed_steps = set(task_result.completed_steps)
        if not ({"音频解包", "事件映射"} & completed_steps):
            return OutputStateRefreshRequest(requires_full_refresh=True)

        task_params = task.draft.task_params
        champion_ids = (
            tuple(str(entity_id) for entity_id in task_params.champion_ids)
            if task_params.champion_ids is not None
            else ()
        )
        map_ids = (
            tuple(str(entity_id) for entity_id in task_params.map_ids)
            if task_params.map_ids is not None
            else ()
        )

        if not champion_ids and not map_ids:
            return OutputStateRefreshRequest(requires_full_refresh=True)

        return OutputStateRefreshRequest(
            champion_ids=champion_ids,
            map_ids=map_ids,
        )

    def _current_selection_source(self) -> str:
        """返回当前任务输入的来源标识。"""
        champion_ids, map_ids = self._current_target_ids()
        if (
            self._synced_selection["source"] != "未同步"
            and champion_ids == tuple(self._synced_selection["champion_ids"])
            and map_ids == tuple(self._synced_selection["map_ids"])
        ):
            return str(self._synced_selection["source"])
        if champion_ids or map_ids:
            return "manual_input"
        return "default_scope"

    def _build_task_draft(self) -> ExecutionTaskDraft:
        """根据当前界面状态创建任务草稿快照。"""
        state = self._task_form_state
        champion_ids = _parse_csv_int_ids(",".join(state.champion_ids), label="英雄 ID")
        map_ids = _parse_csv_int_ids(",".join(state.map_ids), label="地图 ID")
        exclude_types = ("SFX", "MUSIC") if state.vo_filter_key == "VO" else ()
        return ExecutionTaskDraft(
            source=self._current_selection_source(),
            source_summary=state.target_summary(),
            context_input=(
                self.gui_config.to_app_context_input_snapshot()
                if self.gui_config
                else AppContextInputSnapshot()
            ),
            task_params=ExecutionTaskParamsSnapshot(
                champion_ids=champion_ids,
                map_ids=map_ids,
                run_update=state.force_update,
                run_extract=state.include_extract,
                run_mapping=state.include_mapping,
                max_workers=int(state.max_workers_text),
                with_bp_vo=state.with_bp_vo,
                exclude_types=exclude_types,
                integrate_data=state.integrate_data,
            ),
        )

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

    def _sync_task_queue_busy_state(self) -> None:
        """根据当前队列内容重新计算忙碌状态。"""
        self._set_task_queue_busy_state(self.has_incomplete_tasks())

    def _find_task_item_by_id(self, task_id: int) -> QListWidgetItem | None:
        """按任务编号查找对应的列表项。"""
        for index in range(self.draft_list.count()):
            item = self.draft_list.item(index)
            payload = item.data(TASK_ITEM_ROLE)
            if isinstance(payload, QueuedExecutionTask) and payload.task_id == task_id:
                return item
        return None

    def _apply_selected_entities(
        self,
        *,
        champion_ids: tuple[str, ...],
        map_ids: tuple[str, ...],
        source: str,
        summary: str,
    ) -> None:
        """将实体总览选择应用到执行中心输入区。"""
        self._synced_selection = {
            "source": source,
            "champion_ids": champion_ids,
            "map_ids": map_ids,
            "summary": summary,
        }
        self.champion_ids_input.setText(",".join(champion_ids))
        self.map_ids_input.setText(",".join(map_ids))
        self._log_gui_event("info", f"[同步] {summary}")
        self._refresh_task_builder_state()

    def _feedback_parent(self, feedback_parent: QWidget | None = None) -> QWidget:
        """返回全局通知应挂载的父级窗口。"""
        if feedback_parent is not None:
            return feedback_parent

        window = self.window()
        return window if isinstance(window, QWidget) else self

    def _ask_sync_conflict_resolution(
        self,
        *,
        current_champion_ids: tuple[str, ...],
        current_map_ids: tuple[str, ...],
        incoming_champion_ids: tuple[str, ...],
        incoming_map_ids: tuple[str, ...],
        feedback_parent: QWidget | None = None,
    ) -> str:
        """询问实体总览同步与当前输入冲突时的处理方式。"""
        dialog = MessageBox(
            "更新当前任务目标",
            (
                "执行中心里已经填写了目标。\n\n"
                f"当前任务：{_build_target_summary(current_champion_ids, current_map_ids)}\n"
                f"新选择：{_build_target_summary(incoming_champion_ids, incoming_map_ids)}\n\n"
                "你可以选择覆盖、合并，或取消这次同步。"
            ),
            self._feedback_parent(feedback_parent),
        )
        dialog.yesButton.setText("覆盖")
        dialog.cancelButton.setText("取消")

        merge_button = PushButton("合并", dialog.buttonGroup)
        merge_button.setAttribute(Qt.WA_LayoutUsesWidgetRect)
        dialog.buttonLayout.insertWidget(0, merge_button, 1, Qt.AlignVCenter)

        result = {"choice": "cancel"}

        def choose_merge() -> None:
            result["choice"] = "merge"
            dialog.accept()

        dialog.yesSignal.connect(lambda: result.__setitem__("choice", "replace"))
        dialog.cancelSignal.connect(lambda: result.__setitem__("choice", "cancel"))
        merge_button.clicked.connect(choose_merge)
        dialog.exec()
        return str(result["choice"])

    def _apply_task_form_defaults(self) -> None:
        """将执行页维护的默认值应用到任务表单控件。"""
        defaults = self._task_form_defaults
        self.vo_filter.setCurrentItem(defaults.vo_filter_key)
        self.max_workers_combo.setCurrentText(defaults.max_workers_text)
        self.bp_voice_cb.setChecked(defaults.with_bp_vo)
        self.force_update_cb.setChecked(defaults.force_update)
        self.integrate_data_cb.setChecked(defaults.integrate_data)

    def _build_task_form_state_from_widgets(self) -> _ExecutionTaskFormState:
        """从当前控件值提取一份任务表单状态快照。"""
        return _ExecutionTaskFormState(
            champion_ids=_parse_csv_ids(self.champion_ids_input.text()),
            map_ids=_parse_csv_ids(self.map_ids_input.text()),
            include_extract=self.extract_task_cb.isChecked(),
            include_mapping=self.mapping_task_cb.isChecked(),
            vo_filter_key=self.vo_filter.currentRouteKey() or self._task_form_defaults.vo_filter_key,
            max_workers_text=self.max_workers_combo.currentText(),
            with_bp_vo=self.bp_voice_cb.isChecked(),
            force_update=self.force_update_cb.isChecked(),
            integrate_data=self.integrate_data_cb.isChecked(),
        )

    def _sync_task_form_state_from_widgets(self, *_args) -> None:
        """将当前控件值同步到执行页维护的任务表单状态。"""
        self._task_form_state = self._build_task_form_state_from_widgets()
        self._refresh_task_builder_state()

    def _apply_task_form_state(self) -> None:
        """将当前任务表单状态反向应用到控件。"""
        state = self._task_form_state
        self.champion_ids_input.setText(",".join(state.champion_ids))
        self.map_ids_input.setText(",".join(state.map_ids))
        self.extract_task_cb.setChecked(state.include_extract)
        self.mapping_task_cb.setChecked(state.include_mapping)
        self.vo_filter.setCurrentItem(state.vo_filter_key)
        self.max_workers_combo.setCurrentText(state.max_workers_text)
        self.bp_voice_cb.setChecked(state.with_bp_vo)
        self.force_update_cb.setChecked(state.force_update)
        self.integrate_data_cb.setChecked(state.integrate_data)
        self._refresh_task_builder_state()

    def _current_target_ids(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """根据当前输入框返回准备中的英雄 / 地图 ID。"""
        return self._task_form_state.champion_ids, self._task_form_state.map_ids

    def _selected_task_scope_summary(self) -> str:
        """返回当前复选项对应的执行步骤摘要。"""
        return self._task_form_state.task_scope_summary()

    def _append_target_operation_args(
        self,
        args: list[str],
        *,
        operation_name: str,
        champion_ids: tuple[str, ...],
        map_ids: tuple[str, ...],
    ) -> None:
        """按当前目标范围追加一组 CLI 任务参数。"""
        all_flag = f"--{operation_name}"
        champion_flag = f"--{operation_name}-champions"
        map_flag = f"--{operation_name}-maps"
        if champion_ids or map_ids:
            if champion_ids:
                args.extend([champion_flag, ",".join(champion_ids)])
            if map_ids:
                args.extend([map_flag, ",".join(map_ids)])
            return

        args.append(all_flag)

    def _current_task_config_summary(self) -> str:
        """构造当前任务配置摘要。"""
        state = self._task_form_state
        draft_summary = state.target_summary()
        task_scope_summary = state.task_scope_summary()
        return (
            f"{task_scope_summary} · {draft_summary} · "
            f"VO={state.vo_filter_key} · "
            f"BP={state.with_bp_vo} · "
            f"刷新缓存={state.force_update} · "
            f"整合={state.integrate_data} · "
            f"并发={state.max_workers_text}"
        )

    def _refresh_task_builder_state(self) -> None:
        """同步任务创建区和进度区中的摘要文案。"""
        state = self._task_form_state
        task_scope_summary = state.task_scope_summary()
        self.target_summary_value.setText(state.target_summary())

        if task_scope_summary == "未选择执行内容":
            self.task_builder_summary_label.setText("请至少勾选一个执行步骤后再创建任务。")
        else:
            self.task_builder_summary_label.setText(
                f"将创建：{task_scope_summary.replace(' + ', '和')}。"
            )

    def _build_cli_command_text(self) -> str | None:
        """根据当前勾选参数构造可复制的 CLI 命令。"""
        state = self._task_form_state
        if state.task_scope_summary() == "未选择执行内容":
            return None

        champion_ids, map_ids = state.champion_ids, state.map_ids
        args = ["uv", "run", "unpack"]

        if state.force_update:
            self._append_target_operation_args(
                args,
                operation_name="update",
                champion_ids=champion_ids,
                map_ids=map_ids,
            )
            args.append("--force")

        if state.include_extract:
            self._append_target_operation_args(
                args,
                operation_name="extract",
                champion_ids=champion_ids,
                map_ids=map_ids,
            )

        if state.include_mapping:
            self._append_target_operation_args(
                args,
                operation_name="mapping",
                champion_ids=champion_ids,
                map_ids=map_ids,
            )

        args.extend(["--max-workers", state.max_workers_text])
        args.append("--with-bp-vo" if state.with_bp_vo else "--no-with-bp-vo")
        if state.vo_filter_key == "VO":
            args.extend(["--exclude-type", "SFX,MUSIC"])
        if state.include_mapping and state.integrate_data:
            args.append("--integrate-data")

        return " ".join(_quote_cli_arg(arg) for arg in args)

    def _reset_custom_inputs_to_defaults(self) -> None:
        """将自定义输入区恢复到默认状态。"""
        current_state = self._task_form_state
        defaults = self._task_form_defaults
        self._synced_selection = self._build_empty_synced_selection()
        self._task_form_state = _ExecutionTaskFormState(
            champion_ids=(),
            map_ids=(),
            include_extract=current_state.include_extract,
            include_mapping=current_state.include_mapping,
            vo_filter_key=defaults.vo_filter_key,
            max_workers_text=defaults.max_workers_text,
            with_bp_vo=defaults.with_bp_vo,
            force_update=defaults.force_update,
            integrate_data=defaults.integrate_data,
        )
        self._apply_task_form_state()

    def _draft_queue_size(self) -> int:
        """返回当前任务队列中的真实任务数。"""
        if self.draft_list.count() == 1 and self.draft_list.item(0).flags() == Qt.NoItemFlags:
            return 0
        return self.draft_list.count()

    def _queue_status_counts(self) -> dict[str, int]:
        """统计当前任务队列中的状态数量。"""
        counts = {
            TASK_STATUS_RUNNING: 0,
            TASK_STATUS_WAITING: 0,
            TASK_STATUS_COMPLETED: 0,
            TASK_STATUS_FAILED: 0,
            TASK_STATUS_CANCELLED: 0,
        }
        for index in range(self.draft_list.count()):
            item = self.draft_list.item(index)
            payload = item.data(TASK_ITEM_ROLE)
            if not isinstance(payload, QueuedExecutionTask):
                continue
            status = payload.status
            if status in counts:
                counts[status] += 1
        return counts

    def _find_running_task_item(self) -> QListWidgetItem | None:
        """返回当前队列里处于运行中的任务项。"""
        for index in range(self.draft_list.count()):
            item = self.draft_list.item(index)
            payload = item.data(TASK_ITEM_ROLE)
            if isinstance(payload, QueuedExecutionTask) and payload.status == TASK_STATUS_RUNNING:
                return item
        return None

    def _update_queue_item(  # noqa: PLR0913
        self,
        item: QListWidgetItem,
        *,
        status: str | None = None,
        summary: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        progress_current: int | None = None,
        progress_total: int | None = None,
        progress_message: str | None = None,
        progress_detail: ExecutionTaskProgress | None = None,
        result_summary: str | None = None,
        error_message: str | None = None,
    ) -> QueuedExecutionTask:
        """更新任务项模型并同步文本显示。"""
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            raise TypeError("任务队列项缺少有效的任务模型。")

        updated_payload = replace(
            payload,
            status=status if status is not None else payload.status,
            summary=summary if summary is not None else payload.summary,
            started_at=started_at if started_at is not None else payload.started_at,
            finished_at=finished_at if finished_at is not None else payload.finished_at,
            progress_current=progress_current if progress_current is not None else payload.progress_current,
            progress_total=progress_total if progress_total is not None else payload.progress_total,
            progress_message=progress_message if progress_message is not None else payload.progress_message,
            progress_detail=progress_detail if progress_detail is not None else payload.progress_detail,
            result_summary=result_summary if result_summary is not None else payload.result_summary,
            error_message=error_message if error_message is not None else payload.error_message,
        )

        item.setData(TASK_ITEM_ROLE, updated_payload)
        item.setText(
            _build_queue_item_text(
                task_id=updated_payload.task_id,
                status=updated_payload.status,
                summary=updated_payload.summary,
            )
        )
        item.setToolTip(self._build_task_item_tooltip(updated_payload))
        return updated_payload

    def _start_next_waiting_task(self) -> QListWidgetItem | None:
        """将下一个等待中的任务提升为运行中。"""
        if self._find_running_task_item() is not None:
            return None

        for index in range(self.draft_list.count()):
            item = self.draft_list.item(index)
            payload = item.data(TASK_ITEM_ROLE)
            if isinstance(payload, QueuedExecutionTask) and payload.status == TASK_STATUS_WAITING:
                updated_payload = self._update_queue_item(
                    item,
                    status=TASK_STATUS_RUNNING,
                    started_at=datetime.now(),
                    progress_current=0,
                    progress_total=0,
                    progress_message="等待后台线程启动…",
                    progress_detail=None,
                    error_message="",
                )
                self._active_task_id = updated_payload.task_id
                self._set_task_running_state(True)
                self._sync_task_queue_busy_state()
                self._log_gui_event("info", f"[队列] 已自动开始任务：{updated_payload.summary}")
                self._refresh_progress_panel(
                    status_text="状态：任务启动中。",
                    note_text="当前进度：准备中 · 等待后台线程启动。",
                    progress_current=0,
                    progress_total=1,
                )
                self._start_task_worker(updated_payload)
                return item
        self._sync_task_queue_busy_state()
        return None

    def _start_task_worker(self, task: QueuedExecutionTask) -> None:
        """为指定任务创建后台 worker 并提交到线程池。"""

        def run_with_signals(signals) -> ExecutionTaskResult:
            return run_execution_task(task, signals)

        worker = TaskWorker(run_with_signals, pass_signals=True)
        worker.signals.started.connect(lambda task_id=task.task_id: self._on_task_started(task_id))
        worker.signals.progress.connect(
            lambda progress, task_id=task.task_id: self._on_task_progress(
                task_id,
                progress,
            )
        )
        worker.signals.finished.connect(lambda result, task_id=task.task_id: self._on_task_finished(task_id, result))
        worker.signals.failed.connect(lambda error, task_id=task.task_id: self._on_task_failed(task_id, error))
        self._active_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_task_started(self, task_id: int) -> None:
        """处理后台任务真正启动后的 UI 同步。"""
        item = self._find_task_item_by_id(task_id)
        if item is None:
            return
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            return
        self._refresh_progress_panel(
            status_text="状态：任务执行中。",
            note_text=f"当前进度：准备中 · {payload.progress_message or '后台任务已开始执行。'}",
            progress_current=0,
            progress_total=1,
        )

    def _on_task_progress(self, task_id: int, progress: object) -> None:
        """接收后台任务进度并刷新面板。"""
        if not isinstance(progress, ExecutionTaskProgress):
            return
        item = self._find_task_item_by_id(task_id)
        if item is None:
            return
        self._update_queue_item(
            item,
            progress_current=max(progress.current, 0),
            progress_total=max(progress.total, 0),
            progress_message=progress.message,
            progress_detail=progress,
        )
        if progress.stage_finished and progress.stage_key == "extract":
            notification_key = (task_id, progress.stage_key)
            if notification_key not in self._stage_completion_notifications:
                self._stage_completion_notifications.add(notification_key)
                payload = item.data(TASK_ITEM_ROLE)
                if isinstance(payload, QueuedExecutionTask):
                    content = f"任务 #{task_id} 已结束音频解包阶段。"
                    if payload.draft.task_params.run_mapping:
                        content = f"{content} 正在继续事件映射。"
                else:
                    content = f"任务 #{task_id} 已结束音频解包阶段。"
                show_feedback_infobar(
                    title="音频解包阶段已结束",
                    content=content,
                    parent=self._feedback_parent(),
                    level="info",
                    position=InfoBarPosition.TOP,
                )
        if self._active_task_id == task_id:
            self._refresh_progress_panel()

    def _on_task_finished(self, task_id: int, result: object) -> None:
        """处理后台任务成功完成后的状态收敛。"""
        item = self._find_task_item_by_id(task_id)
        if item is None:
            return

        task_result = (
            result
            if isinstance(result, ExecutionTaskResult)
            else ExecutionTaskResult(completed_steps=(), summary="任务执行完成。", duration_seconds=0.0)
        )
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            return

        completed_progress_detail = (
            replace(
                payload.progress_detail,
                current=max(payload.progress_detail.total, 1),
                total=max(payload.progress_detail.total, 1),
                message=task_result.summary,
            )
            if isinstance(payload.progress_detail, ExecutionTaskProgress)
            else None
        )
        updated_payload = self._update_queue_item(
            item,
            status=TASK_STATUS_COMPLETED,
            finished_at=datetime.now(),
            progress_current=max(payload.progress_total, len(task_result.completed_steps), 1),
            progress_total=max(payload.progress_total, len(task_result.completed_steps), 1),
            progress_message=task_result.summary,
            progress_detail=completed_progress_detail,
            result_summary=task_result.summary,
            error_message="",
        )
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications = {
            entry for entry in self._stage_completion_notifications if entry[0] != task_id
        }
        self._set_task_running_state(False)
        next_item = self._start_next_waiting_task()
        self._sync_task_queue_busy_state()
        if next_item is None:
            refresh_request = self._build_output_state_refresh_request(updated_payload, task_result)
            self._refresh_progress_panel(
                status_text="状态：最近任务已完成。",
                note_text=f"100% · {updated_payload.result_summary or task_result.summary}",
                progress_current=1,
                progress_total=1,
            )
            self.output_state_refresh_requested.emit(refresh_request)
        else:
            self._refresh_progress_panel()

    def _on_task_failed(self, task_id: int, error: str) -> None:
        """处理后台任务失败后的状态收敛。"""
        item = self._find_task_item_by_id(task_id)
        if item is None:
            return

        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            return

        progress_total = max(payload.progress_total, 1)
        progress_current = min(payload.progress_current, progress_total)
        failed_progress_detail = (
            replace(payload.progress_detail, message=error)
            if isinstance(payload.progress_detail, ExecutionTaskProgress)
            else None
        )
        updated_payload = self._update_queue_item(
            item,
            status=TASK_STATUS_FAILED,
            finished_at=datetime.now(),
            progress_current=progress_current,
            progress_total=progress_total,
            progress_message=error,
            progress_detail=failed_progress_detail,
            error_message=error,
        )
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications = {
            entry for entry in self._stage_completion_notifications if entry[0] != task_id
        }
        self._set_task_running_state(False)
        logger.error(f"[队列] 任务 #{task_id} 执行失败：{error}")
        next_item = self._start_next_waiting_task()
        self._sync_task_queue_busy_state()
        if next_item is None:
            refresh_request = self._build_output_state_refresh_request(updated_payload, ExecutionTaskResult(
                completed_steps=(),
                summary=error,
                duration_seconds=0.0,
            ))
            self._refresh_progress_panel(
                status_text="状态：最近任务执行失败。",
                note_text=f"当前进度：{progress_current}/{progress_total} · {updated_payload.error_message or error}",
                progress_current=progress_current,
                progress_total=progress_total,
            )
            self.output_state_refresh_requested.emit(refresh_request)
        else:
            self._refresh_progress_panel()
        show_feedback_infobar(
            title="任务执行失败",
            content=error,
            parent=self._feedback_parent(),
            level="error",
            position=InfoBarPosition.TOP,
        )

    def _remove_task_item(self, item: QListWidgetItem) -> None:
        """从队列中移除指定任务项。"""
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, QueuedExecutionTask):
            return

        current_status = payload.status
        if current_status == TASK_STATUS_RUNNING:
            show_feedback_infobar(
                title="暂不支持移除",
                content="运行中的真实任务暂不支持直接移出队列，请等待任务结束后再处理。",
                parent=self._feedback_parent(),
                level="warning",
                position=InfoBarPosition.TOP,
            )
            return

        row = self.draft_list.row(item)
        if row < 0:
            return

        self.draft_list.takeItem(row)
        if self._draft_queue_size() == 0:
            self._set_queue_placeholder()
        else:
            self._apply_queue_list_height()

        self._log_gui_event("info", f"[队列] 已移出任务：{payload.summary}")
        self._sync_task_queue_busy_state()
        self._refresh_progress_panel()
        show_feedback_infobar(
            title="已移出队列",
            content=payload.summary or item.text(),
            parent=self._feedback_parent(),
            level="success",
            position=InfoBarPosition.TOP,
        )

    def _open_task_queue_context_menu(self, pos) -> None:
        """打开任务队列右键菜单。"""
        item = self.draft_list.itemAt(pos)
        has_real_tasks = self._draft_queue_size() > 0
        if item is not None and item.flags() == Qt.NoItemFlags:
            item = None
        if item is None and not has_real_tasks:
            return

        payload = item.data(TASK_ITEM_ROLE) if item is not None else None
        if item is not None and not isinstance(payload, QueuedExecutionTask):
            return

        menu = QMenu(self.draft_list)
        counts = self._queue_status_counts()
        has_removable_tasks = (
            counts[TASK_STATUS_WAITING]
            + counts[TASK_STATUS_COMPLETED]
            + counts[TASK_STATUS_FAILED]
            + counts[TASK_STATUS_CANCELLED]
        ) > 0
        remove_action = None
        if isinstance(payload, QueuedExecutionTask):
            if payload.status == TASK_STATUS_RUNNING:
                remove_action = menu.addAction("运行中的任务暂不支持移除")
                remove_action.setEnabled(False)
            else:
                remove_action = menu.addAction("删除该任务")

        clear_action = None
        if has_real_tasks and has_removable_tasks:
            clear_text = "清空全部非运行中任务" if self._find_running_task_item() is not None else "清空全部队列"
            if remove_action is not None:
                menu.addSeparator()
            clear_action = menu.addAction(clear_text)

        selected_action = menu.exec(self.draft_list.viewport().mapToGlobal(pos))
        if selected_action == remove_action and item is not None:
            self._remove_task_item(item)
        if selected_action == clear_action:
            self._clear_draft_queue()

    def _refresh_progress_panel(
        self,
        *,
        status_text: str | None = None,
        note_text: str | None = None,
        progress_current: int | None = None,
        progress_total: int | None = None,
    ) -> None:
        """刷新右侧任务进度面板的摘要。"""
        draft_count = self._draft_queue_size()
        counts = self._queue_status_counts()
        running_item = self._find_running_task_item()
        running_task = running_item.data(TASK_ITEM_ROLE) if running_item is not None else None
        progress_bar_total = max(progress_total, 1) if progress_total is not None else 1
        progress_value = min(max(progress_current or 0, 0), progress_bar_total)
        running_progress = (
            running_task.progress_detail
            if isinstance(running_task, QueuedExecutionTask) and isinstance(running_task.progress_detail, ExecutionTaskProgress)
            else None
        )
        if progress_current is None and progress_total is None and isinstance(running_task, QueuedExecutionTask):
            if running_progress is not None and running_progress.total > 0:
                progress_bar_total = max(running_progress.total, 1)
                progress_value = min(max(running_progress.current, 0), progress_bar_total)
            elif running_task.progress_total > 0:
                progress_bar_total = max(running_task.progress_total, 1)
                progress_value = min(max(running_task.progress_current, 0), progress_bar_total)
            else:
                progress_bar_total = 1
                progress_value = 0
        if status_text is None:
            if draft_count == 0:
                status_text = "状态：界面已就绪，等待创建第一条任务。"
            elif isinstance(running_task, QueuedExecutionTask) and running_progress is not None:
                stage_text = f"当前阶段：{running_progress.stage_label}"
                if running_progress.entity_scope_label:
                    stage_text = f"{stage_text} · {running_progress.entity_scope_label}"
                status_text = stage_text
            elif isinstance(running_task, QueuedExecutionTask):
                status_text = "状态：队列中有运行中的任务。"
            elif counts[TASK_STATUS_WAITING] > 0:
                status_text = "状态：队列中有等待中的任务。"
            elif counts[TASK_STATUS_FAILED] > 0:
                status_text = "状态：队列中存在执行失败的任务。"
            elif counts[TASK_STATUS_COMPLETED] > 0:
                status_text = "状态：队列中的任务已执行完成。"
            else:
                status_text = "状态：当前队列中的任务已取消。"
        if note_text is None:
            if isinstance(running_task, QueuedExecutionTask):
                if running_progress is not None and running_progress.total > 0:
                    stage_summary = running_progress.stage_label
                    if running_progress.entity_scope_label:
                        stage_summary = f"{stage_summary} · {running_progress.entity_scope_label}"
                    note_text = (
                        f"{stage_summary} · {progress_value}/{progress_bar_total} · "
                        f"{running_progress.message or '后台任务执行中。'}"
                    )
                elif running_progress is not None:
                    stage_summary = running_progress.stage_label
                    if running_progress.entity_scope_label:
                        stage_summary = f"{stage_summary} · {running_progress.entity_scope_label}"
                    note_text = f"{stage_summary} · 准备中 · {running_progress.message or '后台任务执行中。'}"
                elif running_task.progress_total > 0:
                    note_text = (
                        f"当前进度：{progress_value}/{progress_bar_total} · "
                        f"{running_task.progress_message or '后台任务执行中。'}"
                    )
                else:
                    note_text = f"准备中 · {running_task.progress_message or '后台任务执行中。'}"
            elif draft_count == 0:
                note_text = "界面已就绪，等待创建第一条任务。"
            elif counts[TASK_STATUS_COMPLETED] > 0 and counts[TASK_STATUS_RUNNING] == 0 and counts[TASK_STATUS_WAITING] == 0:
                progress_bar_total = 100
                progress_value = 100
                note_text = "100% · 队列中的可执行任务已完成。"
            elif counts[TASK_STATUS_FAILED] > 0 and counts[TASK_STATUS_RUNNING] == 0:
                note_text = "执行失败，请查看日志抽屉和错误提示定位失败原因。"
            else:
                note_text = "当前显示任务队列状态。"

        self.task_progress_bar.setRange(0, progress_bar_total)
        self.task_progress_bar.setValue(progress_value)
        self.task_status_label.setText(status_text)
        self.task_progress_note.setText(note_text)
        self.queue_progress_label.setText(
            "任务队列："
            f"{draft_count} 条 · 运行中 {counts[TASK_STATUS_RUNNING]} · 等待中 {counts[TASK_STATUS_WAITING]} "
            f"· 已完成 {counts[TASK_STATUS_COMPLETED]} · 失败 {counts[TASK_STATUS_FAILED]} · 已取消 {counts[TASK_STATUS_CANCELLED]}"
        )

    def _copy_cli_command(self) -> None:
        """复制当前配置对应的 CLI 命令。"""
        command_text = self._build_cli_command_text()
        if command_text is None:
            self._log_gui_event("warning", "[CLI] 未勾选任何执行步骤，无法复制命令。")
            show_feedback_infobar(
                title="无法复制 CLI 命令",
                content="请至少勾选音频解包或事件映射中的一个步骤。",
                parent=self._feedback_parent(),
                level="warning",
                position=InfoBarPosition.TOP,
            )
            return

        QGuiApplication.clipboard().setText(command_text)
        self._log_gui_event("info", f"[CLI] 已复制命令：{command_text}")
        show_feedback_infobar(
            title="已复制 CLI 命令",
            content=command_text,
            parent=self._feedback_parent(),
            level="success",
            position=InfoBarPosition.TOP,
        )

    def _queue_task_draft(self) -> None:
        """将当前界面参数写入任务队列，并自动开始首个任务。"""
        task_scope_summary = self._selected_task_scope_summary()
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

        try:
            draft = self._build_task_draft()
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

        self._draft_count += 1
        summary = self._current_task_config_summary()
        queued_task = QueuedExecutionTask(
            task_id=self._draft_count,
            draft=draft,
            summary=summary,
        )
        row_text = _build_queue_item_text(
            task_id=queued_task.task_id,
            status=queued_task.status,
            summary=queued_task.summary,
        )

        if self.draft_list.count() == 1 and self.draft_list.item(0).flags() == Qt.NoItemFlags:
            self.draft_list.clear()

        item = QListWidgetItem(row_text)
        item.setData(TASK_ITEM_ROLE, queued_task)
        item.setToolTip(self._build_task_item_tooltip(queued_task))
        self.draft_list.addItem(item)
        self._apply_queue_list_height()
        self._log_gui_event("info", f"[队列] {row_text}")
        started_item = self._start_next_waiting_task()
        self._sync_task_queue_busy_state()
        if started_item is None:
            self._refresh_progress_panel(
                status_text="状态：新任务已加入等待队列。",
                note_text="0% · 当前显示任务队列状态。",
            )
        elif self._active_task_id is not None:
            self._refresh_progress_panel(status_text="状态：任务已加入队列。")
        else:
            self._refresh_progress_panel()
        show_feedback_infobar(
            title="已加入任务队列",
            content=row_text,
            parent=self._feedback_parent(),
            level="success",
            position=InfoBarPosition.TOP,
        )
        self._reset_custom_inputs_to_defaults()

    def _set_queue_placeholder(self) -> None:
        """为任务队列设置占位文本。"""
        self.draft_list.clear()
        placeholder_item = QListWidgetItem("当前任务队列为空。")
        placeholder_item.setFlags(Qt.NoItemFlags)
        self.draft_list.addItem(placeholder_item)
        self._apply_queue_list_height()

    def _apply_queue_list_height(self) -> None:
        """按默认可见行数收敛任务队列列表高度。"""
        row_height = self.draft_list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = max(self.fontMetrics().height() + 14, 32)
        frame_height = self.draft_list.frameWidth() * 2
        self.draft_list.setFixedHeight(row_height * QUEUE_VISIBLE_ROW_COUNT + frame_height + 2)

    def _debug_fill_mock_queue(self, count: int) -> str:
        """填充指定数量的 mock 队列项，方便调试列表布局。"""
        if count <= 0:
            raise ValueError("queue fill 需要大于 0 的整数参数。")

        self.draft_list.clear()
        self._draft_count = count
        self._active_task_id = None
        self._active_worker = None
        self._stage_completion_notifications.clear()

        for task_id in range(1, count + 1):
            if task_id == 1:
                status = TASK_STATUS_RUNNING
                progress_current = 1
                progress_total = 3
                progress_message = "Mock 任务运行中"
            elif task_id % 3 == 0:
                status = TASK_STATUS_COMPLETED
                progress_current = 1
                progress_total = 1
                progress_message = "Mock 任务已完成"
            else:
                status = TASK_STATUS_WAITING
                progress_current = 0
                progress_total = 0
                progress_message = ""

            draft = ExecutionTaskDraft(
                source="dev_console",
                source_summary="开发控制台填充的 mock 队列",
                task_params=ExecutionTaskParamsSnapshot(
                    champion_ids=(task_id,),
                    map_ids=(11,),
                ),
            )
            summary = f"Mock任务 {task_id} · 列表调试"
            queued_task = QueuedExecutionTask(
                task_id=task_id,
                draft=draft,
                summary=summary,
                status=status,
                progress_current=progress_current,
                progress_total=progress_total,
                progress_message=progress_message,
            )
            item = QListWidgetItem(
                _build_queue_item_text(
                    task_id=queued_task.task_id,
                    status=queued_task.status,
                    summary=queued_task.summary,
                )
            )
            item.setData(TASK_ITEM_ROLE, queued_task)
            item.setToolTip(self._build_task_item_tooltip(queued_task))
            self.draft_list.addItem(item)
            if status == TASK_STATUS_RUNNING and self._active_task_id is None:
                self._active_task_id = task_id

        self._set_task_running_state(self._active_task_id is not None)
        self._sync_task_queue_busy_state()
        self._apply_queue_list_height()
        self._refresh_progress_panel()
        return f"已填充 {count} 条 mock 队列项。"

    def _debug_clear_mock_queue(self) -> str:
        """清空当前调试队列并恢复占位状态。"""
        self._active_task_id = None
        self._active_worker = None
        self._set_task_running_state(False)
        self._stage_completion_notifications.clear()
        self._set_queue_placeholder()
        self._sync_task_queue_busy_state()
        self._refresh_progress_panel()
        return "已清空当前队列。"

    def _debug_inspect_queue(self) -> str:
        """返回当前队列列表与卡片尺寸信息。"""
        counts = self._queue_status_counts()
        row_height = self.draft_list.sizeHintForRow(0)
        return "\n".join(
            [
                f"queue_count={self._draft_queue_size()}",
                f"visible_rows={QUEUE_VISIBLE_ROW_COUNT}",
                f"row_height={row_height}",
                f"queue_height={self.draft_list.height()}",
                f"progress_card_height={self.progress_card.height()}",
                f"builder_card_height={self.task_builder_card.height()}",
                f"running={counts[TASK_STATUS_RUNNING]} waiting={counts[TASK_STATUS_WAITING]} completed={counts[TASK_STATUS_COMPLETED]}",
            ]
        )

    def _clear_draft_queue(self) -> None:
        """清空当前任务队列中可直接移除的任务项。"""
        running_item = self._find_running_task_item()
        if running_item is not None:
            removed_count = 0
            for index in range(self.draft_list.count() - 1, -1, -1):
                item = self.draft_list.item(index)
                payload = item.data(TASK_ITEM_ROLE)
                if isinstance(payload, QueuedExecutionTask) and payload.status != TASK_STATUS_RUNNING:
                    self.draft_list.takeItem(index)
                    removed_count += 1

            if removed_count == 0:
                self._log_gui_event("warning", "[队列] 当前存在运行中的任务，暂不支持直接清空。")
                show_feedback_infobar(
                    title="暂无法清空",
                    content="运行中的真实任务暂不支持直接移出队列，请等待任务结束后再清空。",
                    parent=self._feedback_parent(),
                    level="warning",
                    position=InfoBarPosition.TOP,
                )
            else:
                self._log_gui_event("info", f"[队列] 已清空 {removed_count} 条非运行中任务。")
                self._apply_queue_list_height()
                self._sync_task_queue_busy_state()
                self._refresh_progress_panel()
            return

        self._set_queue_placeholder()
        self._sync_task_queue_busy_state()
        self._refresh_progress_panel()
        self._log_gui_event("info", "[队列] 已清空当前任务队列。")

    def current_log_text(self) -> str:
        """返回执行中心当前累计日志文本。

        Returns:
            用换行拼接后的日志全文。
        """
        self._flush_pending_log_lines()
        return "\n".join(self._log_lines)

    def _queue_runtime_log_line(self, message: str) -> None:
        """缓存运行时日志，并在下一帧统一刷新到界面。

        Args:
            message: 已格式化的运行时日志文本。
        """
        self._pending_log_lines.append(message)
        if not self._log_flush_timer.isActive():
            self._log_flush_timer.start(0)

    def _flush_pending_log_lines(self) -> None:
        """将待刷新的运行时日志批量合并进当前页面缓存。"""
        if not self._pending_log_lines:
            return

        pending_lines = tuple(self._pending_log_lines)
        self._pending_log_lines.clear()
        self._log_lines.extend(pending_lines)
        self.log_lines_appended.emit(pending_lines)

    def _detach_runtime_log_sink(self, *_args: object) -> None:
        """移除当前 GUI 运行时日志 sink，避免重复注册。"""
        if self._runtime_log_sink_id is None:
            return

        try:
            logger.remove(self._runtime_log_sink_id)
        except ValueError:
            pass
        self._runtime_log_sink_id = None

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
