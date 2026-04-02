"""执行中心任务创建面板。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from lol_audio_unpack.gui.task_models import (
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
)

if TYPE_CHECKING:
    from lol_audio_unpack.gui.view.execution.advanced_input_panel import AdvancedInputPanel


def _parse_csv_ids(text: str) -> tuple[str, ...]:
    """将逗号分隔的 ID 输入解析为字符串元组。"""
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _parse_csv_int_ids(text: str, *, label: str) -> tuple[int, ...] | None:
    """将逗号分隔的数字 ID 输入解析为整数元组。"""
    raw_ids = _parse_csv_ids(text)
    if not raw_ids:
        return None

    try:
        return tuple(int(entity_id) for entity_id in raw_ids)
    except ValueError as exc:
        raise ValueError(f"{label} 仅支持逗号分隔的数字 ID。") from exc


def _build_target_summary(champion_ids: tuple[str, ...], map_ids: tuple[str, ...]) -> str:
    """构造当前目标范围摘要。"""
    if not champion_ids and not map_ids:
        return "全部英雄+地图"
    return f"目标：英雄 {len(champion_ids)} 个，地图 {len(map_ids)} 个"


def _build_task_scope_summary(
    *,
    include_preflight_update: bool,
    include_extract: bool,
    include_mapping: bool,
) -> str:
    """构造当前任务包含的执行步骤摘要。"""
    parts: list[str] = []
    if include_extract:
        parts.append("音频解包")
    if include_mapping:
        parts.append("事件映射")
    if not parts:
        return "未选择执行内容"
    if include_preflight_update:
        parts.insert(0, "前置强制更新")
    return " + ".join(parts)


def _quote_cli_arg(arg: str) -> str:
    """按 PowerShell 习惯格式化单个命令行参数。"""
    if not arg:
        return "''"

    safe_chars = "-_./,:=\\"
    if all(char.isalnum() or char in safe_chars for char in arg):
        return arg
    return "'" + arg.replace("'", "''") + "'"


@dataclass(slots=True, frozen=True)
class _ExecutionTaskFormDefaults:
    """任务表单默认值。"""

    vo_filter_key: str = "VO"
    max_workers_text: str = "4"
    with_bp_vo: bool = True
    force_update: bool = False
    integrate_data: bool = True


@dataclass(slots=True, frozen=True)
class _ExecutionTaskFormState:
    """任务表单状态快照。"""

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
            include_preflight_update=self.force_update,
            include_extract=self.include_extract,
            include_mapping=self.include_mapping,
        )


class TaskBuilderPanel(CardWidget):
    """承载任务目标与任务创建输入区。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化任务创建面板。

        Args:
            parent: 父级控件。
        """
        super().__init__(parent)
        self._defaults = _ExecutionTaskFormDefaults()
        self._state = _ExecutionTaskFormState()
        self._advanced_panel: AdvancedInputPanel | None = None
        self._synced_selection: dict[str, Any] = self._build_empty_synced_selection()

        builder_layout = QVBoxLayout(self)
        builder_layout.setContentsMargins(18, 16, 18, 18)
        builder_layout.setSpacing(12)

        builder_title = StrongBodyLabel("创建任务", self)
        builder_hint = CaptionLabel("确认当前目标后就能创建任务；如果想在命令行执行，也可以先复制命令。", self)
        builder_hint.setWordWrap(True)
        builder_layout.addWidget(builder_title)
        builder_layout.addWidget(builder_hint)

        target_widget = QWidget(self)
        target_layout = QVBoxLayout(target_widget)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(6)
        self.target_title_label = BodyLabel("当前目标", target_widget)
        self.target_summary_value = StrongBodyLabel("全部英雄+地图", target_widget)
        self.target_summary_value.setWordWrap(True)
        target_layout.addWidget(self.target_title_label)
        target_layout.addWidget(self.target_summary_value)
        builder_layout.addWidget(target_widget)

        action_widget = QWidget(self)
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
        action_layout.addWidget(task_kind_widget)

        builder_button_row = QHBoxLayout()
        builder_button_row.setContentsMargins(0, 0, 0, 0)
        builder_button_row.setSpacing(8)
        self.create_task_btn = PrimaryPushButton("创建任务", self)
        self.copy_cli_btn = PushButton("复制 CLI 命令", self)
        builder_button_row.addStretch(1)
        builder_button_row.addWidget(self.create_task_btn)
        builder_button_row.addWidget(self.copy_cli_btn)
        action_layout.addLayout(builder_button_row)

        builder_layout.addWidget(action_widget)

    def bind_advanced_panel(self, panel: AdvancedInputPanel) -> None:
        """绑定高级输入面板，供任务表单状态聚合使用。"""
        self._advanced_panel = panel

    def _build_empty_synced_selection(self) -> dict[str, Any]:
        """返回空的总览同步状态。"""
        return {
            "source": "未同步",
            "champion_ids": (),
            "map_ids": (),
            "summary": "尚未从实体总览同步选择。",
        }

    def connect_form_signals(self, callback) -> None:
        """连接任务表单相关控件信号。"""
        if self._advanced_panel is None:
            raise RuntimeError("TaskBuilderPanel 尚未绑定 AdvancedInputPanel。")

        self.extract_task_cb.stateChanged.connect(callback)
        self.mapping_task_cb.stateChanged.connect(callback)
        self._advanced_panel.champion_ids_input.textChanged.connect(callback)
        self._advanced_panel.map_ids_input.textChanged.connect(callback)
        self._advanced_panel.vo_filter.currentItemChanged.connect(callback)
        self._advanced_panel.max_workers_combo.currentTextChanged.connect(callback)
        self._advanced_panel.bp_voice_cb.stateChanged.connect(callback)
        self._advanced_panel.force_update_cb.stateChanged.connect(callback)
        self._advanced_panel.integrate_data_cb.stateChanged.connect(callback)

    def apply_defaults(self) -> None:
        """将默认值应用到任务表单控件。"""
        if self._advanced_panel is None:
            raise RuntimeError("TaskBuilderPanel 尚未绑定 AdvancedInputPanel。")

        defaults = self._defaults
        self.extract_task_cb.setChecked(True)
        self.mapping_task_cb.setChecked(True)
        self._advanced_panel.vo_filter.setCurrentItem(defaults.vo_filter_key)
        self._advanced_panel.max_workers_combo.setCurrentText(defaults.max_workers_text)
        self._advanced_panel.bp_voice_cb.setChecked(defaults.with_bp_vo)
        self._advanced_panel.force_update_cb.setChecked(defaults.force_update)
        self._advanced_panel.integrate_data_cb.setChecked(defaults.integrate_data)

    def sync_state_from_widgets(self) -> None:
        """从当前控件值同步内部任务表单状态。"""
        if self._advanced_panel is None:
            raise RuntimeError("TaskBuilderPanel 尚未绑定 AdvancedInputPanel。")

        self._state = _ExecutionTaskFormState(
            champion_ids=_parse_csv_ids(self._advanced_panel.champion_ids_input.text()),
            map_ids=_parse_csv_ids(self._advanced_panel.map_ids_input.text()),
            include_extract=self.extract_task_cb.isChecked(),
            include_mapping=self.mapping_task_cb.isChecked(),
            vo_filter_key=self._advanced_panel.vo_filter.currentRouteKey() or self._defaults.vo_filter_key,
            max_workers_text=self._advanced_panel.max_workers_combo.currentText(),
            with_bp_vo=self._advanced_panel.bp_voice_cb.isChecked(),
            force_update=self._advanced_panel.force_update_cb.isChecked(),
            integrate_data=self._advanced_panel.integrate_data_cb.isChecked(),
        )
        self.refresh_summary()

    def refresh_summary(self) -> None:
        """刷新任务创建区摘要文案。"""
        task_scope_summary = self._state.task_scope_summary()
        self.target_summary_value.setText(self._state.target_summary())
        if task_scope_summary == "未选择执行内容":
            self.task_builder_summary_label.setText("请至少勾选一个执行步骤后再创建任务。")
        else:
            self.task_builder_summary_label.setText(f"将创建：{task_scope_summary.replace(' + ', '、')}。")

    def current_target_ids(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """返回当前任务目标中的英雄和地图 ID。"""
        return self._state.champion_ids, self._state.map_ids

    def current_selection_source(self) -> str:
        """返回当前任务输入的来源标识。"""
        champion_ids, map_ids = self.current_target_ids()
        if (
            self._synced_selection["source"] != "未同步"
            and champion_ids == tuple(self._synced_selection["champion_ids"])
            and map_ids == tuple(self._synced_selection["map_ids"])
        ):
            return str(self._synced_selection["source"])
        if champion_ids or map_ids:
            return "manual_input"
        return "default_scope"

    def selected_task_scope_summary(self) -> str:
        """返回当前选中的执行步骤摘要。"""
        return self._state.task_scope_summary()

    def current_task_config_summary(self) -> str:
        """构造当前任务配置摘要。"""
        state = self._state
        draft_summary = state.target_summary()
        task_scope_summary = state.task_scope_summary()
        return (
            f"{task_scope_summary} · {draft_summary} · "
            f"VO={state.vo_filter_key} · "
            f"BP={state.with_bp_vo} · "
            f"前置强制更新={state.force_update} · "
            f"整合={state.integrate_data} · "
            f"并发={state.max_workers_text}"
        )

    def build_task_draft(self, *, gui_config) -> ExecutionTaskDraft:
        """根据当前表单状态构造任务草稿。"""
        state = self._state
        champion_ids = _parse_csv_int_ids(",".join(state.champion_ids), label="英雄 ID")
        map_ids = _parse_csv_int_ids(",".join(state.map_ids), label="地图 ID")
        exclude_types = ("SFX", "MUSIC") if state.vo_filter_key == "VO" else ()
        return ExecutionTaskDraft(
            source=self.current_selection_source(),
            source_summary=state.target_summary(),
            context_input=(gui_config.to_app_context_input_snapshot() if gui_config else AppContextInputSnapshot()),
            task_params=ExecutionTaskParamsSnapshot(
                champion_ids=champion_ids,
                map_ids=map_ids,
                # GUI 的该开关表示任务前置一次 `update --force`，而不是独立的常规 update 步骤。
                run_update=state.force_update,
                run_extract=state.include_extract,
                run_mapping=state.include_mapping,
                max_workers=int(state.max_workers_text),
                with_bp_vo=state.with_bp_vo,
                exclude_types=exclude_types,
                integrate_data=state.integrate_data,
            ),
        )

    def build_cli_command_text(self) -> str | None:
        """根据当前表单状态构造可复制的 CLI 命令。"""
        state = self._state
        if state.task_scope_summary() == "未选择执行内容":
            return None

        champion_ids, map_ids = state.champion_ids, state.map_ids
        args = ["uv", "run", "unpack"]

        if state.force_update:
            args.append("update")

        if state.include_extract:
            args.append("extract")

        if state.include_mapping:
            args.append("mapping")

        if champion_ids:
            args.extend(["--champions", ",".join(champion_ids)])
        if map_ids:
            args.extend(["--maps", ",".join(map_ids)])

        args.extend(["--max-workers", state.max_workers_text])
        if state.force_update:
            args.append("--force")
        args.append("--with-bp-vo" if state.with_bp_vo else "--no-with-bp-vo")
        if state.vo_filter_key == "VO":
            args.extend(["--exclude-type", "SFX,MUSIC"])
        if state.include_mapping and state.integrate_data:
            args.append("--integrate-data")

        return " ".join(_quote_cli_arg(arg) for arg in args)

    def reset_custom_inputs_to_defaults(self) -> None:
        """将自定义输入恢复到默认状态，同时保留执行步骤选择。"""
        if self._advanced_panel is None:
            raise RuntimeError("TaskBuilderPanel 尚未绑定 AdvancedInputPanel。")

        current_state = self._state
        defaults = self._defaults
        self._synced_selection = self._build_empty_synced_selection()
        self._state = _ExecutionTaskFormState(
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
        self._advanced_panel.champion_ids_input.setText("")
        self._advanced_panel.map_ids_input.setText("")
        self.extract_task_cb.setChecked(self._state.include_extract)
        self.mapping_task_cb.setChecked(self._state.include_mapping)
        self._advanced_panel.vo_filter.setCurrentItem(self._state.vo_filter_key)
        self._advanced_panel.max_workers_combo.setCurrentText(self._state.max_workers_text)
        self._advanced_panel.bp_voice_cb.setChecked(self._state.with_bp_vo)
        self._advanced_panel.force_update_cb.setChecked(self._state.force_update)
        self._advanced_panel.integrate_data_cb.setChecked(self._state.integrate_data)
        self.refresh_summary()

    def apply_selected_entities(
        self,
        *,
        champion_ids: tuple[str, ...],
        map_ids: tuple[str, ...],
        source: str,
        summary: str,
    ) -> None:
        """将实体总览选择应用到任务表单。"""
        if self._advanced_panel is None:
            raise RuntimeError("TaskBuilderPanel 尚未绑定 AdvancedInputPanel。")

        self._synced_selection = {
            "source": source,
            "champion_ids": champion_ids,
            "map_ids": map_ids,
            "summary": summary,
        }
        self._advanced_panel.champion_ids_input.setText(",".join(champion_ids))
        self._advanced_panel.map_ids_input.setText(",".join(map_ids))
        self.sync_state_from_widgets()
