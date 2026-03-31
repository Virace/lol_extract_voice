"""首页状态控制器测试。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.gui.controllers.home_status_controller import (
    HomeCheckResult,
    HomeStatusController,
    HomeStatusDisplayState,
)


def test_home_status_controller_returns_missing_game_path_result() -> None:
    controller = HomeStatusController(
        get_game_version_fn=lambda _path: "16.5",
        cache_check_fn=lambda _output, _version: (False, ""),
    )

    result = controller.run_check(game_path=None, output_path=Path("output"))

    assert result == HomeCheckResult(
        version="",
        version_error="游戏目录未设置",
        cache_found=False,
        cache_path="",
    )


def test_home_status_controller_builds_display_state_for_cached_version() -> None:
    controller = HomeStatusController(
        get_game_version_fn=lambda _path: "16.5",
        cache_check_fn=lambda _output, _version: (True, "output/audios/16.5.2"),
    )

    result = controller.run_check(game_path=Path("Game"), output_path=Path("output"))
    state = controller.build_display_state(result=result, output_path=Path("output"))

    assert state == HomeStatusDisplayState(
        current_version="16.5",
        version_text="16.5",
        version_jump_enabled=False,
        cache_text="已找到 16.5",
        cache_path="output/audios/16.5.2",
        cache_jump_enabled=True,
    )


def test_home_status_controller_builds_failure_display_state() -> None:
    controller = HomeStatusController(
        get_game_version_fn=lambda _path: "16.5",
        cache_check_fn=lambda _output, _version: (False, ""),
    )

    state = controller.build_failure_state()

    assert state == HomeStatusDisplayState(
        current_version="",
        version_text="读取失败",
        version_jump_enabled=False,
        cache_text="检查失败",
        cache_path="",
        cache_jump_enabled=False,
    )


def test_home_status_controller_start_check_emits_display_state_ready(qtbot, tmp_path) -> None:
    controller = HomeStatusController(
        get_game_version_fn=lambda _path: "16.5",
        cache_check_fn=lambda _output, _version: (True, "output/audios/16.5.2"),
    )

    with qtbot.waitSignal(controller.display_state_ready, timeout=1000) as blocker:
        controller.start_check(game_path=tmp_path, output_path=tmp_path)

    assert blocker.args == [
        HomeStatusDisplayState(
            current_version="16.5",
            version_text="16.5",
            version_jump_enabled=False,
            cache_text="已找到 16.5",
            cache_path="output/audios/16.5.2",
            cache_jump_enabled=True,
        )
    ]


def test_home_status_controller_shutdown_clears_active_worker() -> None:
    controller = HomeStatusController(
        get_game_version_fn=lambda _path: "16.5",
        cache_check_fn=lambda _output, _version: (False, ""),
    )
    controller._active_worker = object()

    assert controller.has_active_background_check() is True

    controller.shutdown()

    assert controller.has_active_background_check() is False
