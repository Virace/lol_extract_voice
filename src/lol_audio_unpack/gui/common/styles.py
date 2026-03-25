"""GUI 组件统一样式构建工具。

将散落在各视图文件中重复的 QSS 构建逻辑集中管理，
调用方只需传入差异参数即可获得亮暗双主题样式对。
"""

from __future__ import annotations


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
