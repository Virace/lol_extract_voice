"""首页页面行为测试。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

import lol_audio_unpack.gui.view.home_page as home_page_module
from lol_audio_unpack.gui.shared_data import (
    SharedDataPhase,
    SharedDataProblem,
    SharedDataProblemCode,
    SharedDataProgress,
    SharedDataState,
    SharedDataSummary,
)
from lol_audio_unpack.gui.view.home_page import HomePage

EXPECTED_PROGRESS_CURRENT = 42
EXPECTED_PROGRESS_TOTAL = 173


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

    game_path = "game-client"
    output_path = "output-root"
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

    assert _FakeHomeStatusController.calls == [(Path("game-client"), Path("output-root"))]


def test_home_page_switches_between_determinate_progress_and_terminal_summary(qtbot, monkeypatch) -> None:
    """首页应按同一 typed snapshot 展示真实计数与最终动态摘要。"""
    monkeypatch.setattr(home_page_module, "HomeStatusController", _FakeHomeStatusController)
    page = HomePage(_FakeConfig())
    qtbot.addWidget(page)

    page.set_shared_data_state(
        SharedDataState(
            SharedDataPhase.CHECKING,
            1,
            "local_path",
            progress=SharedDataProgress(
                1,
                "champions",
                "advanced",
                current=EXPECTED_PROGRESS_CURRENT,
                total=EXPECTED_PROGRESS_TOTAL,
            ),
        )
    )

    assert page.indeterminate_progress_bar.isHidden() is True
    assert page.determinate_progress_bar.isHidden() is False
    assert page.determinate_progress_bar.value() == EXPECTED_PROGRESS_CURRENT
    assert page.determinate_progress_bar.maximum() == EXPECTED_PROGRESS_TOTAL
    assert page.progress_count_label.text() == "英雄数据 · 42/173"

    page.set_shared_data_state(
        SharedDataState(
            SharedDataPhase.READY,
            1,
            "local_path",
            summary=SharedDataSummary(173, 173, 0, 9, 9, 0, 63, 0, 63),
        )
    )

    assert page.entity_data_card.valueLabel.text() == "已就绪"
    assert page.entity_data_card.detailLabel.text() == "已加载 173 个英雄和 9 张地图。"
    assert page.determinate_progress_bar.isHidden() is True


def test_home_page_emits_stable_recovery_action_key(qtbot, monkeypatch) -> None:
    """首页恢复按钮只发送稳定 action key，不以按钮中文作为业务身份。"""
    monkeypatch.setattr(home_page_module, "HomeStatusController", _FakeHomeStatusController)
    page = HomePage(_FakeConfig())
    qtbot.addWidget(page)
    page.set_shared_data_state(
        SharedDataState(
            SharedDataPhase.BLOCKED,
            1,
            "local_path",
            problem=SharedDataProblem(
                SharedDataProblemCode.CONFIGURATION_REQUIRED,
                "context",
                "请先配置游戏目录。",
            ),
        )
    )

    with qtbot.waitSignal(page.shared_data_action_requested, timeout=1000) as emitted:
        qtbot.mouseClick(page.shared_data_action_btn, Qt.MouseButton.LeftButton)

    assert emitted.args == ["open_settings"]
