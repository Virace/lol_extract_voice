"""只读任务核对窗口，名单和参数来自即将提交的同一任务快照。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, MessageBoxBase, SubtitleLabel, TableView

from lol_audio_unpack.config import SettingKey
from lol_audio_unpack.gui.controllers.execution_review import ExecutionReview
from lol_audio_unpack.gui.theme import get_semantic_text_color_pair


class ConfirmationDialog(MessageBoxBase):
    """集中核对英雄、地图与特殊内容，不提供第二份编辑表单。"""

    def __init__(self, review: ExecutionReview, parent=None) -> None:
        """以冻结的目标清单构造有限高度的滚动列表。"""
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel("确认执行任务", self))
        summary = BodyLabel(review.draft.source_summary, self)
        summary.setWordWrap(True)
        self.viewLayout.addWidget(summary)
        if review.warnings or not review.can_submit:
            text = "；".join(review.warnings)
            if not review.can_submit:
                text += "。没有有效目标，请返回修改。"
            warning = BodyLabel("提示：" + text, self)
            warning.setWordWrap(True)
            warning.setTextColor(*get_semantic_text_color_pair("caution"))
            self.viewLayout.addWidget(warning)

        self.table = TableView(self)
        self.model = QStandardItemModel(self)
        group_rows = []
        group = None
        for row in review.items:
            if row.group != group:
                group = row.group
                heading = QStandardItem(group)
                identifier = QStandardItem(
                    "ID" if any(item.identifier for item in review.items if item.group == group) else ""
                )
                font = heading.font()
                font.setBold(True)
                heading.setFont(font)
                identifier.setFont(font)
                identifier.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                group_rows.append(self.model.rowCount())
                self.model.appendRow([heading, identifier])
            self.model.appendRow([QStandardItem(row.name), QStandardItem(row.identifier)])
        self.table.setModel(self.model)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.verticalHeader().setMinimumSectionSize(28)
        for row in group_rows:
            self.table.setRowHeight(row, 28)
        # 清单在确认期间不可编辑；按全部行高收缩，超过原高度上限后滚动查看。
        height = self.table.verticalHeader().length() + self.table.frameWidth() * 2
        self.table.setFixedHeight(min(210, height))
        self.table.setVisible(bool(review.items))
        self.viewLayout.addWidget(self.table)

        params = review.draft.task_params
        settings = review.draft.context_input.to_settings()
        lines = [
            "执行：" + "、".join(params.selected_steps()),
            f"音频：{'仅 VO' if params.exclude_types == ('SFX', 'MUSIC') else '全部类型'}"
            f"；大厅音频：{'开启' if params.lobby_audio else '关闭'}；并发：{params.max_workers}",
        ]
        if params.wav_enabled:
            lines.append(
                f"转码：{params.wav_format}；并发：{params.wav_workers}；超时：{params.wav_timeout}s；最多尝试：{params.wav_retries} 次"
            )
        if params.run_mapping:
            lines.append(f"映射整合：{'开启' if params.integrate_data else '关闭'}")
        if params.map_ids and 0 not in params.map_ids:
            lines.append("地图数据准备会使用 Common（0）完成去重。")
        lines.extend(
            (
                f"版本：{review.draft.version or '当前版本'}；语言：{settings.get(SettingKey.GAME_REGION) or '默认语言'}",
                f"输出：{settings.get(SettingKey.OUTPUT_PATH) or '默认输出目录'}",
            )
        )
        details = QWidget(self)
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(8)
        for line in lines:
            detail = BodyLabel(line, details)
            detail.setWordWrap(True)
            detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            detail_layout.addWidget(detail)
        self.viewLayout.addWidget(details)
        self.widget.setMinimumWidth(520)
        self.widget.setMaximumWidth(640)
        self.yesButton.setText("确认")
        self.cancelButton.setText("返回修改")
        self.buttonLayout.removeWidget(self.cancelButton)
        self.buttonLayout.insertWidget(0, self.cancelButton, 1, Qt.AlignmentFlag.AlignVCenter)
        self.setTabOrder(self.cancelButton, self.yesButton)
        self.yesButton.setEnabled(review.can_submit)
