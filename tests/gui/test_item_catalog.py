"""装备资料数据源解析测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.service.item_catalog import ItemRecord, parse_tencent_items


def test_parse_tencent_items_extracts_meta_and_rows() -> None:
    payload = {
        "version": "16.12",
        "fileTime": "2026-06-10 11:51:45",
        "items": [
            {
                "itemId": "3084",
                "name": "心之钢",
                "iconPath": "http://game.gtimg.cn/images/lol/act/img/item/3084.png",
                "keywords": "心之钢,xinzhigang",
            }
        ],
    }

    result = parse_tencent_items(payload)

    assert result.version == "16.12"
    assert result.file_time == "2026-06-10 11:51:45"
    assert result.items == [
        ItemRecord(
            item_id="3084",
            name="心之钢",
            icon_url="https://game.gtimg.cn/images/lol/act/img/item/3084.png",
            keywords="心之钢,xinzhigang",
        )
    ]


def test_parse_tencent_items_normalizes_protocol_relative_icon_url() -> None:
    result = parse_tencent_items(
        {
            "items": [
                {
                    "itemId": 1001,
                    "name": "鞋子",
                    "iconPath": "//game.gtimg.cn/images/lol/act/img/item/1001.png",
                }
            ]
        }
    )

    assert result.items[0].icon_url == "https://game.gtimg.cn/images/lol/act/img/item/1001.png"


def test_parse_tencent_items_extracts_maps() -> None:
    result = parse_tencent_items(
        {
            "items": [
                {
                    "itemId": "223110",
                    "name": "冰霜之心",
                    "maps": ["斗魂竞技场"],
                }
            ]
        }
    )

    assert result.items[0].maps == ("斗魂竞技场",)


def test_parse_tencent_items_skips_invalid_and_duplicate_rows() -> None:
    result = parse_tencent_items(
        {
            "items": [
                {"itemId": "3084", "name": "心之钢", "iconPath": ""},
                {"itemId": "3084", "name": "重复心之钢", "iconPath": ""},
                {"itemId": "", "name": "缺少 ID", "iconPath": ""},
                {"itemId": "9999", "name": "", "iconPath": ""},
            ]
        }
    )

    assert [item.item_id for item in result.items] == ["3084"]
    assert result.items[0].name == "心之钢"


def test_parse_tencent_items_allows_missing_meta() -> None:
    result = parse_tencent_items({"items": [{"itemId": "1055", "name": "多兰之刃"}]})

    assert result.version == ""
    assert result.file_time == ""
    assert result.items[0].item_id == "1055"


def test_item_record_search_text_contains_id_name_and_keywords() -> None:
    item = ItemRecord(item_id="3084", name="心之钢", icon_url="", keywords="xzg,heartsteel")

    assert "3084" in item.search_text()
    assert "心之钢" in item.search_text()
    assert "heartsteel" in item.search_text()
