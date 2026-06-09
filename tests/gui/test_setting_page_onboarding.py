"""设置页新手引导入口测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.controllers.onboarding_state import GUIDE_VERSION
from lol_audio_unpack.gui.view import setting_page as setting_page_module
from lol_audio_unpack.gui.view.setting_page import SettingPage


def test_setting_page_reset_onboarding_state(qtbot, monkeypatch) -> None:
    """重置引导入口应清除当前版本状态并提示下次启动显示。"""

    page = SettingPage()
    qtbot.addWidget(page)
    page.config.mark_onboarding_completed(GUIDE_VERSION)
    notices: list[dict[str, str]] = []
    monkeypatch.setattr(setting_page_module, "show_feedback_infobar", lambda **kwargs: notices.append(kwargs))

    page._reset_onboarding_state()

    assert page.config.should_show_onboarding(GUIDE_VERSION) is True
    assert notices[-1]["title"] == "已重置"
    assert notices[-1]["content"] == "下次启动后会自动显示新手引导。"
