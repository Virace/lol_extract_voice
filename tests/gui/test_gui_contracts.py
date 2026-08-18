"""GUI 合同对象的最小回归测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lol_audio_unpack.gui.controllers.contracts import (
    OverviewSelectionSyncRequest,
    RuntimeLoggingConfig,
)
from lol_audio_unpack.gui.view.execution_page import ExecutionPage


def test_runtime_logging_config_from_gui_config_uses_resolved_log_dir() -> None:
    cfg = SimpleNamespace(
        console_log_level="DEBUG",
        file_log_level="INFO",
        resolve_log_dir=lambda: Path("logs/runtime"),
    )

    payload = RuntimeLoggingConfig.from_gui_config(cfg)

    assert payload.log_dir == Path("logs/runtime")
    assert payload.console_log_level == "DEBUG"
    assert payload.file_log_level == "INFO"


def test_execution_page_accepts_overview_selection_sync_request(qtbot) -> None:
    page = ExecutionPage()
    qtbot.addWidget(page)
    payload = OverviewSelectionSyncRequest(
        source="overview_selection",
        champion_ids=(1, 103),
        map_ids=(11,),
        summary="已同步 2 个英雄、1 张地图，请前往执行中心继续创建任务。",
    )

    summary = page.set_selected_entities(payload)

    assert summary == payload.summary
    assert page.taskBuilderPanel.current_target_ids() == (("1", "103"), ("11",))
