"""测试关于页面中的品牌展示。"""

from __future__ import annotations

import re

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QEnterEvent, QFont
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from qfluentwidgets import IconWidget, Theme, qconfig, setTheme
from qfluentwidgets.common.icon import FluentIconBase

from lol_audio_unpack import __version__
from lol_audio_unpack.gui.common.styles import get_fluent_frame_stroke_pair
from lol_audio_unpack.gui.view.about_page import (
    AboutPage,
    AboutRotatingLogoWidget,
    FaShakeIconWidget,
    SponsorDialog,
)

MIN_HERO_TITLE_GAP = 28
SHAKE_SETTLE_EPSILON = 0.1
SHAKE_PROGRESS_WAIT_MS = 120
SHAKE_REENTRY_WAIT_MS = 180
SHAKE_REENTRY_ANGLE_TOLERANCE = 20.0
LOGO_HALO_SETTLE_EPSILON = 0.05
CARD_ICON_TITLE_GAP = 18
CARD_SUBTITLE_PIXEL_SIZE = 12
CARD_VALUE_PIXEL_SIZE = 20
CARD_TITLE_LIGHT = QColor(36, 36, 36, 140).name(QColor.NameFormat.HexArgb).lower()
CARD_TITLE_DARK = QColor(255, 255, 255, 170).name(QColor.NameFormat.HexArgb).lower()
CARD_HELPER_LIGHT = QColor(36, 36, 36, 112).name(QColor.NameFormat.HexArgb).lower()
CARD_HELPER_DARK = QColor(255, 255, 255, 128).name(QColor.NameFormat.HexArgb).lower()
CARD_VALUE_LIGHT = QColor(17, 17, 17).name(QColor.NameFormat.HexArgb).lower()
CARD_VALUE_DARK = QColor(255, 255, 255).name(QColor.NameFormat.HexArgb).lower()


def test_about_page_displays_valid_svg_logo(qtbot) -> None:
    """关于页面应展示可用的 SVG logo。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    app.processEvents()

    logo = page.findChild(AboutRotatingLogoWidget, "AboutPageLogo")

    assert logo is not None
    assert logo.is_logo_ready() is True


def test_about_page_renders_hero_and_action_cards(qtbot) -> None:
    """关于页应包含主视觉、底部信息卡片与技术栈标签。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    app.processEvents()

    labels = {label.text() for label in page.findChildren(QLabel)}

    assert "Lol Audio Unpack" in labels
    assert __version__ in labels
    assert "英雄联盟音频提取与事件映射工具" in labels
    assert "作者" in labels
    assert "仓库地址" in labels
    assert "B站" in labels
    assert "赞助支持" in labels
    assert "Python" in labels
    assert "PySide6" in labels
    assert "QFluentWidgets" in labels

    assert page.findChild(QWidget, "AboutHeroCard") is not None
    assert page.findChild(QWidget, "AboutActionCardAuthor") is not None
    assert page.findChild(QWidget, "AboutActionCardRepository") is not None
    assert page.findChild(QWidget, "AboutActionCardBilibili") is not None
    assert page.findChild(QWidget, "AboutActionCardSponsor") is not None
    for icon_name in (
        "AboutActionCardAuthorIcon",
        "AboutActionCardRepositoryIcon",
        "AboutActionCardBilibiliIcon",
        "AboutActionCardSponsorIcon",
    ):
        icon_widget = page.findChild(FaShakeIconWidget, icon_name)
        assert icon_widget is not None
        assert isinstance(icon_widget._icon, FluentIconBase)
    assert "Msgpack" not in labels


def test_about_page_clicking_sponsor_card_opens_qr_dialog(qtbot, monkeypatch) -> None:
    """点击赞助卡片后应弹出包含微信和支付宝二维码的模态框。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    page.resize(900, 700)
    page.show()
    app.processEvents()

    sponsor_card = page.findChild(QWidget, "AboutActionCardSponsor")

    assert sponsor_card is not None

    captured: dict[str, SponsorDialog] = {}

    def fake_exec(self) -> int:
        captured["dialog"] = self
        return 0

    monkeypatch.setattr(SponsorDialog, "exec", fake_exec)

    qtbot.mouseClick(sponsor_card, Qt.LeftButton, pos=sponsor_card.rect().center())
    app.processEvents()

    dialog = captured.get("dialog")

    assert dialog is not None

    labels = {label.text() for label in dialog.findChildren(QLabel)}

    assert "赞助支持" in labels
    assert "微信支付" in labels
    assert "支付宝" in labels


def test_sponsor_dialog_uses_solid_surface_container(qtbot) -> None:
    """赞助弹窗的主体容器背景必须是完全不透明的。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1200, 800)
    host.show()
    qtbot.addWidget(host)

    dialog = SponsorDialog(host)
    qtbot.addWidget(dialog)
    app.processEvents()

    style = dialog.widget.styleSheet().replace(" ", "").replace("\n", "").lower()
    assert "qwidget#sponsordialogcontent" in style
    assert (
        re.search(
            r"qwidget#sponsordialogcontent\{background:rgb\(\d+,\d+,\d+\);",
            style,
        )
        is not None
        or re.search(
            r"qwidget#sponsordialogcontent\{background:rgba\(\d+,\d+,\d+,255\);",
            style,
        )
        is not None
    )
    assert "qframe#buttongroup{background:transparent;" in style


def test_sponsor_dialog_description_keeps_single_line_when_space_is_enough(qtbot) -> None:
    """赞助说明文案在当前模态框宽度足够时不应被强制折行。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1200, 800)
    host.show()
    qtbot.addWidget(host)

    dialog = SponsorDialog(host)
    qtbot.addWidget(dialog)
    app.processEvents()

    description_label = dialog.findChild(QLabel, "SponsorDialogDescription")

    assert description_label is not None
    assert description_label.wordWrap() is False
    assert (
        description_label.fontMetrics().horizontalAdvance(description_label.text())
        <= dialog.widget.width() - 48
    )


def test_about_page_helper_labels_use_dedicated_subtitle_style(qtbot) -> None:
    """卡片文本应具备明确的主次层级样式入口。"""
    app = QApplication.instance() or QApplication([])
    original_theme = qconfig.theme

    try:
        setTheme(Theme.LIGHT)
        page = AboutPage()
        qtbot.addWidget(page)
        app.processEvents()

        title_label = page.findChild(QLabel, "AboutActionCardAuthorTitle")
        helper_label = page.findChild(QLabel, "AboutActionCardAuthorHelper")
        value_label = page.findChild(QLabel, "AboutActionCardAuthorValue")

        assert title_label is not None
        assert helper_label is not None
        assert value_label is not None

        assert title_label.font().pixelSize() == CARD_SUBTITLE_PIXEL_SIZE
        assert helper_label.font().pixelSize() == CARD_SUBTITLE_PIXEL_SIZE
        assert value_label.font().pixelSize() == CARD_VALUE_PIXEL_SIZE
        assert int(value_label.font().weight()) == int(QFont.Weight.Bold)
        assert CARD_TITLE_LIGHT in title_label.styleSheet().lower()
        assert CARD_HELPER_LIGHT in helper_label.styleSheet().lower()
        assert CARD_VALUE_LIGHT in value_label.styleSheet().lower()

        setTheme(Theme.DARK)
        app.processEvents()

        assert CARD_TITLE_DARK in title_label.styleSheet().lower()
        assert CARD_HELPER_DARK in helper_label.styleSheet().lower()
        assert CARD_VALUE_DARK in value_label.styleSheet().lower()
    finally:
        setTheme(original_theme)


def test_about_page_keeps_clear_gap_between_logo_and_title(qtbot) -> None:
    """主 logo 与标题之间应保留明显纵向留白。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    page.resize(900, 700)
    page.show()
    app.processEvents()

    logo_shell = page.findChild(QWidget, "AboutLogoShell")
    title_label = page.findChild(QLabel, "AboutHeroTitle")

    assert logo_shell is not None
    assert title_label is not None
    assert title_label.geometry().top() - logo_shell.geometry().bottom() >= MIN_HERO_TITLE_GAP


def test_about_page_logo_rotates_lightly_on_hover(qtbot) -> None:
    """主 logo 的 hover 应只触发轻微旋转，不再使用 halo。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    page.resize(900, 700)
    page.show()
    app.processEvents()

    logo_shell = page.findChild(QWidget, "AboutLogoShell")
    logo = page.findChild(AboutRotatingLogoWidget, "AboutPageLogo")

    assert logo_shell is not None
    assert logo is not None
    assert page.findChild(QWidget, "AboutLogoHalo") is None

    initial_angle = logo.rotationAngle

    logo_shell.enterEvent(QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10)))
    qtbot.wait(120)
    app.processEvents()

    assert abs(logo.rotationAngle) > abs(initial_angle)

    logo_shell.leaveEvent(QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10)))
    qtbot.wait(220)
    app.processEvents()

    assert abs(logo.rotationAngle) < LOGO_HALO_SETTLE_EPSILON


def test_about_page_card_keeps_clear_gap_between_icon_and_title(qtbot) -> None:
    """D 方案下图标区和第一行副标题之间应有明显留白。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    page.resize(900, 700)
    page.show()
    app.processEvents()

    icon_shell = page.findChild(QWidget, "AboutActionCardAuthorIconShell")
    title_label = page.findChild(QLabel, "AboutActionCardAuthorTitle")

    assert icon_shell is not None
    assert title_label is not None
    assert title_label.geometry().top() - icon_shell.geometry().bottom() >= CARD_ICON_TITLE_GAP


def test_about_page_action_icon_geometry_stays_stable_on_hover(qtbot) -> None:
    """整卡 hover 触发 shake 时图标几何仍应保持稳定。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    page.resize(900, 700)
    page.show()
    app.processEvents()

    card = page.findChild(QWidget, "AboutActionCardAuthor")
    icon_shell = page.findChild(QWidget, "AboutActionCardAuthorIconShell")

    assert card is not None
    assert icon_shell is not None

    icon_widget = next(
        child for child in icon_shell.findChildren(QWidget) if child.parent() is icon_shell
    )
    initial_shell_geometry = icon_shell.geometry()
    initial_icon_geometry = icon_widget.geometry()

    card.enterEvent(QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10)))
    qtbot.wait(SHAKE_PROGRESS_WAIT_MS)
    app.processEvents()

    assert icon_shell.geometry() == initial_shell_geometry
    assert icon_widget.geometry() == initial_icon_geometry
    assert icon_shell.graphicsEffect() is None


def test_about_page_bilibili_icon_replays_fa_shake_on_hover(qtbot) -> None:
    """整张 B 站卡片 hover 时应播放一次 Font Awesome 风格的 shake。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    page.resize(900, 700)
    page.show()
    app.processEvents()

    bilibili_card = page.findChild(QWidget, "AboutActionCardBilibili")
    bilibili_icon = page.findChild(FaShakeIconWidget, "AboutActionCardBilibiliIcon")

    assert bilibili_card is not None
    assert bilibili_icon is not None
    assert bilibili_icon.rotationAngle == 0.0

    bilibili_card.enterEvent(QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10)))
    qtbot.wait(SHAKE_PROGRESS_WAIT_MS)
    app.processEvents()

    assert bilibili_icon._shake_animation.state().name == "Running"
    assert abs(bilibili_icon.rotationAngle) > 1.0

    qtbot.wait(1100)
    app.processEvents()

    assert bilibili_icon._shake_animation.state().name == "Stopped"
    assert abs(bilibili_icon.rotationAngle) < SHAKE_SETTLE_EPSILON


def test_about_page_hover_does_not_restart_running_shake(qtbot) -> None:
    """动画播放中再次进入卡片不应重置为开头帧。"""
    app = QApplication.instance() or QApplication([])
    page = AboutPage()
    qtbot.addWidget(page)
    page.resize(900, 700)
    page.show()
    app.processEvents()

    author_card = page.findChild(QWidget, "AboutActionCardAuthor")
    author_icon = page.findChild(FaShakeIconWidget, "AboutActionCardAuthorIcon")

    assert author_card is not None
    assert author_icon is not None

    author_card.enterEvent(QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10)))
    qtbot.wait(SHAKE_REENTRY_WAIT_MS)
    app.processEvents()

    first_progress = author_icon._shake_animation.currentTime()
    first_angle = author_icon.rotationAngle

    author_card.enterEvent(QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10)))
    app.processEvents()

    assert author_icon._shake_animation.state().name == "Running"
    assert author_icon._shake_animation.currentTime() >= first_progress - 30
    assert abs(author_icon.rotationAngle - first_angle) < SHAKE_REENTRY_ANGLE_TOLERANCE


def test_about_page_tech_stack_pill_uses_visible_light_theme_border(qtbot) -> None:
    """技术栈标签在浅色主题下应使用可辨识描边。"""
    app = QApplication.instance() or QApplication([])
    original_theme = qconfig.theme
    light_border, _ = get_fluent_frame_stroke_pair()

    try:
        setTheme(Theme.LIGHT)
        page = AboutPage()
        qtbot.addWidget(page)
        app.processEvents()

        pill = next(
            widget
            for widget in page.findChildren(QWidget)
            if widget.property("aboutRole") == "pill"
        )

        assert pill is not None
        assert light_border in page.view.styleSheet()
        assert "QFrame[aboutRole=\"pill\"]" in page.view.styleSheet()
    finally:
        setTheme(original_theme)
