"""装备查询页面测试。"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from lol_audio_unpack.gui.components.item_lookup_grid import ITEM_MODE_ARENA
from lol_audio_unpack.gui.service.item_catalog import ItemCatalogPayload, ItemRecord
from lol_audio_unpack.gui.view.item_lookup_page import ItemLookupPage


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


def test_item_lookup_page_copies_plain_item_id(qtbot) -> None:
    page = ItemLookupPage(fetch_items_fn=_sample_payload, start_worker_fn=_run_worker_sync)
    qtbot.addWidget(page)
    page.set_catalog(_sample_payload())

    assert page.copy_item_id("3084") is True

    clipboard = QApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == "3084"


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
