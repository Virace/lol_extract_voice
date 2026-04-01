"""打包版远程模式临时策略测试。"""

from lol_audio_unpack.gui.common.packaged_remote_mode_policy import (
    available_source_mode_labels,
    effective_source_mode,
    normalize_app_context_settings,
    packaged_remote_mode_disabled,
    packaged_remote_mode_fallback_needed,
    remote_source_panel_visible,
)


def test_packaged_remote_mode_disabled_matches_frozen_state() -> None:
    """冻结态应启用打包版远程模式限制。"""
    assert packaged_remote_mode_disabled(is_frozen=True) is True
    assert packaged_remote_mode_disabled(is_frozen=False) is False


def test_effective_source_mode_keeps_remote_when_not_frozen() -> None:
    """源码运行时应保留远程模式。"""
    assert effective_source_mode("remote_snapshot", is_frozen=False) == "remote_snapshot"


def test_effective_source_mode_falls_back_to_local_when_frozen() -> None:
    """打包版运行时应把远程模式回退到本地模式。"""
    assert effective_source_mode("remote_snapshot", is_frozen=True) == "local_path"


def test_available_source_mode_items_hide_remote_in_packaged_build() -> None:
    """打包版来源模式下拉只应暴露本地模式。"""
    assert available_source_mode_labels(is_frozen=True) == ["本地模式"]


def test_normalize_app_context_settings_forces_local_path_when_frozen() -> None:
    """打包版 GUI settings 应在运行时强制使用本地模式。"""
    settings = normalize_app_context_settings(
        {"SOURCE_MODE": "remote_snapshot", "GAME_PATH": "game"},
        is_frozen=True,
    )

    assert settings["SOURCE_MODE"] == "local_path"
    assert settings["GAME_PATH"] == "game"


def test_packaged_remote_mode_fallback_needed_only_for_packaged_remote_runtime() -> None:
    """只有打包态且原始值为远程模式时才需要提示自动回退。"""
    assert packaged_remote_mode_fallback_needed("remote_snapshot", is_frozen=True) is True
    assert packaged_remote_mode_fallback_needed("local_path", is_frozen=True) is False
    assert packaged_remote_mode_fallback_needed("remote_snapshot", is_frozen=False) is False


def test_remote_source_panel_visible_matches_effective_source_mode() -> None:
    """远程配置面板显隐应跟随运行时有效来源模式。"""
    assert remote_source_panel_visible("remote_snapshot", is_frozen=False) is True
    assert remote_source_panel_visible("remote_snapshot", is_frozen=True) is False
    assert remote_source_panel_visible("local_path", is_frozen=False) is False
