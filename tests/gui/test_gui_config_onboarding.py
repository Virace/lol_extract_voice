"""GUI 新手引导状态配置测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.controllers.onboarding_state import GUIDE_VERSION

OLD_GUIDE_VERSION = "2026-05-old-guide"


def test_fresh_config_should_show_onboarding() -> None:
    """首次状态应自动展示当前引导版本。"""

    cfg = GuiConfig()

    assert cfg.should_show_onboarding(GUIDE_VERSION) is True


def test_completed_onboarding_should_not_show_again() -> None:
    """完成当前引导版本后不应再次自动展示。"""

    cfg = GuiConfig()

    cfg.mark_onboarding_completed(GUIDE_VERSION)

    assert cfg.should_show_onboarding(GUIDE_VERSION) is False


def test_skipped_onboarding_should_not_show_again() -> None:
    """跳过当前引导版本后不应再次自动展示。"""

    cfg = GuiConfig()

    cfg.mark_onboarding_skipped(GUIDE_VERSION)

    assert cfg.should_show_onboarding(GUIDE_VERSION) is False


def test_reset_completed_onboarding_should_show_again() -> None:
    """重置已完成的当前版本后应允许下次启动展示。"""

    cfg = GuiConfig()
    cfg.mark_onboarding_completed(GUIDE_VERSION)

    cfg.reset_onboarding(GUIDE_VERSION)

    assert cfg.should_show_onboarding(GUIDE_VERSION) is True


def test_reset_skipped_onboarding_should_show_again() -> None:
    """重置已跳过的当前版本后应允许下次启动展示。"""

    cfg = GuiConfig()
    cfg.mark_onboarding_skipped(GUIDE_VERSION)

    cfg.reset_onboarding(GUIDE_VERSION)

    assert cfg.should_show_onboarding(GUIDE_VERSION) is True


def test_new_onboarding_version_ignores_old_completion() -> None:
    """新引导版本不应被旧版本的完成状态压制。"""

    cfg = GuiConfig()

    cfg.mark_onboarding_completed(OLD_GUIDE_VERSION)

    assert cfg.should_show_onboarding(GUIDE_VERSION) is True
