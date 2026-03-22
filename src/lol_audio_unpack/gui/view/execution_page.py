"""执行中心页面，承接任务草稿、参数配置与日志同步。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidgetItem,
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
from lol_audio_unpack.gui.common import apply_smooth_scroll_enabled

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
        self.setExpand(False)

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
        self.use_synced_selection_cb = CheckBox("启用")
        self.use_synced_selection_cb.setChecked(True)

        self._add_row("英雄 ID", "按 CLI 风格输入，使用逗号分隔", self.champion_ids_input)
        self._add_row("地图 ID", "按 CLI 风格输入，使用逗号分隔", self.map_ids_input)
        self._add_row("音频范围", "执行中心里保留与 CLI 对齐的过滤方式", self.vo_filter)
        self._add_row("并发数", "当前只影响草稿摘要，真实执行链后续接入", self.max_workers_combo)
        self._add_row("附加 BP 语音", "保留现有解包参数入口", self.bp_voice_cb)
        self._add_row("强制更新数据", "执行前先刷新 update 数据，适合本地缓存需要重建时使用", self.force_update_cb)
        self._add_row("预留整合数据输出", "后续 mapping 执行链会消费该参数", self.integrate_data_cb)
        self._add_row("优先使用总览同步选择", "开启后优先采用实体总览同步进来的 ID", self.use_synced_selection_cb)

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
        self._log_lines = [
            "执行中心日志会同步到主窗口底部日志面板。",
            "当前阶段：仅记录界面草稿操作。",
        ]
        self._synced_selection: dict[str, Any] = {
            "source": "未同步",
            "champion_ids": (),
            "map_ids": (),
            "summary": "尚未从实体总览同步选择。",
        }
        self._task_status_labels: dict[str, CaptionLabel] = {}
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
        subtitle_label = CaptionLabel("先确定任务参数与草稿队列，日志会实时同步到底部全局面板，实际执行链路留到下一阶段接线。", header_widget)
        subtitle_label.setWordWrap(True)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        header_widget.resize(header_widget.width(), header_widget.sizeHint().height())
        self.expandLayout.addWidget(header_widget)

        cards_widget = QWidget(self.view)
        cards_layout = QHBoxLayout(cards_widget)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(12)
        self.extract_card = self._create_task_card(
            title="音频解包",
            description="保留 VO / BP / 并发等输入入口，并由自定义参数决定是否先做数据刷新。",
            kind="extract",
            button_text="加入解包草稿",
        )
        self.mapping_card = self._create_task_card(
            title="事件映射",
            description="当前承接任务草稿与参数界面，后续再接通 mapping 执行链。",
            kind="mapping",
            button_text="加入映射草稿",
        )
        cards_layout.addWidget(self.extract_card)
        cards_layout.addWidget(self.mapping_card)
        cards_widget.resize(cards_widget.width(), cards_widget.sizeHint().height())
        self.expandLayout.addWidget(cards_widget)

        self.advanced_card = AdvancedInputCard(self.view)
        self.champion_ids_input = self.advanced_card.champion_ids_input
        self.map_ids_input = self.advanced_card.map_ids_input
        self.vo_filter = self.advanced_card.vo_filter
        self.max_workers_combo = self.advanced_card.max_workers_combo
        self.bp_voice_cb = self.advanced_card.bp_voice_cb
        self.force_update_cb = self.advanced_card.force_update_cb
        self.integrate_data_cb = self.advanced_card.integrate_data_cb
        self.use_synced_selection_cb = self.advanced_card.use_synced_selection_cb
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
        draft_title = StrongBodyLabel("任务草稿 / 队列预览", self.draft_card)
        self.clear_drafts_btn = PushButton("清空草稿", self.draft_card)
        draft_header.addWidget(draft_title)
        draft_header.addStretch(1)
        draft_header.addWidget(self.clear_drafts_btn)
        draft_layout.addLayout(draft_header)

        draft_hint = CaptionLabel("当前先承接任务草稿与顺序展示，真正的执行队列逻辑后续接线。", self.draft_card)
        draft_hint.setWordWrap(True)
        draft_layout.addWidget(draft_hint)

        self.draft_list = ListWidget(self.draft_card)
        self.draft_list.setAlternatingRowColors(True)
        draft_layout.addWidget(self.draft_list, 1)

        self._set_queue_placeholder()
        lower_layout.addWidget(self.draft_card, 1)

        lower_widget.resize(lower_widget.width(), lower_widget.sizeHint().height())
        self.expandLayout.addWidget(lower_widget)

    def _create_task_card(self, *, title: str, description: str, kind: str, button_text: str) -> CardWidget:
        """创建执行中心中的任务卡片。"""
        card = CardWidget(self.view)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title_label = StrongBodyLabel(title, card)
        description_label = CaptionLabel(description, card)
        description_label.setWordWrap(True)
        status_label = CaptionLabel("状态：界面已就绪，执行逻辑待接线。", card)
        progress_bar = ProgressBar(card)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_note = BodyLabel("0% · 任务进度将在真实执行接入后显示。", card)
        create_btn = PrimaryPushButton(button_text, card)
        preview_btn = PushButton("写入日志说明", card)

        self._task_status_labels[kind] = status_label
        create_btn.clicked.connect(lambda: self._queue_task_draft(kind))
        preview_btn.clicked.connect(lambda: self._append_log_line(f"[{title}] 当前仅保留界面骨架，尚未接通真实执行。"))

        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addWidget(status_label)
        layout.addWidget(progress_bar)
        layout.addWidget(progress_note)
        layout.addStretch(1)
        layout.addWidget(create_btn)
        layout.addWidget(preview_btn)
        card.resize(card.width(), card.sizeHint().height())
        return card

    def _setup_connections(self) -> None:
        self.clear_drafts_btn.clicked.connect(self._clear_draft_queue)

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

    def set_selected_entities(self, payload: dict[str, Any]) -> None:
        """接收来自实体总览的选择结果。"""
        champion_ids = tuple(str(entity_id) for entity_id in payload.get("champion_ids", ()))
        map_ids = tuple(str(entity_id) for entity_id in payload.get("map_ids", ()))
        self._synced_selection = {
            "source": str(payload.get("source", "overview_selection")),
            "champion_ids": champion_ids,
            "map_ids": map_ids,
            "summary": str(payload.get("summary", "未提供摘要")),
        }
        self.champion_ids_input.setText(",".join(champion_ids))
        self.map_ids_input.setText(",".join(map_ids))
        self.use_synced_selection_cb.setChecked(True)
        self._append_log_line(f"[同步] 已接收来自实体总览的选择：{self._synced_selection['summary']}")

    def is_task_running(self) -> bool:
        """返回当前是否存在正在执行的任务。"""
        return self._is_task_running

    def _create_app_context(self, extra_overrides: dict[str, str | bool] | None = None) -> AppContext:
        """从 GUI 配置创建 ``AppContext``。"""
        cli_overrides = self.gui_config.to_app_context_overrides()
        if extra_overrides:
            cli_overrides.update(extra_overrides)
        return create_app_context(cli_overrides=cli_overrides)

    def _sync_runtime_controls_from_context(self) -> None:
        """使用当前上下文同步运行期控件默认值。"""
        if self.gui_config is None:
            return

        try:
            app_context = self._create_app_context()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"同步执行中心默认参数失败: {exc}")
            return

        self.bp_voice_cb.setChecked(bool(app_context.config.with_bp_vo))
        self.vo_filter.setCurrentItem("VO" if tuple(app_context.config.include_types) == ("VO",) else "ALL")

    def _current_target_ids(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """根据当前输入框返回准备中的英雄 / 地图 ID。"""
        champion_ids = _parse_csv_ids(self.champion_ids_input.text())
        map_ids = _parse_csv_ids(self.map_ids_input.text())
        return champion_ids, map_ids

    def _queue_task_draft(self, kind: str) -> None:
        """将当前界面参数写入一条任务草稿。"""
        champion_ids, map_ids = self._current_target_ids()
        draft_summary = _build_target_summary(champion_ids, map_ids)
        self._draft_count += 1
        row_text = (
            f"#{self._draft_count} · {kind.upper()} · {draft_summary} · "
            f"VO={self.vo_filter.currentRouteKey() or 'VO'} · "
            f"BP={self.bp_voice_cb.isChecked()} · "
            f"更新={self.force_update_cb.isChecked()} · "
            f"并发={self.max_workers_combo.currentText()}"
        )

        if self.draft_list.count() == 1 and self.draft_list.item(0).flags() == Qt.NoItemFlags:
            self.draft_list.clear()

        self.draft_list.addItem(QListWidgetItem(row_text))
        self._task_status_labels[kind].setText("状态：已创建界面草稿，等待真实执行链接入。")
        self._append_log_line(f"[草稿] {row_text}")
        InfoBar.success(
            "已加入任务草稿",
            row_text,
            parent=self,
            position=InfoBarPosition.TOP,
        )

    def _set_queue_placeholder(self) -> None:
        """为草稿队列设置占位文本。"""
        self.draft_list.clear()
        placeholder_item = QListWidgetItem("当前暂无任务草稿。")
        placeholder_item.setFlags(Qt.NoItemFlags)
        self.draft_list.addItem(placeholder_item)

    def _clear_draft_queue(self) -> None:
        """清空当前草稿队列。"""
        self._set_queue_placeholder()
        self._append_log_line("[草稿] 已清空当前任务草稿列表。")

    def current_log_text(self) -> str:
        """返回执行中心当前累计日志文本。

        Returns:
            用换行拼接后的日志全文。
        """
        return "\n".join(self._log_lines)

    def _append_log_line(self, message: str) -> None:
        """向全局日志面板追加一条文本。"""
        self._log_lines.append(message)
        self.log_text_changed.emit(self.current_log_text())

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
