"""GUI AppContext 前置门禁测试。"""

from pathlib import Path

from lol_audio_unpack.gui.common.app_context_guard import get_app_context_block_reason


class _FakeConfig:
    """用于门禁测试的最小配置替身。"""

    source_mode = "remote_snapshot"
    effective_source_mode = "local_path"
    game_path = ""

    def resolve_game_path(self) -> Path | None:
        return None


def test_packaged_remote_mode_still_requires_local_game_path() -> None:
    """打包态远程模式回退后仍应要求本地游戏目录。"""
    cfg = _FakeConfig()

    assert get_app_context_block_reason(cfg) == "请先在「全局设置」中配置游戏目录。"
