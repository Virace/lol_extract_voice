"""GUI 应用图标加载辅助。"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger
from PySide6.QtGui import QIcon

if sys.platform.startswith("win"):
    _APP_ICON_CANDIDATES: tuple[str, ...] = (
        "app_icon.ico",
        "app_icon.png",
        "app_icon.svg",
    )
else:
    _APP_ICON_CANDIDATES = (
        "app_icon.png",
        "app_icon.ico",
        "app_icon.svg",
    )

_APP_LOGO_CANDIDATES: tuple[str, ...] = (
    "app_icon.svg",
    "app_icon.png",
    "app_icon.ico",
)


def _iter_asset_roots() -> tuple[Path, ...]:
    """返回可能包含 GUI 资源文件的目录列表。

    Returns:
        tuple[Path, ...]: 按优先级排序的资源目录候选列表。
    """
    package_assets = Path(__file__).resolve().parent.parent / "assets"
    roots: list[Path] = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            frozen_root = Path(meipass)
            roots.extend(
                [
                    frozen_root / "lol_audio_unpack" / "gui" / "assets",
                    frozen_root / "gui" / "assets",
                    frozen_root / "assets",
                ]
            )
        executable_dir = Path(sys.executable).resolve().parent
        roots.append(executable_dir / "assets")

    roots.append(package_assets)

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        normalized = root.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_roots.append(normalized)

    return tuple(unique_roots)


def get_app_icon_path() -> Path | None:
    """返回首个可用的应用图标路径。

    Returns:
        Path | None: 找到图标时返回其路径，否则返回 ``None``。
    """
    for root in _iter_asset_roots():
        for filename in _APP_ICON_CANDIDATES:
            candidate = root / filename
            if candidate.is_file():
                return candidate
    return None


def get_app_logo_path() -> Path | None:
    """返回适合展示在界面中的品牌 logo 路径。

    Returns:
        Path | None: 优先返回 SVG 资源，找不到时返回其他可用资源。
    """
    for root in _iter_asset_roots():
        for filename in _APP_LOGO_CANDIDATES:
            candidate = root / filename
            if candidate.is_file():
                return candidate
    return None


def load_app_icon() -> QIcon:
    """加载 GUI 主窗口与启动页共用的应用图标。

    Returns:
        QIcon: 找到图标时返回可用对象；若资源缺失则返回空图标。
    """
    icon_path = get_app_icon_path()
    if icon_path is None:
        logger.warning("未找到 GUI 应用图标资源，将继续使用空图标")
        return QIcon()

    icon = QIcon(str(icon_path))
    if icon.isNull():
        logger.warning("GUI 应用图标加载失败: {}", icon_path)
    return icon
