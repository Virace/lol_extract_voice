"""执行中心使用的单卡片任务创建表单。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    ComboBox,
    GroupHeaderCardWidget,
    IconWidget,
    InfoBarIcon,
    LineEdit,
    PrimaryPushButton,
    SegmentedWidget,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.gui.task_models import (
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
)


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
    return f"英雄 {len(champion_ids)} 个，地图 {len(map_ids)} 个"


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


@dataclass(slots=True, frozen=True)
class _ExecutionTaskFormDefaults:
    """任务表单默认值。"""

    vo_filter_key: str = "VO"
    max_workers_text: str = "4"
    with_bp_vo: bool = True
    force_update: bool = False
    integrate_data: bool = True
    wav_enabled: bool = False
    wav_format: str = "pcm16"


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
    wav_enabled: bool = False
    wav_format: str = "pcm16"

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


class TaskCreationCard(GroupHeaderCardWidget):
    """承载执行中心自定义参数与任务创建按钮。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化任务创建卡片。"""
        super().__init__(parent)
        self.setTitle("自定义参数")
        self.setBorderRadius(8)
        self._defaults = _ExecutionTaskFormDefaults()
        self._state = _ExecutionTaskFormState()
        self._synced_selection: dict[str, Any] = self._build_empty_synced_selection()
        self._build_form_controls()
        self._build_bottom_toolbar()
        self.apply_defaults()
        self.refresh_summary()

    def _build_form_controls(self) -> None:
        """创建全部参数输入控件与分组。"""
        self.champion_ids_input = LineEdit(self)
        self.champion_ids_input.setPlaceholderText("英雄 ID，如 1,103,555")
        self.champion_ids_input.setFixedWidth(320)
        self.champion_ids_input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.champion_ids_input.setClearButtonEnabled(True)

        self.map_ids_input = LineEdit(self)
        self.map_ids_input.setPlaceholderText("地图 ID，如 0,11,12")
        self.map_ids_input.setFixedWidth(320)
        self.map_ids_input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.map_ids_input.setClearButtonEnabled(True)

        self.vo_filter = SegmentedWidget(self)
        self.vo_filter.addItem("VO", "仅 VO")
        self.vo_filter.addItem("ALL", "全部类型")
        self.vo_filter.setCurrentItem("VO")
        self.vo_filter.setFixedWidth(180)
        self.vo_filter.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.max_workers_combo = ComboBox(self)
        self.max_workers_combo.addItems(["1", "2", "4", "8", "16", "32", "64"])
        self.max_workers_combo.setCurrentText("4")
        self.max_workers_combo.setFixedWidth(120)
        self.max_workers_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.bp_voice_cb = CheckBox("启用", self)
        self.force_update_cb = CheckBox("启用", self)
        self.integrate_data_cb = CheckBox("启用", self)
        self.wav_output_cb = CheckBox("启用", self)
        self.wav_format_combo = ComboBox(self)
        self.wav_format_combo.addItems(["auto", "pcm16", "pcm24", "pcm32", "float"])
        self.wav_format_combo.setCurrentText("pcm16")
        self.wav_format_combo.setMinimumWidth(140)
        self.wav_format_combo.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.wav_format_combo.setVisible(False)

        self.wav_output_row = QWidget(self)
        self.wav_output_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wav_output_layout = QHBoxLayout(self.wav_output_row)
        wav_output_layout.setContentsMargins(0, 0, 0, 0)
        wav_output_layout.setSpacing(8)
        wav_output_layout.addWidget(self.wav_output_cb)
        wav_output_layout.addWidget(self.wav_format_combo)
        wav_output_layout.addStretch(1)

        self.addGroup(FIF.PEOPLE, "英雄 ID", "多个英雄 ID 用逗号分隔，如 1,103,555", self.champion_ids_input, stretch=1)
        self.addGroup(FIF.GLOBE, "地图 ID", "多个地图 ID 用逗号分隔，如 0,11,12", self.map_ids_input, stretch=1)
        self.addGroup(FIF.FILTER, "音频范围", "默认只处理 VO，需要时可切换为全部类型", self.vo_filter, stretch=1)
        self.addGroup(FIF.SPEED_HIGH, "并发数", "设置任务并发数；一般不建议超过 CPU 线程数", self.max_workers_combo)
        self.addGroup(FIF.MUSIC, "附加 BP 语音", "默认同时处理 BP 语音", self.bp_voice_cb)
        self.addGroup(FIF.ALBUM, "派生 WAV", "解包完成后额外生成 WAV；启用后可选择输出格式", self.wav_output_row)
        self.addGroup(
            FIF.SYNC,
            "前置强制更新",
            "在执行解包或映射前先强制刷新基础数据，相当于先跑一次 update --force",
            self.force_update_cb,
        )
        last_group = self.addGroup(
            FIF.INFO,
            "整合数据文件",
            "映射任务时额外生成整合数据，便于后续整理和查看",
            self.integrate_data_cb,
        )
        last_group.setSeparatorVisible(True)

    def _build_bottom_toolbar(self) -> None:
        """创建底部执行范围与任务创建工具栏。"""
        self.hintIcon = IconWidget(InfoBarIcon.INFORMATION, self)
        self.target_summary_value = BodyLabel("执行范围：全部英雄+地图", self)
        self.extract_task_cb = CheckBox("音频解包", self)
        self.extract_task_cb.setChecked(True)
        self.mapping_task_cb = CheckBox("事件映射", self)
        self.mapping_task_cb.setChecked(True)
        self.create_task_btn = PrimaryPushButton("创建任务", self)

        self.bottom_toolbar_layout = QHBoxLayout()
        self.bottom_toolbar_layout.setSpacing(10)
        self.bottom_toolbar_layout.setContentsMargins(24, 15, 24, 20)
        self.bottom_toolbar_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.hintIcon.setFixedSize(16, 16)
        self.bottom_toolbar_layout.addWidget(self.hintIcon, 0, Qt.AlignmentFlag.AlignLeft)
        self.bottom_toolbar_layout.addWidget(self.target_summary_value, 0, Qt.AlignmentFlag.AlignLeft)
        self.bottom_toolbar_layout.addStretch(1)
        self.bottom_toolbar_layout.addWidget(self.extract_task_cb, 0, Qt.AlignmentFlag.AlignRight)
        self.bottom_toolbar_layout.addWidget(self.mapping_task_cb, 0, Qt.AlignmentFlag.AlignRight)
        self.bottom_toolbar_layout.addWidget(self.create_task_btn, 0, Qt.AlignmentFlag.AlignRight)
        self.vBoxLayout.addLayout(self.bottom_toolbar_layout)

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
        self.extract_task_cb.stateChanged.connect(callback)
        self.mapping_task_cb.stateChanged.connect(callback)
        self.champion_ids_input.textChanged.connect(callback)
        self.map_ids_input.textChanged.connect(callback)
        self.vo_filter.currentItemChanged.connect(callback)
        self.max_workers_combo.currentTextChanged.connect(callback)
        self.bp_voice_cb.stateChanged.connect(callback)
        self.wav_output_cb.stateChanged.connect(callback)
        self.wav_format_combo.currentTextChanged.connect(callback)
        self.force_update_cb.stateChanged.connect(callback)
        self.integrate_data_cb.stateChanged.connect(callback)

    def apply_defaults(self) -> None:
        """将默认值应用到任务表单控件。"""
        defaults = self._defaults
        self.extract_task_cb.setChecked(True)
        self.mapping_task_cb.setChecked(True)
        self.vo_filter.setCurrentItem(defaults.vo_filter_key)
        self.max_workers_combo.setCurrentText(defaults.max_workers_text)
        self.bp_voice_cb.setChecked(defaults.with_bp_vo)
        self.wav_output_cb.setChecked(defaults.wav_enabled)
        self.wav_format_combo.setCurrentText(defaults.wav_format)
        self.force_update_cb.setChecked(defaults.force_update)
        self.integrate_data_cb.setChecked(defaults.integrate_data)
        self._sync_wav_control_state(extract_enabled=True)

    def apply_gui_config_defaults(self, gui_config) -> None:
        """根据当前 GUI 配置更新任务表单默认值。"""
        self._defaults = _ExecutionTaskFormDefaults(
            vo_filter_key=self._defaults.vo_filter_key,
            max_workers_text=self._defaults.max_workers_text,
            with_bp_vo=self._defaults.with_bp_vo,
            force_update=self._defaults.force_update,
            integrate_data=self._defaults.integrate_data,
            wav_enabled=bool(getattr(gui_config, "extract_wav_enabled", False)),
            wav_format=str(getattr(gui_config, "wav_format", "pcm16") or "pcm16"),
        )

    def _sync_wav_control_state(self, *, extract_enabled: bool) -> bool:
        """同步 WAV 控件状态，并返回当前是否启用 WAV。"""
        if not extract_enabled and self.wav_output_cb.isChecked():
            self.wav_output_cb.blockSignals(True)
            self.wav_output_cb.setChecked(False)
            self.wav_output_cb.blockSignals(False)

        wav_enabled = bool(extract_enabled and self.wav_output_cb.isChecked())
        self.set_wav_control_state(extract_enabled=extract_enabled, wav_enabled=wav_enabled)
        return wav_enabled

    def set_wav_control_state(self, *, extract_enabled: bool, wav_enabled: bool) -> None:
        """同步 WAV 开关与格式控件的可见性。"""
        self.wav_output_cb.setEnabled(extract_enabled)
        self.wav_format_combo.setVisible(wav_enabled)
        self.wav_format_combo.setEnabled(wav_enabled)

    def sync_state_from_widgets(self) -> None:
        """从当前控件值同步内部任务表单状态。"""
        include_extract = self.extract_task_cb.isChecked()
        wav_enabled = self._sync_wav_control_state(extract_enabled=include_extract)
        self._state = _ExecutionTaskFormState(
            champion_ids=_parse_csv_ids(self.champion_ids_input.text()),
            map_ids=_parse_csv_ids(self.map_ids_input.text()),
            include_extract=include_extract,
            include_mapping=self.mapping_task_cb.isChecked(),
            vo_filter_key=self.vo_filter.currentRouteKey() or self._defaults.vo_filter_key,
            max_workers_text=self.max_workers_combo.currentText(),
            with_bp_vo=self.bp_voice_cb.isChecked(),
            force_update=self.force_update_cb.isChecked(),
            integrate_data=self.integrate_data_cb.isChecked(),
            wav_enabled=wav_enabled,
            wav_format=self.wav_format_combo.currentText() or self._defaults.wav_format,
        )
        self.refresh_summary()

    def refresh_summary(self) -> None:
        """刷新底部执行范围摘要文案。"""
        self.target_summary_value.setText(f"执行范围：{self._state.target_summary()}")

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
        return (
            f"{state.task_scope_summary()} · 范围={state.target_summary()} · "
            f"VO={state.vo_filter_key} · "
            f"BP={state.with_bp_vo} · "
            f"WAV={state.wav_format if state.wav_enabled else '关闭'} · "
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
        wav_workers = int(getattr(gui_config, "wav_workers", 2) if gui_config else 2)
        wav_timeout = int(getattr(gui_config, "wav_timeout", 5) if gui_config else 5)
        wav_retries = int(getattr(gui_config, "wav_retries", 3) if gui_config else 3)
        return ExecutionTaskDraft(
            source=self.current_selection_source(),
            source_summary=state.target_summary(),
            context_input=(gui_config.to_app_context_input_snapshot() if gui_config else AppContextInputSnapshot()),
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
                wav_enabled=state.wav_enabled,
                wav_workers=wav_workers,
                wav_timeout=wav_timeout,
                wav_retries=wav_retries,
                wav_format=state.wav_format,
            ),
        )

    def reset_custom_inputs_to_defaults(self) -> None:
        """将自定义输入恢复到默认状态，同时保留执行步骤选择。"""
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
            wav_enabled=defaults.wav_enabled,
            wav_format=defaults.wav_format,
        )
        self.champion_ids_input.setText("")
        self.map_ids_input.setText("")
        self.extract_task_cb.setChecked(self._state.include_extract)
        self.mapping_task_cb.setChecked(self._state.include_mapping)
        self.vo_filter.setCurrentItem(self._state.vo_filter_key)
        self.max_workers_combo.setCurrentText(self._state.max_workers_text)
        self.bp_voice_cb.setChecked(self._state.with_bp_vo)
        self.wav_output_cb.setChecked(self._state.wav_enabled)
        self.wav_format_combo.setCurrentText(self._state.wav_format)
        self.force_update_cb.setChecked(self._state.force_update)
        self.integrate_data_cb.setChecked(self._state.integrate_data)
        self._sync_wav_control_state(extract_enabled=self._state.include_extract)
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
        self._synced_selection = {
            "source": source,
            "champion_ids": champion_ids,
            "map_ids": map_ids,
            "summary": summary,
        }
        self.champion_ids_input.setText(",".join(champion_ids))
        self.map_ids_input.setText(",".join(map_ids))
        self.sync_state_from_widgets()
