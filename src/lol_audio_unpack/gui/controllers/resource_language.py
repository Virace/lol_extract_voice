"""根据来源快照维护语言选择，隔离自动发现与用户主动留空。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.manager.source_inventory import SourceInventory, SourceLanguage


class ResourceLanguageController(QObject):
    """消费最新快照并在确认后保存语言偏好。"""

    changed = Signal()

    def __init__(self, config: GuiConfig, card, confirm: Callable[[SourceLanguage], bool], parent=None) -> None:
        """绑定配置、值控件及由展示层提供的缺失确认入口。"""
        super().__init__(parent)
        self.config = config
        self.card = card
        self.confirm = confirm
        self.inventory: SourceInventory | None = None
        card.comboBox.currentTextChanged.connect(self._select)

    def apply_inventory(self, inventory: SourceInventory) -> None:
        """只应用当前 generation；唯一有效语言首次可自动选中。"""
        if self.inventory is not None and inventory.generation < self.inventory.generation:
            return
        self.inventory = inventory
        old = self.config.game_region
        selected = inventory.get_language(old)
        value = selected.locale if selected and selected.available_count else ""
        available = [item for item in inventory.languages if item.available_count]
        if not value and not self.config.language_explicit and len(available) == 1:
            candidate = available[0]
            if candidate.status == "complete" or self.confirm(candidate):
                value = candidate.locale
            else:
                # 拒绝自动选中也是主动留空，后续刷新不能重复打扰。
                self.config.game_region = ""
                self.config.save()
        labels = {"请选择": ""}
        status = {"complete": "", "partial": "（部分缺失）", "unavailable": "（不可用）"}
        labels.update({f"{item.locale}{status[item.status]}": item.locale for item in inventory.languages})
        self.card.set_options(labels, value)
        if old != value:
            self.config.apply_discovered_language(value)
            self.config.save()
            self.changed.emit()

    def _select(self, _text: str) -> None:
        value = self.card.value()
        item = self.inventory.get_language(value) if self.inventory else None
        accepted = not value or (item is not None and (item.status == "complete" or self.confirm(item)))
        if not accepted or (value and item is not None and not item.available_count):
            previous = self.inventory.get_language(self.config.game_region) if self.inventory else None
            value = previous.locale if previous and previous.available_count else ""
        changed = self.config.game_region != value
        self.config.game_region = value
        blocked = self.card.comboBox.blockSignals(True)
        self.card.setValue(value)
        self.card.comboBox.blockSignals(blocked)
        self.config.save()
        if changed:
            self.changed.emit()
