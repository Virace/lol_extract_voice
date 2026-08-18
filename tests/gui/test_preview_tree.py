"""验证试听树上下文动作的可用状态。"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint

from lol_audio_unpack.gui.components.preview_tree import PreviewTreeView


def test_preview_tree_context_audio_id_requires_valid_index(qtbot, monkeypatch) -> None:
    view = PreviewTreeView()
    qtbot.addWidget(view)
    monkeypatch.setattr(view, "indexAt", lambda _pos: QModelIndex(), raising=False)

    assert view._context_audio_id_at(QPoint(12, 12)) is None


def test_preview_tree_context_audio_id_returns_available_audio_id(qtbot, monkeypatch) -> None:
    view = PreviewTreeView()
    qtbot.addWidget(view)

    class _FakeIndex:
        def isValid(self) -> bool:
            return True

    index = _FakeIndex()
    monkeypatch.setattr(view, "indexAt", lambda _pos: index, raising=False)
    monkeypatch.setattr(view, "_is_audio_leaf", lambda item: item is index, raising=False)
    monkeypatch.setattr(view, "_is_audio_available", lambda item: item is index, raising=False)
    monkeypatch.setattr(view, "_audio_id_for_index", lambda item: "1001" if item is index else None, raising=False)

    assert view._context_audio_id_at(QPoint(12, 12)) == "1001"
