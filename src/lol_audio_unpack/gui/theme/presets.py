"""固定强调色预设与参考色阶定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtGui import QColor

AccentPresetId = Literal["purple", "blue", "green", "orange"]
DEFAULT_ACCENT_PRESET_ID: AccentPresetId = "blue"
_TONES = (50, 100, 200, 300, 500, 700, 900, 950)


@dataclass(slots=True, frozen=True)
class AccentScale:
    """描述一个固定强调色预设的参考色阶。

    Args:
        values: tone 到十六进制颜色的映射。
    """

    values: dict[int, str]

    def value(self, tone: int) -> str:
        """返回指定 tone 的颜色值。"""
        return self.values.get(tone, self.values[500])

    def color(self, tone: int) -> QColor:
        """返回指定 tone 的 `QColor`。"""
        return QColor(self.value(tone))


@dataclass(slots=True, frozen=True)
class AccentPreset:
    """描述一个固定强调色预设。

    Args:
        id: 预设稳定标识。
        label: 面向用户的显示名称。
        scale: 该预设的参考色阶。
        dark_hex: 深色主题下优先使用的主强调色；为空时回退到 ``scale[500]``。
    """

    id: AccentPresetId
    label: str
    scale: AccentScale
    dark_hex: str | None = None

    @property
    def primary_hex(self) -> str:
        """返回该预设当前用于 Fluent accent 的主色。"""
        return self.scale.value(500)

    @property
    def primary_color(self) -> QColor:
        """返回该预设当前用于 Fluent accent 的主色对象。"""
        return self.scale.color(500)

    def resolve_primary_hex(self, *, dark: bool = False) -> str:
        """返回指定主题模式下应使用的主强调色。"""
        if dark and self.dark_hex:
            return self.dark_hex
        return self.primary_hex

    def resolve_primary_color(self, *, dark: bool = False) -> QColor:
        """返回指定主题模式下应使用的主强调色对象。"""
        return QColor(self.resolve_primary_hex(dark=dark))


@dataclass(slots=True, frozen=True)
class ThemeProgressPalette:
    """描述进度条组件未来将消费的语义色槽位。

    Args:
        track_base: 轨道主背景色。
        track_border: 轨道边框色。
        fill_main: 主要填充色。
        fill_emphasis: 填充高亮色。
        text_primary: 主文案颜色。
        text_secondary: 次级文案颜色。
        button_icon: 操作按钮图标颜色。
        button_hover: 操作按钮悬停背景色。
        button_pressed: 操作按钮按下背景色。
    """

    track_base: QColor
    track_border: QColor
    fill_main: QColor
    fill_emphasis: QColor
    text_primary: QColor
    text_secondary: QColor
    button_icon: QColor
    button_hover: QColor
    button_pressed: QColor


def _scale(*values: str) -> AccentScale:
    """按固定 tone 序列构造强调色色阶。"""
    return AccentScale(values=dict(zip(_TONES, values, strict=True)))


_ACCENT_PRESETS: tuple[AccentPreset, ...] = (
    AccentPreset(
        id="purple",
        label="紫色",
        scale=_scale(
            "#F7F2FF",
            "#EDE3FF",
            "#D9C6FF",
            "#BEA0FF",
            "#8A63D2",
            "#6A43AD",
            "#432A73",
            "#2C1B4C",
        ),
    ),
    AccentPreset(
        id="blue",
        label="蓝色",
        scale=_scale(
            "#F1F7FD",
            "#E0EDF9",
            "#C8E0F5",
            "#A2CDEE",
            "#4C83D2",
            "#3768BE",
            "#2D497B",
            "#202E4B",
        ),
    ),
    AccentPreset(
        id="green",
        label="绿色",
        scale=_scale(
            "#F7FAEF",
            "#ECF2D8",
            "#D3E2AF",
            "#ADC878",
            "#78964A",
            "#567136",
            "#374724",
            "#243018",
        ),
        dark_hex="#60783A",
    ),
    AccentPreset(
        id="orange",
        label="橙色",
        scale=_scale(
            "#FFF6ED",
            "#FFE7D0",
            "#FFD1A8",
            "#FFB06E",
            "#D88943",
            "#B6672C",
            "#78411C",
            "#4B2912",
        ),
    ),
)

_PRESET_BY_ID = {preset.id: preset for preset in _ACCENT_PRESETS}


def list_accent_presets() -> tuple[AccentPreset, ...]:
    """返回所有固定强调色预设。"""
    return _ACCENT_PRESETS


def get_accent_preset(id: AccentPresetId | str) -> AccentPreset:
    """按标识返回固定强调色预设。"""
    return _PRESET_BY_ID[resolve_accent_preset_id(id)]


def resolve_accent_preset_id(id: AccentPresetId | str | None) -> AccentPresetId:
    """把任意输入收敛成受支持的强调色预设标识。"""
    text = str(id or "").strip().lower()
    if text in _PRESET_BY_ID:
        return text  # type: ignore[return-value]
    return DEFAULT_ACCENT_PRESET_ID


def resolve_legacy_accent_preset(color: str | None) -> AccentPresetId:
    """把旧自由主题色迁移到固定强调色预设。

    Args:
        color: 旧配置中的十六进制颜色值。

    Returns:
        AccentPresetId: 能稳定落到的固定预设；未知颜色回退到默认值。
    """
    normalized = str(color or "").strip().lower()
    if not normalized:
        return DEFAULT_ACCENT_PRESET_ID

    for preset in _ACCENT_PRESETS:
        tone_values = {value.lower() for value in preset.scale.values.values()}
        if normalized in tone_values:
            return preset.id

    return DEFAULT_ACCENT_PRESET_ID
