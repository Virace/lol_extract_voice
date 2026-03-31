"""首页页面行为测试。"""

from __future__ import annotations

from pathlib import Path

import lol_audio_unpack.gui.view.home_page as home_page_module
from lol_audio_unpack.gui.view.home_page import HomePage


class _FakeSignal:
    """最小信号替身。"""

    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self._callbacks):
            callback(*args)


class _FakeHomeStatusController:
    """记录首页状态检查调用次数的替身控制器。"""

    calls: list[tuple[Path | None, Path]] = []

    def __init__(self, parent=None) -> None:
        _ = parent
        self.display_state_ready = _FakeSignal()

    def start_check(self, *, game_path: Path | None, output_path: Path) -> None:
        self.__class__.calls.append((game_path, output_path))


class _FakeConfig:
    """首页页面测试使用的最小配置对象。"""

    game_path = "D:/Games/Tencent/WeGameApps/英雄联盟"
    output_path = "E:/Temp/Scratch/lol"
    wwiser_path = ""
    vgmstream_path = ""

    def resolve_game_path(self) -> Path:
        return Path(self.game_path)

    def resolve_output_path(self) -> Path:
        return Path(self.output_path)


def test_home_page_defers_initial_status_check_until_show(qtbot, monkeypatch) -> None:
    _FakeHomeStatusController.calls = []
    monkeypatch.setattr(home_page_module, "HomeStatusController", _FakeHomeStatusController)

    page = HomePage(_FakeConfig())
    qtbot.addWidget(page)

    assert _FakeHomeStatusController.calls == []

    page.show()
    qtbot.waitUntil(lambda: len(_FakeHomeStatusController.calls) == 1, timeout=1000)

    assert _FakeHomeStatusController.calls == [
        (Path("D:/Games/Tencent/WeGameApps/英雄联盟"), Path("E:/Temp/Scratch/lol"))
    ]
