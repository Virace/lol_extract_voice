"""验证动态语言选择的确认、恢复与迟到快照边界。"""

from pathlib import Path

from qfluentwidgets import FluentIcon as FIF

from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.controllers.resource_language import ResourceLanguageController
from lol_audio_unpack.gui.view.settings.cards import ComboRowSettingCard
from lol_audio_unpack.manager.source_inventory import SourceEntity, SourceInventory, SourceLanguage


def make_language(locale: str, *, missing: bool = False, partial: bool = False) -> SourceLanguage:
    """构造具有实际实体缺失语义的语言快照。"""
    entities = [SourceEntity("champion", "1", "Annie", ("one.wad",), ("one.wad",) if missing else ())]
    if partial:
        entities.append(SourceEntity("champion", "2", "Olaf", ("two.wad",), ("two.wad",)))
    return SourceLanguage(locale, tuple(entities))


def make_controller(qtbot, tmp_path, confirm):
    """使用真实配置和值控件，隔离人工确认。"""
    cfg = GuiConfig()
    cfg._config_file = tmp_path / "settings.ini"
    card = ComboRowSettingCard(FIF.LANGUAGE, "语言", "", ["请选择"], {"请选择": ""})
    qtbot.addWidget(card)
    return ResourceLanguageController(cfg, card, confirm)


def test_unique_language_selects_once_and_explicit_empty_stays(qtbot, tmp_path):
    """首次唯一语言自动生效，用户清空后重扫不得重新选中。"""
    controller = make_controller(qtbot, tmp_path, lambda _: True)
    language = make_language("ja_JP")
    controller.apply_inventory(SourceInventory(tmp_path, 1, (language,)))
    assert controller.config.game_region == "ja_JP"
    controller.card.setValue("")
    controller.apply_inventory(SourceInventory(tmp_path, 2, (language,)))
    controller.config.load()
    assert controller.config.game_region == ""
    controller.config.load()
    assert controller.config.language_explicit
    assert controller.config.language_explicit


def test_unavailable_choice_restores_valid_language_and_stale_result_is_ignored(qtbot, tmp_path):
    """不可用语言能查看原因但不能提交，迟到结果不能清空当前选择。"""
    shown = []
    controller = make_controller(qtbot, tmp_path, lambda item: shown.append(item.locale) or False)
    japanese = make_language("ja_JP")
    english = make_language("en_US", missing=True)
    controller.apply_inventory(SourceInventory(tmp_path, 2, (japanese, english)))
    controller.card.setValue("en_US")
    assert shown == ["en_US"]
    assert controller.card.value() == controller.config.game_region == "ja_JP"
    controller.apply_inventory(SourceInventory(Path("old-game"), 1, (english,)))
    assert controller.config.game_region == "ja_JP"


def test_partial_unique_language_requires_confirmation_and_cancel_is_persisted(qtbot, tmp_path):
    """唯一部分语言也须确认，取消后保持空且刷新不重复弹窗。"""
    shown = []
    controller = make_controller(qtbot, tmp_path, lambda item: shown.append(item.locale) or False)
    language = make_language("ja_JP", partial=True)
    controller.apply_inventory(SourceInventory(tmp_path, 1, (language,)))
    controller.apply_inventory(SourceInventory(tmp_path, 2, (language,)))
    assert shown == ["ja_JP"]
    assert controller.config.game_region == ""
    controller.card.setValue("ja_JP")
    assert controller.config.game_region == ""
