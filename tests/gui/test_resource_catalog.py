"""GUI 资源目录统一入口的回归测试。"""

from PySide6.QtSvg import QSvgRenderer
from qfluentwidgets import ImageLabel

from lol_audio_unpack.gui.resources import assets


def test_window_icon_loads_from_app_assets(qtbot) -> None:
    """应用图标应能从统一资源入口加载。"""
    _ = qtbot
    icon = assets.app.window_icon()

    assert not icon.isNull()


def test_logo_asset_can_load_into_svg_renderer() -> None:
    """logo 资源应能被 SVG 渲染器消费。"""
    renderer = QSvgRenderer()

    assets.app.logo_svg().load_into(renderer)

    assert renderer.isValid()


def test_dot_icon_uses_circle_template() -> None:
    """dot 图标应复用现有圆点模板。"""
    assert assets.icons.DOT.path().endswith("circle-solid-full.svg")


def test_bilibili_icon_uses_icon_directory_asset() -> None:
    """B 站图标应从 icon 子目录加载。"""
    assert assets.icons.BILIBILI.path().endswith("bilibili-brands-solid-full.svg")


def test_icon_assets_expose_uppercase_constants_only() -> None:
    """图标资源入口应只保留大写常量式访问。"""
    assert assets.icons.PAUSE.path().endswith("pause-solid-full.svg")
    assert assets.icons.PLAY.path().endswith("play-solid-full.svg")
    assert assets.icons.STOP.path().endswith("stop-solid-full.svg")
    assert not hasattr(assets.icons, "pause")
    assert not hasattr(assets.icons, "play")
    assert not hasattr(assets.icons, "stop")
    assert not hasattr(assets.icons, "dot")
    assert not hasattr(assets.icons, "bilibili")


def test_wechat_qr_asset_applies_to_image_label(qtbot) -> None:
    """二维码图片资源应能应用到 ImageLabel。"""
    label = ImageLabel()
    qtbot.addWidget(label)

    assets.images.wechat_qr().apply_to(label)

    assert not label.image.isNull()
