#!/usr/bin/env python3
"""按分支校验版本号后缀，避免切分支后忘记更新版本。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

DEFAULT_RULES: dict[str, str] = {
    "v3-test": "test",
    "test": "test",
    "v3-lite": "lite",
    "lite": "lite",
    "v3-hash": "hash",
    "main": "",
    "master": "",
}


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


def load_rules(repo_root: Path, rules_path: Path) -> dict[str, str]:
    """加载分支后缀规则；文件不存在时使用默认规则。"""
    full_path = rules_path if rules_path.is_absolute() else repo_root / rules_path
    if not full_path.exists():
        return DEFAULT_RULES

    data = json.loads(full_path.read_text(encoding="utf-8"))
    loaded = data.get("branch_suffix_rules", {})
    if not isinstance(loaded, dict):
        raise ValueError(f"规则文件格式错误: {full_path}")
    return {str(k): str(v) for k, v in loaded.items()}


def load_version(pyproject_path: Path) -> str:
    """读取 pyproject.toml 中的 project.version。"""
    if not pyproject_path.exists():
        raise FileNotFoundError(f"未找到版本文件: {pyproject_path}")

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    version = project.get("version")
    if not version:
        raise ValueError(f"无法在 {pyproject_path} 中找到 project.version")
    return str(version)


def check_suffix(branch: str, version: str, rules: dict[str, str]) -> tuple[bool, str]:
    """根据分支规则校验版本号。"""
    if branch not in rules:
        return True, f"[skip] 当前分支 {branch} 不在规则中，跳过后缀校验。"

    required = rules[branch].strip().lower()
    version_lower = version.lower()

    if required:
        if required in version_lower:
            return True, f"[ok] 分支 {branch} 要求后缀包含 {required}，当前版本 {version}。"
        return False, f"[fail] 分支 {branch} 要求后缀包含 {required}，当前版本 {version}。"

    # 空后缀规则：不允许出现其他规则中的显式后缀
    disallow = sorted({v.strip().lower() for v in rules.values() if v.strip()})
    hit = [token for token in disallow if token in version_lower]
    if hit:
        return False, f"[fail] 分支 {branch} 要求正式版本（无后缀），但版本 {version} 含后缀 {hit}。"
    return True, f"[ok] 分支 {branch} 使用正式版本 {version}。"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按分支校验版本号后缀")
    parser.add_argument("--branch", type=str, default=None, help="手动指定分支名，不指定则自动检测")
    parser.add_argument("--version", type=str, default=None, help="手动指定版本号，不指定则读取 pyproject.toml")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent, help="仓库根目录")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"), help="版本文件路径")
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path(".version-suffix-rules.json"),
        help="分支后缀规则文件路径（JSON）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    pyproject_path = args.pyproject if args.pyproject.is_absolute() else repo_root / args.pyproject

    try:
        branch = args.branch or detect_branch(repo_root)
        version = args.version or load_version(pyproject_path)
        rules = load_rules(repo_root, args.rules)
        ok, msg = check_suffix(branch=branch, version=version, rules=rules)
        print(msg)
        return 0 if ok else 1
    except Exception as e:
        print(f"[fail] 版本后缀校验异常: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
