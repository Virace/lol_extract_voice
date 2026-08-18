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
