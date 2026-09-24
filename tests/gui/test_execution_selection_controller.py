from __future__ import annotations

from lol_audio_unpack.gui.controllers.execution_selection import (
    ExecutionSelectionController,
)


def test_execution_selection_controller_merge_keeps_order_and_deduplicates() -> None:
    controller = ExecutionSelectionController()

    result = controller.resolve_selection_update(
        current_champion_ids=("1", "103"),
        current_map_ids=("11",),
        incoming_champion_ids=("103", "222"),
        incoming_map_ids=("11", "12"),
        source="overview_selection",
        summary="未提供摘要",
        resolution="merge",
    )

    assert result is not None
    assert result.champion_ids == ("1", "103", "222")
    assert result.map_ids == ("11", "12")
    assert result.modes == ("ids", "ids")
    assert result.source == "overview_selection"


def test_execution_selection_controller_replace_builds_default_summary_when_missing() -> None:
    controller = ExecutionSelectionController()

    result = controller.resolve_selection_update(
        current_champion_ids=(),
        current_map_ids=(),
        incoming_champion_ids=("1", "103"),
        incoming_map_ids=("11",),
        source="overview_selection",
        summary="未提供摘要",
        resolution=None,
    )

    assert result is not None
    assert result.champion_ids == ("1", "103")
    assert result.map_ids == ("11",)
    assert result.modes == ("ids", "ids")
    assert result.summary


def test_execution_selection_controller_cancel_returns_none() -> None:
    controller = ExecutionSelectionController()

    result = controller.resolve_selection_update(
        current_champion_ids=("1",),
        current_map_ids=("11",),
        incoming_champion_ids=("103",),
        incoming_map_ids=("12",),
        source="overview_selection",
        summary="未提供摘要",
        resolution="cancel",
    )

    assert result is None


def test_merge_preserves_all_but_replace_uses_incoming_ids() -> None:
    """模式也是冲突的一部分，合并全部与指定时不缩小原范围。"""
    controller = ExecutionSelectionController()
    kwargs = dict(
        current_champion_ids=(),
        current_map_ids=(),
        current_modes=("all", "none"),
        incoming_champion_ids=("1",),
        incoming_map_ids=(),
        source="overview_selection",
        summary="",
    )
    assert controller.resolve_selection_update(**kwargs, resolution="cancel") is None
    merged = controller.resolve_selection_update(**kwargs, resolution="merge")
    assert merged.modes == ("all", "none") and merged.champion_ids == ()
    replaced = controller.resolve_selection_update(**kwargs, resolution="replace")
    assert replaced.modes == ("ids", "none") and replaced.champion_ids == ("1",)


def test_execution_selection_controller_detects_conflict_only_when_targets_differ() -> None:
    controller = ExecutionSelectionController()

    assert (
        controller.has_conflict(
            current_champion_ids=("1",),
            current_map_ids=("11",),
            incoming_champion_ids=("103",),
            incoming_map_ids=("11",),
        )
        is True
    )
    assert (
        controller.has_conflict(
            current_champion_ids=("1",),
            current_map_ids=("11",),
            incoming_champion_ids=("1",),
            incoming_map_ids=("11",),
        )
        is False
    )


def test_execution_selection_controller_merges_special_targets_without_exposing_key_as_name() -> None:
    """特殊内容缺少历史展示名时，合并结果不能把稳定 key 显示给用户。"""
    controller = ExecutionSelectionController()

    result = controller.resolve_selection_update(
        current_champion_ids=(),
        current_map_ids=(),
        incoming_champion_ids=(),
        incoming_map_ids=(),
        current_special_targets=("champion:66600",),
        incoming_special_targets=("champion:77702",),
        current_special_target_names=(),
        incoming_special_target_names=("无尽狂潮 · 金克丝",),
        source="overview_selection",
        summary="未提供摘要",
        resolution="merge",
    )

    assert result is not None
    assert result.special_targets == ("champion:66600", "champion:77702")
    assert result.special_target_names == ("特殊内容", "无尽狂潮 · 金克丝")
