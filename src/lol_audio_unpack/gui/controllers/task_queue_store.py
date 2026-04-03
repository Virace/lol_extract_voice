"""执行中心任务队列的纯状态存储。"""

from __future__ import annotations

from dataclasses import replace

from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    QueuedExecutionTask,
)


def build_task_queue_row_text(task: QueuedExecutionTask) -> str:
    """构造任务队列日志与通知使用的单行摘要。"""
    return f"#{task.task_id} · [{task.status}] {task.summary}"


class TaskQueueStore:
    """维护执行任务列表及其状态快照。"""

    def __init__(self) -> None:
        """初始化空任务队列。"""
        self._tasks: list[QueuedExecutionTask] = []

    def task_count(self) -> int:
        """返回当前任务数量。"""
        return len(self._tasks)

    def tasks(self) -> tuple[QueuedExecutionTask, ...]:
        """返回当前全部任务快照。"""
        return tuple(self._tasks)

    def status_counts(self) -> dict[str, int]:
        """统计当前队列中的任务状态数量。"""
        counts = {
            TASK_STATUS_RUNNING: 0,
            TASK_STATUS_WAITING: 0,
            TASK_STATUS_COMPLETED: 0,
            TASK_STATUS_FAILED: 0,
            TASK_STATUS_CANCELLED: 0,
        }
        for task in self._tasks:
            if task.status in counts:
                counts[task.status] += 1
        return counts

    def find_task_by_id(self, task_id: int) -> QueuedExecutionTask | None:
        """按任务编号查找任务。"""
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        return None

    def find_running_task(self) -> QueuedExecutionTask | None:
        """返回当前运行中的任务。"""
        for task in self._tasks:
            if task.status == TASK_STATUS_RUNNING:
                return task
        return None

    def append_task(self, task: QueuedExecutionTask) -> QueuedExecutionTask:
        """将任务追加到队列尾部。"""
        self._tasks.append(task)
        return task

    def update_task(self, task_id: int, **changes) -> QueuedExecutionTask:
        """按任务编号更新任务快照。"""
        for index, task in enumerate(self._tasks):
            if task.task_id != task_id:
                continue
            updated_task = replace(task, **changes)
            self._tasks[index] = updated_task
            return updated_task
        raise KeyError(f"任务 #{task_id} 不存在。")

    def clear_tasks(self) -> int:
        """清空全部任务并返回删除数量。"""
        removed_count = len(self._tasks)
        self._tasks.clear()
        return removed_count

    def clear_non_running_tasks(self) -> int:
        """清空所有非运行中的任务并返回删除数量。"""
        retained_tasks = [task for task in self._tasks if task.status == TASK_STATUS_RUNNING]
        removed_count = len(self._tasks) - len(retained_tasks)
        self._tasks = retained_tasks
        return removed_count
