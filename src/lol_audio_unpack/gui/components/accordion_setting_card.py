"""可复用的手风琴式设置卡组件。"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import SimpleExpandGroupSettingCard


class FormAccordionCard(SimpleExpandGroupSettingCard):
    """统一手风琴设置卡的容器与行布局。

    该组件用于复用执行中心与设置页里相同的「左侧标题/说明 + 右侧控件」
    行格式，避免多个手风琴卡片各自维护一套近似但容易漂移的布局实现。

    Args:
        icon: 卡片图标。
        title: 卡片标题。
        content: 卡片副标题。
        parent: 父级控件。
    """

    def __init__(
        self,
        icon: Any,
        title: str,
        content: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(icon, title, content, parent)
        self.viewLayout.setContentsMargins(0, 0, 0, 8)
        self.viewLayout.setSpacing(0)

    def add_form_row(
        self,
        label_text: str,
        description_text: str,
        widget: QWidget,
        *,
        min_height: int = 60,
    ) -> QWidget:
        """添加统一格式的设置项行。

        Args:
            label_text: 左侧主标题。
            description_text: 左侧说明文字。
            widget: 右侧交互控件。
            min_height: 行最小高度。

        Returns:
            已添加到卡片中的行控件。
        """

        row = QWidget(self.view)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row.setMinimumHeight(min_height)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(48, 12, 48, 12)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignVCenter)

        label_column = QVBoxLayout()
        label_column.setContentsMargins(0, 0, 0, 0)
        label_column.setSpacing(0)

        title_label = QLabel(label_text, row)
        title_label.setObjectName("titleLabel")
        title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label_column.addWidget(title_label)

        description_label = QLabel(description_text, row)
        description_label.setObjectName("contentLabel")
        description_label.setWordWrap(False)
        description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label_column.addWidget(description_label)

        layout.addLayout(label_column, 1)
        layout.addWidget(widget, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.addGroupWidget(row)
        return row
