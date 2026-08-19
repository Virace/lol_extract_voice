"""验证试听树上下文动作的可用状态。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.gui.components.preview_tree import (
    AUDIO_AMBIGUOUS_ROLE,
    AUDIO_REF_ROLE,
    PreviewTreeModel,
    PreviewTreeView,
    build_tree_summary_text,
    collect_tree_stats,
)


def _make_ref(relative_path: str) -> AudioRef:
    """构造事件树测试需要的路径级音频引用。"""
    return AudioRef(
        relative_path=relative_path,
        path=Path("audios") / relative_path,
        wem_id=Path(relative_path).stem,
        audio_type="VO",
        sub_entity="1000",
    )


def _event_leaf_indexes(model: PreviewTreeModel):
    """展开单事件树并返回其音频叶子索引。"""
    root = model.index(0, 0)
    model.ensure_children_loaded(root)
    audio_type = model.index(0, 0, root)
    model.ensure_children_loaded(audio_type)
    event = model.index(0, 0, audio_type)
    model.ensure_children_loaded(event)
    return [model.index(row, 0, event) for row in range(model.rowCount(event))]


def test_preview_tree_context_audio_ref_requires_valid_index(qtbot, monkeypatch) -> None:
    view = PreviewTreeView()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "indexAt", lambda _pos: QModelIndex(), raising=False)

    assert view._context_audio_ref_at(QPoint(12, 12)) is None


def test_preview_tree_context_audio_ref_returns_available_audio_ref(qtbot, monkeypatch) -> None:
    view = PreviewTreeView()
    qtbot.addWidget(view)

    class _FakeIndex:
        def isValid(self) -> bool:
            return True

    index = _FakeIndex()
    monkeypatch.setattr(view, "indexAt", lambda _pos: index, raising=False)
    monkeypatch.setattr(view, "_is_audio_leaf", lambda item: item is index, raising=False)
    monkeypatch.setattr(view, "_is_audio_available", lambda item: item is index, raising=False)
    audio_ref = _make_ref("1000/VO/1001.wem")
    monkeypatch.setattr(view, "_audio_ref_for_index", lambda item: audio_ref if item is index else None, raising=False)

    assert view._context_audio_ref_at(QPoint(12, 12)) == audio_ref


def test_preview_tree_uses_event_audio_paths_for_exact_duplicate_id(qtbot) -> None:
    view = PreviewTreeView()
    qtbot.addWidget(view)
    model = view.model()
    assert isinstance(model, PreviewTreeModel)
    first = _make_ref("1000/VO/1001.wem")
    second = _make_ref("1001/VO/1001.wem")
    model.set_preview_data(
        {
            "skins": {
                "1000": {
                    "events": {"VO": {"evt": ["1001"]}},
                    "audioPaths": {"VO": {"evt": [second.relative_path]}},
                }
            }
        },
        (first, second),
    )

    leaf = _event_leaf_indexes(model)[0]

    assert model.data(leaf, AUDIO_REF_ROLE) == second
    assert model.data(leaf, AUDIO_AMBIGUOUS_ROLE) is False


def test_preview_tree_marks_legacy_duplicate_id_as_ambiguous(qtbot) -> None:
    view = PreviewTreeView()
    qtbot.addWidget(view)
    model = view.model()
    assert isinstance(model, PreviewTreeModel)
    model.set_preview_data(
        {"skins": {"1000": {"events": {"VO": {"evt": ["1001"]}}}}},
        (_make_ref("1000/VO/1001.wem"), _make_ref("1001/VO/1001.wem")),
    )

    leaf = _event_leaf_indexes(model)[0]

    assert model.data(leaf, AUDIO_REF_ROLE) is None
    assert model.data(leaf, AUDIO_AMBIGUOUS_ROLE) is True
    assert "全部音频" in model.data(leaf)


def test_preview_tree_does_not_fallback_when_exact_mapping_path_is_missing(qtbot) -> None:
    view = PreviewTreeView()
    qtbot.addWidget(view)
    model = view.model()
    assert isinstance(model, PreviewTreeModel)
    model.set_preview_data(
        {
            "skins": {
                "1000": {
                    "events": {"VO": {"evt": ["1001"]}},
                    "audioPaths": {"VO": {"evt": ["missing/VO/1001.wem"]}},
                }
            }
        },
        (_make_ref("1000/VO/1001.wem"),),
    )

    leaf = _event_leaf_indexes(model)[0]

    assert model.data(leaf, AUDIO_REF_ROLE) is None
    assert model.data(leaf, AUDIO_AMBIGUOUS_ROLE) is False
    assert "映射路径当前不可用" in model.data(leaf)


def test_collect_tree_stats_does_not_count_missing_exact_mapping_path() -> None:
    """明确存在但未落盘的 mapping 路径不得按同 ID 回退统计。"""
    mapping_data = {
        "skins": {
            "1000": {
                "events": {"VO": {"evt": ["1001"]}},
                "audioPaths": {"VO": {"evt": ["missing/VO/1001.wem"]}},
            }
        }
    }

    stats = collect_tree_stats(mapping_data, (_make_ref("1000/VO/1001.wem"),))

    assert stats.available_audio_id_count == 0
    assert "可试听 0" in build_tree_summary_text(stats)


def test_collect_tree_stats_does_not_count_legacy_duplicate_id_as_playable() -> None:
    """旧 mapping 的同 ID 多路径候选必须保持不可试听。"""
    mapping_data = {"skins": {"1000": {"events": {"VO": {"evt": ["1001"]}}}}}

    stats = collect_tree_stats(
        mapping_data,
        (
            _make_ref("1000/VO/1001.wem"),
            _make_ref("1001/VO/1001.wem"),
        ),
    )

    assert stats.available_audio_id_count == 0
    assert "可试听 0" in build_tree_summary_text(stats)
