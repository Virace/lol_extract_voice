"""GUI AppContext 前置门禁测试。"""

from pathlib import Path

from lol_audio_unpack.gui.common.app_context_guard import get_block_reason


class _FakeConfig:
    """用于门禁测试的最小配置替身。"""

    game_path = ""

    def resolve_game_path(self) -> Path | None:
        return None


def test_gui_context_requires_local_game_path() -> None:
    """GUI 上下文必须要求本地游戏目录。"""
    cfg = _FakeConfig()

    assert get_block_reason(cfg) == "请先在「全局设置」中配置游戏目录。"
