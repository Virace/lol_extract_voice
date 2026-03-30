from __future__ import annotations

from time import perf_counter
from weakref import ref

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CustomColorSettingCard,
    ExpandLayout,
    MessageBox,
    OptionsSettingCard,
    PushSettingCard,
    SettingCardGroup,
    SmoothScrollArea,
    Theme,
    TitleLabel,
    qconfig,
    setTheme,
    setThemeColor,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.gui.common import (
    GuiConfig,
    apply_smooth_scroll_enabled,
    format_default_relative_path,
    format_path_for_display,
)
from lol_audio_unpack.gui.common.style import (
    apply_page_content_margins,
    configure_transparent_scroll_page,
)
from lol_audio_unpack.gui.controllers.contracts import RuntimeLoggingConfig
from lol_audio_unpack.gui.controllers.path_picker_controller import (
    apply_path_card_label,
    pick_and_apply_directory,
    pick_and_apply_file,
    pick_directory,
    pick_file,
)
from lol_audio_unpack.gui.controllers.remote_source_controller import (
    RemoteSourceController,
    RemoteSourceDraft,
)
from lol_audio_unpack.gui.view.settings.appearance_panel import AppearancePanel
from lol_audio_unpack.gui.view.settings.cards import (
    ComboRowSettingCard,
    LocalizedSwitchSettingCard,
    LogLevelSettingCard,
    SliderSettingCard,
    SmoothScrollSettingCard,
)
from lol_audio_unpack.gui.view.settings.remote_source_panel import RemoteSourcePanel
from lol_audio_unpack.gui.view.settings.source_mode_panel import SourceModePanel
from lol_audio_unpack.gui.view.settings.tool_path_panel import (
    BaseSettingsPanel,
    ToolPathPanel,
)
from lol_audio_unpack.utils.runtime_paths import (
    get_default_output_relative_path,
    get_default_vgmstream_relative_path,
    get_default_wwiser_relative_path,
)

DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY = "default"


def _build_audio_output_device_key(device) -> str:
    """为 Qt 音频输出设备构造稳定键值。"""
    return f"device:{bytes(device.id()).hex()}"


def get_preview_audio_output_device_options() -> list[tuple[str, str]]:
    """列出 GUI 可选的试听输出设备。

    Returns:
        list[tuple[str, str]]: ``[(显示文案, 设备键值), ...]``，首项永远为
        ``("默认设备", "default")``。
    """
    options: list[tuple[str, str]] = [("默认设备", DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY)]
    seen_labels: dict[str, int] = {}

    for index, device in enumerate(QMediaDevices.audioOutputs(), start=1):
        base_label = device.description().strip() or f"输出设备 {index}"
        count = seen_labels.get(base_label, 0) + 1
        seen_labels[base_label] = count
        label = base_label if count == 1 else f"{base_label} ({count})"
        options.append((label, _build_audio_output_device_key(device)))

    return options


def _log_setting_stage(stage: str, startup_begin: float, previous_mark: float) -> float:
    """记录设置页初始化阶段耗时。"""
    current_mark = perf_counter()
    logger.trace(
        "设置页阶段 | {} | 本段 {:.3f}s | 累计 {:.3f}s",
        stage,
        current_mark - previous_mark,
        current_mark - startup_begin,
    )
    return current_mark


# ---------------------------------------------------------------------------
# SettingPage
# ---------------------------------------------------------------------------

class SettingPage(SmoothScrollArea):
    """Settings Page — all persistent config in one scrollable view."""

    # 路径变更信号
    game_path_changed = Signal(str)
    output_path_changed = Signal(str)
    wwiser_path_changed = Signal(str)
    vgmstream_path_changed = Signal(str)
    shared_context_input_changed = Signal()
    smooth_scroll_changed = Signal(bool, bool)
    log_drawer_auto_collapse_changed = Signal(bool)
    log_levels_changed = Signal(object)
    preview_audio_output_device_changed = Signal(str)
    preview_audio_volume_changed = Signal(int)

    def __init__(self, parent=None):
        startup_begin = perf_counter()
        previous_mark = startup_begin
        super().__init__(parent=parent)
        previous_mark = _log_setting_stage("SmoothScrollArea 基类初始化", startup_begin, previous_mark)
        self.view = configure_transparent_scroll_page(
            self,
            page_object_name="SettingPage",
            view_object_name="SettingPageView",
        )
        self._runtime_config_locked = False
        previous_mark = _log_setting_stage("滚动容器与视图初始化完成", startup_begin, previous_mark)

        # 配置对象：先建好再构建 UI，确保 load() 后可立即应用
        self._cfg = GuiConfig()
        self._remote_source_controller = RemoteSourceController()
        self._theme_persistence_listener = None
        previous_mark = _log_setting_stage("GuiConfig 实例创建完成", startup_begin, previous_mark)

        self._build_ui()
        previous_mark = _log_setting_stage("_build_ui 完成", startup_begin, previous_mark)
        self._load_config()
        previous_mark = _log_setting_stage("_load_config 完成", startup_begin, previous_mark)
        apply_smooth_scroll_enabled(self, self._cfg.page_smooth_scroll_enabled)
        self._connect_signals()
        self.destroyed.connect(self._disconnect_theme_persistence_signals)
        previous_mark = _log_setting_stage("_connect_signals 完成", startup_begin, previous_mark)

        # 初始化时根据当前模式刷新动态显隐
        self._on_source_mode_changed(self.sourceModeCard.displayValue(), persist=False)
        self.set_runtime_config_locked(False)
        _log_setting_stage("_on_source_mode_changed 完成", startup_begin, previous_mark)

    # ------------------------------------------------------------------
    # UI 建造
    # ------------------------------------------------------------------

    def _build_ui(self):
        root_layout = QVBoxLayout(self.view)
        apply_page_content_margins(root_layout)
        root_layout.setSpacing(16)

        page_title = TitleLabel("全局设置", self.view)
        page_title.setObjectName("SettingPageTitle")
        root_layout.addWidget(page_title)

        page_subtitle = BodyLabel("统一管理运行环境、工具路径与界面偏好。", self.view)
        page_subtitle.setObjectName("SettingPageSubtitle")
        page_subtitle.setWordWrap(True)
        root_layout.addWidget(page_subtitle)

        content_widget = QWidget(self.view)
        self.content_widget = content_widget
        root_layout.addWidget(content_widget)

        self.expandLayout = ExpandLayout(content_widget)
        self.expandLayout.setContentsMargins(0, 6, 0, 0)
        self.expandLayout.setSpacing(24)

        build_begin = perf_counter()
        build_mark = build_begin

        self._build_source_group()   # 1. 数据来源（动态显隐子组）
        build_mark = _log_setting_stage("_build_source_group 完成", build_begin, build_mark)
        self._build_base_group()     # 2. 基础设置
        build_mark = _log_setting_stage("_build_base_group 完成", build_begin, build_mark)
        self._build_tools_group()    # 3. 工具配置
        build_mark = _log_setting_stage("_build_tools_group 完成", build_begin, build_mark)
        self._build_personal_group() # 4. 个性化
        _log_setting_stage("_build_personal_group 完成", build_begin, build_mark)

    # 1. 数据来源 -------------------------------------------------------

    # 来源模式：显示文字 → 实际 env 值的映射
    _SOURCE_MODE_MAP = {
        "本地模式": "local_path",
        "远程模式": "remote_snapshot",
    }
    def _build_source_group(self):
        group_begin = perf_counter()
        group_mark = group_begin

        self.sourceModePanel = SourceModePanel(
            parent=self.content_widget,
            source_mode_map=self._SOURCE_MODE_MAP,
        )
        self.sourceModeGroup = self.sourceModePanel.sourceModeGroup
        self.sourceModeCard = self.sourceModePanel.sourceModeCard
        self.localGroup = self.sourceModePanel.localGroup
        self.gamePathCard = self.sourceModePanel.gamePathCard
        self.remoteSourcePanel = self.sourceModePanel.remoteSourcePanel
        group_mark = _log_setting_stage("source: sourceModePanel 创建完成", group_begin, group_mark)
        self.sourceModePanel.add_to_layout(self.expandLayout)
        _log_setting_stage("source: remoteGroup.addWidget 完成", group_begin, group_mark)

    # 2. 基础设置 -------------------------------------------------------

    def _build_base_group(self):
        self.baseSettingsPanel = BaseSettingsPanel(parent=self.content_widget)
        self.baseGroup = self.baseSettingsPanel.group
        self.outputPathCard = self.baseSettingsPanel.outputPathCard
        self.gameRegionCard = self.baseSettingsPanel.gameRegionCard
        self.groupByTypeCard = self.baseSettingsPanel.groupByTypeCard
        self.expandLayout.addWidget(self.baseGroup)

    # 3. 工具配置 -------------------------------------------------------

    def _build_tools_group(self):
        self.toolPathPanel = ToolPathPanel(parent=self.content_widget)
        self.toolsGroup = self.toolPathPanel.group
        self.wwiserCard = self.toolPathPanel.wwiserCard
        self.vgmstreamCard = self.toolPathPanel.vgmstreamCard
        self.expandLayout.addWidget(self.toolsGroup)

    # 4. 个性化 ---------------------------------------------------------

    def _build_personal_group(self):
        audio_output_device_options = get_preview_audio_output_device_options()
        self.appearancePanel = AppearancePanel(
            parent=self.content_widget,
            audio_output_device_options=audio_output_device_options,
        )
        self.personalGroup = self.appearancePanel.group
        self.themeCard = self.appearancePanel.themeCard
        self.colorCard = self.appearancePanel.colorCard
        self.smoothScrollCard = self.appearancePanel.smoothScrollCard
        self.previewAudioOutputDeviceCard = self.appearancePanel.previewAudioOutputDeviceCard
        self.previewAudioVolumeCard = self.appearancePanel.previewAudioVolumeCard
        self.logDrawerAutoCollapseCard = self.appearancePanel.logDrawerAutoCollapseCard
        self.logLevelCard = self.appearancePanel.logLevelCard
        self.consoleLogLevelCard = self.appearancePanel.consoleLogLevelCard
        self.fileLogLevelCard = self.appearancePanel.fileLogLevelCard
        self.expandLayout.addWidget(self.personalGroup)

    # ------------------------------------------------------------------
    # 配置加载 / 保存
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        """从 GuiConfig 读取保存的配置并应用到各控件。"""
        cfg = self._cfg
        cfg.load()

        # 来源模式
        self.sourceModeCard.setValue(cfg.source_mode)

        # 游戏路径
        apply_path_card_label(self.gamePathCard, cfg.game_path)

        # 远程配置
        remote_draft = self._remote_source_controller.draft_from_config(cfg)
        self.remoteSourcePanel.set_source_mode(cfg.source_mode)
        self.remoteSourcePanel.apply_draft(remote_draft)

        # 基础设置
        apply_path_card_label(self.outputPathCard, cfg.output_path, f"./{get_default_output_relative_path()}")
        self.gameRegionCard.setValue(cfg.game_region)
        self.groupByTypeCard.setChecked(cfg.group_by_type)

        # 工具配置
        apply_path_card_label(self.wwiserCard, cfg.wwiser_path, f"./{get_default_wwiser_relative_path()}")
        apply_path_card_label(self.vgmstreamCard, cfg.vgmstream_path, f"./{get_default_vgmstream_relative_path()}")

        # 个性化 — 应用已保存的主题
        self._apply_theme_from_config()
        self.smoothScrollCard.setValues(
            page_enabled=cfg.page_smooth_scroll_enabled,
            widget_enabled=cfg.widget_smooth_scroll_enabled,
        )
        self.previewAudioOutputDeviceCard.setValue(cfg.preview_audio_output_device_key)
        self.previewAudioVolumeCard.setValue(cfg.preview_audio_volume_percent)
        self.logDrawerAutoCollapseCard.setValue(cfg.log_drawer_auto_collapse_enabled)
        self.logLevelCard.setValues(
            console_level=cfg.console_log_level,
            file_level=cfg.file_log_level,
        )
        self._refresh_remote_runtime_summary()

    def _save_config(
        self,
        *_args,
        emit_shared_context_input_change: bool = True,
        persist_remote_source_mode: bool = True,
    ) -> None:
        """将各控件当前值写入 GuiConfig 并持久化。"""
        cfg = self._cfg

        remote_draft = self.remoteSourcePanel.build_draft(source_mode=self.sourceModeCard.value())
        self._remote_source_controller.apply_draft_to_config(
            cfg,
            remote_draft,
            persist_remote_source_mode=persist_remote_source_mode,
        )
        cfg.game_region = self.gameRegionCard.value()
        cfg.group_by_type = self.groupByTypeCard.isChecked()
        cfg.page_smooth_scroll_enabled = self.smoothScrollCard.pageScrollEnabled()
        cfg.widget_smooth_scroll_enabled = self.smoothScrollCard.widgetScrollEnabled()
        cfg.log_drawer_auto_collapse_enabled = self.logDrawerAutoCollapseCard.isChecked()
        cfg.console_log_level = self.logLevelCard.consoleValue()
        cfg.file_log_level = self.logLevelCard.fileValue()

        cfg.save()
        self._refresh_remote_runtime_summary()
        if emit_shared_context_input_change:
            self.shared_context_input_changed.emit()

    def _save_remote_draft_config(self, draft: RemoteSourceDraft | None = None, *_args) -> None:
        """保存远程配置草稿，但不立即切换共享 runtime 上下文。"""
        remote_draft = draft or self.remoteSourcePanel.current_draft()
        self._remote_source_controller.apply_draft_to_config(
            self._cfg,
            remote_draft,
            persist_remote_source_mode=False,
        )
        self._cfg.save()
        self._refresh_remote_runtime_summary(remote_draft)

    def _save_theme_config(self) -> None:
        """保存主题配置到 GuiConfig。"""
        cfg = self._cfg
        # 从 qconfig 读取当前主题设置
        theme_map = {Theme.LIGHT: "Light", Theme.DARK: "Dark", Theme.AUTO: "Auto"}
        cfg.theme_mode = theme_map.get(qconfig.themeMode.value, "Light")
        cfg.theme_color = qconfig.themeColor.value.name()
        cfg.save_theme_preferences()

    def _disconnect_theme_persistence_signals(self, *_args: object) -> None:
        """断开设置页注册的全局主题持久化监听。"""
        if self._theme_persistence_listener is None:
            return
        for signal in (qconfig.themeChanged, qconfig.themeColorChanged):
            try:
                signal.disconnect(self._theme_persistence_listener)
            except (RuntimeError, TypeError):
                pass
        self._theme_persistence_listener = None

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """连接所有控件的变更信号，实现即时持久化。"""
        # 来源模式 — Local 立即生效，Remote 进入草稿态
        self.sourceModeCard.comboBox.currentTextChanged.connect(self._on_source_mode_changed)

        # 目录 / 文件选择按钮
        self.gamePathCard.clicked.connect(
            lambda: pick_and_apply_directory(
                title="选择游戏根目录",
                host=self,
                current=str(self._cfg.resolve_game_path() or ""),
                assign=lambda path: setattr(self._cfg, "game_path", path),
                save=self._cfg.save,
                card=self.gamePathCard,
                default="",
                changed_signal=self.game_path_changed,
                emit_shared_context_input_changed=self.shared_context_input_changed.emit,
            )
        )
        self.outputPathCard.clicked.connect(
            lambda: pick_and_apply_directory(
                title="选择解包输出目录",
                host=self,
                current=str(self._cfg.resolve_output_path()),
                assign=lambda path: setattr(self._cfg, "output_path", path),
                save=self._cfg.save,
                card=self.outputPathCard,
                default=f"./{get_default_output_relative_path()}",
                changed_signal=self.output_path_changed,
                emit_shared_context_input_changed=self.shared_context_input_changed.emit,
            )
        )
        self.wwiserCard.clicked.connect(
            lambda: pick_and_apply_file(
                title="选择 wwiser.py",
                host=self,
                current=str(self._cfg.resolve_wwiser_path() or ""),
                file_filter="Python 脚本 (wwiser.py wwiser.pyz);;所有文件 (*)",
                assign=lambda path: setattr(self._cfg, "wwiser_path", path),
                save=self._cfg.save,
                card=self.wwiserCard,
                default=f"./{get_default_wwiser_relative_path()}",
                changed_signal=self.wwiser_path_changed,
            )
        )
        self.vgmstreamCard.clicked.connect(
            lambda: pick_and_apply_file(
                title="选择 vgmstream-cli",
                host=self,
                current=str(self._cfg.resolve_vgmstream_path() or ""),
                file_filter="可执行文件 (vgmstream-cli.exe vgmstream-cli);;所有文件 (*)",
                assign=lambda path: setattr(self._cfg, "vgmstream_path", path),
                save=self._cfg.save,
                card=self.vgmstreamCard,
                default=f"./{get_default_vgmstream_relative_path()}",
                changed_signal=self.vgmstream_path_changed,
            )
        )

        # 远程配置草稿
        self.remoteSourcePanel.draft_changed.connect(self._save_remote_draft_config)
        self.remoteSourcePanel.apply_requested.connect(self._apply_remote_runtime_config)

        # 基础设置
        self.gameRegionCard.comboBox.currentTextChanged.connect(self._save_config)
        self.groupByTypeCard.checkedChanged.connect(self._save_config)
        self.smoothScrollCard.pageSwitchButton.checkedChanged.connect(self._on_smooth_scroll_changed)
        self.smoothScrollCard.widgetSwitchButton.checkedChanged.connect(self._on_smooth_scroll_changed)
        self.previewAudioOutputDeviceCard.comboBox.currentTextChanged.connect(
            lambda _value: self._save_preview_audio_output_device()
        )
        self.previewAudioVolumeCard.slider.valueChanged.connect(
            lambda value: self._save_preview_audio_volume(int(value))
        )
        self.logDrawerAutoCollapseCard.checkedChanged.connect(
            lambda _checked: self._save_log_drawer_auto_collapse()
        )
        self.consoleLogLevelCard.comboBox.currentTextChanged.connect(self._on_console_log_level_changed)
        self.fileLogLevelCard.comboBox.currentTextChanged.connect(
            lambda _value: self._save_file_log_level()
        )

        # 个性化 — 主题变更时保存
        if self._theme_persistence_listener is None:
            self_ref = ref(self)

            def _save_theme_config_with_weakref(*_args) -> None:
                page = self_ref()
                if page is not None:
                    page._save_theme_config()

            self._theme_persistence_listener = _save_theme_config_with_weakref
        qconfig.themeChanged.connect(self._theme_persistence_listener)
        qconfig.themeColorChanged.connect(self._theme_persistence_listener)

    # ------------------------------------------------------------------
    # 目录 / 文件选择槽
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 动态显隐
    # ------------------------------------------------------------------

    def _on_source_mode_changed(self, label: str, persist: bool = True) -> None:
        """根据来源模式（显示文字）切换 local / remote 子组的可见性。"""
        is_local = (label == "本地模式")
        self.localGroup.setVisible(is_local)
        self.remoteSourcePanel.group.setVisible(not is_local)
        self.remoteSourcePanel.set_source_mode(self.sourceModeCard.value())
        self.remoteSourcePanel.set_snapshot_strategy_visibility(self.remoteSourcePanel.snapshotStrategyCard.value())
        self._refresh_remote_runtime_summary()
        self.set_runtime_config_locked(self._runtime_config_locked)

        if not persist:
            return
        if is_local:
            self._save_config()
        else:
            self._save_remote_draft_config()

    def _refresh_remote_runtime_summary(self, draft: RemoteSourceDraft | None = None) -> None:
        """刷新远端版本提示与确认按钮可用性。"""
        remote_draft = draft or self.remoteSourcePanel.current_draft()
        version_text, action_text, apply_enabled = self._remote_source_controller.build_runtime_summary(remote_draft)
        self.remoteSourcePanel.update_runtime_summary(
            version_text=version_text,
            action_text=action_text,
            apply_enabled=apply_enabled,
        )

    def _apply_remote_runtime_config(self, draft: RemoteSourceDraft | None = None) -> None:
        """确认远端配置，并触发一次共享上下文刷新。"""
        if draft is not None:
            self._remote_source_controller.apply_draft_to_config(
                self._cfg,
                draft,
                persist_remote_source_mode=True,
            )
            self._cfg.save()
            self._refresh_remote_runtime_summary(draft)
            self.shared_context_input_changed.emit()
            return
        self._save_config()

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _apply_theme_from_config(self) -> None:
        """从 GuiConfig 应用主题设置到 qconfig。"""
        cfg = self._cfg
        # 应用主题模式
        theme_map = {"Light": Theme.LIGHT, "Dark": Theme.DARK, "Auto": Theme.AUTO}
        theme = theme_map.get(cfg.theme_mode, Theme.LIGHT)
        qconfig.set(qconfig.themeMode, theme)
        setTheme(theme)

        # 应用主题颜色
        color = QColor(cfg.theme_color)
        qconfig.set(qconfig.themeColor, color)
        setThemeColor(color)

    def set_runtime_config_locked(self, locked: bool) -> None:
        """按分层策略锁定或解锁后端上下文相关配置。"""
        self._runtime_config_locked = locked
        enabled = not locked
        self.sourceModeGroup.setEnabled(enabled)
        self.localGroup.setEnabled(enabled)
        self.remoteSourcePanel.set_runtime_config_locked(locked)
        self.baseGroup.setEnabled(enabled)
        self.wwiserCard.setEnabled(enabled)
        self.vgmstreamCard.setEnabled(True)
        self.toolsGroup.setEnabled(True)
        self.personalGroup.setEnabled(True)

    def _on_smooth_scroll_changed(self, _checked: bool) -> None:
        """保存并广播平滑滚动配置。"""
        self._save_config(emit_shared_context_input_change=False)
        page_enabled = self.smoothScrollCard.pageScrollEnabled()
        widget_enabled = self.smoothScrollCard.widgetScrollEnabled()
        apply_smooth_scroll_enabled(self, page_enabled)
        self.smooth_scroll_changed.emit(page_enabled, widget_enabled)

    def _save_log_drawer_auto_collapse(self) -> None:
        """保存并广播日志抽屉点击外部自动收起配置。"""
        self._save_config(emit_shared_context_input_change=False)
        self.log_drawer_auto_collapse_changed.emit(self.logDrawerAutoCollapseCard.isChecked())

    def _save_preview_audio_output_device(self) -> None:
        """保存并广播试听输出设备配置。"""
        self._cfg.preview_audio_output_device_key = self.previewAudioOutputDeviceCard.value()
        self._cfg.save()
        self.preview_audio_output_device_changed.emit(self._cfg.preview_audio_output_device_key)

    def _save_preview_audio_volume(self, value: int) -> None:
        """保存并广播试听音量配置。"""
        self._cfg.preview_audio_volume_percent = int(value)
        self._cfg.save()
        self.preview_audio_volume_changed.emit(self._cfg.preview_audio_volume_percent)

    def _on_console_log_level_changed(self, _value: str) -> None:
        """保存控制台日志等级，并在高频级别下提醒用户。"""
        self._save_config(emit_shared_context_input_change=False)
        if self.consoleLogLevelCard.value() in {"DEBUG", "TRACE"}:
            dialog = MessageBox(
                "高频日志提示",
                "将控制台日志设置为 DEBUG 或 TRACE 可能影响窗口流畅度。\n"
                "如果窗口卡死，可以手动修改配置文件，或直接删除配置文件让程序自动重建后恢复默认值。",
                self.window() or self,
            )
            dialog.hideCancelButton()
            dialog.yesButton.setText("我知道了")
            dialog.exec()
        self.log_levels_changed.emit(RuntimeLoggingConfig.from_gui_config(self._cfg))

    def _save_file_log_level(self) -> None:
        """保存文件日志等级并广播配置变更。"""
        self._save_config(emit_shared_context_input_change=False)
        self.log_levels_changed.emit(RuntimeLoggingConfig.from_gui_config(self._cfg))

    # ------------------------------------------------------------------
    # 公共值读取（供其他页面或 Worker 调用）
    # ------------------------------------------------------------------

    @property
    def config(self) -> GuiConfig:
        """返回当前已加载的 GuiConfig 对象（调用前请确保已 load()）。"""
        return self._cfg

    def source_mode_value(self) -> str:
        """返回来源模式的实际 env 值（local_path / remote_snapshot）。"""
        return self.sourceModeCard.value()
