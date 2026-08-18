"""首页状态控制器测试。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.gui.controllers.home_status import (
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
        version_detail="当前游戏客户端版本。",
        version_role="info",
        cache_detail="已发现当前版本的音频产物。",
        cache_role="success",
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
        version_detail="请检查游戏目录是否完整。",
        version_role="critical",
        cache_detail="暂时无法判断当前版本产物状态。",
        cache_role="critical",
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
            version_detail="当前游戏客户端版本。",
            version_role="info",
            cache_detail="已发现当前版本的音频产物。",
            cache_role="success",
        )
    ]


def test_home_status_controller_builds_guidance_for_missing_game_path() -> None:
    """未配置目录时应提供行动指引，不直接暴露内部异常文本。"""
    controller = HomeStatusController(
        get_game_version_fn=lambda _path: "16.5",
        cache_check_fn=lambda _output, _version: (False, ""),
    )
    result = controller.run_check(game_path=None, output_path=Path("output"))

    state = controller.build_display_state(result=result, output_path=Path("output"))

    assert state.version_text == "等待配置"
    assert state.version_role == "caution"
    assert state.cache_text == "尚未检查"
    assert state.cache_role == "neutral"


def test_home_status_controller_builds_neutral_state_for_missing_outputs() -> None:
    """版本有效但没有产物时应表达为空态，而不是错误态。"""
    controller = HomeStatusController(
        get_game_version_fn=lambda _path: "16.5",
        cache_check_fn=lambda _output, _version: (False, ""),
    )
    result = controller.run_check(game_path=Path("Game"), output_path=Path("output"))

    state = controller.build_display_state(result=result, output_path=Path("output"))

    assert state.cache_text == "尚未解包"
    assert state.cache_detail == "当前版本 16.5 尚无音频产物。"
    assert state.cache_role == "neutral"


def test_home_status_controller_shutdown_clears_active_worker() -> None:
    controller = HomeStatusController(
        get_game_version_fn=lambda _path: "16.5",
        cache_check_fn=lambda _output, _version: (False, ""),
    )
    controller._active_worker = object()

    assert controller.has_active_background_check() is True

    controller.shutdown()

    assert controller.has_active_background_check() is False
