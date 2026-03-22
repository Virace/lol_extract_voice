"""执行中心页面，承接任务队列、参数配置与日志同步。"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import QObject, Qt, QTimer, Signal
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
    ExpandGroupSettingCard,
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

from lol_audio_unpack.app_context import create_app_context
from lol_audio_unpack.gui.common import (
    GUI_LOG_FORMAT,
    GUI_LOG_MAX_LINES,
    apply_smooth_scroll_enabled,
    get_buffered_log_lines,
)

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext


def _parse_csv_ids(text: str) -> tuple[str, ...]:
    """将逗号分隔的 ID 输入解析为字符串元组。"""
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _build_target_summary(champion_ids: tuple[str, ...], map_ids: tuple[str, ...]) -> str:
    """构造当前目标范围摘要。"""
    if not champion_ids and not map_ids:
        return "目标：默认全部实体"
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
TASK_STATUS_WAITING = "等待中"
TASK_STATUS_RUNNING = "运行中"
TASK_STATUS_CANCELLED = "已取消"


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


class AdvancedInputCard(ExpandGroupSettingCard):
    """执行中心的高级输入折叠卡。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            FIF.SETTING,
            "自定义输入",
            "贴近 CLI 的自定义参数入口，用于补充或覆盖从实体总览同步进来的默认选择。",
            parent,
        )
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.setSpacing(0)
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
        self.max_workers_combo.addItems(["1", "2", "4", "8", "16"])
        self.max_workers_combo.setCurrentText("4")
        self.max_workers_combo.setMinimumWidth(120)
        self.max_workers_combo.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)

        self.bp_voice_cb = CheckBox("启用")
        self.bp_voice_cb.setChecked(True)
        self.force_update_cb = CheckBox("启用")
        self.integrate_data_cb = CheckBox("启用")

        self._add_row("英雄 ID", "按 CLI 风格输入，使用逗号分隔", self.champion_ids_input)
        self._add_row("地图 ID", "按 CLI 风格输入，使用逗号分隔", self.map_ids_input)
        self._add_row("音频范围", "执行中心里保留与 CLI 对齐的过滤方式", self.vo_filter)
        self._add_row("并发数", "设置批量任务使用的最大线程数", self.max_workers_combo)
        self._add_row("附加 BP 语音", "保留现有解包参数入口", self.bp_voice_cb)
        self._add_row("强制更新数据", "执行前先刷新 update 数据，适合本地缓存需要重建时使用", self.force_update_cb)
        self._add_row("生成整合数据文件", "对应 CLI 参数 --integrate-data，仅在映射任务中生效", self.integrate_data_cb)

    def _add_row(self, label_text: str, key_text: str, widget: QWidget) -> None:
        """添加一行设置项。"""
        row = QWidget()

        layout = QHBoxLayout(row)
        layout.setContentsMargins(48, 12, 48, 12)
        layout.setSpacing(16)

        label_column = QVBoxLayout()
        label_column.setSpacing(2)
        label_column.addWidget(BodyLabel(label_text))
        key_label = CaptionLabel(key_text)
        key_label.setObjectName("keyLabel")
        key_label.setWordWrap(False)
        label_column.addWidget(key_label)

        layout.addLayout(label_column, 1)
        layout.addWidget(widget, 1, Qt.AlignRight | Qt.AlignVCenter)

        self.addGroupWidget(row)


class ExecutionPage(SmoothScrollArea):
    """执行中心页面。"""

    refresh_requested = Signal()
    task_running_changed = Signal(bool)
    log_text_changed = Signal(str)
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
        self._cached_data: dict[str, list[dict[str, Any]]] = {"champions": [], "maps": []}
        self._draft_count = 0
        self._is_task_running = False
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
        self._last_draft_summary = "暂无队列任务。"
        self.destroyed.connect(self._detach_runtime_log_sink)
        self._build_ui()
        self._setup_connections()

    def _build_ui(self) -> None:
        self.expandLayout = ExpandLayout(self.view)
        self.expandLayout.setContentsMargins(24, 24, 24, 24)
        self.expandLayout.setSpacing(16)

        header_widget = QWidget(self.view)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        title_label = SubtitleLabel("执行中心", header_widget)
        subtitle_label = CaptionLabel("在这里添加任务、查看队列状态，或复制当前配置对应的 CLI 命令。", header_widget)
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
        builder_layout.setContentsMargins(18, 16, 18, 16)
        builder_layout.setSpacing(12)
        builder_title = StrongBodyLabel("创建任务", self.task_builder_card)
        builder_hint = CaptionLabel("确认当前目标和执行内容后，可以直接创建任务或复制 CLI 命令。", self.task_builder_card)
        builder_hint.setWordWrap(True)
        builder_layout.addWidget(builder_title)
        builder_layout.addWidget(builder_hint)

        context_widget = QWidget(self.task_builder_card)
        context_layout = QHBoxLayout(context_widget)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.setSpacing(12)

        source_widget = QWidget(context_widget)
        source_layout = QVBoxLayout(source_widget)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(4)
        source_title = CaptionLabel("选择来源", source_widget)
        self.selection_source_value = BodyLabel("默认范围", source_widget)
        self.selection_source_hint = CaptionLabel("尚未从实体总览同步选择。", source_widget)
        self.selection_source_hint.setWordWrap(True)
        source_layout.addWidget(source_title)
        source_layout.addWidget(self.selection_source_value)
        source_layout.addWidget(self.selection_source_hint)

        target_widget = QWidget(context_widget)
        target_layout = QVBoxLayout(target_widget)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(4)
        target_title = CaptionLabel("当前目标", target_widget)
        self.target_summary_value = BodyLabel("目标：默认全部实体", target_widget)
        target_hint = CaptionLabel("支持总览同步选择，也支持在高级输入里手动输入 ID。", target_widget)
        target_hint.setWordWrap(True)
        target_layout.addWidget(target_title)
        target_layout.addWidget(self.target_summary_value)
        target_layout.addWidget(target_hint)

        context_layout.addWidget(source_widget, 1)
        context_layout.addWidget(target_widget, 1)
        builder_layout.addWidget(context_widget)

        task_kind_widget = QWidget(self.task_builder_card)
        task_kind_layout = QVBoxLayout(task_kind_widget)
        task_kind_layout.setContentsMargins(0, 0, 0, 0)
        task_kind_layout.setSpacing(8)
        task_kind_title = BodyLabel("执行内容", task_kind_widget)
        task_kind_row = QHBoxLayout()
        task_kind_row.setContentsMargins(0, 0, 0, 0)
        task_kind_row.setSpacing(16)
        self.extract_task_cb = CheckBox("音频解包")
        self.extract_task_cb.setChecked(True)
        self.mapping_task_cb = CheckBox("事件映射")
        self.mapping_task_cb.setChecked(True)
        task_kind_row.addWidget(self.extract_task_cb)
        task_kind_row.addWidget(self.mapping_task_cb)
        task_kind_row.addStretch(1)
        self.task_builder_summary_label = BodyLabel("当前会创建：音频解包 + 事件映射。", task_kind_widget)
        task_kind_layout.addWidget(task_kind_title)
        task_kind_layout.addLayout(task_kind_row)
        task_kind_layout.addWidget(self.task_builder_summary_label)
        builder_layout.addWidget(task_kind_widget)

        builder_button_row = QHBoxLayout()
        builder_button_row.setContentsMargins(0, 0, 0, 0)
        builder_button_row.setSpacing(8)
        self.create_task_btn = PrimaryPushButton("创建任务", self.task_builder_card)
        self.copy_cli_btn = PushButton("复制 CLI 命令", self.task_builder_card)
        builder_button_row.addWidget(self.create_task_btn)
        builder_button_row.addWidget(self.copy_cli_btn)
        builder_button_row.addStretch(1)
        builder_layout.addLayout(builder_button_row)
        top_layout.addWidget(self.task_builder_card, 2)

        self.progress_card = CardWidget(self.view)
        progress_layout = QVBoxLayout(self.progress_card)
        progress_layout.setContentsMargins(18, 16, 18, 16)
        progress_layout.setSpacing(10)
        progress_title = StrongBodyLabel("任务进度", self.progress_card)
        progress_hint = CaptionLabel("这里会显示任务队列状态和最近一条任务。", self.progress_card)
        progress_hint.setWordWrap(True)
        self.task_status_label = CaptionLabel("状态：界面已就绪，等待创建第一条任务。", self.progress_card)
        self.task_progress_bar = ProgressBar(self.progress_card)
        self.task_progress_bar.setRange(0, 100)
        self.task_progress_bar.setValue(0)
        self.task_progress_note = BodyLabel("0% · 当前还没有待执行任务。", self.progress_card)
        self.queue_progress_label = CaptionLabel("任务队列：0 条", self.progress_card)
        self.recent_task_label = CaptionLabel("最近任务：暂无队列任务。", self.progress_card)
        self.recent_task_label.setWordWrap(True)
        progress_layout.addWidget(progress_title)
        progress_layout.addWidget(progress_hint)
        progress_layout.addWidget(self.task_status_label)
        progress_layout.addWidget(self.task_progress_bar)
        progress_layout.addWidget(self.task_progress_note)
        progress_layout.addWidget(self.queue_progress_label)
        progress_layout.addWidget(self.recent_task_label)
        progress_layout.addStretch(1)
        top_layout.addWidget(self.progress_card, 1)

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

        lower_widget = QWidget(self.view)
        lower_layout = QHBoxLayout(lower_widget)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(12)

        self.draft_card = CardWidget(self.view)
        draft_layout = QVBoxLayout(self.draft_card)
        draft_layout.setContentsMargins(18, 16, 18, 16)
        draft_layout.setSpacing(10)
        draft_header = QHBoxLayout()
        draft_title = StrongBodyLabel("任务队列 / 进度列表", self.draft_card)
        self.clear_drafts_btn = PushButton("清空队列", self.draft_card)
        draft_header.addWidget(draft_title)
        draft_header.addStretch(1)
        draft_header.addWidget(self.clear_drafts_btn)
        draft_layout.addLayout(draft_header)

        draft_hint = CaptionLabel("右键任务可取消。", self.draft_card)
        draft_hint.setWordWrap(True)
        draft_layout.addWidget(draft_hint)

        self.draft_list = ListWidget(self.draft_card)
        self.draft_list.setAlternatingRowColors(True)
        draft_layout.addWidget(self.draft_list, 1)

        self._set_queue_placeholder()
        lower_layout.addWidget(self.draft_card, 1)

        lower_widget.resize(lower_widget.width(), lower_widget.sizeHint().height())
        self.expandLayout.addWidget(lower_widget)

    def _setup_connections(self) -> None:
        self.clear_drafts_btn.clicked.connect(self._clear_draft_queue)
        self.create_task_btn.clicked.connect(self._queue_task_draft)
        self.copy_cli_btn.clicked.connect(self._copy_cli_command)
        self.champion_ids_input.textChanged.connect(self._refresh_task_builder_state)
        self.map_ids_input.textChanged.connect(self._refresh_task_builder_state)
        self.extract_task_cb.stateChanged.connect(self._refresh_task_builder_state)
        self.mapping_task_cb.stateChanged.connect(self._refresh_task_builder_state)
        self.draft_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.draft_list.customContextMenuRequested.connect(self._open_task_queue_context_menu)
        self._refresh_task_builder_state()
        self._refresh_progress_panel()

    def set_gui_config(self, cfg) -> None:
        """注入 GUI 配置并刷新默认值。"""
        self.gui_config = cfg
        self._sync_runtime_controls_from_context()
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

    def clear_entity_data(self) -> None:
        """清空当前已加载实体目录摘要。"""
        self._cached_data = {"champions": [], "maps": []}

    def attach_runtime_log_sink(self) -> None:
        """重新挂载 GUI 运行时日志 sink。"""
        self._detach_runtime_log_sink()
        self._runtime_log_sink_id = logger.add(
            self._runtime_log_relay,
            level="INFO",
            colorize=False,
            enqueue=False,
            format=GUI_LOG_FORMAT,
        )

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
                self._append_log_line("[同步] 已取消从实体总览同步选择。")
                return None
            if choice == "merge":
                champion_ids = _merge_unique_ids(current_champion_ids, champion_ids)
                map_ids = _merge_unique_ids(current_map_ids, map_ids)
                summary = f"已与当前输入合并：{_build_target_summary(champion_ids, map_ids)}"
            else:
                summary = f"已覆盖为实体总览选择：{_build_target_summary(champion_ids, map_ids)}"
        elif summary == "未提供摘要":
            summary = f"已同步实体总览选择：{_build_target_summary(champion_ids, map_ids)}"

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

    def _create_app_context(self, extra_overrides: dict[str, str | bool] | None = None) -> AppContext:
        """从 GUI 配置创建 ``AppContext``。"""
        cli_overrides = self.gui_config.to_app_context_overrides()
        if extra_overrides:
            cli_overrides.update(extra_overrides)
        return create_app_context(cli_overrides=cli_overrides)

    def _build_empty_synced_selection(self) -> dict[str, Any]:
        """返回空的总览同步状态。"""
        return {
            "source": "未同步",
            "champion_ids": (),
            "map_ids": (),
            "summary": "尚未从实体总览同步选择。",
        }

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
        self._append_log_line(f"[同步] {summary}")
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
            "同步到执行中心",
            (
                "当前执行中心里已经有待处理的 ID。\n\n"
                f"当前输入：{_build_target_summary(current_champion_ids, current_map_ids)}\n"
                f"实体总览：{_build_target_summary(incoming_champion_ids, incoming_map_ids)}\n\n"
                "请选择如何处理。"
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

    def _sync_runtime_controls_from_context(self) -> None:
        """使用当前上下文同步运行期控件默认值。"""
        if self.gui_config is None:
            return

        try:
            app_context = self._create_app_context()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"同步执行中心默认参数失败: {exc}")
            return

        self.bp_voice_cb.setChecked(self.bp_voice_cb.isChecked() or bool(app_context.config.with_bp_vo))
        self.vo_filter.setCurrentItem("VO" if tuple(app_context.config.include_types) == ("VO",) else "ALL")
        self._refresh_task_builder_state()

    def _current_target_ids(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """根据当前输入框返回准备中的英雄 / 地图 ID。"""
        champion_ids = _parse_csv_ids(self.champion_ids_input.text())
        map_ids = _parse_csv_ids(self.map_ids_input.text())
        return champion_ids, map_ids

    def _selected_task_scope_summary(self) -> str:
        """返回当前复选项对应的执行步骤摘要。"""
        return _build_task_scope_summary(
            include_extract=self.extract_task_cb.isChecked(),
            include_mapping=self.mapping_task_cb.isChecked(),
        )

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
        champion_ids, map_ids = self._current_target_ids()
        draft_summary = _build_target_summary(champion_ids, map_ids)
        task_scope_summary = self._selected_task_scope_summary()
        return (
            f"{task_scope_summary} · {draft_summary} · "
            f"VO={self.vo_filter.currentRouteKey() or 'VO'} · "
            f"BP={self.bp_voice_cb.isChecked()} · "
            f"更新={self.force_update_cb.isChecked()} · "
            f"整合={self.integrate_data_cb.isChecked()} · "
            f"并发={self.max_workers_combo.currentText()}"
        )

    def _refresh_task_builder_state(self) -> None:
        """同步任务创建区和进度区中的摘要文案。"""
        champion_ids, map_ids = self._current_target_ids()
        task_scope_summary = self._selected_task_scope_summary()
        self.target_summary_value.setText(_build_target_summary(champion_ids, map_ids))

        if (
            self._synced_selection["source"] != "未同步"
            and champion_ids == tuple(self._synced_selection["champion_ids"])
            and map_ids == tuple(self._synced_selection["map_ids"])
        ):
            self.selection_source_value.setText("实体总览同步")
            self.selection_source_hint.setText(self._synced_selection["summary"])
        elif champion_ids or map_ids:
            self.selection_source_value.setText("手动输入")
            self.selection_source_hint.setText("当前目标来自执行中心里的 ID 输入框。")
        else:
            self.selection_source_value.setText("默认范围")
            self.selection_source_hint.setText("尚未填写 ID，后续将按默认实体范围执行。")

        if task_scope_summary == "未选择执行内容":
            self.task_builder_summary_label.setText("请至少勾选一个执行步骤后再创建任务。")
        else:
            self.task_builder_summary_label.setText(f"当前会创建：{task_scope_summary}。")

    def _build_cli_command_text(self) -> str | None:
        """根据当前勾选参数构造可复制的 CLI 命令。"""
        if self._selected_task_scope_summary() == "未选择执行内容":
            return None

        champion_ids, map_ids = self._current_target_ids()
        args = ["uv", "run", "unpack"]

        if self.force_update_cb.isChecked():
            self._append_target_operation_args(
                args,
                operation_name="update",
                champion_ids=champion_ids,
                map_ids=map_ids,
            )
            args.append("--force")

        if self.extract_task_cb.isChecked():
            self._append_target_operation_args(
                args,
                operation_name="extract",
                champion_ids=champion_ids,
                map_ids=map_ids,
            )

        if self.mapping_task_cb.isChecked():
            self._append_target_operation_args(
                args,
                operation_name="mapping",
                champion_ids=champion_ids,
                map_ids=map_ids,
            )

        args.extend(["--max-workers", self.max_workers_combo.currentText()])
        args.append("--with-bp-vo" if self.bp_voice_cb.isChecked() else "--no-with-bp-vo")
        if self.vo_filter.currentRouteKey() == "VO":
            args.extend(["--exclude-type", "SFX,MUSIC"])
        if self.mapping_task_cb.isChecked() and self.integrate_data_cb.isChecked():
            args.append("--integrate-data")

        return " ".join(_quote_cli_arg(arg) for arg in args)

    def _reset_custom_inputs_to_defaults(self) -> None:
        """将自定义输入区恢复到默认状态。"""
        self._synced_selection = self._build_empty_synced_selection()
        self.champion_ids_input.clear()
        self.map_ids_input.clear()
        self.vo_filter.setCurrentItem("VO")
        self.max_workers_combo.setCurrentText("4")
        self.bp_voice_cb.setChecked(True)
        self.force_update_cb.setChecked(False)
        self.integrate_data_cb.setChecked(False)
        self._refresh_task_builder_state()

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
            TASK_STATUS_CANCELLED: 0,
        }
        for index in range(self.draft_list.count()):
            item = self.draft_list.item(index)
            payload = item.data(TASK_ITEM_ROLE)
            if not isinstance(payload, dict):
                continue
            status = str(payload.get("status", ""))
            if status in counts:
                counts[status] += 1
        return counts

    def _find_running_task_item(self) -> QListWidgetItem | None:
        """返回当前队列里处于运行中的任务项。"""
        for index in range(self.draft_list.count()):
            item = self.draft_list.item(index)
            payload = item.data(TASK_ITEM_ROLE)
            if isinstance(payload, dict) and payload.get("status") == TASK_STATUS_RUNNING:
                return item
        return None

    def _update_queue_item(
        self,
        item: QListWidgetItem,
        *,
        status: str | None = None,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """更新任务项元数据并同步文本显示。"""
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, dict):
            payload = {}
        if status is not None:
            payload["status"] = status
        if summary is not None:
            payload["summary"] = summary

        item.setData(TASK_ITEM_ROLE, payload)
        item.setText(
            _build_queue_item_text(
                task_id=int(payload.get("task_id", 0)),
                status=str(payload.get("status", TASK_STATUS_WAITING)),
                summary=str(payload.get("summary", "")),
            )
        )
        return payload

    def _start_next_waiting_task(self) -> QListWidgetItem | None:
        """将下一个等待中的任务提升为运行中。"""
        if self._find_running_task_item() is not None:
            return None

        for index in range(self.draft_list.count()):
            item = self.draft_list.item(index)
            payload = item.data(TASK_ITEM_ROLE)
            if isinstance(payload, dict) and payload.get("status") == TASK_STATUS_WAITING:
                updated_payload = self._update_queue_item(item, status=TASK_STATUS_RUNNING)
                summary = str(updated_payload.get("summary", ""))
                self._last_draft_summary = item.text()
                self._append_log_line(f"[队列] 已自动开始任务：{summary}")
                return item
        return None

    def _cancel_task_item(self, item: QListWidgetItem) -> None:
        """取消指定任务项，并在需要时启动下一个等待任务。"""
        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, dict):
            return

        current_status = str(payload.get("status", ""))
        if current_status == TASK_STATUS_CANCELLED:
            return

        summary = str(payload.get("summary", ""))
        was_running = current_status == TASK_STATUS_RUNNING
        self._update_queue_item(item, status=TASK_STATUS_CANCELLED)
        self._last_draft_summary = item.text()
        self._append_log_line(f"[队列] 已取消任务：{summary}")
        if was_running:
            self._start_next_waiting_task()
        self._refresh_progress_panel()
        InfoBar.info(
            "任务已取消",
            summary or item.text(),
            parent=self._feedback_parent(),
            position=InfoBarPosition.TOP,
        )

    def _open_task_queue_context_menu(self, pos) -> None:
        """打开任务队列右键菜单。"""
        item = self.draft_list.itemAt(pos)
        if item is None or item.flags() == Qt.NoItemFlags:
            return

        payload = item.data(TASK_ITEM_ROLE)
        if not isinstance(payload, dict):
            return

        status = str(payload.get("status", ""))
        if status == TASK_STATUS_CANCELLED:
            return

        menu = QMenu(self.draft_list)
        action_text = "取消运行中任务" if status == TASK_STATUS_RUNNING else "取消排队任务"
        cancel_action = menu.addAction(action_text)
        selected_action = menu.exec(self.draft_list.viewport().mapToGlobal(pos))
        if selected_action == cancel_action:
            self._cancel_task_item(item)

    def _refresh_progress_panel(
        self,
        *,
        status_text: str | None = None,
        note_text: str | None = None,
    ) -> None:
        """刷新右侧任务进度面板的摘要。"""
        draft_count = self._draft_queue_size()
        counts = self._queue_status_counts()
        if status_text is None:
            if draft_count == 0:
                status_text = "状态：界面已就绪，等待创建第一条任务。"
            elif counts[TASK_STATUS_RUNNING] > 0:
                status_text = "状态：队列中有运行中的任务。"
            elif counts[TASK_STATUS_WAITING] > 0:
                status_text = "状态：队列中有等待中的任务。"
            else:
                status_text = "状态：当前队列中的任务已取消。"
        if note_text is None:
            if draft_count == 0:
                note_text = "0% · 当前还没有待执行任务。"
            else:
                note_text = "0% · 当前显示任务队列状态。"

        self.task_progress_bar.setValue(0)
        self.task_status_label.setText(status_text)
        self.task_progress_note.setText(note_text)
        self.queue_progress_label.setText(
            f"任务队列：{draft_count} 条 · 运行中 {counts[TASK_STATUS_RUNNING]} · 等待中 {counts[TASK_STATUS_WAITING]} · 已取消 {counts[TASK_STATUS_CANCELLED]}"
        )
        self.recent_task_label.setText(f"最近任务：{self._last_draft_summary}")

    def _copy_cli_command(self) -> None:
        """复制当前配置对应的 CLI 命令。"""
        command_text = self._build_cli_command_text()
        if command_text is None:
            self._append_log_line("[CLI] 未勾选任何执行步骤，无法复制命令。")
            InfoBar.warning(
                "无法复制 CLI 命令",
                "请至少勾选音频解包或事件映射中的一个步骤。",
                parent=self._feedback_parent(),
                position=InfoBarPosition.TOP,
            )
            return

        QGuiApplication.clipboard().setText(command_text)
        self._append_log_line(f"[CLI] 已复制命令：{command_text}")
        InfoBar.success(
            "已复制 CLI 命令",
            command_text,
            parent=self._feedback_parent(),
            position=InfoBarPosition.TOP,
        )

    def _queue_task_draft(self) -> None:
        """将当前界面参数写入任务队列，并自动开始首个任务。"""
        task_scope_summary = self._selected_task_scope_summary()
        if task_scope_summary == "未选择执行内容":
            self._append_log_line("[队列] 未勾选任何执行步骤，已阻止创建任务。")
            InfoBar.warning(
                "无法创建任务",
                "请至少勾选音频解包或事件映射中的一个步骤。",
                parent=self._feedback_parent(),
                position=InfoBarPosition.TOP,
            )
            return

        self._draft_count += 1
        summary = self._current_task_config_summary()
        status = TASK_STATUS_WAITING if self._find_running_task_item() is not None else TASK_STATUS_RUNNING
        row_text = _build_queue_item_text(task_id=self._draft_count, status=status, summary=summary)

        if self.draft_list.count() == 1 and self.draft_list.item(0).flags() == Qt.NoItemFlags:
            self.draft_list.clear()

        item = QListWidgetItem(row_text)
        item.setData(
            TASK_ITEM_ROLE,
            {
                "task_id": self._draft_count,
                "status": status,
                "summary": summary,
            },
        )
        self.draft_list.addItem(item)
        self._last_draft_summary = row_text
        self._refresh_progress_panel(
            status_text="状态：任务已加入队列。" if status == TASK_STATUS_RUNNING else "状态：新任务已加入等待队列。",
            note_text="0% · 当前显示任务队列状态。",
        )
        self._append_log_line(f"[队列] {row_text}")
        InfoBar.success(
            "已加入任务队列",
            row_text,
            parent=self._feedback_parent(),
            position=InfoBarPosition.TOP,
        )
        self._reset_custom_inputs_to_defaults()

    def _set_queue_placeholder(self) -> None:
        """为任务队列设置占位文本。"""
        self.draft_list.clear()
        placeholder_item = QListWidgetItem("当前任务队列为空。")
        placeholder_item.setFlags(Qt.NoItemFlags)
        self.draft_list.addItem(placeholder_item)

    def _clear_draft_queue(self) -> None:
        """清空当前任务队列。"""
        self._set_queue_placeholder()
        self._last_draft_summary = "暂无队列任务。"
        self._refresh_progress_panel()
        self._append_log_line("[队列] 已清空当前任务队列。")

    def current_log_text(self) -> str:
        """返回执行中心当前累计日志文本。

        Returns:
            用换行拼接后的日志全文。
        """
        self._flush_pending_log_lines()
        return "\n".join(self._log_lines)

    def _append_log_line(self, message: str) -> None:
        """向全局日志面板追加一条文本。"""
        self._flush_pending_log_lines()
        self._log_lines.append(message)
        self.log_text_changed.emit(self.current_log_text())

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
