"""远端来源配置面板。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    FluentIcon as FIF,
)
from qfluentwidgets import PushSettingCard, SettingCardGroup

from lol_audio_unpack.gui.controllers.remote_source import RemoteSourceDraft
from lol_audio_unpack.gui.view.settings.cards import (
    ComboRowSettingCard,
    FixedSnapshotCard,
    LineEditSettingCard,
    LocalizedSwitchSettingCard,
)

REMOTE_SNAPSHOT_STRATEGY_MAP = {
    "最新 live 快照": "latest",
    "固定快照": "custom",
}

REMOTE_LIVE_REGION_OPTIONS = ["EUW", "NA", "KR", "JP", "BR", "TR", "RU", "OCE", "EUNE", "LAN", "LAS", "ME"]


class RemoteSourcePanel(QObject):
    """托管远端来源区域的所有 UI 控件。"""

    draft_changed = Signal(object)
    apply_requested = Signal(object)

    def __init__(self, parent: QWidget) -> None:
        """初始化远端来源面板。

        Args:
            parent: 面板宿主控件。
        """
        super().__init__(parent)
        self._source_mode = "local_path"
        self.group = SettingCardGroup("远程配置", parent)
        self.snapshotStrategyCard = ComboRowSettingCard(
            FIF.SYNC,
            "远端快照来源",
            "选择确认时使用最新 live 快照，或使用下方自定义固定快照。",
            list(REMOTE_SNAPSHOT_STRATEGY_MAP.keys()),
            label_map=REMOTE_SNAPSHOT_STRATEGY_MAP,
        )
        self.liveRegionCard = ComboRowSettingCard(
            FIF.GLOBE,
            "Live 区服",
            "仅在“最新”模式下生效；确认后会按该 Riot 区服解析最新快照。",
            REMOTE_LIVE_REGION_OPTIONS,
        )
        self.cleanupRemoteCard = LocalizedSwitchSettingCard(
            FIF.DELETE,
            "完成后自动清理",
            "删除远程下载的阶段性冗余文件，保持输出目录整洁",
        )
        self.versionInfoCard = LineEditSettingCard(
            FIF.INFO,
            "远端版本提示",
            "只有点击确认后，当前远端来源策略才会真正用于重建共享实体数据。",
            parent=self.group,
        )
        self.versionInfoCard.lineEdit.setReadOnly(True)
        self.versionInfoCard.lineEdit.setClearButtonEnabled(False)
        self.fixedSnapshotCard = FixedSnapshotCard()
        self.applyCard = PushSettingCard(
            "确认并刷新",
            FIF.ACCEPT,
            "应用远端配置",
            "确认当前远端来源策略后，再重建共享实体数据。",
        )

        self.group.addSettingCard(self.snapshotStrategyCard)
        self.group.addSettingCard(self.liveRegionCard)
        self.group.addSettingCard(self.cleanupRemoteCard)
        self.group.addSettingCard(self.versionInfoCard)
        self.group.addSettingCard(self.fixedSnapshotCard)
        self.group.addSettingCard(self.applyCard)

        self.snapshotStrategyCard.comboBox.currentTextChanged.connect(self._on_strategy_changed)
        self.liveRegionCard.comboBox.currentTextChanged.connect(self._emit_draft_changed)
        self.cleanupRemoteCard.checkedChanged.connect(self._emit_draft_changed)
        self.fixedSnapshotCard.versionEdit.editingFinished.connect(self._emit_draft_changed)
        self.fixedSnapshotCard.lcuUrlEdit.editingFinished.connect(self._emit_draft_changed)
        self.fixedSnapshotCard.gameUrlEdit.editingFinished.connect(self._emit_draft_changed)
        self.applyCard.clicked.connect(self._emit_apply_requested)

    def _emit_draft_changed(self, *_args) -> None:
        """屏蔽 Qt 原始信号参数，统一发出无参草稿变更信号。"""
        self.draft_changed.emit(self.current_draft())

    def _emit_apply_requested(self) -> None:
        """发出当前远端来源草稿的确认应用请求。"""
        self.apply_requested.emit(self.current_draft())

    def _on_strategy_changed(self, _label: str) -> None:
        """切换远端快照来源策略时同步 UI 显隐。"""
        self.set_snapshot_strategy_visibility(self.snapshotStrategyCard.value())
        self._emit_draft_changed()

    def apply_draft(self, draft: RemoteSourceDraft) -> None:
        """把远端来源草稿同步到 UI。

        Args:
            draft: 要显示的远端来源草稿。
        """
        self._source_mode = draft.source_mode
        self.snapshotStrategyCard.setValue(draft.strategy)
        self.liveRegionCard.setValue(draft.live_region)
        self.cleanupRemoteCard.setChecked(draft.cleanup_remote)
        self.fixedSnapshotCard.setValues(
            draft.snapshot_version,
            draft.snapshot_lcu_url,
            draft.snapshot_game_url,
        )
        self.set_snapshot_strategy_visibility(draft.strategy)

    def build_draft(self, *, source_mode: str) -> RemoteSourceDraft:
        """根据当前控件值构建远端来源草稿。

        Args:
            source_mode: 当前页面选择的数据来源模式。

        Returns:
            RemoteSourceDraft: 当前远端来源 UI 的草稿快照。
        """
        return RemoteSourceDraft(
            source_mode=source_mode,
            strategy=self.snapshotStrategyCard.value(),
            live_region=self.liveRegionCard.value(),
            cleanup_remote=self.cleanupRemoteCard.isChecked(),
            snapshot_version=self.fixedSnapshotCard.versionValue(),
            snapshot_lcu_url=self.fixedSnapshotCard.lcuUrlValue(),
            snapshot_game_url=self.fixedSnapshotCard.gameUrlValue(),
        )

    def current_draft(self) -> RemoteSourceDraft:
        """根据当前 source mode 与控件值返回远端来源草稿。"""
        return self.build_draft(source_mode=self._source_mode)

    def set_source_mode(self, source_mode: str) -> None:
        """同步当前来源模式，供后续草稿信号使用。

        Args:
            source_mode: 当前来源模式。
        """
        self._source_mode = source_mode

    def set_snapshot_strategy_visibility(self, strategy: str) -> None:
        """根据远端快照策略切换子配置可见性。

        Args:
            strategy: 远端快照策略，`latest` 或 `custom`。
        """
        use_latest = strategy == "latest"
        self.liveRegionCard.setVisible(use_latest)
        self.fixedSnapshotCard.setVisible(not use_latest)

    def update_runtime_summary(self, *, version_text: str, action_text: str, apply_enabled: bool) -> None:
        """同步远端运行时摘要展示。

        Args:
            version_text: 版本摘要文本。
            action_text: 操作提示文本。
            apply_enabled: 确认按钮是否可用。
        """
        self.versionInfoCard.setValue(version_text)
        self.applyCard.setContent(action_text)
        self.applyCard.setEnabled(apply_enabled)

    def set_runtime_config_locked(self, locked: bool) -> None:
        """锁定或解锁整块远端来源配置。

        Args:
            locked: 是否锁定。
        """
        self.group.setEnabled(not locked)
