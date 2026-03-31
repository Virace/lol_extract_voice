"""执行中心页面初始化回归测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.view.execution_page import ExecutionPage


def test_execution_page_initializes_with_queue_placeholder(qtbot) -> None:
    page = ExecutionPage()
    qtbot.addWidget(page)

    assert page.draft_list.count() == 1
    placeholder = page.draft_list.item(0)
    assert placeholder is not None
    assert placeholder.text() == "当前任务队列为空。"
