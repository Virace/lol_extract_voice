"""测试实体总览基础试听树的 model 与 view。"""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeView

from lol_audio_unpack.gui.components.preview_tree import (
    AUDIO_AVAILABLE_ROLE,
    AUDIO_ID_ROLE,
    PreviewTreeModel,
    PreviewTreeView,
    collect_tree_stats,
)

EXPECTED_LEAF_AUDIO_ID_COUNT = 2
EXPECTED_FULL_AUDIO_TYPE_COUNT = 2
EXPECTED_FULL_EVENT_COUNT = 2
EXPECTED_FULL_AUDIO_ID_COUNT = 3
EXPECTED_FULL_AVAILABLE_AUDIO_ID_COUNT = 2
EXPECTED_ROOT_CHILD_COUNT = 2


def _find_child_index_by_label(model: PreviewTreeModel, parent_index, label: str):
    """在指定父节点下按显示文案查找子节点索引。"""
    for row in range(model.rowCount(parent_index)):
        index = model.index(row, 0, parent_index)
        if model.data(index, Qt.DisplayRole) == label:
            return index

    raise AssertionError(f"未找到子节点: {label}")


def _sample_mapping_data() -> dict:
    """返回一份最小试听树样例数据。"""
    return {
        "skins": {
            "1000": {
                "events": {
                    "Annie_Base_VO": {
                        "Play_vo_Annie_Attack2DGeneral": [118669424, 223585177],
                    },
                    "Annie_Base_SFX": {
                        "Play_sfx_Annie_AnnieQ_OnCast": [214822182],
                    },
                }
            }
        }
    }


def _sample_map_mapping_data() -> dict:
    """返回一份地图试听树样例数据。"""
    return {
        "map": {
            "11": {
                "events": {
                    "Map11_Music": {
                        "Play_map_theme": [7654321, 7654322],
                    }
                }
            }
        }
    }


def test_collect_audio_preview_stats_counts_full_tree() -> None:
    """统计信息应覆盖完整 mapping 树，而不是只统计已展开节点。"""
    stats = collect_tree_stats(_sample_mapping_data(), {"118669424", "214822182"})

    assert stats.skin_count == 1
    assert stats.audio_type_count == EXPECTED_FULL_AUDIO_TYPE_COUNT
    assert stats.event_count == EXPECTED_FULL_EVENT_COUNT
    assert stats.audio_id_count == EXPECTED_FULL_AUDIO_ID_COUNT
    assert stats.available_audio_id_count == EXPECTED_FULL_AVAILABLE_AUDIO_ID_COUNT


def test_collect_audio_preview_stats_counts_map_tree() -> None:
    """地图 mapping 也应统计到试听树摘要里。"""
    stats = collect_tree_stats(_sample_map_mapping_data(), {"7654321"})

    assert stats.skin_count == 1
    assert stats.audio_type_count == 1
    assert stats.event_count == 1
    assert stats.audio_id_count == EXPECTED_LEAF_AUDIO_ID_COUNT
    assert stats.available_audio_id_count == 1


def test_audio_preview_tree_model_populates_children_on_demand() -> None:
    """试听树模型应只在需要时展开下一层子节点。"""
    model = PreviewTreeModel()
    model.set_preview_data(_sample_mapping_data(), {"118669424"})

    assert model.rowCount() == 1
    skin_index = model.index(0, 0)
    assert model.data(skin_index, Qt.DisplayRole) == "1000"

    model.ensure_children_loaded(skin_index)
    type_index = _find_child_index_by_label(model, skin_index, "Annie_Base_VO")
    assert model.data(type_index, Qt.DisplayRole) == "Annie_Base_VO"

    model.ensure_children_loaded(type_index)
    event_index = _find_child_index_by_label(model, type_index, "Play_vo_Annie_Attack2DGeneral")
    assert model.data(event_index, Qt.DisplayRole) == "Play_vo_Annie_Attack2DGeneral"

    model.ensure_children_loaded(event_index)
    available_leaf = model.index(0, 0, event_index)
    unavailable_leaf = model.index(1, 0, event_index)
    assert model.data(available_leaf, Qt.DisplayRole) == "118669424"
    assert model.data(available_leaf, AUDIO_ID_ROLE) == "118669424"
    assert model.data(available_leaf, AUDIO_AVAILABLE_ROLE) is True
    assert model.data(unavailable_leaf, Qt.DisplayRole) == "223585177"
    assert model.data(unavailable_leaf, AUDIO_AVAILABLE_ROLE) is False


def test_audio_preview_tree_model_populates_map_children_on_demand() -> None:
    """试听树模型应能按需展开地图 mapping 的层级。"""
    model = PreviewTreeModel()
    model.set_preview_data(_sample_map_mapping_data(), {"7654321"})

    root_index = model.index(0, 0)
    assert model.data(root_index, Qt.DisplayRole) == "11"

    model.ensure_children_loaded(root_index)
    type_index = _find_child_index_by_label(model, root_index, "Map11_Music")
    model.ensure_children_loaded(type_index)
    event_index = _find_child_index_by_label(model, type_index, "Play_map_theme")
    model.ensure_children_loaded(event_index)
    available_leaf = model.index(0, 0, event_index)
    unavailable_leaf = model.index(1, 0, event_index)

    assert model.data(available_leaf, Qt.DisplayRole) == "7654321"
    assert model.data(available_leaf, AUDIO_AVAILABLE_ROLE) is True
    assert model.data(unavailable_leaf, Qt.DisplayRole) == "7654322"
    assert model.data(unavailable_leaf, AUDIO_AVAILABLE_ROLE) is False


def test_audio_preview_tree_view_uses_custom_preview_tree_styles() -> None:
    """试听树视图应保持基础 QTreeView 结构并注入自定义样式。"""
    QApplication.instance() or QApplication([])
    view = PreviewTreeView()

    assert isinstance(view, QTreeView)
    assert view.styleSheet() != ""
    assert hasattr(view, "audio_id_requested") is False
    assert hasattr(view, "scrollDelegate") is False
    assert isinstance(view.model(), PreviewTreeModel)


def test_audio_preview_tree_view_expands_with_basic_model_loading() -> None:
    """展开信号触发后，基础树视图也应能通过模型补齐下一层数据。"""
    QApplication.instance() or QApplication([])
    view = PreviewTreeView()
    model = view.model()
    assert isinstance(model, PreviewTreeModel)

    model.set_preview_data(_sample_mapping_data(), {"118669424"})
    root_index = model.index(0, 0)
    assert model.rowCount(root_index) == 0

    view.expanded.emit(root_index)

    assert model.rowCount(root_index) == EXPECTED_ROOT_CHILD_COUNT


def test_audio_preview_tree_mouse_expand_subprocess_does_not_crash() -> None:
    """子进程中的基础试听树展开链路不应直接崩溃。"""
    script = """
from PySide6.QtWidgets import QApplication

from lol_audio_unpack.gui.components.preview_tree import PreviewTreeModel, PreviewTreeView

app = QApplication.instance() or QApplication([])
view = PreviewTreeView()
model = view.model()
assert isinstance(model, PreviewTreeModel)
model.set_preview_data(
    {
        "skins": {
            "1000": {
                "events": {
                    "Annie_Base_VO": {
                        "Play_vo_Annie_Attack2DGeneral": [118669424, 223585177],
                    }
                }
            }
        }
    },
    {"118669424"},
)
view.resize(640, 480)
view.show()
app.processEvents()

root = model.index(0, 0)
view.expand(root)
app.processEvents()
audio_type = model.index(0, 0, root)
view.expand(audio_type)
app.processEvents()
event = model.index(0, 0, audio_type)
view.expand(event)
app.processEvents()
print("ok", model.rowCount(event))
"""
    completed = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "ok 2" in completed.stdout
