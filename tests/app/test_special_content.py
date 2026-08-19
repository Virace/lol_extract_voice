"""特殊内容 profile 与稳定选择 key 的行为测试。"""

from __future__ import annotations

from lol_audio_unpack.app.special_content import (
    build_special_content_item,
    get_special_content_profile,
    is_structured_special_champion,
    merge_champion_ids,
    resolve_special_target_ids,
)
from lol_audio_unpack.app.targets import filter_default_visible_champions, should_hide_champion_by_default


def test_structured_special_profile_uses_alias_or_wad_basename() -> None:
    """特殊目录分类应同时识别 alias 与根 WAD 技术前缀。"""
    ruby = {
        "id": 66600,
        "alias": "Ruby_Urgot",
        "wad": {"root": "Game/DATA/FINAL/Champions/Ruby_Urgot.wad.client"},
    }
    jade_from_wad = {
        "id": 60001,
        "alias": "Annie",
        "wad": {"root": "Game/DATA/FINAL/Champions/Jade_Annie.wad.client"},
    }

    assert get_special_content_profile(ruby).mode_key == "doom_bots"
    assert get_special_content_profile(jade_from_wad).mode_key == "legacy_champions"
    assert is_structured_special_champion(ruby) is True
    assert is_structured_special_champion(jade_from_wad) is True


def test_special_item_uses_localized_name_or_base_alias_and_searches_raw_identity() -> None:
    """特殊项展示不泄露技术前缀，但搜索保留原始可发现性。"""
    item = build_special_content_item(
        {
            "id": 77701,
            "alias": "Strawberry_Jinx",
            "wad": {"root": "Champions/Strawberry_Jinx.wad.client"},
        },
        display_name="",
    )

    assert item is not None
    assert item.key == "champion:77701"
    assert item.profile.display_name == "无尽狂潮"
    assert item.display_name == "Jinx"
    assert item.standalone_name == "无尽狂潮 · Jinx"
    assert all(term in item.search_text for term in ("swarm", "strawberry_jinx", "champion:77701"))


def test_special_item_uses_wad_basename_for_base_alias_fallback() -> None:
    """只有 WAD 技术前缀时仍能恢复去前缀的可见名称。"""
    item = build_special_content_item(
        {
            "id": 66601,
            "wad": {"root": "Assets/Champions/Ruby_Urgot.wad.client"},
        }
    )

    assert item is not None
    assert item.base_alias == "Urgot"
    assert item.display_name == "Urgot"
    assert item.internal_alias == "Ruby_Urgot"
    assert "ruby_urgot" in item.search_text


def test_special_item_uses_approved_mode_and_localized_display_names() -> None:
    """Ruby 与 Strawberry 的目录名和独立展示应使用批准的中文规则。"""
    ruby = build_special_content_item(
        {"id": 66600, "alias": "Ruby_Urgot", "wad": {"root": "Champions/Ruby_Urgot.wad.client"}},
        display_name="厄加特",
    )
    strawberry = build_special_content_item(
        {
            "id": 77702,
            "alias": "Strawberry_Jinx",
            "wad": {"root": "Champions/Strawberry_Jinx.wad.client"},
        },
        display_name="金克丝",
    )

    assert ruby is not None
    assert strawberry is not None
    assert (ruby.profile.display_name, ruby.display_name, ruby.standalone_name) == (
        "末日人机",
        "厄加特",
        "末日人机 · 厄加特",
    )
    assert (strawberry.profile.display_name, strawberry.display_name, strawberry.standalone_name) == (
        "无尽狂潮",
        "金克丝",
        "无尽狂潮 · 金克丝",
    )


def test_special_target_round_trip_merges_with_ordinary_champion_ids() -> None:
    """运行层应归约 stable key，同时保持普通 ID 顺序去重。"""
    targets = ("champion:66600", "champion:222", "champion:66600")

    assert resolve_special_target_ids(targets) == (66600, 222)
    assert merge_champion_ids((1, 66600), targets) == (1, 66600, 222)


def test_strawberry_is_hidden_by_default_but_stable_key_stays_explicitly_resolvable() -> None:
    """默认批量排除 Strawberry，不能阻断特殊目录的显式选择。"""
    ordinary = {"id": 1, "alias": "Annie", "wad": {"root": "Champions/Annie.wad.client"}}
    strawberry = {
        "id": 77702,
        "alias": "Strawberry_Jinx",
        "wad": {"root": "Champions/Strawberry_Jinx.wad.client"},
    }

    assert should_hide_champion_by_default(strawberry) is True
    assert filter_default_visible_champions([ordinary, strawberry]) == [ordinary]
    assert resolve_special_target_ids(("champion:77702",)) == (77702,)
