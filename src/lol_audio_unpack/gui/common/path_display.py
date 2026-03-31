"""GUI 路径显示格式化工具。"""

from __future__ import annotations

import sys


def _is_windows_platform(platform: str | None = None) -> bool:
    """判断目标显示平台是否为 Windows。

    Args:
        platform: 可选平台标识；未提供时使用当前解释器平台。

    Returns:
        当目标平台为 Windows 时返回 ``True``。
    """
    normalized = (platform or sys.platform).lower()
    return normalized.startswith("win")


def format_path_for_display(path: str, *, platform: str | None = None) -> str:
    """按目标平台统一路径分隔符显示风格。

    Args:
        path: 原始路径字符串。
        platform: 可选平台标识；未提供时使用当前解释器平台。

    Returns:
        已按目标平台规范化分隔符的路径文本。
    """
    if not path:
        return ""

    normalized = str(path).replace("\\", "/")
    if _is_windows_platform(platform):
        return normalized.replace("/", "\\")
    return normalized


def format_default_relative_path(
    path: str,
    *,
    platform: str | None = None,
    root_label: str = "根目录",
) -> str:
    """把默认相对路径格式化为面向用户的根目录提示。

    Args:
        path: 原始路径字符串。
        platform: 可选平台标识；未提供时使用当前解释器平台。
        root_label: 根目录显示文案。

    Returns:
        若路径以当前目录相对形式表示，则返回带根目录文案的显示文本；
        否则返回按平台规范化后的路径文本。
    """
    normalized = format_path_for_display(path, platform=platform)
    separator = "\\" if _is_windows_platform(platform) else "/"

    if normalized in {".", f".{separator}"}:
        return root_label

    prefix = f".{separator}"
    if normalized.startswith(prefix):
        remainder = normalized[len(prefix):].lstrip(separator)
        if not remainder:
            return root_label
        return f"{root_label}{separator}{remainder}"

    return normalized
