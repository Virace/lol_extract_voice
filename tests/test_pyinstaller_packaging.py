"""PyInstaller 正式构建入口测试。"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYINSTALLER_DIR = PROJECT_ROOT / "scripts" / "pyinstaller"


def _load_build_gui_module():
    module_path = PYINSTALLER_DIR / "build_gui.py"
    spec = importlib.util.spec_from_file_location("lol_audio_unpack_build_gui_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_pyinstaller_spec_recursively_packages_nested_gui_assets() -> None:
    """spec 应递归打包 GUI 资源子目录，避免冻结态缺少二维码等嵌套资源。"""
    spec_text = (PYINSTALLER_DIR / "gui.spec").read_text(encoding="utf-8")

    assert 'GUI_ASSET_ROOT.rglob("*")' in spec_text
    assert "relative_to(GUI_ASSET_ROOT)" in spec_text
    assert "lol_audio_unpack/gui/assets/" in spec_text


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


def test_pyinstaller_build_script_keeps_version_file_when_cleaning_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """--clean 不应把即将传给 spec 的 version file 一起删掉。"""
    build_gui = _load_build_gui_module()
    output_root = tmp_path / "pyinstaller-out"
    stale_file = output_root / "build" / "stale.txt"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text("stale", encoding="utf-8")

    def _fake_run_command(command: list[str], *, dry_run: bool) -> None:
        assert dry_run is False
        version_path = Path(command[command.index("--version-file") + 1])
        assert version_path.is_file()
        assert "CompanyName" in version_path.read_text(encoding="utf-8")

    monkeypatch.setattr(build_gui, "_ensure_supported_host", lambda: None)
    monkeypatch.setattr(build_gui, "_resolve_build_version", lambda: "3.6.0-pre.5")
    monkeypatch.setattr(build_gui, "_run_command", _fake_run_command)
    monkeypatch.setattr(sys, "argv", ["build_gui.py", "--clean", "--skip-sync", "--output-root", str(output_root)])

    assert build_gui.main() == 0
    assert stale_file.exists() is False
