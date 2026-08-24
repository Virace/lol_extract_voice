"""实体总览共享数据阶段与选择门禁测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.shared_data import SharedDataPhase, SharedDataState, SharedDataSummary
from lol_audio_unpack.gui.view.overview_page import OverviewPage


def test_overview_partial_keeps_verified_rows_but_disables_sync(qtbot) -> None:
    """partial 可浏览已验证行，但不能把不完整目录发送到执行中心。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    page.set_entity_data("champions", [{"id": "1", "name": "Annie"}])
    page.set_entity_data("maps", [{"id": "0", "name": "Common"}])
    page._selected_entity_ids["champions"] = {"1"}
    page.set_shared_data_state(
        SharedDataState(
            SharedDataPhase.PARTIAL,
            2,
            summary=SharedDataSummary(2, 1, 1, 1, 1, 0, 0, 0, 0),
        )
    )

    assert page._entity_data_store.rows_for("champions") == [{"id": "1", "name": "Annie"}]
    assert page.shared_data_status.isHidden() is False
    assert page.shared_data_status.statusLabel.text() == "部分实体数据未就绪"
    assert page.clear_selection_btn.isEnabled() is True
    assert page.sync_selection_btn.isEnabled() is False
    assert "新任务已暂停" in page.sync_selection_btn.toolTip()

    page.set_shared_data_state(SharedDataState(SharedDataPhase.READY, 2))

    assert page.shared_data_status.isHidden() is True
    assert page.sync_selection_btn.isEnabled() is True


def test_overview_active_state_uses_loading_placeholder_instead_of_empty_catalog(qtbot) -> None:
    """扫描阶段的空 rows 必须呈现当前阶段，而不是“没有实体”。"""
    page = OverviewPage()
    qtbot.addWidget(page)

    page.set_shared_data_state(SharedDataState(SharedDataPhase.VERIFYING, 3))

    assert page.shared_data_status.statusLabel.text() == "正在完整复检英雄与地图目录。"
    assert "验证实体数据" in page.text_preview.toPlainText()
