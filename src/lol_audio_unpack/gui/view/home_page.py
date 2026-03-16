from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    SmoothScrollArea,
    TitleLabel,
    BodyLabel,
    CardWidget,
    SubtitleLabel,
    CaptionLabel,
    ProgressBar,
    FlowLayout,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    IndeterminateProgressBar,
)
from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common import GuiConfig
from lol_audio_unpack.gui.workers import TaskWorker
from lol_audio_unpack.manager.utils import get_game_version


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


# ---------------------------------------------------------------------------
# ClickableCard
# ---------------------------------------------------------------------------

class ClickableCard(CardWidget):
    """Clickable card that opens a path in the system file manager on click.

    If the path is unset / non-existent an InfoBar warning is displayed.
    """

    def __init__(self, icon, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(240, 140)

        self._raw_path: str = ""  # resolved path for jump; empty = no jump

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

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def setPath(self, path: str) -> None:
        """Register the filesystem path this card should jump to."""
        self._raw_path = path
        self.contentLabel.setText(path if path else "")
        self.contentLabel.setToolTip(path if path else "")

    def setDisplayText(self, text: str) -> None:
        """Set display text without affecting the jump path."""
        self.contentLabel.setText(text)
        self.contentLabel.setToolTip(text)

    # ------------------------------------------------------------------
    # Click → open in file manager
    # ------------------------------------------------------------------

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self._open_in_explorer()

    def _open_in_explorer(self) -> None:
        raw = self._raw_path.strip()
        if not raw:
            self._warn("路径未设置", "请先在「全局设置」中配置此路径。")
            return

        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p

        if p.is_file():
            target = p.parent
        elif p.is_dir():
            target = p
        else:
            # Traverse upward to find nearest existing ancestor
            ancestor = p.parent
            while ancestor != ancestor.parent and not ancestor.exists():
                ancestor = ancestor.parent
            if ancestor.exists():
                target = ancestor
            else:
                self._warn("路径不存在", f"找不到路径：{raw}")
                return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

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

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root_layout = QVBoxLayout(self.view)
        root_layout.setContentsMargins(36, 36, 36, 36)
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

        # ── Overview cards ─────────────────────────────────────────────
        root_layout.addWidget(CaptionLabel("概览", self))

        self.overview_flow = FlowLayout()
        self.overview_flow.setContentsMargins(0, 0, 0, 0)
        self.overview_flow.setHorizontalSpacing(16)
        self.overview_flow.setVerticalSpacing(16)

        self.version_card = ClickableCard(FIF.CODE, "游戏版本", "读取中…", self)
        self.version_card.linkIcon.hide()
        self.version_card.setCursor(Qt.CursorShape.ArrowCursor)
        self.version_card._raw_path = ""

        self.game_dir_card = ClickableCard(FIF.FOLDER, "游戏目录", "未设置", self)
        self.output_dir_card = ClickableCard(FIF.DOWNLOAD, "输出目录", r".\output", self)

        # Cache-status card (no path jump initially; will be set if found)
        self.cache_card = ClickableCard(FIF.SYNC, "缓存资源", "检查中…", self)

        for card in (
            self.version_card,
            self.cache_card,
            self.game_dir_card,
            self.output_dir_card,
        ):
            self.overview_flow.addWidget(card)

        root_layout.addLayout(self.overview_flow)

        # ── Tool cards ─────────────────────────────────────────────────
        root_layout.addWidget(CaptionLabel("工具配置", self))

        self.tools_flow = FlowLayout()
        self.tools_flow.setContentsMargins(0, 0, 0, 0)
        self.tools_flow.setHorizontalSpacing(16)
        self.tools_flow.setVerticalSpacing(16)

        self.wwiser_card = ClickableCard(
            FIF.DEVELOPER_TOOLS, "wwiser", r".\tools\wwiser\wwiser.pyz", self
        )
        self.vgmstream_card = ClickableCard(
            FIF.COMMAND_PROMPT, "vgmstream-cli", r".\tools\vgmstream\vgmstream-cli.exe", self
        )

        for card in (self.wwiser_card, self.vgmstream_card):
            self.tools_flow.addWidget(card)

        root_layout.addLayout(self.tools_flow)
        root_layout.addStretch(1)

    # ------------------------------------------------------------------
    # Config → cards sync (called at init and when settings change)
    # ------------------------------------------------------------------

    def _sync_from_config(self) -> None:
        """Pull current GuiConfig values into path-based cards."""
        cfg = self._cfg

        if cfg.game_path:
            self.game_dir_card.setPath(cfg.game_path)
        else:
            self.game_dir_card.setPath("")
            self.game_dir_card.setDisplayText("未设置")

        output = cfg.output_path or r".\output"
        self.output_dir_card.setPath(output)

        self.wwiser_card.setPath(cfg.wwiser_path or r".\tools\wwiser\wwiser.pyz")
        self.vgmstream_card.setPath(
            cfg.vgmstream_path or r".\tools\vgmstream\vgmstream-cli.exe"
        )

    # ------------------------------------------------------------------
    # Background initialisation worker
    # ------------------------------------------------------------------

    def _resolve_output_path(self) -> Path:
        """Return the absolute output directory path."""
        raw = self._cfg.output_path or r".\output"
        p = Path(raw).expanduser()
        return p if p.is_absolute() else Path.cwd() / p

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
        self._loading_widget.setVisible(True)
        self.progress_bar.start()

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
        else:
            self._current_version = r.version
            self.version_card.setDisplayText(r.version)

        # — cache card —
        if not r.version:
            # Cannot determine version → cannot check cache
            self.cache_card.setDisplayText("无法获取版本")
            self.cache_card.linkIcon.hide()
        elif r.cache_found:
            self.cache_card.setPath(r.cache_path)
            self.cache_card.setDisplayText(f"已找到 {r.version}")
        else:
            output_path = self._resolve_output_path()
            audios_dir = output_path / "audios"
            self.cache_card.setPath(str(audios_dir))
            self.cache_card.setDisplayText(f"无 {r.version} 缓存")

        self._finish_loading("就绪")

    def _on_check_failed(self, error: str) -> None:
        """Handle unexpected worker exception."""
        self.version_card.setDisplayText("读取失败")
        self.cache_card.setDisplayText("检查失败")
        self.cache_card.linkIcon.hide()
        self._finish_loading(f"初始化失败: {error}")

    def _finish_loading(self, message: str) -> None:
        self.progress_bar.stop()
        self.loading_label.setText(message)

    # ------------------------------------------------------------------
    # Public update helpers (called by MainWindow on settings change)
    # ------------------------------------------------------------------

    def update_game_dir(self, path: str) -> None:
        if path:
            self.game_dir_card.setPath(path)
        else:
            self.game_dir_card.setPath("")
            self.game_dir_card.setDisplayText("未设置")
        # Re-run background check with new game path
        self._start_background_check()

    def update_output_dir(self, path: str) -> None:
        display = path if path else r".\output"
        self.output_dir_card.setPath(display)
        # Re-check cache with new output path
        if self._current_version:
            self._start_background_check()

    def update_wwiser(self, path: str) -> None:
        self.wwiser_card.setPath(path or r".\tools\wwiser\wwiser.pyz")

    def update_vgmstream(self, path: str) -> None:
        self.vgmstream_card.setPath(path or r".\tools\vgmstream\vgmstream-cli.exe")

    # Legacy compat
    def update_dir_status(self, has_dir: bool, version: str | None = None) -> None:
        pass
