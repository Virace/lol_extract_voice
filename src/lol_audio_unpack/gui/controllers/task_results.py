"""持有最近任务结果、常驻通知和失败重试关联。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget
from qfluentwidgets import PushButton
from shiboken6 import isValid

from lol_audio_unpack.app.failures import TaskFailure, collect_failures, reconcile_failures
from lol_audio_unpack.app.results import ResultStatus
from lol_audio_unpack.gui.common.feedback import show_feedback_infobar
from lol_audio_unpack.gui.components.result_drawer import ResultDrawer
from lol_audio_unpack.gui.service.task_retry import build_retry_stages
from lol_audio_unpack.gui.task_models import ExecutionTaskResult, QueuedExecutionTask

_SUBJECT_LIMIT = 70


class TaskResultsController(QObject):
    """把结果生命周期与通知生命周期分开，关闭提示仍可恢复详情。"""

    retry_requested = Signal(object)

    def __init__(self, button: PushButton, *, feedback_parent: Callable[[], QWidget], parent=None) -> None:
        """绑定标题区恢复入口，详情按需创建。"""
        super().__init__(parent)
        self.button = button
        self._feedback_parent = feedback_parent
        self.task: QueuedExecutionTask | None = None
        self.result: ExecutionTaskResult | None = None
        self.history: tuple[ExecutionTaskResult, ...] = ()
        self.issues: tuple[TaskFailure, ...] = ()
        self.attempts = 0
        self.drawer: ResultDrawer | None = None
        self.notice = None
        self.busy = False
        self._return_focus: QWidget | None = None
        self.button.hide()
        self.button.clicked.connect(self.open_details)

    def set_busy(self, busy: bool) -> None:
        """任务启动时收起旧通知；旧结果仍能从标题区查看。"""
        self.busy = busy
        self.button.setText("查看上次结果" if busy else "查看本次结果")
        if busy:
            self._close_notice()
        if self.drawer is not None:
            self.drawer.set_busy(busy)

    def receive_result(self, task: QueuedExecutionTask, result: ExecutionTaskResult) -> None:
        """保存当前操作快照，重试只更新已尝试失败项的解决状态。"""
        if self.task is not None and task.draft.retry_of == self.task.draft.operation_id:
            self.issues = reconcile_failures(self.issues, result.run_result, result.wav_batches, task.draft.retry_keys)
            self.attempts += 1
        else:
            self.task = task
            self.issues = collect_failures(result.run_result, result.wav_batches)
            self.attempts = 0
            self.history = ()
        self.history += (result,)
        self.result = result
        self.button.show()
        self.button.setText("查看本次结果")
        self._close_notice()
        status = result.run_result.status
        if any(not issue.resolved for issue in self.issues) and status is ResultStatus.SUCCESS:
            status = ResultStatus.PARTIAL
        title, level = {
            ResultStatus.SUCCESS: ("任务执行完成", "success"),
            ResultStatus.PARTIAL: ("任务部分完成", "warning"),
            ResultStatus.FAILED: ("任务执行失败", "error"),
            ResultStatus.CANCELLED: ("任务已取消", "warning"),
        }[status]
        subject = self.task.draft.source_summary
        if len(subject) > _SUBJECT_LIMIT:
            subject = subject[: _SUBJECT_LIMIT - 1] + "…"
        count = sum(not issue.resolved for issue in self.issues)
        content = subject + (f" · {count} 项待处理，详情中按文件、容器或实体区分" if count else " · 可查看本次结果")
        self.notice = show_feedback_infobar(
            parent=self._feedback_parent(), title=title, content=content, level=level, duration=-1
        )
        notice = self.notice
        action = PushButton("查看详情", notice)
        action.clicked.connect(self.open_details)
        notice.addWidget(action)
        notice.destroyed.connect(lambda *_: self._notice_destroyed(notice))
        if self.drawer is not None:
            self.drawer.set_result(self.task, result, self.issues, attempts=self.attempts, history=self.history)

    def _notice_destroyed(self, notice) -> None:
        if self.notice is notice:
            self.notice = None

    def _close_notice(self) -> None:
        notice = self.notice
        self.notice = None
        if notice is not None and isValid(notice):
            notice.close()

    def open_details(self) -> None:
        """在原页面上覆盖打开详情，不切换主路由。"""
        if self.task is None or self.result is None:
            return
        host = self._feedback_parent()
        self._return_focus = host.focusWidget()
        if self.drawer is None:
            self.drawer = ResultDrawer(host)
            self.drawer.retry_requested.connect(self.review_retry)
            self.drawer.finished.connect(self._restore_focus)
        self.drawer.set_result(self.task, self.result, self.issues, attempts=self.attempts, history=self.history)
        self.drawer.set_busy(self.busy)
        self.drawer.open()

    def _restore_focus(self, *_args) -> None:
        focus = self._return_focus
        if focus is not None and isValid(focus) and focus.isVisible():
            focus.setFocus()
        elif self.button.isVisible():
            self.button.setFocus()

    def review_retry(self, issues: tuple[TaskFailure, ...]) -> None:
        """展示真实重试范围，确认后提交限定阶段的单次执行请求。"""
        if self.busy or self.task is None:
            return
        active = tuple(issue for issue in issues if issue.retry_mode not in {"none", "diagnostics"})
        plan = build_retry_stages(self.task.draft.task_params, active)
        if not plan:
            return
        dialog = QMessageBox(self.drawer or self._feedback_parent())
        dialog.setWindowTitle("核对失败重试范围")
        dialog.setText(self.task.draft.source_summary)
        outputs = tuple(dict.fromkeys(issue.output_path for issue in active if issue.output_path))
        dialog.setInformativeText(
            "\n".join(stage.label for stage in plan)
            + "\n复用原任务的格式和输出位置。请先处理权限、空间或输入问题；未知解析错误直接重试可能无效。"
            + ("\n输出示例：" + "\n".join(outputs[:3]) if outputs else "")
        )
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dialog.button(QMessageBox.StandardButton.Ok).setText("按此范围重试")
        dialog.button(QMessageBox.StandardButton.Cancel).setText("返回详情")
        if dialog.exec() != int(QMessageBox.StandardButton.Ok):
            return
        draft = replace(
            self.task.draft,
            operation_id=uuid4().hex,
            source="failure_retry",
            export_request=None,
            retry_of=self.task.draft.operation_id,
            retry_stages=plan,
            retry_keys=frozenset(issue.key for issue in active),
        )
        self.retry_requested.emit(draft)
