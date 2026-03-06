"""版本字符串与 Windows 客户端版本资源解析工具。"""

from __future__ import annotations

import re

WINDOWS_VERSION_PATTERN = re.compile(rb"(?:[0-9]\x00)+(?:\.\x00(?:[0-9]\x00)+){3}")
PATCH_VERSION_PATTERN = re.compile(r"^(\d+\.\d+)")
WINDOWS_VERSION_DOT_COUNT = 3


def normalize_patch_version(version: str) -> str:
    """把版本字符串标准化为 ``major.minor``。

    Args:
        version: 原始版本字符串，例如 ``16.5.751.1533`` 或 ``16.5``。

    Returns:
        标准化后的补丁版本号，例如 ``16.5``。

    Raises:
        ValueError: 当输入无法解析出 ``major.minor`` 时抛出。
    """
    match = PATCH_VERSION_PATTERN.match(str(version).strip())
    if match is None:
        raise ValueError(f"无法解析补丁版本号: {version}")
    return match.group(1)


def extract_windows_file_version(payload: bytes) -> str:
    """从 Windows PE 文件字节中提取版本字符串。

    Args:
        payload: PE 文件完整字节内容。

    Returns:
        提取到的四段式版本号，例如 ``16.5.751.1533``。

    Raises:
        ValueError: 当无法从版本资源中提取 `ProductVersion` 或 `FileVersion` 时抛出。
    """
    for label in ("ProductVersion", "FileVersion"):
        marker = label.encode("utf-16le")
        index = payload.find(marker)
        if index < 0:
            continue

        window = payload[index : index + 512]
        matches = WINDOWS_VERSION_PATTERN.findall(window)
        for match in matches:
            version = match.decode("utf-16le", errors="ignore")
            if version.count(".") == WINDOWS_VERSION_DOT_COUNT:
                return version

    raise ValueError("无法从可执行文件中提取 FileVersion/ProductVersion")
