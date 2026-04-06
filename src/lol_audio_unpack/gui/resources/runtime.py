"""提供 GUI 静态资源根目录解析与文件定位能力。"""

import sys
from pathlib import Path


def iter_asset_roots() -> tuple[Path, ...]:
    """返回所有可能的 GUI 资源根目录。

    Returns:
        tuple[Path, ...]: 按优先级去重后的资源根目录列表。
    """

    package_assets = Path(__file__).resolve().parent.parent / "assets"
    roots: list[Path] = []

    # 兼容 PyInstaller 解包目录与旁路可执行目录。
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

        roots.append(Path(sys.executable).resolve().parent / "assets")

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


def resolve_first(rel_paths: tuple[str, ...]) -> Path | None:
    """返回第一个存在的候选资源文件。

    Args:
        rel_paths: 相对资源路径候选列表。

    Returns:
        Path | None: 找到资源时返回路径，否则返回 ``None``。
    """

    for root in iter_asset_roots():
        for rel_path in rel_paths:
            candidate = root / rel_path
            if candidate.is_file():
                return candidate
    return None


def resolve_required(rel_path: str) -> Path:
    """返回必须存在的资源路径。

    Args:
        rel_path: 相对资源路径。

    Returns:
        Path: 定位到的资源路径。

    Raises:
        FileNotFoundError: 当资源文件不存在时抛出。
    """

    path = resolve_first((rel_path,))
    if path is None:
        raise FileNotFoundError(rel_path)
    return path
