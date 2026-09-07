"""统一事件树与全部音频列表的路径级试听行样式。"""

from __future__ import annotations

from PySide6.QtGui import QColor

from lol_audio_unpack.gui.theme import current_accent_preset_id, get_accent_preset

AUDIO_ROW_HORIZONTAL_MARGIN = 10
AUDIO_ROW_LEADING_SLOT_WIDTH = 28
AUDIO_ROW_TEXT_GAP = 4
AUDIO_ROW_SELECTED_BAR_WIDTH = 3
AUDIO_ROW_SELECTED_BAR_MARGIN = 0
AUDIO_ROW_BUTTON_SIZE = 18
AUDIO_ROW_BUTTON_GAP = 6
# 平铺播放按钮与树根展开箭头共用中心轴，但不预留整格箭头位置。
AUDIO_ROW_BUTTON_LEADING_INSET = (AUDIO_ROW_LEADING_SLOT_WIDTH - AUDIO_ROW_BUTTON_SIZE) // 2


def active_audio_row_color(*, is_dark: bool) -> QColor:
    """返回活动试听行的弱强调底色。

    Args:
        is_dark: 当前是否使用暗色主题。

    Returns:
        与当前强调色预设匹配的半透明行底色。
    """
    tone = 900 if is_dark else 100
    color = get_accent_preset(current_accent_preset_id()).scale.color(tone)
    color.setAlpha(44 if is_dark else 38)
    return color


def audio_progress_color(*, is_dark: bool, is_playing: bool) -> QColor:
    """返回整行试听进度的强调底色。

    Args:
        is_dark: 当前是否使用暗色主题。
        is_playing: 当前条目是否正在播放。

    Returns:
        播放或暂停状态对应的半透明进度颜色。
    """
    tone = 700 if is_dark else 300
    color = get_accent_preset(current_accent_preset_id()).scale.color(tone)
    color.setAlpha(72 if is_playing else 56)
    return color


def audio_control_colors(*, is_dark: bool) -> tuple[QColor, QColor]:
    """返回活动试听按钮的背景与图标颜色。

    Args:
        is_dark: 当前是否使用暗色主题。

    Returns:
        背景色与图标色组成的二元组。
    """
    preset = get_accent_preset(current_accent_preset_id())
    background = preset.scale.color(900 if is_dark else 100)
    background.setAlpha(52 if is_dark else 46)
    icon = preset.scale.color(100 if is_dark else 700)
    return background, icon


def audio_selection_bar_color(*, is_dark: bool) -> QColor:
    """返回选中试听行左侧竖条的强调色。

    Args:
        is_dark: 当前是否使用暗色主题。

    Returns:
        与当前强调色预设匹配的实色竖条颜色。
    """
    return get_accent_preset(current_accent_preset_id()).scale.color(300 if is_dark else 700)


__all__ = [
    "AUDIO_ROW_BUTTON_GAP",
    "AUDIO_ROW_BUTTON_LEADING_INSET",
    "AUDIO_ROW_BUTTON_SIZE",
    "AUDIO_ROW_HORIZONTAL_MARGIN",
    "AUDIO_ROW_LEADING_SLOT_WIDTH",
    "AUDIO_ROW_SELECTED_BAR_MARGIN",
    "AUDIO_ROW_SELECTED_BAR_WIDTH",
    "AUDIO_ROW_TEXT_GAP",
    "active_audio_row_color",
    "audio_control_colors",
    "audio_progress_color",
    "audio_selection_bar_color",
]
