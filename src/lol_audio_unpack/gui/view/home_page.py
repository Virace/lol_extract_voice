from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
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
from lol_audio_unpack.gui.common.style import apply_page_content_margins
from lol_audio_unpack.gui.workers import TaskWorker
from lol_audio_unpack.manager.utils import get_game_version
from lol_audio_unpack.utils.runtime_paths import (
    detect_runtime_paths,
    get_default_output_relative_path,
    get_default_output_root,
    get_default_vgmstream_path,
    get_default_vgmstream_relative_path,
    get_default_wwiser_path,
    get_default_wwiser_relative_path,
)

# ---------------------------------------------------------------------------
# Worker result dataclass
# ---------------------------------------------------------------------------

@dataclass
class HomeCheckResult:
    """Result produced by the background home-page initialisation worker."""
    version: str             # e.g. "16.5", or "" on error
    version_error: str       # non-empty when version lookup failed
    cache_found: bool        # True when matching audios/<ver>* folder exists
    cache_path: str          # the matched folder path, or "" when not found


# ---------------------------------------------------------------------------
# ElidedLabel
# ---------------------------------------------------------------------------

class ElidedLabel(CaptionLabel):
    """A label that elides text when it overflows the layout."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setMinimumWidth(50)

    def setText(self, text):
        self._full_text = text
        self._elide_text()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide_text()

    def _elide_text(self):
        metrics = self.fontMetrics()
        elided = metrics.elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, self.width() - 2
        )
        super().setText(elided)


def _open_path_in_explorer(raw: str, *, warn) -> None:
    """打开目标路径，必要时向上回退到最近存在的父目录。"""
    raw = raw.strip()
    if not raw:
        warn("路径未设置", "请先在「全局设置」中配置此路径。")
        return

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = detect_runtime_paths().launch_root / path

    if path.is_file():
        target = path.parent
    elif path.is_dir():
        target = path
    else:
        ancestor = path.parent
        while ancestor != ancestor.parent and not ancestor.exists():
            ancestor = ancestor.parent
        if ancestor.exists():
            target = ancestor
        else:
            warn("路径不存在", f"找不到路径：{raw}")
            return

    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


# ---------------------------------------------------------------------------
# ClickableCard
# ---------------------------------------------------------------------------

class ClickableCard(CardWidget):
    """Clickable card that opens a path in the system file manager on click.

    If the path is unset / non-existent an InfoBar warning is displayed.
    """

    def __init__(self, icon, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 140)

        self._raw_path: str = ""  # resolved path for jump; empty = no jump
        self._jump_enabled = True

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(20, 20, 20, 20)
        self.vBoxLayout.setSpacing(4)

        # Header (icon left, link icon right)
        self.headerLayout = QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)

        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(24, 24)

        self.linkIcon = IconWidget(FIF.LINK, self)
        self.linkIcon.setFixedSize(14, 14)

        self.headerLayout.addWidget(self.iconWidget)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.linkIcon)
        self.headerLayout.setAlignment(
            self.linkIcon, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
        )

        # Labels
        self.titleLabel = SubtitleLabel(title, self)

        self.contentLabel = ElidedLabel(content, self)
        self.contentLabel.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        self.contentLabel.setToolTip(content)

        self.vBoxLayout.addLayout(self.headerLayout)
        self.vBoxLayout.addSpacing(12)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addSpacing(4)
        self.vBoxLayout.addWidget(self.contentLabel)
        self.vBoxLayout.addStretch(1)
        self.setJumpEnabled(True)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def setPath(self, path: str) -> None:
        """Register the filesystem path this card should jump to."""
        self._raw_path = path
        display_path = format_default_relative_path(path) if path else ""
        self.contentLabel.setText(display_path)
        self.contentLabel.setToolTip(display_path)

    def setDisplayText(self, text: str) -> None:
        """Set display text without affecting the jump path."""
        self.contentLabel.setText(text)
        self.contentLabel.setToolTip(text)

    def isJumpEnabled(self) -> bool:
        """返回当前卡片是否具备跳转能力。"""
        return self._jump_enabled

    def setJumpEnabled(self, is_enabled: bool) -> None:
        """设置当前卡片是否允许跳转，并同步图标与鼠标样式。"""
        self._jump_enabled = bool(is_enabled)
        self.linkIcon.setVisible(self._jump_enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._jump_enabled
            else Qt.CursorShape.ArrowCursor
        )

    # ------------------------------------------------------------------
    # Click → open in file manager
    # ------------------------------------------------------------------

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if not self._jump_enabled:
            return
        self._open_in_explorer()

    def _open_in_explorer(self) -> None:
        _open_path_in_explorer(self._raw_path, warn=self._warn)

    def _warn(self, title: str, content: str) -> None:
        InfoBar.warning(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.window(),
        )


class CompactStatusCard(CardWidget):
    """首页顶部使用的紧凑状态卡。"""

    def __init__(self, icon, title: str, content: str, parent=None):
        super().__init__(parent)
        self._raw_path: str = ""
        self._jump_enabled = False

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(18, 18, 18, 18)
        self.vBoxLayout.setSpacing(8)

        self.headerLayout = QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        self.headerLayout.setSpacing(8)

        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(18, 18)
        self.linkIcon = IconWidget(FIF.LINK, self)
        self.linkIcon.setFixedSize(14, 14)
        self.linkIcon.hide()

        self.headerLayout.addWidget(self.iconWidget)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.linkIcon)

        self.titleCaption = CaptionLabel(title, self)
        self.valueLabel = StrongBodyLabel(content, self)
        self.detailLabel = CaptionLabel("", self)
        self.detailLabel.hide()
        self.detailLabel.setWordWrap(True)

        self.vBoxLayout.addLayout(self.headerLayout)
        self.vBoxLayout.addWidget(self.titleCaption)
        self.vBoxLayout.addWidget(self.valueLabel)
        self.vBoxLayout.addWidget(self.detailLabel)
        self.vBoxLayout.addStretch(1)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def setPath(self, path: str) -> None:
        """设置当前状态卡关联的跳转路径。"""
        self._raw_path = path

    def setDisplayText(self, text: str) -> None:
        """设置状态卡主文案。"""
        self.valueLabel.setText(text)

    def setDetailText(self, text: str) -> None:
        """设置状态卡补充说明。"""
        self.detailLabel.setVisible(bool(text))
        self.detailLabel.setText(text)

    def isJumpEnabled(self) -> bool:
        """返回当前状态卡是否允许跳转。"""
        return self._jump_enabled

    def setJumpEnabled(self, is_enabled: bool) -> None:
        """设置状态卡是否允许跳转。"""
        self._jump_enabled = bool(is_enabled)
        self.linkIcon.setVisible(self._jump_enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if self._jump_enabled else Qt.CursorShape.ArrowCursor
        )

    def mouseReleaseEvent(self, event):
        """处理状态卡点击跳转。"""
        super().mouseReleaseEvent(event)
        if self._jump_enabled:
            self._open_in_explorer()

    def _open_in_explorer(self) -> None:
        _open_path_in_explorer(self._raw_path, warn=self._warn)

    def _warn(self, title: str, content: str) -> None:
        InfoBar.warning(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.window(),
        )


class ExecutionEntryCard(CardWidget):
    """首页顶部的执行中心入口卡。"""

    requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(18, 18, 18, 18)
        self.vBoxLayout.setSpacing(8)

        self.titleCaption = CaptionLabel("Next Step", self)
        self.titleLabel = StrongBodyLabel("前往执行中心", self)
        self.detailLabel = CaptionLabel("首页不直接执行任务，只负责进入真正的执行流程页面。", self)
        self.detailLabel.setWordWrap(True)
        self.action_button = PrimaryPushButton("进入执行中心", self)
        self.action_button.clicked.connect(self.requested.emit)

        self.vBoxLayout.addWidget(self.titleCaption)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.detailLabel)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignLeft)


class QuickOpenRow(CardWidget):
    """首页下方的长条快捷入口。"""

    def __init__(self, icon, title: str, content: str, action_text: str, parent=None):
        super().__init__(parent)
        self._raw_path: str = ""
        self._jump_enabled = True

        self.rowLayout = QHBoxLayout(self)
        self.rowLayout.setContentsMargins(16, 14, 16, 14)
        self.rowLayout.setSpacing(14)

        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(18, 18)

        self.textLayout = QVBoxLayout()
        self.textLayout.setContentsMargins(0, 0, 0, 0)
        self.textLayout.setSpacing(4)
        self.titleLabel = BodyLabel(title, self)
        self.contentLabel = ElidedLabel(content, self)
        self.contentLabel.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        self.contentLabel.setToolTip(content)
        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.contentLabel)

        self.action_button = PushButton(action_text, self)
        self.action_button.clicked.connect(self._open_in_explorer)

        self.rowLayout.addWidget(self.iconWidget, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.rowLayout.addLayout(self.textLayout, 1)
        self.rowLayout.addWidget(self.action_button, alignment=Qt.AlignmentFlag.AlignVCenter)

    def setPath(self, path: str) -> None:
        """设置长条入口关联的真实路径。"""
        self._raw_path = path
        display_path = format_default_relative_path(path) if path else ""
        self.contentLabel.setText(display_path)
        self.contentLabel.setToolTip(display_path)

    def setDisplayText(self, text: str) -> None:
        """设置长条入口显示文本。"""
        self.contentLabel.setText(text)
        self.contentLabel.setToolTip(text)

    def isJumpEnabled(self) -> bool:
        """返回入口是否可跳转。"""
        return self._jump_enabled

    def setJumpEnabled(self, is_enabled: bool) -> None:
        """设置入口是否允许跳转。"""
        self._jump_enabled = bool(is_enabled)
        self.action_button.setEnabled(self._jump_enabled)

    def mouseReleaseEvent(self, event):
        """点击整行时也可触发打开。"""
        super().mouseReleaseEvent(event)
        if self._jump_enabled:
            self._open_in_explorer()

    def _open_in_explorer(self) -> None:
        if not self._jump_enabled:
            return
        _open_path_in_explorer(self._raw_path, warn=self._warn)

    def _warn(self, title: str, content: str) -> None:
        InfoBar.warning(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.window(),
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

        self.setObjectName("HomePage")
        self.view = QWidget(self)
        self.view.setObjectName("HomePageView")
        self.view.setStyleSheet("QWidget#HomePageView{background: transparent}")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea {border: none; background: transparent;}")

        self._build_ui()
        self._sync_from_config()
        self._start_background_check()

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

        self.version_card = CompactStatusCard(FIF.CODE, "Game Version", "读取中…", self.top_status_widget)
        self.version_card.setJumpEnabled(False)
        self.version_card.setDetailText("当前游戏客户端版本。")

        self.cache_card = CompactStatusCard(FIF.SYNC, "Cache Resource", "检查中…", self.top_status_widget)
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
        entry_desc = CaptionLabel(
            "主要承担目录与工具位置跳转。长条结构优先保证路径可读性，而不是信息堆叠。",
            self.entry_header,
        )
        entry_desc.setWordWrap(True)
        self.entry_header_layout.addWidget(entry_desc)
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
        runtime_paths = detect_runtime_paths()
        raw = self._cfg.output_path or str(get_default_output_root(runtime_paths))
        p = Path(raw).expanduser()
        return p if p.is_absolute() else runtime_paths.launch_root / p

    @staticmethod
    def _check_audio_cache(output_path: Path, major_minor: str) -> tuple[bool, str]:
        """Check if audios/<major.minor>* folder exists.

        Ignores the patch revision (e.g. '16.5' matches '16.5.1', '16.5.2', …).
        Returns (found, matched_path_str).
        """
        audios_dir = output_path / "audios"
        if not audios_dir.is_dir():
            return False, ""
        for child in audios_dir.iterdir():
            if child.is_dir() and child.name.startswith(major_minor):
                return True, str(child)
        return False, ""

    def _build_check_fn(self):
        """Return the callable for TaskWorker (captures config snapshot)."""
        game_path_str = self._cfg.game_path
        output_path = self._resolve_output_path()

        def _check() -> HomeCheckResult:
            # Step 1: game version
            if not game_path_str:
                return HomeCheckResult(
                    version="",
                    version_error="游戏目录未设置",
                    cache_found=False,
                    cache_path="",
                )
            try:
                version = get_game_version(Path(game_path_str))
            except Exception as exc:  # noqa: BLE001
                return HomeCheckResult(
                    version="",
                    version_error=str(exc),
                    cache_found=False,
                    cache_path="",
                )

            # Step 2: cache check
            found, matched = HomePage._check_audio_cache(output_path, version)
            return HomeCheckResult(
                version=version,
                version_error="",
                cache_found=found,
                cache_path=matched,
            )

        return _check

    def _start_background_check(self) -> None:
        """Kick off the background initialisation worker."""
        worker = TaskWorker(self._build_check_fn())
        worker.signals.finished.connect(self._on_check_finished)
        worker.signals.failed.connect(self._on_check_failed)
        QThreadPool.globalInstance().start(worker)

    def _on_check_finished(self, result: object) -> None:
        """Apply HomeCheckResult to the UI (called on the main thread)."""
        r: HomeCheckResult = result  # type: ignore[assignment]

        # — version card —
        if r.version_error:
            self.version_card.setDisplayText(r.version_error)
            self._current_version = ""
            self.version_card.setJumpEnabled(False)
        else:
            self._current_version = r.version
            self.version_card.setDisplayText(r.version)
            self.version_card.setJumpEnabled(False)

        # — cache card —
        if not r.version:
            # Cannot determine version → cannot check cache
            self.cache_card.setDisplayText("无法获取版本")
            self.cache_card.setJumpEnabled(False)
        elif r.cache_found:
            self.cache_card.setPath(r.cache_path)
            self.cache_card.setDisplayText(f"已找到 {r.version}")
            self.cache_card.setJumpEnabled(True)
        else:
            output_path = self._resolve_output_path()
            audios_dir = output_path / "audios"
            self.cache_card.setPath(str(audios_dir))
            self.cache_card.setDisplayText(f"无 {r.version} 缓存")
            self.cache_card.setJumpEnabled(True)

    def _on_check_failed(self, error: str) -> None:
        """Handle unexpected worker exception."""
        self.version_card.setDisplayText("读取失败")
        self.version_card.setJumpEnabled(False)
        self.cache_card.setDisplayText("检查失败")
        self.cache_card.setJumpEnabled(False)

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
        self._start_background_check()

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
            self._start_background_check()

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
