"""测试实体总览试听树的 model 与 view。"""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from lol_audio_unpack.gui.view.overview_audio_tree import (
    AUDIO_AVAILABLE_ROLE,
    AUDIO_ID_ROLE,
    AudioPreviewTreeModel,
    AudioPreviewTreeView,
    build_branch_indicator_center_x,
    collect_audio_preview_stats,
)


def _find_child_index_by_label(model: AudioPreviewTreeModel, parent_index, label: str):
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


def test_collect_audio_preview_stats_counts_full_tree() -> None:
    """统计信息应覆盖完整 mapping 树，而不是只统计已展开节点。"""
    stats = collect_audio_preview_stats(_sample_mapping_data(), {"118669424", "214822182"})
    expected_audio_type_count = 2
    expected_event_count = 2
    expected_audio_id_count = 3
    expected_available_audio_id_count = 2

    assert stats.skin_count == 1
    assert stats.audio_type_count == expected_audio_type_count
    assert stats.event_count == expected_event_count
    assert stats.audio_id_count == expected_audio_id_count
    assert stats.available_audio_id_count == expected_available_audio_id_count


def test_audio_preview_tree_model_populates_children_on_demand() -> None:
    """试听树模型应只在需要时展开下一层子节点。"""
    model = AudioPreviewTreeModel()
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


def test_audio_preview_tree_view_only_emits_available_audio_id() -> None:
    """试听树视图只应为可试听叶子节点发出请求。"""
    app = QApplication.instance() or QApplication([])
    view = AudioPreviewTreeView()
    emitted_ids: list[str] = []
    view.audio_id_requested.connect(emitted_ids.append)
    view.set_preview_data(_sample_mapping_data(), {"118669424"})

    model = view.preview_model
    skin_index = model.index(0, 0)
    view.ensure_children_loaded(skin_index)
    type_index = _find_child_index_by_label(model, skin_index, "Annie_Base_VO")
    view.ensure_children_loaded(type_index)
    event_index = _find_child_index_by_label(model, type_index, "Play_vo_Annie_Attack2DGeneral")
    view.ensure_children_loaded(event_index)

    available_leaf = model.index(0, 0, event_index)
    unavailable_leaf = model.index(1, 0, event_index)

    assert view.try_emit_audio_request(available_leaf) is True
    assert view.try_emit_audio_request(unavailable_leaf) is False
    app.processEvents()

    assert emitted_ids == ["118669424"]


def test_audio_preview_tree_view_applies_fluent_tree_theme() -> None:
    """试听树应接入 Fluent 的 TreeView 样式。"""
    QApplication.instance() or QApplication([])
    view = AudioPreviewTreeView()

    assert "QTreeView" in view.styleSheet()
    assert "QTreeView::branch:selected" in view.styleSheet()


def test_branch_indicator_center_x_increases_with_depth() -> None:
    """展开箭头的水平位置应随层级递增。"""
    root_center = build_branch_indicator_center_x(depth=0, indentation=22)
    child_center = build_branch_indicator_center_x(depth=1, indentation=22)
    leaf_parent_center = build_branch_indicator_center_x(depth=2, indentation=22)

    assert root_center < child_center < leaf_parent_center


def test_audio_preview_tree_view_qtbot_can_expand_and_emit_audio_id(qtbot) -> None:
    """qtbot 应能驱动试听树展开并点击可试听 ID。"""
    view = AudioPreviewTreeView()
    qtbot.addWidget(view)
    emitted_ids: list[str] = []
    view.audio_id_requested.connect(emitted_ids.append)
    view.set_preview_data(_sample_mapping_data(), {"118669424"})
    view.resize(640, 480)
    view.show()
    qtbot.wait(10)

    model = view.preview_model
    skin_index = model.index(0, 0)
    view.expand(skin_index)
    view.ensure_children_loaded(skin_index)

    type_index = _find_child_index_by_label(model, skin_index, "Annie_Base_VO")
    view.expand(type_index)
    view.ensure_children_loaded(type_index)

    event_index = _find_child_index_by_label(model, type_index, "Play_vo_Annie_Attack2DGeneral")
    view.expand(event_index)
    view.ensure_children_loaded(event_index)

    available_leaf = model.index(0, 0, event_index)
    rect = view.visualRect(available_leaf)
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())

    assert emitted_ids == ["118669424"]


def test_audio_preview_tree_mouse_expand_subprocess_does_not_crash() -> None:
    """真实鼠标展开链路不应导致子进程直接崩溃。"""
    script = """
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from lol_audio_unpack.gui.view.overview_audio_tree import AudioPreviewTreeView

app = QApplication.instance() or QApplication([])
view = AudioPreviewTreeView()
view.set_preview_data(
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
model = view.preview_model

def click_expander(index):
    rect = view.visualRect(index)
    point = QPoint(max(6, rect.x() + 8), rect.center().y())
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    app.processEvents()

skin = model.index(0, 0)
click_expander(skin)
audio_type = model.index(0, 0, skin)
click_expander(audio_type)
event = model.index(0, 0, audio_type)
click_expander(event)
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
    assert "ok" in completed.stdout
