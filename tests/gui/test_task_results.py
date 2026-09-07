"""验证结果通知与详情独立生命周期及重试事实保留。"""

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import PushButton

from lol_audio_unpack.app.results import EntityResult, ResultStatus, RunResult, StageResult
from lol_audio_unpack.gui.controllers.task_results import TaskResultsController
from lol_audio_unpack.gui.task_models import ExecutionTaskDraft, ExecutionTaskResult, QueuedExecutionTask


def test_dismiss_reopen_and_retry_preserve_results(qtbot) -> None:
    """关闭常驻通知不丢结果，成功重试保留原始失败事实并禁止运行中再次提交。"""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(1000, 720)
    button = PushButton("查看本次结果", host)
    layout = QVBoxLayout(host)
    layout.addWidget(button)
    controller = TaskResultsController(button, feedback_parent=lambda: host, parent=host)
    host.show()
    task = QueuedExecutionTask(1, ExecutionTaskDraft("manual", "英雄 1"), "英雄 1")
    original = ExecutionTaskResult(
        ("音频解包",),
        "部分完成",
        1,
        RunResult(
            (
                StageResult.from_entities(
                    "extract",
                    (
                        EntityResult("champion", 1, ResultStatus.SUCCESS, artifacts=("1.wem",)),
                        EntityResult("champion", 2, ResultStatus.FAILED, error_message="permission denied"),
                    ),
                ),
            )
        ),
    )
    controller.receive_result(task, original)
    assert controller.notice.duration == -1
    controller.notice.close()
    qtbot.waitUntil(lambda: controller.notice is None)
    button.click()
    assert controller.drawer.isVisible()
    controller.set_busy(True)
    assert not controller.drawer.retry_all_button.isEnabled()
    qtbot.keyClick(controller.drawer, Qt.Key.Key_Escape)
    assert not controller.drawer.isVisible()
    assert controller.result is original
    retry = replace(
        task,
        task_id=2,
        draft=replace(
            task.draft,
            operation_id="retry",
            retry_of=task.draft.operation_id,
            retry_keys=frozenset(issue.key for issue in controller.issues),
        ),
    )
    success = ExecutionTaskResult(
        ("音频解包",),
        "完成",
        0.5,
        RunResult((StageResult.from_entities("extract", (EntityResult("champion", 2, ResultStatus.SUCCESS),)),)),
    )
    controller.set_busy(False)
    controller.receive_result(retry, success)
    assert all(issue.resolved for issue in controller.issues)
    assert controller.history == (original, success)
    controller.open_details()
    assert controller.drawer.model.issues[0].resolved
    controller.drawer.reject()
    controller._close_notice()
