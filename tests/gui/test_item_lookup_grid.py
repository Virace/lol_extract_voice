"""装备查询宫格组件测试。"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QListView

from lol_audio_unpack.gui.components.item_lookup_grid import (
    ITEM_MODE_ARENA,
    ITEM_MODE_COMMON,
    ITEM_ROW_ROLE,
    ItemDelegate,
    ItemGridView,
    ItemIconCache,
)
from lol_audio_unpack.gui.service.item_catalog import ItemRecord

ITEM_COUNT = 2


def _png_bytes() -> bytes:
    """生成测试用的极小 PNG 图标。"""
    image = QImage(1, 1, QImage.Format.Format_ARGB32)
    image.fill(QColor("#ff0000"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def _run_worker_sync(worker) -> None:
    """同步执行图标 worker，避免测试依赖真实网络。"""
    worker.run()


def test_item_grid_view_uses_wrapped_icon_mode(qtbot) -> None:
    view = ItemGridView()
    qtbot.addWidget(view)

    assert view.viewMode() == QListView.ViewMode.IconMode
    assert view.flow() == QListView.Flow.LeftToRight
    assert view.isWrapping() is True
    assert view.gridSize().width() > view.gridSize().height() // 2


def test_item_icon_cache_loads_pixmap_from_background_bytes(qtbot) -> None:
    cache = ItemIconCache(
        fetch_bytes_fn=lambda _url: _png_bytes(),
        start_worker_fn=_run_worker_sync,
    )

    assert cache.pixmap("https://example.test/item.png", QSize(16, 16)) is None

    pixmap = cache.pixmap("https://example.test/item.png", QSize(16, 16))

    assert pixmap is not None
    assert pixmap.isNull() is False


def test_item_delegate_paints_rounded_icon_corners(qtbot) -> None:
    cache = ItemIconCache(
        fetch_bytes_fn=lambda _url: _png_bytes(),
        start_worker_fn=_run_worker_sync,
    )
    cache.pixmap("https://example.test/item.png", QSize(20, 20))
    delegate = ItemDelegate(cache)
    image = QImage(20, 20, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)

    delegate._paint_icon(painter, image.rect(), "https://example.test/item.png")
    painter.end()

    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(10, 10).alpha() > 0


def test_item_grid_view_filters_by_name_id_and_keywords(qtbot) -> None:
    view = ItemGridView()
    qtbot.addWidget(view)
    view.set_items(
        [
            ItemRecord(item_id="3084", name="心之钢", icon_url="", keywords="xzg,heartsteel"),
            ItemRecord(item_id="1001", name="鞋子", icon_url="", keywords="xiezi"),
        ]
    )

    assert view.total_count() == ITEM_COUNT
    assert view.visible_count() == ITEM_COUNT

    view.set_keyword("心之钢")
    assert view.visible_count() == 1
    assert view.find_index_by_item_id("3084").isValid() is True

    view.set_keyword("1001")
    assert view.visible_count() == 1
    assert view.find_index_by_item_id("1001").data(ITEM_ROW_ROLE).name == "鞋子"

    view.set_keyword("heartsteel")
    assert view.visible_count() == 1
    assert view.find_index_by_item_id("3084").isValid() is True


def test_item_grid_view_filters_by_mode(qtbot) -> None:
    view = ItemGridView()
    qtbot.addWidget(view)
    view.set_items(
        [
            ItemRecord(item_id="3110", name="冰霜之心", icon_url="", maps=("召唤师峡谷", "嚎哭深渊")),
            ItemRecord(item_id="223110", name="冰霜之心", icon_url="", maps=("斗魂竞技场",)),
            ItemRecord(item_id="323110", name="冰霜之心", icon_url="", maps=("未知",)),
        ]
    )

    view.set_mode(ITEM_MODE_COMMON)
    assert view.visible_items() == [
        ItemRecord(item_id="3110", name="冰霜之心", icon_url="", maps=("召唤师峡谷", "嚎哭深渊"))
    ]

    view.set_mode(ITEM_MODE_ARENA)
    assert view.visible_items() == [
        ItemRecord(item_id="223110", name="冰霜之心", icon_url="", maps=("斗魂竞技场",))
    ]


def test_item_grid_view_exposes_visible_items(qtbot) -> None:
    view = ItemGridView()
    qtbot.addWidget(view)
    view.set_items(
        [
            ItemRecord(item_id="3084", name="心之钢", icon_url="", keywords="xzg"),
            ItemRecord(item_id="1055", name="多兰之刃", icon_url="", keywords="duolan"),
        ]
    )

    view.set_keyword("duolan")

    assert view.visible_items() == [ItemRecord(item_id="1055", name="多兰之刃", icon_url="", keywords="duolan")]
