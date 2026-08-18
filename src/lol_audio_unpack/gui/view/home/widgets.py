"""首页展示组件。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    isDarkTheme,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from lol_audio_unpack.gui.common import format_default_relative_path
from lol_audio_unpack.gui.theme import SemanticColorRole, get_semantic_text_color_pair
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths, resolve_runtime_path

_STATUS_ICONS = {
    "accent": FIF.INFO,
    "info": FIF.INFO,
    "success": FIF.ACCEPT,
    "neutral": FIF.INFO,
    "caution": FIF.QUESTION,
    "critical": FIF.CANCEL,
}


def _apply_status_role(
    *,
    icon_widget: IconWidget,
    label: BodyLabel | CaptionLabel,
    role: SemanticColorRole,
) -> None:
    """把统一语义色应用到状态图标和文字。"""
    light, dark = get_semantic_text_color_pair(role)
    label.setTextColor(light, dark)
    icon_widget.setIcon(_STATUS_ICONS[role].icon(color=dark if isDarkTheme() else light))


class ElidedLabel(CaptionLabel):
    """会在空间不足时自动省略文本的标签。"""

    def __init__(self, text: str = "", parent: QWidget | None = None):
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
        elided = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width() - 2)
        super().setText(elided)


def _open_path_in_explorer(raw: str, *, warn) -> None:
    """打开目标路径，必要时回退到最近存在的父目录。"""
    raw = raw.strip()
    if not raw:
        warn("路径未设置", "请先在「全局设置」中配置此路径。")
        return

    path = resolve_runtime_path(raw, runtime_paths=detect_runtime_paths())

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


class ClickableCard(CardWidget):
    """首页可点击状态卡。"""

    def __init__(self, icon, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 140)

        self._raw_path: str = ""
        self._jump_enabled = True

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(20, 20, 20, 20)
        self.vBoxLayout.setSpacing(4)

        self.headerLayout = QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)

        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(24, 24)

        self.linkIcon = IconWidget(FIF.LINK, self)
        self.linkIcon.setFixedSize(14, 14)

        self.headerLayout.addWidget(self.iconWidget)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.linkIcon)
        self.headerLayout.setAlignment(self.linkIcon, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

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

    def setPath(self, path: str) -> None:
        """注册当前卡片应跳转到的文件系统路径。"""
        self._raw_path = path
        display_path = format_default_relative_path(path) if path else ""
        self.contentLabel.setText(display_path)
        self.contentLabel.setToolTip(display_path)

    def setDisplayText(self, text: str) -> None:
        """只更新显示文案，不修改跳转路径。"""
        self.contentLabel.setText(text)
        self.contentLabel.setToolTip(text)

    def isJumpEnabled(self) -> bool:
        """返回当前卡片是否允许跳转。"""
        return self._jump_enabled

    def setJumpEnabled(self, is_enabled: bool) -> None:
        """设置当前卡片是否允许跳转。"""
        self._jump_enabled = bool(is_enabled)
        self.linkIcon.setVisible(self._jump_enabled)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._jump_enabled else Qt.CursorShape.ArrowCursor)

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
        self._status_role: SemanticColorRole = "neutral"

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
        self.set_status_role("neutral")

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

    def set_status_role(self, role: SemanticColorRole) -> None:
        """设置主状态文字与图标的语义角色。"""
        self._status_role = role
        _apply_status_role(icon_widget=self.iconWidget, label=self.valueLabel, role=role)

    def refresh_theme(self) -> None:
        """在深浅主题或强调色变化后刷新语义色。"""
        self.set_status_role(self._status_role)

    def isJumpEnabled(self) -> bool:
        """返回当前状态卡是否允许跳转。"""
        return self._jump_enabled

    def setJumpEnabled(self, is_enabled: bool) -> None:
        """设置状态卡是否允许跳转。"""
        self._jump_enabled = bool(is_enabled)
        self.linkIcon.setVisible(self._jump_enabled)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._jump_enabled else Qt.CursorShape.ArrowCursor)

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


class StatusLine(QWidget):
    """以图标、颜色和简短文案展示首页环境状态。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        """初始化状态行。

        Args:
            text: 初始状态文案。
            parent: 父级控件。
        """
        super().__init__(parent)
        self._status_role: SemanticColorRole = "info"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.statusIcon = IconWidget(FIF.INFO, self)
        self.statusIcon.setFixedSize(16, 16)
        self.statusLabel = CaptionLabel(text, self)
        self.statusLabel.setWordWrap(True)
        layout.addWidget(self.statusIcon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.statusLabel, 1)
        self.set_status(text, role="info")

    def set_status(self, text: str, *, role: SemanticColorRole) -> None:
        """更新状态文案和语义角色。"""
        self._status_role = role
        self.statusLabel.setText(text)
        _apply_status_role(icon_widget=self.statusIcon, label=self.statusLabel, role=role)

    def refresh_theme(self) -> None:
        """在深浅主题或强调色变化后刷新语义色。"""
        self.set_status(self.statusLabel.text(), role=self._status_role)


class ExecutionEntryCard(CardWidget):
    """首页顶部的当前版本产物状态与操作入口。"""

    requested = Signal()
    overview_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(18, 18, 18, 18)
        self.vBoxLayout.setSpacing(6)
        self._status_role: SemanticColorRole = "neutral"

        self.headerLayout = QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        self.statusIcon = IconWidget(FIF.DOWNLOAD, self)
        self.statusIcon.setFixedSize(18, 18)
        self.titleCaption = CaptionLabel("当前版本产物", self)
        self.headerLayout.addWidget(self.statusIcon)
        self.headerLayout.addWidget(self.titleCaption)
        self.headerLayout.addStretch(1)

        self.titleLabel = StrongBodyLabel("检查中…", self)
        self.detailLabel = CaptionLabel("正在检查当前版本的音频产物。", self)
        self.detailLabel.setWordWrap(True)
        self.action_button = PrimaryPushButton("进入执行中心", self)
        self.overview_button = PushButton("查看总览", self)
        self.action_button.clicked.connect(self.requested.emit)
        self.overview_button.clicked.connect(self.overview_requested.emit)

        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        action_layout.addWidget(self.action_button)
        action_layout.addWidget(self.overview_button)
        action_layout.addStretch(1)

        self.vBoxLayout.addLayout(self.headerLayout)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.detailLabel)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addLayout(action_layout)
        self.set_status_role("neutral")

    def setDisplayText(self, text: str) -> None:
        """设置当前版本产物的主状态文案。"""
        self.titleLabel.setText(text)

    def setDetailText(self, text: str) -> None:
        """设置当前版本产物的补充说明。"""
        self.detailLabel.setText(text)

    def set_status_role(self, role: SemanticColorRole) -> None:
        """设置当前版本产物的语义角色。"""
        self._status_role = role
        _apply_status_role(icon_widget=self.statusIcon, label=self.titleLabel, role=role)

    def refresh_theme(self) -> None:
        """在深浅主题或强调色变化后刷新语义色。"""
        self.set_status_role(self._status_role)


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
