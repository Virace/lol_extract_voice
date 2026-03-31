"""PyInstaller 正式构建入口测试。"""
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYINSTALLER_DIR = PROJECT_ROOT / "scripts" / "pyinstaller"


def test_pyinstaller_entry_files_exist() -> None:
    """正式打包入口应落在 ``scripts/pyinstaller`` 下。"""
    assert (PYINSTALLER_DIR / "build_gui.py").is_file()
    assert (PYINSTALLER_DIR / "build_gui.ps1").is_file()
    assert (PYINSTALLER_DIR / "gui.spec").is_file()
    assert (PYINSTALLER_DIR / "runtime_hook_chdir.py").is_file()


def test_pyinstaller_spec_supports_default_onefile_and_optional_onedir() -> None:
    """spec 文件应默认 onefile，并允许切换到 onedir。"""
    spec_text = (PYINSTALLER_DIR / "gui.spec").read_text(encoding="utf-8")

    assert 'parser.add_argument("--mode"' in spec_text
    assert 'parser.add_argument("--runtime-version"' in spec_text
    assert 'parser.add_argument("--version-file"' in spec_text
    assert 'default="onefile"' in spec_text
    assert 'if options.mode == "onefile"' in spec_text
    assert 'elif options.mode == "onedir"' in spec_text
    assert "runtime_hooks = []" in spec_text
    assert "runtime_hooks.append(str(BUILD_VERSION_HOOK))" in spec_text
    assert "runtime_hooks.append(str(RUNTIME_HOOK))" in spec_text
    assert "runtime_hook_chdir.py" in spec_text
    assert "LOL_AUDIO_UNPACK_BUILD_VERSION" in spec_text
    assert "version_file is not None" in spec_text
    assert 'sys.platform.startswith("win")' in spec_text
    assert "version=str(version_file)" in spec_text
    assert "console=False" in spec_text
    assert "COLLECT(" in spec_text
    assert "exclude_binaries=True" in spec_text


def test_pyinstaller_python_build_script_defaults_to_onefile() -> None:
    """Python 构建入口应默认 onefile，并把模式参数转发给 spec。"""
    script_text = (PYINSTALLER_DIR / "build_gui.py").read_text(encoding="utf-8")

    assert "gui.spec" in script_text
    assert ".temp/pyinstaller" in script_text.replace("\\", "/")
    assert '"--mode"' in script_text
    assert '"--runtime-version"' in script_text
    assert '"--version-file"' in script_text
    assert 'default="onefile"' in script_text
    assert "pyinstaller" in script_text.lower()
    assert "--" in script_text
    assert "packer" not in script_text.lower()
    assert "CompanyName" in script_text
    assert "FileDescription" in script_text
    assert "ProductVersion" in script_text
    assert "OriginalFilename" in script_text


def test_pyinstaller_ps1_is_only_a_wrapper_to_python_entry() -> None:
    """PowerShell 脚本应退化为 Windows 包装层，而不是主实现。"""
    script_text = (PYINSTALLER_DIR / "build_gui.ps1").read_text(encoding="utf-8")

    assert "build_gui.py" in script_text
    assert "python" in script_text.lower()
    assert "packer" not in script_text.lower()


def test_pyinstaller_dependency_group_is_declared_in_pyproject() -> None:
    """仓库应声明独立的 PyInstaller 打包依赖组。"""
    pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "[dependency-groups]" in pyproject_text
    assert "build = [" in pyproject_text
    assert "pyinstaller" in pyproject_text.lower()


def test_runtime_hook_uses_runtime_paths_helper() -> None:
    """runtime hook 应避免提前导入项目包，防止触发启动期副作用。"""
    hook_text = (PYINSTALLER_DIR / "runtime_hook_chdir.py").read_text(encoding="utf-8")

    assert "lol_audio_unpack" not in hook_text
    assert "sys.executable" in hook_text
    assert "os.chdir" in hook_text


def test_pyinstaller_build_script_dry_run_supports_cp1252_output(tmp_path: Path) -> None:
    """build script 在 cp1252 控制台下也应能完成 dry-run。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    result = subprocess.run(
        [
            sys.executable,
            str(PYINSTALLER_DIR / "build_gui.py"),
            "--dry-run",
            "--skip-sync",
            "--clean",
            "--output-root",
            str(tmp_path / "pyinstaller-out"),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="cp1252",
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
