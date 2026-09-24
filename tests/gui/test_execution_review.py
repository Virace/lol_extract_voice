"""确认快照的有效范围、排除诊断与只读交互验证。"""

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QWidget

from lol_audio_unpack.gui.controllers.execution_review import build_review
from lol_audio_unpack.gui.task_models import AppContextInputSnapshot, ExecutionTaskDraft, ExecutionTaskParamsSnapshot
from lol_audio_unpack.gui.view.execution.confirmation_dialog import ConfirmationDialog


def _draft(champions, maps=()) -> ExecutionTaskDraft:
    """构造只有目标不同的独立请求。"""
    return ExecutionTaskDraft(
        source="manual",
        source_summary="待核对",
        context_input=AppContextInputSnapshot(),
        task_params=ExecutionTaskParamsSnapshot(champion_ids=champions, map_ids=maps),
    )


def test_review_partitions_ids_and_keeps_complete_diagnostics() -> None:
    """部分未知只排除未知项，地图 0 仍是有效 ID。"""
    review = build_review(
        _draft((1, 999, 1), (0, 888)),
        {
            "champions": [{"id": "1", "name": "安妮"}],
            "maps": [{"id": "0", "name": "Common"}],
        },
    )
    assert review.can_submit
    assert review.draft.task_params.champion_ids == (1,)
    assert review.draft.task_params.map_ids == (0,)
    assert review.draft.excluded_targets == ("英雄 ID 999", "地图 ID 888")
    assert review.draft.requested_targets == ("英雄 ID 1", "英雄 ID 999", "地图 ID 0", "地图 ID 888")
    assert [(item.name, item.identifier) for item in review.items[-2:]] == [("安妮", "1"), ("Common", "0")]


def test_review_freezes_all_without_including_special_content() -> None:
    """全部普通英雄固定为当前清单；显式特殊内容保留独立范围。"""
    catalog = {
        "champions": [{"id": "1", "name": "安妮"}],
        "special": [
            {"id": "66600", "key": "champion:66600", "display_name": "斗魂竞技场"},
        ],
    }
    draft = _draft(None)
    draft = replace(draft, task_params=replace(draft.task_params, special_targets=("champion:66600",)))
    review = build_review(draft, catalog)
    catalog["champions"].append({"id": "103", "name": "阿狸"})
    assert review.draft.task_params.champion_ids == (1,)
    assert review.draft.task_params.map_ids == ()
    assert review.draft.task_params.special_targets == ("champion:66600",)
    assert review.items[-1].name == "斗魂竞技场"


@pytest.mark.parametrize("ids, allowed", [((999,), False), ((1, 999), True)])
def test_confirmation_is_readonly_and_return_does_not_accept(qtbot, ids, allowed) -> None:
    """全部未知时禁止确认，返回修改只拒绝当前对话框。"""
    review = build_review(_draft(ids), {"champions": [{"id": "1", "name": "安妮"}]})
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(1000, 800)
    dialog = ConfirmationDialog(review, parent)
    qtbot.addWidget(dialog)
    assert review.can_submit is allowed
    assert dialog.yesButton.isEnabled() is allowed
    assert dialog.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert dialog.yesButton.text() == "确认"
    assert dialog.cancelButton.text() == "返回修改"
    with qtbot.waitSignal(dialog.rejected):
        qtbot.mouseClick(dialog.cancelButton, Qt.MouseButton.LeftButton)
    assert dialog.result() == 0
