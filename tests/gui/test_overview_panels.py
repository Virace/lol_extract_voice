"""总览页子面板的最小回归测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

import lol_audio_unpack.gui.service.data_loader as data_loader_module
from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.app.resource_pack import ResourcePackWadRef, build_resource_pack_key
from lol_audio_unpack.gui.components.preview_tree import (
    extract_preview_modifiers,
    extract_tree_groups,
    filter_preview_mapping_data,
)
from lol_audio_unpack.gui.components.special_content_tree import SpecialContentTreeView
from lol_audio_unpack.gui.controllers.contracts import OverviewSelectionSyncRequest
from lol_audio_unpack.gui.controllers.overview_preview import OverviewPreviewController
from lol_audio_unpack.gui.view.overview.audio_preview_panel import OverviewAudioPreviewPanel
from lol_audio_unpack.gui.view.overview.entity_list_panel import OverviewEntityListPanel
from lol_audio_unpack.gui.view.overview.preview_panel import OverviewPreviewPanel
from lol_audio_unpack.manager.errors import SharedDataMissingError


def _make_special_row(
    *,
    key: str,
    mode_key: str,
    name: str,
    group_name: str,
) -> dict:
    """构造特殊内容树行为测试使用的最小行。"""
    return {
        "id": key.partition(":")[2],
        "key": key,
        "name": name,
        "display_name": f"{group_name} · {name}",
        "mode_key": mode_key,
        "audio": "未准备",
        "mapping": "未准备",
        "search_text": f"{group_name} {name} {key}".casefold(),
    }


MATCHED_AUDIO_IDS = 2


def test_overview_entity_list_panel_switches_current_entity_type(qtbot) -> None:
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)

    assert panel.current_entity_type() == "champions"
    assert panel.current_list() is panel.entity_lists["champions"]

    panel.set_current_entity_type("maps")
    panel.set_selection_actions_enabled(True)

    assert panel.current_entity_type() == "maps"
    assert panel.current_list() is panel.entity_lists["maps"]
    assert panel.clear_selection_btn.isEnabled() is True
    assert panel.sync_selection_btn.isEnabled() is True
    panel.set_selection_counts(champion_count=2, map_count=1, special_count=0)
    assert panel.selection_status_label.text() == "已选：2 英雄 · 1 地图 · 0 特殊内容"


def test_overview_entity_list_panel_filters_and_finds_entity_ids(qtbot) -> None:
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)
    panel.set_rows(
        "champions",
        [
            {"id": 1, "name": "Annie", "alias": "annie"},
            {"id": 103, "name": "Ahri", "alias": "ahri"},
        ],
    )

    visible_count = panel.apply_keyword_and_restore(
        entity_type="champions",
        keyword="ann",
        selected_ids={"1"},
        current_entity_id="1",
    )
    index = panel.find_index_by_entity_id("champions", "1")

    assert visible_count == 1
    assert index.isValid() is True
    assert panel.current_list().selected_entity_ids() == {"1"}
    assert panel.selected_entity_ids("champions") == {"1"}
    assert panel.resolve_row_payload(index) == {"id": 1, "name": "Annie", "alias": "annie"}


def test_overview_entity_list_panel_can_clear_selection_state(qtbot) -> None:
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)
    panel.set_rows(
        "champions",
        [
            {"id": 1, "name": "Annie", "alias": "annie"},
            {"id": 103, "name": "Ahri", "alias": "ahri"},
        ],
    )
    panel.apply_keyword_and_restore(
        entity_type="champions",
        keyword="",
        selected_ids={"1"},
        current_entity_id="1",
    )

    panel.clear_selection("champions")

    assert panel.selected_entity_ids("champions") == set()
    assert panel.current_list().currentIndex().isValid() is False


def test_overview_entity_list_panel_can_build_selection_sync_request(qtbot) -> None:
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)

    payload = panel.build_selection_sync_request(
        selected_champion_ids={"103", "1"},
        selected_map_ids={"11"},
        selected_special_targets={"champion:66600"},
        special_target_names={"champion:66600": "末日人机 · 厄加特"},
    )

    assert payload == OverviewSelectionSyncRequest(
        source="overview_selection",
        champion_ids=(1, 103),
        map_ids=(11,),
        summary="已选择 2 个英雄、1 张地图、1 个特殊内容，请前往执行中心继续创建任务。",
        special_targets=("champion:66600",),
        special_target_names=("末日人机 · 厄加特",),
    )


def test_special_content_tree_keeps_one_level_groups_and_restores_expansion_after_search(qtbot) -> None:
    """特殊目录分组不可选，搜索和数据刷新不应丢失会话展开状态。"""
    tree = SpecialContentTreeView()
    qtbot.addWidget(tree)
    rows = [
        _make_special_row(
            key="champion:60001",
            mode_key="legacy_champions",
            name="安妮",
            group_name="旧版英雄",
        ),
        _make_special_row(
            key="champion:66600",
            mode_key="doom_bots",
            name="厄加特",
            group_name="末日人机",
        ),
        _make_special_row(
            key="champion:77702",
            mode_key="swarm",
            name="金克丝",
            group_name="无尽狂潮",
        ),
    ]

    tree.set_rows(rows)
    model = tree.model()
    legacy_group = model.index(0, 0)
    doom_group = model.index(1, 0)
    assert [model.index(row, 0).data() for row in range(model.rowCount())] == [
        "旧版英雄 (1)",
        "末日人机 (1)",
        "无尽狂潮 (1)",
    ]
    assert not bool(legacy_group.flags() & Qt.ItemFlag.ItemIsSelectable)
    assert legacy_group.data(Qt.ItemDataRole.AccessibleTextRole) == "旧版英雄，1 项"
    assert "可展开或折叠" in legacy_group.data(Qt.ItemDataRole.AccessibleDescriptionRole)
    assert tree.isExpanded(doom_group) is True

    tree.collapseAll()
    tree.set_rows(rows)
    assert tree.expanded_mode_keys() == set()

    tree.set_keyword("末日人机")
    assert tree.visible_row_count() == 1
    assert tree.isExpanded(tree.model().index(0, 0)) is True
    tree.set_keyword("")
    assert tree.expanded_mode_keys() == set()


def test_special_content_tree_clear_then_reload_restores_default_expansion(qtbot) -> None:
    """数据清空后的重新加载应回到 profile 默认展开，而非沿用空模型状态。"""
    tree = SpecialContentTreeView()
    qtbot.addWidget(tree)
    rows = [
        _make_special_row(
            key="champion:60001",
            mode_key="legacy_champions",
            name="安妮",
            group_name="旧版英雄",
        ),
        _make_special_row(
            key="champion:66600",
            mode_key="doom_bots",
            name="厄加特",
            group_name="末日人机",
        ),
        _make_special_row(
            key="champion:77702",
            mode_key="swarm",
            name="金克丝",
            group_name="无尽狂潮",
        ),
    ]

    tree.set_rows(rows)
    tree.set_rows([])
    tree.set_rows(rows)

    assert tree.expanded_mode_keys() == {"doom_bots", "swarm"}


def test_special_content_tree_keeps_hidden_search_selection_state_restorable(qtbot) -> None:
    """搜索中刷新时，隐藏的 special key 不得被视为已删除。"""
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)
    rows = [
        _make_special_row(
            key="champion:66600",
            mode_key="doom_bots",
            name="厄加特",
            group_name="末日人机",
        ),
        _make_special_row(
            key="champion:77702",
            mode_key="swarm",
            name="金克丝",
            group_name="无尽狂潮",
        ),
    ]
    selected_ids = {"champion:66600", "champion:77702"}
    panel.set_rows("special", rows)
    panel.apply_keyword_and_restore(
        entity_type="special",
        keyword="",
        selected_ids=selected_ids,
        current_entity_id="champion:77702",
    )

    panel.apply_keyword_and_restore(
        entity_type="special",
        keyword="末日人机",
        selected_ids=selected_ids,
        current_entity_id="champion:77702",
    )
    special_tree = panel.entity_lists["special"]
    assert special_tree.entity_ids() == selected_ids

    panel.set_rows("special", rows)
    panel.apply_keyword_and_restore(
        entity_type="special",
        keyword="末日人机",
        selected_ids=selected_ids,
        current_entity_id="champion:77702",
    )
    panel.apply_keyword_and_restore(
        entity_type="special",
        keyword="",
        selected_ids=selected_ids,
        current_entity_id="champion:77702",
    )

    assert special_tree.selected_entity_ids() == selected_ids
    assert special_tree.currentIndex().data(Qt.ItemDataRole.UserRole)["key"] == "champion:77702"


def test_special_content_tree_disables_selection_until_shared_data_is_ready(qtbot) -> None:
    """共享数据未就绪时特殊目录可浏览但不可选择。"""
    tree = SpecialContentTreeView()
    qtbot.addWidget(tree)
    tree.set_rows(
        [
            _make_special_row(
                key="champion:66600",
                mode_key="doom_bots",
                name="厄加特",
                group_name="末日人机",
            )
        ]
    )
    tree.set_interaction_enabled(False)
    group = tree.model().index(0, 0)
    item = tree.model().index(0, 0, group)

    assert not bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)
    assert tree.toolTip() == "共享数据就绪后可选择特殊内容。"


def test_resource_pack_catalog_uses_safe_display_name_and_selectable_snapshot(monkeypatch, tmp_path: Path) -> None:
    """资源包行使用本地化基础别名，并携带可发送的 WAD snapshot。"""
    key = build_resource_pack_key("Ruby_Urgot.wad.client", "MODE_DOOM_BOTS_SFX")
    wad_path = tmp_path / "Game" / "DATA" / "FINAL" / "Ruby_Urgot.wad.client"
    wad_path.parent.mkdir(parents=True)
    wad_path.write_bytes(b"selected wad")
    ref = ResourcePackWadRef.from_path(tmp_path, wad_path)
    loader = data_loader_module.EntityDataLoader.__new__(data_loader_module.EntityDataLoader)
    loader.ctx = SimpleNamespace(config=SimpleNamespace(game_path=tmp_path), game_region="zh_CN")
    loader.data_reader = SimpleNamespace(version="16.16")
    monkeypatch.setattr(
        loader,
        "_build_entity_data",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("未准备 banks")),
    )

    row = loader._build_resource_pack_row(
        {
            "resourcePack": {
                "key": key,
                "wad": ref.identity,
                "namespace": "MODE_DOOM_BOTS_SFX",
                "source": {"wad": ref.identity, "size": ref.size, "mtimeNs": ref.mtime_ns},
                "discovery": {"status": "complete", "candidateEntries": 2, "payloadReads": 1},
            },
            "diagnostics": {"completeness": "complete"},
        },
        "16.16",
        ordinary_names={"urgot": "厄加特"},
    )

    assert row is not None
    assert row["name"] == "厄加特 · SFX"
    assert row["mode_key"] == "doom_bots"
    assert row["resource_pack_wad"] == ref
    assert row["selectable"] is True
    assert "Ruby_Urgot" not in row["name"]


def test_resource_pack_catalog_distinguishes_namespaces_from_the_same_wad(monkeypatch, tmp_path: Path) -> None:
    """同一 WAD 的多个 BANK_UNITS category 必须有不同的目录主名称。"""
    wad_path = tmp_path / "Game" / "DATA" / "FINAL" / "TFTCommon.wad.client"
    wad_path.parent.mkdir(parents=True)
    wad_path.write_bytes(b"selected wad")
    ref = ResourcePackWadRef.from_path(tmp_path, wad_path)
    loader = data_loader_module.EntityDataLoader.__new__(data_loader_module.EntityDataLoader)
    loader.ctx = SimpleNamespace(config=SimpleNamespace(game_path=tmp_path), game_region="zh_CN")
    loader.data_reader = SimpleNamespace(version="16.16")
    monkeypatch.setattr(
        loader,
        "_build_entity_data",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("未准备 banks")),
    )

    rows = [
        loader._build_resource_pack_row(
            {
                "resourcePack": {
                    "key": build_resource_pack_key("TFTCommon.wad.client", namespace),
                    "wad": ref.identity,
                    "namespace": namespace,
                    "source": {"wad": ref.identity, "size": ref.size, "mtimeNs": ref.mtime_ns},
                }
            },
            "16.16",
        )
        for namespace in ("MODE_TFT_NPC_ELDER_DRAGON_SFX", "MODE_TFT_NPC_BARON_SFX")
    ]

    assert all(row is not None for row in rows)
    assert rows[0]["name"] != rows[1]["name"]


def test_stale_resource_pack_snapshot_is_not_selectable(monkeypatch, tmp_path: Path) -> None:
    """目录重载必须拒绝来源已变化的旧快照，避免把陈旧任务发送到执行中心。"""
    wad_path = tmp_path / "Game" / "DATA" / "FINAL" / "Legacy.wad.client"
    wad_path.parent.mkdir(parents=True)
    wad_path.write_bytes(b"old")
    ref = ResourcePackWadRef.from_path(tmp_path, wad_path)
    wad_path.write_bytes(b"new payload")

    loader = data_loader_module.EntityDataLoader.__new__(data_loader_module.EntityDataLoader)
    loader.ctx = SimpleNamespace(config=SimpleNamespace(game_path=tmp_path), game_region="zh_CN")
    loader.data_reader = SimpleNamespace(version="16.16")
    monkeypatch.setattr(
        loader,
        "_build_entity_data",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("未准备 banks")),
    )

    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")
    row = loader._build_resource_pack_row(
        {
            "resourcePack": {
                "key": key,
                "wad": ref.identity,
                "namespace": "MODE_LEGACY",
                "source": {"wad": ref.identity, "size": ref.size, "mtimeNs": ref.mtime_ns},
            }
        },
        "16.16",
    )

    assert row is not None
    assert row["resource_pack_wad"] is None
    assert row["selectable"] is False
    assert "选择快照无效" in row["tooltip"]


def test_invalid_resource_pack_snapshot_is_not_selectable_or_synced(qtbot) -> None:
    """旧 artifact 的无效 source snapshot 只能浏览，不能进入执行任务。"""
    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")
    tree = SpecialContentTreeView()
    qtbot.addWidget(tree)
    tree.set_rows(
        [
            {
                "id": key,
                "key": key,
                "name": "Legacy",
                "mode_key": "historical_resource_packs",
                "audio": "未准备",
                "mapping": "未准备",
                "search_text": key,
                "selectable": False,
            }
        ]
    )
    group = tree.model().index(0, 0)
    item = tree.model().index(0, 0, group)
    panel = OverviewEntityListPanel()
    qtbot.addWidget(panel)

    payload = panel.build_selection_sync_request(
        selected_champion_ids=set(),
        selected_map_ids=set(),
        selected_special_targets={"champion:66600", key},
        special_target_names={"champion:66600": "末日人机 · 厄加特", key: "Legacy"},
    )

    assert not bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)
    assert payload.special_targets == ("champion:66600",)
    assert payload.resource_pack_wads == ()


def test_entity_data_loader_partitions_special_rows_and_keeps_unprepared_rows(monkeypatch) -> None:
    """一次冠军扫描应分区普通/特殊，并为未准备 special 保留诚实状态。"""
    loader = data_loader_module.EntityDataLoader.__new__(data_loader_module.EntityDataLoader)
    loader.ctx = SimpleNamespace(game_region="zh_CN")
    loader.data_reader = SimpleNamespace(
        version="16.16",
        get_champions=lambda: [
            {"id": 6, "alias": "Urgot", "names": {"zh_CN": "厄加特"}},
            {"id": 222, "alias": "Jinx", "names": {"zh_CN": "金克丝"}},
            {"id": 666123, "alias": "Kaisa", "names": {"zh_CN": "卡莎"}},
            {"id": 66600, "alias": "Ruby_Urgot", "wad": {"root": "Champions/Ruby_Urgot.wad.client"}},
            {
                "id": 77702,
                "alias": "Strawberry_Jinx",
                "wad": {"root": "Champions/Strawberry_Jinx.wad.client"},
            },
        ],
    )
    monkeypatch.setattr(loader, "_ensure_bank_dataset_ready", lambda _entity_type: None)
    monkeypatch.setattr(
        loader,
        "_build_entity_row",
        lambda _entity_type, entity, _version: {"id": str(entity["id"]), "name": entity["names"]["zh_CN"]},
    )
    monkeypatch.setattr(
        loader,
        "_build_entity_data",
        lambda _entity_type, entity_id: (_ for _ in ()).throw(RuntimeError(f"banks missing: {entity_id}")),
    )

    catalog = loader.load_champion_catalog()

    assert [row["id"] for row in catalog["champions"]] == ["6", "222"]
    assert [(row["name"], row["display_name"]) for row in catalog["special"]] == [
        ("厄加特", "末日人机 · 厄加特"),
        ("金克丝", "无尽狂潮 · 金克丝"),
    ]
    assert all(row["audio"] == "未准备" and row["mapping"] == "未准备" for row in catalog["special"])
    assert "资源键: champion:66600" in catalog["special"][0]["tooltip"]


def test_entity_data_loader_default_raw_champions_preserve_hidden_marker_filter() -> None:
    """普通列表的原始加载仍复用默认隐藏策略。"""
    loader = data_loader_module.EntityDataLoader.__new__(data_loader_module.EntityDataLoader)
    loader.data_reader = SimpleNamespace(
        version="16.16",
        get_champions=lambda: [
            {"id": 6, "alias": "Urgot"},
            {"id": 666123, "alias": "Kaisa"},
            {"id": 66600, "alias": "Ruby_Urgot"},
        ],
    )

    _version, champions = loader._load_raw_entities("champions")

    assert [champion["id"] for champion in champions] == [6]


def test_entity_data_loader_incremental_champion_targets_only_build_requested_rows(monkeypatch) -> None:
    """特殊内容增量刷新只重建指定普通与特殊条目，元数据仍只读取一次。"""
    loader = data_loader_module.EntityDataLoader.__new__(data_loader_module.EntityDataLoader)
    loader.ctx = SimpleNamespace(game_region="zh_CN")
    loader.data_reader = SimpleNamespace(
        version="16.16",
        get_champions=lambda: [
            {"id": 6, "alias": "Urgot", "names": {"zh_CN": "厄加特"}},
            {"id": 222, "alias": "Jinx", "names": {"zh_CN": "金克丝"}},
            {"id": 666123, "alias": "Kaisa", "names": {"zh_CN": "卡莎"}},
            {"id": 66600, "alias": "Ruby_Urgot"},
            {"id": 77702, "alias": "Strawberry_Jinx"},
        ],
    )
    monkeypatch.setattr(loader, "_ensure_bank_dataset_ready", lambda _entity_type: None)
    built_rows: list[tuple[str, str]] = []
    monkeypatch.setattr(
        loader,
        "_build_entity_row",
        lambda entity_type, entity, _version: (
            built_rows.append((entity_type, str(entity["id"]))) or {"id": str(entity["id"]), "name": entity["alias"]}
        ),
    )
    monkeypatch.setattr(
        loader,
        "_build_special_row",
        lambda entity, _version, *, display_name: (
            built_rows.append(("special", str(entity["id"])))
            or {"id": str(entity["id"]), "key": f"champion:{entity['id']}", "name": display_name}
        ),
    )

    rows = loader.load_champion_rows_by_targets(
        champion_ids=("6", "666123"),
        special_targets=("champion:66600",),
    )

    assert built_rows == [("champions", "6"), ("special", "66600")]
    assert [row["id"] for row in rows["champions"]] == ["6"]
    assert [row["key"] for row in rows["special"]] == ["champion:66600"]


def test_entity_data_loader_incremental_resource_pack_targets_skip_champion_catalog(monkeypatch) -> None:
    """资源包完成后只读指定 artifact，且仅查询内存英雄元数据用于本地化。"""
    key = build_resource_pack_key("Ruby_Urgot.wad.client", "MODE_DOOM_BOTS_SFX")
    loader = data_loader_module.EntityDataLoader.__new__(data_loader_module.EntityDataLoader)
    calls = []
    loader.ctx = SimpleNamespace(game_region="zh_CN")
    loader.data_reader = SimpleNamespace(
        get_champions=lambda: [{"id": 6, "alias": "Urgot", "names": {"zh_CN": "厄加特"}}],
    )
    monkeypatch.setattr(
        loader,
        "load_resource_pack_rows",
        lambda keys, *, ordinary_names: (
            calls.append((keys, ordinary_names)) or [{"id": key, "key": key, "name": ordinary_names["urgot"]}]
        ),
    )
    monkeypatch.setattr(loader, "_build_entity_data", lambda *_args: pytest.fail("不应扫描英雄 A/M 状态"))

    rows = loader.load_champion_rows_by_targets(special_targets=(key,))

    assert calls == [((key,), {"urgot": "厄加特"})]
    assert rows == {"champions": [], "special": [{"id": key, "key": key, "name": "厄加特"}]}


def test_entity_data_loader_propagates_shared_bank_root_missing_error(monkeypatch) -> None:
    """共享 banks 根缺失必须上抛，交由既有自动准备和刷新回退处理。"""
    loader = data_loader_module.EntityDataLoader.__new__(data_loader_module.EntityDataLoader)
    loader.ctx = SimpleNamespace(game_region="zh_CN")
    loader.data_reader = SimpleNamespace(
        version="16.16",
        get_champions=lambda: [
            {"id": 6, "alias": "Urgot", "names": {"zh_CN": "厄加特"}},
            {"id": 66600, "alias": "Ruby_Urgot"},
        ],
    )
    monkeypatch.setattr(
        loader,
        "_ensure_bank_dataset_ready",
        lambda _entity_type: (_ for _ in ()).throw(SharedDataMissingError("共享 banks 未准备")),
    )
    with pytest.raises(SharedDataMissingError, match="共享 banks 未准备"):
        loader.load_champion_catalog()
    with pytest.raises(SharedDataMissingError, match="共享 banks 未准备"):
        loader.load_champion_rows_by_targets(special_targets=("champion:66600",))


def test_overview_preview_panel_show_placeholder_clears_preview_state(qtbot) -> None:
    panel = OverviewPreviewPanel(audio_summary_placeholder="这里会显示当前实体的事件分组。")
    qtbot.addWidget(panel)

    panel.set_preview_path("mapping.msgpack")
    panel.reveal_file_btn.setEnabled(True)
    panel.show_placeholder("请选择左侧实体。")

    assert panel.preview_path_edit.text() == ""
    assert panel.preview_path_edit.toolTip() == ""
    assert panel.text_preview.toPlainText() == "请选择左侧实体。"
    assert panel.preview_stack.currentWidget() is panel.placeholder_panel
    assert panel.reveal_file_btn.isEnabled() is False


def test_overview_preview_panel_set_preview_path_updates_text_and_tooltip(qtbot) -> None:
    panel = OverviewPreviewPanel(audio_summary_placeholder="这里会显示当前实体的事件分组。")
    qtbot.addWidget(panel)

    panel.set_preview_path("mapping.msgpack")

    assert panel.preview_path_edit.text() == "mapping.msgpack"
    assert panel.preview_path_edit.toolTip() == "mapping.msgpack"


def test_overview_preview_panel_exposes_named_audio_preview_controls(qtbot) -> None:
    """路径级试听控件应提供稳定的辅助功能名称。"""
    panel = OverviewPreviewPanel(audio_summary_placeholder="这里会显示当前实体的事件分组。")
    qtbot.addWidget(panel)

    assert panel.preview_mode_pivot.accessibleName() == "预览模式切换"
    assert panel.preview_search_input.accessibleName() == "预览搜索"
    assert panel.preview_path_edit.accessibleName() == "预览资源路径"
    assert panel.reveal_file_btn.accessibleName() == "打开当前预览资源位置"
    assert panel.audio_preview_panel.audio_preview_tree.accessibleName() == "事件音频树"
    assert panel.audio_preview_panel.audio_list.accessibleName() == "全部音频列表"
    assert panel.text_preview.accessibleName() == "原始映射数据"


def test_overview_audio_preview_panel_can_reset_summary(qtbot) -> None:
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)

    panel.set_summary_text("分组 1 · 类型 2 · 事件 3")
    panel.reset_summary()

    assert panel.summary_label.text() == "等待事件数据。"


def test_overview_audio_preview_panel_can_set_preview_data_and_playback_state(qtbot) -> None:
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)
    expected_progress = 0.25

    panel.set_preview_data(
        mapping_data={"skins": {"1000": {"events": {}}}},
        audio_refs=(),
        group_label_map={"1000": "经典"},
        summary_text="分组 1 · 类型 0 · 事件 0",
    )
    panel.set_playback_state(
        Path("1001.wem"),
        progress=expected_progress,
        is_playing=False,
        is_paused=True,
    )

    assert panel.summary_label.text() == "分组 1 · 类型 0 · 事件 0"
    assert panel.audio_list.active_progress == expected_progress
    assert panel.audio_list.is_playing is False
    assert panel.audio_list.is_paused is True


def test_overview_audio_preview_panel_expands_single_root_by_default(qtbot) -> None:
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)

    panel.set_preview_data(
        mapping_data={"map": {"0": {"events": {"NPC_Map0_VO": {"Play_map0_intro": ["1001"]}}}}},
        audio_refs=(AudioRef("VO/1001.wem", Path("VO/1001.wem"), "1001", "VO", "0"),),
        group_label_map={"0": "常规"},
        summary_text="分组 1 · 类型 1 · 事件 1",
    )

    root_index = panel.audio_preview_tree.model().index(0, 0)

    assert panel.audio_preview_tree.isExpanded(root_index) is True


def test_overview_audio_preview_panel_keeps_multiple_roots_collapsed_by_default(qtbot) -> None:
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)

    panel.set_preview_data(
        mapping_data={
            "skins": {
                "1000": {"events": {"XinZhao_Base_VO": {"Play_base_intro": ["1001"]}}},
                "1001": {"events": {"XinZhao_Skin_VO": {"Play_skin_intro": ["1002"]}}},
            }
        },
        audio_refs=(
            AudioRef("1000/VO/1001.wem", Path("1000/VO/1001.wem"), "1001", "VO", "1000"),
            AudioRef("1001/VO/1002.wem", Path("1001/VO/1002.wem"), "1002", "VO", "1001"),
        ),
        group_label_map={"1000": "经典", "1001": "屠龙勇士"},
        summary_text="分组 2 · 类型 2 · 事件 2",
    )

    first_root_index = panel.audio_preview_tree.model().index(0, 0)
    second_root_index = panel.audio_preview_tree.model().index(1, 0)

    assert panel.audio_preview_tree.isExpanded(first_root_index) is False
    assert panel.audio_preview_tree.isExpanded(second_root_index) is False


def test_filter_preview_mapping_data_keeps_full_event_when_event_name_matches() -> None:
    mapping_data = {
        "skins": {
            "1000": {
                "events": {
                    "XinZhao_Base_VO": {
                        "Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"],
                        "Play_vo_XinZhao_Attack2DDragon": ["888888888"],
                    }
                }
            }
        }
    }

    result = filter_preview_mapping_data(mapping_data, "baron")
    groups = extract_tree_groups(result.mapping_data)
    events = groups["1000"]["events"]["XinZhao_Base_VO"]

    assert result.is_active is True
    assert result.matched_event_count == 1
    assert result.matched_audio_id_count == MATCHED_AUDIO_IDS
    assert events == {"Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"]}


def test_preview_tree_supports_resource_pack_mapping_root() -> None:
    """资源包 event mapping 应复用现有事件树与搜索结构。"""
    mapping_data = {
        "resourcePacks": {"resource_pack:legacy:mode": {"events": {"MODE_LEGACY_SFX": {"Play_legacy": ["1001"]}}}}
    }

    filtered = filter_preview_mapping_data(mapping_data, "legacy")

    assert extract_tree_groups(mapping_data) == mapping_data["resourcePacks"]
    assert extract_tree_groups(filtered.mapping_data)["resource_pack:legacy:mode"]["events"] == {
        "MODE_LEGACY_SFX": {"Play_legacy": ["1001"]}
    }


def test_resource_pack_preview_uses_catalog_name_for_root_label() -> None:
    """资源包试听树不应把稳定 key 作为首层可见名称。"""
    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")
    controller = OverviewPreviewController()

    labels = controller._build_preview_group_label_map(
        entity_type="resource_packs",
        entity_id=key,
        entity_name="历史资源包 · Legacy",
        mapping_data={"resourcePacks": {key: {"events": {}}}},
        loader=SimpleNamespace(),
    )

    assert labels == {key: "历史资源包 · Legacy"}


def test_filter_preview_mapping_data_keeps_only_matching_audio_id_when_id_matches() -> None:
    mapping_data = {
        "skins": {
            "1000": {
                "events": {
                    "XinZhao_Base_VO": {
                        "Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"],
                        "Play_vo_XinZhao_Attack2DDragon": ["888888888"],
                    }
                }
            }
        }
    }

    result = filter_preview_mapping_data(mapping_data, "2619")
    groups = extract_tree_groups(result.mapping_data)
    events = groups["1000"]["events"]["XinZhao_Base_VO"]

    assert result.is_active is True
    assert result.matched_event_count == 1
    assert result.matched_audio_id_count == 1
    assert events == {"Play_vo_XinZhao_Attack2DBaron": ["261984525"]}


def test_extract_preview_modifiers_collects_prefixes_and_suffixes() -> None:
    mapping_data = {
        "map": {
            "12": {
                "events": {
                    "NPC_Map12_VO": {},
                    "MUS_Map12_FirstBlood": {},
                    "ITEMS_Global": {},
                    "HUD_Global": {},
                    "ENV_Map12_SFX": {},
                }
            }
        }
    }

    result = extract_preview_modifiers(mapping_data)

    assert result.prefixes == ("ENV", "HUD", "ITEMS", "MUS", "NPC")
    assert result.suffixes == ("FirstBlood", "Global", "SFX", "VO")
    assert result.audio_types == (
        "ENV_Map12_SFX",
        "HUD_Global",
        "ITEMS_Global",
        "MUS_Map12_FirstBlood",
        "NPC_Map12_VO",
    )


def test_filter_preview_mapping_data_supports_suffix_modifier_scope() -> None:
    mapping_data = {
        "skins": {
            "1000": {
                "events": {
                    "XinZhao_Base_VO": {
                        "Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"],
                    },
                    "XinZhao_Base_SFX": {
                        "Play_sfx_XinZhao_Attack2DBaron": ["777777777"],
                    },
                }
            }
        }
    }

    result = filter_preview_mapping_data(mapping_data, "vo:baron")
    groups = extract_tree_groups(result.mapping_data)
    events = groups["1000"]["events"]

    assert result.is_active is True
    assert result.matched_event_count == 1
    assert result.matched_audio_id_count == MATCHED_AUDIO_IDS
    assert events == {
        "XinZhao_Base_VO": {
            "Play_vo_XinZhao_Attack2DBaron": ["261984525", "520515702"],
        }
    }


def test_filter_preview_mapping_data_supports_prefix_modifier_scope_without_keyword() -> None:
    mapping_data = {
        "map": {
            "12": {
                "events": {
                    "ITEMS_Global": {
                        "Play_items_shop": ["8053", "8054"],
                    },
                    "HUD_Global": {
                        "Play_hud_ping": ["9001"],
                    },
                }
            }
        }
    }

    result = filter_preview_mapping_data(mapping_data, "items:")
    groups = extract_tree_groups(result.mapping_data)
    events = groups["12"]["events"]

    assert result.is_active is True
    assert result.matched_event_count == 1
    assert result.matched_audio_id_count == MATCHED_AUDIO_IDS
    assert events == {
        "ITEMS_Global": {
            "Play_items_shop": ["8053", "8054"],
        }
    }
