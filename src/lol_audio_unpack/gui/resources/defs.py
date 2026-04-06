"""定义 GUI 静态资源的语义名称与相对路径。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AssetDef:
    """描述单文件资源定义。

    Args:
        rel_path: 相对 `gui/assets/` 的资源路径。
    """

    rel_path: str


@dataclass(frozen=True, slots=True)
class CandidateAssetDef:
    """描述带候选文件列表的资源定义。

    Args:
        rel_paths: 按优先级排列的相对资源路径。
    """

    rel_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AppDefs:
    """描述应用级资源定义集合。

    Args:
        window_icon: 应用窗口图标候选列表。
        logo_svg: 应用 logo 候选列表。
    """

    window_icon: CandidateAssetDef
    logo_svg: CandidateAssetDef


@dataclass(frozen=True, slots=True)
class IconDefs:
    """描述 SVG 图标模板定义集合。

    Args:
        pause: 暂停图标模板。
        play: 播放图标模板。
        stop: 停止图标模板。
        dot: 圆点图标模板。
        bilibili: B 站品牌图标模板。
    """

    pause: AssetDef
    play: AssetDef
    stop: AssetDef
    dot: AssetDef
    bilibili: AssetDef


@dataclass(frozen=True, slots=True)
class ImageDefs:
    """描述普通图片资源定义集合。

    Args:
        wechat_qr: 微信二维码图片。
        alipay_qr: 支付宝二维码图片。
    """

    wechat_qr: AssetDef
    alipay_qr: AssetDef


APP_DEFS = AppDefs(
    window_icon=CandidateAssetDef(("app_icon.ico", "app_icon.png", "app_icon.svg")),
    logo_svg=CandidateAssetDef(("app_icon.svg", "app_icon.png")),
)

ICON_DEFS = IconDefs(
    pause=AssetDef("icon/pause-solid-full.svg"),
    play=AssetDef("icon/play-solid-full.svg"),
    stop=AssetDef("icon/stop-solid-full.svg"),
    dot=AssetDef("icon/circle-solid-full.svg"),
    bilibili=AssetDef("icon/bilibili-brands-solid-full.svg"),
)

IMAGE_DEFS = ImageDefs(
    wechat_qr=AssetDef("qr/wechat.png"),
    alipay_qr=AssetDef("qr/ali.png"),
)
