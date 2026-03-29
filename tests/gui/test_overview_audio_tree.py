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
EXPECTED_ACTIVE_AUDIO_PROGRESS = 0.35


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


def _expand_to_first_audio_id_leaf(model: PreviewTreeModel) -> tuple[object, object, object, object]:
    """展开样例树并返回第一对可用/不可用音频叶子索引。"""
    skin_index = model.index(0, 0)
    model.ensure_children_loaded(skin_index)
    type_index = _find_child_index_by_label(model, skin_index, "Annie_Base_VO")
    model.ensure_children_loaded(type_index)
    event_index = _find_child_index_by_label(model, type_index, "Play_vo_Annie_Attack2DGeneral")
    model.ensure_children_loaded(event_index)
    available_leaf = model.index(0, 0, event_index)
    unavailable_leaf = model.index(1, 0, event_index)
    return skin_index, type_index, event_index, available_leaf, unavailable_leaf


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


def test_audio_preview_tree_model_uses_group_label_map_for_root_labels() -> None:
    """试听树模型应允许首层分组显示更友好的皮肤文案。"""
    model = PreviewTreeModel()
    model.set_preview_data(
        _sample_mapping_data(),
        {"118669424"},
        group_label_map={"1000": "基础皮肤"},
    )

    skin_index = model.index(0, 0)

    assert model.data(skin_index, Qt.DisplayRole) == "基础皮肤"


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
    assert hasattr(view, "scrollDelegate")
    assert view.isAnimated() is True
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


def test_audio_preview_tree_view_tracks_audio_playback_state() -> None:
    """试听树应缓存当前播放叶子与进度状态。"""
    QApplication.instance() or QApplication([])
    view = PreviewTreeView()

    view.set_audio_playback_state(
        "118669424",
        progress=EXPECTED_ACTIVE_AUDIO_PROGRESS,
        is_playing=True,
        is_paused=False,
    )

    assert view._active_audio_id == "118669424"
    assert view._active_audio_progress == EXPECTED_ACTIVE_AUDIO_PROGRESS
    assert view._active_audio_is_playing is True
    assert view._active_audio_is_paused is False


def test_audio_preview_tree_view_emits_toggle_signal_for_available_audio_leaf(qtbot) -> None:
    """点击可试听叶子行的播放按钮后应发出 audio id 切换信号。"""
    view = PreviewTreeView()
    qtbot.addWidget(view)
    view.resize(520, 360)
    model = view.model()
    assert isinstance(model, PreviewTreeModel)
    model.set_preview_data(_sample_mapping_data(), {"118669424"})
    view.show()
    qtbot.wait(10)

    skin_index, type_index, event_index, available_leaf, unavailable_leaf = _expand_to_first_audio_id_leaf(model)
    view.expand(skin_index)
    view.expand(type_index)
    view.expand(event_index)
    qtbot.wait(10)

    emitted_audio_ids: list[str] = []
    view.audio_id_toggle_requested.connect(emitted_audio_ids.append)
    available_button_rect = view._audio_control_rect_for_index(available_leaf)
    unavailable_button_rect = view._audio_control_rect_for_index(unavailable_leaf)

    assert available_button_rect.isValid()
    assert unavailable_button_rect.isNull()

    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=available_button_rect.center())

    assert emitted_audio_ids == ["118669424"]


def test_audio_preview_tree_view_does_not_keep_selection_fill_on_non_leaf_rows(qtbot) -> None:
    """非叶子节点被选中时，仍应保留正常的选中高亮。"""
    view = PreviewTreeView()
    qtbot.addWidget(view)
    model = view.model()
    assert isinstance(model, PreviewTreeModel)
    model.set_preview_data(_sample_mapping_data(), {"118669424"})

    skin_index, type_index, event_index, _available_leaf, _unavailable_leaf = _expand_to_first_audio_id_leaf(model)
    view.setCurrentIndex(event_index)
    qtbot.wait(10)

    assert view._current_row_color(event_index) is not None


def test_audio_preview_tree_view_non_leaf_rows_do_not_treat_none_as_active_audio(qtbot) -> None:
    """未进入播放态时，非叶子节点不应因 ``None == None`` 被误判成活动音频。"""
    view = PreviewTreeView()
    qtbot.addWidget(view)
    view.resize(640, 480)
    model = view.model()
    assert isinstance(model, PreviewTreeModel)
    model.set_preview_data(_sample_mapping_data(), {"118669424"})

    skin_index, type_index, event_index, _available_leaf, _unavailable_leaf = _expand_to_first_audio_id_leaf(model)
    view.expand(skin_index)
    view.expand(type_index)
    view.expand(event_index)
    view.show()
    qtbot.wait(10)

    assert view._active_audio_id is None
    assert view._current_row_color(skin_index) is None
    assert view._current_row_color(type_index) is None
    assert view._current_row_color(event_index) is None


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
