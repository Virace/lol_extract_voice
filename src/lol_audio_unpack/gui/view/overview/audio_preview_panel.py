"""实体总览右侧事件树与摘要面板。"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel

from lol_audio_unpack.gui.components.preview_tree import PreviewTreeModel, PreviewTreeView


class OverviewAudioPreviewPanel(QWidget):
    """承载事件树摘要与试听树壳层。"""

    def __init__(self, *, summary_placeholder: str, parent: QWidget | None = None) -> None:
        """初始化音频预览面板。

        Args:
            summary_placeholder: 无预览数据时的默认摘要文案。
            parent: 父级控件。
        """
        super().__init__(parent)
        self._summary_placeholder = summary_placeholder

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.summary_card = QFrame(self)
        self.summary_card.setObjectName("AudioPreviewSummaryCard")
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(12, 10, 12, 10)
        summary_layout.setSpacing(4)

        self.summary_label = BodyLabel(summary_placeholder, self.summary_card)
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_card)

        self.audio_preview_tree = PreviewTreeView(self)
        layout.addWidget(self.audio_preview_tree, 1)

    def set_summary_text(self, text: str) -> None:
        """更新摘要文案。

        Args:
            text: 新的摘要文本。
        """
        self.summary_label.setText(text)

    def set_summary_visible(self, visible: bool) -> None:
        """切换摘要卡显示状态。

        Args:
            visible: 是否显示摘要卡。
        """
        self.summary_card.setVisible(visible)

    def reset_summary(self) -> None:
        """恢复默认摘要文案。"""
        self.summary_label.setText(self._summary_placeholder)

    def clear_preview(self) -> None:
        """清空当前试听树并恢复默认摘要。"""
        model = self.audio_preview_tree.model()
        if isinstance(model, PreviewTreeModel):
            self.audio_preview_tree.collapseAll()
            model.clear_preview()
        self.reset_summary()

    def set_preview_data(
        self,
        *,
        mapping_data: dict | None,
        available_audio_ids: set[str],
        group_label_map: dict[str, str] | None,
        summary_text: str,
    ) -> None:
        """刷新事件树数据与摘要文案。"""
        self.set_summary_text(summary_text)
        model = self.audio_preview_tree.model()
        if isinstance(model, PreviewTreeModel):
            self.audio_preview_tree.collapseAll()
            model.set_preview_data(mapping_data, available_audio_ids, group_label_map)
            self._expand_single_root()

    def _expand_single_root(self) -> None:
        """在仅有一个根节点时自动展开首层。

        地图预览通常只有一个 map 根节点，单皮肤英雄也只有一个 skin 根节点。
        这两类场景下直接展开首层，可以减少一次无意义的点击；多根节点时仍保留
        现有折叠态，避免打乱多皮肤英雄的层级浏览。
        """
        model = self.audio_preview_tree.model()
        if not isinstance(model, PreviewTreeModel) or model.rowCount() != 1:
            return

        root_index = model.index(0, 0)
        if not root_index.isValid():
            return

        self.audio_preview_tree.expand(root_index)

    def set_playback_state(
        self,
        audio_id: str | None,
        *,
        progress: float,
        is_playing: bool,
        is_paused: bool,
    ) -> None:
        """同步当前试听叶子行的播放状态。"""
        self.audio_preview_tree.set_audio_playback_state(
            audio_id,
            progress=progress,
            is_playing=is_playing,
            is_paused=is_paused,
        )
