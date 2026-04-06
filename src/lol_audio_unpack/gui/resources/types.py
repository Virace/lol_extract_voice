"""定义 GUI 资源层对外暴露的对象类型。"""

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtSvg import QSvgRenderer
from qfluentwidgets import ImageLabel, Theme
from qfluentwidgets.common.icon import FluentIconBase


class IconAsset(FluentIconBase):
    """描述可重着色的 SVG 图标模板。"""

    def __init__(self, source_path: Path) -> None:
        """初始化图标模板。

        Args:
            source_path: SVG 模板文件路径。
        """

        self._source_path = source_path

    def path(self, theme=Theme.AUTO) -> str:
        """返回图标模板路径。

        Args:
            theme: QFluentWidgets 主题入参，占位以满足接口要求。

        Returns:
            str: SVG 模板绝对路径。
        """

        _ = theme
        return str(self._source_path)


@dataclass(frozen=True, slots=True)
class SvgAsset:
    """描述可交给 SVG 渲染器消费的矢量资源。

    Args:
        source_path: SVG 文件路径。
    """

    source_path: Path

    def load_into(self, renderer: QSvgRenderer) -> None:
        """将资源加载到指定渲染器。

        Args:
            renderer: 目标 SVG 渲染器。
        """

        renderer.load(str(self.source_path))


@dataclass(frozen=True, slots=True)
class ImageAsset:
    """描述普通图片资源。

    Args:
        source_path: 图片文件路径。
    """

    source_path: Path

    def apply_to(self, label: ImageLabel) -> None:
        """将图片资源设置到 `ImageLabel`。

        Args:
            label: 目标图片标签控件。
        """

        label.setImage(str(self.source_path))


@dataclass(frozen=True, slots=True)
class AppIconAsset:
    """描述应用级窗口图标候选集合。

    Args:
        candidates: 按优先级排列的图标候选路径。
    """

    candidates: tuple[Path, ...]

    def load(self) -> QIcon:
        """加载首个可用应用图标。

        Returns:
            QIcon: 首个成功加载的图标；若都不可用则返回空图标。
        """

        for candidate in self.candidates:
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
        return QIcon()
