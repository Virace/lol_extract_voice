"""导出 GUI 资源系统的统一入口与资源类型。"""

from lol_audio_unpack.gui.resources.catalog import assets
from lol_audio_unpack.gui.resources.types import AppIconAsset, IconAsset, ImageAsset, SvgAsset

__all__ = ["AppIconAsset", "IconAsset", "ImageAsset", "SvgAsset", "assets"]
