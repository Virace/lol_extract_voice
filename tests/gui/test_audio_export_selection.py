"""验证事件树与全部音频共享选择，筛选不会改写节点范围。"""

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.app.audio_export import AudioExportRequest, ExportTarget
from lol_audio_unpack.app.audio_scope import AudioScope, MappingNode
from lol_audio_unpack.app.audio_selection import AudioSelection
from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.gui.components.preview_tree import PreviewTreeModel, collect_tree_stats
from lol_audio_unpack.gui.controllers.audio_export import AudioExportController
from lol_audio_unpack.gui.view.overview.audio_preview_panel import OverviewAudioPreviewPanel


@pytest.fixture
def export_preview(qtbot, tmp_path: Path):
    """构造带有事件分组、缺失引用和平铺列表的真实选择界面。"""
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)
    root = tmp_path / "audios"
    refs = tuple(AudioRef(f"VO/{key}.wem", root / f"VO/{key}.wem", key, "VO", "1000") for key in ("1", "2", "3"))
    mapping = {
        "skins": {
            "1000": {
                "events": {"VO": {"a": ["1", "2"], "b": ["3"], "missing": ["4"]}},
                "audioPaths": {
                    "VO": {
                        "a": [ref.relative_path for ref in refs[:2]],
                        "b": [refs[2].relative_path],
                        "missing": ["VO/4.wem"],
                    }
                },
            }
        }
    }
    controller = AudioExportController(panel.export_bar, panel.audio_preview_tree, panel.audio_list, parent=panel)
    controller.configure(
        AudioExportRequest(
            entity_type="champions",
            entity_id="1",
            entity_name="安妮",
            version="16.17",
            version_root=root,
            targets=(ExportTarget(AudioScope(root), tmp_path / "wavs"),),
            report_root=tmp_path / "reports",
            options=WavOutputOptions(enabled=True),
        )
    )
    panel.audio_preview_tree.setAnimated(False)
    panel.set_preview_data(mapping_data=mapping, audio_refs=refs, group_label_map=None, summary_text="")
    panel.audio_list.set_audio_refs(refs)
    controller.set_available(refs, complete=False)
    panel.resize(800, 600)
    panel.show()
    return panel, controller, refs


def _click_row(qtbot, view, index, *, ctrl: bool = True) -> None:
    """在行正文点击，避开播放按钮、树箭头与行末复选框。"""
    view.scrollTo(index)
    qtbot.mouseClick(
        view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,
        pos=QPoint(view.viewport().width() // 2, view.visualRect(index).center().y()),
    )


@pytest.mark.parametrize("surface", ["events", "leaves", "all_audio"])
@pytest.mark.parametrize("first_ctrl", [False, True])
def test_ctrl_second_item_enters_export_with_both_ranges(qtbot, export_preview, surface, first_ctrl) -> None:
    """真实 Ctrl 手势带入前后完整范围，后续可取消并与另一种视图共享选择。"""
    panel, controller, refs = export_preview
    if surface == "all_audio":
        view = panel.audio_list
        panel.preview_stack.setCurrentWidget(view)
        first, second = (view.model().index(row, 0) for row in range(2))
        expected = refs[:2]
    else:
        view = panel.audio_preview_tree
        model = view.model()
        root = model.index(0, 0)
        kind = model.index(0, 0, root)
        view.expand(kind)
        first, second = (model.index(row, 0, kind) for row in range(2))
        expected = refs
        if surface == "leaves":
            view.expand(first)
            first, second = (model.index(row, 0, first) for row in range(2))
            expected = refs[:2]

    _click_row(qtbot, view, first, ctrl=first_ctrl)
    assert not panel.export_bar.active
    assert controller.selection.count == 0
    with qtbot.waitSignal(controller.index_requested):
        _click_row(qtbot, view, second)
    assert panel.export_bar.active
    assert panel.export_bar.export_button.isEnabled()
    assert controller.selection.count == len(expected)
    assert all(controller.selection.contains(ref.path) for ref in expected)
    for row, ref in enumerate(refs):
        state = panel.audio_list.model().index(row, 0).data(Qt.ItemDataRole.CheckStateRole)
        assert (state == Qt.CheckState.Checked) == (ref in expected)

    _click_row(qtbot, view, first, ctrl=False)
    assert controller.selection.count == len(expected)
    panel.export_bar.only_selected.setChecked(True)
    _click_row(qtbot, view, second)
    assert not controller.selection.contains(expected[-1].path)
    controller.undo()
    assert controller.selection.count == len(expected)
    controller.toggle_mode()
    assert not panel.export_bar.active
    assert controller.selection.count == len(expected)


def test_ctrl_missing_event_does_not_enter_export(qtbot, export_preview) -> None:
    """缺失节点不能触发自动选择，普通单击也不会进入选择模式。"""
    panel, controller, _refs = export_preview
    view = panel.audio_preview_tree
    model = view.model()
    kind = model.index(0, 0, model.index(0, 0))
    view.expand(kind)
    first, second, missing = (model.index(row, 0, kind) for row in range(3))
    _click_row(qtbot, view, first, ctrl=False)
    _click_row(qtbot, view, second, ctrl=False)
    assert not panel.export_bar.active
    _click_row(qtbot, view, second)
    assert not panel.export_bar.active
    _click_row(qtbot, view, second, ctrl=False)
    _click_row(qtbot, view, missing)
    assert not panel.export_bar.active
    assert controller.selection.count == 0
    _click_row(qtbot, view, first)
    assert not panel.export_bar.active


@pytest.mark.parametrize("surface", ["events", "all_audio"])
def test_ctrl_play_button_preserves_playback_action(qtbot, export_preview, surface) -> None:
    """Ctrl 点击播放按钮仍触发试听，不把播放动作转换成导出勾选。"""
    panel, controller, refs = export_preview
    if surface == "all_audio":
        view = panel.audio_list
        panel.preview_stack.setCurrentWidget(view)
        first, second = (view.model().index(row, 0) for row in range(2))
        position = view.audio_control_rect(second).center()
    else:
        view = panel.audio_preview_tree
        model = view.model()
        kind = model.index(0, 0, model.index(0, 0))
        view.expand(kind)
        event = model.index(0, 0, kind)
        view.expand(event)
        first, second = (model.index(row, 0, event) for row in range(2))
        position = view._audio_control_rect_for_index(second).center()
    _click_row(qtbot, view, first, ctrl=False)
    with qtbot.waitSignal(view.audio_ref_toggle_requested) as playback:
        qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, pos=position)
    assert playback.args == [refs[1]]
    assert not panel.export_bar.active
    assert controller.selection.count == 0


@pytest.mark.parametrize("initial", ["empty", "old_selection", "navigation_focus"])
@pytest.mark.parametrize("exact_paths", [False, True])
def test_ctrl_selects_only_clicked_events_with_shared_audio(qtbot, export_preview, initial, exact_paths) -> None:
    """旧范围、导航焦点和共享文件都不能把未点击事件纳入 Ctrl 选择。"""
    panel, controller, refs = export_preview
    mapping = {
        "skins": {
            "1000": {
                "events": {"VO": {"a": ["1"], "b": ["2"], "shared": ["2"], "other": ["3"]}},
                "audioPaths": {
                    "VO": {
                        name: [refs[row].relative_path]
                        for name, row in (("a", 0), ("b", 1), ("shared", 1), ("other", 2))
                    }
                },
            }
        }
    }
    if not exact_paths:
        del mapping["skins"]["1000"]["audioPaths"]
    panel.set_preview_data(mapping_data=mapping, audio_refs=refs, group_label_map=None, summary_text="")
    view = panel.audio_preview_tree
    model = view.model()
    root = model.index(0, 0)
    kind = model.index(0, 0, root)
    view.expand(kind)
    first, second, shared, other = (model.index(row, 0, kind) for row in range(4))
    if initial == "old_selection":
        controller.select_all()
    if initial == "navigation_focus":
        view.setCurrentIndex(kind)
    _click_row(qtbot, view, first)
    assert not controller.mode
    _click_row(qtbot, view, second)
    assert controller.selection.count == len(refs[:2])
    assert first.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert second.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert shared.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert other.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert kind.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.PartiallyChecked

    _click_row(qtbot, view, shared)
    _click_row(qtbot, view, second)
    assert second.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert shared.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert controller.selection.count == len(refs[:2])
    (scope,) = controller.selection.build_scopes((controller.request.targets[0].scope.root,))
    assert set(scope.resolve_files()) == {ref.path for ref in refs[:2]}

    controller.undo()
    assert second.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert shared.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    model.setData(kind, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    _click_row(qtbot, view, second)
    assert second.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert shared.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert controller.selection.count == len(refs)
    panel.export_bar.only_selected.setChecked(True)
    assert view.isRowHidden(second.row(), kind)
    assert not view.isRowHidden(shared.row(), kind)

    # 搜索重建树后仍按事件身份恢复，未显示事件的选择继续留在导出范围内。
    filtered = {"skins": {"1000": {"events": {"VO": {"a": ["1"], "b": ["2"]}}}}}
    panel.set_preview_data(
        mapping_data=filtered, audio_refs=refs, group_label_map=None, summary_text="", selection_mapping=mapping
    )
    kind = model.index(0, 0, model.index(0, 0))
    view.expand(kind)
    first, second = (model.index(row, 0, kind) for row in range(2))
    assert first.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert second.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert kind.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.PartiallyChecked
    assert controller.selection.count == len(refs)


def test_parent_selection_uses_full_mapping_and_disables_missing(qtbot, tmp_path: Path) -> None:
    """搜索后的父节点仍选择完整可用范围，缺失叶子可见但不能勾选。"""
    refs = tuple(
        AudioRef(key, tmp_path / key, Path(key).stem, "VO", "1000") for key in ("1000/VO/1.wem", "1001/VO/1.wem")
    )
    for ref in refs:
        ref.path.parent.mkdir(parents=True, exist_ok=True)
        ref.path.write_bytes(b"wem")
    full = {
        "skins": {
            "1000": {
                "events": {"VO": {"a": ["1", "2"], "b": ["1"]}},
                "audioPaths": {"VO": {"a": [refs[0].relative_path], "b": [refs[1].relative_path]}},
            }
        }
    }
    filtered = {
        "skins": {"1000": {"events": {"VO": {"a": ["1", "2"]}}, "audioPaths": {"VO": {"a": [refs[0].relative_path]}}}}
    }
    selection = AudioSelection()
    selection.set_available(ref.path for ref in refs)
    model = PreviewTreeModel()
    model.audio_selection = selection
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(full), encoding="utf-8")
    stat = mapping_path.stat()
    model.mapping_source = MappingNode(mapping_path, "champions", "1", (stat.st_size, stat.st_mtime_ns))
    model.selection_mode = True
    model.set_preview_data(filtered, refs, selection_mapping=full)
    root = model.index(0, 0)
    assert model.rowCount(root) == 0
    assert model.setData(root, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert selection.count == len(refs)
    (scope,) = selection.build_scopes((tmp_path,))
    assert set(scope.resolve_files()) == {ref.path for ref in refs}
    assert model.data(root, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    model.ensure_children_loaded(root)
    kind = model.index(0, 0, root)
    model.ensure_children_loaded(kind)
    event = model.index(0, 0, kind)
    model.ensure_children_loaded(event)
    leaf, missing = (model.index(row, 0, event) for row in range(2))
    assert not model.flags(missing) & Qt.ItemFlag.ItemIsUserCheckable
    assert not model.setData(missing, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    model.setData(leaf, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    assert selection.count == 1
    (scope,) = selection.build_scopes((tmp_path,))
    assert scope.resolve_files() == (refs[1].path,)
    assert model.data(root, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.PartiallyChecked
    selection.undo()
    assert model.data(root, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked


def test_same_id_missing_path_remains_visible_and_is_not_selected(qtbot, tmp_path: Path) -> None:
    """同 ID 的一个可用路径不能掩盖另一个缺失路径。"""
    ref = AudioRef("1000/VO/1.wem", tmp_path / "1.wem", "1", "VO", "1000")
    mapping = {
        "skins": {
            "1000": {
                "events": {"VO": {"play": ["1"]}},
                "audioPaths": {"VO": {"play": [ref.relative_path, "1001/VO/1.wem"]}},
            }
        }
    }
    stats = collect_tree_stats(mapping, (ref,))
    assert (stats.available_audio_id_count, stats.unavailable_audio_count) == (1, 1)
    selection = AudioSelection()
    selection.set_available((ref.path,))
    model = PreviewTreeModel()
    model.audio_selection = selection
    model.selection_mode = True
    model.set_preview_data(mapping, (ref,))
    root = model.index(0, 0)
    assert model.setData(root, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert selection.count == 1
    parent = root
    for _ in range(2):
        model.ensure_children_loaded(parent)
        parent = model.index(0, 0, parent)
    model.ensure_children_loaded(parent)
    assert model.rowCount(parent) == len(mapping["skins"]["1000"]["audioPaths"]["VO"]["play"])
    missing = model.index(1, 0, parent)
    assert not model.flags(missing) & Qt.ItemFlag.ItemIsUserCheckable
    assert not model.setData(missing, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)


def test_export_footer_keeps_file_total_unknown_until_directory_index_completes(qtbot, tmp_path: Path) -> None:
    """目录索引未完成时底部只报告已确认文件，完成后才显示全目录总数。"""
    panel = OverviewAudioPreviewPanel(summary_placeholder="等待事件数据。")
    qtbot.addWidget(panel)
    root = tmp_path / "16.17" / "champions" / "1"
    root.mkdir(parents=True)
    request = AudioExportRequest(
        entity_type="champions",
        entity_id="1",
        entity_name="安妮",
        version="16.17",
        version_root=tmp_path / "16.17",
        targets=(ExportTarget(AudioScope(root), tmp_path / "wavs"),),
        report_root=tmp_path / "reports",
        options=WavOutputOptions(enabled=True),
    )
    refs = (
        AudioRef("VO/1.wem", root / "VO/1.wem", "1", "VO", "1"),
        AudioRef("VO/2.wem", root / "VO/2.wem", "2", "VO", "1"),
    )
    controller = AudioExportController(panel.export_bar, panel.audio_preview_tree, panel.audio_list)
    controller.configure(request)
    controller.set_available(refs, complete=False)

    assert panel.export_bar.selection_count.text() == "已选 0 个文件 · 目录总数待确认"
    controller.toggle_mode()
    assert "/ 2 个文件" not in panel.export_bar.selection_count.text()

    controller.set_index_error()
    assert "索引失败" in panel.export_bar.selection_count.text()
    assert "/ 2 个文件" not in panel.export_bar.selection_count.text()

    controller.set_available(refs, complete=True)
    assert panel.export_bar.selection_count.text() == "已选 0 / 2 个文件"
    controller.select_all()
    assert panel.export_bar.selection_count.text() == "已选 2 / 2 个文件"
