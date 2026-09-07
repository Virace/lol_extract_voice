"""实体总览右侧事件树与摘要面板。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.gui.components.audio_list import AudioListView
from lol_audio_unpack.gui.components.preview_tree import PreviewTreeModel, PreviewTreeView
from lol_audio_unpack.gui.controllers.overview_preview import ALL_AUDIO_PREVIEW_MODE
from lol_audio_unpack.gui.view.overview.export_bar import AudioExportBar


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

        self.export_bar = AudioExportBar(self)
        # 页面在 Tab 往返时恢复完整摘要，紧凑行只展示状态；二者不参与同一布局。
        self.summary_card = self.export_bar.context_bar
        self.summary_label = BodyLabel(summary_placeholder, self)
        self.summary_label.setVisible(False)
        self.summary_label.setText(summary_placeholder)
        self._summary_text = summary_placeholder

        self.load_progress_bar = self.export_bar.progress_bar
        layout.addWidget(self.export_bar.context_bar)

        self.preview_stack = QStackedWidget(self)
        self.audio_preview_tree = PreviewTreeView(self.preview_stack)
        self.audio_preview_tree.setAccessibleName("事件音频树")
        self.audio_list = AudioListView(self.preview_stack)
        self.audio_list.setAccessibleName("全部音频列表")
        self.preview_stack.addWidget(self.audio_preview_tree)
        self.preview_stack.addWidget(self.audio_list)

        preview_footer = QWidget(self)
        preview_footer_layout = QVBoxLayout(preview_footer)
        preview_footer_layout.setContentsMargins(0, 0, 0, 0)
        preview_footer_layout.setSpacing(0)
        preview_footer_layout.addWidget(self.preview_stack, 1)
        preview_footer_layout.addWidget(self.export_bar.footer_bar)
        layout.addWidget(preview_footer, 1)

    def set_summary_text(self, text: str) -> None:
        """更新摘要文案。

        Args:
            text: 新的摘要文本。
        """
        self._summary_text = str(text)
        self.summary_label.setText(self._summary_text)
        self.export_bar.summary.setText(self._summary_context(self._summary_text))
        self.export_bar.summary.setToolTip(self._summary_text)

    def set_summary_visible(self, visible: bool) -> None:
        """切换上下文摘要显示状态。

        Args:
            visible: 是否显示上下文摘要。
        """
        self.export_bar.summary.setVisible(visible and not self.export_bar.active)

    def reset_summary(self) -> None:
        """恢复默认摘要文案。"""
        self.set_summary_text(self._summary_placeholder)
        self.clear_load_progress()

    def set_load_progress(self, current: int, total: int) -> None:
        """显示全部音频索引的计数进度。

        Args:
            current: 已处理的 WEM 候选数。
            total: 当前发现的 WEM 候选总数；未知时为 0。
        """
        self.export_bar.set_load_progress(current, total)

    def clear_load_progress(self) -> None:
        """隐藏并重置全部音频索引进度。"""
        self.export_bar.clear_load_progress()

    def set_export_visible(self, visible: bool) -> None:
        """按当前预览 tab 显示或隐藏音频选择和导出区域。

        Args:
            visible: 事件或全部音频模式显示，原始数据模式隐藏。
        """
        self.export_bar.set_export_visible(visible)

    @staticmethod
    def _summary_context(text: str) -> str:
        """取摘要首段作为上下文行状态，详细统计保留在内部摘要中。"""
        return str(text).split("·", 1)[0].strip()

    def clear_preview(self) -> None:
        """清空当前试听树并恢复默认摘要。"""
        model = self.audio_preview_tree.model()
        if isinstance(model, PreviewTreeModel):
            self.audio_preview_tree.collapseAll()
            model.clear_preview()
        self.audio_list.set_audio_refs(())
        self.reset_summary()

    def set_preview_data(
        self,
        *,
        mapping_data: dict | None,
        audio_refs: tuple[AudioRef, ...],
        group_label_map: dict[str, str] | None,
        summary_text: str,
        selection_mapping: dict | None = None,
    ) -> None:
        """刷新事件树数据与摘要文案。"""
        self.clear_load_progress()
        self.set_summary_text(summary_text)
        model = self.audio_preview_tree.model()
        if isinstance(model, PreviewTreeModel):
            self.audio_preview_tree.collapseAll()
            model.set_preview_data(mapping_data, audio_refs, group_label_map, selection_mapping)
            self._expand_single_root()

    def set_audio_refs(self, refs: tuple[AudioRef, ...], *, summary_text: str) -> None:
        """刷新全部音频平铺列表与摘要。

        Args:
            refs: 当前实体全部路径级 WEM 引用。
            summary_text: 当前搜索状态对应的摘要文案。
        """
        self.clear_load_progress()
        self.set_summary_text(summary_text)
        self.audio_list.set_audio_refs(refs)

    def set_audio_keyword(self, keyword: str) -> None:
        """将当前搜索关键字应用到全部音频模型。"""
        self.audio_list.set_keyword(keyword)

    def set_preview_mode(self, mode_key: str) -> None:
        """切换事件树与全部音频平铺列表。"""
        self.preview_stack.setCurrentWidget(
            self.audio_list if mode_key == ALL_AUDIO_PREVIEW_MODE else self.audio_preview_tree
        )

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
        audio_path: Path | None,
        *,
        progress: float,
        is_playing: bool,
        is_paused: bool,
    ) -> None:
        """同步当前试听叶子行的播放状态。"""
        self.audio_preview_tree.set_audio_playback_state(
            audio_path,
            progress=progress,
            is_playing=is_playing,
            is_paused=is_paused,
        )
        self.audio_list.set_audio_playback_state(
            audio_path,
            progress=progress,
            is_playing=is_playing,
            is_paused=is_paused,
        )
