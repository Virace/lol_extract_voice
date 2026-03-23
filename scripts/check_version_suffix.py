#!/usr/bin/env python3
"""按分支校验或同步版本号后缀，避免切分支后忘记更新版本。"""

from __future__ import annotations

import argparse
import json
import re
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
DEFAULT_INIT_FILE = Path("src/lol_audio_unpack/__init__.py")
DEFAULT_UV_LOCK_FILE = Path("uv.lock")
PACKAGE_NAME = "lol-audio-unpack"
PYPROJECT_VERSION_PATTERN = re.compile(r'(^version = ")([^"]+)(")', re.MULTILINE)
INIT_VERSION_PATTERN = re.compile(r'(^__version__ = ")([^"]+)(")', re.MULTILINE)
UV_LOCK_VERSION_PATTERN = re.compile(
    rf'(\[\[package\]\]\r?\nname = "{re.escape(PACKAGE_NAME)}"\r?\nversion = ")([^"]+)(")'
)


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


def normalize_version_suffix(version: str, required_suffix: str) -> str:
    """基于分支规则生成目标版本号。"""
    base_version = version.split("+", 1)[0]
    suffix = required_suffix.strip().lower()
    if not suffix:
        return base_version
    return f"{base_version}+{suffix}"


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as f:
        return f.read()


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(content)


def _replace_single(pattern: re.Pattern[str], content: str, new_version: str, file_label: str) -> tuple[str, bool]:
    replaced, count = pattern.subn(rf"\g<1>{new_version}\g<3>", content, count=1)
    if count != 1:
        raise ValueError(f"无法在 {file_label} 中唯一定位版本字段")
    return replaced, replaced != content


def sync_version_files(
    *,
    repo_root: Path,
    pyproject_path: Path,
    init_file: Path,
    uv_lock_file: Path,
    target_version: str,
) -> list[Path]:
    """把版本号同步到项目内的关键文件。"""
    changed_files: list[Path] = []

    pyproject_text = _read_text(pyproject_path)
    updated_pyproject, pyproject_changed = _replace_single(
        PYPROJECT_VERSION_PATTERN, pyproject_text, target_version, str(pyproject_path)
    )
    if pyproject_changed:
        _write_text(pyproject_path, updated_pyproject)
        changed_files.append(pyproject_path)

    init_path = init_file if init_file.is_absolute() else repo_root / init_file
    init_text = _read_text(init_path)
    updated_init, init_changed = _replace_single(INIT_VERSION_PATTERN, init_text, target_version, str(init_path))
    if init_changed:
        _write_text(init_path, updated_init)
        changed_files.append(init_path)

    lock_path = uv_lock_file if uv_lock_file.is_absolute() else repo_root / uv_lock_file
    if lock_path.exists():
        uv_lock_text = _read_text(lock_path)
        updated_lock, lock_changed = _replace_single(UV_LOCK_VERSION_PATTERN, uv_lock_text, target_version, str(lock_path))
        if lock_changed:
            _write_text(lock_path, updated_lock)
            changed_files.append(lock_path)

    return changed_files


def stage_files(repo_root: Path, files: list[Path]) -> None:
    """把自动同步过的文件重新加入 index。"""
    if not files:
        return
    rel_paths = [str(path.relative_to(repo_root)) for path in files]
    subprocess.run(["git", "add", "--", *rel_paths], cwd=repo_root, check=True)


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
    parser.add_argument("--init-file", type=Path, default=DEFAULT_INIT_FILE, help="包内 __version__ 文件路径")
    parser.add_argument("--uv-lock", type=Path, default=DEFAULT_UV_LOCK_FILE, help="uv.lock 文件路径")
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path(".version-suffix-rules.json"),
        help="分支后缀规则文件路径（JSON）",
    )
    parser.add_argument("--sync", action="store_true", help="按当前分支规则自动同步版本号到相关文件")
    parser.add_argument("--stage", action="store_true", help="同步后自动重新 git add 受影响文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    pyproject_path = args.pyproject if args.pyproject.is_absolute() else repo_root / args.pyproject

    try:
        branch = args.branch or detect_branch(repo_root)
        rules = load_rules(repo_root, args.rules)
        version = args.version or load_version(pyproject_path)

        if args.sync:
            if branch in rules:
                target_version = normalize_version_suffix(version, rules[branch])
                changed_files = sync_version_files(
                    repo_root=repo_root,
                    pyproject_path=pyproject_path,
                    init_file=args.init_file,
                    uv_lock_file=args.uv_lock,
                    target_version=target_version,
                )
                if changed_files:
                    changed_labels = ", ".join(str(path.relative_to(repo_root)) for path in changed_files)
                    print(f"[sync] 分支 {branch} 自动同步版本 {version} -> {target_version}: {changed_labels}")
                    if args.stage:
                        stage_files(repo_root, changed_files)
                else:
                    print(f"[sync] 分支 {branch} 版本已匹配，无需修改: {target_version}")
                version = target_version
            else:
                print(f"[sync] 当前分支 {branch} 不在规则中，跳过自动同步。")

        ok, msg = check_suffix(branch=branch, version=version, rules=rules)
        print(msg)
        return 0 if ok else 1
    except Exception as e:
        print(f"[fail] 版本后缀校验异常: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
