from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QShowEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FlowLayout,
    IconWidget,
    IndeterminateProgressBar,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TitleLabel,
)
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common import GuiConfig, format_default_relative_path
from lol_audio_unpack.gui.common.style import (
    apply_page_content_margins,
    configure_transparent_scroll_page,
)
from lol_audio_unpack.gui.controllers import (
    HomeStatusController,
    HomeStatusDisplayState,
)
from lol_audio_unpack.gui.view.home.widgets import (
    ClickableCard,
    CompactStatusCard,
    ExecutionEntryCard,
    QuickOpenRow,
)
from lol_audio_unpack.utils.runtime_paths import (
    detect_runtime_paths,
    get_default_output_relative_path,
    get_default_output_root,
    get_default_vgmstream_path,
    get_default_vgmstream_relative_path,
    get_default_wwiser_path,
    get_default_wwiser_relative_path,
    resolve_runtime_path,
)

# ---------------------------------------------------------------------------
# HomePage
# ---------------------------------------------------------------------------

class HomePage(SmoothScrollArea):
    """Home page showing an overview dashboard with clickable folder cards.

    On show, a background worker reads the game version and checks whether
    a matching audio cache exists under the configured output directory.
    """

    navigate_to_execution_requested = Signal()

    def __init__(self, cfg: GuiConfig, parent=None):
        super().__init__(parent=parent)
        self._cfg = cfg
        self._current_version: str = ""  # filled in by worker
        self._initial_status_check_started = False
        self._home_status_controller = HomeStatusController(parent=self)
        self._home_status_controller.display_state_ready.connect(self._apply_home_status_display_state)

        self.view = configure_transparent_scroll_page(
            self,
            page_object_name="HomePage",
            view_object_name="HomePageView",
        )

        self._build_ui()
        self._sync_from_config()

    def showEvent(self, event: QShowEvent) -> None:
        """在页面首次显示后再启动首页状态检查。"""
        super().showEvent(event)
        if self._initial_status_check_started:
            return
        self._initial_status_check_started = True
        self._start_home_status_check()

    @staticmethod
    def _runtime_paths():
        """返回当前 GUI 运行时路径快照。"""
        return detect_runtime_paths()

    @staticmethod
    def _default_relative_display_path(relative_path: str) -> str:
        """将默认相对路径格式化为基于根目录的展示文案。"""
        return format_default_relative_path(f"./{relative_path}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root_layout = QVBoxLayout(self.view)
        apply_page_content_margins(root_layout)
        root_layout.setSpacing(24)

        # ── Title ──────────────────────────────────────────────────────
        self.title_label = TitleLabel("欢迎使用 Lol Audio Unpack", self)
        root_layout.addWidget(self.title_label)

        desc = BodyLabel(
            "该工具用于提取《英雄联盟》客户端中的原始音频资源，输出 `.wem` 文件，"
            "这包含了英雄与地图相关的可用资源。",
            self,
        )
        desc.setWordWrap(True)
        root_layout.addWidget(desc)

        # ── Loading (indeterminate until worker finishes) ───────────────
        self._loading_widget = QWidget(self)
        loading_layout = QVBoxLayout(self._loading_widget)
        loading_layout.setContentsMargins(0, 0, 0, 0)
        loading_layout.setSpacing(6)
        self.loading_label = CaptionLabel("正在读取游戏版本…", self)
        self.progress_bar = IndeterminateProgressBar(self)
        loading_layout.addWidget(self.loading_label)
        loading_layout.addWidget(self.progress_bar)
        root_layout.addWidget(self._loading_widget)

        self.top_status_widget = QWidget(self.view)
        self.top_status_layout = QHBoxLayout(self.top_status_widget)
        self.top_status_layout.setContentsMargins(0, 0, 0, 0)
        self.top_status_layout.setSpacing(16)

        self.version_card = CompactStatusCard(FIF.CODE, "游戏版本", "读取中…", self.top_status_widget)
        self.version_card.setJumpEnabled(False)
        self.version_card.setDetailText("当前游戏客户端版本。")

        self.cache_card = CompactStatusCard(FIF.SYNC, "资源状态", "检查中…", self.top_status_widget)
        self.cache_card.setJumpEnabled(False)
        self.cache_card.setDetailText("当前缓存资源状态。")

        self.execution_center_card = ExecutionEntryCard(self.top_status_widget)
        self.execution_center_card.requested.connect(self.navigate_to_execution_requested.emit)

        for card in (self.version_card, self.cache_card, self.execution_center_card):
            card.setMinimumHeight(116)
            self.top_status_layout.addWidget(card, 1)

        root_layout.addWidget(self.top_status_widget)

        self.entry_panel = QFrame(self.view)
        self.entry_panel_layout = QVBoxLayout(self.entry_panel)
        self.entry_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.entry_panel_layout.setSpacing(12)
        self.entry_header = QWidget(self.entry_panel)
        self.entry_header_layout = QVBoxLayout(self.entry_header)
        self.entry_header_layout.setContentsMargins(0, 0, 0, 0)
        self.entry_header_layout.setSpacing(4)
        self.entry_header_layout.addWidget(StrongBodyLabel("快捷入口", self.entry_header))
        self.entry_desc_label = CaptionLabel("这里可以快速打开常用目录和工具位置。", self.entry_header)
        self.entry_desc_label.setWordWrap(True)
        self.entry_header_layout.addWidget(self.entry_desc_label)
        self.entry_panel_layout.addWidget(self.entry_header)

        self.entry_list_layout = QVBoxLayout()
        self.entry_list_layout.setContentsMargins(0, 0, 0, 0)
        self.entry_list_layout.setSpacing(10)

        self.game_dir_card = QuickOpenRow(FIF.FOLDER, "游戏目录", "未设置", "打开目录", self.entry_panel)
        self.output_dir_card = QuickOpenRow(
            FIF.DOWNLOAD,
            "输出目录",
            self._default_relative_display_path(get_default_output_relative_path()),
            "打开目录",
            self.entry_panel,
        )
        self.wwiser_card = QuickOpenRow(
            FIF.DEVELOPER_TOOLS,
            "wwiser",
            self._default_relative_display_path(get_default_wwiser_relative_path()),
            "打开位置",
            self.entry_panel,
        )
        self.vgmstream_card = QuickOpenRow(
            FIF.COMMAND_PROMPT,
            "vgmstream-cli",
            self._default_relative_display_path(get_default_vgmstream_relative_path()),
            "打开位置",
            self.entry_panel,
        )

        for card in (self.game_dir_card, self.output_dir_card, self.wwiser_card, self.vgmstream_card):
            self.entry_list_layout.addWidget(card)

        self.entry_panel_layout.addLayout(self.entry_list_layout)
        root_layout.addWidget(self.entry_panel)
        root_layout.addStretch(1)

    # ------------------------------------------------------------------
    # Config → cards sync (called at init and when settings change)
    # ------------------------------------------------------------------

    def _sync_from_config(self) -> None:
        """Pull current GuiConfig values into path-based cards."""
        cfg = self._cfg
        runtime_paths = self._runtime_paths()

        if cfg.game_path:
            self.game_dir_card.setPath(cfg.game_path)
            self.game_dir_card.setJumpEnabled(True)
        else:
            self.game_dir_card.setPath("")
            self.game_dir_card.setDisplayText("未设置")
            self.game_dir_card.setJumpEnabled(False)

        if cfg.output_path:
            self.output_dir_card.setPath(cfg.output_path)
        else:
            self.output_dir_card.setPath(str(get_default_output_root(runtime_paths)))
            self.output_dir_card.setDisplayText(
                self._default_relative_display_path(get_default_output_relative_path())
            )
        self.output_dir_card.setJumpEnabled(True)

        if cfg.wwiser_path:
            self.wwiser_card.setPath(cfg.wwiser_path)
        else:
            self.wwiser_card.setPath(str(get_default_wwiser_path(runtime_paths)))
            self.wwiser_card.setDisplayText(
                self._default_relative_display_path(get_default_wwiser_relative_path())
            )
        self.wwiser_card.setJumpEnabled(True)
        if cfg.vgmstream_path:
            self.vgmstream_card.setPath(cfg.vgmstream_path)
        else:
            self.vgmstream_card.setPath(str(get_default_vgmstream_path(runtime_paths)))
            self.vgmstream_card.setDisplayText(
                self._default_relative_display_path(get_default_vgmstream_relative_path())
            )
        self.vgmstream_card.setJumpEnabled(True)

    # ------------------------------------------------------------------
    # Background initialisation worker
    # ------------------------------------------------------------------

    def _resolve_output_path(self) -> Path:
        """Return the absolute output directory path."""
        return self._cfg.resolve_output_path()

    def _start_home_status_check(self) -> None:
        """启动首页版本与缓存状态检查。"""
        self._home_status_controller.start_check(
            game_path=self._cfg.resolve_game_path(),
            output_path=self._resolve_output_path(),
        )

    def has_active_background_check(self) -> bool:
        """返回首页状态后台检查是否仍在运行。"""
        return self._home_status_controller.has_active_background_check()

    def shutdown_background_check(self) -> None:
        """在窗口关闭前清理首页后台检查引用。"""
        self._home_status_controller.shutdown()

    def _apply_home_status_display_state(self, state: HomeStatusDisplayState) -> None:
        """把首页状态控制器产出的显示状态应用到卡片。"""
        self._current_version = state.current_version
        self.version_card.setDisplayText(state.version_text)
        self.version_card.setJumpEnabled(state.version_jump_enabled)
        self.cache_card.setPath(state.cache_path)
        self.cache_card.setDisplayText(state.cache_text)
        self.cache_card.setJumpEnabled(state.cache_jump_enabled)

    def set_loading_state(self, message: str, *, active: bool) -> None:
        """更新首页顶部的加载状态条。

        Args:
            message: 当前要展示的状态文案。
            active: 是否处于活跃加载阶段。
        """
        self._loading_widget.setVisible(True)
        self.loading_label.setText(message)
        if active:
            self.progress_bar.start()
        else:
            self.progress_bar.stop()

    # ------------------------------------------------------------------
    # Public update helpers (called by MainWindow on settings change)
    # ------------------------------------------------------------------

    def update_game_dir(self, path: str) -> None:
        if path:
            self.game_dir_card.setPath(path)
            self.game_dir_card.setJumpEnabled(True)
        else:
            self.game_dir_card.setPath("")
            self.game_dir_card.setDisplayText("未设置")
            self.game_dir_card.setJumpEnabled(False)
        # Re-run background check with new game path
        self._start_home_status_check()

    def update_output_dir(self, path: str) -> None:
        if path:
            self.output_dir_card.setPath(path)
        else:
            runtime_paths = self._runtime_paths()
            self.output_dir_card.setPath(str(get_default_output_root(runtime_paths)))
            self.output_dir_card.setDisplayText(
                self._default_relative_display_path(get_default_output_relative_path())
            )
        # Re-check cache with new output path
        if self._current_version:
            self._start_home_status_check()

    def update_wwiser(self, path: str) -> None:
        if path:
            self.wwiser_card.setPath(path)
            return

        runtime_paths = self._runtime_paths()
        self.wwiser_card.setPath(str(get_default_wwiser_path(runtime_paths)))
        self.wwiser_card.setDisplayText(
            self._default_relative_display_path(get_default_wwiser_relative_path())
        )

    def update_vgmstream(self, path: str) -> None:
        if path:
            self.vgmstream_card.setPath(path)
            return

        runtime_paths = self._runtime_paths()
        self.vgmstream_card.setPath(str(get_default_vgmstream_path(runtime_paths)))
        self.vgmstream_card.setDisplayText(
            self._default_relative_display_path(get_default_vgmstream_relative_path())
        )

    # Legacy compat
    def update_dir_status(self, has_dir: bool, version: str | None = None) -> None:
        pass
