"""解析 GUI 开发启动参数。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_MOCK_PROGRESS_INTERVAL_MS = 50
MIN_MOCK_PROGRESS_INTERVAL_MS = 10
MAX_MOCK_PROGRESS_INTERVAL_MS = 2000


@dataclass(frozen=True, slots=True)
class GuiLaunchOptions:
    """描述 GUI 启动时启用的开发能力。

    Attributes:
        shared_progress_demo_interval_ms: 共享进度 mock 的刷新间隔；为空时使用真实数据链路。
    """

    shared_progress_demo_interval_ms: int | None = None


def parse_gui_launch_options(arguments: Sequence[str]) -> tuple[GuiLaunchOptions, list[str]]:
    """解析应用自有参数，并保留 Qt 可继续消费的未知参数。

    Args:
        arguments: 不含程序名的命令行参数。

    Returns:
        GUI 启动选项与未识别的 Qt 参数。
    """
    parser = argparse.ArgumentParser(
        prog="unpack-gui",
        description="启动 Lol Audio Unpack 图形界面。",
    )
    parser.add_argument(
        "--mock-shared-progress",
        action="store_true",
        help="循环模拟实体数据检查、更新与验证进度，不读取或修改真实实体数据。",
    )
    parser.add_argument(
        "--mock-progress-interval",
        type=int,
        metavar="MS",
        help=f"mock 每步间隔（{MIN_MOCK_PROGRESS_INTERVAL_MS}-{MAX_MOCK_PROGRESS_INTERVAL_MS} 毫秒）。",
    )
    namespace, qt_arguments = parser.parse_known_args(list(arguments))

    interval_ms = namespace.mock_progress_interval
    if interval_ms is not None and not namespace.mock_shared_progress:
        parser.error("--mock-progress-interval 只能与 --mock-shared-progress 一起使用")
    if interval_ms is not None and not MIN_MOCK_PROGRESS_INTERVAL_MS <= interval_ms <= MAX_MOCK_PROGRESS_INTERVAL_MS:
        parser.error(
            "--mock-progress-interval 必须在 "
            f"{MIN_MOCK_PROGRESS_INTERVAL_MS} 到 {MAX_MOCK_PROGRESS_INTERVAL_MS} 毫秒之间"
        )

    if namespace.mock_shared_progress:
        interval_ms = interval_ms or DEFAULT_MOCK_PROGRESS_INTERVAL_MS
    return GuiLaunchOptions(shared_progress_demo_interval_ms=interval_ms), qt_arguments


__all__ = ["GuiLaunchOptions", "parse_gui_launch_options"]
