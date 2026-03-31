"""测试 pytest 运行时目录与路径字面量约束。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lol_audio_unpack.gui.common.gui_config import GuiConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_TEMP_ROOT = (REPO_ROOT / ".temp" / "pytest").resolve()
PYTEST_CACHE_ROOT = (REPO_ROOT / ".temp" / ".pytest_cache").resolve()
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"[A-Za-z]:[\\/]")
POSIX_NONPORTABLE_PATH_RE = re.compile(r"/tmp/|/mnt/[A-Za-z]/")
FORBIDDEN_ROOT_TEMP_LITERALS = (
    '.cache/',
    '.cache\\',
    'Path(".cache")',
    "Path('.cache')",
    'benchmarks/remote_live/',
    'benchmarks\\remote_live\\',
    'Path("benchmarks/remote_live',
    "Path('benchmarks/remote_live",
)


def _iter_test_sources() -> list[Path]:
    """返回需要扫描的测试源码文件列表。"""
    current_file = Path(__file__).resolve()
    return sorted(
        path
        for path in (REPO_ROOT / "tests").rglob("*.py")
        if "__pycache__" not in path.parts and path.resolve() != current_file
    )


def test_tmp_path_stays_inside_repo_temp(tmp_path: Path) -> None:
    """pytest ``tmp_path`` 应固定在仓库内 ``.temp/pytest`` 下。"""
    assert tmp_path.resolve().is_relative_to(PYTEST_TEMP_ROOT)


def test_pytest_cache_stays_inside_repo_temp(pytestconfig: pytest.Config) -> None:
    """pytest cache 应固定在仓库内 ``.temp/.pytest_cache`` 下。"""
    cache_probe = pytestconfig.cache.mkdir("runtime_policy")
    assert cache_probe.resolve().is_relative_to(PYTEST_CACHE_ROOT)


def test_gui_config_default_env_file_stays_inside_repo_temp() -> None:
    """测试环境中的 GuiConfig 不应指向项目根目录下的真实 .lol.env。"""
    cfg = GuiConfig()
    assert cfg._env_file.resolve().is_relative_to(PYTEST_TEMP_ROOT)


def test_gui_config_uses_fake_qsettings_backend_in_tests() -> None:
    """测试环境中的 GuiConfig 不应直接使用系统真实 QSettings。"""
    cfg = GuiConfig()
    assert type(cfg._qs).__name__ == "FakeQSettings"


def test_tests_do_not_embed_nonportable_absolute_path_literals() -> None:
    """测试源码中不应再写入非便携的绝对路径字面量。"""
    offenders: list[str] = []
    for path in _iter_test_sources():
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "://" in line:
                continue
            if WINDOWS_ABSOLUTE_PATH_RE.search(line) or POSIX_NONPORTABLE_PATH_RE.search(line):
                offenders.append(f"{relative_path}:{line_number}:{line.strip()}")

    assert not offenders, "请改用 tmp_path、动态路径拼装或相对路径样本:\n" + "\n".join(offenders)


def test_tests_do_not_write_runtime_artifacts_to_repo_root() -> None:
    """测试源码中不应再把运行时产物路径直接写到仓库根目录。"""
    offenders: list[str] = []
    for path in _iter_test_sources():
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(literal in line for literal in FORBIDDEN_ROOT_TEMP_LITERALS):
                offenders.append(f"{relative_path}:{line_number}:{line.strip()}")

    assert not offenders, "请把测试运行时产物统一迁到 .temp/ 下:\n" + "\n".join(offenders)
