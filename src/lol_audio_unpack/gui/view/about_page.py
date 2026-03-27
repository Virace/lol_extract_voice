"""关于页面展示品牌信息、版本信息与相关链接。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    IconWidget,
    SimpleCardWidget,
    SmoothScrollArea,
    Theme,
    TitleLabel,
    isDarkTheme,
    qconfig,
)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.common.icon import FluentIconBase, drawIcon

from lol_audio_unpack import __version__
from lol_audio_unpack.gui.common.icon import get_app_logo_path
from lol_audio_unpack.gui.common.styles import (
    get_fluent_frame_stroke_pair,
    get_fluent_neutral_surface_pair,
)

AUTHOR_URL = "https://x-item.com"
REPOSITORY_URL = "https://github.com/Virace/lol_audio_unpack"
BILIBILI_URL = "https://space.bilibili.com/12353537"
TECH_STACK = ("Python", "PySide6", "QFluentWidgets")
BILIBILI_ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "bilibili.svg"


def _rgba_text(rgba: tuple[int, int, int, int]) -> str:
    """将 RGBA 元组转换为 QSS 可用的 `rgba(...)` 字符串。"""
    red, green, blue, alpha = rgba
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _configure_label_font(
    label: QWidget,
    *,
    pixel_size: int,
    weight: QFont.Weight = QFont.Weight.Normal,
) -> None:
    """配置单个标签的字号与字重。"""
    font = label.font()
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    label.setFont(font)


class AboutCustomIcon(FluentIconBase, Enum):
    """关于页使用的自定义 Fluent 图标。"""

    BILIBILI = "bilibili"

    def path(self, theme=Theme.AUTO) -> str:
        """返回图标路径。"""
        _ = theme
        return str(BILIBILI_ICON_PATH)


@dataclass(frozen=True, slots=True)
class AboutActionSpec:
    """关于页底部动作卡片定义。"""

    object_name: str
    icon: object
    title: str
    value: str
    helper: str
    url: str | None = None


class AboutRotatingLogoWidget(QWidget):
    """支持轻微旋转动画的关于页 Logo。"""

    def __init__(self, parent=None) -> None:
        """初始化 Logo 控件。"""
        super().__init__(parent)
        self.setObjectName("AboutPageLogo")
        self._rotation_angle = 0.0
        self._renderer = QSvgRenderer(self)

    def load_logo(self, logo_path: str) -> None:
        """加载 SVG Logo。"""
        self._renderer.load(logo_path)
        self.update()

    def is_logo_ready(self) -> bool:
        """返回当前 Logo 是否加载成功。"""
        return self._renderer.isValid()

    def get_rotation_angle(self) -> float:
        """返回当前旋转角度。"""
        return self._rotation_angle

    def set_rotation_angle(self, value: float) -> None:
        """更新当前旋转角度。"""
        self._rotation_angle = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        """按当前角度绘制 SVG Logo。"""
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        center = self.rect().center()
        painter.translate(center)
        painter.rotate(self._rotation_angle)
        painter.translate(-center)
        self._renderer.render(painter, QRectF(self.rect()))

    rotationAngle = Property(float, get_rotation_angle, set_rotation_angle)


class HoverLogoShell(QFrame):
    """带轻微旋转 hover 动画的 Logo 容器。"""

    def __init__(self, parent=None) -> None:
        """初始化 Logo 容器。"""
        super().__init__(parent)
        self.setObjectName("AboutLogoShell")
        self.setFixedSize(176, 176)
        self._base_size = 132

        self.logo_widget = AboutRotatingLogoWidget(self)
        self._update_logo_geometry()

        self._rotation_animation = QPropertyAnimation(self.logo_widget, b"rotationAngle", self)
        self._rotation_animation.setDuration(220)
        self._rotation_animation.setEasingCurve(QEasingCurve.OutCubic)

    def set_logo(self, logo_path: str) -> None:
        """设置 SVG logo 路径。"""
        self.logo_widget.load_logo(logo_path)

    def enterEvent(self, event) -> None:
        """鼠标进入时轻微旋转 logo。"""
        super().enterEvent(event)
        self._animate_rotation(4.0)

    def leaveEvent(self, event) -> None:
        """鼠标离开时恢复 logo 角度。"""
        super().leaveEvent(event)
        self._animate_rotation(0.0)

    def _animate_rotation(self, target: float) -> None:
        """启动中心旋转动画。"""
        self._rotation_animation.stop()
        self._rotation_animation.setStartValue(self.logo_widget.rotationAngle)
        self._rotation_animation.setEndValue(target)
        self._rotation_animation.start()

    def resizeEvent(self, event) -> None:
        """容器尺寸变化时保持 logo 居中。"""
        super().resizeEvent(event)
        self._update_logo_geometry()

    def _update_logo_geometry(self) -> None:
        """保持 logo 居中。"""
        size = self._base_size
        x = (self.width() - size) // 2
        y = (self.height() - size) // 2
        self.logo_widget.setGeometry(x, y, size, size)


class FaShakeIconWidget(IconWidget):
    """复刻 Font Awesome `fa-shake` 的图标控件。"""

    def __init__(self, icon, parent=None) -> None:
        """初始化图标控件。"""
        super().__init__(parent)
        self.setIcon(icon)
        self._rotation_angle = 0.0
        self._shake_animation = QPropertyAnimation(self, b"rotationAngle", self)
        self._shake_animation.setDuration(1000)
        self._shake_animation.setEasingCurve(QEasingCurve.Linear)
        self._configure_fa_shake_keyframes()

    def _configure_fa_shake_keyframes(self) -> None:
        """配置与 Font Awesome 对齐的 `fa-shake` 关键帧。"""
        for progress, angle in (
            (0.00, -15.0),
            (0.04, 15.0),
            (0.08, -18.0),
            (0.12, 18.0),
            (0.16, -22.0),
            (0.20, 22.0),
            (0.24, -18.0),
            (0.28, 18.0),
            (0.32, -12.0),
            (0.36, 12.0),
            (0.40, 0.0),
            (1.00, 0.0),
        ):
            self._shake_animation.setKeyValueAt(progress, angle)

    def play_shake(self) -> None:
        """重新播放一次 shake 动画。"""
        if self._shake_animation.state() == QPropertyAnimation.Running:
            return

        self._shake_animation.stop()
        self._shake_animation.start()

    def get_rotation_angle(self) -> float:
        """返回当前旋转角度。"""
        return self._rotation_angle

    def set_rotation_angle(self, angle: float) -> None:
        """更新当前旋转角度并重绘。"""
        self._rotation_angle = float(angle)
        self.update()

    def paintEvent(self, event) -> None:
        """在绘制图标时应用旋转。"""
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        center = self.rect().center()
        painter.translate(center)
        painter.rotate(self._rotation_angle)
        painter.translate(-center)
        drawIcon(self._icon, painter, self.rect())

    rotationAngle = Property(float, get_rotation_angle, set_rotation_angle)


class AboutActionIconShell(QFrame):
    """底部卡片使用的静态图标容器。"""

    def __init__(self, *, icon, animated: bool = True, parent=None) -> None:
        """初始化图标容器。"""
        super().__init__(parent)
        self.setFixedSize(76, 76)
        self._base_size = 24

        icon_widget_class = FaShakeIconWidget if animated else IconWidget
        self.icon_widget = icon_widget_class(icon, self)
        self.icon_widget.setStyleSheet("background: transparent;")
        self._update_icon_geometry()

    def resizeEvent(self, event) -> None:
        """尺寸变化时保持图标居中。"""
        super().resizeEvent(event)
        self._update_icon_geometry()

    def _update_icon_geometry(self) -> None:
        """更新图标几何位置。"""
        size = self._base_size
        x = int((self.width() - size) / 2)
        y = int((self.height() - size) / 2)
        self.icon_widget.setGeometry(x, y, size, size)


class AboutActionCard(SimpleCardWidget):
    """关于页底部的入口卡片。"""

    def __init__(self, spec: AboutActionSpec, parent=None) -> None:
        """初始化入口卡片。"""
        super().__init__(parent)
        self._url = spec.url
        self.setObjectName(spec.object_name)
        self.setFixedSize(196, 236)
        self.setBorderRadius(20)
        self.setCursor(Qt.PointingHandCursor if spec.url else Qt.ArrowCursor)
        self.setProperty("aboutRole", "action")
        self._animated_icon_widget: FaShakeIconWidget | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        icon_shell = AboutActionIconShell(
            icon=spec.icon,
            animated=True,
            parent=self,
        )
        icon_shell.setObjectName(f"{spec.object_name}IconShell")
        icon_shell.icon_widget.setObjectName(f"{spec.object_name}Icon")
        if isinstance(icon_shell.icon_widget, FaShakeIconWidget):
            self._animated_icon_widget = icon_shell.icon_widget

        title_label = CaptionLabel(spec.title, self)
        title_label.setObjectName(f"{spec.object_name}Title")
        title_label.setAlignment(Qt.AlignHCenter)
        value_label = BodyLabel(spec.value, self)
        value_label.setObjectName(f"{spec.object_name}Value")
        value_label.setAlignment(Qt.AlignHCenter)
        helper_label = CaptionLabel(spec.helper, self)
        helper_label.setObjectName(f"{spec.object_name}Helper")
        helper_label.setWordWrap(True)
        helper_label.setAlignment(Qt.AlignHCenter)

        title_label.setTextColor(QColor(36, 36, 36, 140), QColor(255, 255, 255, 170))
        helper_label.setTextColor(QColor(36, 36, 36, 112), QColor(255, 255, 255, 128))
        value_label.setTextColor(QColor(17, 17, 17), QColor(255, 255, 255))
        _configure_label_font(title_label, pixel_size=12)
        _configure_label_font(helper_label, pixel_size=12)
        _configure_label_font(value_label, pixel_size=20, weight=QFont.Weight.Bold)

        layout.addWidget(icon_shell, alignment=Qt.AlignHCenter)
        layout.addSpacing(28)
        layout.addWidget(title_label)
        layout.addSpacing(12)
        layout.addWidget(value_label)
        layout.addSpacing(12)
        layout.addWidget(helper_label)
        layout.addStretch(1)

    def enterEvent(self, event) -> None:
        """鼠标进入整张卡片时触发图标 shake。"""
        super().enterEvent(event)
        if self._animated_icon_widget is not None:
            self._animated_icon_widget.play_shake()

    def mouseReleaseEvent(self, event) -> None:
        """整卡点击时打开目标链接。"""
        super().mouseReleaseEvent(event)
        if self._url:
            QDesktopServices.openUrl(QUrl(self._url))


class AboutPage(SmoothScrollArea):
    """展示项目品牌信息、版本信息与外部链接。"""

    def __init__(self, parent=None):
        """初始化关于页面。

        Args:
            parent: 父级窗口或容器。
        """
        super().__init__(parent=parent)
        self.setObjectName("AboutPage")
        self.view = QWidget(self)
        self.view.setObjectName("AboutPageView")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea {border: none; background: transparent;}")
        qconfig.themeChanged.connect(self._refresh_theme_styles)

        self._build_ui()

    def _refresh_theme_styles(self, *_args: object) -> None:
        """按当前主题刷新关于页的容器样式。"""
        self.view.setStyleSheet(self._build_view_stylesheet())

    def _build_view_stylesheet(self) -> str:
        """根据当前主题构造关于页的样式表。"""
        light_idle_surface, dark_idle_surface = get_fluent_neutral_surface_pair("subtle_idle")
        light_hover_surface, dark_hover_surface = get_fluent_neutral_surface_pair("subtle_hover")
        light_border, dark_border = get_fluent_frame_stroke_pair()

        if isDarkTheme():
            action_background = _rgba_text(dark_idle_surface)
            action_hover_background = _rgba_text(dark_hover_surface)
            frame_border = dark_border
            accent_hover_border = "rgba(132, 168, 255, 68)"
        else:
            action_background = _rgba_text(light_idle_surface)
            action_hover_background = _rgba_text(light_hover_surface)
            frame_border = light_border
            accent_hover_border = "rgba(87, 132, 255, 48)"

        return f"""
        QWidget#AboutPageView {{
            background: transparent;
        }}
        QFrame#AboutHeroCard {{
            background: transparent;
            border: none;
        }}
        SimpleCardWidget[aboutRole="action"] {{
            background: {action_background};
            border: 1px solid {frame_border};
            border-radius: 20px;
        }}
        SimpleCardWidget[aboutRole="action"]:hover {{
            background: {action_hover_background};
            border: 1px solid {accent_hover_border};
        }}
        QFrame#AboutLogoShell {{
            background: transparent;
            border: none;
            border-radius: 34px;
        }}
        QFrame[aboutRole="pill"] {{
            background: {action_background};
            border: 1px solid {frame_border};
            border-radius: 14px;
        }}
        CaptionLabel#AboutPageSubtitle {{
            color: rgba(255, 255, 255, 0.72);
        }}
        QFrame#AboutActionCardAuthorIconShell {{
            background: rgba(70, 110, 255, 0.12);
            border-radius: 16px;
        }}
        QFrame#AboutActionCardRepositoryIconShell {{
            background: rgba(0, 0, 0, 0.08);
            border-radius: 16px;
        }}
        QFrame#AboutActionCardBilibiliIconShell {{
            background: rgba(0, 180, 255, 0.12);
            border-radius: 16px;
        }}
        QFrame#AboutActionCardSponsorIconShell {{
            background: rgba(255, 79, 141, 0.12);
            border-radius: 16px;
        }}
        """

    def _build_ui(self):
        """构建关于页面的布局内容。"""
        root_layout = QVBoxLayout(self.view)
        root_layout.setContentsMargins(36, 34, 36, 34)
        root_layout.setSpacing(24)
        self._refresh_theme_styles()

        hero_card = QFrame(self.view)
        hero_card.setObjectName("AboutHeroCard")
        hero_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        hero_card.setFixedHeight(338)
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(32, 10, 32, 12)
        hero_layout.setSpacing(6)
        hero_layout.setAlignment(Qt.AlignHCenter)

        logo_path = get_app_logo_path()
        if logo_path is not None:
            logo_shell = HoverLogoShell(hero_card)
            logo_shell.set_logo(str(logo_path))
            hero_layout.addWidget(logo_shell, alignment=Qt.AlignHCenter)
            hero_layout.addSpacing(34)

        hero_title = TitleLabel("Lol Audio Unpack", hero_card)
        hero_title.setObjectName("AboutHeroTitle")
        hero_title.setAlignment(Qt.AlignHCenter)
        hero_layout.addWidget(hero_title)

        hero_version = CaptionLabel(__version__, hero_card)
        hero_version.setAlignment(Qt.AlignHCenter)
        hero_layout.addWidget(hero_version)

        hero_description = BodyLabel("英雄联盟音频提取与事件映射工具", hero_card)
        hero_description.setAlignment(Qt.AlignHCenter)
        hero_description.setWordWrap(True)
        hero_layout.addWidget(hero_description)

        root_layout.addWidget(hero_card)

        tags_row = QWidget(self.view)
        tags_layout = QHBoxLayout(tags_row)
        tags_layout.setContentsMargins(0, 0, 0, 0)
        tags_layout.setSpacing(10)
        tags_layout.addStretch(1)
        for tech in TECH_STACK:
            pill = QFrame(self.view)
            pill.setProperty("aboutRole", "pill")
            pill_layout = QHBoxLayout(pill)
            pill_layout.setContentsMargins(14, 8, 14, 8)
            pill_layout.setSpacing(0)
            pill_layout.addWidget(CaptionLabel(tech, pill))
            tags_layout.addWidget(pill)
        tags_layout.addStretch(1)
        root_layout.addWidget(tags_row)

        cards_row = QWidget(self.view)
        cards_layout = QHBoxLayout(cards_row)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(16)
        cards_layout.addStretch(1)

        action_specs = (
            AboutActionSpec(
                object_name="AboutActionCardAuthor",
                icon=FIF.PEOPLE,
                title="作者",
                value="Virace",
                helper="个人主页",
                url=AUTHOR_URL,
            ),
            AboutActionSpec(
                object_name="AboutActionCardRepository",
                icon=FIF.GITHUB,
                title="仓库地址",
                value="GitHub",
                helper="查看代码",
                url=REPOSITORY_URL,
            ),
            AboutActionSpec(
                object_name="AboutActionCardBilibili",
                icon=AboutCustomIcon.BILIBILI.colored("#242424", "#F5F5F5"),
                title="B站",
                value="Virace",
                helper="频道入口",
                url=BILIBILI_URL,
            ),
            AboutActionSpec(
                object_name="AboutActionCardSponsor",
                icon=FIF.HEART,
                title="赞助支持",
                value="支持作者",
                helper="赞助入口",
            ),
        )
        for spec in action_specs:
            cards_layout.addWidget(AboutActionCard(spec, cards_row))
        cards_layout.addStretch(1)
        root_layout.addWidget(cards_row)
        root_layout.addStretch(1)
