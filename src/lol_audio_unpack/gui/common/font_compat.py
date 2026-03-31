"""GUI 字体兼容性辅助工具。"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets.common.style_sheet import setCustomStyleSheet

DEFAULT_DPI = 96.0


def build_font_with_point_size(font: QFont, *, dpi: float | None = None) -> QFont:
    """为只带像素字号的字体补齐一个安全的 point size。

    Args:
        font: 原始字体对象。
        dpi: 当前控件对应的垂直 DPI。

    Returns:
        QFont: 若原字体已有合法 point size，则原样复制返回；否则返回补齐 point size
        的兼容字体。
    """
    safe_font = QFont(font)
    if safe_font.pointSizeF() > 0:
        return safe_font

    pixel_size = safe_font.pixelSize()
    if pixel_size <= 0:
        return safe_font

    effective_dpi = float(dpi or 0)
    if effective_dpi <= 0:
        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
        effective_dpi = float(screen.logicalDotsPerInchY()) if screen is not None else DEFAULT_DPI

    safe_font.setPointSizeF(max(pixel_size * 72.0 / effective_dpi, 1.0))
    return safe_font


def apply_switch_button_safe_font(switch_button) -> None:
    """为 `SwitchButton` 及其文本标签补齐安全字体。

    Args:
        switch_button: `qfluentwidgets.SwitchButton` 实例。
    """
    if switch_button is None:
        return

    dpi = float(getattr(switch_button, "logicalDpiY", lambda: DEFAULT_DPI)())
    safe_font = build_font_with_point_size(switch_button.font(), dpi=dpi)
    if safe_font.pointSizeF() <= 0:
        return

    switch_button.setFont(safe_font)
    indicator = getattr(switch_button, "indicator", None)
    if isinstance(indicator, QWidget):
        indicator.setFont(safe_font)
    label = getattr(switch_button, "label", None)
    if isinstance(label, QWidget):
        families = ", ".join(f"'{family}'" for family in safe_font.families())
        font_qss = (
            "SwitchButton>QLabel {"
            f"font: {safe_font.pointSizeF():.2f}pt {families};"
            f"font-weight: {int(safe_font.weight())};"
            "}"
        )
        setCustomStyleSheet(switch_button, font_qss, font_qss)
        label.setFont(safe_font)


def apply_tool_button_safe_font(tool_button) -> None:
    """为 `ToolButton/TransparentToolButton` 补齐安全字体。

    Args:
        tool_button: 目标按钮实例。
    """
    if tool_button is None:
        return

    dpi = float(getattr(tool_button, "logicalDpiY", lambda: DEFAULT_DPI)())
    safe_font = build_font_with_point_size(tool_button.font(), dpi=dpi)
    if safe_font.pointSizeF() <= 0:
        return

    tool_button.setFont(safe_font)
