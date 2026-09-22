"""以独立滚动的文件清单说明当前语言的缺失与实体影响。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem
from qfluentwidgets import BodyLabel, ListWidget, MessageBoxBase, SubtitleLabel

from lol_audio_unpack.manager.source_inventory import SourceLanguage


class SourceMissingDialog(MessageBoxBase):
    """部分可用时确认范围；零可用时仅展示修复信息。"""

    def __init__(self, language: SourceLanguage, parent=None, *, previous: str = "") -> None:
        """构造单行路径清单，完整路径与影响实体可通过 hover 查看。"""
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel(f"{language.locale} 资源不完整", self))
        detail = (
            language.diagnostic or f"{language.available_count}/{len(language.entities)} 个实体可用。补齐文件后请刷新。"
        )
        label = BodyLabel(detail, self)
        label.setWordWrap(True)
        self.viewLayout.addWidget(label)
        recovery = f"取消后恢复为 {previous}。" if previous else "没有可恢复的语言，将保留为空。"
        self.viewLayout.addWidget(BodyLabel(recovery, self))
        files = ListWidget(self)
        files.setWordWrap(False)
        files.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        files.setMaximumHeight(280)
        records = language.missing_records
        for path in language.missing:
            affected = [entity.name for entity in language.entities if path in entity.missing]
            purposes = sorted({record.purpose for record in records if record.path == path})
            item = QListWidgetItem(path)
            item.setToolTip(f"{path}\n用途：{', '.join(purposes)}\n影响：{', '.join(affected)}")
            files.addItem(item)
        self.viewLayout.addWidget(files)
        self.widget.setMinimumWidth(560)
        self.yesButton.setText("使用可用资源")
        self.cancelButton.setText("取消" if language.available_count else "返回")
        self.yesButton.setVisible(bool(language.available_count))
