#!/usr/bin/env python3
"""检查 main/master 分支是否仍引用本地路径依赖。"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

MAIN_BRANCHES = {"main", "master"}


def detect_branch(repo_root: Path) -> str:
    """读取当前分支名。"""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def load_pyproject(pyproject_path: Path) -> dict[str, Any]:
    """加载 pyproject.toml。"""
    if not pyproject_path.exists():
        raise FileNotFoundError(f"未找到配置文件: {pyproject_path}")
    with pyproject_path.open("rb") as f:
        return tomllib.load(f)


def find_local_sources(pyproject_data: dict[str, Any]) -> list[str]:
    """提取 tool.uv.sources 中的本地路径依赖。"""
    tool_data = pyproject_data.get("tool", {})
    uv_data = tool_data.get("uv", {})
    sources = uv_data.get("sources", {})
    if not isinstance(sources, dict):
        return []

    local_entries: list[str] = []
    for pkg_name, source in sources.items():
        if isinstance(source, dict) and "path" in source:
            source_path = source.get("path")
            editable = bool(source.get("editable"))
            local_entries.append(
                f"{pkg_name}: path={source_path}, editable={str(editable).lower()}"
            )
    return local_entries


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="检查 main 分支是否存在本地路径依赖")
    parser.add_argument(
        "--mode",
        choices=["warn", "enforce"],
        default="enforce",
        help="warn: 仅提示；enforce: 检测到问题时返回非0",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="仓库根目录",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="pyproject.toml 路径",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=None,
        help="手动指定分支名（默认自动检测）",
    )
    return parser.parse_args()


def main() -> int:
    """程序入口。"""
    args = parse_args()
    repo_root = args.repo_root.resolve()
    pyproject_path = args.pyproject if args.pyproject.is_absolute() else repo_root / args.pyproject

    try:
        branch = args.branch or detect_branch(repo_root)
        if branch not in MAIN_BRANCHES:
            return 0

        pyproject_data = load_pyproject(pyproject_path)
        local_entries = find_local_sources(pyproject_data)
        if not local_entries:
            print(f"[ok] 分支 {branch} 未发现本地路径依赖。")
            return 0

        print(f"[warn] 分支 {branch} 检测到本地路径依赖，禁止合并/提交到 {branch}：")
        for entry in local_entries:
            print(f"  - {entry}")
        print("[hint] 请开发者先移除本地依赖（例如 tool.uv.sources 的 path 源），再合并到 main/master。")
        return 1 if args.mode == "enforce" else 0
    except Exception as e:
        print(f"[fail] 本地依赖检查异常: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
