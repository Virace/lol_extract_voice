"""GitHub Release workflow 配置测试。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "release-build-gui.yml"


def test_release_build_gui_workflow_exists() -> None:
    """应提供 tag 触发的 GUI release workflow。"""
    assert WORKFLOW_PATH.is_file()


def test_release_build_gui_workflow_targets_tag_push_and_main_guard() -> None:
    """workflow 应允许 tag 触发，并在运行时校验 tag 提交属于 main。"""
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "push:" in workflow_text
    assert "tags:" in workflow_text
    assert "- '*'" in workflow_text
    assert "origin/main" in workflow_text
    assert "on_main=true" in workflow_text
    assert "on_main=false" in workflow_text
    assert "is_prerelease" in workflow_text
    assert "-pre\\." in workflow_text


def test_release_build_gui_workflow_builds_windows_gui_and_publishes_release() -> None:
    """workflow 应在 Windows 上构建 GUI 并发布 GitHub Release。"""
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "windows-latest" in workflow_text
    assert "actions/checkout@v6" in workflow_text
    assert "actions/setup-python@v6" in workflow_text
    assert "astral-sh/setup-uv@v6" in workflow_text
    assert "python-version-file: .python-version" in workflow_text
    assert "python scripts/pyinstaller/build_gui.py --clean" in workflow_text
    assert "LolAudioUnpack-$tag-windows-x64.exe" in workflow_text
    assert "softprops/action-gh-release@v2" in workflow_text
    assert "prerelease:" in workflow_text
    assert "generate_release_notes: true" in workflow_text
