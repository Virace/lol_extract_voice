"""验证事件树与全部音频共享选择，筛选不会改写节点范围。"""

from pathlib import Path

from PySide6.QtCore import Qt

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.app.audio_export import AudioExportRequest, ExportTarget
from lol_audio_unpack.app.audio_scope import AudioScope, MappingNode
from lol_audio_unpack.app.audio_selection import AudioSelection
from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.gui.components.preview_tree import PreviewTreeModel, collect_tree_stats
from lol_audio_unpack.gui.controllers.audio_export import AudioExportController
from lol_audio_unpack.gui.view.overview.audio_preview_panel import OverviewAudioPreviewPanel


def test_parent_selection_uses_full_mapping_and_disables_missing(qtbot, tmp_path: Path) -> None:
    """搜索后的父节点仍选择完整可用范围，缺失叶子可见但不能勾选。"""
    refs = tuple(
        AudioRef(key, tmp_path / key, Path(key).stem, "VO", "1000") for key in ("1000/VO/1.wem", "1001/VO/1.wem")
    )
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
    model.mapping_source = MappingNode(tmp_path / "mapping.json", "champions", "1", (0, 0))
    model.selection_mode = True
    model.set_preview_data(filtered, refs, selection_mapping=full)
    root = model.index(0, 0)
    assert model.rowCount(root) == 0
    assert model.setData(root, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert selection.count == len(refs)
    assert selection.state.nodes[0].key == ("1000",)
    assert selection.state.included == frozenset()
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
