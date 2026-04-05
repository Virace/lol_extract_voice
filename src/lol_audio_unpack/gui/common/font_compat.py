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


def apply_safe_font(widget) -> QFont | None:
    """为单个控件补齐安全 point size。

    Args:
        widget: 目标控件实例。

    Returns:
        QFont | None: 成功应用时返回兼容字体；若控件为空或无法推导安全字体则返回 `None`。
    """
    if widget is None:
        return None

    dpi = float(getattr(widget, "logicalDpiY", lambda: DEFAULT_DPI)())
    safe_font = build_font_with_point_size(widget.font(), dpi=dpi)
    if safe_font.pointSizeF() <= 0:
        return None

    widget.setFont(safe_font)
    return safe_font


def apply_switch_button_safe_font(switch_button) -> None:
    """为 `SwitchButton` 及其文本标签补齐安全字体。

    Args:
        switch_button: `qfluentwidgets.SwitchButton` 实例。
    """
    safe_font = apply_safe_font(switch_button)
    if safe_font is None:
        return

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
    apply_safe_font(tool_button)


def apply_line_edit_safe_font(line_edit) -> None:
    """为带内置图标按钮的输入框补齐安全字体。

    Args:
        line_edit: 目标输入框实例。
    """
    if line_edit is None:
        return

    for button_name in ("searchButton", "clearButton"):
        apply_tool_button_safe_font(getattr(line_edit, button_name, None))
