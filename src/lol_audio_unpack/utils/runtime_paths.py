"""统一源码态与冻结态的默认运行时路径语义。"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lol_audio_unpack.utils.type_hints import StrPath

__all__ = [
    "apply_frozen_working_directory",
    "RuntimePaths",
    "detect_runtime_paths",
    "get_default_output_root",
    "get_default_output_relative_path",
    "get_default_wwiser_path",
    "get_default_wwiser_relative_path",
    "get_default_vgmstream_path",
    "get_default_vgmstream_relative_path",
]


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """描述当前进程的默认运行时路径。

    Attributes:
        is_frozen: 当前是否为冻结态运行，例如 PyInstaller 产物。
        executable_path: 当前解释器或可执行文件路径。
        launch_root: 本次运行应采用的默认根目录。
        config_root: 默认配置目录。
        bundle_root: 默认 bundle 目录，用于随程序分发的资源或工具。
    """

    is_frozen: bool
    executable_path: Path
    launch_root: Path
    config_root: Path
    bundle_root: Path


def _normalize_path(path: StrPath) -> Path:
    """将路径标准化为绝对 ``Path``。"""

    return Path(path).expanduser().resolve(strict=False)


def detect_runtime_paths(
    *,
    is_frozen: bool | None = None,
    cwd: StrPath | None = None,
    executable: StrPath | None = None,
) -> RuntimePaths:
    """推导当前进程的默认运行时路径。

    Args:
        is_frozen: 是否强制指定冻结态；传 ``None`` 时按运行时自动探测。
        cwd: 用于源码态的当前工作目录；传 ``None`` 时读取真实 ``Path.cwd()``。
        executable: 当前解释器或可执行文件路径；传 ``None`` 时读取 ``sys.executable``。

    Returns:
        RuntimePaths: 已解析好的默认运行时路径快照。
    """

    current_cwd = _normalize_path(cwd or Path.cwd())
    executable_path = _normalize_path(executable or sys.executable)
    frozen = getattr(sys, "frozen", False) if is_frozen is None else is_frozen

    launch_root = executable_path.parent if frozen else current_cwd

    return RuntimePaths(
        is_frozen=frozen,
        executable_path=executable_path,
        launch_root=launch_root,
        config_root=launch_root,
        bundle_root=launch_root,
    )


def apply_frozen_working_directory(
    *,
    runtime_paths: RuntimePaths | None = None,
    chdir: Callable[[StrPath], None] = os.chdir,
) -> Path | None:
    """在冻结态下将当前工作目录切换到 ``launch_root``。

    Args:
        runtime_paths: 可选的运行时路径快照；未提供时自动探测当前进程。
        chdir: 可注入的 ``chdir`` 实现，便于测试。

    Returns:
        Path | None: 实际切换到的目录；源码态返回 ``None``。
    """

    current_paths = runtime_paths or detect_runtime_paths()
    if not current_paths.is_frozen:
        return None

    chdir(current_paths.launch_root)
    return current_paths.launch_root


def get_default_output_root(runtime_paths: RuntimePaths) -> Path:
    """返回未显式指定输出目录时的默认输出根目录。

    Args:
        runtime_paths: 运行时路径快照。

    Returns:
        Path: 默认输出根目录，固定为 ``launch_root / "output"``。
    """

    return runtime_paths.launch_root / Path(get_default_output_relative_path())


def get_default_output_relative_path() -> str:
    """返回默认输出目录相对于根目录的路径。"""

    return "output"


def get_default_wwiser_relative_path() -> str:
    """返回默认 wwiser 工具相对于根目录的路径。"""

    return "tools/wwiser/wwiser.pyz"


def get_default_wwiser_path(runtime_paths: RuntimePaths) -> Path:
    """返回默认的 wwiser 工具路径。"""

    return runtime_paths.launch_root / Path(get_default_wwiser_relative_path())


def get_default_vgmstream_relative_path(*, platform: str | None = None) -> str:
    """返回默认 vgmstream 工具相对于根目录的路径。"""

    normalized_platform = (platform or sys.platform).lower()
    filename = "vgmstream-cli.exe" if normalized_platform.startswith("win") else "vgmstream-cli"
    return f"tools/vgmstream/{filename}"


def get_default_vgmstream_path(
    runtime_paths: RuntimePaths,
    *,
    platform: str | None = None,
) -> Path:
    """返回默认的 vgmstream-cli 工具路径。

    Args:
        runtime_paths: 运行时路径快照。
        platform: 可选目标平台；未提供时使用当前解释器平台。

    Returns:
        Path: 默认的 vgmstream-cli 可执行文件路径。
    """

    return runtime_paths.launch_root / Path(get_default_vgmstream_relative_path(platform=platform))
