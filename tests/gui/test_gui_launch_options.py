"""GUI 开发启动参数测试。"""

from __future__ import annotations

import pytest

from lol_audio_unpack.gui.launch_options import (
    DEFAULT_MOCK_PROGRESS_INTERVAL_MS,
    parse_gui_launch_options,
)

CUSTOM_MOCK_PROGRESS_INTERVAL_MS = 80


def test_gui_launch_options_use_real_data_by_default() -> None:
    options, qt_arguments = parse_gui_launch_options(["--style", "windows"])

    assert options.shared_progress_demo_interval_ms is None
    assert qt_arguments == ["--style", "windows"]


def test_gui_launch_options_enable_default_or_custom_mock_speed() -> None:
    default_options, _qt_arguments = parse_gui_launch_options(["--mock-shared-progress"])
    custom_options, _qt_arguments = parse_gui_launch_options(
        ["--mock-shared-progress", "--mock-progress-interval", str(CUSTOM_MOCK_PROGRESS_INTERVAL_MS)]
    )

    assert default_options.shared_progress_demo_interval_ms == DEFAULT_MOCK_PROGRESS_INTERVAL_MS
    assert custom_options.shared_progress_demo_interval_ms == CUSTOM_MOCK_PROGRESS_INTERVAL_MS


@pytest.mark.parametrize(
    "arguments",
    [
        ["--mock-progress-interval", "80"],
        ["--mock-shared-progress", "--mock-progress-interval", "0"],
        ["--mock-shared-progress", "--mock-progress-interval", "2001"],
    ],
)
def test_gui_launch_options_reject_invalid_mock_interval(arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_gui_launch_options(arguments)
