"""测试基础预览树组件的集成行为。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from lol_audio_unpack.gui.components.preview_tree import PreviewTreeModel, PreviewTreeView

EXPECTED_ROOT_NODE_COUNT = 2


def _sample_mapping_data() -> dict:
    """返回一份最小的多层预览树数据。"""
    return {
        "skins": {
            "4000": {
                "events": {
                    "TwistedFate_Base_SFX": {
                        "Play_sfx_TwistedFate_Test": [1, 2],
                    }
                }
            },
            "4003": {
                "events": {
                    "TwistedFate_Alt_SFX": {
                        "Play_sfx_TwistedFate_Alt": [3],
                    }
                }
            },
        }
    }


def test_preview_tree_view_uses_preview_tree_model() -> None:
    """组件应注入自定义树样式并挂载自定义模型。"""
    QApplication.instance() or QApplication([])
    view = PreviewTreeView()

    assert isinstance(view.model(), PreviewTreeModel)
    assert view.styleSheet() != ""
    assert "border: 1px solid" not in view.styleSheet()
    assert hasattr(view, "audio_id_requested") is False
    assert hasattr(view, "scrollDelegate")
    assert view.isAnimated() is True


def test_preview_tree_nodes_do_not_expose_native_tooltips() -> None:
    """试听树节点不应通过 ToolTipRole 触发系统原生浮层。"""
    QApplication.instance() or QApplication([])
    view = PreviewTreeView()
    model = view.model()
    assert isinstance(model, PreviewTreeModel)
    model.set_preview_data(_sample_mapping_data(), {"1"})

    root_index = model.index(0, 0)
    model.ensure_children_loaded(root_index)
    child_index = model.index(0, 0, root_index)

    assert model.data(root_index, Qt.ItemDataRole.ToolTipRole) is None
    assert model.data(child_index, Qt.ItemDataRole.ToolTipRole) is None


def test_preview_tree_view_clear_preview_resets_model() -> None:
    """清空预览后，树模型应回到空状态。"""
    QApplication.instance() or QApplication([])
    view = PreviewTreeView()
    model = view.model()
    assert isinstance(model, PreviewTreeModel)

    model.set_preview_data(_sample_mapping_data(), {"1"})
    assert model.rowCount() == EXPECTED_ROOT_NODE_COUNT

    model.clear_preview()

    assert model.rowCount() == 0
