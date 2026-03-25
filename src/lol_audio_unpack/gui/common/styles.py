"""GUI 组件统一样式构建工具。

将散落在各视图文件中重复的 QSS 构建逻辑集中管理，
调用方只需传入差异参数即可获得亮暗双主题样式对。
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from PySide6.QtGui import QColor
from qfluentwidgets import Theme, isDarkTheme
from qfluentwidgets.common.color import FluentSystemColor

RgbaTuple: TypeAlias = tuple[int, int, int, int]

_FLUENT_FRAME_STROKE_PAIR = ("rgba(0, 0, 0, 15)", "rgba(255, 255, 255, 21)")
_FLUENT_TEXT_PRIMARY_PAIR = ("#242424", "#F5F5F5")
_FLUENT_NEUTRAL_SURFACE_PAIRS: dict[str, tuple[RgbaTuple, RgbaTuple]] = {
    "subtle_idle": ((0, 0, 0, 8), (255, 255, 255, 12)),
    "subtle_hover": ((0, 0, 0, 10), (255, 255, 255, 14)),
    "subtle_selected": ((0, 0, 0, 18), (255, 255, 255, 22)),
    "emphasis_hover": ((0, 0, 0, 15), (255, 255, 255, 20)),
    "emphasis_selected": ((0, 0, 0, 26), (255, 255, 255, 36)),
}
_FLUENT_STATUS_TEXT_PAIR = ("#FFFFFF", "#111111")


def get_fluent_frame_stroke_pair() -> tuple[str, str]:
    """返回项目内复用的 Fluent 微弱描边色对。

    Returns:
        ``(light, dark)`` 亮暗主题边框色。
    """
    return _FLUENT_FRAME_STROKE_PAIR


def get_fluent_text_primary_pair() -> tuple[str, str]:
    """返回项目内复用的 Fluent 主文本色对。

    Returns:
        ``(light, dark)`` 亮暗主题文本色。
    """
    return _FLUENT_TEXT_PRIMARY_PAIR


def get_fluent_neutral_surface_pair(
    kind: Literal["subtle_idle", "subtle_hover", "subtle_selected", "emphasis_hover", "emphasis_selected"],
) -> tuple[RgbaTuple, RgbaTuple]:
    """返回指定语义下的中性 surface 亮暗色对。

    Args:
        kind: 语义化 surface 类型。

    Returns:
        ``(light_rgba, dark_rgba)`` 形式的 RGBA 元组对。
    """
    return _FLUENT_NEUTRAL_SURFACE_PAIRS[kind]


def resolve_fluent_neutral_surface(
    kind: Literal["subtle_idle", "subtle_hover", "subtle_selected", "emphasis_hover", "emphasis_selected"],
) -> QColor:
    """按当前主题解析指定语义的中性 surface 颜色。

    Args:
        kind: 语义化 surface 类型。

    Returns:
        当前亮暗主题下应使用的 ``QColor``。
    """
    light_rgba, dark_rgba = get_fluent_neutral_surface_pair(kind)
    return QColor(*(dark_rgba if isDarkTheme() else light_rgba))


def resolve_fluent_text_primary_color() -> QColor:
    """按当前主题解析主文本色。

    Returns:
        当前亮暗主题下应使用的主文本 ``QColor``。
    """
    light_text, dark_text = get_fluent_text_primary_pair()
    return QColor(dark_text if isDarkTheme() else light_text)


def get_fluent_status_badge_color_pair(status: str) -> tuple[tuple[str, str], tuple[str, str]]:
    """返回状态徽章的背景色对与文字色对。

    Args:
        status: 当前状态文案。

    Returns:
        ``((background_light, background_dark), (foreground_light, foreground_dark))``。
    """
    if status == "已存在":
        background_pair = (
            FluentSystemColor.SUCCESS_FOREGROUND.color(Theme.LIGHT).name(),
            FluentSystemColor.SUCCESS_FOREGROUND.color(Theme.DARK).name(),
        )
    else:
        background_pair = (
            FluentSystemColor.CAUTION_FOREGROUND.color(Theme.LIGHT).name(),
            FluentSystemColor.CAUTION_FOREGROUND.color(Theme.DARK).name(),
        )
    return background_pair, _FLUENT_STATUS_TEXT_PAIR


def resolve_fluent_status_badge_colors(status: str) -> tuple[QColor, QColor]:
    """按当前主题解析状态徽章底色和文字色。

    Args:
        status: 当前状态文案。

    Returns:
        ``(background, foreground)`` 颜色对。
    """
    background_pair, foreground_pair = get_fluent_status_badge_color_pair(status)
    background = background_pair[1] if isDarkTheme() else background_pair[0]
    foreground = foreground_pair[1] if isDarkTheme() else foreground_pair[0]
    return QColor(background), QColor(foreground)


def build_item_view_qss(  # noqa: PLR0913
    *,
    view_type: str = "QTreeView",
    background: str = "transparent",
    color: str = "#202020",
    border: str = "none",
    border_radius: str = "0",
    padding: str = "6px",
    item_min_height: int = 32,
    item_border_radius: int = 0,
    extra_item_rules: str = "",
    extra_rules: str = "",
    include_branch_reset: bool = False,
    include_header_reset: bool = False,
) -> str:
    """构造 QTreeView / QListView 等 item view 的完整 QSS 文本。

    Args:
        view_type: 目标控件类型选择器，如 ``"QTreeView"`` 或 ``"QListView"``。
        background: 控件整体背景色。
        color: 文本前景色。
        border: 边框声明。
        border_radius: 圆角半径。
        padding: 内边距。
        item_min_height: item 最小行高。
        item_border_radius: item 圆角半径。
        extra_item_rules: 追加到 ``::item`` 块内的额外 CSS 属性。
        extra_rules: 追加到整段 QSS 末尾的额外规则块。
        include_branch_reset: 是否包含 ``::branch`` 透明重置规则（TreeView 专用）。
        include_header_reset: 是否包含 ``QHeaderView::section`` 透明重置规则。

    Returns:
        完整的 QSS 字符串。
    """
    parts: list[str] = []

    parts.append(f"""
    {view_type} {{
        background-color: {background};
        color: {color};
        border: {border};
        border-radius: {border_radius};
        outline: none;
        padding: {padding};
        selection-background-color: transparent;
    }}
    {view_type}::item {{
        min-height: {item_min_height}px;
        padding: 0;
        margin: 0;
        border-radius: {item_border_radius}px;{extra_item_rules}
    }}
    {view_type}::item:hover {{
        background-color: transparent;
    }}
    {view_type}::item:selected {{
        background-color: transparent;
    }}""")

    if include_branch_reset:
        parts.append(f"""
    {view_type}::branch {{
        background: transparent;
    }}
    {view_type}::branch:hover {{
        background-color: transparent;
    }}
    {view_type}::branch:selected {{
        background-color: transparent;
    }}""")

    if include_header_reset:
        parts.append("""
    QHeaderView::section {
        background: transparent;
        border: none;
    }""")

    if extra_rules:
        parts.append(extra_rules)

    return "\n".join(parts)


def build_item_view_theme_pair(  # noqa: PLR0913
    *,
    view_type: str = "QTreeView",
    light_color: str = "#202020",
    dark_color: str = "#F5F5F5",
    light_background: str = "transparent",
    dark_background: str = "transparent",
    light_border: str = "none",
    dark_border: str = "none",
    border_radius: str = "0",
    padding: str = "6px",
    item_min_height: int = 32,
    item_border_radius: int = 0,
    extra_item_rules: str = "",
    extra_rules: str = "",
    include_branch_reset: bool = False,
    include_header_reset: bool = False,
) -> tuple[str, str]:
    """构造 item view 的亮暗主题 QSS 样式对。

    只需传入两套主题间的差异参数（通常只是颜色），
    共同的结构由 :func:`build_item_view_qss` 统一生成。

    Returns:
        ``(light_qss, dark_qss)`` 元组。
    """
    common_kwargs = dict(
        view_type=view_type,
        border_radius=border_radius,
        padding=padding,
        item_min_height=item_min_height,
        item_border_radius=item_border_radius,
        extra_item_rules=extra_item_rules,
        extra_rules=extra_rules,
        include_branch_reset=include_branch_reset,
        include_header_reset=include_header_reset,
    )
    light_qss = build_item_view_qss(
        background=light_background,
        color=light_color,
        border=light_border,
        **common_kwargs,
    )
    dark_qss = build_item_view_qss(
        background=dark_background,
        color=dark_color,
        border=dark_border,
        **common_kwargs,
    )
    return light_qss, dark_qss


def build_fluent_list_shell_theme_pair(  # noqa: PLR0913
    *,
    light_background: str = "transparent",
    dark_background: str = "transparent",
    light_border: str = "none",
    dark_border: str = "none",
    border_radius: str = "0",
    padding: str = "0 4px",
    item_min_height: int = 35,
    item_border_radius: int = 0,
    extra_item_rules: str = "",
    extra_rules: str = "",
) -> tuple[str, str]:
    """构造参考 QFluentWidgets ListView 默认基线的列表壳层样式。

    Args:
        light_background: 亮色主题外层背景。
        dark_background: 暗色主题外层背景。
        light_border: 亮色主题外层边框。
        dark_border: 暗色主题外层边框。
        border_radius: 外层圆角半径。
        padding: 外层内边距。
        item_min_height: item 最小高度。
        item_border_radius: item 圆角半径。
        extra_item_rules: 追加到 ``QListView::item`` 的额外规则。
        extra_rules: 追加到 QSS 尾部的额外规则。

    Returns:
        ``(light_qss, dark_qss)`` 亮暗主题样式对。
    """
    light_text, dark_text = get_fluent_text_primary_pair()
    list_item_rules = """
        background-color: transparent;
        border: 0px;
        padding-left: 11px;
        padding-right: 11px;
    """
    if extra_item_rules:
        list_item_rules += extra_item_rules

    return build_item_view_theme_pair(
        view_type="QListView",
        light_color=light_text,
        dark_color=dark_text,
        light_background=light_background,
        dark_background=dark_background,
        light_border=light_border,
        dark_border=dark_border,
        border_radius=border_radius,
        padding=padding,
        item_min_height=item_min_height,
        item_border_radius=item_border_radius,
        extra_item_rules=list_item_rules,
        extra_rules=extra_rules,
    )


def build_fluent_tree_shell_theme_pair(  # noqa: PLR0913
    *,
    light_background: str = "transparent",
    dark_background: str = "transparent",
    is_border_visible: bool = True,
    border_radius: str = "5px",
    padding: str = "0 5px 0 0",
    item_min_height: int = 32,
    item_border_radius: int = 5,
    extra_item_rules: str = "",
    extra_rules: str = "",
    include_branch_reset: bool = False,
    include_header_reset: bool = False,
) -> tuple[str, str]:
    """构造参考 QFluentWidgets TreeView 默认基线的树壳层样式。

    Args:
        light_background: 亮色主题外层背景。
        dark_background: 暗色主题外层背景。
        is_border_visible: 是否使用 QFluentWidgets TreeView 的默认细描边。
        border_radius: 外层圆角半径。
        padding: 外层内边距。
        item_min_height: item 最小高度。
        item_border_radius: item 圆角半径。
        extra_item_rules: 追加到 ``QTreeView::item`` 的额外规则。
        extra_rules: 追加到 QSS 尾部的额外规则。
        include_branch_reset: 是否追加 branch 透明重置。
        include_header_reset: 是否追加 header 透明重置。

    Returns:
        ``(light_qss, dark_qss)`` 亮暗主题样式对。
    """
    light_text, dark_text = get_fluent_text_primary_pair()
    light_stroke, dark_stroke = get_fluent_frame_stroke_pair()
    tree_item_rules = """
        padding: 4px;
        margin-top: 2px;
        margin-bottom: 2px;
        padding-left: 20px;
        background-color: transparent;
        border: none;
    """
    if extra_item_rules:
        tree_item_rules += extra_item_rules

    return build_item_view_theme_pair(
        view_type="QTreeView",
        light_color=light_text,
        dark_color=dark_text,
        light_background=light_background,
        dark_background=dark_background,
        light_border=f"1px solid {light_stroke}" if is_border_visible else "none",
        dark_border=f"1px solid {dark_stroke}" if is_border_visible else "none",
        border_radius=border_radius,
        padding=padding,
        item_min_height=item_min_height,
        item_border_radius=item_border_radius,
        extra_item_rules=tree_item_rules,
        extra_rules=extra_rules,
        include_branch_reset=include_branch_reset,
        include_header_reset=include_header_reset,
    )
