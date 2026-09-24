"""装备查询页面测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.gui.components.item_lookup_grid import ITEM_MODE_ARENA
from lol_audio_unpack.gui.controllers.overview_preview import EVENT_PREVIEW_MODE, OverviewPreviewLoadResult
from lol_audio_unpack.gui.service.item_catalog import ItemCatalogPayload, ItemRecord
from lol_audio_unpack.gui.view.item_lookup_page import ItemLookupPage
from lol_audio_unpack.gui.view.overview_page import OverviewPage
from lol_audio_unpack.gui.window import MainWindow


def _run_worker_sync(worker) -> None:
    """在测试里同步执行 GUI worker。"""
    worker.run()


def _sample_payload() -> ItemCatalogPayload:
    """构造装备查询页测试数据。"""
    return ItemCatalogPayload(
        version="16.12",
        file_time="2026-06-10 11:51:45",
        items=[
            ItemRecord(item_id="3084", name="心之钢", icon_url="", keywords="xzg,heartsteel", maps=("召唤师峡谷",)),
            ItemRecord(item_id="1001", name="鞋子", icon_url="", keywords="xiezi"),
        ],
    )


def test_item_lookup_page_loads_catalog_and_filters(qtbot) -> None:
    page = ItemLookupPage(fetch_items_fn=_sample_payload, start_worker_fn=_run_worker_sync)
    qtbot.addWidget(page)

    page.load_items()

    assert "版本 16.12" in page.source_label.text()
    assert "2026-06-10 11:51:45" in page.source_label.text()
    assert page.status_label.text() == "显示 2/2 件装备"

    page.search_input.setText("3084")

    assert page.item_grid.visible_count() == 1
    assert page.status_label.text() == "显示 1/2 件装备"


@pytest.mark.parametrize("item_id", ["3084", "223110"])
def test_item_click_opens_common_events_after_loading(qtbot, item_id) -> None:
    """普通与竞技场 ID 原样传入常规地图，异步完成与重复点击均保留事件筛选。"""
    page = ItemLookupPage(fetch_items_fn=_sample_payload, start_worker_fn=_run_worker_sync)
    qtbot.addWidget(page)
    page.set_catalog(ItemCatalogPayload(version="", file_time="", items=[ItemRecord(item_id=item_id, name="装备")]))
    overview = OverviewPage()
    qtbot.addWidget(overview)
    overview.set_entity_data("maps", [{"id": "0", "name": "常规"}, {"id": "11", "name": "召唤师峡谷"}])
    overview.search_input.setText("Annie")
    scheduled = []
    overview._preview_pool = SimpleNamespace(start=scheduled.append)
    destinations = []
    window = SimpleNamespace(overviewInterface=overview, switchTo=destinations.append)
    page.item_search_requested.connect(lambda value: MainWindow._show_item_events(window, value))

    page.item_grid.clicked.emit(page.item_grid.find_index_by_item_id(item_id))

    assert destinations == [overview]
    assert overview.nav_pivot.currentRouteKey() == "maps"
    assert overview.search_input.text() == ""
    assert (
        overview.entityListPanel.resolve_row_payload(overview.entityListPanel.current_list().currentIndex())["id"]
        == "0"
    )
    assert overview.entityListPanel.selected_entity_ids("maps") == set()
    assert len(scheduled) == 1
    scheduled[0].signals.finished.emit(
        OverviewPreviewLoadResult(
            entity_id="0",
            mapping_path=Path("common.msgpack"),
            mapping_data={"map": {"0": {"events": {"SFX": {f"Play_Item_{item_id}": ["123"], "Play_Other": ["456"]}}}}},
            preview_content="",
            available_audio_ids={"123", "456"},
            group_label_map={},
        )
    )

    assert overview.preview_mode_pivot.currentRouteKey() == EVENT_PREVIEW_MODE
    assert overview.previewPanel.preview_search_input.text() == item_id
    assert "匹配事件 1" in overview.audio_preview_summary_label.text()
    overview.previewPanel.preview_search_input.setText("Other")
    page.item_grid.clicked.emit(page.item_grid.find_index_by_item_id(item_id))
    assert len(scheduled) == 1
    assert overview.previewPanel.preview_search_input.text() == item_id
    assert "匹配事件 1" in overview.audio_preview_summary_label.text()


def test_item_navigation_cancel_preserves_export_and_filters(qtbot, monkeypatch) -> None:
    """取消清空导出选择时，不跳页也不修改原目录和搜索。"""
    overview = OverviewPage()
    qtbot.addWidget(overview)
    overview.set_entity_data("maps", [{"id": "0", "name": "常规"}])
    overview.search_input.setText("Annie")
    overview.previewPanel.preview_search_input.setText("Attack")
    request = SimpleNamespace(entity_type="champions", entity_id="1")
    overview.export_controller.request = request
    monkeypatch.setattr(overview.export_controller, "confirm_change", lambda: False)
    destinations = []
    window = SimpleNamespace(overviewInterface=overview, switchTo=destinations.append)

    MainWindow._show_item_events(window, "3084")

    assert destinations == []
    assert overview.export_controller.request is request
    assert overview.nav_pivot.currentRouteKey() == "champions"
    assert overview.search_input.text() == "Annie"
    assert overview.previewPanel.preview_search_input.text() == "Attack"


def test_item_lookup_page_filters_by_mode_tab(qtbot) -> None:
    payload = ItemCatalogPayload(
        version="16.12",
        file_time="2026-06-10 11:51:45",
        items=[
            ItemRecord(item_id="3110", name="冰霜之心", maps=("召唤师峡谷", "嚎哭深渊")),
            ItemRecord(item_id="223110", name="冰霜之心", maps=("斗魂竞技场",)),
        ],
    )
    page = ItemLookupPage(fetch_items_fn=lambda: payload, start_worker_fn=_run_worker_sync)
    qtbot.addWidget(page)
    page.set_catalog(payload)

    page.mode_tabs.setCurrentItem(ITEM_MODE_ARENA)

    assert page.item_grid.visible_items() == [ItemRecord(item_id="223110", name="冰霜之心", maps=("斗魂竞技场",))]
    assert page.status_label.text() == "显示 1/2 件装备"


def test_item_lookup_page_shows_failure_state_without_hiding_refresh(qtbot) -> None:
    def _raise_error() -> ItemCatalogPayload:
        raise RuntimeError("offline")

    page = ItemLookupPage(fetch_items_fn=_raise_error, start_worker_fn=_run_worker_sync)
    qtbot.addWidget(page)

    page.load_items()

    assert page.refresh_button.isEnabled() is True
    assert "装备数据加载失败" in page.status_label.text()
    assert "offline" in page.status_label.toolTip()
