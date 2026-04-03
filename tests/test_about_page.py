"""关于页面布局回归测试。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.gui.view.about_page import AboutActionCard, AboutPage, get_about_page_minimum_shell_size

EXPECTED_ABOUT_ACTION_CARD_COUNT = 4


def test_about_page_keeps_four_cards_visible_at_minimum_size(qtbot, tmp_path: Path) -> None:
    """关于页在最小尺寸下应保持四卡并排且无横向滚动。"""
    page = AboutPage()
    qtbot.addWidget(page)

    minimum_size = get_about_page_minimum_shell_size()
    page.resize(minimum_size)
    page.show()
    qtbot.waitUntil(
        lambda: page.isVisible()
        and len(page.findChildren(AboutActionCard)) == EXPECTED_ABOUT_ACTION_CARD_COUNT
    )

    screenshot_path = tmp_path / "about-page-minimum.png"
    page.grab().save(str(screenshot_path))

    assert screenshot_path.exists()
    assert len(page.findChildren(AboutActionCard)) == EXPECTED_ABOUT_ACTION_CARD_COUNT
    assert not page.horizontalScrollBar().isVisible()
