"""版本号解析与运行时派生工具。"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

WINDOWS_VERSION_PATTERN = re.compile(rb"(?:[0-9]\x00)+(?:\.\x00(?:[0-9]\x00)+){3}")
PATCH_VERSION_PATTERN = re.compile(r"^(\d+\.\d+)")
RUNTIME_VERSION_PATTERN = re.compile(
    r"^(?:v)?(?P<base>\d+\.\d+\.\d+)(?:\.dev(?P<dev>\d+))?(?:\+(?P<local>[0-9A-Za-z.-]+))?$"
)
GIT_DESCRIBE_PATTERN = re.compile(r"^(?P<tag>.+)-(?P<count>\d+)-g(?P<sha>[0-9a-f]+)(?P<dirty>-dirty)?$")
WINDOWS_VERSION_DOT_COUNT = 3
BUILD_VERSION_ENV = "LOL_AUDIO_UNPACK_BUILD_VERSION"


def is_git_repository(repo_root: Path) -> bool:
    """判断目标目录是否仍携带 Git 仓库元数据。"""

    return (repo_root / ".git").exists()


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


def _parse_runtime_version(version: str) -> tuple[str, int | None, str | None]:
    """解析仓库使用的运行时版本格式。"""
    match = RUNTIME_VERSION_PATTERN.fullmatch(version.strip())
    if match is None:
        raise ValueError(f"无法解析运行时版本号: {version}")

    dev_group = match.group("dev")
    return match.group("base"), int(dev_group) if dev_group is not None else None, match.group("local")


def _bump_patch_version(base_version: str) -> str:
    """把 ``major.minor.patch`` 的 patch 段加一。"""
    major, minor, patch = base_version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def _normalize_tag_version(tag: str) -> str:
    """把 Git tag 规范化为仓库运行时版本格式。"""
    normalized = tag.strip()
    if normalized.startswith(("v", "V")):
        normalized = normalized[1:]
    _parse_runtime_version(normalized)
    return normalized


def _next_cycle_version(tag_version: str) -> str:
    """根据最近 tag 推导当前开发周期的起始版本。"""
    base_version, dev_number, _ = _parse_runtime_version(tag_version)
    if dev_number is None:
        return f"{_bump_patch_version(base_version)}.dev0"
    return f"{base_version}.dev{dev_number}"


def _advance_dev_version(version: str, commit_count: int) -> str:
    """把开发版号按提交数推进。"""
    base_version, dev_number, _ = _parse_runtime_version(version)
    if dev_number is None:
        raise ValueError(f"版本 {version} 不是合法的开发版本号")
    return f"{base_version}.dev{dev_number + commit_count}"


def describe_git_version(repo_root: Path) -> str:
    """读取当前仓库的 `git describe` 结果。

    Args:
        repo_root: 仓库根目录。

    Returns:
        `git describe --tags --long --dirty` 的标准输出。
    """
    if getattr(sys, "frozen", False) or not is_git_repository(repo_root):
        raise RuntimeError(f"当前环境不应执行 git describe: {repo_root}")

    result = subprocess.run(
        [
            "git",
            "describe",
            "--tags",
            "--long",
            "--dirty",
            "--abbrev=7",
            "--match",
            "v[0-9]*",
            "--match",
            "[0-9]*",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def derive_version_from_git_describe(describe_output: str, fallback_version: str) -> str:
    """根据 `git describe` 输出生成运行时版本号。

    Args:
        describe_output: `git describe --tags --long --dirty` 的输出。
        fallback_version: 取不到 Git 信息时使用的静态回退版本。

    Returns:
        适合展示的运行时版本号。
    """
    match = GIT_DESCRIBE_PATTERN.fullmatch(describe_output.strip())
    if match is None:
        return fallback_version

    tag_version = _normalize_tag_version(match.group("tag"))
    commit_count = int(match.group("count"))
    sha = match.group("sha")
    is_dirty = bool(match.group("dirty"))

    if commit_count == 0 and not is_dirty:
        return tag_version

    next_cycle_version = _next_cycle_version(tag_version)
    derived_version = _advance_dev_version(next_cycle_version, commit_count)
    local_suffix = f"g{sha}"
    if is_dirty:
        local_suffix += ".dirty"
    return f"{derived_version}+{local_suffix}"


def resolve_runtime_version(repo_root: Path, fallback_version: str) -> str:
    """优先根据 Git 历史派生运行时版本，失败时回退到静态版本。

    Args:
        repo_root: 仓库根目录。
        fallback_version: 无法访问 Git 信息时使用的静态版本。

    Returns:
        运行时展示使用的版本号。
    """
    injected_version = os.getenv(BUILD_VERSION_ENV)
    if injected_version:
        return injected_version.strip()

    if getattr(sys, "frozen", False):
        return fallback_version

    try:
        return derive_version_from_git_describe(describe_git_version(repo_root), fallback_version)
    except Exception:
        return fallback_version


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
