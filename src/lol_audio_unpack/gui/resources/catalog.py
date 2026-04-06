"""组织 GUI 资源的统一 catalog 入口。"""

from dataclasses import dataclass
from functools import cached_property

from PySide6.QtGui import QIcon

from lol_audio_unpack.gui.resources.defs import APP_DEFS, ICON_DEFS, IMAGE_DEFS
from lol_audio_unpack.gui.resources.runtime import resolve_first, resolve_required
from lol_audio_unpack.gui.resources.types import AppIconAsset, IconAsset, ImageAsset, SvgAsset


class AppAssets:
    """提供应用级资源访问入口。"""

    def window_icon_asset(self) -> AppIconAsset:
        """返回应用窗口图标候选集合。

        Returns:
            AppIconAsset: 已解析的窗口图标候选集合。
        """

        candidates = tuple(
            path
            for rel_path in APP_DEFS.window_icon.rel_paths
            if (path := resolve_first((rel_path,))) is not None
        )
        return AppIconAsset(candidates)

    def window_icon(self) -> QIcon:
        """返回可直接用于窗口的应用图标。

        Returns:
            QIcon: 已解析的应用图标对象。
        """

        return self.window_icon_asset().load()

    def logo_svg(self) -> SvgAsset:
        """返回应用 logo SVG 资源。

        Returns:
            SvgAsset: 应用 logo 资源对象。
        """

        return SvgAsset(resolve_required(APP_DEFS.logo_svg.rel_paths[0]))


class IconAssets:
    """提供图标模板资源访问入口。"""

    @cached_property
    def PAUSE(self) -> IconAsset:
        """返回暂停图标模板。"""

        return IconAsset(resolve_required(ICON_DEFS.pause.rel_path))

    @cached_property
    def PLAY(self) -> IconAsset:
        """返回播放图标模板。"""

        return IconAsset(resolve_required(ICON_DEFS.play.rel_path))

    @cached_property
    def STOP(self) -> IconAsset:
        """返回停止图标模板。"""

        return IconAsset(resolve_required(ICON_DEFS.stop.rel_path))

    @cached_property
    def DOT(self) -> IconAsset:
        """返回圆点图标模板常量。"""

        return IconAsset(resolve_required(ICON_DEFS.dot.rel_path))

    @cached_property
    def BILIBILI(self) -> IconAsset:
        """返回 B 站品牌图标模板。"""

        return IconAsset(resolve_required(ICON_DEFS.bilibili.rel_path))


class ImageAssets:
    """提供普通图片资源访问入口。"""

    def wechat_qr(self) -> ImageAsset:
        """返回微信二维码图片资源。"""

        return ImageAsset(resolve_required(IMAGE_DEFS.wechat_qr.rel_path))

    def alipay_qr(self) -> ImageAsset:
        """返回支付宝二维码图片资源。"""

        return ImageAsset(resolve_required(IMAGE_DEFS.alipay_qr.rel_path))


@dataclass(frozen=True, slots=True)
class GuiAssets:
    """组合所有 GUI 资源子入口。

    Args:
        app: 应用级资源入口。
        icons: 图标模板入口。
        images: 普通图片入口。
    """

    app: AppAssets
    icons: IconAssets
    images: ImageAssets


assets = GuiAssets(app=AppAssets(), icons=IconAssets(), images=ImageAssets())
