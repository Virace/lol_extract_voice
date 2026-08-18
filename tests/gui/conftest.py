"""为显式 GUI 测试提供 Qt 标记与配置路径隔离。"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from qfluentwidgets import qconfig

from lol_audio_unpack.gui.common import gui_config as gui_config_module
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """给当前目录收集的测试统一附加 GUI 标记。

    Args:
        items: 当前收集阶段包含的测试项。
    """
    gui_dir = Path(__file__).parent.resolve()
    for item in items:
        try:
            Path(item.path).resolve().relative_to(gui_dir)
        except ValueError:
            continue
        item.add_marker("gui")


@pytest.fixture(autouse=True)
def _isolate_gui_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """阻止 GUI 测试读取或写入真实项目配置。

    Args:
        monkeypatch: pytest 属性替换夹具。
        tmp_path: 当前测试的临时目录。
    """
    work_dir = tmp_path / "isolated_gui"
    work_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        gui_config_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=False,
            cwd=work_dir,
            executable=work_dir / "python.exe",
        ),
    )


@pytest.fixture(autouse=True)
def _restore_theme_state() -> Iterator[None]:
    """在每个 GUI 测试后恢复全局主题配置。

    Yields:
        测试执行控制权。
    """
    theme_mode = qconfig.themeMode.value
    theme_color = qconfig.themeColor.value

    yield

    qconfig.set(qconfig.themeMode, theme_mode)
    qconfig.set(qconfig.themeColor, theme_color)
